"""Slack credentials for the Bolt app.

The signing secret is what proves a request to /slack/events really came from
Slack. It is never replaced by a known value: outside dev a missing secret
stops the process, and in dev it becomes a random one that nothing can sign
for, so every Slack request is rejected until a real secret is configured.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from agent.config import Settings

log = structlog.get_logger(__name__)

# Example values that appear in this repository. Anyone can read them, so
# they are treated the same as an empty setting.
_PLACEHOLDERS = frozenset(
    {
        "dev-placeholder",
        "xoxb-dev-placeholder",
        "YOUR_SIGNING_SECRET",
        "xoxb-YOUR-BOT-TOKEN",
    }
)


def _configured(value: str) -> str | None:
    value = value.strip()
    if not value or value in _PLACEHOLDERS:
        return None
    return value


def signing_secret(settings: Settings) -> str:
    """Secret used to verify Slack's request signatures."""
    secret = _configured(settings.slack_signing_secret)
    if secret is not None:
        return secret
    if settings.env != "dev":
        raise RuntimeError(
            "MIGRATION_AGENT_SLACK_SIGNING_SECRET must be set to the Slack app's signing "
            f"secret when MIGRATION_AGENT_ENV is {settings.env!r}; refusing to start "
            "without request verification."
        )
    log.warning(
        "slack_signing_secret_missing",
        detail="Slack requests will be rejected until MIGRATION_AGENT_SLACK_SIGNING_SECRET is set.",
    )
    return secrets.token_hex(32)


def bot_token(settings: Settings) -> str:
    """Bot token for calls to the Slack API."""
    token = _configured(settings.slack_bot_token)
    if token is not None:
        return token
    if settings.env != "dev":
        raise RuntimeError(
            "MIGRATION_AGENT_SLACK_BOT_TOKEN must be set to the Slack app's bot token "
            f"when MIGRATION_AGENT_ENV is {settings.env!r}."
        )
    # Not a credential: it only lets the app object be built on a developer's
    # machine. Slack rejects it on the first API call.
    return "xoxb-dev-placeholder"
