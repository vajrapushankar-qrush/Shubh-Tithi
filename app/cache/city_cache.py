"""Per-city sunrise/sunset/moonrise/moonset caching with lazy 15-month
extension, plus ensuring the shared global-events table covers the span.

First request for a city computes a horizon (default 15 months) starting from
``min(requested_date, today)`` and serves. Later requests are pure lookups; a
request past the cached horizon transparently extends the cache by another
horizon from the gap.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.astronomy.core import MOON, SUN, datetime_to_jd, rise_set
from app.cache.global_events import ensure_global_coverage
from app.config import get_settings
from app.db import City, CityDay

log = logging.getLogger("shubhtithi.citycache")


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    # Clamp day to end of target month.
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 or not year % 400) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _local_midnight_jd(d: date, tz: ZoneInfo) -> float:
    return datetime_to_jd(datetime(d.year, d.month, d.day, tzinfo=tz))


def compute_rise_set(d: date, tz: ZoneInfo, lat: float, lon: float) -> dict:
    """Sun/Moon rise & set for calendar date ``d`` at the location.

    Sun uses the configured convention (default: apparent upper-limb with
    refraction, matching published almanacs). Moon rise/set are constrained to the
    calendar day (``None`` when the Moon does not rise/set that day)."""
    settings = get_settings()
    jd0 = _local_midnight_jd(d, tz)
    jd_end = jd0 + 1.0
    ul, refr = settings.sunrise_upper_limb, settings.sunrise_refraction

    sunrise = rise_set(jd0, SUN, rising=True, lat=lat, lon=lon,
                       upper_limb=ul, refraction=refr)
    sunset = rise_set(sunrise if sunrise else jd0, SUN, rising=False, lat=lat,
                      lon=lon, upper_limb=ul, refraction=refr)
    moonrise = rise_set(jd0, MOON, rising=True, lat=lat, lon=lon,
                        upper_limb=ul, refraction=refr)
    moonset = rise_set(jd0, MOON, rising=False, lat=lat, lon=lon,
                       upper_limb=ul, refraction=refr)

    if moonrise is not None and moonrise >= jd_end:
        moonrise = None
    if moonset is not None and moonset >= jd_end:
        moonset = None
    return {"sunrise_jd": sunrise, "sunset_jd": sunset,
            "moonrise_jd": moonrise, "moonset_jd": moonset}


def _store_days(session, city: City, d_from: date, d_to: date) -> int:
    tz = ZoneInfo(city.tz)
    existing = set(
        session.scalars(
            select(CityDay.date).where(
                CityDay.city_id == city.id,
                CityDay.date >= d_from.isoformat(),
                CityDay.date <= d_to.isoformat(),
            )
        )
    )
    rows = []
    d = d_from
    while d <= d_to:
        iso = d.isoformat()
        if iso not in existing:
            rs = compute_rise_set(d, tz, city.lat, city.lon)
            rows.append({"city_id": city.id, "date": iso, **rs})
        d += timedelta(days=1)
    if rows:
        session.bulk_insert_mappings(CityDay, rows)
        session.commit()
    return len(rows)


def ensure_city_cached(session, city: City, need_from: date, need_to: date) -> None:
    """Ensure city_days + global events cover [need_from, need_to]."""
    settings = get_settings()
    today = date.today()
    horizon = settings.default_cache_months

    cached_from = date.fromisoformat(city.cached_from) if city.cached_from else None
    cached_to = date.fromisoformat(city.cached_to) if city.cached_to else None

    if cached_from is None:
        start = min(need_from, today)
        end = add_months(start, horizon)
        while end < need_to:
            end = add_months(end, horizon)
        t0 = time.perf_counter()
        # Global events first (shared across cities), then this city's rise/set.
        ensure_global_coverage(
            session,
            datetime_to_jd(datetime(start.year, start.month, start.day)) - 2.0,
            datetime_to_jd(datetime(end.year, end.month, end.day)) + 3.0,
        )
        n = _store_days(session, city, start, end)
        city.cached_from, city.cached_to = start.isoformat(), end.isoformat()
        session.add(city)
        session.commit()
        log.info(
            "First-time cache for city %s (%s): %d days [%s..%s] in %.2fs",
            city.id, city.name, n, start, end, time.perf_counter() - t0,
        )
        return

    # Extend backwards if needed.
    if need_from < cached_from:
        new_from = min(need_from, add_months(cached_from, -horizon))
        ensure_global_coverage(
            session,
            datetime_to_jd(datetime(new_from.year, new_from.month, new_from.day)) - 2.0,
            datetime_to_jd(datetime(cached_to.year, cached_to.month, cached_to.day)) + 3.0,
        )
        _store_days(session, city, new_from, cached_from - timedelta(days=1))
        cached_from = new_from
        city.cached_from = new_from.isoformat()

    # Extend forwards if needed.
    if need_to > cached_to:
        new_to = add_months(cached_to, horizon)
        while new_to < need_to:
            new_to = add_months(new_to, horizon)
        ensure_global_coverage(
            session,
            datetime_to_jd(datetime(cached_from.year, cached_from.month, cached_from.day)) - 2.0,
            datetime_to_jd(datetime(new_to.year, new_to.month, new_to.day)) + 3.0,
        )
        _store_days(session, city, cached_to + timedelta(days=1), new_to)
        cached_to = new_to
        city.cached_to = new_to.isoformat()

    session.add(city)
    session.commit()


def get_city_day(session, city: City, d: date) -> CityDay | None:
    return session.scalar(
        select(CityDay).where(CityDay.city_id == city.id, CityDay.date == d.isoformat())
    )


def get_or_compute_day(session, city: City, d: date) -> CityDay:
    """Return the cached rise/set for a date, computing/extending if needed."""
    row = get_city_day(session, city, d)
    if row is None:
        ensure_city_cached(session, city, d, d)
        row = get_city_day(session, city, d)
    return row
