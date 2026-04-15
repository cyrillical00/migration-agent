<p align="center">
  <img src="images/porcupine.png" width="160" alt="Porcupine logo" />
</p>

# Porcupine

Private prediction market signal engine. Fetches live Polymarket markets, queries three LLM models for independent probability estimates, and surfaces a delta signal via CLI. Invite-only, stored in Supabase, auth via magic link.

---

## Quick Start

```bash
# 1. Install dependencies
# supabase pulls pyiceberg which needs C++ build tools — install its sub-packages
# individually to avoid that. Run these commands in order:
pip install litellm[all] anthropic tiktoken tokenizers
pip install py-clob-client
pip install "storage3==0.8.1"   # newer storage3 requires pyiceberg (needs C++ build tools)
pip install supabase-auth supabase-functions postgrest gotrue realtime supafunc supabase
pip install typer[all] rich keyring python-dotenv tenacity httpx

# 2. Copy and fill in secrets
cp .env.example .env
# edit .env — add SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY

# 3. Log in (must be pre-invited by admin in Supabase dashboard)
python porcupine.py auth login --email you@example.com

# 4. Fetch live markets
python porcupine.py fetch

# 5. Run signal on a market
python porcupine.py signal <condition_id>

# 6. Compare across top 10 markets
python porcupine.py compare --top 10
```

To install as a system command (`porcupine` instead of `python porcupine.py`):

```bash
# Run as admin (cyril) for machine-wide install
pip install -e .
porcupine fetch
```

---

## Commands

| Command | Description |
|---------|-------------|
| `porcupine fetch [-n N]` | Pull top N active markets (default 20), sorted by volume. Caches in Supabase. |
| `porcupine signal <id>` | Run LLM ensemble on one market. Shows per-model estimate + delta vs market price. |
| `porcupine compare [--top N]` | Run ensemble across top N markets, ranked by signal strength (abs delta). |
| `porcupine auth login` | Send magic link, open browser callback, store token in OS keychain. |
| `porcupine auth status` | Show current login state. |
| `porcupine auth logout` | Clear keychain session. |

---

## Supabase Setup

### Schema

Run this SQL in your Supabase project (SQL Editor → New Query):

```sql
-- Market cache (public read, no RLS needed)
create table markets (
  id text primary key,
  question text not null,
  implied_prob numeric,
  volume numeric,
  end_date text,
  fetched_at timestamptz default now()
);

-- Signal runs (RLS-protected — users see only their own rows)
create table signal_runs (
  id uuid default gen_random_uuid() primary key,
  market_id text references markets(id),
  user_id uuid references auth.users(id),
  run_at timestamptz default now(),
  results jsonb
);

alter table signal_runs enable row level security;

create policy "users see own runs"
  on signal_runs for select
  using (auth.uid() = user_id);

create policy "users insert own runs"
  on signal_runs for insert
  with check (auth.uid() = user_id);
```

### Inviting Users

Supabase does not allow self-signup by default. To invite users:
1. Supabase dashboard → **Authentication → Users → Invite user**
2. Enter their email. They'll receive a magic link.
3. On first login they'll be added to `auth.users` — RLS kicks in automatically.

---

## Technical Notes

### Architecture

```
porcupine/
├── cli/main.py              Typer app — all commands
├── ingestion/polymarket.py  py-clob-client wrapper — normalized Market objects
├── signals/
│   ├── engine.py            LiteLLM orchestration, JSON extraction, retry logic
│   └── prompts.py           CoT elicitation prompts (system + user)
├── db/supabase_client.py    Supabase writes/reads, RLS-aware
├── auth/session.py          Magic link flow, keyring persistence
├── porcupine.py             Root entry point
├── litellm_config.yaml      Optional proxy config
└── .env.example
```

### LiteLLM Routing

The signal engine calls LiteLLM inline (no proxy server required). Models are queried sequentially to avoid parallel rate-limit contention:

1. **Claude Sonnet** (`claude-sonnet-4-20250514`) — primary, best calibration
2. **Gemini Flash** (`gemini/gemini-2.0-flash`) — secondary, fast
3. **Ollama qwen2.5-coder:32b** (`ollama/qwen2.5-coder:32b`) — local fallback, RTX 5090

If a model fails (API error or JSON parse failure after one retry), its slot shows as unavailable in the output. The ensemble mean uses only successful signals.

To run LiteLLM as a local proxy instead:
```bash
pip install litellm[proxy]
litellm --config litellm_config.yaml --port 4000
```

### Probability Prompt Design

LLMs are not calibrated forecasters by default — they anchor on salient numbers and produce round estimates. The CoT prompt (`signals/prompts.py`) forces:
1. Steel-man arguments for both sides
2. Base rate / reference class identification
3. Inside vs. outside view adjustment
4. Explicit probability statement before the JSON output

JSON extraction has two fallback layers: direct parse → regex extraction → retry with stripped prompt. Parse failures are captured as errors in the signal, not exceptions.

### Auth Token Storage

- **Backend:** OS keychain via `keyring` library — Windows Credential Manager on this machine
- **Service name:** `porcupine`
- **Keys stored:** `access_token`, `user_id`, `email`
- **Session persistence:** Token survives terminal restarts and reboots

The magic link callback flow uses a temporary local HTTP server on port 54321. Supabase appends the token as a URL fragment; a small JavaScript snippet in the served HTML POSTs it back to the server before redirecting.

### Windows Install Notes

- Python must be installed system-wide (not per-user) so both `cbot` and `cyril` profiles can access it
- Run `pip install -r requirements.txt` as `cyril` (admin) if packages aren't accessible from `cbot`
- Ollama is assumed to be running at `http://localhost:11434` with `qwen2.5-coder:32b` already loaded
- Windows Credential Manager handles keyring automatically — no extra backend config needed
- Port 54321 is used briefly during `auth login` only; it is not a persistent server

---

## Security

- All secrets in `.env` — never committed (`.gitignore` excludes it)
- Supabase RLS enabled on `signal_runs` — users can only read/write their own rows
- No self-signup — admin must invite via Supabase dashboard
- Anon key is public-safe but RLS gates all writes
- Rotate `ANTHROPIC_API_KEY` and `GOOGLE_API_KEY` immediately if exposed

---

## v2 Roadmap (not started)

- Brier score tracking + calibration curves across resolved markets
- Kalshi / Metaculus ingestion + cross-platform market matching
- Historical-accuracy-weighted ensemble (start static: Claude 40% / Gemini 35% / Ollama 25%)
- Streamlit web dashboard (read-only view of signal history)
- REST API (FastAPI) for programmatic access
- News feed aggregation as additional signal source
- Live trade execution (Polymarket L2 wallet, CLOB order placement)
