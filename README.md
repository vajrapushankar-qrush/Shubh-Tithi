# ShubhTithi

**Open-source FastAPI service that computes Hindu Panchang (almanac) data.**

ShubhTithi is a pure backend HTTP API. It computes tithi, nakshatra, yoga,
karana, vara, sun/moon timings, inauspicious windows, muhurats, lunar & solar
months, rashi, eclipses and more — for any city on Earth, any date — using the
[Swiss Ephemeris](https://www.astro.com/swisseph/) for all astronomy.

All calculations are **sidereal with Lahiri ayanamsa** and follow the
conventions used by traditional Panchangam publishers, so results are
directly comparable.

- **No frontend.** Consumed over HTTP (test with Postman/curl). Interactive docs
  at `/docs`.
- **Self-contained.** Bundles a global city dataset; no external services.
- **Lazily cached.** First request for a city computes 15 months and stores it in
  SQLite; subsequent requests are pure lookups.
- **License:** AGPL-3.0-or-later.

---

## Quick start

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/) (or plain pip).

```bash
# 1. Install dependencies
uv sync

# 2. (Optional) seed the DB up front — otherwise it seeds on first startup
uv run python -m scripts.seed

# 3. Run the API
uv run uvicorn app.main:app --reload
#   or: uv run fastapi dev app/main.py

# 4. Open the docs
#   http://127.0.0.1:8000/docs
```

The first startup seeds ~153k cities into SQLite (a few seconds, one time). The
first Panchang request for a given city computes a 15-month horizon (~1–2 s);
everything after that is a lookup.

With plain pip instead of uv:

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

---

## API

Base path: `/v1`. All times are ISO-8601 **with the city's local UTC offset**.
Errors share the shape `{"error": {"code", "message", "detail"}}`.

### `GET /v1/cities` — search cities (for disambiguation)

```bash
curl "http://127.0.0.1:8000/v1/cities?q=new+yo&country=US"
```
```json
{
  "query": "new yo", "count": 5,
  "results": [
    {"id": 122795, "name": "New York City", "state": "New York",
     "country": "United States", "country_code": "US",
     "lat": 40.71427, "lon": -74.00597, "timezone": "America/New_York"}
  ]
}
```
`country` accepts an ISO2 code or a country-name fragment.

### `GET /v1/panchang` — full panchang for one day

By `city_id` (from `/v1/cities`) **or** direct `lat`/`lon` (+ optional `tz`):

```bash
curl "http://127.0.0.1:8000/v1/panchang?city_id=132132&date=2026-08-15"
curl "http://127.0.0.1:8000/v1/panchang?lat=17.385&lon=78.4867&tz=Asia/Kolkata&date=2026-08-15"
```

Response (abridged):
```json
{
  "date": "2026-08-15",
  "city": {"id": 132132, "name": "Hyderabad", "timezone": "Asia/Kolkata", "...": "..."},
  "vara": {"name": "Shanivara", "english": "Saturday"},
  "tithi": [
    {"number": 3, "name": "Tritiya", "paksha": "Shukla", "end": "2026-08-15T17:29:24+05:30"},
    {"number": 4, "name": "Chaturthi", "paksha": "Shukla", "end": "2026-08-16T16:53:02+05:30"}
  ],
  "nakshatra": [
    {"number": 12, "name": "Uttara Phalguni", "pada": 1, "end": "2026-08-16T03:25:45+05:30"},
    {"number": 13, "name": "Hasta", "pada": 4, "end": "2026-08-17T03:50:53+05:30"}
  ],
  "yoga":  [{"number": 20, "name": "Shiva", "end": "2026-08-15T07:09:05+05:30"}, "..."],
  "karana":[{"name": "Taitila", "end": "2026-08-15T06:03:26+05:30"}, "..."],
  "moon_rashi": {"number": 5, "name": "Simha", "transition": "2026-08-15T09:34:49+05:30", "next": "Kanya"},
  "sun_rashi":  {"number": 4, "name": "Karka", "transition": null},
  "lunar_month": {"amanta": "Bhadrapada", "purnimanta": "Bhadrapada", "adhika_masa": false},
  "samvatsara": "Parabhava", "shaka_year": 1948, "vikram_year": 2083,
  "solar_month": {"tamil_month": "Aadi", "malayalam_month": "Karkidakam",
                  "bengali_month": "Shrabon",
                  "current_sankranti": "2026-07-16T23:39:23+05:30",
                  "next_sankranti": "2026-08-17T07:58:46+05:30"},
  "sun":  {"sunrise": "2026-08-15T05:58:49+05:30", "sunset": "2026-08-15T18:42:09+05:30"},
  "moon": {"moonrise": "2026-08-15T08:14:10+05:30", "moonset": "2026-08-15T20:33:27+05:30"},
  "inauspicious": {
    "rahu_kalam":   {"start": "...09:09:39+05:30", "end": "...10:45:04+05:30"},
    "yamaganda":    {"start": "...", "end": "..."},
    "gulika_kalam": {"start": "...", "end": "..."}
  },
  "auspicious": {
    "abhijit_muhurat": {"start": "...11:55:03+05:30", "end": "...12:45:56+05:30", "avoided_today": false},
    "brahma_muhurat":  {"start": "...04:23:30+05:30", "end": "...05:00:08+05:30"}
  },
  "choghadiya": {
    "day":   [{"name": "Kaal",  "quality": "bad",  "start": "...05:58+05:30", "end": "...07:33+05:30"}, "... 8 bands"],
    "night": [{"name": "Char",  "quality": "good", "start": "...18:42+05:30", "end": "...20:17+05:30"}, "... 8 bands"]
  },
  "abhijit_muhurat": {"start": "...11:55:03+05:30", "end": "...12:45:56+05:30", "avoided_today": false},
  "bhadra": [{"start": "2026-08-16T05:05:48+05:30", "end": "2026-08-16T16:53:02+05:30"}],
  "eclipse": null
}
```

Notes:
- **Tithi / nakshatra / yoga / karana are lists.** The first entry is the one
  prevailing at sunrise; further entries are the other angas *touching* the
  Hindu day (sunrise → next sunrise). This naturally reports **kshaya** (skipped)
  and **vriddhi** (repeated) tithis. Each entry carries its **end time**.
- **`inauspicious`** — Rahu Kalam, Yamaganda, Gulika Kalam (avoid these).
- **`auspicious`** — Abhijit Muhurat (midday; `avoided_today` on Wednesdays) and
  Brahma Muhurat (pre-dawn).
- **`choghadiya`** — the primary muhurat time-band system. Day (sunrise→sunset)
  and night (sunset→next sunrise) each split into 8 bands, each named
  (Amrit/Shubh/Labh = `good`, Char = `neutral`, Rog/Kaal/Udveg = `bad`). A
  consuming app picks activity times from the `good` bands minus the
  inauspicious/Bhadra/eclipse windows.
- **`bhadra`** lists explicit Vishti/Bhadra windows for the day (karana == Vishti).
- **`eclipse`** is `null` unless a solar/lunar eclipse falls on the Hindu day; when
  present it includes `type` and `visible_here` (`yes`/`no`/`unknown`).

> **Muhurat selection** is *subtractive*: take the day, exclude the inauspicious
> windows / Bhadra / eclipse, confirm the tithi–nakshatra–yoga–vara quality for
> the activity, and choose within the `good` Choghadiya bands (and Abhijit /
> Brahma Muhurat). The activity-specific decision belongs in the consuming app;
> ShubhTithi supplies all the windows it needs.

### `GET /v1/panchang/range` — many days at once

```bash
curl "http://127.0.0.1:8000/v1/panchang/range?city_id=132132&start=2026-08-01&end=2026-08-31"
```
Returns `{city_id, start, end, count, days:[...]}`. Ranges longer than 400 days
(configurable) return `422 range_too_large`.

### `GET /v1/nakshatra-at` — moon nakshatra/pada/rashi at an instant

```bash
curl "http://127.0.0.1:8000/v1/nakshatra-at?date=1990-04-21&time=14:35:00&lat=17.0&lon=82.2"
```
`time` is optional; if omitted, local **sunrise** of that date is used and the
response includes `"time_assumed": "sunrise"` (a common janma-nakshatra
convention when birth time is unknown).

### `GET /v1/chart` — natal chart (kundali) at an instant

```bash
curl "http://127.0.0.1:8000/v1/chart?date=1984-04-24&time=21:06:00&tz=Asia/Kolkata&lat=17.0&lon=82.2"
```

Returns the sidereal ascendant, all nine grahas (longitude, rashi, nakshatra +
pada, degree-in-sign, **whole-sign house**, retrograde), the twelve houses, the
**navamsa (D9)** chart, the **Vimshottari dasha** tree (mahadasha +
antardasha, full 120-year cycle from birth), and manglik / kaal sarp / sade
sati flags.

`time` is **required** here — unlike `/v1/nakshatra-at` there is no sunrise
fallback, because an assumed birth time makes the ascendant and all twelve
houses wrong rather than merely approximate.

House system is **whole sign**; Rahu is the **mean** node and Ketu is exactly
opposite it. Full semantics, a worked example and the list of what is *not*
implemented: [`docs/CHART-API.md`](docs/CHART-API.md).

### `GET /v1/health`

Status, ephemeris version + ayanamsa, and cache statistics.

---

## Astronomical conventions

- **Sidereal zodiac, Lahiri ayanamsa** (`swe.SIDM_LAHIRI`) for every longitude.
- **Hindu day = local sunrise → next sunrise.** Each anga "for a date" is the one
  prevailing at that day's sunrise; end times are reported.
- **Sunrise/sunset = apparent rise/set of the upper limb with refraction** — the
  Swiss Ephemeris default and the convention published almanacs use. Both aspects are
  configurable (`SHUBHTITHI_SUNRISE_UPPER_LIMB`, `_REFRACTION`); see the comment
  in [`app/astronomy/core.py`](app/astronomy/core.py).
- **Element boundaries are global instants in UT**, found by bracketing then
  bisecting the true crossing to sub-second precision (never daily
  interpolation), then rendered into the city's local timezone.
- Index math: `tithi = ⌊(moon−sun)/12°⌋`, `nakshatra = ⌊moon/13°20′⌋`,
  `yoga = ⌊(sun+moon)/13°20′⌋`, `karana = ⌊(moon−sun)/6°⌋` — all sidereal.

### Comparing with a published almanac

Pick a city + date on both. Element **names** and **paksha** should match
exactly. **End times** should match to the minute when using downloaded Swiss
Ephemeris data files (below); with the built-in Moshier fallback expect
agreement within ~1–2 minutes on lunar events. Rahu Kalam / Yamaganda / Gulika
and Abhijit windows depend only on sunrise/sunset and the weekday, so they match
once sunrise matches.

---

## Ephemeris precision

`pyswisseph` bundles the **Moshier** analytical model (no data files, accurate to
a few arc-seconds) — good enough for minute-precision Panchang, and the default.

For maximum precision, download Swiss Ephemeris data files and point the service
at them:

1. Get `sepl_*.se1` (planets) and `semo_*.se1` (moon) from
   <https://www.astro.com/ftp/swisseph/ephe/> (or the
   [pyswisseph docs](https://astrorigin.com/pyswisseph/)).
2. Put them in a directory, e.g. `data/ephe/`.
3. Set `SHUBHTITHI_EPHEMERIS_PATH=data/ephe` in `.env`.

The service auto-detects the files and switches from Moshier to Swiss Ephemeris;
`/v1/health` shows which backend is active.

---

## How caching works

| table             | holds                                                             |
|-------------------|-------------------------------------------------------------------|
| `cities`          | id, name, country, lat, lon, **tz** (derived), cached_from/to     |
| `global_events`   | location-independent element boundaries (tithi/nakshatra/…) in UT |
| `global_eclipses` | eclipses within the computed span                                 |
| `city_days`       | per-city sunrise/sunset/moonrise/moonset                          |

Element boundaries and eclipses are the **same for every city**, so they are
computed once over a JD span and reused. Per-city work is only rise/set +
rendering + deriving Rahu Kalam etc. A request past a city's cached horizon
transparently extends it by another 15 months.

---

## Development

```bash
uv run pytest            # unit + integration tests
```

Tests include element index math, per-weekday Rahu/Yamaganda/Gulika segments,
Abhijit, a timezone-edge case (tithi ending after local midnight), eclipse
detection + visibility, and solar-month/sankranti checks. **Golden fixtures**
comparing to a published reference almanac are scaffolded in
[`tests/test_golden.py`](tests/test_golden.py) with clearly-marked `TODO`s to
fill in verified values (New York, London, Hyderabad, Bengaluru, plus
kshaya/vriddhi and adhika-masa days).

### Layout

```
app/
  astronomy/   core.py (swisseph wrappers), rootfind.py (boundary solver)
  panchang/    elements, names, windows, months, eclipses, instant, derive
  cache/       global_events, city_cache
  geo/         seed, search
  routers/     cities, panchang, nakshatra, health
  main.py      FastAPI app + lifespan
data/geo/      bundled trimmed city dataset (see PROVENANCE.md)
scripts/seed.py
tests/
```

---

## Data & licensing

- City data: trimmed [Countries-States-Cities](https://github.com/dr5hn/countries-states-cities-database)
  dataset — see [`data/geo/PROVENANCE.md`](data/geo/PROVENANCE.md).
- Astronomy: [Swiss Ephemeris](https://www.astro.com/swisseph/) via `pyswisseph`
  (AGPL-compatible; note Swiss Ephemeris' own dual license if you redistribute
  its data files).
- **ShubhTithi is licensed under AGPL-3.0-or-later.** See [LICENSE](LICENSE). If
  you run a modified version as a network service, the AGPL requires you to offer
  users the corresponding source.
