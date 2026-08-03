"""Tests for GET /v1/chart.

The reference birth throughout is 1984-04-24 21:06:00 Asia/Kolkata at
17.0N 82.2E -- the fixture the Navodayam backend pins against.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import install_error_handlers
from app.astronomy.core import init_ephemeris
from app.jyotish import dasha as dasha_mod
from app.routers import chart as chart_router
from app.routers import nakshatra as nakshatra_router

BIRTH = {"date": "1984-04-24", "time": "21:06:00", "tz": "Asia/Kolkata",
         "lat": 17.0, "lon": 82.2}

NAK_ARC = 360.0 / 27.0


@pytest.fixture(scope="module")
def client():
    """Chart + nakshatra routers only -- neither touches the DB, so this
    avoids the 153k-city seed that the full app's lifespan performs."""
    init_ephemeris(None)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(chart_router.router)
    app.include_router(nakshatra_router.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def body(client):
    r = client.get("/v1/chart", params=BIRTH)
    assert r.status_code == 200, r.text
    return r.json()


# --- Shape -----------------------------------------------------------------
def test_top_level_shape(body):
    assert body["instant"] == "1984-04-24T21:06:00+05:30"
    assert body["coordinates"] == {"lat": 17.0, "lon": 82.2, "timezone": "Asia/Kolkata"}
    assert body["ayanamsa"] == "lahiri"
    assert body["house_system"] == "whole_sign"
    assert body["node_type"] == "mean"


def test_nine_grahas_in_order(body):
    assert [p["name"] for p in body["planets"]] == [
        "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu",
    ]


def test_every_planet_has_a_house_1_to_12(body):
    """The one field the consumer cannot degrade on."""
    for p in body["planets"]:
        assert isinstance(p["house"], int)
        assert 1 <= p["house"] <= 12


def test_houses_block_is_twelve_consecutive_rashis(body):
    houses = body["houses"]
    assert len(houses) == 12
    asc_rashi = body["ascendant"]["rashi"]["number"]
    for i, h in enumerate(houses):
        assert h["house"] == i + 1
        assert h["rashi"]["number"] == ((asc_rashi - 1 + i) % 12) + 1


# --- Identities the consumer asserts ---------------------------------------
def test_rashi_and_nakshatra_identities_hold_on_emitted_longitudes(body):
    """rashi == floor(lon/30)+1 and nakshatra == floor(lon/13.333)+1, on the
    numbers exactly as serialised."""
    subjects = body["planets"] + [body["ascendant"]]
    for s in subjects:
        lon = s["longitude_sidereal"]
        assert s["rashi"]["number"] == int(lon // 30.0) + 1
        assert s["nakshatra"]["number"] == int(lon // NAK_ARC) + 1
        assert 1 <= s["nakshatra"]["pada"] <= 4
        assert s["degree"] == pytest.approx(lon % 30.0, abs=1e-6)
        assert 0.0 <= lon < 360.0


def test_house_is_whole_sign_from_ascendant(body):
    asc_rashi = body["ascendant"]["rashi"]["number"]
    for p in body["planets"]:
        assert p["house"] == ((p["rashi"]["number"] - asc_rashi) % 12) + 1


def test_ketu_is_exactly_opposite_rahu(body):
    by = {p["name"]: p for p in body["planets"]}
    delta = (by["Ketu"]["longitude_sidereal"] - by["Rahu"]["longitude_sidereal"]) % 360
    assert delta == pytest.approx(180.0, abs=1e-6)
    assert (by["Ketu"]["house"] - by["Rahu"]["house"]) % 12 == 6


def test_luminaries_and_nodes_never_retrograde(body):
    for p in body["planets"]:
        if p["name"] in {"Sun", "Moon", "Rahu", "Ketu"}:
            assert p["retrograde"] is False


def test_retrograde_matches_sign_of_speed(body):
    for p in body["planets"]:
        if p["name"] not in {"Sun", "Moon", "Rahu", "Ketu"}:
            assert p["retrograde"] == (p["speed_deg_per_day"] < 0)


def test_known_retrogrades_for_this_birth(body):
    """Mars, Mercury and Saturn were retrograde on 1984-04-24."""
    by = {p["name"]: p for p in body["planets"]}
    assert by["Mars"]["retrograde"] is True
    assert by["Mercury"]["retrograde"] is True
    assert by["Saturn"]["retrograde"] is True
    assert by["Jupiter"]["retrograde"] is False


# --- Agreement with /v1/nakshatra-at ---------------------------------------
def test_moon_agrees_with_nakshatra_at_endpoint(client, body):
    r = client.get("/v1/nakshatra-at", params=BIRTH)
    assert r.status_code == 200
    moon_ep = r.json()
    moon_chart = next(p for p in body["planets"] if p["name"] == "Moon")

    assert moon_chart["longitude_sidereal"] == moon_ep["moon_longitude_sidereal"]
    assert moon_chart["nakshatra"] == moon_ep["nakshatra"]
    assert moon_chart["rashi"] == moon_ep["moon_rashi"]
    assert body["instant"] == moon_ep["instant"]


# --- Navamsa ---------------------------------------------------------------
def test_navamsa_shape_and_d9_rule(body):
    nav = body["navamsa"]
    assert len(nav["planets"]) == 9
    assert len(nav["houses"]) == 12
    d1 = {p["name"]: p for p in body["planets"]}
    nav_asc = nav["ascendant"]["rashi"]["number"]
    for p in nav["planets"]:
        expected = ((d1[p["name"]]["longitude_sidereal"] * 9) % 360)
        assert p["longitude_sidereal"] == pytest.approx(expected, abs=1e-6)
        assert p["rashi"]["number"] == int(p["longitude_sidereal"] // 30) + 1
        assert p["house"] == ((p["rashi"]["number"] - nav_asc) % 12) + 1


def test_navamsa_of_movable_sign_starts_from_itself(body):
    """Classical cross-check of the *9 rule: a graha in the first navamsa of a
    movable sign (Mesha) must land in that same sign in D9."""
    from app.jyotish.chart import _navamsa_longitude
    # 1 degree into Mesha -> first navamsa -> Mesha.
    assert int(_navamsa_longitude(1.0) // 30) + 1 == 1
    # 1 degree into Karka (90) -> movable -> Karka.
    assert int(_navamsa_longitude(91.0) // 30) + 1 == 4


# --- Vimshottari dasha -----------------------------------------------------
def test_dasha_lord_is_birth_nakshatra_lord(body):
    """Moon in Dhanishta -> Mars mahadasha at birth."""
    moon = next(p for p in body["planets"] if p["name"] == "Moon")
    assert moon["nakshatra"]["name"] == "Dhanishta"
    assert body["dashas"]["vimshottari"][0]["lord"] == "Mars"
    assert body["dashas"]["balance_at_birth"]["lord"] == "Mars"


def test_dasha_periods_are_contiguous_and_start_at_birth(body):
    periods = body["dashas"]["vimshottari"]
    assert periods[0]["start"] == body["instant"]
    for a, b in zip(periods, periods[1:]):
        assert a["end"] == b["start"], "gap or overlap between mahadashas"


def test_dasha_covers_today(body):
    """The consumer selects the current period by comparing now() to the
    bounds, so the tree must actually span the present."""
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    periods = body["dashas"]["vimshottari"]
    current = [p for p in periods
               if datetime.fromisoformat(p["start"]) <= now < datetime.fromisoformat(p["end"])]
    assert len(current) == 1, "exactly one mahadasha must contain the present"
    assert current[0]["children"], "the current mahadasha must carry antardashas"


def test_dasha_iso_strings_share_one_offset_so_they_sort(body):
    stamps = []
    for m in body["dashas"]["vimshottari"]:
        stamps += [m["start"], m["end"]]
        for a in m["children"]:
            stamps += [a["start"], a["end"]]
    assert all(s.endswith("+05:30") for s in stamps)
    starts = [m["start"] for m in body["dashas"]["vimshottari"]]
    assert starts == sorted(starts), "ISO strings must sort lexicographically"


def test_antardashas_tile_their_mahadasha(body):
    for m in body["dashas"]["vimshottari"]:
        kids = m["children"]
        if not kids:
            continue
        assert kids[0]["start"] == m["start"]
        assert kids[-1]["end"] == m["end"]
        for a, b in zip(kids, kids[1:]):
            assert a["end"] == b["start"]


def test_first_mahadasha_is_truncated_to_the_balance(body):
    """Mars' full period is 7 years; this native was born partway through, so
    the first mahadasha must be shorter and must equal the reported balance."""
    first = body["dashas"]["vimshottari"][0]
    span = datetime.fromisoformat(first["end"]) - datetime.fromisoformat(first["start"])
    full = timedelta(days=dasha_mod.YEARS["Mars"] * dasha_mod.YEAR_DAYS)
    assert span < full

    # balance_at_birth.total_years is rounded to 6 decimal places, which is
    # worth up to 5e-7 yr ~= 16 s of slack against the full-precision span.
    balance_years = body["dashas"]["balance_at_birth"]["total_years"]
    expected = timedelta(days=balance_years * dasha_mod.YEAR_DAYS)
    assert span.total_seconds() == pytest.approx(expected.total_seconds(), abs=30)


def test_full_cycle_is_120_years(body):
    """Nine full mahadashas after the truncated first sum to 120 years."""
    assert sum(dasha_mod.YEARS.values()) == dasha_mod.TOTAL_YEARS
    periods = body["dashas"]["vimshottari"]
    lords = [p["lord"] for p in periods]
    # Lords cycle in the canonical order without repeats inside one turn.
    start = dasha_mod.ORDER.index(lords[0])
    for i, lord in enumerate(lords):
        assert lord == dasha_mod.ORDER[(start + i) % 9]


def test_include_antardashas_false_omits_children(client):
    r = client.get("/v1/chart", params=BIRTH | {"include_antardashas": "false"})
    assert r.status_code == 200
    assert all(m["children"] == [] for m in r.json()["dashas"]["vimshottari"])


# --- Doshas ----------------------------------------------------------------
def test_manglik_for_this_birth(body):
    """Mars sits in Vrishchika, the lagna rashi -> house 1 -> manglik."""
    m = body["doshas"]["manglik"]
    assert m["mars_house_from_lagna"] == 1
    assert m["value"] is True
    assert m["reference_houses"] == [1, 2, 4, 7, 8, 12]


def test_manglik_agrees_with_mars_house(body):
    m = body["doshas"]["manglik"]
    mars = next(p for p in body["planets"] if p["name"] == "Mars")
    assert m["mars_house_from_lagna"] == mars["house"]
    assert m["value"] == (mars["house"] in (1, 2, 4, 7, 8, 12))
    assert m["from_lagna_strict"] == (mars["house"] in (1, 4, 7, 8, 12))


def test_kaal_sarp_shape(body):
    k = body["doshas"]["kaal_sarp"]
    assert isinstance(k["value"], bool)
    assert k["side"] in (None, "rahu_to_ketu", "ketu_to_rahu")
    assert (k["side"] is not None) == k["value"]


def test_sade_sati_is_time_dependent_and_says_so(body):
    s = body["doshas"]["sade_sati"]
    assert isinstance(s["value"], bool)
    assert s["evaluated_at"]
    assert s["value"] == (s["saturn_house_from_moon"] in (12, 1, 2))


def test_kaal_sarp_true_when_all_grahas_one_side():
    """Synthetic: pack all seven grahas into the Rahu->Ketu arc."""
    from app.jyotish.doshas import kaal_sarp
    lons = {n: 10.0 + i for i, n in enumerate(
        ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"))}
    assert kaal_sarp(lons, rahu_longitude=0.0)["value"] is True
    # Move one graha across the axis -> broken.
    lons["Saturn"] = 200.0
    assert kaal_sarp(lons, rahu_longitude=0.0)["value"] is False


# --- Parameter handling ----------------------------------------------------
def test_time_is_required(client):
    r = client.get("/v1/chart", params={k: v for k, v in BIRTH.items() if k != "time"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_invalid_timezone_is_422_json_not_500(client):
    for bad in ("+05:30", "IST", "Not/AZone"):
        r = client.get("/v1/chart", params=BIRTH | {"tz": bad})
        assert r.status_code == 422, f"{bad} -> {r.status_code}"
        assert r.json()["error"]["code"] == "invalid_timezone"


def test_nakshatra_at_also_returns_422_for_bad_timezone(client):
    """The fix applies to the pre-existing endpoint too."""
    r = client.get("/v1/nakshatra-at", params=BIRTH | {"tz": "+05:30"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_timezone"


def test_timezone_derived_from_coordinates_when_omitted(client):
    r = client.get("/v1/chart", params={k: v for k, v in BIRTH.items() if k != "tz"})
    assert r.status_code == 200
    assert r.json()["coordinates"]["timezone"] == "Asia/Kolkata"


def test_datetime_in_date_is_rejected(client):
    r = client.get("/v1/chart", params=BIRTH | {"date": "1984-04-24T21:06:00"})
    assert r.status_code == 422


def test_out_of_range_coordinates(client):
    assert client.get("/v1/chart", params=BIRTH | {"lat": 91}).status_code == 422
    assert client.get("/v1/chart", params=BIRTH | {"lon": -181}).status_code == 422


def test_date_is_interpreted_in_tz_not_utc(client):
    """Same wall clock, different zone -> different instant, different chart."""
    a = client.get("/v1/chart", params=BIRTH | {"tz": "Asia/Kolkata"}).json()
    b = client.get("/v1/chart", params=BIRTH | {"tz": "UTC"}).json()
    assert a["instant"] == "1984-04-24T21:06:00+05:30"
    assert b["instant"] == "1984-04-24T21:06:00+00:00"
    assert a["ascendant"]["longitude_sidereal"] != b["ascendant"]["longitude_sidereal"]


def test_southern_hemisphere_chart_is_complete(client):
    r = client.get("/v1/chart", params={
        "date": "1985-06-15", "time": "09:00:00", "tz": "Australia/Sydney",
        "lat": -33.8688, "lon": 151.2093})
    assert r.status_code == 200
    b = r.json()
    assert len(b["planets"]) == 9
    assert all(1 <= p["house"] <= 12 for p in b["planets"])


def test_high_latitude_chart_still_has_houses(client):
    """No sunrise dependency here, so polar births are ordinary."""
    r = client.get("/v1/chart", params={
        "date": "1985-06-21", "time": "12:00:00", "tz": "Europe/Oslo",
        "lat": 69.6496, "lon": 18.9560})
    assert r.status_code == 200
    assert all(1 <= p["house"] <= 12 for p in r.json()["planets"])


def test_date_outside_ephemeris_range_is_422_json(client):
    """Moshier spans roughly 3001 BCE..3000 CE; past it we must not 500."""
    for bad_year in ("3200", "9998"):
        r = client.get("/v1/chart", params=BIRTH | {"date": f"{bad_year}-04-24"})
        assert r.status_code == 422, f"{bad_year} -> {r.status_code}"
        assert r.json()["error"]["code"] == "ephemeris_range"


def test_nakshatra_at_range_error_is_also_json(client):
    r = client.get("/v1/nakshatra-at", params=BIRTH | {"date": "3500-04-24"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ephemeris_range"


def test_first_century_birth_does_not_overflow_the_dasha_wind_back(client):
    """The first mahadasha's notional start precedes birth; for a year-1 birth
    that is before datetime.min, which must not surface as a 500."""
    r = client.get("/v1/chart", params=BIRTH | {"date": "0001-04-24"})
    assert r.status_code == 200
    periods = r.json()["dashas"]["vimshottari"]
    assert periods
    assert periods[0]["start"] == r.json()["instant"]


def test_1980s_dst_offset_is_applied(client):
    r = client.get("/v1/chart", params={
        "date": "1985-07-04", "time": "12:00:00", "tz": "America/New_York",
        "lat": 40.7143, "lon": -74.006})
    assert r.status_code == 200
    assert r.json()["instant"] == "1985-07-04T12:00:00-04:00"
