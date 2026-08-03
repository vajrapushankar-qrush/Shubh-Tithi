"""Dosha tests: Manglik (Mangal), Kaal Sarp, Sade Sati.

Each function returns not just a boolean but the inputs that produced it, so a
consumer can re-derive the verdict under a different school without another
request. Where traditions disagree (and for Manglik they very much do) the
disagreement is surfaced as separate fields rather than resolved silently.
"""
from __future__ import annotations

# Houses from the lagna that render Mars a manglik placement.
#
# Houses 1, 4, 7, 8 and 12 are agreed on across essentially all schools. The
# **2nd house is disputed**: North Indian practice generally counts it, much of
# South Indian practice does not. We include it in the headline ``manglik``
# verdict (the more conservative, wider reading) and also report the strict
# 5-house verdict separately so a consumer can choose.
MANGLIK_HOUSES = (1, 2, 4, 7, 8, 12)
MANGLIK_HOUSES_STRICT = (1, 4, 7, 8, 12)

SEVEN_GRAHAS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")

# Rashis from the natal moon that Saturn transits during Sade Sati:
# the 12th (approaching), the 1st (peak) and the 2nd (departing).
SADE_SATI_OFFSETS = (-1, 0, 1)


def _house_from(reference_rashi: int, target_rashi: int) -> int:
    """Whole-sign house number (1..12) of ``target_rashi`` counted from
    ``reference_rashi``. Both are 1-based rashi numbers."""
    return ((target_rashi - reference_rashi) % 12) + 1


def manglik(mars_rashi: int, lagna_rashi: int, moon_rashi: int) -> dict:
    """Mangal dosha from the lagna, with the from-moon reading alongside."""
    from_lagna = _house_from(lagna_rashi, mars_rashi)
    from_moon = _house_from(moon_rashi, mars_rashi)
    return {
        "value": from_lagna in MANGLIK_HOUSES,
        "reference": "lagna",
        "reference_houses": list(MANGLIK_HOUSES),
        "mars_house_from_lagna": from_lagna,
        "mars_house_from_moon": from_moon,
        "from_lagna": from_lagna in MANGLIK_HOUSES,
        "from_moon": from_moon in MANGLIK_HOUSES,
        "from_lagna_strict": from_lagna in MANGLIK_HOUSES_STRICT,
        "second_house_counted": True,
        "note": (
            "value == from_lagna, counting houses 1/2/4/7/8/12 from the "
            "ascendant. The 2nd house is disputed between schools; "
            "from_lagna_strict omits it."
        ),
    }


def kaal_sarp(planet_longitudes: dict[str, float], rahu_longitude: float) -> dict:
    """True when all seven grahas fall on one side of the Rahu-Ketu axis.

    Measured as the forward arc from Rahu: a graha with offset in (0, 180) lies
    on the Rahu-to-Ketu side, one in (180, 360) on the Ketu-to-Rahu side. All
    seven on the same side is the yoga. A graha exactly conjunct either node
    (offset 0 or 180) breaks the test here — schools differ on whether that
    counts, and we do not guess.
    """
    offsets = {
        name: (planet_longitudes[name] - rahu_longitude) % 360.0
        for name in SEVEN_GRAHAS
    }
    rahu_side = all(0.0 < off < 180.0 for off in offsets.values())
    ketu_side = all(180.0 < off < 360.0 for off in offsets.values())
    return {
        "value": rahu_side or ketu_side,
        "side": "rahu_to_ketu" if rahu_side else ("ketu_to_rahu" if ketu_side else None),
        "note": (
            "All seven grahas (Sun, Moon, Mars, Mercury, Jupiter, Venus, "
            "Saturn) strictly between Rahu and Ketu on one side."
        ),
    }


def sade_sati(
    natal_moon_rashi: int,
    transit_saturn_rashi: int,
    evaluated_at: str,
) -> dict:
    """Saturn's *current* transit of the 12th, 1st or 2nd from the natal moon.

    Unlike every other value in a chart response this is a function of the
    present moment, not of the birth. ``evaluated_at`` records when it was
    determined; the same birth details will produce a different answer on a
    different day.
    """
    house = _house_from(natal_moon_rashi, transit_saturn_rashi)
    phase = {12: "rising", 1: "peak", 2: "setting"}.get(house)
    return {
        "value": phase is not None,
        "phase": phase,
        "saturn_transit_rashi": transit_saturn_rashi,
        "natal_moon_rashi": natal_moon_rashi,
        "saturn_house_from_moon": house,
        "evaluated_at": evaluated_at,
        "note": (
            "Time-dependent: evaluated against Saturn's position at "
            "evaluated_at, not at birth. Exclude from fixture comparisons."
        ),
    }
