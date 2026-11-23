"""Okta connector — user access, MFA enforcement, audit logs."""
import re
import requests
from typing import Any
from urllib.parse import quote, urlsplit

# What "strong" means for password_policy_strong, applied to the weakest
# active password policy in the org.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LOCKOUT_ATTEMPTS = 10

# 200 users per page.
_MAX_USER_PAGES = 250

_SIGNAL_KEYS = (
    "mfa_enforced",
    "unique_user_ids",
    "auto_logoff_minutes",
    "password_policy_strong",
    "audit_log_retention_days",
    "active_user_count",
)

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

    def _get_url(self, url: str):
        """GET a URL on the validated Okta host. Redirects are not followed,
        so the token is never replayed to wherever a response points."""
        if not url.startswith(f"https://{self.domain}/"):
            raise ValueError("Refusing to send the Okta token to another host.")
        return requests.get(url, headers=self.headers, timeout=10, allow_redirects=False)

    def _get(self, path: str):
        return self._get_url(f"https://{self.domain}{path}")

    def _get_list(self, path: str):
        """The JSON list a successful call returned, or None when it did not succeed."""
        r = self._get(path)
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, list) else None

    def _next_page(self, response):
        """URL of the next page, only when it stays on this Okta host over HTTPS."""
        link = response.headers.get("Link") or response.headers.get("link") or ""
        for part in link.split(","):
            if 'rel="next"' not in part:
                continue
            url = part.split(";")[0].strip().strip("<>")
            target = urlsplit(url)
            if target.scheme == "https" and target.netloc.lower() == self.domain:
                return url
        return None

    def test_connection(self) -> bool:
        try:
            r = self._get("/api/v1/users?limit=1")
            return r.status_code == 200
        except Exception:
            return False

    def _active_rules(self, policy_type: str):
        """Active rules of every active policy of one type, or None if a call failed."""
        policies = self._get_list(f"/api/v1/policies?type={policy_type}")
        if policies is None:
            return None
        rules = []
        for policy in policies:
            if policy.get("status") != "ACTIVE":
                continue
            policy_id = quote(str(policy.get("id", "")), safe="")
            policy_rules = self._get_list(f"/api/v1/policies/{policy_id}/rules")
            if policy_rules is None:
                return None
            rules.extend(r for r in policy_rules if r.get("status") == "ACTIVE")
        return rules

    def _measure_sign_on(self, findings: dict) -> None:
        """MFA requirement and idle timeout, from the global session policy rules."""
        rules = self._active_rules("OKTA_SIGN_ON")
        if rules is None:
            return
        allow = [r.get("actions", {}).get("signon", {}) for r in rules]
        allow = [a for a in allow if a.get("access") == "ALLOW"]
        if not allow:
            return

        idle = [a.get("session", {}).get("maxSessionIdleMinutes") for a in allow]
        if all(isinstance(m, int) and m > 0 for m in idle):
            # The longest idle time any rule allows is what the org really permits.
            findings["auto_logoff_minutes"] = max(idle)

        if all(a.get("requireFactor") is True for a in allow):
            findings["mfa_enforced"] = True
            return
        # The global session policy lets some sign-ins through on one factor.
        # On Identity Engine the per-app authentication policies can still
        # require a second one; MFA counts as enforced only if all of them do.
        # Where that listing is unavailable (Classic Engine has no such
        # policies) nothing compensates, and the answer stays "not enforced".
        app_rules = None
        try:
            app_rules = self._active_rules("ACCESS_POLICY")
        except Exception:
            pass
        app_allow = [r.get("actions", {}).get("appSignOn", {}) for r in app_rules or []]
        app_allow = [a for a in app_allow if a.get("access") == "ALLOW"]
        findings["mfa_enforced"] = bool(app_allow) and all(
            a.get("verificationMethod", {}).get("factorMode") == "2FA" for a in app_allow
        )

    def _measure_users(self, findings: dict) -> None:
        """Count active users across every page of the listing."""
        url = f'https://{self.domain}/api/v1/users?limit=200&filter=status eq "ACTIVE"'
        total = 0
        for _ in range(_MAX_USER_PAGES):
            r = self._get_url(url)
            if r.status_code != 200:
                return
            page = r.json()
            if not isinstance(page, list):
                return
            total += len(page)
            url = self._next_page(r)
            if url is None:
                findings["active_user_count"] = total
                return
        # More pages than we are willing to walk: a partial count is not a count.

    def _measure_admin_groups(self, findings: dict) -> None:
        groups = self._get_list("/api/v1/groups?q=admin")
        if groups is not None:
            findings["admin_group_count"] = len(groups)

    def _measure_password_policy(self, findings: dict) -> None:
        """Length and lockout settings of the weakest active password policy."""
        policies = self._get_list("/api/v1/policies?type=PASSWORD")
        if policies is None:
            return
        settings = [
            p.get("settings", {}).get("password", {})
            for p in policies if p.get("status") == "ACTIVE"
        ]
        lengths = [s.get("complexity", {}).get("minLength") for s in settings]
        lockouts = [s.get("lockout", {}).get("maxAttempts") for s in settings]
        if not settings or not all(isinstance(n, int) for n in lengths + lockouts):
            return
        findings["password_min_length"] = min(lengths)
        # 0 means accounts are never locked out.
        findings["password_lockout_attempts"] = 0 if 0 in lockouts else max(lockouts)
        findings["password_policy_strong"] = (
            min(lengths) >= PASSWORD_MIN_LENGTH
            and all(0 < n <= PASSWORD_MAX_LOCKOUT_ATTEMPTS for n in lockouts)
        )

    def get_findings(self) -> dict:
        """Signals read from the org. A value of None means it was not measured."""
        findings = {
            "mfa_enforced": None,
            # Okta gives every account its own ID, but whether people share an
            # account is not something the API can show.
            "unique_user_ids": None,
            "auto_logoff_minutes": None,
            "password_policy_strong": None,
            # System Log retention is a platform property, not an org setting
            # this API exposes, and logs exported elsewhere are not visible here.
            "audit_log_retention_days": None,
            "active_user_count": None,
        }
        for measure in (
            self._measure_sign_on,
            self._measure_users,
            self._measure_admin_groups,
            self._measure_password_policy,
        ):
            try:
                measure(findings)
            except Exception as e:
                findings["error"] = str(e)
        return findings

    def to_hipaa_signals(self) -> dict:
        findings = self.get_findings()
        signals = {key: findings.get(key) for key in _SIGNAL_KEYS}
        for key in ("password_min_length", "password_lockout_attempts"):
            if key in findings:
                signals[key] = findings[key]
        # Named explicitly so a reader does not take "null" for a result.
        signals["not_measured"] = [key for key in _SIGNAL_KEYS if signals[key] is None]
        return signals


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
