"""Swiss Ephemeris wrappers — the *only* place we touch pyswisseph.

Conventions (must match published Panchangam almanacs):

* **Sidereal zodiac, Lahiri ayanamsa** (``swe.SIDM_LAHIRI``) for every planetary
  longitude used in Panchang element math.
* **Sunrise / sunset**: apparent rise/set of the **upper limb with atmospheric
  refraction** — Swiss Ephemeris' default when neither ``BIT_DISC_CENTER`` nor
  ``BIT_NO_REFRACTION`` is passed. This is the convention published almanacs use, so
  it is our default; both aspects are configurable (see :class:`app.config`).
* All element boundaries are computed as **global instants in UT** and only
  rendered into a city's local timezone at the presentation layer.

Ephemeris data: if ``SHUBHTITHI_EPHEMERIS_PATH`` points at Swiss Ephemeris data
files we use ``FLG_SWIEPH`` (sub-arc-second). Otherwise we use ``FLG_MOSEPH``
(the built-in Moshier analytical theory, accurate to a few arc-seconds) — good
enough for minute-precision Panchang, and it removes pyswisseph's "no data
file" warnings.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import swisseph as swe

# Bodies
SUN = swe.SUN
MOON = swe.MOON

# IMPORTANT: pyswisseph is built thread-safe — the ephemeris path and, crucially,
# the *sidereal mode* (ayanamsa) are stored per thread. FastAPI runs sync
# endpoints in a worker-thread pool, so a mode set once at startup on the main
# thread would NOT apply to request threads (they would silently fall back to the
# default Fagan-Bradley ayanamsa, corrupting every absolute-longitude quantity:
# nakshatra, yoga, rashi, lunar month). We therefore configure Swiss Ephemeris
# *lazily per thread* on first use.
_calc_flag = swe.FLG_MOSEPH
_ephe_path_str: str | None = None
_configured = False
_thread = threading.local()


def init_ephemeris(ephemeris_path: Path | None = None) -> str:
    """Select the ephemeris backend and record the sidereal configuration.

    Returns a short human-readable description of the active backend. The actual
    per-thread ``set_ephe_path`` / ``set_sid_mode`` happens lazily (see
    :func:`_ensure_thread`) so every thread — including FastAPI's worker pool —
    gets Lahiri applied.
    """
    global _calc_flag, _ephe_path_str, _configured
    backend = "Moshier (built-in)"
    if ephemeris_path is not None and Path(ephemeris_path).is_dir():
        _ephe_path_str = str(ephemeris_path)
        _calc_flag = swe.FLG_SWIEPH
        backend = f"Swiss Ephemeris files ({ephemeris_path})"
    else:
        _ephe_path_str = None
        _calc_flag = swe.FLG_MOSEPH
    _configured = True
    # Re-apply on this (the calling) thread immediately.
    _thread.ready = False
    _ensure_thread()
    return backend


def _ensure_thread() -> None:
    """Apply the ephemeris path + Lahiri sidereal mode on the current thread."""
    if not _configured:
        init_ephemeris(None)
        return
    if getattr(_thread, "ready", False):
        return
    if _ephe_path_str:
        swe.set_ephe_path(_ephe_path_str)
    # Lahiri ayanamsa; t0=0, ayan_t0=0 selects the built-in Lahiri definition.
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    _thread.ready = True


def ephemeris_version() -> str:
    return swe.version


# --- Time conversions ------------------------------------------------------
def datetime_to_jd(dt: datetime) -> float:
    """UTC (or tz-aware) datetime -> Julian Day (UT)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    hour = dt.hour + dt.minute / 60 + dt.second / 3600 + dt.microsecond / 3.6e9
    return swe.julday(dt.year, dt.month, dt.day, hour, swe.GREG_CAL)


def jd_to_datetime(jd: float) -> datetime:
    """Julian Day (UT) -> tz-aware UTC datetime, rounded to the second."""
    y, m, d, hour = swe.revjul(jd, swe.GREG_CAL)
    total_seconds = round(hour * 3600)
    base = datetime(y, m, d, tzinfo=timezone.utc)
    return base + timedelta(seconds=total_seconds)


# --- Longitudes (sidereal, Lahiri) ----------------------------------------
def _sidereal_longitude(jd: float, body: int) -> float:
    _ensure_thread()
    flags = _calc_flag | swe.FLG_SIDEREAL
    values, _ = swe.calc_ut(jd, body, flags)
    return values[0] % 360.0


def sun_longitude(jd: float) -> float:
    return _sidereal_longitude(jd, SUN)


def moon_longitude(jd: float) -> float:
    return _sidereal_longitude(jd, MOON)


def sun_moon_longitudes(jd: float) -> tuple[float, float]:
    """Return (sun_long, moon_long) sidereal degrees — one call site, two bodies."""
    return sun_longitude(jd), moon_longitude(jd)


def ayanamsa(jd: float) -> float:
    _ensure_thread()
    return swe.get_ayanamsa_ut(jd)


# --- Rise / set / transit --------------------------------------------------
def rise_set(
    jd_start: float,
    body: int,
    *,
    rising: bool,
    lat: float,
    lon: float,
    alt: float = 0.0,
    upper_limb: bool = True,
    refraction: bool = True,
) -> float | None:
    """Next rise (or set) of ``body`` at or after ``jd_start``.

    Returns the event JD (UT), or ``None`` if the body is circumpolar / never
    crosses the horizon in the search window (Swiss Ephemeris searches ahead a
    few days internally).
    """
    _ensure_thread()
    rsmi = swe.CALC_RISE if rising else swe.CALC_SET
    # Defaults (no extra bits) = upper limb + refraction = published-almanac style.
    if not upper_limb:
        rsmi |= swe.BIT_DISC_CENTER
    if not refraction:
        rsmi |= swe.BIT_NO_REFRACTION
    # Rise/set uses apparent geocentric position; sidereal flag is irrelevant.
    res, tret = swe.rise_trans(
        jd_start, body, rsmi, (lon, lat, alt), 0.0, 0.0, _calc_flag
    )
    if res < 0:
        return None
    return tret[0]


def calc_flag() -> int:
    _ensure_thread()
    return _calc_flag
