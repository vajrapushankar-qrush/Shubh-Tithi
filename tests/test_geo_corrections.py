"""Coordinate corrections applied over the bundled CSC dataset.

A few CSC rows carry a quarter-degree grid point instead of the city. Sunrise
is what every tithi and nakshatra boundary is read against, so a coordinate
that is a third of a degree out moves the whole day's panchang.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.db import City, CityDay, SessionLocal
from app.geo.seed import apply_corrections, load_corrections

DATA = Path(__file__).resolve().parent.parent / "data" / "geo"


def test_corrections_file_is_well_formed():
    rows = json.loads((DATA / "corrections.json").read_text())["corrections"]
    assert rows, "no corrections defined"
    for row in rows:
        assert isinstance(row["id"], int)
        assert -90 <= row["lat"] <= 90
        assert -180 <= row["lon"] <= 180
        # Every correction must say what it replaced and why, so a future
        # reader can tell a real fix from someone's guess.
        assert row["was"]["lat"] != row["lat"] or row["was"]["lon"] != row["lon"]
        assert row["why"] and row["source"]


def test_corrected_points_are_not_on_the_quarter_degree_grid():
    """The bug being fixed: a coordinate that is an exact multiple of 0.25 is a
    grid point, not a city."""
    for row in load_corrections(get_settings()).values():
        on_grid = (
            abs(row["lat"] * 4 - round(row["lat"] * 4)) < 1e-9
            and abs(row["lon"] * 4 - round(row["lon"] * 4)) < 1e-9
        )
        assert not on_grid, f"{row['name']} is still on the grid"
        was = row["was"]
        assert (
            abs(was["lat"] * 4 - round(was["lat"] * 4)) < 1e-9
            and abs(was["lon"] * 4 - round(was["lon"] * 4)) < 1e-9
        ), f"{row['name']}: the value being replaced was not a grid point"


@pytest.fixture
def uncorrected_city():
    """A city row as it exists BEFORE the correction — the production state.

    Built here rather than relying on the full 150k seed, which the suite
    deliberately skips; the behaviour under test is the fix-up, not the seed.
    """
    fixes = load_corrections(get_settings())
    city_id, fix = next(iter(fixes.items()))
    was = fix["was"]
    with SessionLocal() as session:
        session.merge(City(
            id=city_id, name=fix["name"], name_lower=fix["name"].lower(),
            lat=was["lat"], lon=was["lon"], tz="Asia/Kolkata", source="CSC",
        ))
        session.commit()
    yield city_id, fix
    with SessionLocal() as session:
        session.query(CityDay).filter(CityDay.city_id == city_id).delete()
        obj = session.get(City, city_id)
        if obj is not None:
            session.delete(obj)
        session.commit()


def test_apply_corrections_fixes_the_coordinate(uncorrected_city):
    city_id, fix = uncorrected_city
    assert apply_corrections() == 1
    with SessionLocal() as session:
        city = session.get(City, city_id)
        assert city.lat == pytest.approx(fix["lat"])
        assert city.lon == pytest.approx(fix["lon"])
        assert city.source == "CSC+corrected"


def test_apply_corrections_is_idempotent(uncorrected_city):
    """It runs on every startup, so the second run must change nothing."""
    assert apply_corrections() == 1
    assert apply_corrections() == 0


def test_correcting_a_city_drops_its_cached_days(uncorrected_city):
    """Cached days were computed from the old sunrise. Keeping them would serve
    the wrong answer forever — the exact bug the correction exists to fix."""
    city_id, _ = uncorrected_city
    with SessionLocal() as session:
        city = session.get(City, city_id)
        city.cached_from, city.cached_to = "2026-01-01", "2026-01-31"
        session.add(CityDay(city_id=city_id, date="2026-01-01", sunrise_jd=1.0))
        session.commit()

    assert apply_corrections() == 1

    with SessionLocal() as session:
        city = session.get(City, city_id)
        assert city.cached_from is None and city.cached_to is None
        assert session.query(CityDay).filter(CityDay.city_id == city_id).count() == 0


def test_the_correction_actually_moves_sunrise(uncorrected_city):
    """If the shift were negligible the correction would be churn. It is not:
    Cuttack's bundled longitude put sunrise ~88 seconds early."""
    import swisseph as swe
    from app.astronomy.core import rise_set

    _, fix = uncorrected_city
    jd0 = swe.julday(2026, 10, 1, 0.0)
    before = rise_set(jd0, swe.SUN, lat=fix["was"]["lat"], lon=fix["was"]["lon"],
                      rising=True)
    after = rise_set(jd0, swe.SUN, lat=fix["lat"], lon=fix["lon"], rising=True)
    shift_seconds = abs(after - before) * 86400
    assert shift_seconds > 20, f"only {shift_seconds:.0f}s — is the fix worth it?"
