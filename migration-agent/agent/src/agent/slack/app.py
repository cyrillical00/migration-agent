from __future__ import annotations

import structlog
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from agent.config import get_settings

log = structlog.get_logger(__name__)

_settings = get_settings()

app = AsyncApp(
    token=_settings.slack_bot_token or "xoxb-dev-placeholder",
    signing_secret=_settings.slack_signing_secret or "dev-placeholder",
)
handler = AsyncSlackRequestHandler(app)


@app.command("/ping")
async def handle_ping(ack, respond):  # type: ignore[no-untyped-def]
    await ack()
    await respond("pong")


@app.event("app_home_opened")
async def handle_app_home_opened(event, client):  # type: ignore[no-untyped-def]
    user_id = event.get("user")
    log.info("app_home_opened", user_id=user_id)
    await client.views_publish(
        user_id=user_id,
        view={
            "type": "home",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Migration Agent* is ready.\nStep 1 skeleton running.",
                    },
                }
            ],
        },
    )
