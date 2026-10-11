
from __future__ import annotations

import json
import re
from typing import Literal

from .config import settings
from .explain import _chat
from .main_helpers import build_plan, make_facts


SYSTEM_PROMPT = """
You are Roamwise, a friendly outdoor-planning assistant.

You receive:
1. A user's question.
2. Structured facts returned by Roamwise's Python tools.

Rules:
- Use only the supplied facts for claims about current air quality, forecast
  readings, verdicts, times, and nearby parks.
- Never change or contradict the supplied air-quality verdict.
- Never invent PM2.5 values, AQI values, park names, opening hours, routes,
  distances, or travel times.
- Answer the user's actual question in plain, friendly language.
- When recommending a time, use a time window from the supplied facts.
- When the verdict is "avoid", recommend considering an indoor alternative.
- When the verdict is "caution", suggest reducing duration or intensity.
- General precautions are allowed, but do not diagnose, prescribe treatment,
  or guarantee that an outdoor activity is safe.
- Do not claim that a park is cleaner than the surrounding area. The air-quality
  reading represents a regional model grid, not an individual park.
- If information is missing, say so clearly.
- Keep the answer concise: around 3 to 6 short sentences.
"""


LANGUAGE_HINTS = {
    "en": "Answer in English.",
    "hi": "Answer in Hindi using Devanagari script.",
    "hinglish": "Answer in Hinglish, using Hindi in Roman script mixed with simple English.",
}

BANNED = re.compile(
    r"\b(cure[sd]?|diagnos\w*|guarantee\w*|100%\s*safe|"
    r"prevents?\s+(cancer|asthma|disease))\b",
    re.IGNORECASE,
)

CONTRADICTS_AVOID = re.compile(
    r"\b(safe to go|good time to go|go ahead|perfectly fine)\b",
    re.IGNORECASE,
)


def choose_tools(message: str) -> list[str]:
    """
    Select the Roamwise tools relevant to a user's question.

    The forecast tool supplies the rule-based verdict, hourly forecast,
    weather context and ranked nearby parks.
    """
    text = message.lower()
    selected = ["get_outdoor_plan"]

    park_words = (
        "park", "parks", "green space", "garden", "dog walk",
        "dog run", "nearby place",
    )
    precaution_words = (
        "mask", "precaution", "protect", "poor air", "bad air",
        "sensitive", "lung", "asthma", "child", "children",
        "alternative", "instead", "what should i do",
    )

    if any(word in text for word in park_words):
        selected.append("find_nearby_parks")

    if any(word in text for word in precaution_words):
        selected.append("suggest_precautions")

    return selected


def get_outdoor_plan(plan: dict) -> dict:
    """Tool: return the existing engine's forecast and rule-based verdict."""
    return {
        "location": plan["location"],
        "current": plan["current"],
        "best_window": plan["best_window"],
        "hours": plan["hours"][:24],
        "thresholds": plan["thresholds"],
        "profile": plan["profile"],
        "intensity": plan["intensity"],
        "daylight_only": plan["daylight_only"],
        "warnings": plan["warnings"],
        "air_quality_resolution_note": plan["air_quality_resolution_note"],
    }


def find_nearby_parks(plan: dict) -> list[dict]:
    """Tool: return only parks actually found by the existing data source."""
    return [
        {
            "name": park["name"],
            "walk_min": park["walk_min"],
            "distance_m": park.get("distance_m"),
        }
        for park in plan["parks"][:5]
    ]


def suggest_precautions(plan: dict) -> list[str]:
    """Tool: provide general precautions based on the rule-based verdict."""
    verdict = plan["current"]["verdict"]
    profile = plan["profile"]
    intensity = plan["intensity"]

    tips = []

    if verdict == "avoid":
        tips.extend([
            "Consider an indoor activity while pollution is elevated.",
            "If going outside is necessary, reduce exertion and time outdoors.",
            "A well-fitting N95/FFP2 respirator can reduce exposure to particles, "
            "but does not make every outdoor activity safe.",
        ])
    elif verdict == "caution":
        tips.extend([
            "Consider a shorter, less intense outdoor activity.",
            "Compare forecast hours and reconsider the plan if a lower-pollution "
            "window is available.",
        ])
    elif verdict == "go":
        tips.extend([
            "Check the latest local air-quality information before leaving.",
            "Conditions can change, so reassess if you will be outside for a long time.",
        ])
    else:
        tips.append(
            "The current air-quality reading is unavailable. Check a trusted "
            "local source before strenuous outdoor activity."
        )

    if profile == "sensitive":
        tips.append(
            "Follow your clinician's guidance and local health alerts if you "
            "have a heart or lung condition or are otherwise sensitive to pollution."
        )

    if intensity == "vigorous":
        tips.append(
            "Consider lowering exercise intensity when particle pollution is elevated."
        )

    return tips


def _fallback_answer(message: str, tool_data: dict) -> str:
    """Return a useful response even when the language model is unavailable."""
    plan = tool_data["outdoor_plan"]
    current = plan["current"]
    verdict = current["verdict"]
    pm25 = current.get("pm25")

    if verdict == "go":
        answer = "The current rule-based assessment is favourable for your selected activity."
    elif verdict == "caution":
        answer = (
            "The current assessment calls for caution. Consider a shorter, "
            "less intense outing."
        )
    elif verdict == "avoid":
        answer = (
            "The current assessment recommends avoiding this outdoor activity "
            "for now. Consider an indoor alternative."
        )
    else:
        answer = (
            "There is no current air-quality reading available, so I can't "
            "reliably assess outdoor conditions."
        )

    if pm25 is not None:
        answer += f" The forecast's current PM2.5 reading is {pm25:.0f} µg/m³."

    window = plan.get("best_window")
    if window:
        answer += (
            f" The suggested forecast window is {window['start'][11:16]} "
            f"to {window['end'][11:16]}."
        )

    parks = tool_data.get("nearby_parks", [])
    if parks:
        answer += (
            f" One nearby option is {parks[0]['name']}, "
            f"about {parks[0]['walk_min']} minutes on foot."
        )

    tips = tool_data.get("precautions", [])
    if tips:
        answer += " Practical tip: " + tips[0]

    return answer


def run_agent(
    message: str,
    plan: dict,
    lang: Literal["en", "hi", "hinglish"] = "en",
) -> dict:
    """Run selected tools and produce a grounded answer."""
    selected = choose_tools(message)

    # The forecast tool is always run: the answer must be grounded in data.
    tool_data = {
        "outdoor_plan": get_outdoor_plan(plan),
        "tools_used": ["get_outdoor_plan"],
    }

    if "find_nearby_parks" in selected:
        tool_data["nearby_parks"] = find_nearby_parks(plan)
        tool_data["tools_used"].append("find_nearby_parks")

    if "suggest_precautions" in selected:
        tool_data["precautions"] = suggest_precautions(plan)
        tool_data["tools_used"].append("suggest_precautions")

    fallback = _fallback_answer(message, tool_data)

    if settings.llm_provider == "none":
        return {
            "answer": fallback,
            "source": "rules",
            "tools_used": tool_data["tools_used"],
        }

    user_prompt = (
        f"{LANGUAGE_HINTS.get(lang, LANGUAGE_HINTS['en'])}\n\n"
        f"User question:\n{message}\n\n"
        f"Tools and their results (JSON):\n"
        f"{json.dumps(tool_data, ensure_ascii=False, default=str)}"
    )

    try:
        answer = _chat(SYSTEM_PROMPT, user_prompt).strip()
        verdict = plan["current"]["verdict"]

        if (
            not answer
            or len(answer) > 1800
            or BANNED.search(answer)
            or (verdict == "avoid" and CONTRADICTS_AVOID.search(answer))
        ):
            raise ValueError("The model answer did not pass validation.")

        return {
            "answer": answer,
            "source": f"llm:{settings.llm_model}",
            "tools_used": tool_data["tools_used"],
        }

    except Exception:
        return {
            "answer": fallback,
            "source": "rules_fallback",
            "tools_used": tool_data["tools_used"],
        }
