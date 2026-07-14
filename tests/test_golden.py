"""Golden tests against Drik Panchang (https://www.drikpanchang.com).

HOW TO USE
----------
Each fixture below is a real (city, date) whose expected values must be filled
in FROM DRIK PANCHANG and verified by a human. Until an ``expected`` block is
filled (its fields are non-None), that case is skipped with a clear message.

To fill a fixture: open Drik Panchang for the city + date, read the sunrise-tithi
name/paksha and its end time (local), the sunrise nakshatra and its end time,
then paste them below. End times are compared to the minute.

Cover, per the spec:
  * New York, London, Hyderabad, Bengaluru
  * one kshaya (skipped) / vriddhi (repeated) tithi day
  * one adhika-masa month
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

# --- TODO: fill each `expected` from Drik Panchang and set verified=True ------
GOLDEN = [
    {
        "id": "hyderabad-2026-08-15",
        "city": "hyderabad",
        "date": date(2026, 8, 15),
        "expected": {
            # "tithi_name": "Tritiya", "tithi_paksha": "Shukla",
            # "tithi_end_local": "2026-08-15T17:29",   # HH:MM local
            # "nakshatra_name": "Uttara Phalguni",
            # "nakshatra_end_local": "2026-08-16T03:26",
        },
    },
    {"id": "new_york-adhika-masa", "city": "new_york", "date": None, "expected": {},
     "note": "TODO: pick a date inside an Adhika masa (e.g. Adhika months are "
             "rarer; use a known intercalary month) and fill expected."},
    {"id": "london-kshaya-or-vriddhi", "city": "london", "date": None, "expected": {},
     "note": "TODO: pick a day with a kshaya (skipped) or vriddhi (repeated) "
             "tithi and fill expected (assert the extra tithi appears in the list)."},
    {"id": "bengaluru-sample", "city": "bengaluru", "date": None, "expected": {},
     "note": "TODO: fill a verified Bengaluru date."},
]


def _minute(iso_local: str) -> str:
    dt = datetime.fromisoformat(iso_local)
    return dt.strftime("%Y-%m-%dT%H:%M")


@pytest.mark.parametrize("fx", GOLDEN, ids=[f["id"] for f in GOLDEN])
def test_golden_against_drik(fx, panchang_for):
    if fx["date"] is None or not fx["expected"]:
        pytest.skip(f"TODO fixture not filled: {fx['id']}"
                    + (f" — {fx.get('note')}" if fx.get("note") else ""))

    p = panchang_for(fx["city"], fx["date"])
    exp = fx["expected"]
    sunrise_tithi = p["tithi"][0]
    sunrise_nak = p["nakshatra"][0]

    if "tithi_name" in exp:
        assert sunrise_tithi["name"] == exp["tithi_name"]
    if "tithi_paksha" in exp:
        assert sunrise_tithi["paksha"] == exp["tithi_paksha"]
    if "tithi_end_local" in exp:
        assert _minute(sunrise_tithi["end"]) == exp["tithi_end_local"]
    if "nakshatra_name" in exp:
        assert sunrise_nak["name"] == exp["nakshatra_name"]
    if "nakshatra_end_local" in exp:
        assert _minute(sunrise_nak["end"]) == exp["nakshatra_end_local"]


def test_panchang_structure_is_complete(panchang_for):
    """Non-golden guard: every documented field is present and well-formed."""
    p = panchang_for("hyderabad", date(2026, 8, 15))
    for key in ["vara", "tithi", "nakshatra", "yoga", "karana", "moon_rashi",
                "sun_rashi", "lunar_month", "samvatsara", "shaka_year",
                "vikram_year", "solar_month", "sun", "moon", "inauspicious",
                "auspicious", "choghadiya", "abhijit_muhurat", "bhadra",
                "eclipse"]:
        assert key in p, key
    assert p["tithi"] and p["tithi"][0]["name"]
    assert p["sun"]["sunrise"] and p["sun"]["sunset"]
    for w in ("rahu_kalam", "yamaganda", "gulika_kalam"):
        assert p["inauspicious"][w]["start"] < p["inauspicious"][w]["end"]
    # Auspicious muhurats + Choghadiya bands present.
    assert p["auspicious"]["abhijit_muhurat"]["start"]
    assert len(p["choghadiya"]["day"]) == 8 and len(p["choghadiya"]["night"]) == 8
    assert p["choghadiya"]["day"][0]["quality"] in ("good", "neutral", "bad")


def test_nakshatra_pada_only_on_sunrise_entry(panchang_for):
    """Pada is meaningful only for the sunrise nakshatra; later entries (which
    always start at pada 1) omit it. New York 2026-07-14 has two nakshatras."""
    p = panchang_for("new_york", date(2026, 7, 14))
    naks = p["nakshatra"]
    assert len(naks) >= 2
    assert naks[0]["name"] == "Punarvasu" and naks[0]["pada"] == 3
    assert "pada" not in naks[1]           # Pushya (starts at pada 1) — omitted
