"""Initial schema: all core tables, triggers, and indexes.

Revision ID: 0001
Revises:
Create Date: 2026-04-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- updated_at trigger function ----
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # ---- audit_log immutability trigger function ----
    op.execute(
        """
        CREATE OR REPLACE FUNCTION deny_audit_log_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; UPDATE and DELETE are forbidden';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # ---- audit trigger function (fires after INSERT/UPDATE on other tables) ----
    op.execute(
        """
        CREATE OR REPLACE FUNCTION write_audit_log()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO audit_log (actor, action, target, result, payload)
            VALUES (
                current_user,
                TG_OP || ':' || TG_TABLE_NAME,
                to_jsonb(NEW),
                'ok',
                jsonb_build_object('old', to_jsonb(OLD), 'new', to_jsonb(NEW))
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # ---- source_inventory ----
    op.create_table(
        "source_inventory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("normalized", JSONB, nullable=False),
        sa.Column("raw", JSONB, nullable=True),
        sa.Column("content_hash", sa.Text, nullable=True),
        sa.Column("discovered_at", TIMESTAMPTZ, nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "entity_type", "source_id"),
    )
    op.create_index("ix_source_inventory_entity_type", "source_inventory", ["entity_type"])
    op.create_index("ix_source_inventory_tenant_id", "source_inventory", ["tenant_id"])
    _add_updated_at_trigger("source_inventory")
    _add_audit_trigger("source_inventory")

    # ---- target_inventory ----
    op.create_table(
        "target_inventory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("target_system", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("target_id", sa.Text, nullable=False),
        sa.Column("normalized", JSONB, nullable=False),
        sa.Column("raw", JSONB, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("target_system", "entity_type", "target_id"),
    )
    op.create_index("ix_target_inventory_entity_type", "target_inventory", ["entity_type"])
    _add_updated_at_trigger("target_inventory")
    _add_audit_trigger("target_inventory")

    # ---- identity_map ----
    op.create_table(
        "identity_map",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_tenant", sa.Text, nullable=False),
        sa.Column("source_upn", sa.Text, nullable=False),
        sa.Column("target_system", sa.Text, nullable=False),
        sa.Column("target_upn", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("llm_proposed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("human_confirmed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", sa.Text, nullable=False, server_default="proposed"),
        sa.Column("is_contractor", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_service_account", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("confirmed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("confirmed_by", sa.Text, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected')", name="ck_identity_map_status"
        ),
        sa.UniqueConstraint("source_tenant", "source_upn", "target_system"),
    )
    op.create_index("ix_identity_map_status", "identity_map", ["status"])
    _add_updated_at_trigger("identity_map")
    _add_audit_trigger("identity_map")

    # ---- wave_plan ----
    op.create_table(
        "wave_plan",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("wave_number", sa.Integer, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("scheduled_start", TIMESTAMPTZ, nullable=True),
        sa.Column("scheduled_end", TIMESTAMPTZ, nullable=True),
        sa.Column("members", JSONB, nullable=False, server_default="'[]'"),
        sa.Column(
            "canary_member_id",
            UUID(as_uuid=True),
            sa.ForeignKey("identity_map.id"),
            nullable=True,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("approved_at", TIMESTAMPTZ, nullable=True),
        sa.Column("approved_by", sa.Text, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'in_progress', 'complete', 'rolled_back')",
            name="ck_wave_plan_status",
        ),
    )
    _add_updated_at_trigger("wave_plan")
    _add_audit_trigger("wave_plan")

    # ---- migration_job ----
    op.create_table(
        "migration_job",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("wave_id", UUID(as_uuid=True), sa.ForeignKey("wave_plan.id"), nullable=False),
        sa.Column("action_type", sa.Text, nullable=False),
        sa.Column("subject", JSONB, nullable=False),
        sa.Column("connector", sa.Text, nullable=False),
        sa.Column("input", JSONB, nullable=False),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("queued_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", TIMESTAMPTZ, nullable=True),
        sa.Column("completed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_migration_job_status",
        ),
        sa.UniqueConstraint("wave_id", "input_hash", name="uq_migration_job_idempotency"),
    )
    op.create_index("ix_migration_job_status", "migration_job", ["status"])
    op.create_index("ix_migration_job_wave_id", "migration_job", ["wave_id"])
    _add_updated_at_trigger("migration_job")
    _add_audit_trigger("migration_job")

    # ---- audit_log (no updated_at, no audit trigger on itself) ----
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("timestamp", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target", JSONB, nullable=True),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
    )
    op.create_index("ix_audit_log_correlation_id", "audit_log", ["correlation_id"])
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    # Immutability trigger
    op.execute(
        """
        CREATE TRIGGER trg_audit_log_immutable
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION deny_audit_log_mutation();
        """
    )

    # ---- gate_decision ----
    op.create_table(
        "gate_decision",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("gate_number", sa.Integer, nullable=False),
        sa.Column(
            "wave_id", UUID(as_uuid=True), sa.ForeignKey("wave_plan.id"), nullable=True
        ),
        sa.Column("phase", sa.Text, nullable=False),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("artifacts", JSONB, nullable=True),
        sa.Column("approver", sa.Text, nullable=False),
        sa.Column("decided_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("gate_number BETWEEN 1 AND 7", name="ck_gate_decision_gate_number"),
        sa.CheckConstraint(
            "decision IN ('approved', 'denied', 'revoked')", name="ck_gate_decision_decision"
        ),
    )
    _add_updated_at_trigger("gate_decision")
    _add_audit_trigger("gate_decision")

    # ---- permission_diff ----
    op.create_table(
        "permission_diff",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("wave_id", UUID(as_uuid=True), sa.ForeignKey("wave_plan.id"), nullable=False),
        sa.Column("source_resource", sa.Text, nullable=False),
        sa.Column("target_resource", sa.Text, nullable=False),
        sa.Column("source_principal", sa.Text, nullable=False),
        sa.Column("target_principal", sa.Text, nullable=True),
        sa.Column("source_role", sa.Text, nullable=False),
        sa.Column("target_role", sa.Text, nullable=True),
        sa.Column("equivalence", sa.Text, nullable=False),
        sa.Column("blocking", sa.Boolean, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("computed_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "equivalence IN ('EXACT', 'WIDER', 'NARROWER', 'UNMAPPABLE')",
            name="ck_permission_diff_equivalence",
        ),
    )
    op.create_index("ix_permission_diff_wave_id", "permission_diff", ["wave_id"])
    op.create_index(
        "ix_permission_diff_blocking_true",
        "permission_diff",
        ["blocking"],
        postgresql_where=sa.text("blocking = true"),
    )
    _add_updated_at_trigger("permission_diff")
    _add_audit_trigger("permission_diff")

    # ---- delta_queue ----
    op.create_table(
        "delta_queue",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_tenant", sa.Text, nullable=False),
        sa.Column("subject_id", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("change_type", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("received_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("applied_at", TIMESTAMPTZ, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'failed', 'skipped')",
            name="ck_delta_queue_status",
        ),
    )
    op.create_index("ix_delta_queue_status", "delta_queue", ["status"])
    op.create_index("ix_delta_queue_subject_id", "delta_queue", ["subject_id"])

    # ---- rollback_state ----
    op.create_table(
        "rollback_state",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "migration_job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("migration_job.id"),
            nullable=False,
        ),
        sa.Column("reverse_action", sa.Text, nullable=False),
        sa.Column("reverse_input", JSONB, nullable=False),
        sa.Column("executable_until", TIMESTAMPTZ, nullable=True),
        sa.Column("executed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("executed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("executed_by", sa.Text, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )
    _add_updated_at_trigger("rollback_state")
    _add_audit_trigger("rollback_state")

    # ---- retention_ledger ----
    op.create_table(
        "retention_ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_entity_id", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("policy_type", sa.Text, nullable=False),
        sa.Column("policy_name", sa.Text, nullable=False),
        sa.Column("hold_start", TIMESTAMPTZ, nullable=True),
        sa.Column("hold_end", TIMESTAMPTZ, nullable=True),
        sa.Column("archive_location", sa.Text, nullable=True),
        sa.Column("archive_manifest_hash", sa.Text, nullable=True),
        sa.Column("transferred_to_target", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )
    _add_updated_at_trigger("retention_ledger")
    _add_audit_trigger("retention_ledger")

    # ---- busy_season ----
    op.create_table(
        "busy_season",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("hard_freeze_start", TIMESTAMPTZ, nullable=False),
        sa.Column("hard_freeze_end", TIMESTAMPTZ, nullable=False),
        sa.Column("soft_freeze_weeks_before", sa.Integer, nullable=False, server_default="2"),
        sa.Column("soft_freeze_weeks_after", sa.Integer, nullable=False, server_default="1"),
        sa.Column("applies_to_users", JSONB, nullable=True, server_default="'[]'"),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("hard_freeze_end > hard_freeze_start", name="ck_busy_season_dates"),
    )
    _add_updated_at_trigger("busy_season")
    _add_audit_trigger("busy_season")

    # ---- schedulability_override ----
    op.create_table(
        "schedulability_override",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("action_type", sa.Text, nullable=False),
        sa.Column("subject", JSONB, nullable=False),
        sa.Column("valid_from", TIMESTAMPTZ, nullable=False),
        sa.Column("valid_until", TIMESTAMPTZ, nullable=False),
        sa.Column("approver", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("valid_until > valid_from", name="ck_schedulability_override_window"),
    )
    _add_updated_at_trigger("schedulability_override")
    _add_audit_trigger("schedulability_override")


def downgrade() -> None:
    # Drop in reverse FK dependency order
    tables = [
        "schedulability_override",
        "busy_season",
        "retention_ledger",
        "rollback_state",
        "delta_queue",
        "permission_diff",
        "gate_decision",
        "audit_log",
        "migration_job",
        "wave_plan",
        "identity_map",
        "target_inventory",
        "source_inventory",
    ]
    for table in tables:
        op.drop_table(table)

    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS deny_audit_log_mutation() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS write_audit_log() CASCADE")


# ---- helpers ----

def _add_updated_at_trigger(table: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER trg_{table}_updated_at
        BEFORE UPDATE ON {table}
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def _add_audit_trigger(table: str) -> None:
    op.execute(
        f"""
        CREATE TRIGGER trg_{table}_audit
        AFTER INSERT OR UPDATE ON {table}
        FOR EACH ROW EXECUTE FUNCTION write_audit_log();
        """
    )
