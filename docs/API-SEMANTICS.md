# API Semantics — `GET /v1/nakshatra-at`

Reference for consumers integrating ShubhTithi. This document covers the
**semantics** the OpenAPI schema cannot express: what the numbers mean, which
astronomical conventions produce them, and where the behaviour will surprise
you.

Everything below was verified against the code at commit `ed7ed22` by executing
it, not by reading intent. Where something is **not implemented**, it says so.

> **Changed in `ed7ed22`** (see [§8](#8-changelog)): invalid `tz` and
> out-of-range `date` now return a **JSON 422** instead of a plain-text 500.
> §3a, §5.1 and §5.3 have been rewritten accordingly — if you are re-reading
> this document against notes from an earlier revision, those are the three
> sections that moved.
>
> **See also:** [`CHART-API.md`](CHART-API.md) documents `GET /v1/chart` (natal
> chart: ascendant, nine grahas with whole-sign houses, D9, Vimshottari dasha,
> manglik / kaal sarp / sade sati).

- Audience: backend integrators (written for the RR Matrimony Ashtakoota use case).
- Service version: `0.1.0` · Python ≥ 3.12 · FastAPI · AGPL-3.0-or-later.
- Source of truth: [`app/panchang/instant.py`](../app/panchang/instant.py),
  [`app/astronomy/core.py`](../app/astronomy/core.py),
  [`app/panchang/elements.py`](../app/panchang/elements.py),
  [`app/panchang/names.py`](../app/panchang/names.py),
  [`app/routers/nakshatra.py`](../app/routers/nakshatra.py),
  [`app/api.py`](../app/api.py) (error envelopes and timezone validation).

---

## 0. Executive summary for Guna Milan

| Question | Answer |
|---|---|
| Sidereal or tropical? | **Sidereal** |
| Which ayanamsa? | **Lahiri** (`swe.SIDM_LAHIRI`). Not configurable. |
| Is `moon_rashi` the moon sign or lagna? | **Moon sign (chandra rashi).** Lagna is not computed anywhere in this service. |
| Is `pada` returned? | **Yes**, always, `1..4`. |
| Numeric index available? | **Yes** — every element returns both `number` (1-based) and `name`. |
| Ephemeris | Swiss Ephemeris via `pyswisseph` 2.10.03, running the **Moshier** built-in model in the deployed image. |
| Auth | **None implemented.** `X-API-Key` is accepted-and-ignored (as is any header). |
| Rate limits | **None implemented** in the application. |
| Is there a birth chart? | **Yes**, `GET /v1/chart` — see [`CHART-API.md`](CHART-API.md). Not part of this endpoint. |

**The three things most likely to bite you** — details in §5:

1. If you omit `time`, the instant used is **local sunrise**, not midnight or noon.
2. At high latitudes where the sun does not rise, the sunrise fallback silently
   uses **local midnight** while still reporting `"time_assumed": "sunrise"`.
3. `tz` accepts an **IANA name only** — no UTC offsets, no abbreviations. This
   is now a clean 422 rather than the 500 it used to be, but it is still a
   rejection.

---

## 1. Astronomical basis

### 1a. Zodiac and ayanamsa — sidereal, Lahiri, not configurable

All longitudes are **sidereal**, using the **Lahiri** ayanamsa
(`swe.SIDM_LAHIRI`, set with `t0=0, ayan_t0=0`, i.e. the built-in Lahiri
definition). Set in [`app/astronomy/core.py:79`](../app/astronomy/core.py#L79).

**Ayanamsa is not configurable.** There is no request parameter, no environment
variable, and no code path that selects a different ayanamsa. To use Raman or KP
you would have to fork the service. This is a statement of current fact, not a
roadmap item — no alternative-ayanamsa support is planned or scaffolded.

Measured Lahiri values from this build:

| Epoch | Lahiri ayanamsa |
|---|---|
| 1985-01-01 | 23.64759° |
| 1990-01-01 | 23.71743° |
| 2000-01-01 | 23.85709° |
| 2026-01-01 | 24.22032° |

**Why this matters to you, quantified.** You noted that a different ayanamsa
moves nakshatra boundaries. Measured over 20 000 instants sampled across
1980–1999:

| Alternative ayanamsa | Offset vs Lahiri (1990) | Births assigned a **different nakshatra** |
|---|---|---|
| Raman | −1.446° | **10.71%** |
| Krishnamurti (KP) | −0.097° | **0.71%** |
| Fagan–Bradley | +0.883° | (not measured; ~6.6% expected from offset) |

So roughly **one birth in nine** will get a different nakshatra under Raman than
under Lahiri. If RR Matrimony has legacy records whose nakshatra was computed
under a different ayanamsa, they will disagree with this API at that rate, and
the disagreement is *not* a bug on either side.

A worked boundary case: for a birth on **1988-03-01 21:35 UT**, Lahiri gives
**Ashlesha** and Raman gives **Magha**. Under Ashtakoota that flips the
Gana, Yoni, Nadi and Tara koota inputs simultaneously.

> There is a subtlety in "Lahiri" itself: Swiss Ephemeris' `SIDM_LAHIRI` is the
> Calendar Reform Committee definition. Some Indian almanac publishers use
> slightly different Lahiri realisations (differences of a few arc-seconds).
> That is far below the level that moves a nakshatra boundary except for births
> within a second or two of one.

### 1b. `moon_rashi` is the MOON's sign, not the ascendant

**`moon_rashi` is the chandra rashi.** This is the field Guna Milan needs.

The derivation is unambiguous — the same moon longitude feeds both the nakshatra
and the rashi ([`instant.py:49-52`](../app/panchang/instant.py#L49-L52)):

```python
moon      = moon_longitude(jd)          # sidereal, Lahiri
nak_idx   = elements.nakshatra_index(moon)   # floor(moon / 13°20′)
pada      = elements.nakshatra_pada(moon)
rashi_idx = elements.rashi_index(moon)       # floor(moon / 30°)
```

**The ascendant is not computed anywhere in this service.** There is no call to
`swe.houses`, no `ascmc`, no lagna, in any module. Consequently there is no risk
of the field silently being lagna — the code has no way to produce a lagna. The
15 Ashtakoota points that depend on rashi (Varna 1, Vashya 2, Graha Maitri 5,
Bhakoot 7) are safe to compute from `moon_rashi`.

You can verify this yourself on any response without trusting this document:
`moon_rashi.number == floor(moon_longitude_sidereal / 30) + 1` must hold
exactly, and it does for every response — the field is a pure function of the
returned moon longitude. A lagna could not satisfy that identity, since it
depends on latitude and sidereal time. **Use this as an integration assertion.**

Likewise `nakshatra.number == floor(moon_longitude_sidereal / (360/27)) + 1`.

### 1c. Ephemeris and accuracy

The astronomy is **Swiss Ephemeris** via **`pyswisseph` 2.10.03**. Two backends
exist, selected at startup by [`init_ephemeris`](../app/astronomy/core.py#L45):

| Backend | Flag | When used | Accuracy |
|---|---|---|---|
| **Moshier** (built-in analytical theory) | `FLG_MOSEPH` | Whenever `SHUBHTITHI_EPHEMERIS_PATH` is unset or not a directory | A few arc-seconds (project's own claim) |
| Swiss Ephemeris data files | `FLG_SWIEPH` | `SHUBHTITHI_EPHEMERIS_PATH` points at a directory of `sepl_*.se1` / `semo_*.se1` | Sub-arc-second |

**The deployed service runs Moshier.** This is not a configuration accident you
can fix with an env var: [`.dockerignore`](../.dockerignore) explicitly excludes
`data/ephe/` from the build context, and no `.se1` files exist in the repository.
The container therefore has no ephemeris data files to point at, so
`SHUBHTITHI_EPHEMERIS_PATH` cannot currently be satisfied in the Railway image
as built. Shipping the files would require a Dockerfile/`.dockerignore` change
or a mounted volume. Neither is in place today.

**What Moshier's accuracy means in practice.** The moon moves ~13.176°/day
≈ 0.549 arcsec/second of time. So a 3-arcsecond longitude error corresponds to
roughly **5–6 seconds of clock time** in the placement of a nakshatra boundary.
For janma-nakshatra this is irrelevant unless a birth is timed to within seconds
of a boundary crossing — and birth times recorded to the minute already carry
~60× more uncertainty than the ephemeris does. The README states that with data
files, element end times match published almanacs to the minute; with Moshier,
expect agreement within ~1–2 minutes on lunar events.

Practical guidance: **the ephemeris backend is not your error budget; the
recorded birth time is.** See §5.6.

`/v1/health` reports the active backend and ayanamsa at runtime:

```json
{"status":"ok","ephemeris":"Swiss Ephemeris (pyswisseph 2.10.03)",
 "ayanamsa":"Lahiri; 23.8571deg at J2000", "...": "..."}
```

Note that the `ephemeris` string says "Swiss Ephemeris" in **both** backend
cases — it reports the pyswisseph library version, not which model is active.
It is not a reliable way to detect Moshier vs. data files. The startup log line
`Ephemeris backend: Moshier (built-in)` is authoritative.

---

## 2. The response

### 2a. Verified example

Request (a birth instant; no personal data):

```
GET /v1/nakshatra-at?date=1990-04-21&time=14:35:00&lat=17.0&lon=82.2&tz=Asia/Kolkata
```

Actual response body, produced by running this build:

```json
{
  "instant": "1990-04-21T14:35:00+05:30",
  "coordinates": {
    "lat": 17.0,
    "lon": 82.2,
    "timezone": "Asia/Kolkata"
  },
  "moon_longitude_sidereal": 314.944169,
  "nakshatra": {
    "number": 24,
    "name": "Shatabhisha",
    "pada": 3
  },
  "moon_rashi": {
    "number": 11,
    "name": "Kumbha"
  }
}
```

With `time` omitted, one extra top-level key appears and the instant becomes
local sunrise:

```json
{
  "instant": "1990-04-21T05:41:46+05:30",
  "coordinates": {"lat": 17.0, "lon": 82.2, "timezone": "Asia/Kolkata"},
  "moon_longitude_sidereal": 309.831122,
  "nakshatra": {"number": 24, "name": "Shatabhisha", "pada": 1},
  "moon_rashi": {"number": 11, "name": "Kumbha"},
  "time_assumed": "sunrise"
}
```

Note the pada differs (3 vs 1) for the same calendar date — see §5.6.

### 2b. Field reference

| Key | Type | Always present | Meaning |
|---|---|---|---|
| `instant` | `string` | yes | ISO-8601 datetime **with UTC offset**, in the resolved timezone. The exact instant the computation used. |
| `coordinates.lat` | `number` | yes | Echo of the request `lat`. |
| `coordinates.lon` | `number` | yes | Echo of the request `lon`. |
| `coordinates.timezone` | `string` | yes | IANA zone actually used — echoed from `tz`, or derived from coordinates when `tz` was omitted. |
| `moon_longitude_sidereal` | `number` | yes | Moon's sidereal (Lahiri) ecliptic longitude in degrees, `[0, 360)`, rounded to 6 decimal places. |
| `nakshatra.number` | `integer` | yes | **1..27**, Ashwini = 1. |
| `nakshatra.name` | `string` | yes | See the fixed vocabulary in §2c. |
| `nakshatra.pada` | `integer` | yes | **1..4**. Quarter of the nakshatra (3°20′ each). |
| `moon_rashi.number` | `integer` | yes | **1..12**, Mesha = 1. |
| `moon_rashi.name` | `string` | yes | See §2c. |
| `time_assumed` | `string` | **conditional** | Present **only** when `time` was omitted from the request. Current only value: `"sunrise"`. Absent when `time` was supplied. |

**Types.** `lat`/`lon`/`moon_longitude_sidereal` are JSON numbers (floats);
`number` and `pada` are JSON integers. `instant` is a string.

**There is no `response_model` declared for this endpoint.** It returns a plain
`dict`, so the OpenAPI document contains **no response schema** for
`/v1/nakshatra-at` — only for `/v1/health` and `/v1/cities`. If you are
generating a client from the schema, you must hand-write this response type.
The table above is the contract.

### 2c. Value vocabulary — exact spellings

This is the part you asked about most specifically. The service emits **exactly
one fixed ASCII spelling per value**. It never emits English sign names
("Aquarius"), never emits regional variants ("Sadayam", "Kumbham"), never emits
diacritics, and the spelling does not vary by request. Source:
[`app/panchang/names.py`](../app/panchang/names.py).

**Strong recommendation: map on `number`, not on `name`.** `nakshatra.number`
and `moon_rashi.number` are already the canonical 1-based indices that
Ashtakoota tables are keyed on. Your existing Sanskrit/English/regional name
matcher is unnecessary for this API and is a source of avoidable breakage — a
future spelling normalisation would silently misroute string matches, whereas
the numbers are fixed by the tradition itself.

#### Nakshatra — `number` → `name` (27)

| # | Name | # | Name | # | Name |
|---|---|---|---|---|---|
| 1 | `Ashwini` | 10 | `Magha` | 19 | `Mula` |
| 2 | `Bharani` | 11 | `Purva Phalguni` | 20 | `Purva Ashadha` |
| 3 | `Krittika` | 12 | `Uttara Phalguni` | 21 | `Uttara Ashadha` |
| 4 | `Rohini` | 13 | `Hasta` | 22 | `Shravana` |
| 5 | `Mrigashira` | 14 | `Chitra` | 23 | `Dhanishta` |
| 6 | `Ardra` | 15 | `Swati` | 24 | `Shatabhisha` |
| 7 | `Punarvasu` | 16 | `Vishakha` | 25 | `Purva Bhadrapada` |
| 8 | `Pushya` | 17 | `Anuradha` | 26 | `Uttara Bhadrapada` |
| 9 | `Ashlesha` | 18 | `Jyeshtha` | 27 | `Revati` |

Spellings that commonly differ in other sources — these are the forms this API
emits, and it emits **only** these:

- `Mrigashira` (not Mrigashirsha / Makayiram / Mrugasira)
- `Ardra` (not Arudra / Thiruvathirai)
- `Ashlesha` (not Aslesha / Ayilyam)
- `Mula` (not Moola / Moolam)
- `Dhanishta` (not Dhanishtha / Avittam)
- `Shatabhisha` (not Shatataraka / Sadayam / Satabhisha)
- `Jyeshtha` (not Jyestha / Kettai)
- `Swati` (not Svati / Chothi)
- `Purva Phalguni` / `Uttara Phalguni` / `Purva Ashadha` / `Uttara Ashadha` /
  `Purva Bhadrapada` / `Uttara Bhadrapada` — **single ASCII space**, no hyphen,
  no "Poorva", no "Uttra".

#### Rashi — `number` → `name` (12)

| # | Name | Western equivalent | # | Name | Western equivalent |
|---|---|---|---|---|---|
| 1 | `Mesha` | Aries | 7 | `Tula` | Libra |
| 2 | `Vrishabha` | Taurus | 8 | `Vrishchika` | Scorpio |
| 3 | `Mithuna` | Gemini | 9 | `Dhanu` | Sagittarius |
| 4 | `Karka` | Cancer | 10 | `Makara` | Capricorn |
| 5 | `Simha` | Leo | 11 | `Kumbha` | Aquarius |
| 6 | `Kanya` | Virgo | 12 | `Meena` | Pisces |

The Western column is for your orientation only — **the API never returns those
strings.** Watch `Karka` (not Kataka/Karkata), `Vrishchika` (not Vrischika),
`Meena` (not Meenam), `Vrishabha` (not Vrishab/Rishabha).

These names are **stable but not contractually frozen** — they are plain module
constants with no test asserting their exact spelling, so a future
transliteration cleanup would not be caught by CI. Another reason to key on
`number`.

---

## 3. Parameter semantics

Definition: [`app/routers/nakshatra.py`](../app/routers/nakshatra.py).

| Param | Required | Type | Notes |
|---|---|---|---|
| `date` | **yes** | `date` | `YYYY-MM-DD`. |
| `lat` | **yes** | `float` | `-90 ≤ lat ≤ 90`, enforced. |
| `lon` | **yes** | `float` | `-180 ≤ lon ≤ 180`, enforced. |
| `time` | no | `time` | `HH:MM` or `HH:MM:SS`. |
| `tz` | no | `string` | **IANA name only.** |

### 3a. `tz` — IANA names only, despite the `anyOf`

**The `anyOf` in the OpenAPI schema does not mean "name or offset".** It is the
standard pydantic rendering of the Python type `str | None` — i.e.
`anyOf: [{type: string}, {type: null}]`. The two branches are *string* and
*null*, not two string formats.

The value must be a key in the IANA tz database. It is validated by
`resolve_zone()` ([`app/api.py`](../app/api.py)) before any computation runs,
then used as `zoneinfo.ZoneInfo(tz_name)`.

Verified behaviour:

| `tz` value | Result |
|---|---|
| `Asia/Kolkata` | ✅ 200 |
| `UTC` | ✅ 200 |
| `Etc/GMT+9` | ✅ 200 |
| omitted | ✅ 200 — derived from `lat`/`lon` |
| `+05:30` | ❌ **422 `invalid_timezone`** |
| `IST` | ❌ **422 `invalid_timezone`** |
| `Not/AZone` | ❌ **422 `invalid_timezone`** |

The rejection body is a normal error envelope:

```json
{
  "error": {
    "code": "invalid_timezone",
    "message": "Unknown IANA timezone: '+05:30'.",
    "detail": "Expected an IANA timezone name such as 'Asia/Kolkata'. UTC offsets ('+05:30') and abbreviations ('IST') are not accepted. (ZoneInfoNotFoundError)"
  }
}
```

> **Changed in `ed7ed22`.** This used to be an uncaught `ZoneInfoNotFoundError`
> surfacing as a bare **HTTP 500 with a `text/plain` body**. If you have a
> contract test pinning `500`, or a client that special-cases a non-JSON error
> here, both need updating. See [§8](#8-changelog).

Send a validated IANA name. For Indian births that is `Asia/Kolkata` for
essentially all of them.

**When `tz` is omitted** it is derived from the coordinates with
`timezonefinder` ([`app/geo/tz.py`](../app/geo/tz.py)). Two consequences:

- Over open ocean you get an `Etc/GMT±N` zone rather than an error — e.g.
  `lat=0, lon=-140` yields `Etc/GMT+9`. The documented `422 tz_unresolved` is
  therefore rarely reachable in practice; do not rely on it to catch bad
  coordinates.
- The **first** coordinate lookup after a process start loads the polygon
  dataset and costs **~1.5 seconds** (measured). Subsequent lookups are ~3 µs.
  Passing `tz` explicitly skips this path entirely.

### 3b. `time` omitted → **local sunrise** (not midnight, not noon)

The result is a **single instant**, never date-wide.

If `time` is omitted, the service computes **apparent sunrise at `lat`/`lon` on
`date`** and evaluates the moon there, then sets `"time_assumed": "sunrise"`
([`instant.py:33-42`](../app/panchang/instant.py#L33-L42)). This follows the
janma-nakshatra convention for unknown birth times.

Sunrise is the **apparent rise of the sun's upper limb including atmospheric
refraction** (Swiss Ephemeris default; the published-almanac convention).
Configurable service-side via `SHUBHTITHI_SUNRISE_UPPER_LIMB` and
`SHUBHTITHI_SUNRISE_REFRACTION`, both defaulting to `true`. Not settable per
request.

In the example above, sunrise (05:41:46) vs. the real birth time (14:35) changed
the **pada from 1 to 3** while leaving the nakshatra unchanged. That is typical:
see §5.6 for when it changes the nakshatra itself.

**When `time` IS supplied**, note that any UTC offset embedded in the `time`
value is **silently discarded**. `time=14:35:00+05:30` is parsed, then only
`.hour`, `.minute`, `.second` are read and re-tagged with `tz`
([`instant.py:45-46`](../app/panchang/instant.py#L45-L46)). Sending
`time=14:35:00+05:30&tz=Asia/Kolkata` happens to be harmless, but
`time=14:35:00+05:30&tz=America/New_York` would be interpreted as 14:35
**New York** time with no error. Send a naive `HH:MM:SS` and let `tz` carry the
offset.

Sub-second precision is not supported: only `hour`, `minute`, `second` are used.

### 3c. `lat` / `lon` — signed decimal degrees, validated

Signed decimal degrees. **North and East positive**; south and west negative.
`lat ∈ [-90, 90]` and `lon ∈ [-180, 180]` are enforced by FastAPI
(`Query(..., ge=…, le=…)`), returning a well-formed 422:

```json
{"error": {"code": "validation_error",
           "message": "Invalid request parameters.",
           "detail": "[{'type': 'less_than_equal', 'loc': ('query', 'lat'), ...}]"}}
```

No other validation: `0,0` is accepted, and there is no plausibility check
against the supplied `tz`. **A `lat`/`lon` that contradicts `tz` produces a
confidently wrong answer, not an error** — the coordinates only affect sunrise
(and the derived zone when `tz` is absent), while `tz` alone fixes the instant.
Sign errors on `lon` are the classic failure and will not be caught.

`detail` is a stringified Python repr of the pydantic error list, not JSON.
Treat it as opaque human-readable text; branch on `error.code`.

### 3d. `date` is interpreted in `tz`, never UTC

`date` + `time` + `tz` are combined into a single local, timezone-aware
datetime, which is then converted to UT for the ephemeris
([`instant.py:45-47`](../app/panchang/instant.py#L45-L47) →
[`datetime_to_jd`](../app/astronomy/core.py#L88)).

So `date=1990-04-21&time=23:50:00&tz=Asia/Kolkata` is 1990-04-21 23:50 **IST**
(= 18:20 UTC), *not* 1990-04-21 23:50 UTC. Do not pre-convert your birth
timestamps to UTC — send local civil date/time plus the birth-place zone, which
is how such records are normally stored anyway.

`date` must be a **pure date**. `date=1990-04-21T14:35:00` is rejected with 422
(`date_from_datetime_inexact`).

---

## 4. Operational

### 4a. Auth and rate limits — neither is implemented

**Authentication: none.** There is no API key check, no auth dependency, no
security scheme in the OpenAPI document. Verified by searching the whole
codebase for `api_key`, `X-API-Key`, `Depends(`, and middleware registration:
the only `Depends` in the service are DB-session injections on `/cities`,
`/panchang`, `/health` — and `/v1/nakshatra-at` has none at all.

Your `X-API-Key` header, when configured, is **accepted and ignored** like any
unrecognised header. Sending it is harmless and forward-compatible, so keep
doing it. But today the endpoint is fully open to anyone who can reach the host.

**No API key mechanism is planned or scaffolded** — there is no partial
implementation, config flag, or TODO for one in the repository. If you need the
header enforced, treat it as unbuilt work, not as a switch to flip.

**Rate limiting: none.** No `slowapi`, no limiter, no throttling middleware.
Any limit you encounter would come from the Railway edge, not this application.

**CORS: not configured.** No `CORSMiddleware` is registered, so browsers will
block cross-origin calls. Irrelevant for your server-to-server integration, but
it means this API cannot be called directly from a customer's browser.

Taken together: **do not expose this base URL to untrusted clients.** Keep the
calls server-side from the RR Matrimony backend.

### 4b. Availability — treat it as a hobby deployment

Being direct, since you are deciding whether to put a customer-facing feature
behind it: **as configured today this is a single-instance hobby deployment, not
a service with an availability guarantee.**

Evidence from the repository:

- **Railway**, Docker builder, healthcheck `GET /v1/health` (300 s timeout),
  `restartPolicyType: ON_FAILURE`, `restartPolicyMaxRetries: 3`
  ([`railway.json`](../railway.json)).
- **Single uvicorn process**, no `--workers`, no process manager
  ([`Dockerfile`](../Dockerfile)).
- **SQLite** on the container filesystem, with no volume declared — the cache DB
  is rebuilt from scratch on every deploy and every restart.
- No load balancer, no replicas, no readiness/liveness distinction beyond the
  single healthcheck, no uptime monitoring, no alerting, no SLO, no error
  tracking, no request logging beyond uvicorn's default stdout.
- No staging environment.

There is **no published SLA and no uptime history** — I have no measurement of
either, and this document will not invent one.

**Mitigating facts specific to your endpoint.** `/v1/nakshatra-at` is the
best-behaved endpoint in the service for your purposes:

- It touches **no database** — no session dependency, no cache read or write. It
  is pure computation, so SQLite loss, cache eviction, and the 15-month cache
  horizon are all irrelevant to it.
- It is **fast and deterministic**: measured **0.02 ms/call** warm with an
  explicit `time`, **0.17 ms/call** on the sunrise path, ~11 ms on the very
  first call (per-thread ephemeris init). Network latency will dominate
  entirely.
- It is **stateless and idempotent**, so retries are always safe and results are
  perfectly cacheable.

**Cold start is the real risk.** Application startup seeds ~153 000 cities into
SQLite before serving traffic, and the first `tz`-derivation loads
timezonefinder polygons (~1.5 s). After any restart or redeploy, expect a
multi-second window of unavailability or slow first responses.

**Recommendation.** Because the endpoint is pure, deterministic and
sub-millisecond, the robust integration is: **compute once at profile-creation
time and persist `nakshatra.number`, `nakshatra.pada` and `moon_rashi.number` on
your own record.** Then Guna Milan runs entirely against your database and never
depends on this service's availability at match time. Call the API again only
when birth details are edited. That reduces this from an availability dependency
to a batch-enrichment dependency, and it also insulates you from a future
ayanamsa or spelling change (store the values *and* the service version you got
them from).

If you do call it synchronously, set a short timeout (1–2 s is generous given
sub-millisecond compute) and degrade gracefully.

### 4c. Custom domain — none configured, none planned in-repo

The repository contains **no custom domain configuration**: no domain in
`railway.json`, no reverse-proxy config, no CNAME, no hostname in any settings
file or documentation. The service is reachable only at whatever
Railway-generated URL the deployment has.

I found **no evidence in the repository of a planned custom domain** — no issue,
TODO, or config stub. That is the honest state; it is not the same as "a domain
will never be added," and this document cannot speak to intentions not recorded
in the code.

Keeping the base URL per-tenant configurable, as you already do, is the right
call. Two related notes: the app sets no `root_path`, so it must be mounted at
the domain root rather than a subpath, and it emits no `Cache-Control` headers.

---

## 5. Known limitations

Things you would otherwise discover in production.

### 5.1 Invalid `tz` is rejected — 422, not a fallback

Covered in §3a. `+05:30`, `IST`, or any non-IANA string yields
**422 `invalid_timezone`** with a normal JSON envelope. The service never
guesses a zone from a malformed value and never silently substitutes UTC, so a
bad `tz` fails loudly rather than producing a chart-shifted result.

This is no longer the trap it was — as of `ed7ed22` it is an ordinary
validation error. It stays on this list only because the *rejection* still
surprises people who expect an offset to work.

### 5.2 High latitude: the sunrise fallback silently becomes local midnight

**The most dangerous behaviour in the endpoint**, because it is wrong *silently*.

When `time` is omitted and the sun does not rise or set on that date,
`rise_set()` returns `None` and the code falls back to `jd0` — **local
midnight** — but still reports `"time_assumed": "sunrise"`
([`instant.py:41-42`](../app/panchang/instant.py#L41-L42)):

```python
jd = sunrise if sunrise is not None else jd0   # jd0 = local midnight
time_assumed = "sunrise"                        # ← set unconditionally
```

Verified at Tromsø (69.65 °N):

| Request | `instant` returned | `time_assumed` |
|---|---|---|
| `2026-06-21`, no `time` (midnight sun) | `2026-06-21T00:00:00+02:00` | `"sunrise"` |
| `2026-12-21`, no `time` (polar night) | `2026-12-21T00:00:00+01:00` | `"sunrise"` |

The response is indistinguishable from a genuine sunrise result. Because the
moon moves ~13.18°/day, a spurious 12-hour shift is up to **~6.6° ≈ half a
nakshatra** of error.

Affects latitudes above roughly ±66.5° near the solstices — a real concern for
diaspora births in Norway, Sweden, Finland, northern Russia, Alaska and northern
Canada.

**Mitigation: always send `time`.** With an explicit `time` this code path is
never entered and high latitudes behave correctly. If you must omit `time`,
treat `|lat| > 60` results as low-confidence, or detect the fallback yourself —
`instant` ending in exactly `T00:00:00` alongside `"time_assumed": "sunrise"` is
the signature.

### 5.3 Supported date range

The backend's own limit is expressed in Julian Days: the Moshier model spans
**JD 625000.5 – 2818000.5**, which is `-3001-02-03` to `+3003-04-29` in the
proleptic Gregorian calendar (roughly 3002 BCE to 3003 CE).

| Bound | Value | Cause |
|---|---|---|
| Earliest reachable | `0001-01-01` | Python/pydantic `date` minimum — years ≤ 0 cannot be expressed in the request at all, so the ephemeris' BCE range is unreachable |
| Latest working for any time of day | **`3003-04-28`** | Last date wholly inside the Moshier range |
| Beyond that | **422 `ephemeris_range`** | Clean JSON rejection |

Because the limit is an *instant* (JD 2818000.5 = `3003-04-29` 00:00 UT) rather
than a date, the final day is partial: `3003-04-29` succeeds only for instants
before 00:00 UT, which for any eastern timezone means it does not succeed at
all. Verified by bisection — every year from 1 through 3002 returns 200,
`3003-04-28` at 12:00 IST returns 200, and `3003-04-29` at 12:00 IST returns
422.

```json
{
  "error": {
    "code": "ephemeris_range",
    "message": "Date is outside the supported ephemeris range.",
    "detail": "swisseph.calc_ut: jd 2999573.963647 outside Moshier's Moon range 625000.50 .. 2818000.50 "
  }
}
```

> **Changed in `ed7ed22`.** This used to be an uncaught `swisseph.Error`
> surfacing as a bare HTTP 500. See [§8](#8-changelog).

Irrelevant for matrimony use either way, but the failure is now diagnosable
from the response body.

### 5.4 Historical timezones — correct via tzdata, with a pre-1906 surprise

Historical offsets come from `zoneinfo` + the bundled `tzdata` package, so
**DST-era and historical rules are applied correctly**, including for your 1980s
births. Verified:

| Request | `instant` | Correct? |
|---|---|---|
| 1985-07-04 12:00 `America/New_York` | `1985-07-04T12:00:00-04:00` | ✅ EDT |
| 1985-01-15 12:00 `America/New_York` | `1985-01-15T12:00:00-05:00` | ✅ EST |
| 1985-06-15 09:00 `Australia/Sydney` | `1985-06-15T09:00:00+10:00` | ✅ AEST (winter) |

**Indian births from the 1980s are straightforward** — `Asia/Kolkata` has been a
constant `+05:30` since 1945, with no DST. India observed DST only in 1942–1945.

**The surprise is pre-1906 dates**, where tzdata supplies local mean time:

| Date | Offset returned for `Asia/Kolkata` |
|---|---|
| 1900-06-15 | `+05:21:10` (Madras time) |
| 1800-06-15 | `+05:53:28` (LMT) |
| 1000-06-15 | `+05:53:28` (LMT) |

This is *correct* per tzdata, but it means an old record's offset will not be
`+05:30`, and the resulting `instant` string carries a seconds component in the
offset (`+05:53:28`) that some ISO-8601 parsers reject. If you ingest
pre-1906 births, test your date parser against that format.

**Ambiguous and nonexistent local times are not handled.** During a DST
fall-back, a repeated local time resolves to one of the two instants by
`zoneinfo`'s default rule (`fold=0`, the earlier offset) with no warning; during
a spring-forward gap, a nonexistent local time is silently normalised rather
than rejected. The error is at most one hour ≈ 0.55° of moon motion, which flips
a nakshatra only for births within an hour of a boundary (~4%). No error is
raised either way.

### 5.5 Southern hemisphere is fine

No hemisphere-specific logic exists; negative `lat` is handled by the same
Swiss Ephemeris rise/set call. Sydney 1985-06-15 09:00 correctly returns
`+10:00` (southern winter, no DST) and Bharani pada 3. **No known
southern-hemisphere issues** — the only latitude-dependent risk is §5.2, which
applies symmetrically to both poles.

### 5.6 Birth-time precision is your dominant error source

Not a defect, but the thing most likely to cause a Guna Milan dispute. Derived
from the moon's mean motion of ~13.176°/day:

| Quantity | Arc | Mean duration |
|---|---|---|
| One nakshatra | 13°20′ | **~24.3 hours** |
| One pada | 3°20′ | **~6.1 hours** |
| Moon motion per hour | ~0.549° | — |

Consequences:

- A **±15-minute** birth-time uncertainty moves the moon ~0.14°. It changes the
  nakshatra only for births within 15 minutes of a boundary — a 30-minute window
  out of ~1458 minutes, so **~2% of births**. It changes the **pada** for a
  30-minute window out of ~364, so **~8% of births**.
- Omitting `time` and accepting the sunrise default gives an instant that can be
  up to ~18 hours from the true birth — **up to ~0.74 nakshatra of error.** In
  the §2a example it shifted the pada by 2. For Ashtakoota, a nakshatra-unknown
  match is not merely approximate; Nadi (8 points) and Gana (6 points) can be
  entirely wrong.

**Recommendation:** treat sunrise-defaulted results as provisional, mark them in
your data model (the `time_assumed` key tells you exactly when this happened),
and do not present a Guna Milan score derived from one with the same confidence
as a timed birth.

### 5.7 Miscellaneous

- **No response schema in OpenAPI** for this endpoint (§2b) — generated clients
  will type it as a free-form object.
- **Name spellings are untested** (§2c) — no test pins them; key on `number`.
- **`coordinates.lat`/`lon` are echoed** unrounded and unvalidated for
  plausibility (§3c).
- **The `X-API-Key` you send is ignored** (§4a) — do not infer from a 200 that
  your key was accepted.
- **`error.detail` is a Python repr** for `validation_error`, not JSON (§3c).
  Branch on `error.code`, treat `detail` as opaque human-readable text.
- **Every error is now a JSON envelope** — `{"error": {"code", "message",
  "detail"}}` — including the two cases that used to return plain-text 500s
  (§5.1, §5.3). A genuinely unhandled exception would still produce a
  non-envelope 500, so defensive parsing is still worth keeping, but there is
  no longer a *known* path that does.
- **Ayanamsa correctness depends on a per-thread fix.** pyswisseph stores the
  sidereal mode per thread, and FastAPI runs sync endpoints on a worker pool, so
  a mode set once at startup would not apply to request threads — they would
  fall back to Fagan–Bradley (~0.9° off) and corrupt every nakshatra and rashi.
  The service handles this by configuring the mode lazily per thread
  ([`_ensure_thread`](../app/astronomy/core.py#L69)), and
  [`tests/test_ayanamsa_threading.py`](../tests/test_ayanamsa_threading.py)
  guards it. Flagged because it is invisible in the response: a regression here
  would produce plausible, uniformly-wrong nakshatras rather than an error. If
  you ever see a systematic ~1-nakshatra skew, check `/v1/health`'s reported
  ayanamsa (~24.2° for 2026 is Lahiri; ~25.1° is Fagan–Bradley).

---

## 6. Recommended integration checklist

1. **Always send `time`** when known — avoids §5.2 entirely and removes the
   largest error source (§5.6).
2. **Always send `tz`** as a validated IANA name — avoids the `invalid_timezone`
   rejection in §5.1 and the 1.5 s cold-start polygon load in §3a.
3. Send **local civil date/time**, not UTC (§3d).
4. **Key on `nakshatra.number` and `moon_rashi.number`**, never on the name
   strings (§2c).
5. **Assert the identities** on every response (§1b):
   `nakshatra.number == floor(moon_longitude_sidereal / (360/27)) + 1` and
   `moon_rashi.number == floor(moon_longitude_sidereal / 30) + 1`.
   These are cheap and would catch an ayanamsa/field-semantics regression.
6. **Branch on `time_assumed`** — if present, flag the profile as
   birth-time-unknown and degrade the Guna Milan confidence (§5.6).
7. **Persist the computed values** at profile creation rather than calling at
   match time (§4b), storing the service version alongside them.
8. **Branch on `error.code`**, not on status or message text (§5.7). All known
   error paths now return the JSON envelope.
9. **Keep calls server-side** — no auth, no rate limiting, no CORS (§4a).
10. **Need the ascendant, houses, dashas or Mars' house for manglik?** Those are
    on `GET /v1/chart`, not here — see [`CHART-API.md`](CHART-API.md). This
    endpoint returns the moon only.

---

## 7. Open questions for the ShubhTithi maintainer

Not answerable from the code; listed so they are not mistaken for settled facts.

1. Will `X-API-Key` ever be enforced, and should consumers send it now? (Today
   it is ignored — §4a.)
2. Is a custom domain intended? (Nothing in the repository — §4c.)
3. Is there an intended availability target, or is a hobby deployment the
   settled answer? (§4b.)
4. Will Swiss Ephemeris data files ever ship in the image, and would that be a
   versioned change? Results would shift by seconds of arc (§1c).
5. Is the §5.2 high-latitude fallback intended? A distinct
   `"time_assumed": "midnight_no_sunrise"` would make it detectable. **Still
   open** — this is the one known silent-wrongness path left in this endpoint,
   and it is a two-line fix whenever you want it.

Resolved since the first revision of this document:

- ~~Should `date` beyond the ephemeris range and invalid `tz` return 422 instead
  of 500?~~ **Done in `ed7ed22`** — both are JSON 422s now (§8).

---

## 8. Changelog

### `ed7ed22` — chart endpoint; two error paths corrected

**Added:** `GET /v1/chart`, documented separately in
[`CHART-API.md`](CHART-API.md). It does not change this endpoint's behaviour,
but note that a chart and a `/v1/nakshatra-at` call for the same instant now
agree on the moon **exactly** — identical `longitude_sidereal`, `nakshatra`
(including `pada`), `rashi` and `instant`. That equality is asserted in the
test suite and is a useful integration canary.

**Changed — two behaviours that were previously plain-text HTTP 500s are now
JSON 422s.** Both affect `/v1/nakshatra-at`, not just the new endpoint:

| Trigger | Was | Now |
|---|---|---|
| `tz` not an IANA name (`+05:30`, `IST`, …) | 500, `text/plain` | **422 `invalid_timezone`** |
| `date` outside the ephemeris range | 500, `text/plain` | **422 `ephemeris_range`** |

The first was explicitly requested by the Navodayam integration; the second is
the same defect class and came along with the handler.

**Migration note.** If you have contract tests pinning `500` for either case,
they will now fail. If your client special-cases a non-JSON error body on these
paths, that branch is now dead code. Nothing else about the request or success
response changed — no field was added, removed, renamed or re-typed on
`/v1/nakshatra-at`.

**Unchanged:** ayanamsa (Lahiri, still not configurable), the Moshier ephemeris
backend, the sunrise fallback and its high-latitude bug (§5.2), auth, rate
limiting, CORS, hosting.
