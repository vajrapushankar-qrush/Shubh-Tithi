"""Pydantic response models.

The full Panchang payload is deeply nested and somewhat dynamic (variable-length
tithi/nakshatra/karana lists), so those endpoints return plain dict payloads
(documented in the README). We model the stable, simple shapes here.
"""
from __future__ import annotations

from pydantic import BaseModel


class CityOut(BaseModel):
    id: int
    name: str
    state: str | None = None
    country: str | None = None
    country_code: str | None = None
    lat: float
    lon: float
    timezone: str


class CitiesResponse(BaseModel):
    query: str
    count: int
    results: list[CityOut]


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    ephemeris: str
    ayanamsa: str
    cities_cached: int
    cities_total: int
    global_events: int
    cache_spans: dict
