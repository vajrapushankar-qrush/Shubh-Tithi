"""Assemble a full Panchang for one city-day.

Read path: cached rise/set (city_days) + cached element boundaries
(global_events) + a little live computation for month / samvatsara / solar month
/ eclipse visibility. Everything is computed as UT instants and rendered into the
city's local timezone here, at the presentation edge.

Hindu day = local sunrise -> next local sunrise. Each anga "for the date" is the
one prevailing at that sunrise; we also list every anga *touching* the day
(so vriddhi/repeated and kshaya/skipped tithis are all reported) with end times.
"""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.astronomy.core import jd_to_datetime, moon_longitude, sun_longitude
from app.cache.city_cache import get_or_compute_day
from app.cache.global_events import (
    eclipses_overlapping,
    events_in_window,
    next_event_after,
)
from app.db import GlobalEvent
from app.panchang import elements, months, names, windows
from app.panchang.eclipses import visible_from

_EPS = 1.0 / 86400.0  # one second in JD


def _render(jd: float | None, tz: ZoneInfo) -> str | None:
    if jd is None:
        return None
    return jd_to_datetime(jd).astimezone(tz).isoformat()


def _segments(session, event_type: str, sunrise: float, next_sunrise: float):
    """Return [(idx, start_jd, end_jd)] for every element of ``event_type``
    touching [sunrise, next_sunrise)."""
    win = events_in_window(session, event_type, sunrise, next_sunrise)
    segs: list[tuple[int, float, float]] = []
    if not win:
        nxt = next_event_after(session, event_type, sunrise)
        if nxt is not None:
            segs.append((nxt[1], sunrise, nxt[0]))
        return segs
    start = sunrise
    for end_jd, idx in win:
        segs.append((idx, start, end_jd))
        start = end_jd
    # Tail element active at next sunrise (started before it -> touches the day).
    if win[-1][0] < next_sunrise - _EPS:
        tail = next_event_after(session, event_type, win[-1][0] + _EPS)
        if tail is not None:
            segs.append((tail[1], start, tail[0]))
    return segs


def _amavasya_around(session, sunrise: float):
    prev = session.execute(
        select(GlobalEvent.end_jd)
        .where(GlobalEvent.event_type == "tithi", GlobalEvent.idx == 29,
               GlobalEvent.end_jd <= sunrise)
        .order_by(GlobalEvent.end_jd.desc()).limit(1)
    ).scalar()
    nxt = session.execute(
        select(GlobalEvent.end_jd)
        .where(GlobalEvent.event_type == "tithi", GlobalEvent.idx == 29,
               GlobalEvent.end_jd > sunrise)
        .order_by(GlobalEvent.end_jd).limit(1)
    ).scalar()
    return prev, nxt


def _lunar_month(session, sunrise: float, tithi_no_at_sunrise: int) -> dict:
    """DB-backed amanta/purnimanta month + adhika flag, with a live fallback."""
    prev_nm, next_nm = _amavasya_around(session, sunrise)
    if prev_nm is None or next_nm is None:
        # Near a cache edge: fall back to the fully-live computation.
        return months.lunar_month(sunrise, elements.make_angle_funcs())

    r_start = elements.rashi_index(sun_longitude(prev_nm + _EPS))
    r_end = elements.rashi_index(sun_longitude(next_nm - _EPS))
    if r_end != r_start:
        amanta_idx = (r_end + 1) % 12
        adhika = False
    else:
        amanta_idx = (r_start + 2) % 12
        adhika = True

    paksha = names.tithi_paksha(tithi_no_at_sunrise)
    purnimanta_idx = amanta_idx if paksha == "Shukla" else (amanta_idx + 1) % 12
    return {
        "amanta": ("Adhika " if adhika else "") + names.LUNAR_MONTHS[amanta_idx],
        "purnimanta": names.LUNAR_MONTHS[purnimanta_idx],
        "adhika_masa": adhika,
        "amanta_index": amanta_idx,
    }


def _solar_month(session, sunrise: float, tz: ZoneInfo) -> dict:
    r = elements.rashi_index(sun_longitude(sunrise))
    # Current solar month began at the previous Sun-rashi ingress; the next
    # ingress ends it. Both are cached sun_rashi boundaries.
    prev_ingress = session.execute(
        select(GlobalEvent.end_jd)
        .where(GlobalEvent.event_type == "sun_rashi", GlobalEvent.end_jd <= sunrise)
        .order_by(GlobalEvent.end_jd.desc()).limit(1)
    ).scalar()
    next_ingress = session.execute(
        select(GlobalEvent.end_jd)
        .where(GlobalEvent.event_type == "sun_rashi", GlobalEvent.end_jd > sunrise)
        .order_by(GlobalEvent.end_jd).limit(1)
    ).scalar()
    return {
        "tamil_month": names.TAMIL_MONTHS[r],
        "malayalam_month": names.MALAYALAM_MONTHS[r],
        "bengali_month": names.BENGALI_MONTHS[r],
        "current_sankranti": _render(prev_ingress, tz),
        "next_sankranti": _render(next_ingress, tz),
    }


def derive_panchang(session, city, d: date) -> dict:
    tz = ZoneInfo(city.tz)
    day = get_or_compute_day(session, city, d)
    next_day = get_or_compute_day(session, city, d + timedelta(days=1))

    sunrise = day.sunrise_jd
    if sunrise is None:
        # Polar day/night: no sunrise. Report rise/set as null and skip
        # sunrise-anchored angas gracefully.
        return {
            "date": d.isoformat(),
            "city": {"id": city.id, "name": city.name, "country": city.country,
                     "timezone": city.tz, "lat": city.lat, "lon": city.lon},
            "note": "No sunrise at this location on this date (polar day/night).",
            "sun": {"sunrise": None, "sunset": _render(day.sunset_jd, tz)},
        }
    next_sunrise = next_day.sunrise_jd or (sunrise + 1.0)

    # --- Vara (weekday of the day at sunrise) ---
    weekday_sun0 = (d.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> Sun=0..Sat=6

    # --- Longitudes at sunrise (for pada + rashi values) ---
    moon_sr = moon_longitude(sunrise)

    # --- Tithi list ---
    tithi_segs = _segments(session, "tithi", sunrise, next_sunrise)
    tithis = [
        {**elements.describe_tithi(idx), "end": _render(end, tz)}
        for idx, _s, end in tithi_segs
    ]

    # --- Nakshatra list (pada from moon longitude at each segment start) ---
    nak_segs = _segments(session, "nakshatra", sunrise, next_sunrise)
    nakshatras = []
    for idx, seg_start, end in nak_segs:
        pada = elements.nakshatra_pada(moon_longitude(seg_start))
        nakshatras.append({**elements.describe_nakshatra(idx, pada), "end": _render(end, tz)})

    # --- Yoga list ---
    yoga_segs = _segments(session, "yoga", sunrise, next_sunrise)
    yogas = [
        {**elements.describe_yoga(idx), "end": _render(end, tz)}
        for idx, _s, end in yoga_segs
    ]

    # --- Karana list (+ Bhadra/Vishti windows) ---
    karana_segs = _segments(session, "karana", sunrise, next_sunrise)
    karanas = []
    bhadra = []
    for idx, seg_start, end in karana_segs:
        name = names.karana_name(idx % 60)
        karanas.append({"name": name, "end": _render(end, tz)})
        if name == names.VISHTI:
            bhadra.append({"start": _render(max(seg_start, sunrise), tz), "end": _render(end, tz)})

    # --- Moon & Sun rashi (with transition if it lands in the day) ---
    def rashi_field(event_type):
        segs = _segments(session, event_type, sunrise, next_sunrise)
        first_idx = segs[0][0] if segs else elements.rashi_index(
            sun_longitude(sunrise) if event_type == "sun_rashi" else moon_sr)
        out = elements.describe_rashi(first_idx)
        # A transition within the day = the first segment ends before next sunrise.
        if segs and segs[0][2] < next_sunrise - _EPS:
            out["transition"] = _render(segs[0][2], tz)
            out["next"] = elements.describe_rashi(segs[1][0])["name"] if len(segs) > 1 else \
                elements.describe_rashi((first_idx + 1) % 12)["name"]
        else:
            out["transition"] = None
        return out

    moon_rashi = rashi_field("moon_rashi")
    sun_rashi = rashi_field("sun_rashi")

    # --- Windows ---
    sunset = day.sunset_jd or sunrise
    win = windows.inauspicious_windows(sunrise, sunset, weekday_sun0)
    abhijit = windows.abhijit_muhurat(sunrise, sunset, weekday_sun0)

    # Auspicious muhurat bands (Choghadiya) + Brahma Muhurat.
    chogh = windows.choghadiya(sunrise, sunset, next_sunrise, weekday_sun0)
    prev_day = get_or_compute_day(session, city, d - timedelta(days=1))
    brahma = (
        windows.brahma_muhurat(prev_day.sunset_jd, sunrise)
        if prev_day and prev_day.sunset_jd else None
    )

    # --- Month / samvatsara / years ---
    tithi_no_at_sunrise = tithis[0]["number"] if tithis else 1
    lm = _lunar_month(session, sunrise, tithi_no_at_sunrise)
    years = months.samvatsara_and_years(sunrise, elements.make_angle_funcs(), d.year)

    # --- Solar months ---
    solar = _solar_month(session, sunrise, tz)

    # --- Eclipse ---
    eclipse = None
    for ecl in eclipses_overlapping(session, sunrise, next_sunrise):
        eclipse = {
            "kind": ecl.kind,
            "type": ecl.type,
            "max": _render(ecl.max_jd, tz),
            "begin": _render(ecl.begin_jd, tz),
            "end": _render(ecl.end_jd, tz),
            "visible_here": visible_from(ecl.kind, ecl.max_jd, city.lat, city.lon),
        }
        break  # at most one eclipse per day in practice

    return {
        "date": d.isoformat(),
        "city": {
            "id": city.id, "name": city.name, "state": city.state,
            "country": city.country, "timezone": city.tz,
            "lat": city.lat, "lon": city.lon,
        },
        "vara": {"name": names.VARAS[weekday_sun0], "english": names.VARA_ENGLISH[weekday_sun0]},
        "tithi": tithis,
        "nakshatra": nakshatras,
        "yoga": yogas,
        "karana": karanas,
        "moon_rashi": moon_rashi,
        "sun_rashi": sun_rashi,
        "lunar_month": {
            "amanta": lm["amanta"], "purnimanta": lm["purnimanta"],
            "adhika_masa": lm["adhika_masa"],
        },
        "samvatsara": years["samvatsara"],
        "shaka_year": years["shaka_year"],
        "vikram_year": years["vikram_year"],
        "solar_month": solar,
        "sun": {
            "sunrise": _render(sunrise, tz),
            "sunset": _render(day.sunset_jd, tz),
        },
        "moon": {
            "moonrise": _render(day.moonrise_jd, tz),
            "moonset": _render(day.moonset_jd, tz),
        },
        "inauspicious": {
            "rahu_kalam": _window_dict(win["rahu_kalam"], tz),
            "yamaganda": _window_dict(win["yamaganda"], tz),
            "gulika_kalam": _window_dict(win["gulika_kalam"], tz),
        },
        "auspicious": {
            "abhijit_muhurat": {
                "start": _render(abhijit["start_jd"], tz),
                "end": _render(abhijit["end_jd"], tz),
                "avoided_today": abhijit["avoided_today"],
            },
            "brahma_muhurat": (
                {"start": _render(brahma["start_jd"], tz),
                 "end": _render(brahma["end_jd"], tz)}
                if brahma else None
            ),
        },
        "choghadiya": {
            "day": [_chogh_band(b, tz) for b in chogh["day"]],
            "night": [_chogh_band(b, tz) for b in chogh["night"]],
        },
        # Kept at top level for backward compatibility with earlier consumers.
        "abhijit_muhurat": {
            "start": _render(abhijit["start_jd"], tz),
            "end": _render(abhijit["end_jd"], tz),
            "avoided_today": abhijit["avoided_today"],
        },
        "bhadra": bhadra,
        "eclipse": eclipse,
    }


def _window_dict(pair: tuple[float, float], tz: ZoneInfo) -> dict:
    return {"start": _render(pair[0], tz), "end": _render(pair[1], tz)}


def _chogh_band(band: dict, tz: ZoneInfo) -> dict:
    return {
        "name": band["name"],
        "quality": band["quality"],
        "start": _render(band["start_jd"], tz),
        "end": _render(band["end_jd"], tz),
    }
