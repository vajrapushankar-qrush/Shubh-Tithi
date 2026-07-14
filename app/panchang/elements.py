"""Pure index math for the five Panchang angas, plus the angle functions the
root-finder crosses.

Tithi   = floor((moon - sun) / 12deg)            -> 0..29   (number = +1)
Karana  = floor((moon - sun) / 6deg)             -> 0..59   (half-tithi)
Nakshatra = floor(moon / (13deg20'))             -> 0..26
Yoga    = floor((sun + moon) / (13deg20'))       -> 0..26
Rashi   = floor(longitude / 30deg)               -> 0..11

All longitudes are sidereal (Lahiri). These functions are deliberately free of
any Swiss Ephemeris dependency so they can be unit-tested from raw longitudes.
"""
from __future__ import annotations

from . import names

# Angular units (degrees)
TITHI_ARC = 12.0
KARANA_ARC = 6.0
NAK_ARC = 360.0 / 27.0  # 13deg20'
YOGA_ARC = 360.0 / 27.0
RASHI_ARC = 30.0
PADA_ARC = NAK_ARC / 4.0  # 3deg20'


# --- Index computation from longitudes ------------------------------------
def tithi_index(sun_long: float, moon_long: float) -> int:
    """0-based tithi index (0..29)."""
    elong = (moon_long - sun_long) % 360.0
    return int(elong // TITHI_ARC)


def karana_index(sun_long: float, moon_long: float) -> int:
    """0-based half-tithi index within the lunation (0..59)."""
    elong = (moon_long - sun_long) % 360.0
    return int(elong // KARANA_ARC)


def nakshatra_index(moon_long: float) -> int:
    return int((moon_long % 360.0) // NAK_ARC)


def nakshatra_pada(moon_long: float) -> int:
    """1..4."""
    within = (moon_long % 360.0) % NAK_ARC
    return int(within // PADA_ARC) + 1


def yoga_index(sun_long: float, moon_long: float) -> int:
    return int(((sun_long + moon_long) % 360.0) // YOGA_ARC)


def rashi_index(longitude: float) -> int:
    return int((longitude % 360.0) // RASHI_ARC)


# --- Human-facing descriptors ---------------------------------------------
def describe_tithi(index0: int) -> dict:
    number = (index0 % 30) + 1
    return {
        "number": number,
        "name": names.tithi_name(number),
        "paksha": names.tithi_paksha(number),
    }


def describe_karana(index0: int) -> dict:
    return {"name": names.karana_name(index0 % 60)}


def describe_nakshatra(index0: int, pada: int | None = None) -> dict:
    out = {"number": (index0 % 27) + 1, "name": names.NAKSHATRAS[index0 % 27]}
    if pada is not None:
        out["pada"] = pada
    return out


def describe_yoga(index0: int) -> dict:
    return {"number": (index0 % 27) + 1, "name": names.YOGAS[index0 % 27]}


def describe_rashi(index0: int) -> dict:
    return {"number": (index0 % 12) + 1, "name": names.RASHIS[index0 % 12]}


# --- Angle functions for the root-finder (jd -> degrees) ------------------
# Bound lazily to avoid importing swisseph at module import time.
def make_angle_funcs():
    from app.astronomy.core import moon_longitude, sun_longitude

    def elong(jd: float) -> float:
        return (moon_longitude(jd) - sun_longitude(jd)) % 360.0

    def moon(jd: float) -> float:
        return moon_longitude(jd)

    def yoga(jd: float) -> float:
        return (sun_longitude(jd) + moon_longitude(jd)) % 360.0

    def sun(jd: float) -> float:
        return sun_longitude(jd)

    return {"elong": elong, "moon": moon, "yoga": yoga, "sun": sun}
