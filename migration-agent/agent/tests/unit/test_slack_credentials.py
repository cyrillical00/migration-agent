"""Slack request verification must never rest on a published secret."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import sys
import time

import pytest
from slack_sdk.signature import SignatureVerifier

from agent.config import Settings
from agent.slack_credentials import bot_token, signing_secret

PUBLISHED = ("dev-placeholder", "YOUR_SIGNING_SECRET")
BODY = "token=x&command=%2Fping&text=&user_id=U1&team_id=T1"


def _settings(env: str, **slack: str) -> Settings:
    return Settings(  # type: ignore[call-arg]
        env=env,
        secret_key="x",
        database_url="postgresql+asyncpg://localhost/db",
        _env_file=None,
        **slack,
    )


def _sign(secret: str, body: str, timestamp: str) -> str:
    base = f"v0:{timestamp}:{body}".encode()
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


@pytest.mark.parametrize("env", ["staging", "prod"])
@pytest.mark.parametrize("value", ["", "   ", *PUBLISHED])
def test_missing_or_published_signing_secret_stops_startup_outside_dev(
    env: str, value: str
) -> None:
    with pytest.raises(RuntimeError, match="SLACK_SIGNING_SECRET"):
        signing_secret(_settings(env, slack_signing_secret=value, slack_bot_token="xoxb-real"))


@pytest.mark.parametrize("env", ["staging", "prod"])
@pytest.mark.parametrize("value", ["", "xoxb-dev-placeholder", "xoxb-YOUR-BOT-TOKEN"])
def test_missing_or_published_bot_token_stops_startup_outside_dev(env: str, value: str) -> None:
    with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
        bot_token(_settings(env, slack_bot_token=value))


@pytest.mark.parametrize("env", ["dev", "staging", "prod"])
def test_configured_values_are_used_as_given(env: str) -> None:
    settings = _settings(
        env, slack_signing_secret=" real-signing-secret ", slack_bot_token="xoxb-real"
    )
    assert signing_secret(settings) == "real-signing-secret"
    assert bot_token(settings) == "xoxb-real"


@pytest.mark.parametrize("value", ["", *PUBLISHED])
def test_dev_without_a_secret_gets_one_nobody_knows(value: str) -> None:
    settings = _settings("dev", slack_signing_secret=value)
    first, second = signing_secret(settings), signing_secret(settings)
    assert first not in PUBLISHED
    assert second not in PUBLISHED
    assert first != second
    assert len(first) == 64


@pytest.mark.parametrize("published", PUBLISHED)
def test_request_signed_with_a_published_secret_is_rejected(published: str) -> None:
    timestamp = str(int(time.time()))
    forged = _sign(published, BODY, timestamp)

    # What the app verified against before: the literal from the repository.
    assert SignatureVerifier(published).is_valid(BODY, timestamp, forged)

    for configured in ("", published):
        secret = signing_secret(_settings("dev", slack_signing_secret=configured))
        assert not SignatureVerifier(secret).is_valid(BODY, timestamp, forged)


def _load_app(monkeypatch: pytest.MonkeyPatch, **env: str):  # type: ignore[no-untyped-def]
    """Import agent.main afresh under the given environment."""
    for name in ("MIGRATION_AGENT_SLACK_SIGNING_SECRET", "MIGRATION_AGENT_SLACK_BOT_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MIGRATION_AGENT_SECRET_KEY", "x")
    monkeypatch.setenv("MIGRATION_AGENT_DATABASE_URL", "postgresql+asyncpg://localhost/db")
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    import agent.config

    monkeypatch.setattr(agent.config, "_settings", None)
    for module in ("agent.main", "agent.slack.app", "agent.slack"):
        monkeypatch.delitem(sys.modules, module, raising=False)
    return importlib.import_module("agent.main")


def test_slack_endpoint_rejects_a_forged_request(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("aiohttp", reason="slack_bolt's async app needs aiohttp")
    from fastapi.testclient import TestClient

    main = _load_app(monkeypatch, MIGRATION_AGENT_ENV="dev")
    client = TestClient(main.app)
    timestamp = str(int(time.time()))

    for published in PUBLISHED:
        response = client.post(
            "/slack/events",
            content=BODY,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": _sign(published, BODY, timestamp),
            },
        )
        assert response.status_code == 401, published


def test_slack_endpoint_accepts_a_request_signed_with_the_real_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("aiohttp", reason="slack_bolt's async app needs aiohttp")
    from fastapi.testclient import TestClient

    main = _load_app(
        monkeypatch,
        MIGRATION_AGENT_ENV="dev",
        MIGRATION_AGENT_SLACK_SIGNING_SECRET="real-signing-secret",
    )
    client = TestClient(main.app)
    timestamp = str(int(time.time()))
    body = '{"type":"url_verification","challenge":"abc"}'
    response = client.post(
        "/slack/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": _sign("real-signing-secret", body, timestamp),
        },
    )
    assert response.status_code == 200
    assert response.json() == {"challenge": "abc"}


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_app_does_not_start_outside_dev_without_the_signing_secret(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    pytest.importorskip("aiohttp", reason="slack_bolt's async app needs aiohttp")
    with pytest.raises(RuntimeError, match="SLACK_SIGNING_SECRET"):
        _load_app(monkeypatch, MIGRATION_AGENT_ENV=env, MIGRATION_AGENT_SLACK_BOT_TOKEN="xoxb-real")
