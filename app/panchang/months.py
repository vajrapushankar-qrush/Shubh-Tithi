"""Lunar month (amanta + purnimanta), adhika masa, samvatsara, Shaka/Vikram
years, moon/sun rashi, and solar (sankranti-based) months.

Naming rule (amanta): a lunar month runs new-moon -> new-moon; it is named after
the solar month (rashi) the Sun *enters* during that lunar month. If the Sun
enters no new rashi within the lunar month (i.e. two new moons fall inside one
solar month), that month is an **adhika masa** (intercalary) and borrows the name
of the following nija month. This matches Drik Panchang for ordinary months; the
adhika-masa naming edge is pinned by a golden test.

Purnimanta reckoning shares the amanta name during Shukla paksha and takes the
*next* month's name during Krishna paksha (the purnimanta month rolls over at
Purnima, half a month ahead of the amanta rollover at Amavasya).
"""
from __future__ import annotations

from . import elements, names
from app.astronomy.rootfind import next_boundary, RATE_ELONGATION, RATE_SUN

_SECOND = 1.0 / 86400.0


# --- New moon (conjunction) finding via tithi boundaries -------------------
def next_new_moon(jd: float, angle_funcs) -> float:
    """First conjunction (elongation 360->0) strictly after ``jd``.

    Amavasya (tithi index 29) ends exactly at the new moon, so we walk tithi
    boundaries until one whose *ending* tithi is index 29.
    """
    cur = jd
    for _ in range(35):  # at most ~30 tithis in a lunation
        end, index_before = next_boundary(angle_funcs["elong"], 12.0, cur, RATE_ELONGATION)
        if index_before == 29:
            return end
        cur = end + _SECOND
    raise RuntimeError("no new moon found within search window")


def prev_new_moon(jd: float, angle_funcs) -> float:
    """Last conjunction at or before ``jd``."""
    # Step back beyond one lunation, then walk forward to the last one <= jd.
    start = jd - 31.0
    cur = start
    last = None
    for _ in range(40):
        end, index_before = next_boundary(angle_funcs["elong"], 12.0, cur, RATE_ELONGATION)
        if end > jd:
            break
        if index_before == 29:
            last = end
        cur = end + _SECOND
    if last is None:
        # Fallback: search a wider window.
        cur = jd - 62.0
        for _ in range(80):
            end, index_before = next_boundary(angle_funcs["elong"], 12.0, cur, RATE_ELONGATION)
            if end > jd:
                break
            if index_before == 29:
                last = end
            cur = end + _SECOND
    return last


# --- Rashi (with optional transition time) --------------------------------
def rashi_with_transition(
    jd_ref: float, body_angle_func, rate: float
) -> dict:
    """Rashi at ``jd_ref`` plus the transition instant if a sign change occurs
    within ~1 day after ``jd_ref`` (caller decides whether it lands in the day).
    """
    longitude = body_angle_func(jd_ref)
    idx = elements.rashi_index(longitude)
    end, index_before = next_boundary(body_angle_func, 30.0, jd_ref, rate, max_days=45.0)
    return {
        **elements.describe_rashi(idx),
        "transition_jd": end,  # when this rashi ends (caller renders/filters)
    }


# --- Lunar month ------------------------------------------------------------
def lunar_month(sunrise_jd: float, angle_funcs) -> dict:
    """Amanta + purnimanta month names, adhika flag, for the day at ``sunrise_jd``."""
    start_nm = prev_new_moon(sunrise_jd, angle_funcs)
    next_nm = next_new_moon(sunrise_jd, angle_funcs)

    sun = angle_funcs["sun"]
    r_start = elements.rashi_index(sun(start_nm + _SECOND))
    r_end = elements.rashi_index(sun(next_nm - _SECOND))

    if r_end != r_start:
        # Normal month: Sun entered rashi r_end during this lunation.
        amanta_idx = (r_end + 1) % 12
        adhika = False
    else:
        # No sankranti within the lunation -> adhika masa. It borrows the name
        # of the following nija month, which will contain the ingress into the
        # next rashi (r_start + 1).
        amanta_idx = (r_start + 2) % 12
        adhika = True

    # Paksha of the day (at sunrise) drives the purnimanta rollover.
    s, m = angle_funcs["sun"](sunrise_jd), angle_funcs["moon"](sunrise_jd)
    tithi_no = (elements.tithi_index(s, m) % 30) + 1
    paksha = names.tithi_paksha(tithi_no)
    purnimanta_idx = amanta_idx if paksha == "Shukla" else (amanta_idx + 1) % 12

    return {
        "amanta": ("Adhika " if adhika else "") + names.LUNAR_MONTHS[amanta_idx],
        "purnimanta": names.LUNAR_MONTHS[purnimanta_idx],
        "adhika_masa": adhika,
        "amanta_index": amanta_idx,
    }


# --- Samvatsara + years -----------------------------------------------------
def samvatsara_and_years(sunrise_jd: float, angle_funcs, gregorian_year: int) -> dict:
    """Shaka & Vikram year numbers and the 60-year samvatsara name.

    Year boundaries follow the lunar new year (Chaitra Shukla Pratipada). We
    approximate the boundary by the Sun's sidereal longitude: the Shaka/Vikram
    year increments around the Mesha ingress / Chaitra, so a date whose amanta
    month is Phalguna-or-earlier in the Gregorian year start belongs to the
    previous elapsed year.
    """
    lm = lunar_month(sunrise_jd, angle_funcs)
    amanta_idx = lm["amanta_index"]

    # Shaka elapsed year: Gregorian - 78, minus 1 before Chaitra new year.
    # amanta_idx 0 == Chaitra; months Magha(10)/Phalguna(11) at the start of a
    # Gregorian year are still the *previous* Shaka year.
    shaka = gregorian_year - 78
    if amanta_idx >= 10:  # Magha, Phalguna -> before Chaitra rollover
        shaka -= 1
    vikram = shaka + 135  # Vikram Samvat = Shaka + 135

    # Samvatsara from Shaka year: verified against 2025-26 -> Vishvavasu.
    samvatsara_idx = (shaka + 11) % 60
    return {
        "samvatsara": names.SAMVATSARAS[samvatsara_idx],
        "shaka_year": shaka,
        "vikram_year": vikram,
    }


# --- Solar (sankranti-based) months ----------------------------------------
def solar_months(jd_ref: float, angle_funcs) -> dict:
    """Regional solar month names from the Sun's current sidereal rashi, plus
    the current solar-month's sankranti (ingress) instant.
    """
    sun = angle_funcs["sun"]
    r = elements.rashi_index(sun(jd_ref))
    # Sankranti that began the current solar month = previous Sun sign ingress.
    # We expose the *upcoming* sankranti (end of current solar month) as an ISO
    # instant at the derivation layer; here we return names + the rashi.
    return {
        "sidereal_rashi_index": r,
        "tamil_month": names.TAMIL_MONTHS[r],
        "malayalam_month": names.MALAYALAM_MONTHS[r],
        "bengali_month": names.BENGALI_MONTHS[r],
    }
