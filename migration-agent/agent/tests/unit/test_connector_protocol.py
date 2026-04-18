"""Unit tests for the Connector Protocol and registry."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from agent.connectors.protocol import (
    ActionError,
    ActionInput,
    ActionResult,
    Connector,
    InventoryResult,
    NormalizedEntity,
    get_connector,
    list_connectors,
    register_connector,
)

if TYPE_CHECKING:
    from datetime import datetime


class _StubConnector:
    name = "stub"

    async def inventory(
        self,
        entity_type: str,
        cursor: str | None = None,
        since: datetime | None = None,
    ) -> InventoryResult:
        return InventoryResult(
            entities=[
                NormalizedEntity(
                    source_id="e1",
                    entity_type=entity_type,
                    attributes={"display_name": "Test Entity"},
                )
            ]
        )

    async def execute(self, input: ActionInput) -> ActionResult:
        return ActionResult(success=True, target_id="t1")

    async def validate_action(self, input: ActionInput) -> tuple[bool, str | None]:
        return True, None

    async def health_check(self) -> bool:
        return True


def test_normalized_entity_roundtrip() -> None:
    entity = NormalizedEntity(
        source_id="src-123",
        entity_type="user",
        attributes={"upn": "alice@contoso.com"},
        content_hash="abc123",
    )
    assert entity.source_id == "src-123"
    assert entity.attributes["upn"] == "alice@contoso.com"


def test_action_error_factories() -> None:
    err = ActionError.transient("network blip")
    assert err.retriable is True
    assert err.class_ == "transient"

    err2 = ActionError.data_integrity("hash mismatch", {"expected": "a", "got": "b"})
    assert err2.retriable is False
    assert err2.class_ == "data_integrity"

    err3 = ActionError.permission("forbidden")
    assert err3.retriable is False


def test_action_error_alias_serialization() -> None:
    err = ActionError.logical("precondition failed")
    dumped = err.model_dump(by_alias=True)
    assert "class" in dumped
    assert dumped["class"] == "logical"


def test_connector_protocol_conformance() -> None:
    stub = _StubConnector()
    assert isinstance(stub, Connector)


def test_connector_registry_register_and_retrieve() -> None:
    stub = _StubConnector()
    register_connector(stub)
    retrieved = get_connector("stub")
    assert retrieved is stub
    assert "stub" in list_connectors()


def test_connector_registry_missing_raises() -> None:
    with pytest.raises(KeyError, match="nonexistent"):
        get_connector("nonexistent")


@pytest.mark.asyncio
async def test_stub_connector_inventory() -> None:
    stub = _StubConnector()
    result = await stub.inventory("user")
    assert len(result.entities) == 1
    assert result.entities[0].entity_type == "user"


@pytest.mark.asyncio
async def test_stub_connector_execute() -> None:
    stub = _StubConnector()
    action_input = ActionInput(
        action_type="test_action",
        subject={"upn": "alice@contoso.com"},
        parameters={},
        correlation_id=uuid.uuid4(),
    )
    result = await stub.execute(action_input)
    assert result.success is True
    assert result.target_id == "t1"


@pytest.mark.asyncio
async def test_stub_connector_health_check() -> None:
    stub = _StubConnector()
    assert await stub.health_check() is True
