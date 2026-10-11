from app import explain
from app.config import settings


FACTS = {
    "place": "Delhi",
    "now": {
        "pm25": 150.0,
        "band": "Very poor",
        "verdict": "avoid",
    },
    "best_window": None,
    "parks": [],
}


def test_disabled_llm_uses_template(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "none")

    def unexpected_llm_call(system_prompt, user_prompt):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr(explain, "_chat", unexpected_llm_call)

    result = explain.explain(FACTS)

    assert result["source"] == "template"
    assert result["text"]


def test_contradictory_advice_is_replaced(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(
        explain,
        "_chat",
        lambda system_prompt, user_prompt: (
            "The air is very poor, but it is safe to go out."
        ),
    )

    result = explain.explain(FACTS)

    assert result["source"] == "template"


def test_medical_claim_is_replaced(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(
        explain,
        "_chat",
        lambda system_prompt, user_prompt: (
            "Staying inside will cure your cough."
        ),
    )

    result = explain.explain(FACTS)

    assert result["source"] == "template"


def test_valid_llm_explanation_is_used(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(
        explain,
        "_chat",
        lambda system_prompt, user_prompt: (
            "Air quality is very poor, so consider staying indoors today."
        ),
    )

    result = explain.explain(FACTS)

    assert result["source"].startswith("llm:")
    assert result["text"]


def test_llm_failure_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    def fail_llm(system_prompt, user_prompt):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(explain, "_chat", fail_llm)

    result = explain.explain(FACTS)

    assert result["source"] == "template"
    assert result["text"]