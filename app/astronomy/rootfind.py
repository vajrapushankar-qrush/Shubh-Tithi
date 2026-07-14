"""Root-finding for Panchang element boundaries.

Every element we track (tithi, karana, nakshatra, yoga, moon/sun rashi) is a
``floor(angle / unit)`` of an angle that is **monotonically increasing** on the
timescale of interest:

* tithi / karana: ``(moon - sun)`` elongation rises ~12.2°/day (moon always
  outpaces the sun in longitude), so it never reverses.
* nakshatra: moon longitude rises ~13.2°/day.
* yoga: ``(sun + moon)`` rises ~14.2°/day.
* moon rashi: moon longitude; sun rashi: sun longitude ~1°/day.

Because the driving angle is monotonic, each ``unit`` boundary is crossed
exactly once and we can bracket-then-bisect to the crossing instant. We do NOT
approximate boundaries by daily interpolation — we solve for the true instant to
sub-second precision (well past the minute precision Drik Panchang reports).
"""
from __future__ import annotations

from typing import Callable

# Nominal rise rate (deg/day) of each driving angle — used only to size the
# initial bracket search step; correctness does not depend on its accuracy.
RATE_ELONGATION = 12.19  # tithi, karana
RATE_MOON = 13.18  # nakshatra, moon rashi
RATE_SUN_PLUS_MOON = 14.18  # yoga
RATE_SUN = 0.986  # sun rashi

_SECOND = 1.0 / 86400.0


def _signed_gap(angle: float, target: float) -> float:
    """Signed angular distance from ``angle`` up to ``target`` in (-180, 180].

    Negative while ``angle`` is still approaching ``target`` from below;
    crosses 0 exactly at the boundary; handles the 360->0 wrap cleanly.
    """
    return ((angle - target + 180.0) % 360.0) - 180.0


def next_boundary(
    angle_func: Callable[[float], float],
    unit: float,
    jd_ref: float,
    rate: float,
    max_days: float = 45.0,
) -> tuple[float, int] | None:
    """Find the next boundary of ``floor(angle/unit)`` strictly after ``jd_ref``.

    Returns ``(end_jd, index_before)`` where ``index_before`` is the element
    index (0-based, unreduced) in effect at ``jd_ref``, and ``end_jd`` is when it
    ends. Returns ``None`` if no crossing within ``max_days`` (should not happen
    for real inputs).
    """
    a0 = angle_func(jd_ref) % 360.0
    index_before = int(a0 // unit)
    target = ((index_before + 1) * unit) % 360.0

    def h(jd: float) -> float:
        return _signed_gap(angle_func(jd) % 360.0, target)

    step = max(unit / max(rate, 1e-6) / 8.0, 1.0 / 1440.0)  # >= 1 minute
    prev, h_prev = jd_ref, h(jd_ref)
    # If we're numerically sitting exactly on the boundary, nudge forward.
    if h_prev >= 0.0:
        prev = jd_ref + _SECOND
        h_prev = h(prev)

    span = 0.0
    lo = hi = None
    while span < max_days:
        cur = prev + step
        h_cur = h(cur)
        if h_prev < 0.0 <= h_cur:
            lo, hi = prev, cur
            break
        prev, h_prev = cur, h_cur
        span += step
    if lo is None:
        return None

    # Bisection to ~1 second.
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if h(mid) < 0.0:
            lo = mid
        else:
            hi = mid
        if (hi - lo) < _SECOND:
            break
    return 0.5 * (lo + hi), index_before


def enumerate_boundaries(
    angle_func: Callable[[float], float],
    unit: float,
    jd_from: float,
    jd_to: float,
    rate: float,
) -> list[tuple[float, int]]:
    """All boundaries with end time in ``(jd_from, jd_to]``.

    Returns ``[(end_jd, index_before), ...]`` in time order. ``index_before`` is
    the unreduced 0-based element index that *ends* at ``end_jd``.
    """
    events: list[tuple[float, int]] = []
    jd = jd_from
    guard = 0
    max_events = int((jd_to - jd_from) * rate / unit) + 8
    while jd < jd_to and guard <= max_events:
        result = next_boundary(angle_func, unit, jd, rate)
        if result is None:
            break
        end_jd, index_before = result
        if end_jd > jd_to:
            break
        events.append((end_jd, index_before))
        jd = end_jd + _SECOND
        guard += 1
    return events
