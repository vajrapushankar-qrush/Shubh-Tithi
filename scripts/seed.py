"""Seed / initialise the ShubhTithi cache database.

Zero manual DB setup required — this creates the schema and loads the bundled
city dataset. First-run panchang requests compute their own 15-month horizon
lazily, so running this is optional (the API seeds on startup too).

Usage:
    uv run python -m scripts.seed          # create schema + seed cities
    uv run python -m scripts.seed --force  # re-seed cities from scratch
"""
from __future__ import annotations

import argparse
import logging

from app.astronomy.core import init_ephemeris
from app.config import get_settings
from app.db import init_db
from app.geo.seed import seed_cities


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Seed the ShubhTithi database.")
    parser.add_argument("--force", action="store_true", help="Re-seed cities.")
    args = parser.parse_args()

    settings = get_settings()
    print(f"DB: {settings.db_path}")
    print(f"Ephemeris backend: {init_ephemeris(settings.ephemeris_path)}")
    init_db()
    count = seed_cities(force=args.force)
    print(f"Cities in database: {count}")


if __name__ == "__main__":
    main()
