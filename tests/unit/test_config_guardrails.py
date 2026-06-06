"""
Production config guardrails (Phase 5 auth-hardening PR1).

APP_ENV=production refuses to boot with a security-critical misconfiguration
(dev JWT secret, non-https base URL, auth off) and warns on operational gaps
(no SMTP). Non-production envs keep their convenient defaults.

`_env_file=None` makes each Settings() hermetic (ignore any on-disk .env).
"""
from __future__ import annotations

import pytest
from pydantic import SecretStr

from src.core.config import DEV_JWT_SECRET, Settings


def _settings(**overrides) -> Settings:
    base = dict(
        APP_ENV="production",
        JWT_SECRET=SecretStr("a-strong-production-secret"),
        APP_BASE_URL="https://rit.example.com",
        REQUIRE_AUTH=True,
        SMTP_HOST="smtp.example.com",
        DATABASE_URL="postgresql+asyncpg://u:p@h:5432/db",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_valid_production_config_boots():
    s = _settings()
    assert s.APP_ENV == "production"


def test_rejects_dev_jwt_secret_in_production():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _settings(JWT_SECRET=SecretStr(DEV_JWT_SECRET))


def test_rejects_non_https_base_url_in_production():
    with pytest.raises(ValueError, match="https"):
        _settings(APP_BASE_URL="http://rit.example.com")


def test_rejects_dev_previous_secret_in_production():
    with pytest.raises(ValueError, match="JWT_SECRET_PREVIOUS"):
        _settings(JWT_SECRET_PREVIOUS=SecretStr(DEV_JWT_SECRET))


def test_rejects_auth_off_in_production():
    with pytest.raises(ValueError, match="REQUIRE_AUTH"):
        _settings(REQUIRE_AUTH=False)


def test_reports_all_problems_at_once():
    with pytest.raises(ValueError) as exc:
        _settings(
            JWT_SECRET=SecretStr(DEV_JWT_SECRET),
            APP_BASE_URL="http://rit.example.com",
            REQUIRE_AUTH=False,
        )
    msg = str(exc.value)
    assert "JWT_SECRET" in msg and "https" in msg and "REQUIRE_AUTH" in msg


def test_missing_smtp_warns_but_boots(capsys):
    s = _settings(SMTP_HOST="")
    assert s.APP_ENV == "production"          # boots
    assert "SMTP_HOST" in capsys.readouterr().err  # but warns


def test_development_allows_insecure_defaults():
    # The whole point: dev keeps the convenient defaults, no raise.
    s = Settings(
        _env_file=None,
        APP_ENV="development",
        JWT_SECRET=SecretStr(DEV_JWT_SECRET),
        APP_BASE_URL="http://localhost",
        REQUIRE_AUTH=False,
        DATABASE_URL="postgresql+asyncpg://u:p@h:5432/db",
    )
    assert s.APP_ENV == "development"
