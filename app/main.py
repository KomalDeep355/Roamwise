from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import exposure, sources
from .agent import run_agent
from .explain import explain as explain_facts
from .partner_integrations import get_partner_status

BASE_DIR = Path(__file__).resolve().parent.parent
PARK_RADIUS_M = 3000

app = FastAPI(title="Roamwise", version="0.1.0")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/geocode")
def geocode(q: str = Query(..., min_length=2, max_length=80)):
    try:
        results, _ = sources.geocode(q)
    except sources.SourceError as exc:
        raise HTTPException(502, f"Place search is unavailable right now: {exc}")
    return {"results": results}


def _build_plan(lat, lon, name, profile, intensity, horizon, daylight_only):
    warnings: list[str] = []
    stale = False

    try:
        aq, aq_stale = sources.fetch_air_quality(lat, lon)
    except sources.SourceError as exc:
        raise HTTPException(502, f"Air-quality data is unavailable right now: {exc}")
    stale = stale or aq_stale

    try:
        wx, wx_stale = sources.fetch_weather(lat, lon)
        stale = stale or wx_stale
    except sources.SourceError:
        wx = None
        warnings.append("Weather data is unavailable, so heat, rain and daylight checks are approximate.")

    try:
        raw_parks, parks_stale = sources.fetch_parks(lat, lon, PARK_RADIUS_M)
        stale = stale or parks_stale
    except sources.SourceError:
        raw_parks = []
        warnings.append("Park data is unavailable right now.")

    offset = int(aq.get("utc_offset_seconds", 0))
    now_local = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=offset)

    hours = exposure.build_hours(aq, wx, now_local, horizon, profile, intensity)
    if not hours:
        raise HTTPException(502, "No forecast hours were returned for this location.")

    go_max, caution_max = exposure.thresholds(profile, intensity)
    parks = exposure.rank_parks(raw_parks, lat, lon, PARK_RADIUS_M)
    if stale:
        warnings.append("Some data is from cache because a live source did not respond.")

    return {
        "location": {"lat": lat, "lon": lon, "name": name},
        "now_local": now_local.isoformat(timespec="minutes"),
        "profile": profile,
        "intensity": intensity,
        "daylight_only": daylight_only,
        "thresholds": {"go_max": go_max, "caution_max": caution_max},
        "current": exposure.hour_to_dict(hours[0]),
        "best_window": exposure.best_window(hours, daylight_only),
        "hours": [exposure.hour_to_dict(h) for h in hours],
        "parks": parks,
        "warnings": warnings,
        "air_quality_resolution_note": (
            "Air quality comes from a regional model grid, so it describes the area, not a specific park."
        ),
    }


def _facts(plan: dict) -> dict:
    cur = plan["current"]
    return {
        "place": plan["location"].get("name"),
        "profile": plan["profile"],
        "activity_intensity": plan["intensity"],
        "daylight_only": plan["daylight_only"],
        "now": {"pm25": cur["pm25"], "band": cur["band"], "verdict": cur["verdict"]},
        "best_window": plan["best_window"],
        "parks": [{"name": p["name"], "walk_min": p["walk_min"]} for p in plan["parks"][:3]],
    }


Profile = Literal["general", "sensitive"]
Intensity = Literal["light", "vigorous"]


@app.get("/api/plan")
def plan(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    name: str | None = Query(None, max_length=120),
    profile: Profile = "general",
    intensity: Intensity = "light",
    horizon: int = Query(24, ge=6, le=48),
    daylight_only: bool = True,
):
    return _build_plan(lat, lon, name, profile, intensity, horizon, daylight_only)


@app.get("/api/explain")
def explain(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    name: str | None = Query(None, max_length=120),
    profile: Profile = "general",
    intensity: Intensity = "light",
    horizon: int = Query(24, ge=6, le=48),
    daylight_only: bool = True,
    lang: Literal["en", "hi", "hinglish"] = "en",
):
    p = _build_plan(lat, lon, name, profile, intensity, horizon, daylight_only)
    return explain_facts(_facts(p), lang)


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    name: str | None = Field(None, max_length=120)
    profile: Profile = "general"
    intensity: Intensity = "light"
    horizon: int = Field(24, ge=6, le=48)
    daylight_only: bool = True
    lang: Literal["en", "hi", "hinglish"] = "en"


@app.post("/api/agent")
def agent_endpoint(request: AgentRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(422, "Please enter a question.")

    # Retrieve real data using the existing Roamwise planning engine.
    p = _build_plan(
        lat=request.lat,
        lon=request.lon,
        name=request.name,
        profile=request.profile,
        intensity=request.intensity,
        horizon=request.horizon,
        daylight_only=request.daylight_only,
    )

    # The agent chooses relevant tools and explains their results.
    result = run_agent(message, p, request.lang)

    return {
        **result,
        "location": p["location"],
        "verdict": p["current"]["verdict"],
        "pm25": p["current"]["pm25"],
    }


@app.get("/api/partners")
def partner_status():
    return {"partners": get_partner_status()}


class VoiceRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2500)


@app.post("/api/voice")
async def generate_voice(request: VoiceRequest):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    if not api_key or not voice_id:
        raise HTTPException(
            status_code=503,
            detail="Voice output is not configured. Set the ElevenLabs API key and voice ID.",
        )

    text = request.text.strip()
    if not text:
        raise HTTPException(422, "Text cannot be empty.")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                },
                params={"output_format": "mp3_44100_128"},
            )
            response.raise_for_status()

        return Response(
            content=response.content,
            media_type="audio/mpeg",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Voice generation failed.",
        ) from exc


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
