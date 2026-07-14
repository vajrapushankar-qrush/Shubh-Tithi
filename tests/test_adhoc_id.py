"""Ad-hoc (lat/lon/tz) city ids must be stable across processes/restarts."""
from __future__ import annotations

import hashlib

from app.routers.panchang import _ADHOC_BASE, _adhoc_id


def test_adhoc_id_is_deterministic():
    a = _adhoc_id(17.385, 78.4867, "Asia/Kolkata")
    b = _adhoc_id(17.385, 78.4867, "Asia/Kolkata")
    assert a == b


def test_adhoc_id_matches_stable_md5_digest():
    # Pinned value — must not depend on Python's per-process hash randomisation.
    key = "17.385|78.4867|Asia/Kolkata"
    expected = _ADHOC_BASE + int(hashlib.md5(key.encode()).hexdigest()[:8], 16) % 90_000_000
    assert _adhoc_id(17.385, 78.4867, "Asia/Kolkata") == expected == 933838245


def test_adhoc_id_distinguishes_locations():
    assert _adhoc_id(17.385, 78.4867, "Asia/Kolkata") != _adhoc_id(40.7128, -74.006, "America/New_York")
    # Rounding to 4 dp means sub-metre differences collapse to the same id.
    assert _adhoc_id(17.385, 78.48671, "Asia/Kolkata") == _adhoc_id(17.385, 78.48669, "Asia/Kolkata")
