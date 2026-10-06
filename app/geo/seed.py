"""One-time seeding of the ``cities`` table from the bundled trimmed
Countries-States-Cities (CSC) dataset.

Timezone is derived from coordinates with ``timezonefinder`` at insert time (per
spec) — fast (~3s for the full set). When a point falls outside timezonefinder's
polygons (open ocean), we fall back to the IANA zone the CSC dataset already
carries so every city ends up with a usable zone.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import func, select

from app.config import get_settings
from app.db import City, CityDay, SessionLocal, get_meta, set_meta

log = logging.getLogger("shubhtithi.seed")

SEED_FLAG = "cities_seeded"
_CHUNK = 5000


def load_corrections(settings) -> dict[int, dict]:
    """Coordinate fixes applied over the bundled CSC rows, keyed by city id.

    A handful of CSC rows carry a quarter-degree grid point rather than the
    city itself — Jaipur sits at 27.0/76.0, Cuttack at 20.5/86.25. That is up
    to ~0.37 deg of longitude, which moves sunrise by about a minute and a
    half, and sunrise is what every tithi and nakshatra boundary is read
    against. For a city we publish muhurat pages for, that is worth fixing.

    Kept beside the dataset rather than edited into it, so refreshing the
    upstream copy does not silently undo the corrections.
    """
    path = settings.cities_seed_path.parent / "corrections.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {row["id"]: row for row in data.get("corrections", [])}


def cities_count(session) -> int:
    return session.scalar(select(func.count()).select_from(City)) or 0


def seed_cities(force: bool = False) -> int:
    """Load cities into SQLite if not already seeded. Returns row count."""
    settings = get_settings()
    with SessionLocal() as session:
        if not force and get_meta(session, SEED_FLAG) == "1" and cities_count(session):
            return cities_count(session)

    from timezonefinder import TimezoneFinder

    tf = TimezoneFinder(in_memory=True)
    with open(settings.cities_seed_path, encoding="utf-8") as fh:
        rows = json.load(fh)

    corrections = load_corrections(settings)
    if corrections:
        log.info("Applying %d coordinate correction(s)", len(corrections))

    log.info("Seeding %d cities from %s", len(rows), settings.cities_seed_path)
    mappings: list[dict] = []
    inserted = 0
    with SessionLocal() as session:
        if force:
            session.query(City).delete()
            session.commit()
        for c in rows:
            lat, lon = c["lat"], c["lon"]
            source = "CSC"
            fix = corrections.get(c["id"])
            if fix:
                lat, lon = fix["lat"], fix["lon"]
                source = "CSC+corrected"
            # Derived from the CORRECTED point: a wrong coordinate can sit in
            # the wrong timezone polygon near a border.
            tz = tf.timezone_at(lat=lat, lng=lon) or c.get("tz") or "UTC"
            name = c["name"]
            mappings.append({
                "id": c["id"],
                "name": name,
                "name_lower": name.lower(),
                "state": c.get("state"),
                "country": c.get("country"),
                "country_code": c.get("cc"),
                "lat": lat,
                "lon": lon,
                "tz": tz,
                "population": c.get("pop"),
                "source": source,
            })
            if len(mappings) >= _CHUNK:
                session.bulk_insert_mappings(City, mappings)
                session.commit()
                inserted += len(mappings)
                mappings.clear()
        if mappings:
            session.bulk_insert_mappings(City, mappings)
            session.commit()
            inserted += len(mappings)
        set_meta(session, SEED_FLAG, "1")
        session.commit()
    log.info("Seeded %d cities", inserted)
    return inserted


def apply_corrections() -> int:
    """Bring an already-seeded database in line with corrections.json.

    seed_cities() only runs on an empty database, so a correction added later
    would never reach production without re-seeding 153k rows. This updates
    just the affected cities in place and is safe to run on every startup: it
    compares before writing, so an already-correct database is untouched.

    Cached days for a corrected city are deleted. They were computed from the
    old sunrise, and every tithi and nakshatra boundary is read against
    sunrise, so leaving them would serve the wrong answer indefinitely —
    exactly the bug the correction is meant to fix. The cache rebuilds lazily
    on the next request for that city.

    Returns the number of cities actually changed.
    """
    settings = get_settings()
    corrections = load_corrections(settings)
    if not corrections:
        return 0

    from timezonefinder import TimezoneFinder

    changed = 0
    with SessionLocal() as session:
        for city_id, fix in corrections.items():
            city = session.get(City, city_id)
            if city is None:
                log.warning("Correction for unknown city id %s (%s)", city_id,
                            fix.get("name"))
                continue
            lat, lon = float(fix["lat"]), float(fix["lon"])
            # Float equality is fine here: both sides come from JSON decimals
            # that round-trip exactly, and a spurious rewrite would only cost
            # one cache rebuild.
            if city.lat == lat and city.lon == lon:
                continue

            log.info("Correcting %s (%s): %s,%s -> %s,%s",
                     city.name, city_id, city.lat, city.lon, lat, lon)
            city.lat, city.lon = lat, lon
            tz = TimezoneFinder(in_memory=True).timezone_at(lat=lat, lng=lon)
            if tz:
                city.tz = tz
            city.source = "CSC+corrected"
            # Drop the stale cache and the horizon that describes it.
            session.query(CityDay).filter(CityDay.city_id == city_id).delete()
            city.cached_from = None
            city.cached_to = None
            changed += 1
        if changed:
            session.commit()
    return changed
