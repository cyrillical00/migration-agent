"""
Tab 1 — Integrations
Connect data sources or use demo mode.
"""
import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from connectors.okta import OktaConnector, OKTA_DEMO_FINDINGS
from connectors.aws import AWSConnector, AWS_DEMO_FINDINGS
from connectors.google_workspace import GoogleWorkspaceConnector, GOOGLE_WORKSPACE_DEMO_FINDINGS
from connectors.jamf import JamfConnector, JAMF_DEMO_FINDINGS
from connectors.github import GitHubConnector, GITHUB_DEMO_FINDINGS
from connectors.jira import JiraConnector, JIRA_DEMO_FINDINGS
from connectors.confluence import ConfluenceConnector, CONFLUENCE_DEMO_FINDINGS
from connectors.intune import IntuneConnector, INTUNE_DEMO_FINDINGS
from connectors.gcp import GCPConnector, GCP_DEMO_FINDINGS

st.set_page_config(page_title="Integrations — HIPAA Agent", layout="wide")
st.markdown("# Integrations")
st.caption("Connect your infrastructure for automated HIPAA signal detection, or run in Demo Mode.")

if st.session_state.get("demo_mode"):
    st.success("**Demo Mode Active** — All connectors returning realistic mock data for Meridian Health Tech.", icon="🎭")
    # Auto-populate demo findings
    st.session_state.connector_findings = {
        "okta": OKTA_DEMO_FINDINGS,
        "aws": AWS_DEMO_FINDINGS,
        "google_workspace": GOOGLE_WORKSPACE_DEMO_FINDINGS,
        "jamf": JAMF_DEMO_FINDINGS,
        "github": GITHUB_DEMO_FINDINGS,
        "jira": JIRA_DEMO_FINDINGS,
        "confluence": CONFLUENCE_DEMO_FINDINGS,
    }

    # Display demo findings summary
    st.markdown("### Detected Signals (Demo)")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Identity & Access")
        okta = OKTA_DEMO_FINDINGS
        st.metric("MFA Enforced", "✅ Yes" if okta["mfa_enforced"] else "❌ No")
        st.metric("Active Users", okta["active_user_count"])
        st.metric("Auto-logoff", f"{okta['auto_logoff_minutes']} min")
        st.metric("Audit Log Retention", f"{okta['audit_log_retention_days']} days")

    with col2:
        st.markdown("#### Cloud Infrastructure")
        aws = AWS_DEMO_FINDINGS
        st.metric("S3 Encryption", "✅ All buckets" if aws["s3_default_encryption"] else "❌ Partial")
        st.metric("CloudTrail", "✅ Enabled" if aws["cloudtrail_enabled"] else "❌ Not enabled")
        st.metric("KMS in Use", "✅ Yes" if aws["kms_in_use"] else "❌ No")
        st.metric("Log Retention", f"{aws['log_retention_days']} days", delta="⚠️ Below 6yr HIPAA guidance", delta_color="inverse")

    with col3:
        st.markdown("#### Endpoint & Policy")
        jamf = JAMF_DEMO_FINDINGS
        st.metric("FileVault Coverage", f"{jamf['filevault_enabled_pct']}%", delta="⚠️ BYOD gap", delta_color="inverse")
        st.metric("MDM Enrollment", f"{jamf['mdm_enrollment_pct']}%", delta=f"{jamf.get('byod_device_count',0)} unmanaged BYOD", delta_color="inverse")
        gws = GOOGLE_WORKSPACE_DEMO_FINDINGS
        st.metric("Email TLS Enforced", "❌ Not confirmed" if not gws["tls_enforced_inbound"] else "✅ Yes")
        st.metric("GWS BAA", "❌ NOT EXECUTED" if not gws["baa_in_place"] else "✅ In place")

    st.divider()
    st.markdown("### HIPAA-Specific Risk Signals")
    risks = [
        ("🔴 CRITICAL", "Google Workspace BAA not executed — ePHI in Drive/email without agreement"),
        ("🔴 CRITICAL", "AWS log retention only 90 days — HIPAA audit logs should be retained 6 years"),
        ("🟠 HIGH", "22% of workforce using BYOD devices without MDM enrollment or FileVault"),
        ("🟠 HIGH", "Okta audit log retention 90 days — insufficient for HIPAA requirements"),
        ("🟡 MEDIUM", "Email TLS enforcement not confirmed for all outbound routes"),
        ("🟢 LOW", "MFA enforced for all users via Okta — strong authentication control"),
        ("🟢 LOW", "S3 encryption enabled on all 12 buckets with KMS — ePHI at rest secured"),
        ("🟢 LOW", "CloudTrail enabled across 2 trails — audit logging active"),
    ]
    for tier, msg in risks:
        st.markdown(f"**{tier}** — {msg}")

else:
    st.markdown("""
> **Demo Mode is off.** Enter credentials below to pull live signals from your infrastructure.
> All credentials are used only for read-only API calls and are never stored.
""")

    tab_names = ["Okta", "AWS", "Google Workspace", "Jamf / Kandji", "Intune", "GitHub", "Jira / Confluence", "Manual Upload"]
    tabs = st.tabs(tab_names)

    # Okta
    with tabs[0]:
        st.markdown("#### Okta — Identity & Access Management")
        st.caption("Reads: MFA policy, user list, password policy, session timeout, admin groups")
        col1, col2 = st.columns(2)
        okta_domain = col1.text_input("Okta Domain", placeholder="yourorg.okta.com")
        okta_token = col2.text_input("API Token (SSWS)", type="password")
        if st.button("Test & Connect Okta", key="okta_connect"):
            if okta_domain and okta_token:
                with st.spinner("Connecting to Okta..."):
                    try:
                        conn = OktaConnector(okta_token, okta_domain)
                    except ValueError as exc:
                        # Not an Okta host: nothing was sent.
                        conn = None
                        st.error(str(exc))
                    if conn is None:
                        pass
                    elif conn.test_connection():
                        findings = conn.to_hipaa_signals()
                        st.session_state.connector_findings["okta"] = findings
                        st.success("Connected! Okta signals loaded.")
                        st.json(findings)
                    else:
                        st.error("Connection failed. Check domain and API token.")
            else:
                st.warning("Enter domain and API token.")

    # AWS
    with tabs[1]:
        st.markdown("#### AWS — Cloud Infrastructure")
        st.caption("Reads: S3 encryption status, CloudTrail, KMS keys, log retention (read-only IAM policy recommended)")
        col1, col2, col3 = st.columns(3)
        aws_key = col1.text_input("Access Key ID", type="password")
        aws_secret = col2.text_input("Secret Access Key", type="password")
        aws_region = col3.text_input("Region", value="us-east-1")
        if st.button("Test & Connect AWS", key="aws_connect"):
            if aws_key and aws_secret:
                with st.spinner("Connecting to AWS..."):
                    conn = AWSConnector(aws_key, aws_secret, aws_region)
                    if conn.test_connection():
                        findings = conn.to_hipaa_signals()
                        st.session_state.connector_findings["aws"] = findings
                        st.success("Connected! AWS signals loaded.")
                        st.json(findings)
                    else:
                        st.error("Connection failed. Check credentials and permissions.")
            else:
                st.warning("Enter AWS credentials.")

    # Google Workspace
    with tabs[2]:
        st.markdown("#### Google Workspace")
        st.caption("Reads: Email TLS, DLP config, Drive sharing policy, audit log retention")
        sa_json = st.text_area("Service Account JSON", height=100, placeholder='{"type": "service_account", ...}')
        if st.button("Test & Connect Google Workspace", key="gws_connect"):
            if sa_json:
                conn = GoogleWorkspaceConnector(sa_json)
                findings = conn.to_hipaa_signals()
                st.session_state.connector_findings["google_workspace"] = findings
                st.success("Connected!")
                st.json(findings)

    # Jamf / Kandji
    with tabs[3]:
        st.markdown("#### Jamf / Kandji — macOS MDM")
        st.caption("Reads: FileVault status, screen lock, MDM enrollment percentage")
        mdm_choice = st.radio("MDM Platform", ["Jamf", "Kandji"])
        col1, col2 = st.columns(2)
        if mdm_choice == "Jamf":
            jamf_url = col1.text_input("Jamf Pro URL", placeholder="https://yourorg.jamfcloud.com")
            jamf_user = col1.text_input("Username")
            jamf_pass = col2.text_input("Password", type="password")
            if st.button("Connect Jamf"):
                conn = JamfConnector(jamf_url, jamf_user, jamf_pass)
                findings = conn.to_hipaa_signals()
                st.session_state.connector_findings["jamf"] = findings
                st.success("Connected!")
                st.json(findings)

    # Intune
    with tabs[4]:
        st.markdown("#### Microsoft Intune — Windows MDM")
        st.caption("Reads: BitLocker status, compliance policy enforcement, managed device count")
        col1, col2 = st.columns(2)
        tenant_id = col1.text_input("Tenant ID")
        client_id = col1.text_input("Client ID")
        client_secret = col2.text_input("Client Secret", type="password")
        if st.button("Connect Intune"):
            st.info("Intune connector requires Azure AD app registration with DeviceManagementManagedDevices.Read.All permission.")

    # GitHub
    with tabs[5]:
        st.markdown("#### GitHub — Access Controls & Secrets")
        st.caption("Reads: 2FA requirement, branch protection, secret scanning, outside collaborators")
        col1, col2 = st.columns(2)
        gh_token = col1.text_input("GitHub Token", type="password")
        gh_org = col2.text_input("Organization", placeholder="your-org")
        if st.button("Connect GitHub"):
            if gh_token and gh_org:
                conn = GitHubConnector(gh_token, gh_org)
                if conn.test_connection():
                    findings = conn.to_hipaa_signals()
                    st.session_state.connector_findings["github"] = findings
                    st.success("Connected!")
                    st.json(findings)
                else:
                    st.error("Connection failed.")

    # Jira / Confluence
    with tabs[6]:
        st.markdown("#### Jira & Confluence — Incident Tracking & Policy Docs")
        col1, col2 = st.columns(2)
        jira_url = col1.text_input("Atlassian URL", placeholder="https://yourorg.atlassian.net")
        jira_email = col1.text_input("Email")
        jira_token = col2.text_input("API Token", type="password")
        if st.button("Connect Jira & Confluence"):
            if jira_url and jira_email and jira_token:
                j = JiraConnector(jira_url, jira_email, jira_token)
                c = ConfluenceConnector(jira_url, jira_email, jira_token)
                if j.test_connection():
                    st.session_state.connector_findings["jira"] = j.to_hipaa_signals()
                    st.session_state.connector_findings["confluence"] = c.to_hipaa_signals()
                    st.success("Connected!")
                else:
                    st.error("Connection failed.")

    # Manual Upload
    with tabs[7]:
        st.markdown("#### Manual CSV Upload")
        st.caption("Upload a CSV with columns: control_id, status, evidence, notes, alt_control_documented")

        from engine.control_mapper import load_controls
        from connectors.manual_upload import generate_csv_template, parse_csv_upload
        controls = load_controls()

        template_csv = generate_csv_template(controls)
        st.download_button(
            "Download CSV Template",
            data=template_csv,
            file_name="hipaa_assessment_template.csv",
            mime="text/csv",
        )

        uploaded = st.file_uploader("Upload Completed CSV", type=["csv"])
        if uploaded:
            assessment, errors = parse_csv_upload(uploaded.read())
            if errors:
                for err in errors:
                    st.warning(err)
            if assessment:
                st.session_state.manual_overrides = assessment
                st.success(f"Loaded {len(assessment)} control entries from CSV.")

# Connected sources indicator
connected = list(st.session_state.get("connector_findings", {}).keys())
if connected:
    st.divider()
    st.markdown(f"**Connected sources:** {', '.join(connected)}")
    st.caption("Proceed to **Gap Assessment** to run the full analysis →")
