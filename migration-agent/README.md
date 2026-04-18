# Migration Agent

Hybrid AI agent for enterprise email and productivity migration. Handles O365 tenant-to-tenant (Type A) and O365 to Google Workspace / GCP (Type B) migrations with per-phase human gates. Teams chat migration offers three variants (Teams, Google Chat, Slack).

## Doc inventory

Read in this order:

1. `README.md` — you are here. Project entry point and doc map.
2. `architecture.md` — the **what**. Invariants, architecture layers, phases, gates, handling rules. Authoritative design source.
3. `implementation-decisions.md` — the **how**. Stack, schema, interfaces, file layout, dev env, conventions. Pinned before coding.
4. `CLAUDE.md` — operating manual for Claude Code working in this repo. Rules of engagement, testing, PR discipline.
5. `step1-build-prompt.md` — current build scope. What to build this session.

When a new step opens, a new `stepN-build-prompt.md` lands. Earlier step prompts stay as historical record.

## Workflow rules

- **Planning is in Opus**, execution is in Sonnet (Claude Code).
- **No direct commits to main or remote.** Claude Code creates branches, produces diffs, surfaces them for human review.
- **Spec is the source of truth.** If code and spec disagree, raise a question; don't silently rewrite either.
- **Open questions go in `QUESTIONS.md`**, not inline in code. Batched and resolved by the human.

## Current status

Step 1 (Foundation) in progress. Steps 2-6 blocked until Step 1 milestone hits.

## Invariants (full treatment in architecture.md §2)

1. Zero user data loss. Source is read-only until target parity is verified.
2. Zero business-hours access loss. Agent refuses mutating actions during affected users' in-hours windows.

Both are enforced in code as primitives, not procedural reminders.

## Stack (summary; full in implementation-decisions.md §1)

- Agent: Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, Slack Bolt
- Dashboard: Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui, TanStack Query
- State store: Supabase (managed Postgres)
- Queue: Cloud Tasks
- Deploy: Cloud Run (agent), Vercel (dashboard), Supabase (state)
- Infra: Terraform
- Observability: structlog, OpenTelemetry, Cloud Logging + Cloud Trace

## Repo layout (summary; full in implementation-decisions.md §3)

```
migration-agent/
├── agent/              # FastAPI orchestrator (Python)
├── dashboard/          # Next.js
├── packages/           # Shared Python packages (connectors, models, state)
├── infra/              # Terraform
├── docs/               # architecture.md, implementation-decisions.md, CLAUDE.md, stepN prompts
├── scripts/
├── docker-compose.yml
└── README.md
```

## Quick start (dev)

```bash
cp .env.example .env
# Fill in required values
make dev
```

See `docs/CLAUDE.md` for the full dev env setup.
