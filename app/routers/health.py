"""GET /v1/health — status + ephemeris version + cache stats."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api import get_session
from app.astronomy.core import ayanamsa, ephemeris_version
from app.db import City, GlobalEvent, get_meta
from app.schemas import HealthResponse

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(session=Depends(get_session)):
    cities_total = session.scalar(select(func.count()).select_from(City)) or 0
    cities_cached = session.scalar(
        select(func.count()).select_from(City).where(City.cached_from.is_not(None))
    ) or 0
    global_events = session.scalar(select(func.count()).select_from(GlobalEvent)) or 0
    g_from = get_meta(session, "global_from_jd")
    g_to = get_meta(session, "global_to_jd")

    # Current ayanamsa for a fixed reference (informational).
    import swisseph as swe

    ref_jd = swe.julday(2000, 1, 1, 12.0)
    return HealthResponse(
        status="ok",
        ephemeris=f"Swiss Ephemeris (pyswisseph {ephemeris_version()})",
        ayanamsa=f"Lahiri; {ayanamsa(ref_jd):.4f}deg at J2000",
        cities_cached=cities_cached,
        cities_total=cities_total,
        global_events=global_events,
        cache_spans={"global_from_jd": g_from, "global_to_jd": g_to},
    )
