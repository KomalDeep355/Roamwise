
import os


def get_partner_status():
    """Report configured integrations without exposing API keys."""

    ollama_model = os.getenv("LLM_MODEL", "gemma3:4b")
    llm_provider = os.getenv("LLM_PROVIDER", "ollama")

    return {
        "gemma": {
            "name": "Gemma",
            "category": "AI explanations",
            "configured": (
                llm_provider == "ollama"
                and bool(ollama_model)
            ),
            "model": ollama_model,
            "note": (
                "Configuration detected; verify the model "
                "is running before claiming live integration."
            ),
        },
        "tabpfn": {
            "name": "TabPFN",
            "category": "Tabular forecasting",
            "configured": False,
            "note": (
                "Activate only after training and evaluating "
                "the model against a baseline."
            ),
        },
        "elevenlabs": {
            "name": "ElevenLabs",
            "category": "Voice",
            "configured": bool(
                os.getenv("ELEVENLABS_API_KEY")
            ),
            "note": (
                "An API key alone does not prove that "
                "voice functionality is working."
            ),
        },
        "render": {
            "name": "Render",
            "category": "Deployment",
            "configured": bool(
                os.getenv("RENDER")
            ),
            "note": (
                "Verify deployment through the live service "
                "and its health endpoint."
            ),
        },
    }
