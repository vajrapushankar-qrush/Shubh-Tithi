"""Solar and lunar eclipse discovery + per-location visibility.

We scan the cached JD range once for global eclipses (location-independent) and
store them. Per city-day we expose whether an eclipse is visible from that
location by evaluating Swiss Ephemeris local circumstances at the instant of
maximum eclipse:

* Solar: ``sol_eclipse_how`` returns 0 when nothing is visible at the position;
  otherwise the body's true altitude (attr[5]) must be above the horizon.
* Lunar: ``lun_eclipse_how`` reports the moon's apparent altitude (attr[6]); the
  eclipse is visible where the moon is above the horizon during the event.

Visibility is evaluated at maximum only — a good approximation. Partial-window
visibility (eclipse in progress at moonrise/set) is left as a refinement TODO.
"""
from __future__ import annotations

import swisseph as swe

from app.astronomy.core import calc_flag

_TYPE_FLAGS = [
    (swe.ECL_TOTAL, "total"),
    (swe.ECL_ANNULAR_TOTAL, "hybrid"),
    (swe.ECL_ANNULAR, "annular"),
    (swe.ECL_PARTIAL, "partial"),
    (swe.ECL_PENUMBRAL, "penumbral"),
]


def _classify(retflag: int) -> str:
    for bit, label in _TYPE_FLAGS:
        if retflag & bit:
            return label
    return "unknown"


def find_solar_eclipses(jd_from: float, jd_to: float) -> list[dict]:
    flags = calc_flag()
    out: list[dict] = []
    jd = jd_from
    for _ in range(200):
        retflag, tret = swe.sol_eclipse_when_glob(jd, flags, 0, False)
        t_max = tret[0]
        if t_max > jd_to:
            break
        out.append({
            "kind": "solar",
            "type": _classify(retflag),
            "max_jd": t_max,
            "begin_jd": tret[2],
            "end_jd": tret[3],
        })
        jd = t_max + 2.0
    return out


def find_lunar_eclipses(jd_from: float, jd_to: float) -> list[dict]:
    flags = calc_flag()
    out: list[dict] = []
    jd = jd_from
    for _ in range(200):
        retflag, tret = swe.lun_eclipse_when(jd, flags, 0, False)
        t_max = tret[0]
        if t_max > jd_to:
            break
        out.append({
            "kind": "lunar",
            "type": _classify(retflag),
            "max_jd": t_max,
            "begin_jd": tret[6] if tret[6] else tret[2],
            "end_jd": tret[7] if tret[7] else tret[3],
        })
        jd = t_max + 2.0
    return out


def find_all_eclipses(jd_from: float, jd_to: float) -> list[dict]:
    events = find_solar_eclipses(jd_from, jd_to) + find_lunar_eclipses(jd_from, jd_to)
    events.sort(key=lambda e: e["max_jd"])
    return events


def visible_from(eclipse_kind: str, max_jd: float, lat: float, lon: float,
                 alt: float = 0.0) -> str:
    """Return "yes" / "no" for visibility at maximum, or "unknown" on error."""
    flags = calc_flag()
    geopos = (lon, lat, alt)
    try:
        if eclipse_kind == "solar":
            retflag, attr = swe.sol_eclipse_how(max_jd, geopos, flags)
            if retflag == 0:
                return "no"
            return "yes" if attr[5] > 0.0 else "no"  # sun above horizon
        else:  # lunar
            retflag, attr = swe.lun_eclipse_how(max_jd, geopos, flags)
            if retflag == 0:
                return "no"
            return "yes" if attr[6] > 0.0 else "no"  # moon above horizon
    except swe.Error:
        return "unknown"
