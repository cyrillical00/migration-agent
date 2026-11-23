# HIPAA Readiness Agent

Full-lifecycle HIPAA Security Rule readiness assessment tool built with Streamlit and Claude.

**[Live Demo →](https://hipaa-readiness.streamlit.app)**

---

## What it does

A 5-tab Streamlit app that assesses HIPAA Security Rule readiness across all three safeguard categories, tracks Business Associate Agreements, cross-maps SOC2 overlaps, and generates a phased remediation roadmap powered by Claude.

| Tab | Contents |
|-----|---------|
| **Integrations** | Connect 10+ data sources or use Demo Mode |
| **Gap Assessment** | All 42 controls — Required vs Addressable scoring, per-control cards, gauge chart |
| **BAA Tracker** | Business Associate inventory with CRITICAL/HIGH/MEDIUM/LOW risk classification |
| **SOC2 Overlap** | Control crosswalk — what SOC2 work already covers HIPAA |
| **Remediation Roadmap** | Claude-generated 3-phase action plan, exportable as Jira-importable CSV |

## Demo

**Demo org: Meridian Health Tech** — 150-person SaaS Business Associate for 3 hospital EHR clients.

Toggle Demo Mode in the sidebar. No credentials required.

- Overall readiness: **70.7% (Partial)**
- Critical BAA gaps: **5** (Slack, Google Workspace, DataDog, Snowflake, Retool)
- SOC2 Type I coverage: **~46%** of HIPAA controls partially satisfied
- Roadmap generated in **< 5 seconds**

## Stack

- **Python 3.11+** · **Streamlit** · **Plotly** · **Pandas**
- **Anthropic Claude API** (claude-sonnet-4-6) — two calls: assessment analysis + roadmap generation
- **fpdf2** — PDF report export

## Run locally

```bash
git clone https://github.com/cyrillical00/hipaa-readiness-agent
cd hipaa-readiness-agent
pip install -r requirements.txt

# Add your API key
echo 'ANTHROPIC_API_KEY = "sk-ant-..."' >> .streamlit/secrets.toml

streamlit run app.py
```

## Connectors

| Connector | HIPAA Signals |
|-----------|--------------|
| **Okta** | MFA requirement and session idle timeout (read from the sign-on policy rules), password length and lockout settings, active user count. Signals the API cannot show, such as shared accounts and log retention, are reported as not measured |
| **AWS** | S3 encryption, CloudTrail, KMS, log retention |
| **Google Workspace** | Email TLS, DLP, audit log retention, BAA status |
| **Jamf / Kandji** | FileVault %, screen lock, MDM enrollment % |
| **Intune** | BitLocker %, compliance policy % |
| **GitHub** | 2FA requirement, branch protection, secret scanning |
| **Jira** | Open HIPAA tickets, remediation SLA tracking |
| **Confluence** | Policy doc existence, last-reviewed dates |
| **Manual CSV** | Template-based upload for any control |

All connectors support Demo Mode — no credentials required.

## Scoring Logic

```
Required controls:
  Implemented         → 100 pts
  Partial             → 50 pts   (HIGH gap)
  Not Implemented     → 0 pts    (CRITICAL gap)

Addressable controls:
  Implemented         → 100 pts
  N/A (Documented)    → 100 pts  (fully valid under HIPAA)
  Partial             → 60 pts
  Not Implemented + Alt Control → 70 pts
  Not Implemented     → 0 pts    (HIGH gap)
```

Readiness bands: **Not Ready** (0–49%) · **Partial** (50–74%) · **Nearing Ready** (75–89%) · **Ready** (90–100%)

## Deploy to Streamlit Community Cloud

1. Fork this repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → connect repo
3. Main file: `app.py`
4. Add secrets:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   # All other secrets optional — app runs in Demo Mode without them
   ```

## Project Structure

```
├── app.py                     # Entry point — org context, sidebar, session state
├── pages/
│   ├── 1_Integrations.py      # Connector tabs + manual CSV upload
│   ├── 2_Gap_Assessment.py    # 42-control scoring, gauge, Claude analysis
│   ├── 3_BAA_Tracker.py       # BAA inventory, risk classification
│   ├── 4_SOC2_Overlap.py      # Crosswalk analysis
│   └── 5_Remediation_Roadmap.py  # Claude roadmap generation + export
├── engine/
│   ├── scorer.py              # Required/Addressable scoring
│   ├── baa_engine.py          # BAA risk classification
│   ├── soc2_crosswalk.py      # Overlap computation
│   ├── roadmap_generator.py   # Claude API calls
│   └── control_mapper.py      # Connector signals → HIPAA controls
├── connectors/                # 10+ data source connectors
├── data/
│   ├── hipaa_controls.json    # 42-control HIPAA Security Rule library
│   ├── soc2_hipaa_crosswalk.json  # TSC ↔ HIPAA mapping (42 entries)
│   ├── sample_assessment.py   # Demo org control statuses
│   └── sample_baas.py         # Demo BAA inventory (15 vendors)
└── utils/
    ├── pdf_exporter.py        # PDF assessment report
    └── csv_exporter.py        # CSV exports (assessment, roadmap, BAAs)
```

## Key Differentiator vs SOC2 Tools

| | SOC2 | HIPAA |
|--|------|-------|
| Framework | AICPA Trust Services Criteria | HHS Security Rule (3 safeguard categories) |
| Unique concept | TSC scope | Required vs Addressable distinction |
| Primary differentiator | TSC gap lifecycle | **BAA Tracker** (no SOC2 equivalent) + SOC2 crosswalk |
| Demo narrative | Tech company seeking SOC2 | SaaS BA for hospital EHR client |
| Accent color | Teal | Indigo (#6366F1) |

---

*HIPAA Security Rule (45 CFR §164.300–.318) · This tool assists with readiness assessment and does not constitute legal advice.*
