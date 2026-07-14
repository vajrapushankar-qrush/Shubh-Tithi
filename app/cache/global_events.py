"""Compute and cache location-independent element boundaries + eclipses.

These instants (tithi/karana/nakshatra/yoga ends, moon/sun rashi transits,
eclipses) are the same for every city on Earth, so we compute them once over a
JD span and reuse them for all cities. Per-city work is reduced to rise/set +
rendering into local time.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select

from app.astronomy.rootfind import (
    RATE_ELONGATION,
    RATE_MOON,
    RATE_SUN,
    RATE_SUN_PLUS_MOON,
    enumerate_boundaries,
)
from app.db import GlobalEclipse, GlobalEvent, get_meta, set_meta
from app.panchang import elements
from app.panchang.eclipses import find_all_eclipses

log = logging.getLogger("shubhtithi.global")

# (event_type, angle_func_key, arc_degrees, nominal_rate)
EVENT_SPECS = [
    ("tithi", "elong", elements.TITHI_ARC, RATE_ELONGATION),
    ("karana", "elong", elements.KARANA_ARC, RATE_ELONGATION),
    ("nakshatra", "moon", elements.NAK_ARC, RATE_MOON),
    ("yoga", "yoga", elements.YOGA_ARC, RATE_SUN_PLUS_MOON),
    ("moon_rashi", "moon", elements.RASHI_ARC, RATE_MOON),
    ("sun_rashi", "sun", elements.RASHI_ARC, RATE_SUN),
]

_G_FROM = "global_from_jd"
_G_TO = "global_to_jd"


def _compute_span(session, jd_from: float, jd_to: float) -> None:
    """Compute all event types + eclipses over (jd_from, jd_to] and insert."""
    if jd_to <= jd_from:
        return
    angle_funcs = elements.make_angle_funcs()
    total = 0
    for event_type, key, arc, rate in EVENT_SPECS:
        boundaries = enumerate_boundaries(angle_funcs[key], arc, jd_from, jd_to, rate)
        session.bulk_insert_mappings(
            GlobalEvent,
            [
                {"event_type": event_type, "idx": idx, "end_jd": end_jd}
                for end_jd, idx in boundaries
            ],
        )
        total += len(boundaries)
    for ecl in find_all_eclipses(jd_from, jd_to):
        session.add(
            GlobalEclipse(
                kind=ecl["kind"],
                type=ecl["type"],
                max_jd=ecl["max_jd"],
                begin_jd=ecl["begin_jd"],
                end_jd=ecl["end_jd"],
            )
        )
    session.commit()
    log.info("Computed %d global events over JD [%.3f, %.3f]", total, jd_from, jd_to)


def ensure_global_coverage(session, jd_from: float, jd_to: float) -> None:
    """Guarantee global events exist across the whole [jd_from, jd_to] span,
    extending the single contiguous covered interval as needed.
    """
    g_from = get_meta(session, _G_FROM)
    g_to = get_meta(session, _G_TO)

    if g_from is None or g_to is None:
        _compute_span(session, jd_from, jd_to)
        set_meta(session, _G_FROM, str(jd_from))
        set_meta(session, _G_TO, str(jd_to))
        session.commit()
        return

    g_from_f, g_to_f = float(g_from), float(g_to)
    # Extend backwards.
    if jd_from < g_from_f:
        _compute_span(session, jd_from, g_from_f)
        g_from_f = jd_from
        set_meta(session, _G_FROM, str(g_from_f))
    # Extend forwards.
    if jd_to > g_to_f:
        _compute_span(session, g_to_f, jd_to)
        g_to_f = jd_to
        set_meta(session, _G_TO, str(g_to_f))
    session.commit()


def events_in_window(
    session, event_type: str, jd_start: float, jd_end: float
) -> list[tuple[float, int]]:
    """Boundaries of ``event_type`` with end instant in (jd_start, jd_end], in
    time order, as (end_jd, idx)."""
    stmt = (
        select(GlobalEvent.end_jd, GlobalEvent.idx)
        .where(
            GlobalEvent.event_type == event_type,
            GlobalEvent.end_jd > jd_start,
            GlobalEvent.end_jd <= jd_end,
        )
        .order_by(GlobalEvent.end_jd)
    )
    return [(row[0], row[1]) for row in session.execute(stmt)]


def next_event_after(
    session, event_type: str, jd: float
) -> tuple[float, int] | None:
    stmt = (
        select(GlobalEvent.end_jd, GlobalEvent.idx)
        .where(GlobalEvent.event_type == event_type, GlobalEvent.end_jd > jd)
        .order_by(GlobalEvent.end_jd)
        .limit(1)
    )
    row = session.execute(stmt).first()
    return (row[0], row[1]) if row else None


def eclipses_overlapping(
    session, jd_start: float, jd_end: float
) -> list[GlobalEclipse]:
    stmt = (
        select(GlobalEclipse)
        .where(GlobalEclipse.end_jd > jd_start, GlobalEclipse.begin_jd <= jd_end)
        .order_by(GlobalEclipse.max_jd)
    )
    return list(session.scalars(stmt))


def clear_global(session) -> None:
    session.execute(delete(GlobalEvent))
    session.execute(delete(GlobalEclipse))
    session.commit()
