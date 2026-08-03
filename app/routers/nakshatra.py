"""GET /v1/nakshatra-at — moon nakshatra/pada/rashi at an exact instant."""
from __future__ import annotations

from datetime import date, time

from fastapi import APIRouter, Query

from app.api import ApiError, resolve_zone
from app.geo.tz import timezone_at
from app.panchang.instant import nakshatra_at

router = APIRouter(prefix="/v1", tags=["nakshatra"])


@router.get("/nakshatra-at")
def nakshatra_at_endpoint(
    date_: date = Query(..., alias="date"),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time_: time | None = Query(None, alias="time",
                               description="HH:MM:SS; if omitted, local sunrise is used."),
    tz: str | None = Query(None, description="IANA tz; derived from coords if omitted."),
):
    tzname = tz
    if tzname is None:
        tzname = timezone_at(lat, lon)
        if not tzname:
            raise ApiError(422, "tz_unresolved",
                           "Could not resolve timezone; pass tz explicitly.")
    resolve_zone(tzname)  # 422 with a JSON body instead of an uncaught 500
    return nakshatra_at(date_, lat, lon, tzname, time_)
