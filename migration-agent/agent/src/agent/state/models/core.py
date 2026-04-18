from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SourceInventory(TimestampMixin, Base):
    __tablename__ = "source_inventory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "source_id"),
        Index("ix_source_inventory_entity_type", "entity_type"),
        Index("ix_source_inventory_tenant_id", "tenant_id"),
    )


class TargetInventory(TimestampMixin, Base):
    __tablename__ = "target_inventory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    target_system: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("target_system", "entity_type", "target_id"),
        Index("ix_target_inventory_entity_type", "entity_type"),
    )


class IdentityMap(TimestampMixin, Base):
    __tablename__ = "identity_map"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_tenant: Mapped[str] = mapped_column(Text, nullable=False)
    source_upn: Mapped[str] = mapped_column(Text, nullable=False)
    target_system: Mapped[str] = mapped_column(Text, nullable=False)
    target_upn: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    llm_proposed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")
    is_contractor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_service_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected')", name="ck_identity_map_status"
        ),
        UniqueConstraint("source_tenant", "source_upn", "target_system"),
        Index("ix_identity_map_status", "status"),
    )


class WavePlan(TimestampMixin, Base):
    __tablename__ = "wave_plan"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    wave_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_start: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    members: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    canary_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_map.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'in_progress', 'complete', 'rolled_back')",
            name="ck_wave_plan_status",
        ),
    )


class MigrationJob(TimestampMixin, Base):
    __tablename__ = "migration_job"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    wave_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wave_plan.id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[dict] = mapped_column(JSONB, nullable=False)
    connector: Mapped[str] = mapped_column(Text, nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_migration_job_status",
        ),
        UniqueConstraint("wave_id", "input_hash", name="uq_migration_job_idempotency"),
        Index("ix_migration_job_status", "status"),
        Index("ix_migration_job_wave_id", "wave_id"),
    )


class GateDecision(TimestampMixin, Base):
    __tablename__ = "gate_decision"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    gate_number: Mapped[int] = mapped_column(Integer, nullable=False)
    wave_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wave_plan.id"), nullable=True
    )
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifacts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approver: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("gate_number BETWEEN 1 AND 7", name="ck_gate_decision_gate_number"),
        CheckConstraint(
            "decision IN ('approved', 'denied', 'revoked')", name="ck_gate_decision_decision"
        ),
    )


class AuditLog(Base):
    """Append-only. No updated_at. Trigger blocks UPDATE and DELETE."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_audit_log_correlation_id", "correlation_id"),
        Index("ix_audit_log_timestamp", "timestamp"),
    )


class PermissionDiff(TimestampMixin, Base):
    __tablename__ = "permission_diff"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    wave_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wave_plan.id"), nullable=False
    )
    source_resource: Mapped[str] = mapped_column(Text, nullable=False)
    target_resource: Mapped[str] = mapped_column(Text, nullable=False)
    source_principal: Mapped[str] = mapped_column(Text, nullable=False)
    target_principal: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_role: Mapped[str] = mapped_column(Text, nullable=False)
    target_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    equivalence: Mapped[str] = mapped_column(Text, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "equivalence IN ('EXACT', 'WIDER', 'NARROWER', 'UNMAPPABLE')",
            name="ck_permission_diff_equivalence",
        ),
        Index("ix_permission_diff_wave_id", "wave_id"),
        Index(
            "ix_permission_diff_blocking_true",
            "blocking",
            postgresql_where=text("blocking = true"),
        ),
    )


class DeltaQueue(Base):
    __tablename__ = "delta_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_tenant: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now()
    )
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'applied', 'failed', 'skipped')", name="ck_delta_queue_status"
        ),
        Index("ix_delta_queue_status", "status"),
        Index("ix_delta_queue_subject_id", "subject_id"),
    )


class RollbackState(TimestampMixin, Base):
    __tablename__ = "rollback_state"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    migration_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_job.id"), nullable=False
    )
    reverse_action: Mapped[str] = mapped_column(Text, nullable=False)
    reverse_input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    executable_until: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    executed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    executed_by: Mapped[str | None] = mapped_column(Text, nullable=True)


class RetentionLedger(TimestampMixin, Base):
    __tablename__ = "retention_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    policy_type: Mapped[str] = mapped_column(Text, nullable=False)
    policy_name: Mapped[str] = mapped_column(Text, nullable=False)
    hold_start: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    hold_end: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    archive_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_manifest_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    transferred_to_target: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class BusySeason(TimestampMixin, Base):
    __tablename__ = "busy_season"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    hard_freeze_start: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    hard_freeze_end: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    soft_freeze_weeks_before: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    soft_freeze_weeks_after: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    applies_to_users: Mapped[list] = mapped_column(JSONB, nullable=True, default=list)

    __table_args__ = (
        CheckConstraint("hard_freeze_end > hard_freeze_start", name="ck_busy_season_dates"),
    )


class SchedulabilityOverride(TimestampMixin, Base):
    __tablename__ = "schedulability_override"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[dict] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    approver: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("valid_until > valid_from", name="ck_schedulability_override_window"),
    )
