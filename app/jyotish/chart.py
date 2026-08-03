"""Natal chart assembly for GET /v1/chart.

House system is **whole sign** throughout: house 1 is the entire rashi the
ascendant falls in, house 2 the next rashi, and so on. No cusp interpolation is
involved, so a graha's house is a pure function of its rashi and the lagna's
rashi. This is the convention the North Indian square diagram assumes.

Every longitude emitted is sidereal, Lahiri ayanamsa -- the same source
``/v1/nakshatra-at`` uses, so the two agree on the moon for a given instant.

Rounding note: rashi, nakshatra and pada indices are derived from the
*rounded* longitude that appears in the response, not from the full-precision
value. This costs nothing astronomically (the two differ only within 5e-7 of a
boundary) and guarantees the consumer-side identities
``rashi.number == floor(longitude_sidereal / 30) + 1`` and
``nakshatra.number == floor(longitude_sidereal / (360/27)) + 1``
hold exactly on the numbers as serialised.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.astronomy.core import (
    GRAHA_BODIES,
    ascendant as compute_ascendant,
    datetime_to_jd,
    longitude_and_speed,
)
from app.jyotish import dasha as dasha_mod
from app.jyotish import doshas as dosha_mod
from app.panchang import names

LON_PRECISION = 6
NAK_ARC = 360.0 / 27.0
PADA_ARC = NAK_ARC / 4.0
RASHI_ARC = 30.0

# Emission order for the graha list (Ketu is derived, not calculated).
GRAHA_ORDER = (
    "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu",
)

# Grahas that are never reported retrograde. The luminaries never retrograde in
# fact; the nodes always do (the mean node's motion is negative by definition),
# but reporting them as retrograde is not the convention this API follows --
# see the endpoint documentation.
NEVER_RETROGRADE = frozenset({"Sun", "Moon", "Rahu", "Ketu"})


def _rashi(longitude: float) -> dict:
    index0 = int((longitude % 360.0) // RASHI_ARC)
    return {"number": index0 + 1, "name": names.RASHIS[index0]}


def _nakshatra(longitude: float) -> dict:
    lon = longitude % 360.0
    index0 = int(lon // NAK_ARC)
    pada = int((lon % NAK_ARC) // PADA_ARC) + 1
    return {"number": index0 + 1, "name": names.NAKSHATRAS[index0], "pada": pada}


def _whole_sign_house(rashi_number: int, lagna_rashi_number: int) -> int:
    return ((rashi_number - lagna_rashi_number) % 12) + 1


def _navamsa_longitude(longitude: float) -> float:
    """D9 longitude. Multiplying the sidereal longitude by 9 (mod 360) is
    exactly equivalent to the classical rule that movable signs start their
    navamsa count from themselves, fixed signs from the 9th and dual from the
    5th."""
    return (longitude * 9.0) % 360.0


def _position(name: str, longitude: float, speed: float, lagna_rashi: int) -> dict:
    lon = round(longitude % 360.0, LON_PRECISION)
    rashi = _rashi(lon)
    return {
        "name": name,
        "longitude_sidereal": lon,
        "rashi": rashi,
        "nakshatra": _nakshatra(lon),
        "degree": round(lon % RASHI_ARC, LON_PRECISION),
        "house": _whole_sign_house(rashi["number"], lagna_rashi),
        "retrograde": False if name in NEVER_RETROGRADE else speed < 0,
        "speed_deg_per_day": round(speed, LON_PRECISION),
    }


def compute_chart(
    instant_local: datetime,
    lat: float,
    lon: float,
    tz_name: str,
    *,
    dasha_span_years: float = 120.0,
    include_antardashas: bool = True,
) -> dict:
    """Full natal chart for a tz-aware local birth instant."""
    jd = datetime_to_jd(instant_local)

    # --- Ascendant ---------------------------------------------------------
    asc_lon = round(compute_ascendant(jd, lat, lon), LON_PRECISION)
    asc_rashi = _rashi(asc_lon)
    lagna_rashi_number = asc_rashi["number"]

    ascendant_block = {
        "longitude_sidereal": asc_lon,
        "rashi": asc_rashi,
        "nakshatra": _nakshatra(asc_lon),
        "degree": round(asc_lon % RASHI_ARC, LON_PRECISION),
    }

    # --- Grahas ------------------------------------------------------------
    raw: dict[str, tuple[float, float]] = {}
    for name, body in GRAHA_BODIES.items():
        raw[name] = longitude_and_speed(jd, body)
    # Ketu is exactly opposite Rahu, sharing its speed.
    rahu_lon, rahu_speed = raw["Rahu"]
    raw["Ketu"] = ((rahu_lon + 180.0) % 360.0, rahu_speed)

    planets = [
        _position(name, raw[name][0], raw[name][1], lagna_rashi_number)
        for name in GRAHA_ORDER
    ]
    by_name = {p["name"]: p for p in planets}

    # --- Houses (whole sign) ----------------------------------------------
    houses = [
        {
            "house": i + 1,
            "rashi": {
                "number": ((lagna_rashi_number - 1 + i) % 12) + 1,
                "name": names.RASHIS[(lagna_rashi_number - 1 + i) % 12],
            },
        }
        for i in range(12)
    ]

    # --- Navamsa (D9) ------------------------------------------------------
    nav_asc_lon = _navamsa_longitude(asc_lon)
    nav_asc_rashi = _rashi(nav_asc_lon)
    navamsa = {
        "ascendant": {
            "longitude_sidereal": round(nav_asc_lon, LON_PRECISION),
            "rashi": nav_asc_rashi,
        },
        "planets": [],
    }
    for p in planets:
        nav_lon = _navamsa_longitude(p["longitude_sidereal"])
        nav_rashi = _rashi(nav_lon)
        navamsa["planets"].append({
            "name": p["name"],
            "longitude_sidereal": round(nav_lon, LON_PRECISION),
            "rashi": nav_rashi,
            "degree": round(nav_lon % RASHI_ARC, LON_PRECISION),
            "house": _whole_sign_house(nav_rashi["number"], nav_asc_rashi["number"]),
            "retrograde": p["retrograde"],
        })
    navamsa["houses"] = [
        {
            "house": i + 1,
            "rashi": {
                "number": ((nav_asc_rashi["number"] - 1 + i) % 12) + 1,
                "name": names.RASHIS[(nav_asc_rashi["number"] - 1 + i) % 12],
            },
        }
        for i in range(12)
    ]

    # --- Vimshottari dasha -------------------------------------------------
    moon_lon = by_name["Moon"]["longitude_sidereal"]
    dashas = {
        "vimshottari": dasha_mod.vimshottari(
            moon_lon, instant_local,
            span_years=dasha_span_years,
            include_antar=include_antardashas,
        ),
        "balance_at_birth": dasha_mod.balance_at_birth(moon_lon),
        "system": {
            "name": "vimshottari",
            "cycle_years": dasha_mod.TOTAL_YEARS,
            "year_days": dasha_mod.YEAR_DAYS,
            "levels": ["maha", "antar"] if include_antardashas else ["maha"],
        },
    }

    # --- Doshas ------------------------------------------------------------
    now = datetime.now(timezone.utc)
    saturn_transit_lon, _ = longitude_and_speed(datetime_to_jd(now), GRAHA_BODIES["Saturn"])
    doshas = {
        "manglik": dosha_mod.manglik(
            mars_rashi=by_name["Mars"]["rashi"]["number"],
            lagna_rashi=lagna_rashi_number,
            moon_rashi=by_name["Moon"]["rashi"]["number"],
        ),
        "kaal_sarp": dosha_mod.kaal_sarp(
            {n: by_name[n]["longitude_sidereal"] for n in dosha_mod.SEVEN_GRAHAS},
            by_name["Rahu"]["longitude_sidereal"],
        ),
        "sade_sati": dosha_mod.sade_sati(
            natal_moon_rashi=by_name["Moon"]["rashi"]["number"],
            transit_saturn_rashi=_rashi(saturn_transit_lon)["number"],
            evaluated_at=now.isoformat(),
        ),
    }

    return {
        "instant": instant_local.isoformat(),
        "coordinates": {"lat": lat, "lon": lon, "timezone": tz_name},
        "ayanamsa": "lahiri",
        "house_system": "whole_sign",
        "node_type": "mean",
        "ascendant": ascendant_block,
        "planets": planets,
        "houses": houses,
        "navamsa": navamsa,
        "dashas": dashas,
        "doshas": doshas,
    }
