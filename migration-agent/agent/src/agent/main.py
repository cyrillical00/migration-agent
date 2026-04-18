from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI, Request

from agent.api.health import router as health_router
from agent.config import get_settings
from agent.observability import configure_logging, configure_tracing
from agent.slack.app import handler as slack_handler

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi.responses import JSONResponse

settings = get_settings()
configure_logging(settings.env)
configure_tracing(settings.env)

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("migration_agent_starting", env=settings.env)
    yield
    log.info("migration_agent_stopping")


app = FastAPI(
    title="Migration Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)


@app.post("/slack/events")
async def slack_events(req: Request) -> JSONResponse:
    return await slack_handler.handle(req)
