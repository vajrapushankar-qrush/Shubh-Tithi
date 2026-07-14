"""Timezone edge: a tithi that ends just after local midnight must still be
attributed to the correct Hindu day (sunrise-to-sunrise), with its end time
rendered on the *next* local calendar date.

We scan a month for New York (large UTC offset) to find a day whose sunrise-tithi
ends between 00:00 and 03:00 local of the following calendar day, then assert the
attribution and rendering are correct.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest


def test_tithi_ending_after_local_midnight(panchang_for):
    found = None
    d = date(2026, 8, 1)
    for _ in range(31):
        p = panchang_for("new_york", d)
        end_iso = p["tithi"][0]["end"]
        end_dt = datetime.fromisoformat(end_iso)
        # End is on the day AFTER `d` and in the small hours -> crossed midnight.
        if end_dt.date() == d + timedelta(days=1) and end_dt.hour < 3:
            found = (d, p, end_dt)
            break
        d += timedelta(days=1)

    if found is None:
        pytest.skip("no post-midnight tithi end found in the scanned window")

    day, p, end_dt = found
    # The sunrise-tithi belongs to `day` even though it ends on the next date.
    sunrise_dt = datetime.fromisoformat(p["sun"]["sunrise"])
    assert sunrise_dt.date() == day
    assert end_dt > sunrise_dt
    # Offset is New York's (-04:00 DST or -05:00), not UTC.
    assert end_dt.utcoffset() is not None and end_dt.utcoffset().total_seconds() < 0
