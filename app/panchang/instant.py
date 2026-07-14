"""Pure Layer-1/2 computation for an exact instant (serves /nakshatra-at).

No cache, no city lookup — just coordinates + optional time. When time is
omitted we use local sunrise at the coordinates (a common convention for
janma-nakshatra when birth time is unknown) and flag that assumption.
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.astronomy.core import (
    MOON,
    datetime_to_jd,
    jd_to_datetime,
    moon_longitude,
    rise_set,
    SUN,
)
from app.config import get_settings
from app.panchang import elements


def nakshatra_at(
    d: date,
    lat: float,
    lon: float,
    tz_name: str,
    t: time | None = None,
) -> dict:
    tz = ZoneInfo(tz_name)
    time_assumed = None
    if t is None:
        settings = get_settings()
        jd0 = datetime_to_jd(datetime(d.year, d.month, d.day, tzinfo=tz))
        sunrise = rise_set(
            jd0, SUN, rising=True, lat=lat, lon=lon,
            upper_limb=settings.sunrise_upper_limb,
            refraction=settings.sunrise_refraction,
        )
        jd = sunrise if sunrise is not None else jd0
        time_assumed = "sunrise"
        instant_local = jd_to_datetime(jd).astimezone(tz)
    else:
        instant_local = datetime(d.year, d.month, d.day, t.hour, t.minute,
                                 t.second, tzinfo=tz)
        jd = datetime_to_jd(instant_local)

    moon = moon_longitude(jd)
    nak_idx = elements.nakshatra_index(moon)
    pada = elements.nakshatra_pada(moon)
    rashi_idx = elements.rashi_index(moon)

    out = {
        "instant": instant_local.isoformat(),
        "coordinates": {"lat": lat, "lon": lon, "timezone": tz_name},
        "moon_longitude_sidereal": round(moon, 6),
        "nakshatra": elements.describe_nakshatra(nak_idx, pada),
        "moon_rashi": elements.describe_rashi(rashi_idx),
    }
    if time_assumed:
        out["time_assumed"] = time_assumed
    return out
