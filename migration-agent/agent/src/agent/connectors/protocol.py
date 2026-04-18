from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field


class NormalizedEntity(BaseModel):
    source_id: str
    entity_type: str
    attributes: dict[str, object]
    raw: dict[str, object] | None = None
    content_hash: str | None = None


class InventoryResult(BaseModel):
    entities: list[NormalizedEntity]
    cursor: str | None = None
    total_expected: int | None = None


class ActionInput(BaseModel):
    action_type: str
    subject: dict[str, object]
    parameters: dict[str, object]
    correlation_id: UUID


class ActionError(BaseModel):
    class_: str = Field(alias="class")
    message: str
    retriable: bool
    detail: dict[str, object] | None = None

    model_config = {"populate_by_name": True}

    @classmethod
    def transient(cls, message: str, detail: dict[str, object] | None = None) -> ActionError:
        return cls(
            **{"class": "transient", "message": message, "retriable": True, "detail": detail}
        )

    @classmethod
    def permission(cls, message: str) -> ActionError:
        return cls(**{"class": "permission", "message": message, "retriable": False})

    @classmethod
    def data_integrity(cls, message: str, detail: dict[str, object] | None = None) -> ActionError:
        return cls(
            **{"class": "data_integrity", "message": message, "retriable": False, "detail": detail}
        )

    @classmethod
    def schema(cls, message: str) -> ActionError:
        return cls(**{"class": "schema", "message": message, "retriable": False})

    @classmethod
    def capacity(cls, message: str) -> ActionError:
        return cls(**{"class": "capacity", "message": message, "retriable": False})

    @classmethod
    def logical(cls, message: str) -> ActionError:
        return cls(**{"class": "logical", "message": message, "retriable": False})


class ActionResult(BaseModel):
    success: bool
    target_id: str | None = None
    output: dict[str, object] | None = None
    error: ActionError | None = None


_REGISTRY: dict[str, Connector] = {}


@runtime_checkable
class Connector(Protocol):
    name: str

    async def inventory(
        self,
        entity_type: str,
        cursor: str | None = None,
        since: datetime | None = None,
    ) -> InventoryResult: ...

    async def execute(self, input: ActionInput) -> ActionResult: ...

    async def validate_action(self, input: ActionInput) -> tuple[bool, str | None]: ...

    async def health_check(self) -> bool: ...


def register_connector(connector: Connector) -> None:
    _REGISTRY[connector.name] = connector


def get_connector(name: str) -> Connector:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"No connector registered with name {name!r}. Available: {list(_REGISTRY)}"
        ) from exc


def list_connectors() -> list[str]:
    return list(_REGISTRY.keys())
