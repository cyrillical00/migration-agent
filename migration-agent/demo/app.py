"""Migration Agent -- Streamlit demo/presentation layer.

Reads from the same Postgres as the agent (or uses bundled mock data if
DATABASE_URL is not set). Designed for demos and stakeholder presentations;
not a replacement for the Next.js production dashboard.

Run: streamlit run demo/app.py
"""
from __future__ import annotations

import os

import streamlit as st

# ---- page config ----
st.set_page_config(
    page_title="Migration Agent",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATABASE_URL = os.getenv("MIGRATION_AGENT_DATABASE_URL", "")
USE_MOCK = not DATABASE_URL

# ---- mock data ----
MOCK_INVENTORY = [
    {"entity_type": "user", "count": 47, "source": "contoso.com"},
    {"entity_type": "shared_mailbox", "count": 12, "source": "contoso.com"},
    {"entity_type": "group", "count": 31, "source": "contoso.com"},
    {"entity_type": "sharepoint_site", "count": 8, "source": "contoso.com"},
    {"entity_type": "teams_channel", "count": 64, "source": "contoso.com"},
    {"entity_type": "calendar_resource", "count": 6, "source": "contoso.com"},
    {"entity_type": "license", "count": 52, "source": "contoso.com"},
]

MOCK_WAVES = [
    {
        "wave_number": 1,
        "name": "Wave 1 — Corp Engineering",
        "status": "approved",
        "members": 18,
        "scheduled_start": "2026-05-12 22:00",
        "canary": "alice@contoso.com",
    },
    {
        "wave_number": 2,
        "name": "Wave 2 — Operations",
        "status": "draft",
        "members": 14,
        "scheduled_start": "2026-05-19 22:00",
        "canary": "TBD",
    },
    {
        "wave_number": 3,
        "name": "Wave 3 — Tax (post busy season)",
        "status": "draft",
        "members": 15,
        "scheduled_start": "2026-05-26 22:00",
        "canary": "TBD",
    },
]

MOCK_GATES = [
    {"gate": 1, "label": "Scope confirmation", "status": "open"},
    {"gate": 2, "label": "Identity mapping approval", "status": "pending"},
    {"gate": 3, "label": "Wave schedule approval", "status": "pending"},
    {"gate": 4, "label": "Per-wave go/no-go", "status": "pending"},
    {"gate": 5, "label": "Proceed to next wave", "status": "pending"},
    {"gate": 6, "label": "Source teardown approval", "status": "pending"},
    {"gate": 7, "label": "Final sign-off (24h cooldown)", "status": "pending"},
]

MOCK_AUDIT = [
    {"timestamp": "2026-04-17 17:30:00", "actor": "agent", "action": "INSERT:busy_season", "result": "ok"},
    {"timestamp": "2026-04-17 17:30:01", "actor": "agent", "action": "INSERT:wave_plan", "result": "ok"},
    {"timestamp": "2026-04-17 17:30:02", "actor": "agent", "action": "INSERT:source_inventory", "result": "ok"},
    {"timestamp": "2026-04-17 17:30:02", "actor": "agent", "action": "INSERT:source_inventory", "result": "ok"},
    {"timestamp": "2026-04-17 17:30:02", "actor": "agent", "action": "INSERT:source_inventory", "result": "ok"},
]

MOCK_BUSY_SEASONS = [
    {
        "name": "Tax Returns 2026",
        "hard_freeze_start": "2026-01-15",
        "hard_freeze_end": "2026-04-18",
        "status": "ACTIVE",
    },
    {
        "name": "Extensions 2026",
        "hard_freeze_start": "2026-09-15",
        "hard_freeze_end": "2026-10-15",
        "status": "upcoming",
    },
]

STATUS_ICON = {
    "approved": "🟢",
    "open": "🟡",
    "in_progress": "🔵",
    "draft": "⚪",
    "pending": "⚪",
    "complete": "✅",
    "ACTIVE": "🔴",
    "upcoming": "🟡",
}


def badge(status: str) -> str:
    return f"{STATUS_ICON.get(status, '⚪')} {status}"


# ---- sidebar ----
with st.sidebar:
    st.markdown("## 🔄 Migration Agent")
    st.caption("Demo / Presentation Layer")
    st.divider()
    if USE_MOCK:
        st.info("Mock data active.\nSet `MIGRATION_AGENT_DATABASE_URL` to use live DB.", icon="ℹ️")
    else:
        st.success("Connected to live DB", icon="✅")
    st.divider()
    page = st.radio(
        "Navigate",
        ["Overview", "Inventory", "Waves", "Gates", "Busy Season", "Audit Log"],
        label_visibility="collapsed",
    )

# ============================
# Overview
# ============================
if page == "Overview":
    st.title("Migration Agent")
    st.caption("Enterprise email and productivity migration — O365 → O365 or O365 → Google Workspace + GCP.")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Entities discovered", sum(r["count"] for r in MOCK_INVENTORY))
    col2.metric("Waves planned", len(MOCK_WAVES))
    col3.metric("Gates open", sum(1 for g in MOCK_GATES if g["status"] == "open"))
    col4.metric("Busy season", "ACTIVE 🔴")

    st.divider()
    st.subheader("Phase status")

    phases = [
        ("0", "Preflight", "complete", "Exit criteria met."),
        ("1", "Discovery & Inventory", "open", "Awaiting Gate 1 — scope confirmation."),
        ("2", "Identity Mapping", "pending", "Blocked on Gate 1."),
        ("3", "Wave Planning", "pending", "Blocked on Gate 2."),
        ("4", "Pre-migration Prep", "pending", "Blocked on Gate 3."),
        ("5", "Wave Execution", "pending", "Blocked on Gate 4 (per-wave go/no-go)."),
        ("6", "Post-migration Validation", "pending", "Blocked on Gate 5."),
        ("7", "Source Teardown", "pending", "Blocked on Gates 6 + 7."),
    ]
    for pid, name, status, note in phases:
        c1, c2, c3 = st.columns([0.5, 2, 5])
        c1.markdown(f"**{pid}**")
        c2.markdown(name)
        c3.markdown(f"{badge(status)} — {note}")

    st.divider()
    st.subheader("Core invariants")
    st.markdown(
        "🔒 **Zero data loss** — source stays read-only until target parity is verified.  \n"
        "🔒 **Zero business-hours access loss** — agent refuses mutating actions during affected users' in-hours windows. "
        "Tax users during busy season are considered in-hours 24/7."
    )

# ============================
# Inventory
# ============================
elif page == "Inventory":
    st.title("Source Inventory")
    st.caption("Entities discovered from source tenant during Phase 1.")

    if USE_MOCK:
        st.warning("Showing mock data — Phase 1 discovery has not run yet.", icon="⚠️")

    import pandas as pd

    df = pd.DataFrame(MOCK_INVENTORY)
    df.columns = ["Entity Type", "Count", "Source Tenant"]

    col1, col2 = st.columns([3, 2])
    with col1:
        st.dataframe(df, use_container_width=True, hide_index=True)
    with col2:
        st.bar_chart(df.set_index("Entity Type")["Count"])

    st.divider()
    total = sum(r["count"] for r in MOCK_INVENTORY)
    for row in MOCK_INVENTORY:
        st.progress(row["count"] / total, text=f"{row['entity_type']}  —  {row['count']}")

# ============================
# Waves
# ============================
elif page == "Waves":
    st.title("Wave Plan")
    st.caption(
        "Each wave has a canary (migrated 48-72h ahead), a scheduled window outside business hours, "
        "and a per-wave Gate 4 go/no-go."
    )

    for wave in MOCK_WAVES:
        with st.expander(
            f"Wave {wave['wave_number']} — {wave['name']}  {STATUS_ICON.get(wave['status'], '')}",
            expanded=wave["wave_number"] == 1,
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Status", wave["status"])
            c2.metric("Members", wave["members"])
            c3.metric("Scheduled start", wave["scheduled_start"])
            c4.metric("Canary", wave["canary"])

            if wave["status"] == "approved":
                st.success("Wave approved. Canary migrates 48-72h before wave start.")
            else:
                st.info("Draft — Gate 3 (wave schedule approval) must close first.")

# ============================
# Gates
# ============================
elif page == "Gates":
    st.title("Gates")
    st.caption("Seven gates. No gate is skippable. Each records approver, decision, and reason.")

    gate_notes = {
        1: "Scope confirmation — inventory report reviewed and signed.",
        2: "Identity mapping approval — LLM-proposed mappings confirmed by human.",
        3: "Wave schedule approval — busy season checked, canaries named.",
        4: "Per-wave go/no-go — fires once per wave before cutover.",
        5: "Proceed to next wave — post-wave reconciliation passed.",
        6: "Source teardown approval — all waves complete, user sign-off.",
        7: "Final sign-off — 24h cooling-off timer before deletion commands execute.",
    }

    for g in MOCK_GATES:
        icon = STATUS_ICON.get(g["status"], "⚪")
        with st.expander(f"{icon} Gate {g['gate']} — {g['label']}", expanded=g["status"] == "open"):
            st.markdown(gate_notes[g["gate"]])
            if g["status"] == "open":
                st.warning("Awaiting human approval. Agent is paused at this gate.", icon="🚧")
            else:
                st.markdown(f"**Status:** {badge(g['status'])}")

# ============================
# Busy Season
# ============================
elif page == "Busy Season":
    st.title("Busy Season Policy")
    st.caption(
        "Hard freezes block migrations 24/7 for tax-side users. "
        "Soft freeze (2 weeks before, 1 week after) requires a human override with a recorded reason."
    )

    for season in MOCK_BUSY_SEASONS:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"**{season['name']}**")
            c2.markdown(f"Start: `{season['hard_freeze_start']}`")
            c3.markdown(f"End: `{season['hard_freeze_end']}`")
            s = season["status"]
            c4.markdown(f"{STATUS_ICON.get(s, '⚪')} {s}")

    st.divider()
    st.info(
        "The `can_execute()` primitive enforces these dates in code. "
        "No agent-level override exists — a human override creates a second, separately-logged audit entry.",
        icon="🔒",
    )

# ============================
# Audit Log
# ============================
elif page == "Audit Log":
    st.title("Audit Log")
    st.caption("Append-only. Postgres trigger blocks UPDATE and DELETE at the DB level.")

    import pandas as pd

    df = pd.DataFrame(MOCK_AUDIT)
    df.columns = ["Timestamp", "Actor", "Action", "Result"]
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.info(
        "In production, this table streams to a GCS write-once bucket with 7-year retention. "
        "Any UPDATE or DELETE raises a Postgres exception — not enforced at the app layer.",
        icon="🔒",
    )
