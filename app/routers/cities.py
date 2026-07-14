"""GET /v1/cities — city search for disambiguation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api import get_session
from app.geo.search import search_cities
from app.schemas import CitiesResponse, CityOut

router = APIRouter(prefix="/v1", tags=["cities"])


@router.get("/cities", response_model=CitiesResponse)
def cities(
    q: str = Query(..., min_length=1, description="City name (prefix or substring)."),
    country: str | None = Query(None, description="ISO2 code or country-name fragment."),
    limit: int = Query(25, ge=1, le=100),
    session=Depends(get_session),
):
    rows = search_cities(session, q, country=country, limit=limit)
    results = [
        CityOut(
            id=r.id, name=r.name, state=r.state, country=r.country,
            country_code=r.country_code, lat=r.lat, lon=r.lon, timezone=r.tz,
        )
        for r in rows
    ]
    return CitiesResponse(query=q, count=len(results), results=results)
