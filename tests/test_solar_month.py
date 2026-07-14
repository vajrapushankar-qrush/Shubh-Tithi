"""Solar (sankranti-based) month test.

The Sun is in Karka (Cancle) from ~16 Jul to ~17 Aug 2026, which is the Tamil
month Aadi / Malayalam Karkidakam / Bengali Shrabon. This is a verifiable
sankranti fixture; add more as needed.
"""
from __future__ import annotations

from datetime import date


def test_karka_sankranti_solar_month(panchang_for):
    p = panchang_for("hyderabad", date(2026, 8, 1))
    solar = p["solar_month"]
    assert solar["tamil_month"] == "Aadi"
    assert solar["malayalam_month"] == "Karkidakam"
    assert solar["bengali_month"] == "Shrabon"
    # Sun rashi at this date is Karka.
    assert p["sun_rashi"]["name"] == "Karka"


def test_sankranti_transition_dates_present(panchang_for):
    p = panchang_for("hyderabad", date(2026, 8, 1))
    solar = p["solar_month"]
    # The current solar month started at Karka sankranti (~16 Jul 2026) and the
    # next (Simha) sankranti is ~17 Aug 2026.
    assert solar["current_sankranti"].startswith("2026-07")
    assert solar["next_sankranti"].startswith("2026-08")
