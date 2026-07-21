"""Day-eighth based inauspicious windows and Abhijit muhurat.

The daytime (local sunrise -> sunset) is divided into 8 equal parts. Rahu Kalam,
Yamaganda and Gulika Kalam each occupy one part; which part depends on the
weekday. Segments are numbered 1..8 from sunrise.

Abhijit muhurat is the 8th of 15 equal daytime muhurtas — centred on solar noon.
It is traditionally avoided on Wednesdays (flagged, not omitted).
"""
from __future__ import annotations

# Indexed by weekday 0=Sunday .. 6=Saturday (matches names.VARAS ordering).
# Values are the 1-based day-eighth each window occupies.
RAHU_SEGMENT = [8, 2, 7, 5, 6, 4, 3]
YAMAGANDA_SEGMENT = [5, 4, 3, 2, 1, 7, 6]
GULIKA_SEGMENT = [7, 6, 5, 4, 3, 2, 1]


def _segment(sunrise_jd: float, sunset_jd: float, seg_1based: int) -> tuple[float, float]:
    eighth = (sunset_jd - sunrise_jd) / 8.0
    start = sunrise_jd + (seg_1based - 1) * eighth
    return start, start + eighth


def inauspicious_windows(
    sunrise_jd: float, sunset_jd: float, weekday_sun0: int
) -> dict[str, tuple[float, float]]:
    """Return {name: (start_jd, end_jd)} for Rahu/Yamaganda/Gulika."""
    return {
        "rahu_kalam": _segment(sunrise_jd, sunset_jd, RAHU_SEGMENT[weekday_sun0]),
        "yamaganda": _segment(sunrise_jd, sunset_jd, YAMAGANDA_SEGMENT[weekday_sun0]),
        "gulika_kalam": _segment(sunrise_jd, sunset_jd, GULIKA_SEGMENT[weekday_sun0]),
    }


def abhijit_muhurat(
    sunrise_jd: float, sunset_jd: float, weekday_sun0: int
) -> dict:
    """Abhijit = 8th of 15 daytime muhurtas. Avoided on Wednesday (weekday 3)."""
    muhurta = (sunset_jd - sunrise_jd) / 15.0
    start = sunrise_jd + 7 * muhurta
    end = start + muhurta
    return {
        "start_jd": start,
        "end_jd": end,
        "avoided_today": weekday_sun0 == 3,  # Wednesday
    }


# --- Choghadiya ------------------------------------------------------------
# The primary muhurat time-band system. Day (sunrise->sunset) and night
# (sunset->next sunrise) are each split into 8 equal parts. The 7 choghadiyas
# rotate in a fixed planetary order; the day's first band and the night's first
# band are weekday-dependent.
CHOGHADIYA_CYCLE = ["Udveg", "Char", "Labh", "Amrit", "Kaal", "Shubh", "Rog"]
CHOGHADIYA_QUALITY = {
    "Amrit": "good", "Shubh": "good", "Labh": "good",
    "Char": "neutral",
    "Rog": "bad", "Kaal": "bad", "Udveg": "bad",
}


def _choghadiya_bands(start_jd: float, end_jd: float, first_index: int) -> list[dict]:
    span = (end_jd - start_jd) / 8.0
    bands = []
    for i in range(8):
        name = CHOGHADIYA_CYCLE[(first_index + i) % 7]
        s = start_jd + i * span
        bands.append({
            "name": name,
            "quality": CHOGHADIYA_QUALITY[name],
            "start_jd": s,
            "end_jd": s + span,
        })
    return bands


def choghadiya(
    sunrise_jd: float, sunset_jd: float, next_sunrise_jd: float, weekday_sun0: int
) -> dict:
    """Return {'day': [...8 bands], 'night': [...8 bands]}.

    Day first band index = (weekday*3) mod 7 (Sun=Udveg, Mon=Amrit, ...);
    night first band = day first + 5 (mod 7). Verified against a published almanac.
    """
    day_start = (weekday_sun0 * 3) % 7
    night_start = (day_start + 5) % 7
    return {
        "day": _choghadiya_bands(sunrise_jd, sunset_jd, day_start),
        "night": _choghadiya_bands(sunset_jd, next_sunrise_jd, night_start),
    }


# --- Brahma Muhurat --------------------------------------------------------
def brahma_muhurat(prev_sunset_jd: float, sunrise_jd: float) -> dict:
    """Auspicious pre-dawn window: the 14th of 15 equal night muhurtas, i.e. the
    muhurta spanning from 2 to 1 night-muhurtas before sunrise."""
    night_muhurta = (sunrise_jd - prev_sunset_jd) / 15.0
    return {
        "start_jd": sunrise_jd - 2 * night_muhurta,
        "end_jd": sunrise_jd - night_muhurta,
    }
