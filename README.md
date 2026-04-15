<p align="center">
  <img src="porcupine/images/porcupine.png" width="160" alt="Porcupine logo" />
</p>

# Porcupine

Private prediction market signal engine. Fetches live Polymarket markets, queries three LLM models for independent probability estimates, and surfaces a delta signal via Streamlit dashboard and CLI. Invite-only, stored in Supabase, auth via email + password + TOTP MFA.

---

## Quick Start

```bash
# 1. Install dependencies
pip install litellm[all] anthropic tiktoken tokenizers
pip install py-clob-client
pip install "storage3==0.8.1"
pip install supabase-auth supabase-functions postgrest gotrue realtime supafunc supabase
pip install typer[all] rich keyring python-dotenv tenacity httpx streamlit pandas qrcode[pil]

# 2. Copy and fill in secrets
cp porcupine/.env.example porcupine/.env

# 3. Run the Streamlit app
streamlit run porcupine/app.py
```

See [`porcupine/README.md`](porcupine/README.md) for full CLI usage, Supabase schema, and architecture notes.
