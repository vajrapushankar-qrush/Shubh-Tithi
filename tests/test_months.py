"""Shaka/Vikram year rollover at Chaitra Shukla Pratipada."""
from __future__ import annotations

from datetime import date

from app.panchang.months import samvatsara_and_years

# Lunar-month indices: Pausha=9, Magha=10, Phalguna=11, Chaitra=0.


def test_january_pausha_is_previous_shaka_year():
    # Regression: the old `amanta_idx >= 10` check missed Pausha (idx 9), which
    # extends into January -> before Chaitra new year -> previous Shaka year.
    y = samvatsara_and_years(2026, 1, 9)
    assert y["shaka_year"] == 1947
    assert y["vikram_year"] == 2082


def test_december_pausha_is_current_shaka_year():
    # Same lunar-month index (9) but in December is AFTER Chaitra -> not reduced.
    assert samvatsara_and_years(2026, 12, 9)["shaka_year"] == 1948


def test_pre_and_post_chaitra_boundary():
    assert samvatsara_and_years(2026, 2, 10)["shaka_year"] == 1947  # Feb Magha
    assert samvatsara_and_years(2026, 3, 11)["shaka_year"] == 1947  # Mar Phalguna
    assert samvatsara_and_years(2026, 4, 0)["shaka_year"] == 1948   # Apr Chaitra
    assert samvatsara_and_years(2026, 8, 5)["shaka_year"] == 1948   # Aug Bhadrapada


def test_samvatsara_anchor():
    # 2025-26 (Shaka 1947) is the Vishvavasu samvatsara.
    assert samvatsara_and_years(2025, 8, 4)["samvatsara"] == "Vishvavasu"


def test_january_date_via_full_panchang(panchang_for):
    p = panchang_for("hyderabad", date(2026, 1, 5))
    assert p["shaka_year"] == 1947
    assert p["vikram_year"] == 2082
    assert p["samvatsara"] == "Vishvavasu"
