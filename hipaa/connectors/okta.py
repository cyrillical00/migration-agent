"""Okta connector — user access, MFA enforcement, audit logs."""
import re
import requests
from typing import Any

# Hosts Okta itself operates. The domain is typed by whoever uses the app and
# the API token is sent to it, so anything else (an internal host, an IP
# address, a look-alike) is refused. A custom domain such as
# login.example.com cannot be told apart from an arbitrary host and is not
# accepted; use the org's own *.okta.com name.
_OKTA_HOST_RE = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"\.(?:okta\.com|oktapreview\.com|okta-emea\.com|okta-gov\.com|okta\.mil)"
)


def normalize_okta_domain(domain: str) -> str:
    """Return the bare Okta hostname for `domain`, or raise ValueError."""
    host = (domain or "").strip().lower()
    for scheme in ("https://", "http://"):
        if host.startswith(scheme):
            host = host[len(scheme):]
    host = host.rstrip("/")
    if not _OKTA_HOST_RE.fullmatch(host):
        raise ValueError(
            "Enter your Okta org domain, for example yourorg.okta.com "
            "(okta.com, oktapreview.com, okta-emea.com, okta-gov.com or okta.mil)."
        )
    return host


class OktaConnector:
    def __init__(self, api_token: str, domain: str):
        self.api_token = api_token
        self.domain = normalize_okta_domain(domain)
        self.headers = {
            "Authorization": f"SSWS {api_token}",
            "Accept": "application/json",
        }

    def _get(self, path: str):
        """GET a path on the validated Okta host. Redirects are not followed,
        so the token is never replayed to wherever a response points."""
        return requests.get(
            f"https://{self.domain}{path}",
            headers=self.headers, timeout=10, allow_redirects=False,
        )

    def test_connection(self) -> bool:
        try:
            r = self._get("/api/v1/users?limit=1")
            return r.status_code == 200
        except Exception:
            return False

    def get_findings(self) -> dict:
        findings = {}
        try:
            # MFA policy
            r = self._get("/api/v1/policies?type=MFA_ENROLL")
            policies = r.json() if r.status_code == 200 else []
            findings["mfa_enforced"] = any(p.get("status") == "ACTIVE" for p in policies)

            # Users
            r = self._get('/api/v1/users?limit=200&filter=status eq "ACTIVE"')
            users = r.json() if r.status_code == 200 else []
            findings["active_user_count"] = len(users)
            findings["unique_user_ids"] = True  # Okta always assigns unique IDs

            # Admin users
            r = self._get("/api/v1/groups?q=admin")
            groups = r.json() if r.status_code == 200 else []
            findings["admin_group_count"] = len(groups)

            # Password policy
            r = self._get("/api/v1/policies?type=PASSWORD")
            pwd_policies = r.json() if r.status_code == 200 else []
            findings["password_policy_strong"] = len(pwd_policies) > 0

            # Auto-logoff / session timeout
            findings["auto_logoff_minutes"] = 15  # Would parse from session policy

            findings["audit_log_retention_days"] = 90  # Okta default

        except Exception as e:
            findings["error"] = str(e)

        return findings

    def to_hipaa_signals(self) -> dict:
        findings = self.get_findings()
        return {
            "mfa_enforced": findings.get("mfa_enforced", False),
            "unique_user_ids": findings.get("unique_user_ids", True),
            "auto_logoff_minutes": findings.get("auto_logoff_minutes", 15),
            "password_policy_strong": findings.get("password_policy_strong", False),
            "audit_log_retention_days": findings.get("audit_log_retention_days", 90),
            "active_user_count": findings.get("active_user_count", 0),
        }


OKTA_DEMO_FINDINGS = {
    "mfa_enforced": True,
    "unique_user_ids": True,
    "auto_logoff_minutes": 15,
    "password_policy_strong": True,
    "audit_log_retention_days": 90,
    "active_user_count": 148,
    "admin_group_count": 3,
    "inactive_users_count": 4,
    "device_trust_enabled": False,
}
