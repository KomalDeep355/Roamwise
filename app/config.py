import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.llm_provider = os.getenv("LLM_PROVIDER", "ollama")  # ollama | openai_compat | none
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.llm_model = os.getenv("LLM_MODEL", "gemma3:4b")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.llm_timeout = float(os.getenv("LLM_TIMEOUT", "60"))
        self.db_path = os.getenv("DB_PATH", "cache.db")


settings = Settings()
