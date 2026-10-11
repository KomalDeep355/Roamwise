from app import explain
from app.config import settings

FACTS = {
    "place": "Delhi",
    "now": {"pm25": 150.0, "band": "Very poor", "verdict": "avoid"},
    "best_window": None,
    "parks": [],
}


def test_llm_text_that_contradicts_verdict_is_replaced(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(explain, "_chat", lambda s, u: "It is safe to go out, go ahead!")
    out = explain.explain(FACTS)
    assert out["source"] == "template"


def test_medical_claims_are_replaced(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(explain, "_chat", lambda s, u: "Staying in will cure your cough.")
    assert explain.explain(FACTS)["source"] == "template"


def test_good_llm_text_is_used(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(explain, "_chat", lambda s, u: "Air is very poor now, so stay in today.")
    out = explain.explain(FACTS)
    assert out["source"].startswith("llm:")


def test_llm_failure_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    def boom(s, u):
        raise RuntimeError("down")

    monkeypatch.setattr(explain, "_chat", boom)
    assert explain.explain(FACTS)["source"] == "template"
