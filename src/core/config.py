from typing import List

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ── Database ─────────────────────────────────────────
    POSTGRES_USER: str = "rit_user"
    POSTGRES_PASSWORD: SecretStr = SecretStr("rit_password")
    POSTGRES_DB: str = "resume_intelligence"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = ""

    # ── LLM ──────────────────────────────────────────────
    # Legacy / unused — kept for backwards compat with existing .env files.
    GEMINI_API_KEY: SecretStr = SecretStr("")

    # Active LLM provider abstraction. Designed for an OpenAI-compatible
    # chat completions endpoint so the same code can hit a locally
    # deployed model now or a cloud endpoint later.
    #
    # LLM_PROVIDER       — informational tag ("openai", "ollama", "local", ...)
    # LLM_BASE_URL       — base URL of the chat-completions endpoint
    #                      (e.g. "http://localhost:11434/v1" for ollama,
    #                       "https://api.openai.com/v1" for OpenAI)
    # LLM_API_KEY        — bearer token; may be blank for local endpoints
    # LLM_MODEL          — model identifier passed to the API
    # LLM_TIMEOUT_SEC    — per-request timeout
    LLM_PROVIDER: str = "openai"
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "llama3.1:8b"
    LLM_TIMEOUT_SEC: int = 120

    # ── Email watcher (n8n integration) ──────────────────
    # Gating flag — when false the email-event router is not mounted
    # and n8n integration is effectively disabled. Defaults to false:
    # the unified product treats email monitoring as optional / deprecated.
    ENABLE_EMAIL_WATCHER: bool = False

    # ── CORS ─────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    # Regex applied via Starlette CORSMiddleware's allow_origin_regex.
    # Default lets any installed Chrome extension call the API (extension
    # IDs are unstable in development; pinning to one would block reloads).
    # Set to "" to disable.
    ALLOWED_ORIGIN_REGEX: str = r"chrome-extension://.*"

    # ── Auth seam (Phase 5 will replace this) ────────────
    # Until real auth ships, every request is treated as owned by a fixed
    # owner_id. `get_current_owner()` (src/api/deps.py) returns this UUID,
    # and Phase 0+ writes it into `owner_id` columns. When auth lands,
    # only the dependency body changes.
    DEFAULT_OWNER_ID: str = "00000000-0000-0000-0000-000000000001"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str, info) -> str:
        if v:
            return v
        data = info.data
        password = data.get('POSTGRES_PASSWORD')
        if hasattr(password, 'get_secret_value'):
            password = password.get_secret_value()

        return (
            f"postgresql+asyncpg://{data.get('POSTGRES_USER')}:"
            f"{password}@{data.get('POSTGRES_HOST')}:"
            f"{data.get('POSTGRES_PORT')}/{data.get('POSTGRES_DB')}"
        )

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
