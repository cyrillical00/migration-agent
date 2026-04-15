"""
Porcupine — Streamlit dashboard.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from ingestion.polymarket import fetch_markets, fetch_market, Market
from signals.engine import run_ensemble, MODELS, EnsembleResult, _query_model

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Porcupine",
    page_icon="🦔",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stSidebar"] { min-width: 220px; max-width: 220px; }
  .delta-pos  { color: #00c853; font-weight: 700; }
  .delta-neg  { color: #ff1744; font-weight: 700; }
  .delta-flat { color: #9e9e9e; }
  .model-card { border: 1px solid #2a2a2a; border-radius: 8px; padding: 16px; margin-bottom: 12px; background: #1a1a1a; }
  .prob-big   { font-size: 2.2rem; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(p: float | None) -> str:
    return f"{p * 100:.1f}%" if p is not None else "—"

def _delta_html(delta: float | None) -> str:
    if delta is None:
        return '<span class="delta-flat">—</span>'
    pct = delta * 100
    sign = "+" if pct >= 0 else ""
    cls = "delta-pos" if pct > 1 else ("delta-neg" if pct < -1 else "delta-flat")
    return f'<span class="{cls}">{sign}{pct:.1f}%</span>'

def _conf_badge(conf: str | None) -> str:
    colors = {"high": "#00b0ff", "medium": "#ffab00", "low": "#ff6d00"}
    c = (conf or "").lower()
    color = colors.get(c, "#9e9e9e")
    return f'<span style="background:{color};color:#000;padding:2px 8px;border-radius:10px;font-size:0.75rem;font-weight:700">{c.upper() or "—"}</span>'

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


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🦔 Porcupine")
    st.caption("Prediction market signal engine")
    st.divider()
    page = st.radio(
        "Navigate",
        ["Markets", "Signal", "Compare"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Models active")
    for m in MODELS:
        st.caption(f"• {m['label']}")


# ---------------------------------------------------------------------------
# Page: Markets
# ---------------------------------------------------------------------------

if page == "Markets":
    st.header("Live Markets")
    st.caption("Top active Polymarket markets by 24-hour volume. Refreshes every 2 minutes.")

    col_n, col_refresh = st.columns([3, 1])
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

    # Render as a clean table
    import pandas as pd
    df = pd.DataFrame(rows)
    df["implied_prob_%"] = (df["implied_prob"] * 100).round(1).astype(str) + "%"
    df["volume_fmt"] = df["volume"].apply(
        lambda v: f"${v:,.0f}" if v else "—"
    )
    df["market_id"] = df["condition_id"].str[:20] + "…"

    st.dataframe(
        df[["market_id", "question", "implied_prob_%", "volume_fmt", "end_date"]].rename(columns={
            "market_id":    "Market ID",
            "question":     "Question",
            "implied_prob_%": "Implied Prob",
            "volume_fmt":   "Volume (USDC)",
            "end_date":     "Ends",
        }),
        use_container_width=True,
        hide_index=True,
        height=min(80 + len(df) * 35, 700),
    )

    st.divider()
    st.caption("Paste any Market ID into the **Signal** page to run the LLM ensemble.")
    selected = st.selectbox(
        "Or pick one to signal now →",
        options=[""] + [r["condition_id"] for r in rows],
        format_func=lambda cid: "Select…" if not cid else next(
            (r["question"][:70] for r in rows if r["condition_id"] == cid), cid
        ),
    )
    if selected:
        st.session_state["signal_market_id"] = selected
        st.switch_page if hasattr(st, "switch_page") else None  # no-op on older streamlit
        # Navigate to signal page via rerun trick
        st.session_state["_nav"] = "Signal"
        st.rerun()


# ---------------------------------------------------------------------------
# Page: Signal
# ---------------------------------------------------------------------------

elif page == "Signal":
    st.header("Signal")
    st.caption("Run the LLM ensemble on a single market.")

    default_id = st.session_state.pop("signal_market_id", "")

    market_id_input = st.text_input(
        "Market condition ID",
        value=default_id,
        placeholder="0x…",
    )

    if not market_id_input:
        st.info("Enter a market condition ID above. You can copy one from the **Markets** page.")
        st.stop()

    # Fetch market metadata
    with st.spinner("Fetching market…"):
        try:
            market = fetch_market(market_id_input.strip())
        except Exception as exc:
            st.error(str(exc))
            st.stop()

    st.subheader(market.question)

    c1, c2, c3 = st.columns(3)
    c1.metric("Market price", _pct(market.implied_prob), help="Polymarket YES token price")
    c2.metric("Ends", (market.end_date or "—")[:10])
    c3.metric("Volume", f"${market.volume:,.0f}" if market.volume else "—")

    st.divider()

    run_btn = st.button("▶  Run ensemble", type="primary", use_container_width=False)

    if run_btn or st.session_state.get("_last_signal_id") == market_id_input:
        st.session_state["_last_signal_id"] = market_id_input

        signals = []
        progress_area = st.empty()

        for i, model_cfg in enumerate(MODELS):
            with progress_area.container():
                for j, mc in enumerate(MODELS):
                    done = j < i
                    active = j == i
                    icon = "✓" if done else ("⟳" if active else "·")
                    label = mc["label"]
                    st.caption(f"{icon} {label}" + (" …" if active else ""))

            sig = _query_model(model_cfg, market)
            signals.append(sig)

        progress_area.empty()

        # Compute mean
        estimates = [s.estimate for s in signals if s.ok]
        mean = sum(estimates) / len(estimates) if estimates else None

        # Summary row
        st.divider()
        sa, sb, sc = st.columns(3)
        sa.metric("Ensemble mean", _pct(mean))
        if mean is not None and market.implied_prob is not None:
            delta = mean - market.implied_prob
            sb.metric(
                "vs Market",
                f"{'+' if delta >= 0 else ''}{delta*100:.1f}%",
                delta=round(delta * 100, 1),
                delta_color="normal",
            )
        sc.metric("Models responded", f"{len(estimates)} / {len(signals)}")

        st.divider()
        st.subheader("Per-model breakdown")

        for sig in signals:
            with st.container():
                cols = st.columns([2, 1, 1, 1, 3])
                cols[0].markdown(f"**{sig.model_label}**")
                if sig.ok:
                    cols[1].markdown(f"**{_pct(sig.estimate)}**")
                    delta = market.delta(sig.estimate)
                    cols[2].markdown(_delta_html(delta), unsafe_allow_html=True)
                    cols[3].markdown(_conf_badge(sig.confidence), unsafe_allow_html=True)
                    cols[4].caption(sig.rationale or "")
                else:
                    cols[1].markdown("—")
                    cols[2].markdown("—")
                    cols[3].markdown("—")
                    cols[4].caption(f"⚠ {sig.error}")
                st.divider()

        # Persist to Supabase if logged in
        try:
            from auth.session import load_session
            from db.supabase_client import insert_signal_run
            sess = load_session()
            if sess:
                result = EnsembleResult(market_id=market.condition_id)
                result.signals = signals
                run_id = insert_signal_run(
                    market_id=market.condition_id,
                    results=result.to_json_list(),
                    access_token=sess["access_token"],
                    user_id=sess["user_id"],
                )
                st.caption(f"Saved → run `{run_id[:8]}…`")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Page: Compare
# ---------------------------------------------------------------------------

elif page == "Compare":
    st.header("Compare")
    st.caption("Run the ensemble across the top N markets and rank by signal strength.")

    col_top, col_run = st.columns([3, 1])
    with col_top:
        top_n = st.slider("Markets to compare", 3, 20, 10, step=1)
    with col_run:
        st.write("")
        run_compare = st.button("▶  Run compare", type="primary", use_container_width=True)

    if not run_compare:
        st.info("Set the number of markets above and click **Run compare**.")
        st.stop()

    with st.spinner("Fetching markets…"):
        try:
            rows = _cached_fetch(top_n)
        except Exception as exc:
            st.error(str(exc))
            st.stop()

    results = []
    progress = st.progress(0, text="Running ensemble…")

    for i, row in enumerate(rows):
        market = _dict_to_market(row)
        progress.progress((i) / len(rows), text=f"[{i+1}/{len(rows)}] {market.question[:55]}…")

        signals = []
        for model_cfg in MODELS:
            sig = _query_model(model_cfg, market)
            signals.append(sig)

        estimates = [s.estimate for s in signals if s.ok]
        mean = sum(estimates) / len(estimates) if estimates else None
        delta = (mean - market.implied_prob) if (mean is not None and market.implied_prob is not None) else None

        results.append({
            "market":  market,
            "signals": signals,
            "mean":    mean,
            "delta":   delta,
        })

    progress.empty()

    # Sort by abs delta
    results.sort(key=lambda r: abs(r["delta"]) if r["delta"] is not None else 0, reverse=True)

    st.divider()
    st.subheader("Results — ranked by signal strength")

    import pandas as pd
    summary_rows = []
    for rank, r in enumerate(results, 1):
        m = r["market"]
        delta = r["delta"]
        ok_count = sum(1 for s in r["signals"] if s.ok)
        summary_rows.append({
            "#":            rank,
            "Question":     m.question[:65],
            "Market":       _pct(m.implied_prob),
            "Ensemble":     _pct(r["mean"]),
            "Delta":        f"{'+' if (delta or 0) >= 0 else ''}{(delta or 0)*100:.1f}%",
            "Models":       f"{ok_count}/{len(r['signals'])}",
            "Volume":       f"${m.volume:,.0f}" if m.volume else "—",
        })

    df = pd.DataFrame(summary_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Cache for Supabase
    try:
        from auth.session import load_session
        from db.supabase_client import insert_signal_run
        sess = load_session()
        if sess:
            for r in results:
                ens = EnsembleResult(market_id=r["market"].condition_id)
                ens.signals = r["signals"]
                insert_signal_run(
                    market_id=r["market"].condition_id,
                    results=ens.to_json_list(),
                    access_token=sess["access_token"],
                    user_id=sess["user_id"],
                )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Handle nav from Markets page
# ---------------------------------------------------------------------------

if st.session_state.get("_nav") == "Signal":
    del st.session_state["_nav"]
