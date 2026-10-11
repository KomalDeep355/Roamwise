"""LLM explainer. The model receives the engine's verdict as fixed facts and writes a short,
plain-language plan. If the model is unavailable or its text fails a basic check, a
deterministic template is returned instead, and the response says which source was used."""
from __future__ import annotations

import json
import re

import httpx

from .config import settings

SYSTEM_PROMPT = (
    "You turn outdoor air-quality facts into a short plan for someone deciding whether to go "
    "outside. Rules: use only the facts provided; never change, soften or contradict the verdict; "
    "write at most 4 short sentences in plain language; mention the best time window and the "
    "nearest park if they are provided; if the verdict is avoid, suggest staying in or an indoor "
    "alternative; do not give medical advice or make claims about diseases."
)

LANG_HINT = {
    "en": "Write in English.",
    "hi": "Write in Hindi (Devanagari script).",
    "hinglish": "Write in Hinglish: Hindi in Roman script mixed with simple English.",
}

BANNED = re.compile(r"\b(cure[sd]?|diagnos\w*|guarantee\w*|100% safe|prevents? (cancer|asthma|disease))\b", re.I)
CONTRADICTS_AVOID = re.compile(r"\b(safe to go|good time to go|go ahead|perfectly fine)\b", re.I)

VERDICT_TEXT = {
    "go": "Air quality is fine for this activity right now.",
    "caution": "Air quality is middling. Keep it easy and shorter than usual.",
    "avoid": "Air quality is poor for this activity right now. Staying in is the better choice.",
    "unknown": "There is no air-quality reading for this hour.",
}


def _fmt_range(w: dict) -> str:
    return f"{w['start'][11:16]} to {w['end'][11:16]}"


def template_text(facts: dict) -> str:
    now = facts["now"]
    parts = [VERDICT_TEXT.get(now["verdict"], VERDICT_TEXT["unknown"])]
    if now.get("pm25") is not None:
        parts.append(f"PM2.5 is {now['pm25']:.0f} µg/m³ ({now['band'].lower()}).")
    bw = facts.get("best_window")
    if bw:
        label = "Best window" if bw["level"] == "go" else "Least bad window"
        parts.append(f"{label}: {_fmt_range(bw)} (average PM2.5 {bw['mean_pm25']:.0f}).")
    else:
        parts.append("No daylight window in the forecast looks acceptable. Consider an indoor alternative.")
    parks = facts.get("parks") or []
    if parks and bw:
        parts.append(f"Nearest park: {parks[0]['name']}, about {parks[0]['walk_min']} minutes on foot.")
    return " ".join(parts)


def _chat(system: str, user: str) -> str:
    provider = settings.llm_provider
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if provider == "ollama":
        r = httpx.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": settings.llm_model,
                "stream": False,
                "messages": messages,
                "options": {"temperature": 0.3},
            },
            timeout=settings.llm_timeout,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]
    if provider == "openai_compat":
        r = httpx.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={"model": settings.llm_model, "messages": messages, "temperature": 0.3, "max_tokens": 400},
            timeout=settings.llm_timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise RuntimeError("LLM disabled")


def _acceptable(text: str, verdict: str) -> bool:
    if not text or len(text) > 900:
        return False
    if BANNED.search(text):
        return False
    if verdict == "avoid" and CONTRADICTS_AVOID.search(text):
        return False
    return True


def explain(facts: dict, lang: str = "en") -> dict:
    fallback = {"text": template_text(facts), "source": "template"}
    if settings.llm_provider == "none":
        return fallback
    user = f"{LANG_HINT.get(lang, LANG_HINT['en'])}\nFacts (JSON):\n{json.dumps(facts, ensure_ascii=False)}"
    try:
        text = _chat(SYSTEM_PROMPT, user).strip()
    except Exception:  # network, timeout, bad payload: always fall back
        return fallback
    if not _acceptable(text, facts["now"]["verdict"]):
        return fallback
    return {"text": text, "source": f"llm:{settings.llm_model}"}
