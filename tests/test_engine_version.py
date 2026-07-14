"""The engine-version guard must wipe stale computed cache but keep cities."""
from __future__ import annotations

from datetime import date

from app.db import (
    City,
    CityDay,
    GlobalEvent,
    SessionLocal,
    ensure_engine_version,
    set_meta,
)


def test_version_change_wipes_computed_cache_but_keeps_cities():
    with SessionLocal() as s:
        # Simulate an older engine having populated the cache.
        set_meta(s, "engine_version", "1-old-buggy")
        city = s.get(City, 1003)  # Hyderabad (from conftest)
        city.cached_from = "2026-01-01"
        city.cached_to = "2027-01-01"
        s.add(GlobalEvent(event_type="nakshatra", idx=6, end_jd=2461234.0))
        s.add(CityDay(city_id=1003, date="2099-12-31", sunrise_jd=2461234.0))
        set_meta(s, "global_from_jd", "2461000.0")
        s.commit()

        wiped = ensure_engine_version(s)
        assert wiped is True

    with SessionLocal() as s:
        assert s.query(GlobalEvent).count() == 0
        assert s.query(CityDay).count() == 0
        city = s.get(City, 1003)
        assert city is not None                 # seeded city preserved
        assert city.cached_from is None         # horizon reset
        # Second call is a no-op now that the version matches.
        assert ensure_engine_version(s) is False
