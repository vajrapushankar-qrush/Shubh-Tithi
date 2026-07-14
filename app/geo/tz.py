"""Lazily-initialised, shared TimezoneFinder.

Constructing ``TimezoneFinder`` loads its polygon data, so it must not be built
per request. ``functools.lru_cache`` gives a process-wide singleton created on
first use.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _finder():
    from timezonefinder import TimezoneFinder

    return TimezoneFinder(in_memory=True)


def timezone_at(lat: float, lon: float) -> str | None:
    """IANA timezone for the coordinates, or ``None`` over open ocean."""
    return _finder().timezone_at(lat=lat, lng=lon)
