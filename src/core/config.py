import sys
from typing import List

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings


VALID_ENVS = {"development", "e2e", "staging", "production", "test"}

# The placeholder JWT secret shipped for local dev. Booting production with this
# value is a hard error (see the production guardrail below).
DEV_JWT_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────
    # APP_ENV must be one of VALID_ENVS. The value is stamped onto
    # every response as the X-Environment header and surfaced on
    # /health so the dashboard and extension can show which stack
    # they're talking to. Set explicitly per docker-compose file:
    #   dev   → development
    #   e2e   → e2e
    #   prod  → production
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    @field_validator("APP_ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        if v not in VALID_ENVS:
            raise ValueError(
                f"APP_ENV={v!r} is not one of {sorted(VALID_ENVS)}. "
                "Set it explicitly in the env file for this stack."
            )
        return v

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

    # ── Auth seam ────────────────────────────────────────
    # Until REQUIRE_AUTH is on, every request is treated as owned by a fixed
    # owner_id. `get_current_owner()` (src/api/deps.py) returns this UUID when
    # auth is off; when on it resolves the session cookie to a real user.
    DEFAULT_OWNER_ID: str = "00000000-0000-0000-0000-000000000001"

    # ── Authentication (Phase 2: magic-link sessions) ────
    # Master switch. False (default) = single-tenant default owner, no login
    # required (non-breaking). True = require a valid session; unauthenticated
    # requests get 401. Flip on once the login UI is wired (later Phase 2 PR).
    REQUIRE_AUTH: bool = False
    # HS256 signing secret for session JWTs. MUST be overridden in production
    # (the production guardrail below refuses to boot with the dev default).
    JWT_SECRET: SecretStr = SecretStr(DEV_JWT_SECRET)
    # Previous signing secret, kept for verify-only during a rotation: tokens
    # are always signed with JWT_SECRET, but decode falls back to this one so a
    # secret swap doesn't invalidate everyone's session. Blank = no rotation in
    # progress. Drop it after one SESSION_DAYS window.
    JWT_SECRET_PREVIOUS: SecretStr = SecretStr("")
    SESSION_DAYS: int = 30
    SESSION_COOKIE_NAME: str = "rit_session"
    # Magic-link login token lifetime.
    MAGIC_LINK_TTL_MIN: int = 15
    # Where the dashboard lives — used to build the magic-link URL.
    APP_BASE_URL: str = "http://localhost:5173"

    # SMTP for sending magic links. All optional — when SMTP_HOST is blank
    # (the default, e.g. dev), the link is logged to the console instead of
    # emailed, so local login works with zero mail setup.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: SecretStr = SecretStr("")
    SMTP_FROM: str = "no-reply@rit.local"

    # ── Rate limiting (auth endpoints) ───────────────────
    # Throttles the unauthenticated auth endpoints to prevent email-bombing and
    # verify hammering. In-memory / per-process (single-instance); see the
    # Phase 5 spec for the Redis swap at scale.
    RATE_LIMIT_ENABLED: bool = True
    # Per-IP cap for request-link + verify, per 60s.
    AUTH_RL_IP_PER_MINUTE: int = 20
    # Per-email cap for request-link, per hour (stops bombing one address).
    AUTH_RL_EMAIL_PER_HOUR: int = 10

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

    @model_validator(mode="after")
    def _production_guardrails(self):
        """Fail fast when APP_ENV=production is started with an insecure config.

        These checks only fire in production, so dev / e2e / staging / test keep
        their convenient defaults. Security-critical misconfigurations raise (the
        app refuses to boot); operational ones log a warning.
        """
        if self.APP_ENV != "production":
            return self

        fatal: list[str] = []
        if self.JWT_SECRET.get_secret_value() == DEV_JWT_SECRET:
            fatal.append("JWT_SECRET is still the insecure dev default — set a strong, secret value")
        if self.JWT_SECRET_PREVIOUS.get_secret_value() == DEV_JWT_SECRET:
            fatal.append("JWT_SECRET_PREVIOUS is the insecure dev default — clear it or set a real prior secret")
        if not self.APP_BASE_URL.startswith("https://"):
            fatal.append(f"APP_BASE_URL must use https in production (got {self.APP_BASE_URL!r})")
        if not self.REQUIRE_AUTH:
            fatal.append("REQUIRE_AUTH must be true in production (otherwise every request is the default owner)")

        if fatal:
            raise ValueError(
                "Refusing to start: insecure production configuration:\n  - "
                + "\n  - ".join(fatal)
            )

        # Operational (non-fatal): without SMTP, magic links are only logged, so
        # nobody can actually sign in — warn loudly but don't block boot (an
        # API-token-only or alternative-delivery deployment may be intentional).
        if not self.SMTP_HOST:
            print(
                "WARNING: APP_ENV=production but SMTP_HOST is unset — magic-link "
                "emails will be logged, not delivered.",
                file=sys.stderr,
            )
        return self

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
