"""
Porcupine — Streamlit dashboard.

Run locally:  streamlit run app.py
Deploy:       Streamlit Community Cloud → cyrillical00/porcupine → app.py
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Inject Streamlit secrets into env vars so LiteLLM / dotenv code picks them up
# ---------------------------------------------------------------------------
try:
    import streamlit as _st
    for _k in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OLLAMA_HOST",
                "SUPABASE_URL", "SUPABASE_KEY", "POLYMARKET_CLOB_HOST"):
        _v = _st.secrets.get(_k)
        if _v:
            os.environ[_k] = str(_v)
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd

from ingestion.polymarket import fetch_markets, fetch_market, Market
from signals.engine import MODELS, EnsembleResult, _query_model
from auth.web_auth import render_auth_gate, get_session, logout, render_account_page

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Porcupine",
    page_icon="🦔",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stSidebar"] { min-width: 230px; max-width: 230px; }
  .delta-pos  { color: #00c853; font-weight: 700; }
  .delta-neg  { color: #ff1744; font-weight: 700; }
  .delta-flat { color: #9e9e9e; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Auth gate — stops rendering and shows login if not authenticated
# ---------------------------------------------------------------------------

render_auth_gate()

# Everything below only runs when authenticated
session = get_session()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(p: float | None) -> str:
    return f"{p * 100:.1f}%" if p is not None else "—"


def _delta_html(delta: float | None) -> str:
    if delta is None:
        return '<span class="delta-flat">—</span>'
    pct  = delta * 100
    sign = "+" if pct >= 0 else ""
    cls  = "delta-pos" if pct > 1 else ("delta-neg" if pct < -1 else "delta-flat")
    return f'<span class="{cls}">{sign}{pct:.1f}%</span>'


def _conf_badge(conf: str | None) -> str:
    colors = {"high": "#00b0ff", "medium": "#ffab00", "low": "#ff6d00"}
    c     = (conf or "").lower()
    color = colors.get(c, "#9e9e9e")
    label = c.upper() if c else "—"
    return (
        f'<span style="background:{color};color:#000;padding:2px 8px;'
        f'border-radius:10px;font-size:0.75rem;font-weight:700">{label}</span>'
    )


@st.cache_data(ttl=120, show_spinner=False)
def _cached_fetch(limit: int) -> list[dict]:
    markets = fetch_markets(limit=limit)
    return [
        {
            "condition_id": m.condition_id,
            "question":     m.question,
            "implied_prob": m.implied_prob,
            "volume":       m.volume,
            "end_date":     (m.end_date or "")[:10],
        }
        for m in markets
    ]


def _dict_to_market(d: dict) -> Market:
    return Market(
        condition_id=d["condition_id"],
        question=d["question"],
        implied_prob=d["implied_prob"],
        volume=d["volume"],
        end_date=d["end_date"],
    )


def _save_run(market_id: str, signals: list) -> None:
    if not session:
        return
    try:
        from db.supabase_client import insert_signal_run
        ens = EnsembleResult(market_id=market_id)
        ens.signals = signals
        run_id = insert_signal_run(
            market_id=market_id,
            results=ens.to_json_list(),
            access_token=session["access_token"],
            user_id=session["user_id"],
        )
        st.caption(f"Saved → `{run_id[:8]}…`")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🦔 Porcupine")
    st.caption("Prediction market signal engine")
    st.divider()

    page = st.radio(
        "Navigate",
        ["Markets", "Signal", "Compare", "Account"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Models")
    for m in MODELS:
        st.caption(f"• {m['label']}")

    st.divider()
    if session:
        st.caption(f"Signed in as  \n**{session.get('email', '')}**")
    if st.button("Sign out", use_container_width=True):
        logout()
        st.rerun()


# ---------------------------------------------------------------------------
# Page: Markets
# ---------------------------------------------------------------------------

if page == "Markets":
    st.header("Live Markets")
    st.caption("Top active Polymarket markets by 24-hour volume · refreshes every 2 min")

    col_n, col_refresh = st.columns([4, 1])
    with col_n:
        limit = st.slider("Markets to show", 5, 50, 20, step=5)
    with col_refresh:
        st.write("")
        if st.button("↺ Refresh", use_container_width=True):
            st.cache_data.clear()

    with st.spinner("Fetching markets…"):
        try:
            rows = _cached_fetch(limit)
        except Exception as exc:
            st.error(f"Polymarket API error: {exc}")
            st.stop()

    if not rows:
        st.warning("No active markets returned.")
        st.stop()

    df = pd.DataFrame(rows)
    df["Implied Prob"] = (df["implied_prob"] * 100).round(1).astype(str) + "%"
    df["Volume (USDC)"] = df["volume"].apply(lambda v: f"${v:,.0f}" if v else "—")
    df["Market ID"] = df["condition_id"].str[:20] + "…"

    st.dataframe(
        df[["Market ID", "question", "Implied Prob", "Volume (USDC)", "end_date"]].rename(
            columns={"question": "Question", "end_date": "Ends"}
        ),
        use_container_width=True,
        hide_index=True,
        height=min(80 + len(df) * 35, 680),
    )

    st.divider()
    selected = st.selectbox(
        "Signal a market →",
        options=[""] + [r["condition_id"] for r in rows],
        format_func=lambda cid: "Pick one…" if not cid else next(
            (r["question"][:72] for r in rows if r["condition_id"] == cid), cid
        ),
    )
    if selected:
        st.session_state["signal_market_id"] = selected
        st.session_state["_nav_signal"] = True
        st.rerun()


# ---------------------------------------------------------------------------
# Page: Signal
# ---------------------------------------------------------------------------

elif page == "Signal":
    st.header("Signal")
    st.caption("Run the LLM ensemble on a single market.")

    default_id = st.session_state.pop("signal_market_id", "")

    market_id = st.text_input(
        "Market condition ID",
        value=default_id,
        placeholder="0x…",
    )

    if not market_id:
        st.info("Enter a market condition ID above, or pick one from the **Markets** page.")
        st.stop()

    with st.spinner("Fetching market…"):
        try:
            market = fetch_market(market_id.strip())
        except Exception as exc:
            st.error(str(exc))
            st.stop()

    st.subheader(market.question)

    c1, c2, c3 = st.columns(3)
    c1.metric("Market price", _pct(market.implied_prob))
    c2.metric("Ends", (market.end_date or "—")[:10])
    c3.metric("Volume", f"${market.volume:,.0f}" if market.volume else "—")

    st.divider()

    if not st.button("▶  Run ensemble", type="primary"):
        st.stop()

    # Run models one at a time, updating a live status area
    signals = []
    status  = st.empty()

    for i, model_cfg in enumerate(MODELS):
        with status.container():
            for j, mc in enumerate(MODELS):
                icon = "✓" if j < i else ("⟳" if j == i else "·")
                st.caption(f"{icon}  {mc['label']}" + (" …" if j == i else ""))
        sig = _query_model(model_cfg, market)
        signals.append(sig)

    status.empty()

    estimates = [s.estimate for s in signals if s.ok]
    mean      = sum(estimates) / len(estimates) if estimates else None

    # Summary metrics
    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Ensemble mean", _pct(mean))
    if mean is not None and market.implied_prob is not None:
        delta = mean - market.implied_prob
        m2.metric("vs Market", f"{'+' if delta >= 0 else ''}{delta*100:.1f}%",
                  delta=round(delta * 100, 1), delta_color="normal")
    m3.metric("Models responded", f"{len(estimates)} / {len(signals)}")

    # Per-model breakdown
    st.divider()
    st.subheader("Per-model breakdown")

    for sig in signals:
        cols = st.columns([2, 1, 1, 1, 4])
        cols[0].markdown(f"**{sig.model_label}**")
        if sig.ok:
            cols[1].markdown(f"**{_pct(sig.estimate)}**")
            cols[2].markdown(_delta_html(market.delta(sig.estimate)), unsafe_allow_html=True)
            cols[3].markdown(_conf_badge(sig.confidence), unsafe_allow_html=True)
            cols[4].caption(sig.rationale or "")
        else:
            cols[1].markdown("—")
            cols[2].markdown("—")
            cols[3].markdown("—")
            cols[4].caption(f"⚠ {sig.error}")
        st.divider()

    _save_run(market.condition_id, signals)


# ---------------------------------------------------------------------------
# Page: Compare
# ---------------------------------------------------------------------------

elif page == "Compare":
    st.header("Compare")
    st.caption("Run the ensemble across the top N markets and rank by signal strength.")

    col_n, col_btn = st.columns([4, 1])
    with col_n:
        top_n = st.slider("Markets to compare", 3, 20, 10)
    with col_btn:
        st.write("")
        run = st.button("▶  Run", type="primary", use_container_width=True)

    if not run:
        st.info("Set the number of markets and click **Run**.")
        st.stop()

    with st.spinner("Fetching markets…"):
        try:
            rows = _cached_fetch(top_n)
        except Exception as exc:
            st.error(str(exc))
            st.stop()

    results  = []
    progress = st.progress(0, text="Starting…")

    for i, row in enumerate(rows):
        market = _dict_to_market(row)
        progress.progress(i / len(rows), text=f"[{i+1}/{len(rows)}] {market.question[:55]}…")

        signals   = [_query_model(mc, market) for mc in MODELS]
        estimates = [s.estimate for s in signals if s.ok]
        mean      = sum(estimates) / len(estimates) if estimates else None
        delta     = (mean - market.implied_prob) if (mean is not None and market.implied_prob is not None) else None

        results.append({"market": market, "signals": signals, "mean": mean, "delta": delta})
        _save_run(market.condition_id, signals)

    progress.empty()

    results.sort(key=lambda r: abs(r["delta"]) if r["delta"] is not None else 0, reverse=True)

    st.divider()
    st.subheader("Ranked by signal strength")

    summary = []
    for rank, r in enumerate(results, 1):
        m = r["market"]
        d = r["delta"]
        summary.append({
            "#":        rank,
            "Question": m.question[:65],
            "Market %":   round((m.implied_prob or 0) * 100, 1),
            "Ensemble %": round((r["mean"] or 0) * 100, 1) if r["mean"] is not None else None,
            "Delta %":    round((d or 0) * 100, 1),
            "Models":   f"{sum(1 for s in r['signals'] if s.ok)}/{len(r['signals'])}",
            "Volume":   m.volume or 0,
        })

    st.dataframe(
        pd.DataFrame(summary),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Market %":   st.column_config.NumberColumn(format="%.1f%%"),
            "Ensemble %": st.column_config.NumberColumn(format="%.1f%%"),
            "Delta %":    st.column_config.NumberColumn(format="%+.1f%%"),
            "Volume":     st.column_config.NumberColumn(format="$%,.0f"),
        },
    )


# ---------------------------------------------------------------------------
# Page: Account
# ---------------------------------------------------------------------------

elif page == "Account":
    render_account_page()


# ---------------------------------------------------------------------------
# Handle nav redirect from Markets page
# ---------------------------------------------------------------------------

if st.session_state.pop("_nav_signal", False):
    # Force re-render on Signal page — page radio already set via session state
    pass
