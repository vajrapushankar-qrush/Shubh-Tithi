# Geo data provenance

`cities.min.json` is a **trimmed** copy of the open
[Countries-States-Cities Database](https://github.com/dr5hn/countries-states-cities-database)
(CSC), which aggregates public-domain / open geographic data.

## What was done

The upstream `cities.json` (~200 MB, 153,728 cities worldwide, every row with
latitude/longitude) was reduced to only the fields this service needs:

| field    | meaning                                  |
|----------|------------------------------------------|
| `id`     | CSC city id (used as the API `city_id`)  |
| `name`   | city name                                |
| `state`  | state / province name                    |
| `cc`     | ISO2 country code                        |
| `country`| country name                             |
| `lat`    | latitude (deg, +N)                       |
| `lon`    | longitude (deg, +E)                      |
| `tz`     | IANA timezone (fallback only)            |
| `pop`    | population (for search ranking)          |

The heavy `translations`, `native`, and `wikiDataId` fields were dropped,
shrinking the file to ~22 MB. No coordinates were modified (only rounded to 5
decimal places, ~1 m precision).

## Coverage

153,728 cities across 218 countries, e.g. United States 19,786 · Australia
4,146 · India 4,199 · United Kingdom 3,879 · Canada 1,079 — strong global +
diaspora coverage. All rows have coordinates.

## Timezone

The bundled `tz` is used only as a fallback. On first run, each city's timezone
is **derived from its coordinates with `timezonefinder`** and stored in the
`cities` SQLite table (see `app/geo/seed.py`).

## License

CSC is distributed under the Open Database License (ODbL) / public-domain
sources. See the upstream repository for details.
