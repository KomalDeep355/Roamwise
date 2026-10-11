from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, sources
from app.config import settings


def make_air_quality():
    start = (
        datetime.now(timezone.utc)
        .replace(tzinfo=None, minute=0, second=0, microsecond=0)
    )
    times = [
        (start + timedelta(hours=i)).isoformat(timespec="minutes")
        for i in range(72)
    ]
    pm25 = [40.0 + (i % 24) * 3 for i in range(72)]

    return {
        "utc_offset_seconds": 0,
        "hourly": {
            "time": times,
            "pm2_5": pm25,
            "pm10": pm25,
            "us_aqi": pm25,
        },
    }


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "none")

    monkeypatch.setattr(
        sources,
        "fetch_air_quality",
        lambda lat, lon: (make_air_quality(), False),
    )

    monkeypatch.setattr(
        sources,
        "fetch_weather",
        lambda lat, lon: (
            (_ for _ in ()).throw(sources.SourceError("weather unavailable"))
        ),
    )

    monkeypatch.setattr(
        sources,
        "fetch_parks",
        lambda lat, lon, r=3000: (
            [
                {
                    "name": "Test Park",
                    "kind": "park",
                    "lat": lat + 0.005,
                    "lon": lon,
                    "osm_url": "https://example.com/park",
                }
            ],
            False,
        ),
    )

    return TestClient(main.app)


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_plan_returns_data_when_weather_is_unavailable(client):
    response = client.get(
        "/api/plan",
        params={
            "lat": 28.61,
            "lon": 77.21,
            "name": "Test",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["location"]["name"] == "Test"
    assert body["hours"]
    assert body["current"]["verdict"] in {
        "go", "caution", "avoid", "unknown"
    }
    assert body["thresholds"]
    assert body["parks"][0]["name"] == "Test Park"
    assert any("Weather" in warning for warning in body["warnings"])


def test_plan_includes_requested_profile_and_intensity(client):
    response = client.get(
        "/api/plan",
        params={
            "lat": 28.61,
            "lon": 77.21,
            "profile": "sensitive",
            "intensity": "vigorous",
            "horizon": 12,
            "daylight_only": False,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["profile"] == "sensitive"
    assert body["intensity"] == "vigorous"
    assert body["daylight_only"] is False
    assert len(body["hours"]) <= 12


def test_explain_uses_template_when_llm_is_disabled(client):
    response = client.get(
        "/api/explain",
        params={"lat": 28.61, "lon": 77.21},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["source"] == "template"
    assert body["text"]


def test_agent_returns_answer_and_plan_context(client, monkeypatch):
    captured = {}

    def fake_run_agent(message, plan, lang):
        captured.update(
            message=message,
            plan=plan,
            lang=lang,
        )
        return {
            "answer": "A grounded answer.",
            "tools_used": ["get_outdoor_plan"],
        }

    monkeypatch.setattr(main, "run_agent", fake_run_agent)

    response = client.post(
        "/api/agent",
        json={
            "message": "  Is a walk a good idea?  ",
            "lat": 28.61,
            "lon": 77.21,
            "name": "Test",
            "profile": "sensitive",
            "intensity": "vigorous",
            "horizon": 12,
            "daylight_only": False,
            "lang": "hi",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == "A grounded answer."
    assert body["location"]["name"] == "Test"
    assert body["verdict"] in {"go", "caution", "avoid", "unknown"}
    assert isinstance(body["pm25"], (int, float))

    assert captured["message"] == "Is a walk a good idea?"
    assert captured["lang"] == "hi"
    assert captured["plan"]["profile"] == "sensitive"
    assert captured["plan"]["intensity"] == "vigorous"


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 200, "lon": 0},
        {"lat": 0, "lon": 200},
        {"lat": 1, "lon": 1, "profile": "invalid"},
        {"lat": 1, "lon": 1, "intensity": "invalid"},
        {"lat": 1, "lon": 1, "horizon": 2},
        {"lat": 1, "lon": 1, "horizon": 100},
    ],
)
def test_invalid_plan_parameters_return_422(client, params):
    response = client.get("/api/plan", params=params)

    assert response.status_code == 422


def test_agent_rejects_empty_message(client):
    response = client.post(
        "/api/agent",
        json={"message": " ", "lat": 0, "lon": 0},
    )

    assert response.status_code == 422


def test_geocode_rejects_too_short_query(client):
    response = client.get("/api/geocode", params={"q": "a"})

    assert response.status_code == 422


def test_geocode_returns_results(monkeypatch, client):
    monkeypatch.setattr(
        sources,
        "geocode",
        lambda query: (
            [
                {
                    "name": "New Delhi",
                    "admin1": "Delhi",
                    "country": "India",
                    "lat": 28.61,
                    "lon": 77.21,
                }
            ],
            False,
        ),
    )

    response = client.get(
        "/api/geocode",
        params={"q": "New Delhi"},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["name"] == "New Delhi"


def test_air_quality_failure_returns_502(monkeypatch):
    monkeypatch.setattr(
        sources,
        "fetch_air_quality",
        lambda lat, lon: (
            (_ for _ in ()).throw(sources.SourceError("source unavailable"))
        ),
    )

    response = TestClient(main.app).get(
        "/api/plan",
        params={"lat": 28.61, "lon": 77.21},
    )

    assert response.status_code == 502
