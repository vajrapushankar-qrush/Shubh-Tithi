"""Rahu Kalam / Yamaganda / Gulika segment-per-weekday tests, and Abhijit."""
from __future__ import annotations

from app.panchang import windows

# A simple 06:00 -> 18:00 day expressed in JD-like units (1 day = 1.0).
# Use fractional days from an arbitrary midnight so segment math is exact:
# sunrise at 0.25 (06:00), sunset at 0.75 (18:00); each eighth = 1.5h = 0.0625.
SUNRISE = 0.25
SUNSET = 0.75
EIGHTH = (SUNSET - SUNRISE) / 8.0


def _segment_number(start_jd: float) -> int:
    """Which 1-based eighth does start_jd fall in?"""
    return round((start_jd - SUNRISE) / EIGHTH) + 1


# Expected day-eighth per weekday (0=Sun..6=Sat), from published tables.
EXPECTED = {
    "rahu_kalam": [8, 2, 7, 5, 6, 4, 3],
    "yamaganda": [5, 4, 3, 2, 1, 7, 6],
    "gulika_kalam": [7, 6, 5, 4, 3, 2, 1],
}


def test_rahu_yamaganda_gulika_per_weekday():
    for weekday in range(7):
        w = windows.inauspicious_windows(SUNRISE, SUNSET, weekday)
        for key, table in EXPECTED.items():
            start, end = w[key]
            assert _segment_number(start) == table[weekday], (key, weekday)
            # Each window is exactly one eighth long.
            assert abs((end - start) - EIGHTH) < 1e-9


def test_abhijit_is_8th_of_15_and_wednesday_flag():
    for weekday in range(7):
        a = windows.abhijit_muhurat(SUNRISE, SUNSET, weekday)
        muhurta = (SUNSET - SUNRISE) / 15.0
        assert abs(a["start_jd"] - (SUNRISE + 7 * muhurta)) < 1e-9
        assert abs((a["end_jd"] - a["start_jd"]) - muhurta) < 1e-9
        assert a["avoided_today"] == (weekday == 3)  # Wednesday


# Published day-Choghadiya first band per weekday (0=Sun..6=Sat).
EXPECTED_DAY_FIRST = ["Udveg", "Amrit", "Rog", "Labh", "Shubh", "Char", "Kaal"]
# Published night-Choghadiya first band per weekday.
EXPECTED_NIGHT_FIRST = ["Shubh", "Char", "Kaal", "Udveg", "Amrit", "Rog", "Labh"]


def test_choghadiya_first_band_per_weekday():
    NEXT_SUNRISE = SUNRISE + 1.0
    for weekday in range(7):
        c = windows.choghadiya(SUNRISE, SUNSET, NEXT_SUNRISE, weekday)
        assert c["day"][0]["name"] == EXPECTED_DAY_FIRST[weekday], weekday
        assert c["night"][0]["name"] == EXPECTED_NIGHT_FIRST[weekday], weekday
        # 8 contiguous bands each side, day covers sunrise->sunset exactly.
        assert len(c["day"]) == 8 and len(c["night"]) == 8
        assert abs(c["day"][0]["start_jd"] - SUNRISE) < 1e-9
        assert abs(c["day"][-1]["end_jd"] - SUNSET) < 1e-9
        assert abs(c["night"][0]["start_jd"] - SUNSET) < 1e-9
        assert abs(c["night"][-1]["end_jd"] - NEXT_SUNRISE) < 1e-9


def test_choghadiya_quality_labels():
    c = windows.choghadiya(SUNRISE, SUNSET, SUNRISE + 1.0, 0)
    for band in c["day"] + c["night"]:
        if band["name"] in ("Amrit", "Shubh", "Labh"):
            assert band["quality"] == "good"
        elif band["name"] == "Char":
            assert band["quality"] == "neutral"
        else:
            assert band["quality"] == "bad"


def test_brahma_muhurat_is_14th_night_muhurta():
    prev_sunset = SUNRISE - 0.5  # 12h night
    b = windows.brahma_muhurat(prev_sunset, SUNRISE)
    night_muhurta = (SUNRISE - prev_sunset) / 15.0
    assert abs(b["end_jd"] - (SUNRISE - night_muhurta)) < 1e-9
    assert abs((b["end_jd"] - b["start_jd"]) - night_muhurta) < 1e-9
