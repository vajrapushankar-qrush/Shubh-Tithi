"""Shared pytest fixtures.

Uses a throwaway SQLite file and inserts only the handful of cities the tests
need, so the suite never pays the ~150k-row full seed. The DB path env var is
set *before* importing anything that binds the engine.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

import pytest

_TMP_DB = os.path.join(tempfile.gettempdir(), "shubhtithi_test_cache.db")
os.environ["SHUBHTITHI_DB_PATH"] = _TMP_DB

# City fixtures used across tests: (id, name, lat, lon, tz).
TEST_CITIES = {
    "new_york": (1001, "New York", 40.71427, -74.00597, "America/New_York"),
    "london": (1002, "London", 51.50722, -0.12750, "Europe/London"),
    "hyderabad": (1003, "Hyderabad", 17.38504, 78.48667, "Asia/Kolkata"),
    "bengaluru": (1004, "Bengaluru", 12.97194, 77.59369, "Asia/Kolkata"),
}


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)
    from app.astronomy.core import init_ephemeris
    from app.db import City, SessionLocal, init_db

    init_ephemeris(None)
    init_db()
    with SessionLocal() as s:
        for name, (cid, cname, lat, lon, tz) in TEST_CITIES.items():
            s.merge(City(id=cid, name=cname, name_lower=cname.lower(),
                         lat=lat, lon=lon, tz=tz, source="test"))
        s.commit()
    yield


@pytest.fixture
def session():
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def panchang_for(session):
    """Return a function (city_key, date) -> full panchang dict."""
    from app.cache.city_cache import ensure_city_cached
    from app.db import City
    from app.panchang.derive import derive_panchang

    def _get(city_key: str, d: date) -> dict:
        cid = TEST_CITIES[city_key][0]
        city = session.get(City, cid)
        ensure_city_cached(session, city, d, date(d.year, d.month, d.day))
        return derive_panchang(session, city, d)

    return _get
