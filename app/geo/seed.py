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
from app.db import City, SessionLocal, get_meta, set_meta

log = logging.getLogger("shubhtithi.seed")

SEED_FLAG = "cities_seeded"
_CHUNK = 5000


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

    log.info("Seeding %d cities from %s", len(rows), settings.cities_seed_path)
    mappings: list[dict] = []
    inserted = 0
    with SessionLocal() as session:
        if force:
            session.query(City).delete()
            session.commit()
        for c in rows:
            lat, lon = c["lat"], c["lon"]
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
                "source": "CSC",
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
