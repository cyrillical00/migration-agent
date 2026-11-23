"""
Maps connector findings to HIPAA control signal assessments.
Merges automated signals with any manual overrides from session state.
"""
import json
import os
from typing import Any


def load_controls() -> list[dict]:
    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base, "data", "hipaa_controls.json")
    with open(path) as f:
        return json.load(f)


def map_connector_findings(findings: dict[str, dict], controls: list[dict]) -> dict[str, dict]:
    """
    findings: {connector_name: {signal_key: value}}
    Returns partial assessment dict {control_id: {status, evidence, notes}}
    """
    assessment = {}

    # Okta signals
    okta = findings.get("okta", {})
    if okta:
        # None means the connector did not measure the signal. Such a control
        # is left unassessed instead of being recorded as a pass or a fail.
        mfa = okta.get("mfa_enforced")
        unique_ids = okta.get("unique_user_ids")
        auto_logoff = okta.get("auto_logoff_minutes")
        pwd_policy = okta.get("password_policy_strong")

        if "TEC-007" not in assessment and mfa is not None:
            assessment["TEC-007"] = {
                "status": "Implemented" if mfa else "Not Implemented",
                "evidence": mfa,
                "notes": "MFA enforced via Okta" if mfa else "MFA not enforced in Okta",
            }
        if "TEC-001" not in assessment and unique_ids is not None:
            assessment["TEC-001"] = {
                "status": "Implemented" if unique_ids else "Partial",
                "evidence": unique_ids,
                "notes": "Unique user IDs via Okta" if unique_ids else "Shared accounts detected",
            }
        if "TEC-003" not in assessment and auto_logoff is not None:
            ok = auto_logoff <= 30
            assessment["TEC-003"] = {
                "status": "Implemented" if ok else "Partial",
                "evidence": ok,
                "notes": f"Auto-logoff configured at {auto_logoff} minutes",
            }
        if "ADM-014" not in assessment and pwd_policy is not None:
            assessment["ADM-014"] = {
                "status": "Implemented" if pwd_policy else "Partial",
                "evidence": pwd_policy,
                "notes": "Strong password policy in Okta" if pwd_policy else "Password policy does not meet recommendations",
            }

    # AWS signals
    aws = findings.get("aws", {})
    if aws:
        s3_enc = aws.get("s3_default_encryption", False)
        cloudtrail = aws.get("cloudtrail_enabled", False)
        kms = aws.get("kms_in_use", False)
        log_retention = aws.get("log_retention_days", 0)

        if "TEC-004" not in assessment:
            assessment["TEC-004"] = {
                "status": "Implemented" if s3_enc and kms else ("Partial" if s3_enc else "Not Implemented"),
                "evidence": s3_enc,
                "notes": "S3 encryption enabled, KMS configured" if s3_enc and kms else "Encryption partial or missing",
            }
        if "TEC-005" not in assessment:
            retention_ok = log_retention >= 2190  # 6 years
            assessment["TEC-005"] = {
                "status": "Implemented" if cloudtrail and retention_ok else ("Partial" if cloudtrail else "Not Implemented"),
                "evidence": cloudtrail,
                "notes": f"CloudTrail enabled, retention {log_retention} days" if cloudtrail else "CloudTrail not enabled",
            }

    # Google Workspace signals
    gws = findings.get("google_workspace", {})
    if gws:
        tls_enforced = gws.get("tls_enforced_inbound", False)
        dlp_enabled = gws.get("dlp_enabled", False)
        audit_log = gws.get("audit_log_enabled", False)

        if "TEC-009" not in assessment:
            assessment["TEC-009"] = {
                "status": "Implemented" if tls_enforced else "Partial",
                "evidence": tls_enforced,
                "notes": "Email TLS enforced" if tls_enforced else "Email TLS enforcement not confirmed",
            }

    # Jamf/Kandji signals
    for mdm_key in ["jamf", "kandji"]:
        mdm = findings.get(mdm_key, {})
        if mdm:
            filevault = mdm.get("filevault_enabled_pct", 0)
            screen_lock = mdm.get("screen_lock_minutes", None)
            mdm_enrollment = mdm.get("mdm_enrollment_pct", 0)

            if "PHY-006" not in assessment:
                ok = filevault >= 95 and mdm_enrollment >= 95
                assessment["PHY-006"] = {
                    "status": "Implemented" if ok else "Partial",
                    "evidence": ok,
                    "notes": f"FileVault {filevault}%, MDM enrollment {mdm_enrollment}%",
                }

    # Intune signals
    intune = findings.get("intune", {})
    if intune:
        bitlocker = intune.get("bitlocker_enabled_pct", 0)
        compliance_pct = intune.get("compliance_policy_pct", 0)

        if "PHY-006" not in assessment:
            ok = bitlocker >= 95 and compliance_pct >= 95
            assessment["PHY-006"] = {
                "status": "Implemented" if ok else "Partial",
                "evidence": ok,
                "notes": f"BitLocker {bitlocker}%, compliance policy {compliance_pct}%",
            }

    return assessment


def merge_assessments(auto: dict, manual: dict) -> dict:
    """Manual overrides take precedence over auto-detected signals."""
    merged = dict(auto)
    merged.update(manual)
    return merged
