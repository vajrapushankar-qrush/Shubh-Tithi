"""API smoke tests using the test cities (no full 150k seed).

We patch the seed step so the app uses the small fixture DB prepared in
conftest, then exercise every endpoint.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def client(monkeypatch_session=None):
    from fastapi.testclient import TestClient

    import app.main as main

    # Avoid the heavy full seed; conftest already inserted the test cities.
    original = main.seed_cities
    main.seed_cities = lambda *a, **k: 4  # type: ignore
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        main.seed_cities = original


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_cities_search(client):
    r = client.get("/v1/cities", params={"q": "lond"})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["results"]]
    assert "London" in names


def test_panchang_by_city_id(client):
    r = client.get("/v1/panchang", params={"city_id": 1003, "date": "2026-08-15"})
    assert r.status_code == 200
    body = r.json()
    assert body["vara"]["english"] == "Saturday"
    assert body["tithi"][0]["name"] == "Tritiya"


def test_panchang_by_latlon(client):
    r = client.get("/v1/panchang", params={
        "lat": 12.9719, "lon": 77.5937, "tz": "Asia/Kolkata", "date": "2026-08-15"})
    assert r.status_code == 200
    assert r.json()["sun"]["sunrise"] is not None


def test_range_cap_returns_422(client):
    r = client.get("/v1/panchang/range", params={
        "city_id": 1003, "start": "2020-01-01", "end": "2026-01-01"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "range_too_large"


def test_nakshatra_at_with_and_without_time(client):
    r = client.get("/v1/nakshatra-at", params={
        "date": "1990-04-21", "time": "14:35:00", "lat": 17.0, "lon": 82.2})
    assert r.status_code == 200
    assert "nakshatra" in r.json() and "time_assumed" not in r.json()

    r2 = client.get("/v1/nakshatra-at", params={
        "date": "1990-04-21", "lat": 17.0, "lon": 82.2})
    assert r2.status_code == 200
    assert r2.json()["time_assumed"] == "sunrise"


def test_city_not_found(client):
    r = client.get("/v1/panchang", params={"city_id": 99999999, "date": "2026-08-15"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "city_not_found"
