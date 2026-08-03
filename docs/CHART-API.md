# API Semantics — `GET /v1/chart`

Natal chart (kundali) for an exact birth instant. Companion to
[`API-SEMANTICS.md`](API-SEMANTICS.md), which documents `/v1/nakshatra-at`;
the conventions established there (sidereal Lahiri, `{number, name}` objects,
IANA-only timezones, JSON error envelopes, flag-your-assumptions) all hold here
and are not repeated.

Written for the Navodayam / RR Matrimony integration. Every value below was
produced by executing the code, not by reading intent.

**Status: implemented, tested, and committed — NOT yet deployed.** See
[§7](#7-deployment-status) before wiring the adapter.

---

## 0. Answers to the five questions asked

| # | Question | Answer |
|---|---|---|
| 1 | Worked example | [`docs/examples/chart-1984-04-24.json`](examples/chart-1984-04-24.json) — the full body for your fixture birth, committed to the repo. Abridged inline in [§2](#2-worked-example). |
| 2 | What is NOT implemented | [§6](#6-what-is-not-implemented). Navamsa **is** implemented; dashas **are** implemented (maha + antar). The real gaps are elsewhere. |
| 3 | House system / nodes / manglik houses | **Whole sign**; **mean** node; manglik on **1, 2, 4, 7, 8, 12** from the lagna, with the strict 5-house reading also returned. [§3](#3-conventions) |
| 4 | Response time | **~1.8 ms** warm vs 0.018 ms for `/v1/nakshatra-at`. ~100× the moon endpoint, still ~2700× inside your 5 s cap. [§5](#5-performance) |
| 5 | API key / custom domain | Still unimplemented and unconfigured respectively — unchanged from `API-SEMANTICS.md` §4a/§4c. [§8](#8-auth-and-hosting-unchanged) |

**`planets[].house` — the field you said you cannot degrade on — is always
present, always an integer 1–12, for all nine grahas, on every successful
response.** It is asserted in the test suite for the reference birth, a
southern-hemisphere birth, and a 69°N birth.

---

## 1. Request

```
GET /v1/chart?date=1984-04-24&time=21:06:00&tz=Asia/Kolkata&lat=17.0&lon=82.2
```

| Param | Required | Type | Notes |
|---|---|---|---|
| `date` | **yes** | `date` | `YYYY-MM-DD`, local civil date in `tz`. A datetime is rejected 422, as on `/v1/nakshatra-at`. |
| `time` | **yes** | `time` | `HH:MM` or `HH:MM:SS`, local civil time in `tz`. **Required — see below.** |
| `lat` | **yes** | `float` | Signed decimal degrees, north positive, `[-90, 90]`. |
| `lon` | **yes** | `float` | Signed decimal degrees, east positive, `[-180, 180]`. |
| `tz` | no | `string` | IANA name only. Derived from `lat`/`lon` if omitted. |
| `dasha_span_years` | no | `float` | Default `120`, range `[1, 120]`. How far past birth the Vimshottari tree must reach. |
| `include_antardashas` | no | `bool` | Default `true`. `false` drops all `children` and cuts the body from ~18.7 KB to ~7.9 KB. |

### `time` is required — the endpoint refuses rather than assuming

You suggested this and the argument is right, so it is implemented that way:
omitting `time` returns **422 `validation_error`**, not a sunrise-defaulted
chart. `/v1/nakshatra-at` keeps its sunrise fallback because a moon position
with an assumed time is a *degraded* answer; an ascendant with an assumed time
is a *wrong* one, and all twelve houses inherit the error.

There is consequently **no `time_assumed` field on this endpoint** — it can
never apply.

### A new failure mode worth knowing

`lat`/`lon` are validated for range but never for consistency with `tz`. Since
`tz` alone fixes the instant and `lat`/`lon` alone fix the ascendant, a
**mismatched pair produces a confidently wrong chart, not an error** — and
unlike `/v1/nakshatra-at`, where coordinates only affected the sunrise
fallback, here they move the ascendant and therefore every house assignment. A
sign error on `lon` is the classic case. Validate upstream.

---

## 2. Worked example

Full body: [`docs/examples/chart-1984-04-24.json`](examples/chart-1984-04-24.json)
(18,707 bytes). Pin your fixture against that file — but read
[§4.3](#43-one-field-is-time-dependent) first, because one subtree changes with
the calendar.

```jsonc
{
  "instant": "1984-04-24T21:06:00+05:30",
  "coordinates": { "lat": 17.0, "lon": 82.2, "timezone": "Asia/Kolkata" },
  "ayanamsa": "lahiri",
  "house_system": "whole_sign",
  "node_type": "mean",

  "ascendant": {
    "longitude_sidereal": 229.589834,
    "rashi":     { "number": 8,  "name": "Vrishchika" },
    "nakshatra": { "number": 18, "name": "Jyeshtha", "pada": 1 },
    "degree": 19.589834
  },

  "planets": [
    {
      "name": "Sun",
      "longitude_sidereal": 10.995954,
      "rashi":     { "number": 1, "name": "Mesha" },
      "nakshatra": { "number": 1, "name": "Ashwini", "pada": 4 },
      "degree": 10.995954,
      "house": 6,
      "retrograde": false,
      "speed_deg_per_day": 0.973765
    },
    {
      "name": "Mars",
      "longitude_sidereal": 212.42642,
      "rashi":     { "number": 8,  "name": "Vrishchika" },
      "nakshatra": { "number": 16, "name": "Vishakha", "pada": 4 },
      "degree": 2.42642,
      "house": 1,                       // ← in the lagna: manglik
      "retrograde": true,
      "speed_deg_per_day": -0.237471
    }
    // … 9 total, in the order you specified
  ],

  "houses": [
    { "house": 1, "rashi": { "number": 8, "name": "Vrishchika" } },
    { "house": 2, "rashi": { "number": 9, "name": "Dhanu" } }
    // … 12 total
  ],

  "navamsa": {
    "ascendant": { "longitude_sidereal": 266.308506,
                   "rashi": { "number": 9, "name": "Dhanu" } },
    "planets": [
      { "name": "Sun", "longitude_sidereal": 98.963586,
        "rashi": { "number": 4, "name": "Karka" },
        "degree": 8.963586, "house": 8, "retrograde": false }
      // … 9 total
    ],
    "houses": [ { "house": 1, "rashi": { "number": 9, "name": "Dhanu" } } /* … 12 */ ]
  },

  "dashas": {
    "vimshottari": [
      {
        "level": "maha",
        "lord": "Mars",
        "start": "1984-04-24T21:06:00+05:30",
        "end":   "1988-04-30T16:40:27.207660+05:30",
        "children": [
          { "level": "antar", "lord": "Saturn",
            "start": "1984-04-24T21:06:00+05:30",
            "end":   "1984-10-30T07:40:27.207660+05:30" }
          // … 6 for this truncated first mahadasha, 9 for every later one
        ]
      }
      // … 10 mahadashas, 1984-04-24 → 2108-05-01
    ],
    "balance_at_birth": {
      "lord": "Mars", "years": 4, "months": 0, "days": 5, "total_years": 4.015922
    },
    "system": { "name": "vimshottari", "cycle_years": 120.0,
                "year_days": 365.25, "levels": ["maha", "antar"] }
  },

  "doshas": {
    "manglik": {
      "value": true,
      "reference": "lagna",
      "reference_houses": [1, 2, 4, 7, 8, 12],
      "mars_house_from_lagna": 1,
      "mars_house_from_moon": 11,
      "from_lagna": true,
      "from_moon": false,
      "from_lagna_strict": true,
      "second_house_counted": true,
      "note": "…"
    },
    "kaal_sarp": { "value": false, "side": null, "note": "…" },
    "sade_sati": {
      "value": false, "phase": null,
      "saturn_transit_rashi": 12, "natal_moon_rashi": 10,
      "saturn_house_from_moon": 3,
      "evaluated_at": "2026-08-03T02:45:46.786811+00:00",
      "note": "Time-dependent: … Exclude from fixture comparisons."
    }
  }
}
```

The mahadasha sequence for this birth, for eyeballing against another source:

| Lord | Start | End |
|---|---|---|
| Mars | 1984-04-24 | 1988-04-30 |
| Rahu | 1988-04-30 | 2006-05-01 |
| Jupiter | 2006-05-01 | 2022-05-01 |
| **Saturn** | **2022-05-01** | **2041-04-30** |
| Mercury | 2041-04-30 | 2058-05-01 |
| Ketu | 2058-05-01 | 2065-04-30 |
| Venus | 2065-04-30 | 2085-04-30 |
| Sun | 2085-04-30 | 2091-05-01 |
| Moon | 2091-05-01 | 2101-05-01 |
| Mars | 2101-05-01 | 2108-05-01 |

---

## 3. Conventions

### 3.1 House system: **whole sign**

`"house_system": "whole_sign"` is emitted on every response. House 1 is the
entire rashi the ascendant occupies; house 2 the next rashi; and so on. No cusp
interpolation, no Placidus, no Sripati. This is what your North Indian square
diagram assumes.

The consequence you can rely on:

```
planets[i].house == ((planets[i].rashi.number - ascendant.rashi.number) mod 12) + 1
```

This is asserted in the test suite and holds for the D9 block too (against the
navamsa ascendant). It means `houses[]` and every `house` field are strictly
derivable from `ascendant.rashi.number` — they are convenience, exactly as you
guessed. `houses[]` is included anyway since it costs ~200 bytes.

The ascendant itself comes from Swiss Ephemeris `houses_ex(..., b'W',
FLG_SIDEREAL)`, so the ayanamsa is applied inside the house calculation rather
than subtracted afterwards.

### 3.2 Nodes: **mean**

`"node_type": "mean"` is emitted on every response. Rahu is `swe.MEAN_NODE`;
**Ketu is not calculated at all** — it is exactly `Rahu + 180°`, so
`(Ketu.longitude − Rahu.longitude) mod 360 == 180.0` holds to the emitted
precision, and their houses are always 6 apart. Mean node is the classical
Vedic convention.

For reference, true node differs from mean by ~1.35° at this birth instant
(43.47° vs 44.82°) — enough to change a nakshatra, not usually a rashi.

### 3.3 Retrograde: literal, with a deliberate exception

`retrograde` is `speed_deg_per_day < 0`, **except** for Sun, Moon, Rahu and
Ketu, which are hard-coded `false` per your spec.

Flagging this because it is a deliberate deviation from fact, not an oversight:
**the mean node's motion is genuinely negative** (−0.053°/day here), and many
providers therefore report Rahu/Ketu as permanently retrograde. You asked for
`false`; that is what you get. `speed_deg_per_day` is emitted alongside so you
can see the real sign and override if you ever want the conventional reading.

For the reference birth, Mars, Mercury and Saturn are retrograde; Jupiter and
Venus are direct. (Pinned in the tests.)

### 3.4 Manglik: houses **1, 2, 4, 7, 8, 12** from the lagna

`doshas.manglik.value` counts Mars in houses **1, 2, 4, 7, 8, 12** measured
from the **ascendant**. The houses used are echoed in `reference_houses` so you
never have to infer them.

You flagged the 2nd house as disputed, and it is: North Indian practice
generally counts it, much South Indian practice does not. Rather than pick
silently, the block returns both:

| Field | Meaning |
|---|---|
| `value` | The headline verdict. Equals `from_lagna`. |
| `from_lagna` | Mars in 1/2/4/7/8/12 from the lagna. |
| `from_lagna_strict` | Mars in **1/4/7/8/12** — the 2nd house excluded. |
| `from_moon` | Same six houses, counted from the natal moon instead. |
| `mars_house_from_lagna` | The raw house number, 1–12. |
| `mars_house_from_moon` | The raw house number from the moon. |
| `second_house_counted` | `true`, stating which convention `value` used. |

If RR Matrimony wants the strict reading, read `from_lagna_strict` and ignore
`value` — no API change needed.

### 3.5 Navamsa: the ×9 rule

D9 longitude is `(sidereal_longitude × 9) mod 360`, which is exactly equivalent
to the classical rule (movable signs count from themselves, fixed from the 9th,
dual from the 5th). Navamsa houses are whole-sign from the navamsa ascendant.

`navamsa.planets[]` carries `name`, `longitude_sidereal`, `rashi`, `degree`,
`house` and `retrograde` — a superset of the `name` + `rashi` + `house` you
asked for. No `nakshatra` in the D9 block (it is not meaningful there).

### 3.6 Vimshottari: 365.25-day year

Lord order Ketu→Venus→Sun→Moon→Mars→Rahu→Jupiter→Saturn→Mercury, 120 years
total, keyed to the moon's nakshatra (`ORDER[nakshatra_index % 9]`). The first
mahadasha is truncated to the unelapsed balance; `balance_at_birth` reports it
in years/months/days plus exact `total_years`.

**Year length is the 365.25-day Julian year.** Some traditions use a 360-day
savana year, which drifts ~1.5% — about 22 months across the full cycle. That
variant is **not implemented**; `dashas.system.year_days` states which is in
use so a mismatch with another provider is diagnosable rather than mysterious.

Guarantees, all asserted in tests:

- Mahadashas are **contiguous**: `periods[i].end == periods[i+1].start`, exactly.
- Antardashas **tile their parent**: `children[0].start == maha.start` and
  `children[-1].end == maha.end`, exactly. (The last antardasha is snapped to
  the parent's end; accumulating nine proportional slices otherwise drifts by a
  microsecond.)
- The tree **covers the present** — exactly one mahadasha contains `now()`, and
  it carries antardashas.
- The first mahadasha starts **exactly at** `instant`.

Only **maha** and **antar** levels are produced. Pratyantar, sookshma and prana
are **not implemented**.

### 3.7 Dasha timestamps share one UTC offset

You asked for ISO strings comparable as strings. Every dasha timestamp is
rendered at **the birth timezone's offset at the birth instant, held fixed for
the whole tree** — `+05:30` throughout for the reference birth. That guarantees
lexicographic ordering matches chronological ordering.

The trade-off, stated plainly: for a birth in a DST zone, a dasha boundary
falling in summer shows the *winter* offset. The **instant is still correct**;
only the wall-clock rendering is not what a local calendar would print. Since
dasha boundaries are computed instants rather than civil appointments, this is
the better trade — but if you render these to end users in a DST zone, convert
before display. Asserted in tests (`all(s.endswith("+05:30"))` plus a sort
check).

Timestamps carry microseconds. They are ISO-8601 and
`datetime.fromisoformat`-parseable.

---

## 4. Cross-checks and gotchas

### 4.1 The identities extend to all nine grahas

As requested, `longitude_sidereal` is emitted alongside `rashi` and `nakshatra`
for every planet **and** the ascendant, so your existing assertion generalises:

```
rashi.number     == floor(longitude_sidereal / 30) + 1
nakshatra.number == floor(longitude_sidereal / (360/27)) + 1
```

These hold **exactly on the serialised numbers**. Indices are derived from the
*rounded* 6-dp longitude rather than the full-precision value specifically so
this can never fail spuriously for a planet sitting within 5×10⁻⁷ of a boundary.
Both identities are asserted for all ten subjects in the test suite.

`degree` is `longitude_sidereal mod 30`.

### 4.2 A chart and `/v1/nakshatra-at` agree on the moon exactly

Same instant, same sidereal source. Verified byte-for-byte in the tests:
`longitude_sidereal`, `nakshatra` (including `pada`), `rashi` and `instant` are
all identical between the two endpoints for the same query. Use this as an
integration canary.

### 4.3 One field is time-dependent

**`doshas.sade_sati` is evaluated against Saturn's position right now**, not at
birth — it is a transit test, as you specified. The same birth details return a
different answer on a different day.

For your fixture test, **exclude `doshas.sade_sati` from the comparison.**
Everything else in the response is a pure function of the request. The block
carries `evaluated_at` and a `note` saying so, so the trap is visible in the
payload rather than only in this document.

### 4.4 Error envelopes

All errors are `{"error": {"code", "message", "detail"}}`.

| Code | Status | Cause |
|---|---|---|
| `validation_error` | 422 | Missing/malformed param — including a missing `time`, a datetime in `date`, out-of-range `lat`/`lon`, `dasha_span_years` outside `[1,120]`. |
| `invalid_timezone` | 422 | `tz` is not an IANA name. **New — see §9.** |
| `ephemeris_range` | 422 | `date` outside the ephemeris range. **New — see §9.** |
| `tz_unresolved` | 422 | Coordinates yielded no zone and `tz` was omitted. Rare. |
| `ascendant_undefined` | 422 | Reserved; not currently reachable (see §6). |
| `ephemeris_error` | 500 | Any other Swiss Ephemeris failure. JSON, not text. |

---

## 5. Performance

Measured on the dev machine with the Moshier backend, warm process, excluding
network:

| Call | Warm | Notes |
|---|---|---|
| `/v1/nakshatra-at` | **0.018 ms** | baseline |
| `/v1/chart`, full (120 y + antardashas) | **1.81 ms** | ~100× the moon endpoint |
| `/v1/chart`, `include_antardashas=false` | **0.55 ms** | |
| `/v1/chart`, `dasha_span_years=100` | **1.22 ms** | |
| `/v1/chart`, first call in a thread | **4.1 ms** | one-off per-thread ephemeris init |

Response size: **18.7 KB** full, **7.9 KB** without antardashas.

**Set your timeout from the network, not from the computation.** 1.8 ms is
~2700× inside your 5 s synchronous cap and ~5500× inside the 10 s Celery
budget. The chart does 11 Swiss Ephemeris calls (9 grahas − Ketu, the
ascendant, and one extra for Saturn's *current* position for sade sati) versus
one for the moon endpoint; that ratio, not the dasha tree, is most of the
difference.

Like `/v1/nakshatra-at`, `/v1/chart` **touches no database** — no session
dependency, no cache. It is pure computation, stateless, idempotent, and safe
to retry. The cold-start caveats from `API-SEMANTICS.md` §4b still apply to the
*process* (city seeding on boot; a ~1.5 s timezonefinder polygon load on the
first request that omits `tz`), so pass `tz` explicitly.

---

## 6. What is NOT implemented

Named so you can degrade deliberately rather than discover it on a customer's
PDF.

### Implemented, contrary to your expectation
Both of the things you flagged as most likely to be deferred are **present**:
**navamsa** (D9, full block with houses) and the **Vimshottari tree** (maha +
antar, full 120-year cycle). No placeholder needed for either.

### Not implemented

| Area | Status |
|---|---|
| **Divisional charts other than D9** | Only D1 and D9. No D2, D3, D7, D10, D12, D16, D20, D24, D27, D30, D40, D45, D60. |
| **Dasha levels below antar** | No pratyantar, sookshma or prana. |
| **Dasha systems other than Vimshottari** | No Ashtottari, Yogini, Kalachakra, Chara. |
| **360-day savana dasha year** | Only the 365.25-day year. |
| **House systems other than whole sign** | No Placidus, Sripati, Koch, Equal, Bhava Chalit. No house *cusp* longitudes are emitted at all. |
| **Doshas beyond the three** | Only manglik, kaal sarp, sade sati. No pitra, nadi, guru chandal, kemadruma, grahan. |
| **Aspects (drishti)** | Not computed. |
| **Strength / dignity** | No shadbala, ashtakavarga, vimshopaka, exaltation-debilitation flags, combustion, planetary war, karakas, avastha. |
| **Panchang in the chart body** | No tithi/yoga/karana/vara. Use `/v1/panchang` for the same instant. |
| **Ayanamsa selection** | Still Lahiri only, still not configurable. |
| **Swiss Ephemeris data files** | Still Moshier in the deployed image — `.dockerignore` still excludes `data/ephe/`. See `API-SEMANTICS.md` §1c. |
| **OpenAPI response schema** | No `response_model`, same as `/v1/nakshatra-at`. The OpenAPI document describes the *parameters* but types the response as a free-form object. §2 and the committed fixture are the contract. |
| **PDF rendering** | Out of scope; the API returns data only. |
| **Auth / rate limiting / CORS** | Still none. §8. |

### Known behaviours that are not errors

- **Exact poles return a chart.** At `lat = ±90` the ascendant is degenerate,
  but Swiss Ephemeris returns a value rather than failing, so you get a 200 with
  an astronomically meaningless ascendant and houses — and `lat=90` and
  `lat=-90` return the *same* ascendant, which is the tell. The
  `ascendant_undefined` 422 exists but is not currently reachable. Real birth
  coordinates are never exactly ±90, so this is a curiosity, not a risk. High
  latitudes short of the poles (tested at 69.65°N) are ordinary and correct —
  unlike `/v1/nakshatra-at`, this endpoint has no sunrise dependency, so
  `API-SEMANTICS.md` §5.2 does **not** apply here.
- **Supported date range** is the Moshier backend's: JD 625000.5–2818000.5,
  roughly **3001 BCE to 3000 CE**. Outside it you now get a clean
  422 `ephemeris_range`. Births from year 1 CE onward work (the dasha wind-back
  no longer underflows `datetime.min`); the forward dasha tree stops cleanly
  rather than overflowing for births after ~year 9879.
- **Historical timezones** behave exactly as documented in `API-SEMANTICS.md`
  §5.4 — 1980s DST is applied correctly (verified: 1985-07-04 New York →
  `-04:00`), and pre-1906 Indian dates get LMT offsets with a seconds component.

---

## 7. Deployment status

**The endpoint is implemented, tested and committed. It is not deployed.**

I did not push to `origin` or trigger a Railway build — that is a production
deploy of a live service, and it is your call, not mine. The work sits on the
`dev` branch.

What is done:

- `app/jyotish/` (new package: `chart.py`, `dasha.py`, `doshas.py`)
- `app/routers/chart.py`, wired into `app/main.py` and listed at `/`
- `app/astronomy/core.py`: `GRAHA_BODIES`, `longitude_and_speed()`, `ascendant()`
- `app/api.py`: `resolve_zone()` + a Swiss Ephemeris exception handler
- `tests/test_chart.py`: 39 tests
- `docs/examples/chart-1984-04-24.json`: your fixture
- This document

Test suite: **77 passed, 4 skipped** (the 4 skips are the pre-existing
`test_golden.py` TODO fixtures, untouched). No regressions.

To ship: merge `dev` and push; Railway builds from the Dockerfile and
healthchecks `/v1/health`.

---

## 8. Auth and hosting (unchanged)

Nothing has changed here, and nothing in this work changed it:

- **No API key mechanism.** Your `X-API-Key` is still accepted and ignored, as
  is any header. Since your plumbing is done and unused, turning this on
  server-side later needs no change from you — but it is unbuilt today, not a
  flag to flip. Adding it would be a small, self-contained middleware.
- **No rate limiting**, no CORS. Keep calls server-side.
- **No custom domain** configured, and still nothing in the repository
  indicating a planned one. The Railway subdomain is the only address.

---

## 9. Changes to existing behaviour

Two fixes land alongside the new endpoint. Both turn a bare `text/plain` 500
into a structured 422 — **your contract tests may pin the old status codes.**

### 9.1 Invalid `tz` → 422 `invalid_timezone` (was 500)

You asked for this. It applies to **`/v1/nakshatra-at` as well as `/v1/chart`**:

```json
{"error": {"code": "invalid_timezone",
           "message": "Unknown IANA timezone: '+05:30'.",
           "detail": "Expected an IANA timezone name such as 'Asia/Kolkata'. UTC offsets ('+05:30') and abbreviations ('IST') are not accepted. (ZoneInfoNotFoundError)"}}
```

Covers `+05:30`, `IST`, `Not/AZone` and any other non-IANA value.
`API-SEMANTICS.md` §3a and §5.1 are superseded by this.

### 9.2 Out-of-range `date` → 422 `ephemeris_range` (was 500)

Not requested, but the same defect class you flagged, and two lines once the
handler existed. `/v1/nakshatra-at` with `date=3500-04-24` now returns:

```json
{"error": {"code": "ephemeris_range",
           "message": "Date is outside the supported ephemeris range.",
           "detail": "swisseph.calc_ut: jd … outside Moshier planet range 625000.50 .. 2818000.50"}}
```

`API-SEMANTICS.md` §5.3 is superseded.

If you would rather these stayed 500s until you can update your fixtures, both
are single-commit reverts — say so and I will split them out.
