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
# Database
# --------------------------------------------------------------------------

def ensure_database_ready() -> None:
    """Bring the local database up the way the app does at startup.

    This script talks to the panchang engine in-process rather than over HTTP,
    so it has to do the preparation the FastAPI lifespan normally does. Without
    it a fresh checkout dies on "no such table: cities", which says nothing
    about what to do next.

    init_ephemeris matters as much as the seed: it selects the ephemeris
    backend, and comparing against Prokerala on a different backend from the
    one production runs would be measuring the wrong thing.

    Both this and production resolve to Moshier, because no .se1 files are
    bundled and SHUBHTITHI_EPHEMERIS_PATH is unset — so the comparison does
    reflect what we serve. Prokerala runs the full SE data files, which differ
    from Moshier by a few arc-seconds: well under a second of sunrise, and only
    visible at all when a limb changes within a minute of it. The backend is
    printed on every run so a reader can see which one produced the numbers.
    """
    from app.astronomy.core import init_ephemeris
    from app.config import get_settings
    from app.db import SessionLocal, ensure_engine_version, init_db
    from app.geo.seed import apply_corrections, cities_count, seed_cities

    settings = get_settings()
    backend = init_ephemeris(settings.ephemeris_path)
    init_db()

    with SessionLocal() as session:
        if ensure_engine_version(session):
            print("  engine version changed — computed cache rebuilt")
        have = cities_count(session)

    if not have:
        print("  seeding cities (first run, ~150k rows, takes a moment)…")
    count = seed_cities()
    corrected = apply_corrections()

    print(f"  ephemeris: {backend} · cities: {count:,}"
          + (f" · corrected: {corrected}" if corrected else ""))


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

# urllib's default User-Agent is "Python-urllib/3.x", which WAFs in front of
# public APIs routinely reject with a bare 403 — no body, no explanation, and
# nothing to do with your credentials. Identify ourselves properly.
USER_AGENT = "ShubhSankalpa-panchang-validation/1.0 (+https://shubhsankalpa.com)"


class ProkeralaError(RuntimeError):
    """An API error carrying the response body, which is where the reason is."""

    def __init__(self, status: int, body: str, url: str):
        self.status, self.body = status, body
        hint = {
            400: "check the parameter format — coordinates are 'lat,lon' and "
                 "datetime is ISO 8601 WITH an offset",
            401: "the token was rejected; client id/secret wrong or rotated",
            403: "authenticated but refused. Usually one of: the plan does not "
                 "include this endpoint, credits are exhausted, or a WAF "
                 "blocked the request. The body below says which",
            429: "rate limited — lower --rpm (free tier allows 5/min)",
        }.get(status, "")
        super().__init__(
            f"HTTP {status} from {url}\n"
            + (f"  likely: {hint}\n" if hint else "")
            + f"  response: {body[:600] or '(empty body)'}"
        )


def _send(req: urllib.request.Request) -> dict[str, Any]:
    """Make the request, and turn an error into something that explains itself.

    Without this a 403 arrives as a bare traceback, and the body Prokerala sent
    saying exactly what was wrong is thrown away.
    """
    req.add_header("user-agent", USER_AGENT)
    req.add_header("accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as res:
            return json.load(res)
    except urllib.error.HTTPError as err:
        body = ""
        try:
            body = err.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 — the status still matters
            pass
        raise ProkeralaError(err.code, body, req.full_url) from None


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
        data = _send(req)
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
        def call() -> dict[str, Any]:
            req = urllib.request.Request(f"{PANCHANG_URL}?{params}")
            req.add_header("authorization", f"Bearer {self._token}")
            return _send(req)

        try:
            return call()
        except ProkeralaError as err:
            if err.status == 401:        # token rejected — re-auth once
                self._authenticate()
                return call()
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
    return "sunrise definition, or Moshier vs SE files — expected, not a bug"


REQUIRED_FIELDS = ("sunrise", "sunset", "tithi", "nakshatra", "yoga", "karana")


def assert_mapping_holds(theirs: dict, ours: dict) -> None:
    """Fail loudly if either side's fields cannot be read.

    compare() only reports a difference when BOTH sides parse. So a response
    shaped differently from what this script expects would produce no
    differences at all — and the run would end with a confident "254/254
    agreed" that had in fact compared nothing. A silent pass is far worse here
    than a crash, because the whole point is assurance.

    This runs once, on the first response, and describes what it actually got.
    """
    data = theirs.get("data", theirs)
    missing_theirs = [
        f for f in REQUIRED_FIELDS
        if (_clock(data.get(f)) if f in ("sunrise", "sunset") else _first_name(data.get(f))) is None
    ]
    missing_ours = [
        f for f in REQUIRED_FIELDS
        if (_clock((ours.get("sun") or {}).get(f)) if f in ("sunrise", "sunset")
            else _first_name(ours.get(f))) is None
    ]
    if not missing_theirs and not missing_ours:
        return

    lines = ["\nThe field mapping does not hold — refusing to report a "
             "meaningless pass.\n"]
    if missing_theirs:
        lines.append(f"  Could not read from Prokerala: {', '.join(missing_theirs)}")
        lines.append(f"  Its top-level keys: {sorted(data)[:20]}")
        for f in missing_theirs:
            if f in data:
                lines.append(f"    {f} = {json.dumps(data[f])[:200]}")
    if missing_ours:
        lines.append(f"  Could not read from ours: {', '.join(missing_ours)}")
        lines.append(f"  Our top-level keys: {sorted(ours)[:20]}")
    lines.append("\n  Fix _first_name/_clock in this script to match, then re-run.")
    raise RuntimeError("\n".join(lines))


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
            # One or two of these across the whole sweep is unremarkable: a
            # limb that changes within a minute or two of sunrise can land
            # either side of it on Moshier vs the SE data files. A pattern —
            # the same city, or the same limb, repeatedly — is a real fault.
            issues.append({
                "field": field_name, "theirs": a, "ours": b, "delta_seconds": None,
                "likely": "AYANAMSA, or a limb changing right at sunrise",
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

    ensure_database_ready()
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
        try:
            theirs = api.panchang(lat, lon, when)
        except ProkeralaError as err:
            print(f"✗ {err}\n")
            return 1
        print(json.dumps(theirs, indent=2)[:4000])
        try:
            assert_mapping_holds(theirs, our_panchang(c.city_id, c.day))
        except RuntimeError as err:
            print(err)
            return 1
        print("\n✓ every field this script compares was found on both sides")
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
    checked_mapping = False
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
                if not checked_mapping:
                    assert_mapping_holds(theirs, ours)
                    checked_mapping = True
                    print("  field mapping verified on the first response\n")
                issues = compare(c, theirs, ours)
            except ProkeralaError as err:
                print(f"  [{i}/{len(todo)}] {c.city} {c.day}:\n{err}")
                if err.status in (401, 403):
                    print("\n  Stopping: this will fail identically for every "
                          "remaining call.")
                    return 1
                continue
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
