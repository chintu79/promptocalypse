from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    ADMIN_TOKEN: str = "admin"
    ADMIN_USERNAME: str = "krishna"
    ADMIN_PASSWORD: str = "krishna04@gmail.com"
    DB_PATH: str = "arena.db"
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENROUTER_MODEL: str = "meta-llama/llama-3.1-8b-instruct"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OLLAMA_ENDPOINTS: str = "http://192.168.1.101:11434/v1,http://192.168.1.102:11434/v1"
    OLLAMA_MODEL: str = "llama3.2:latest"
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
    Resolve active LLM provider configuration.

    Supported providers:
    - ollama:      Local Ollama server (OpenAI-compatible at /v1)
    - groq:        Groq cloud API
    - openrouter:  OpenRouter cloud API

    Ollama requires no API key; the openai SDK accepts "ollama" as a
    placeholder value.
    """
    if settings is None:
        settings = get_settings()

    provider = settings.LLM_PROVIDER.lower().strip()

    # Auto-detect cloud providers from API keys if provider is the default 'groq' or 'auto'
    if provider in ("groq", "auto", ""):
        if not settings.GROQ_API_KEY and settings.OPENROUTER_API_KEY:
            provider = "openrouter"
        elif settings.GROQ_API_KEY and settings.GROQ_API_KEY.startswith("sk-or-"):
            provider = "openrouter"
        elif not settings.GROQ_API_KEY and not settings.OPENROUTER_API_KEY:
            # If no API keys are provided and it's default groq, allow it to remain groq 
            # so health checks can correctly report 'unconfigured' instead of failing over to ollama
            pass

    if provider == "ollama":
        endpoints = [
            u.strip() for u in settings.OLLAMA_ENDPOINTS.split(",") if u.strip()
        ] or ["http://localhost:11434/v1"]
        model = settings.OLLAMA_MODEL.strip() or "llama3.2:latest"
        return {
            "provider": "ollama",
            "api_key": "ollama",  # Ollama doesn't require a real key; placeholder for openai SDK
            "base_url": endpoints[0],  # default for single-client callers (health check)
            "endpoints": endpoints,    # full list for round-robin in chat route
            "model": model,
        }
    elif provider == "openrouter":
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

