"""GET /v1/panchang and /v1/panchang/range."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from app.api import ApiError, get_session
from app.cache.city_cache import ensure_city_cached
from app.config import get_settings
from app.db import City
from app.geo.search import get_city
from app.panchang.derive import derive_panchang

router = APIRouter(prefix="/v1", tags=["panchang"])

# Deterministic id space for ad-hoc (lat/lon/tz) "cities" so they reuse the
# same cache machinery without colliding with CSC ids.
_ADHOC_BASE = 900_000_000


def _adhoc_id(lat: float, lon: float, tz: str) -> int:
    key = f"{round(lat, 4)}|{round(lon, 4)}|{tz}"
    return _ADHOC_BASE + (abs(hash(key)) % 90_000_000)


def _resolve_tz(lat: float, lon: float, tz: str | None) -> str:
    if tz:
        return tz
    from timezonefinder import TimezoneFinder

    found = TimezoneFinder().timezone_at(lat=lat, lng=lon)
    if not found:
        raise ApiError(422, "tz_unresolved",
                       "Could not resolve timezone from coordinates; pass tz explicitly.")
    return found


def resolve_city(session, city_id: int | None, lat: float | None,
                 lon: float | None, tz: str | None) -> City:
    if city_id is not None:
        city = get_city(session, city_id)
        if city is None:
            raise ApiError(404, "city_not_found", f"No city with id {city_id}.")
        return city
    if lat is None or lon is None:
        raise ApiError(422, "missing_location",
                       "Provide either city_id or both lat and lon.")
    tzname = _resolve_tz(lat, lon, tz)
    aid = _adhoc_id(lat, lon, tzname)
    city = get_city(session, aid)
    if city is None:
        city = City(id=aid, name=f"({lat:.4f}, {lon:.4f})", name_lower="adhoc",
                    lat=lat, lon=lon, tz=tzname, source="adhoc")
        session.add(city)
        session.commit()
    return city


@router.get("/panchang")
def panchang(
    city_id: int | None = Query(None),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    tz: str | None = Query(None, description="IANA timezone; derived from coords if omitted."),
    date_: date = Query(..., alias="date"),
    session=Depends(get_session),
):
    city = resolve_city(session, city_id, lat, lon, tz)
    ensure_city_cached(session, city, date_, date_ + timedelta(days=1))
    return derive_panchang(session, city, date_)


@router.get("/panchang/range")
def panchang_range(
    start: date,
    end: date,
    city_id: int | None = Query(None),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    tz: str | None = Query(None),
    session=Depends(get_session),
):
    settings = get_settings()
    if end < start:
        raise ApiError(422, "bad_range", "end must be on or after start.")
    span = (end - start).days + 1
    if span > settings.max_range_days:
        raise ApiError(
            422, "range_too_large",
            f"Requested {span} days; maximum is {settings.max_range_days}.",
        )
    city = resolve_city(session, city_id, lat, lon, tz)
    # Cache one extra day so the last day's sunrise->next-sunrise window resolves.
    ensure_city_cached(session, city, start, end + timedelta(days=1))
    days = []
    d = start
    while d <= end:
        days.append(derive_panchang(session, city, d))
        d += timedelta(days=1)
    return {"city_id": city.id, "start": start.isoformat(), "end": end.isoformat(),
            "count": len(days), "days": days}
