"""ShubhTithi — FastAPI application entrypoint.

Run: ``uvicorn app.main:app --reload`` (or ``uv run fastapi dev``).
Interactive docs at /docs.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import install_error_handlers
from app.astronomy.core import init_ephemeris
from app.config import get_settings
from app.db import SessionLocal, ensure_engine_version, init_db
from app.geo.seed import apply_corrections, seed_cities
from app.routers import chart, cities, health, nakshatra, panchang

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("shubhtithi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    backend = init_ephemeris(settings.ephemeris_path)
    log.info("Ephemeris backend: %s", backend)
    init_db()
    # If the computation engine changed, drop stale computed cache (keeps the
    # seeded cities) so nothing from an older ayanamsa/algorithm survives.
    with SessionLocal() as session:
        if ensure_engine_version(session):
            log.warning("Engine version changed — rebuilt computed cache "
                        "(global events + city days will recompute on demand).")
    # First-run seed is idempotent and quick (~a few seconds for ~150k cities).
    count = seed_cities()
    # Runs every start, not just the first: a correction added after a database
    # was seeded would otherwise never reach it. No-ops when nothing changed.
    corrected = apply_corrections()
    if corrected:
        log.info("Applied %d coordinate correction(s)", corrected)
    log.info("Cities available: %d", count)
    yield


app = FastAPI(
    title="ShubhTithi",
    version="0.1.0",
    summary="Hindu Panchang (almanac) computation API — sidereal, Lahiri ayanamsa.",
    description=(
        "Open-source Panchang service built on Swiss Ephemeris. Computes tithi, "
        "nakshatra, yoga, karana, vara, sun/moon timings, inauspicious windows, "
        "muhurats, lunar/solar months, rashi, eclipses and more. AGPL-3.0."
    ),
    lifespan=lifespan,
)

install_error_handlers(app)
app.include_router(health.router)
app.include_router(cities.router)
app.include_router(panchang.router)
app.include_router(nakshatra.router)
app.include_router(chart.router)


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "ShubhTithi",
        "docs": "/docs",
        "endpoints": ["/v1/health", "/v1/cities", "/v1/panchang",
                      "/v1/panchang/range", "/v1/nakshatra-at", "/v1/chart"],
    }
