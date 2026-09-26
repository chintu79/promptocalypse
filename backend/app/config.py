from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    ADMIN_TOKEN: str = "admin"
    DB_PATH: str = "arena.db"
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENROUTER_MODEL: str = "meta-llama/llama-3.1-8b-instruct"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    COOLDOWN_SECONDS: float = 3.0
    MAX_PROMPT_LENGTH: int = 1000
    MAX_TOKENS: int = 150
    # Issue #45: LLM inference temperature increased from 0.1 to 0.4 (0.35 - 0.5 range)
    # to avoid overly deterministic refusals and allow persona roleplay.
    LLM_TEMPERATURE: float = 0.4
    # Issue #28: deterministic mock LLM provider. When true, /api/chat never
    # calls client.chat.completions.create and serves fixed async mock replies.
    MOCK_LLM_MODE: bool = False
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://.*$"
    LOG_FILE_PATH: str = "logs/arena_debug.log"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def get_llm_config(settings: Settings | None = None) -> dict[str, str]:
    """
    Resolve active LLM provider configuration (Groq or OpenRouter).

    Verifies explicit base_url configuration:
    - OpenRouter: base_url="https://openrouter.ai/api/v1"
    - Groq: base_url="https://api.groq.com/openai/v1"
    """
    if settings is None:
        settings = get_settings()

    provider = settings.LLM_PROVIDER.lower().strip()

    # Automatically detect OpenRouter if OPENROUTER_API_KEY is present or GROQ_API_KEY has OpenRouter prefix
    if not settings.GROQ_API_KEY and settings.OPENROUTER_API_KEY:
        provider = "openrouter"
    elif settings.GROQ_API_KEY and settings.GROQ_API_KEY.startswith("sk-or-"):
        provider = "openrouter"

    if provider == "openrouter":
        api_key = settings.OPENROUTER_API_KEY or settings.GROQ_API_KEY
        base_url = settings.OPENROUTER_BASE_URL.strip() if settings.OPENROUTER_BASE_URL else "https://openrouter.ai/api/v1"
        model = settings.OPENROUTER_MODEL if settings.OPENROUTER_API_KEY else settings.GROQ_MODEL
        return {
            "provider": "openrouter",
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        }
    else:
        api_key = settings.GROQ_API_KEY
        base_url = settings.GROQ_BASE_URL.strip() if settings.GROQ_BASE_URL else "https://api.groq.com/openai/v1"
        model = settings.GROQ_MODEL or "llama-3.1-8b-instant"
        return {
            "provider": "groq",
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        }
