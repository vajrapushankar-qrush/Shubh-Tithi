"""Regression test for the per-thread ayanamsa bug.

pyswisseph stores the sidereal mode per thread. If Lahiri is only set on the main
thread, computations that run in a worker thread (as FastAPI's sync endpoints do)
silently fall back to Fagan-Bradley (~0.9deg off), corrupting nakshatra, yoga,
rashi and lunar-month while leaving tithi/karana (elongation-based) correct.

These tests exercise computation *in a worker thread* and assert Lahiri is active.
"""
from __future__ import annotations

import threading
from datetime import date, datetime

import swisseph as swe

from app.astronomy.core import ayanamsa, init_ephemeris


def test_ayanamsa_is_lahiri_in_worker_thread():
    init_ephemeris(None)
    result = {}

    def worker():
        # Lahiri ayanamsa in 2026 is ~24.23deg; Fagan-Bradley (the default that
        # leaks in on an un-configured thread) is ~25.11deg.
        result["value"] = ayanamsa(swe.julday(2026, 7, 14, 12.0))

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert 24.0 < result["value"] < 24.5, (
        f"expected Lahiri (~24.23), got {result['value']} — sidereal mode did "
        "not apply on the worker thread"
    )


def test_nakshatra_matches_drik_via_api(panchang_for):
    """New York, 14 Jul 2026: Punarvasu ends 02:39 PM local (Drik Panchang).

    `panchang_for` runs through the same code path used by the API; this pins the
    absolute-longitude result that the thread bug used to shift by ~1.5 hours.
    """
    p = panchang_for("new_york", date(2026, 7, 14))
    first = p["nakshatra"][0]
    assert first["name"] == "Punarvasu"
    end = datetime.fromisoformat(first["end"])
    assert end.strftime("%Y-%m-%d %H:%M") == "2026-07-14 14:39"
