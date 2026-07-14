"""Unit tests for the pure index math (no ephemeris needed)."""
from __future__ import annotations

from app.panchang import elements, names


def test_tithi_index_from_elongation():
    # elongation = moon - sun.
    assert elements.tithi_index(0.0, 0.0) == 0          # Shukla Pratipada
    assert elements.tithi_index(0.0, 11.99) == 0
    assert elements.tithi_index(0.0, 12.01) == 1        # Dwitiya
    assert elements.tithi_index(0.0, 180.0) == 15       # Krishna Pratipada (16th)
    assert elements.tithi_index(0.0, 359.9) == 29       # Amavasya
    # Wrap: moon just past sun.
    assert elements.tithi_index(350.0, 2.0) == 1        # elong = 12 -> Dwitiya


def test_tithi_describe_and_paksha():
    assert elements.describe_tithi(0) == {"number": 1, "name": "Pratipada", "paksha": "Shukla"}
    assert elements.describe_tithi(14) == {"number": 15, "name": "Purnima", "paksha": "Shukla"}
    assert elements.describe_tithi(15) == {"number": 16, "name": "Pratipada", "paksha": "Krishna"}
    assert elements.describe_tithi(29) == {"number": 30, "name": "Amavasya", "paksha": "Krishna"}


def test_nakshatra_index_and_pada():
    assert elements.nakshatra_index(0.0) == 0           # Ashwini
    assert elements.nakshatra_pada(0.0) == 1
    assert elements.nakshatra_pada(3.3) == 1
    assert elements.nakshatra_pada(3.34) == 2
    assert elements.nakshatra_index(13.34) == 1         # Bharani
    assert elements.nakshatra_index(359.9) == 26        # Revati
    assert names.NAKSHATRAS[elements.nakshatra_index(13.34)] == "Bharani"


def test_yoga_index():
    assert elements.yoga_index(0.0, 0.0) == 0           # Vishkambha
    assert elements.yoga_index(6.7, 6.7) == 1           # sum 13.4 -> Priti
    assert elements.yoga_index(200.0, 159.9) == 26      # sum 359.9 -> Vaidhriti


def test_karana_index_and_names():
    # 60 half-tithis per lunation.
    assert elements.karana_index(0.0, 0.0) == 0
    assert names.karana_name(0) == "Kimstughna"         # fixed first
    assert names.karana_name(1) == "Bava"               # movable cycle start
    assert names.karana_name(7) == "Vishti"             # 7th movable
    assert names.karana_name(8) == "Bava"               # cycle repeats
    assert names.karana_name(57) == "Shakuni"           # fixed tail
    assert names.karana_name(58) == "Chatushpada"
    assert names.karana_name(59) == "Naga"


def test_karana_movable_cycle_covers_middle():
    # Indices 1..56 must all be one of the 7 movable karanas.
    movable = {"Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"}
    for i in range(1, 57):
        assert names.karana_name(i) in movable


def test_rashi_index():
    assert elements.rashi_index(0.0) == 0               # Mesha
    assert elements.rashi_index(29.9) == 0
    assert elements.rashi_index(30.0) == 1              # Vrishabha
    assert elements.rashi_index(359.9) == 11            # Meena
