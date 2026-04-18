# Step 1: Foundation

**Status**: in progress
**Branch**: `step-1/foundation`
**Milestone**: skeleton runs locally; no real connector calls; all tables migrated; Slack app registers; dashboard renders.

---

## Scope

Step 1 builds the skeleton everything else hangs on. No real connector calls. No migrations against real tenants. All state transitions are stubbed. The milestone is: `make dev` brings up a working local stack with the schema applied and both UIs reachable.

## Deliverables

### D1: State store schema

Alembic initial migration covering all tables from implementation-decisions.md §4.1:

- `source_inventory`
- `target_inventory`
- `identity_map`
- `wave_plan`
- `migration_job`
- `gate_decision`
- `audit_log` (with no-update/no-delete trigger)
- `permission_diff`
- `delta_queue`
- `rollback_state`
- `retention_ledger`
- `busy_season`
- `schedulability_override`

`updated_at` triggers on all tables that have it. Audit triggers on all tables except `audit_log`.

### D2: Agent skeleton

FastAPI app that starts and passes health check. Includes:

- `config.py` with Pydantic Settings, all env vars documented, fail-fast at startup.
- `deps.py` with DB session dependency.
- `observability/` with structlog JSON config and OTel setup (no-op exporter in dev).
- `api/health.py` returning `{"status": "ok", "env": ...}`.
- `slack/app.py` with Bolt async app mounted at `/slack/events`, a ping handler for `/ping`, and an app-home handler stub.
- Dockerfile (multi-stage, non-root user).

### D3: Connector Protocol

`connectors/protocol.py` defining:

- `NormalizedEntity`, `InventoryResult`, `ActionInput`, `ActionResult`, `ActionError` Pydantic models.
- `Connector` Protocol class.
- Connector registry (`get_connector`).

Normalized entity models in `state/models/normalized/entities.py` covering all entity types from implementation-decisions.md §5.2.

### D4: SQLAlchemy models

`state/models/core.py` with SQLAlchemy 2.x async declarative models for all tables. Includes `updated_at` event listeners. Separate `BaseModel` with shared columns.

### D5: Dashboard skeleton

Next.js 14 App Router project with:

- shadcn/ui initialized (Button, Card, Badge, Table components installed).
- Tailwind configured, dark mode default.
- App shell: sidebar nav (Inventory, Identity Map, Waves, Gates, Audit Log) + header.
- Stub pages for each section showing "coming in Step 2" placeholders.
- `lib/api.ts` with typed fetch wrapper pointing at agent base URL.
- `lib/supabase.ts` with Supabase JS client (realtime subscriptions only).

### D6: Slack app manifest

`infra/slack/app-manifest.yaml` for the dev Slack workspace.

### D7: docker-compose

Full local stack: postgres, agent, dashboard, graph-stub (FastAPI), slack-stub (FastAPI), fake-gcs.

### D8: Makefile

Targets: `dev`, `test`, `test-integration`, `migrate`, `fixtures`, `typecheck`, `lint`, `format`.

### D9: Scripts

- `scripts/dev-bootstrap.sh`: tool version checks, `.env` copy, docker pull, migrate, fixtures, docker-compose up.
- `scripts/load-fixtures.py`: seeds `busy_season`, a sample `wave_plan`, and a handful of `source_inventory` rows.
- `scripts/gen-mock-data.py`: generates larger synthetic datasets for load testing.

### D10: CI workflow

`.github/workflows/ci.yml`: lint + typecheck + unit tests + integration tests. Required checks.

### D11: Terraform skeleton

`infra/terraform/` with modules and staging/prod envs. Enough to `terraform init` and `plan` against a real GCP project. Actual apply deferred until staging project is confirmed (see QUESTIONS.md).

### D12: DR runbook

`docs/ops/dr-drill.md`: procedure for the quarterly Supabase DR drill. Phase 0 exit criterion.

---

## Acceptance criteria

- `make test` passes with no failures.
- `make typecheck` passes (Python mypy strict, TypeScript tsc strict).
- `make lint` passes (ruff + eslint).
- `make dev` brings up all containers; agent `/health` returns 200; dashboard renders the shell.
- All 13 tables exist in local Postgres after `make migrate`.
- `audit_log` rejects UPDATE and DELETE at the Postgres trigger level (verified in integration test).
- Connector Protocol conformance test runs (no connectors yet; just the abstract test harness).

---

## Out of scope for Step 1

- Real connector implementations (MS Graph, Google, Slack, JumpCloud). Stubs only.
- Phase orchestration logic. State machine shell only.
- LLM calls. Wrapper module scaffolded but no real calls.
- Binary Authorization, VPC Service Controls, IAP. These live in Step 4 hardening.
- Staging deploy. CI only; deploy-staging.yml scaffolded but not wired to real GCP.
