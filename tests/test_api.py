from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, sources
from app.config import settings


def _fixture_aq():
    start = datetime.now(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(72)]
    pm = [40.0 + (i % 24) * 3 for i in range(72)]
    return {"utc_offset_seconds": 0, "hourly": {"time": times, "pm2_5": pm, "pm10": pm, "us_aqi": pm}}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "none")
    monkeypatch.setattr(sources, "fetch_air_quality", lambda lat, lon: (_fixture_aq(), False))
    monkeypatch.setattr(sources, "fetch_weather", lambda lat, lon: (_ for _ in ()).throw(sources.SourceError("down")))
    monkeypatch.setattr(
        sources,
        "fetch_parks",
        lambda lat, lon, r=3000: ([{"name": "Test Park", "kind": "park", "lat": lat + 0.005, "lon": lon, "osm_url": "x"}], False),
    )
    return TestClient(main.app)


def test_plan_degrades_gracefully_without_weather(client):
    r = client.get("/api/plan", params={"lat": 28.61, "lon": 77.21, "name": "Test"})
    assert r.status_code == 200
    body = r.json()
    assert body["hours"] and body["current"]["verdict"] in {"go", "caution", "avoid"}
    assert any("Weather" in w for w in body["warnings"])
    assert body["parks"][0]["name"] == "Test Park"


def test_explain_uses_template_when_llm_disabled(client):
    r = client.get("/api/explain", params={"lat": 28.61, "lon": 77.21})
    assert r.status_code == 200
    assert r.json()["source"] == "template"
    assert r.json()["text"]


def test_agent_uses_planning_engine_and_returns_plan_context(client, monkeypatch):
    captured = {}

    def fake_run_agent(message, plan, lang):
        captured.update(message=message, plan=plan, lang=lang)
        return {"answer": "A grounded answer.", "tools_used": ["get_outdoor_plan"]}

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
    assert body["verdict"] in {"go", "caution", "avoid"}
    assert isinstance(body["pm25"], (int, float))
    assert captured["message"] == "Is a walk a good idea?"
    assert captured["lang"] == "hi"
    assert captured["plan"]["profile"] == "sensitive"
    assert captured["plan"]["intensity"] == "vigorous"


def test_bad_params_are_rejected(client):
    assert client.get("/api/plan", params={"lat": 200, "lon": 0}).status_code == 422
    assert client.get("/api/plan", params={"lat": 1, "lon": 1, "profile": "x"}).status_code == 422
    assert client.post(
        "/api/agent",
        json={"message": " ", "lat": 0, "lon": 0},
    ).status_code == 422


def test_upstream_failure_returns_502(monkeypatch):
    monkeypatch.setattr(sources, "fetch_air_quality", lambda lat, lon: (_ for _ in ()).throw(sources.SourceError("boom")))
    r = TestClient(main.app).get("/api/plan", params={"lat": 1, "lon": 1})
    assert r.status_code == 502
