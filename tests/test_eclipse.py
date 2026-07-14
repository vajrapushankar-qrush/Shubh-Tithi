"""Eclipse detection + visibility.

The two anchor eclipses below are real, published events (verifiable against any
eclipse table, e.g. NASA GSFC eclipse catalog). Add more TODO fixtures as
desired.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.astronomy.core import datetime_to_jd, init_ephemeris
from app.cache.global_events import ensure_global_coverage
from app.panchang.eclipses import find_lunar_eclipses, find_solar_eclipses


# (kind, iso_date, type) — published eclipses.
ANCHOR_ECLIPSES = [
    ("solar", date(2026, 8, 12), "total"),    # Total solar over Iceland/Spain
    ("lunar", date(2026, 8, 28), "partial"),  # Partial lunar eclipse
    # TODO: add fixtures from a published eclipse table as needed.
]


@pytest.mark.parametrize("kind,d,etype", ANCHOR_ECLIPSES,
                         ids=[f"{k}-{d}" for k, d, _ in ANCHOR_ECLIPSES])
def test_known_eclipse_is_found(kind, d, etype):
    init_ephemeris(None)
    jd_from = datetime_to_jd_at(d, -5)
    jd_to = datetime_to_jd_at(d, +5)
    finder = find_solar_eclipses if kind == "solar" else find_lunar_eclipses
    events = finder(jd_from, jd_to)
    assert events, f"no {kind} eclipse found near {d}"
    # An eclipse maximum should land within a day of the published date.
    from app.astronomy.core import jd_to_datetime

    dates = {jd_to_datetime(e["max_jd"]).date() for e in events}
    assert d in dates, f"expected {kind} eclipse on {d}, found {sorted(dates)}"


def datetime_to_jd_at(d: date, offset_days: int) -> float:
    from datetime import datetime, timedelta, timezone

    return datetime_to_jd(datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
                          + timedelta(days=offset_days))


def test_visibility_differs_by_location(session):
    """Aug 12 2026 total solar eclipse: visible (partial) in London at dusk,
    not visible in Hyderabad (local night)."""
    from datetime import date

    from app.cache.city_cache import ensure_city_cached
    from app.db import City
    from app.panchang.derive import derive_panchang

    for cid in (1002, 1003):  # London, Hyderabad
        city = session.get(City, cid)
        ensure_city_cached(session, city, date(2026, 8, 12), date(2026, 8, 12))
    london = derive_panchang(session, session.get(City, 1002), date(2026, 8, 12))
    hyd = derive_panchang(session, session.get(City, 1003), date(2026, 8, 12))
    assert london["eclipse"] and london["eclipse"]["kind"] == "solar"
    assert london["eclipse"]["visible_here"] == "yes"
    assert hyd["eclipse"]["visible_here"] == "no"
