"""Application configuration via pydantic-settings.

All values can be overridden through environment variables or a local ``.env``
file. See ``.env.example`` for the documented set.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of the ``app`` package directory.
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SHUBHTITHI_", extra="ignore"
    )

    # --- Storage -----------------------------------------------------------
    db_path: Path = Field(
        default=ROOT_DIR / "data" / "panchang_cache.db",
        description="SQLite database file for the cache.",
    )

    # --- Bundled geo dataset ----------------------------------------------
    cities_seed_path: Path = Field(
        default=ROOT_DIR / "data" / "geo" / "cities.min.json",
        description="Trimmed Countries-States-Cities dataset seeded on first run.",
    )

    # --- Swiss Ephemeris ---------------------------------------------------
    ephemeris_path: Path | None = Field(
        default=None,
        description=(
            "Directory holding Swiss Ephemeris data files (sepl_*.se1, semo_*.se1). "
            "When unset, pyswisseph falls back to the bundled Moshier model, which "
            "is accurate to a few arc-seconds — fine for Panchang minute precision."
        ),
    )

    # --- Cache behaviour ---------------------------------------------------
    default_cache_months: int = Field(
        default=15,
        description="Horizon (months) computed on first request and on each extension.",
    )
    max_range_days: int = Field(
        default=400,
        description="Hard cap on /panchang/range span; larger requests get a 422.",
    )

    # --- Astronomical conventions (see astronomy.core for rationale) -------
    # Default rise/set flags match Drik Panchang: apparent (refraction) upper limb.
    sunrise_upper_limb: bool = True
    sunrise_refraction: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
