from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agent.config import Settings, get_settings

log = structlog.get_logger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    env: str
    version: str = "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    log.debug("health check")
    return HealthResponse(status="ok", env=settings.env)
