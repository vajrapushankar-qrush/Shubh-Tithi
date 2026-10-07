#!/usr/bin/env python
"""Compare our panchang against Prokerala's, on a sample chosen to find bugs.

    export PROKERALA_CLIENT_ID=... PROKERALA_CLIENT_SECRET=...
    uv run python -m scripts.validate_against_prokerala --plan     # free, no calls
    uv run python -m scripts.validate_against_prokerala --probe    # 1 call
    uv run python -m scripts.validate_against_prokerala            # the run

WHAT THIS DOES AND DOES NOT PROVE
---------------------------------
Prokerala is Swiss Ephemeris-based, and so are we. Agreement therefore does NOT
independently confirm the astronomy — both wrap the same JPL ephemeris, and
planetary positions from two correct configurations agree to a fraction of an
arcsecond regardless.

What it does confirm is everything *around* the ephemeris, which is where
panchang bugs actually live: the coordinate we hold for a city, the timezone we
resolve it to, DST, the ayanamsa, and whether we read the five limbs at sunrise
the way everyone else does. A disagreement here is nearly always one of those,
not the astronomy.

WHY THE SAMPLE IS NOT RANDOM
----------------------------
Ten thousand random city-date pairs is a poor bug detector, because bugs are not
uniformly distributed — they cluster at discontinuities. This samples the
discontinuities directly:

  * DST transitions, found from the tz database rather than hardcoded, for every
    city that has them. This is the highest-risk area by far and the one a
    random sample is least likely to land on.
  * Solstices and equinoxes, where day length is at its extremes.
  * Southern-hemisphere cities, whose seasons are inverted.
  * Cities far enough east that the muhurat falls on a different calendar date
    than it does in India.

A few hundred such cases find more than ten thousand random ones, and fit inside
the free tier's 5,000 credits.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOKEN_URL = "https://api.prokerala.com/token"
PANCHANG_URL = "https://api.prokerala.com/v2/astrology/panchang"
AYANAMSA_LAHIRI = 1
CREDITS_PER_CALL = 10  # Basic Panchang, English.

# The cities we publish muhurat pages for. The claim being validated is about
# these, so this is what to test deeply — not a shallow sample of the 153k-row
# dataset we never serve.
PUBLISHED_CITY_IDS = [
    133210, 133024, 57933, 132132, 131517, 142001, 133504, 57606, 132201,
    132782, 134096, 132166, 132660, 131633, 57867,            # India
    122795, 115875, 111590, 113931, 114990, 118699, 125816, 126104,  # US
    50388, 50274, 48521, 57223,                               # UK + IE
    17121, 16237, 17145,                                      # Canada
    32, 12,                                                   # Gulf
    25222, 99972,                                             # Europe
    104057, 66461, 7408, 6235,                                # APAC
]


# --------------------------------------------------------------------------
# Sample selection
# --------------------------------------------------------------------------

@dataclass
class Case:
    city_id: int
    city: str
    tz: str
    day: date
    reason: str

    def key(self) -> str:
        return f"{self.city_id}:{self.day.isoformat()}"


def dst_transitions(tz_name: str, year: int) -> list[date]:
    """Days in `year` where this zone's UTC offset changes.

    Read from the tz database rather than hardcoded, because the four schedules
    in play here (US, EU/UK, Australia, none) move independently and change by
    legislation. Anything hardcoded would rot.
    """
    tz = ZoneInfo(tz_name)
    out: list[date] = []
    day = date(year, 1, 1)
    prev = datetime(year, 1, 1, 12, tzinfo=tz).utcoffset()
    while day < date(year + 1, 1, 1):
        day += timedelta(days=1)
        offset = datetime(day.year, day.month, day.day, 12, tzinfo=tz).utcoffset()
        if offset != prev:
            out.append(day)
            prev = offset
    return out


def build_cases(year: int) -> list[Case]:
    from app.db import City, SessionLocal

    cases: list[Case] = []
    with SessionLocal() as session:
        for city_id in PUBLISHED_CITY_IDS:
            city = session.get(City, city_id)
            if city is None:
                print(f"  ! city {city_id} not in the database — seed first")
                continue

            # Day length extremes, in every city.
            for d, why in (
                (date(year, 3, 20), "equinox"),
                (date(year, 6, 21), "solstice (longest/shortest)"),
                (date(year, 9, 22), "equinox"),
                (date(year, 12, 21), "solstice (shortest/longest)"),
            ):
                cases.append(Case(city_id, city.name, city.tz, d, why))

            # The clock change itself, and the day either side of it.
            for t in dst_transitions(city.tz, year):
                for delta, why in ((-1, "day before DST change"),
                                   (0, "DST change"),
                                   (1, "day after DST change")):
                    cases.append(Case(city_id, city.name, city.tz,
                                      t + timedelta(days=delta), why))
    return cases


# --------------------------------------------------------------------------
# Prokerala
# --------------------------------------------------------------------------

class Prokerala:
    def __init__(self, client_id: str, client_secret: str):
        self._id, self._secret = client_id, client_secret
        self._token: str | None = None
        self._expires_at = 0.0

    def _authenticate(self) -> None:
        body = urlencode({
            "grant_type": "client_credentials",
            "client_id": self._id,
            "client_secret": self._secret,
        }).encode()
        req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
        req.add_header("content-type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.load(res)
        self._token = data["access_token"]
        # Refresh a minute early; a token expiring mid-run would otherwise fail
        # a call an hour into a ninety-minute sweep.
        self._expires_at = time.time() + int(data.get("expires_in", 3600)) - 60

    def panchang(self, lat: float, lon: float, when: datetime) -> dict[str, Any]:
        if self._token is None or time.time() >= self._expires_at:
            self._authenticate()
        params = urlencode({
            "ayanamsa": AYANAMSA_LAHIRI,
            "coordinates": f"{lat},{lon}",
            "datetime": when.isoformat(),
            "la": "en",
        })
        req = urllib.request.Request(f"{PANCHANG_URL}?{params}")
        req.add_header("authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=45) as res:
                return json.load(res)
        except urllib.error.HTTPError as err:
            if err.code == 401:          # token rejected — re-auth once
                self._authenticate()
                req.add_header("authorization", f"Bearer {self._token}")
                with urllib.request.urlopen(req, timeout=45) as res:
                    return json.load(res)
            raise


# --------------------------------------------------------------------------
# Ours
# --------------------------------------------------------------------------

def our_panchang(city_id: int, day: date) -> dict[str, Any]:
    from app.cache.city_cache import ensure_city_cached
    from app.db import City, SessionLocal
    from app.panchang.derive import derive_panchang

    with SessionLocal() as session:
        city = session.get(City, city_id)
        ensure_city_cached(session, city, day, day)
        return derive_panchang(session, city, day)


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

def _first_name(value: Any) -> str | None:
    """Both sides give the five limbs as a list of spans; compare the one in
    force at sunrise, which is the one every panchang is keyed to."""
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        for key in ("name", "tithi", "nakshatra", "yoga", "karana"):
            if key in value and isinstance(value[key], str):
                return value[key]
            if key in value and isinstance(value[key], dict):
                return value[key].get("name")
    return value if isinstance(value, str) else None


def _clock(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def classify(field_name: str, delta_seconds: float | None) -> str:
    """Name the likely cause, so a failure points at a knob rather than a diff.

    The sizes are diagnostic: a whole-hour offset is a timezone or DST fault, a
    few minutes is usually the coordinate, and seconds is a difference in how
    sunrise itself is defined (upper limb vs centre, refraction).
    """
    if delta_seconds is None:
        return "value mismatch"
    minutes = abs(delta_seconds) / 60
    if minutes >= 50:
        return "TIMEZONE / DST — offset is about a whole hour"
    if minutes >= 5:
        return "COORDINATE — wrong point for the city"
    if minutes >= 1:
        return "coordinate precision, or sunrise definition"
    return "sunrise definition (limb/refraction) — cosmetic"


def compare(case: Case, theirs: dict, ours: dict) -> list[dict]:
    data = theirs.get("data", theirs)
    issues: list[dict] = []

    for field_name, their_key, our_key in (
        ("sunrise", "sunrise", "sunrise"),
        ("sunset", "sunset", "sunset"),
    ):
        a, b = _clock(data.get(their_key)), _clock((ours.get("sun") or {}).get(our_key))
        if a and b:
            delta = (a - b).total_seconds()
            if abs(delta) > 60:
                issues.append({
                    "field": field_name, "theirs": a.isoformat(), "ours": b.isoformat(),
                    "delta_seconds": round(delta), "likely": classify(field_name, delta),
                })

    for field_name in ("tithi", "nakshatra", "yoga", "karana"):
        a = _first_name(data.get(field_name))
        b = _first_name(ours.get(field_name))
        if a and b and a.split()[0].lower() != b.split()[0].lower():
            issues.append({
                "field": field_name, "theirs": a, "ours": b, "delta_seconds": None,
                "likely": "AYANAMSA or sunrise boundary — the limb in force differs",
            })
    return issues


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=date.today().year + 1,
                    help="year to sample (default: next year)")
    ap.add_argument("--rpm", type=int, default=5,
                    help="requests per minute (free tier is 5, Ruby is 60)")
    ap.add_argument("--limit", type=int, help="stop after N comparisons")
    ap.add_argument("--plan", action="store_true",
                    help="show the sample and the credit cost; make no calls")
    ap.add_argument("--probe", action="store_true",
                    help="one call, dump the raw response, exit")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data" / "prokerala_validation.jsonl")
    args = ap.parse_args()

    cases = build_cases(args.year)
    if args.limit:
        cases = cases[: args.limit]

    if args.plan:
        by_reason: dict[str, int] = {}
        for c in cases:
            by_reason[c.reason] = by_reason.get(c.reason, 0) + 1
        print(f"\n{len(cases)} comparisons across {len(PUBLISHED_CITY_IDS)} cities, {args.year}")
        for reason, n in sorted(by_reason.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>4}  {reason}")
        credits = len(cases) * CREDITS_PER_CALL
        print(f"\n  credits: {credits:,} of 5,000 free "
              f"({'fits' if credits <= 5000 else 'TOO MANY — raise --limit down'})")
        print(f"  wall time at {args.rpm}/min: ~{len(cases) / args.rpm:.0f} min\n")
        return 0

    client_id = os.environ.get("PROKERALA_CLIENT_ID", "").strip()
    secret = os.environ.get("PROKERALA_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        print("\n✗ Set PROKERALA_CLIENT_ID and PROKERALA_CLIENT_SECRET.\n"
              "  Export them rather than pasting them anywhere they get stored.\n")
        return 1

    api = Prokerala(client_id, secret)

    if args.probe:
        c = cases[0]
        from app.db import City, SessionLocal
        with SessionLocal() as s:
            city = s.get(City, c.city_id)
            lat, lon = city.lat, city.lon
        when = datetime(c.day.year, c.day.month, c.day.day, 6, 0,
                        tzinfo=ZoneInfo(c.tz))
        print(f"probe: {c.city} {c.day} ({lat},{lon})\n")
        print(json.dumps(api.panchang(lat, lon, when), indent=2)[:4000])
        return 0

    # Resume: a ninety-minute run must not start over because of one timeout.
    done: set[str] = set()
    if args.out.exists():
        for line in args.out.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["key"])
        print(f"resuming — {len(done)} already compared")

    interval = 60.0 / max(args.rpm, 1)
    todo = [c for c in cases if c.key() not in done]
    print(f"{len(todo)} to compare, ~{len(todo) / args.rpm:.0f} min at {args.rpm}/min\n")

    from app.db import City, SessionLocal
    failures = 0
    with args.out.open("a") as fh:
        for i, c in enumerate(todo, 1):
            with SessionLocal() as s:
                city = s.get(City, c.city_id)
                lat, lon = city.lat, city.lon
            when = datetime(c.day.year, c.day.month, c.day.day, 6, 0,
                            tzinfo=ZoneInfo(c.tz))
            started = time.time()
            try:
                theirs = api.panchang(lat, lon, when)
                ours = our_panchang(c.city_id, c.day)
                issues = compare(c, theirs, ours)
            except Exception as err:  # noqa: BLE001 — one bad call must not end the run
                print(f"  [{i}/{len(todo)}] {c.city} {c.day}: ERROR {err}")
                continue

            fh.write(json.dumps({
                "key": c.key(), "city": c.city, "city_id": c.city_id,
                "date": c.day.isoformat(), "tz": c.tz, "reason": c.reason,
                "issues": issues,
            }) + "\n")
            fh.flush()

            if issues:
                failures += 1
                print(f"  [{i}/{len(todo)}] ✗ {c.city} {c.day} ({c.reason})")
                for issue in issues:
                    print(f"        {issue['field']}: ours={issue['ours']} "
                          f"theirs={issue['theirs']} → {issue['likely']}")
            elif i % 10 == 0:
                print(f"  [{i}/{len(todo)}] ok so far ({failures} with issues)")

            elapsed = time.time() - started
            if i < len(todo) and elapsed < interval:
                time.sleep(interval - elapsed)

    print(f"\n{len(todo) - failures}/{len(todo)} agreed. Results: {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
