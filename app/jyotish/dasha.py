"""Vimshottari dasha — the 120-year cycle keyed to the moon's nakshatra.

The cycle assigns each of the 27 nakshatras a ruling graha on a repeating
9-lord sequence, so nakshatra *i* is ruled by ``ORDER[i % 9]``. A native's
first mahadasha is the lord of the birth nakshatra, but only the *unelapsed*
portion of it: the moon having travelled 42.6% of the way through Dhanishta
means 42.6% of Mars' 7 years is already spent at birth.

Antardashas subdivide each mahadasha in the same cyclic order, starting with
the mahadasha lord itself, each proportioned as
``maha_years * antar_lord_years / 120``.

Year length is the **365.25-day Julian year**, the usual convention for
Vimshottari. (Some traditions use a 360-day "savana" year, which drifts ~1.5%
— about 22 months over the full 120-year cycle. This module does not implement
that variant.)
"""
from __future__ import annotations

from datetime import datetime, timedelta

# Cyclic lord order and each lord's share of the 120-year cycle.
ORDER: list[str] = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
]
YEARS: dict[str, float] = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}
TOTAL_YEARS = 120.0
YEAR_DAYS = 365.25

NAK_ARC = 360.0 / 27.0


def _delta(years: float) -> timedelta:
    return timedelta(days=years * YEAR_DAYS)


def nakshatra_lord(nakshatra_index0: int) -> str:
    """Ruling graha of a 0-based nakshatra index (Ashwini = 0 -> Ketu)."""
    return ORDER[nakshatra_index0 % 9]


def _stamp(birth: datetime, offset_years: float) -> str:
    """ISO-8601 timestamp ``offset_years`` after ``birth``.

    Raises ``OverflowError`` past ``datetime.max``; callers stop the sequence
    there rather than propagating it.
    """
    return (birth + _delta(offset_years)).isoformat()


def vimshottari(
    moon_longitude: float,
    birth: datetime,
    *,
    span_years: float = 120.0,
    include_antar: bool = True,
) -> list[dict]:
    """Mahadashas (with antardashas) from ``birth`` forward.

    ``birth`` must be timezone-aware; every emitted timestamp carries the same
    UTC offset it does, so the ISO strings sort lexicographically.

    The first mahadasha is truncated to the balance remaining at birth. The
    sequence runs until it covers ``birth + span_years``, so the final period
    normally extends past that horizon rather than stopping short of it.

    All arithmetic is done in *year offsets from birth* and only materialised
    into datetimes for offsets at or after birth. The elapsed head of the first
    mahadasha therefore never becomes a datetime, which matters because for a
    birth in the first century CE winding back to its notional start would fall
    below ``datetime.min``.
    """
    nak_index = int((moon_longitude % 360.0) // NAK_ARC)
    elapsed_fraction = ((moon_longitude % 360.0) % NAK_ARC) / NAK_ARC

    lord = nakshatra_lord(nak_index)
    elapsed_years = YEARS[lord] * elapsed_fraction

    offset = -elapsed_years  # notional start of the in-progress mahadasha
    index = ORDER.index(lord)
    out: list[dict] = []

    while offset < span_years:
        maha_lord = ORDER[index % 9]
        maha_years = YEARS[maha_lord]
        maha_end = offset + maha_years

        if maha_end > 0.0:
            children: list[dict] = []
            if include_antar:
                cursor = offset
                first = ORDER.index(maha_lord)
                for step in range(9):
                    antar_lord = ORDER[(first + step) % 9]
                    # Snap the final antardasha to the mahadasha's own end.
                    # Accumulating nine proportional slices drifts by a
                    # microsecond or so in float, and the antardashas must
                    # tile their parent exactly for a consumer to walk them.
                    antar_end = (
                        maha_end if step == 8
                        else cursor + maha_years * YEARS[antar_lord] / TOTAL_YEARS
                    )
                    if antar_end > 0.0:
                        try:
                            children.append({
                                "level": "antar",
                                "lord": antar_lord,
                                "start": _stamp(birth, max(cursor, 0.0)),
                                "end": _stamp(birth, antar_end),
                            })
                        except OverflowError:
                            break
                    cursor = antar_end
            try:
                out.append({
                    "level": "maha",
                    "lord": maha_lord,
                    "start": _stamp(birth, max(offset, 0.0)),
                    "end": _stamp(birth, maha_end),
                    "children": children,
                })
            except OverflowError:
                # Past datetime.max (births after ~year 9879). Stop cleanly
                # rather than failing the whole chart.
                break

        offset = maha_end
        index += 1

    return out


def balance_at_birth(moon_longitude: float) -> dict:
    """The unelapsed portion of the birth mahadasha, for display."""
    nak_index = int((moon_longitude % 360.0) // NAK_ARC)
    elapsed_fraction = ((moon_longitude % 360.0) % NAK_ARC) / NAK_ARC
    lord = nakshatra_lord(nak_index)
    remaining = YEARS[lord] * (1.0 - elapsed_fraction)
    years = int(remaining)
    months_f = (remaining - years) * 12
    months = int(months_f)
    days = int((months_f - months) * 30)
    return {
        "lord": lord,
        "years": years,
        "months": months,
        "days": days,
        "total_years": round(remaining, 6),
    }
