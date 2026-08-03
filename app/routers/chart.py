"""GET /v1/chart — natal chart (kundali) at an exact birth instant."""
from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Query

from app.api import ApiError, resolve_zone
from app.geo.tz import timezone_at
from app.jyotish.chart import compute_chart

router = APIRouter(prefix="/v1", tags=["chart"])


@router.get("/chart")
def chart_endpoint(
    date_: date = Query(..., alias="date", description="Birth date, YYYY-MM-DD, local civil date in tz."),
    time_: time = Query(
        ..., alias="time",
        description=(
            "Birth time, HH:MM or HH:MM:SS, local civil time in tz. REQUIRED — "
            "unlike /v1/nakshatra-at this endpoint does not fall back to "
            "sunrise, because an assumed time makes the ascendant and all "
            "twelve houses meaningless rather than merely approximate."
        ),
    ),
    lat: float = Query(..., ge=-90, le=90, description="Signed decimal degrees, north positive."),
    lon: float = Query(..., ge=-180, le=180, description="Signed decimal degrees, east positive."),
    tz: str | None = Query(None, description="IANA tz name; derived from coords if omitted."),
    dasha_span_years: float = Query(
        120.0, ge=1, le=120,
        description="How far past birth the Vimshottari tree must reach.",
    ),
    include_antardashas: bool = Query(
        True, description="Include the antardasha children of each mahadasha.",
    ),
):
    tzname = tz
    if tzname is None:
        tzname = timezone_at(lat, lon)
        if not tzname:
            raise ApiError(422, "tz_unresolved",
                           "Could not resolve timezone; pass tz explicitly.")
    zone = resolve_zone(tzname)

    instant_local = datetime(
        date_.year, date_.month, date_.day,
        time_.hour, time_.minute, time_.second, tzinfo=zone,
    )

    try:
        return compute_chart(
            instant_local, lat, lon, tzname,
            dasha_span_years=dasha_span_years,
            include_antardashas=include_antardashas,
        )
    except ValueError as exc:
        # Ascendant is undefined at the geographic poles.
        raise ApiError(422, "ascendant_undefined", str(exc)) from exc
