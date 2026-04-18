"""Unit tests for Settings validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_invalid_env_raises() -> None:
    from agent.config import Settings

    with pytest.raises(ValidationError, match="env must be one of"):
        Settings(env="production", secret_key="x", database_url="postgresql+asyncpg://localhost/db")  # type: ignore[call-arg]


def test_valid_envs_accepted() -> None:
    from agent.config import Settings

    for env in ("dev", "staging", "prod"):
        s = Settings(env=env, secret_key="x", database_url="postgresql+asyncpg://localhost/db")  # type: ignore[call-arg]
        assert s.env == env
