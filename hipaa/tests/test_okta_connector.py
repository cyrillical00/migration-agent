"""The Okta connector must only ever talk to an Okta-operated host."""
import sys
import unittest
from pathlib import Path
from unittest import mock

HIPAA_ROOT = Path(__file__).resolve().parent.parent
if str(HIPAA_ROOT) not in sys.path:
    sys.path.insert(0, str(HIPAA_ROOT))

from connectors import okta  # noqa: E402
from connectors.okta import OktaConnector, normalize_okta_domain  # noqa: E402

TOKEN = "not-a-real-token"


class _Response:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.headers = headers or {}

    def json(self):
        return self._payload


class DomainValidationTests(unittest.TestCase):
    def test_okta_hosts_are_accepted_and_normalised(self):
        cases = {
            "acme.okta.com": "acme.okta.com",
            "  ACME.okta.com/ ": "acme.okta.com",
            "https://acme.okta.com": "acme.okta.com",
            "http://acme.okta.com/": "acme.okta.com",
            "acme-admin.okta.com": "acme-admin.okta.com",
            "dev-123456.oktapreview.com": "dev-123456.oktapreview.com",
            "acme.okta-emea.com": "acme.okta-emea.com",
            "acme.okta-gov.com": "acme.okta-gov.com",
            "acme.okta.mil": "acme.okta.mil",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_okta_domain(raw), expected, raw)

    def test_everything_else_is_refused(self):
        bad = [
            "",
            None,
            "okta.com",
            "localhost",
            "127.0.0.1",
            "169.254.169.254",
            "internal:8443/x?",
            "internal.corp.example",
            "login.example.com",
            "acme.okta.com.evil.example",
            "evil.example/acme.okta.com",
            "evil.example#.okta.com",
            "evil.example?.okta.com",
            "acme.okta.com@evil.example",
            "evil.example\\.okta.com",
            "acme.okta.com:8443",
            "acme.okta.com/api/v1/users",
            "a.b.okta.com",
            "-acme.okta.com",
            "acme.notokta.com",
            "acmeokta.com",
            "acme.okta.com\nHost: evil.example",
            "ftp://acme.okta.com",
        ]
        for raw in bad:
            with self.assertRaises(ValueError, msg=repr(raw)):
                normalize_okta_domain(raw)

    def test_connector_refuses_a_bad_host_before_sending_anything(self):
        with mock.patch.object(okta.requests, "get") as get:
            with self.assertRaises(ValueError):
                OktaConnector(TOKEN, "internal:8443/x?")
            get.assert_not_called()


class RequestTests(unittest.TestCase):
    def test_requests_go_to_the_validated_host_without_following_redirects(self):
        with mock.patch.object(okta.requests, "get", return_value=_Response()) as get:
            conn = OktaConnector(TOKEN, "https://Acme.okta.com/")
            self.assertTrue(conn.test_connection())
            conn.get_findings()

        self.assertGreater(get.call_count, 1)
        for call in get.call_args_list:
            url = call.args[0]
            self.assertTrue(url.startswith("https://acme.okta.com/api/v1/"), url)
            self.assertIs(call.kwargs.get("allow_redirects"), False, url)

    def test_a_redirect_is_not_a_successful_connection(self):
        redirect = _Response(status_code=302, headers={"Location": "https://evil.example/"})
        with mock.patch.object(okta.requests, "get", return_value=redirect):
            self.assertFalse(OktaConnector(TOKEN, "acme.okta.com").test_connection())


def _sign_on_rule(require_factor, idle=15, access="ALLOW", status="ACTIVE"):
    return {
        "status": status,
        "actions": {"signon": {
            "access": access,
            "requireFactor": require_factor,
            "session": {"maxSessionIdleMinutes": idle},
        }},
    }


def _app_rule(factor_mode, access="ALLOW", status="ACTIVE"):
    return {
        "status": status,
        "actions": {"appSignOn": {"access": access, "verificationMethod": {"factorMode": factor_mode}}},
    }


def _password_policy(min_length, max_attempts, status="ACTIVE"):
    return {
        "status": status,
        "settings": {"password": {
            "complexity": {"minLength": min_length},
            "lockout": {"maxAttempts": max_attempts},
        }},
    }


class _FakeOkta:
    """Answers the connector's GETs from a table of path -> response."""

    HOST = "https://acme.okta.com"

    def __init__(self, routes):
        self.routes = routes
        self.requested = []

    def __call__(self, url, **kwargs):
        self.requested.append(url)
        assert url.startswith(self.HOST + "/"), url
        path = url[len(self.HOST):]
        for prefix, response in self.routes.items():
            if path.startswith(prefix):
                return response(path) if callable(response) else response
        return _Response(status_code=404, payload={"errorCode": "E0000007"})


def _signals(routes):
    fake = _FakeOkta(routes)
    with mock.patch.object(okta.requests, "get", side_effect=fake):
        signals = OktaConnector(TOKEN, "acme.okta.com").to_hipaa_signals()
    return signals, fake


def _org(sign_on_rules=None, app_rules=None, password_policies=None, users=None):
    """Routes for an org with one global session policy and one app policy."""
    routes = {}
    if sign_on_rules is not None:
        routes["/api/v1/policies?type=OKTA_SIGN_ON"] = _Response(payload=[{"id": "gsp", "status": "ACTIVE"}])
        routes["/api/v1/policies/gsp/rules"] = _Response(payload=sign_on_rules)
    if app_rules is not None:
        routes["/api/v1/policies?type=ACCESS_POLICY"] = _Response(payload=[{"id": "app", "status": "ACTIVE"}])
        routes["/api/v1/policies/app/rules"] = _Response(payload=app_rules)
    if password_policies is not None:
        routes["/api/v1/policies?type=PASSWORD"] = _Response(payload=password_policies)
    if users is not None:
        routes["/api/v1/users?"] = users
    return routes


class MeasuredSignalTests(unittest.TestCase):
    def test_nothing_readable_means_everything_unknown(self):
        signals, _ = _signals({"/api/v1/": _Response(status_code=403, payload={"errorCode": "E0000006"})})
        for key in okta._SIGNAL_KEYS:
            self.assertIsNone(signals[key], key)
        self.assertEqual(sorted(signals["not_measured"]), sorted(okta._SIGNAL_KEYS))

    def test_a_network_failure_means_unknown_not_a_pass(self):
        with mock.patch.object(okta.requests, "get", side_effect=OSError("down")):
            signals = OktaConnector(TOKEN, "acme.okta.com").to_hipaa_signals()
        for key in okta._SIGNAL_KEYS:
            self.assertIsNone(signals[key], key)

    def test_values_the_api_cannot_show_are_never_asserted(self):
        signals, _ = _signals(_org(
            sign_on_rules=[_sign_on_rule(True)],
            password_policies=[_password_policy(14, 5)],
            users=_Response(payload=[{"id": "u1"}]),
        ))
        self.assertIsNone(signals["unique_user_ids"])
        self.assertIsNone(signals["audit_log_retention_days"])
        self.assertEqual(signals["not_measured"], ["unique_user_ids", "audit_log_retention_days"])

    def test_mfa_is_enforced_only_when_every_active_allow_rule_requires_a_factor(self):
        signals, _ = _signals(_org(sign_on_rules=[_sign_on_rule(True), _sign_on_rule(True)]))
        self.assertIs(signals["mfa_enforced"], True)

        signals, _ = _signals(_org(sign_on_rules=[_sign_on_rule(True), _sign_on_rule(False)]))
        self.assertIs(signals["mfa_enforced"], False)

        # Inactive and deny rules admit nobody, so they do not weaken the result.
        signals, _ = _signals(_org(sign_on_rules=[
            _sign_on_rule(True),
            _sign_on_rule(False, status="INACTIVE"),
            _sign_on_rule(False, access="DENY"),
        ]))
        self.assertIs(signals["mfa_enforced"], True)

    def test_an_active_enrollment_policy_alone_is_not_enforcement(self):
        routes = _org(sign_on_rules=[_sign_on_rule(False)])
        routes["/api/v1/policies?type=MFA_ENROLL"] = _Response(payload=[{"id": "enroll", "status": "ACTIVE"}])
        signals, _ = _signals(routes)
        self.assertIs(signals["mfa_enforced"], False)

    def test_app_policies_can_supply_the_second_factor(self):
        signals, _ = _signals(_org(sign_on_rules=[_sign_on_rule(False)], app_rules=[_app_rule("2FA")]))
        self.assertIs(signals["mfa_enforced"], True)

        signals, _ = _signals(_org(sign_on_rules=[_sign_on_rule(False)], app_rules=[_app_rule("2FA"), _app_rule("1FA")]))
        self.assertIs(signals["mfa_enforced"], False)

        signals, _ = _signals(_org(sign_on_rules=[_sign_on_rule(False)], app_rules=[]))
        self.assertIs(signals["mfa_enforced"], False)

    def test_idle_timeout_is_the_longest_any_rule_allows(self):
        signals, _ = _signals(_org(sign_on_rules=[_sign_on_rule(True, idle=15), _sign_on_rule(True, idle=120)]))
        self.assertEqual(signals["auto_logoff_minutes"], 120)

        signals, _ = _signals(_org(sign_on_rules=[_sign_on_rule(True, idle=None)]))
        self.assertIsNone(signals["auto_logoff_minutes"])

    def test_password_policy_is_judged_by_its_settings(self):
        signals, _ = _signals(_org(password_policies=[_password_policy(8, 10)]))
        self.assertIs(signals["password_policy_strong"], False)
        self.assertEqual(signals["password_min_length"], 8)

        signals, _ = _signals(_org(password_policies=[_password_policy(14, 5)]))
        self.assertIs(signals["password_policy_strong"], True)

        # The weakest active policy decides; no lockout is never strong.
        signals, _ = _signals(_org(password_policies=[_password_policy(14, 5), _password_policy(8, 5)]))
        self.assertIs(signals["password_policy_strong"], False)
        signals, _ = _signals(_org(password_policies=[_password_policy(14, 0)]))
        self.assertIs(signals["password_policy_strong"], False)
        self.assertEqual(signals["password_lockout_attempts"], 0)
        signals, _ = _signals(_org(password_policies=[_password_policy(14, 5), _password_policy(6, 0, status="INACTIVE")]))
        self.assertIs(signals["password_policy_strong"], True)

        signals, _ = _signals(_org(password_policies=[]))
        self.assertIsNone(signals["password_policy_strong"])
        signals, _ = _signals(_org(password_policies=[{"status": "ACTIVE", "settings": {}}]))
        self.assertIsNone(signals["password_policy_strong"])

    def test_users_are_counted_across_pages_on_the_same_host(self):
        def users(path):
            if "after=p2" in path:
                return _Response(payload=[{"id": "u3"}])
            return _Response(
                payload=[{"id": "u1"}, {"id": "u2"}],
                headers={"Link": '<https://acme.okta.com/api/v1/users?after=p2&limit=200>; rel="next"'},
            )

        signals, fake = _signals(_org(users=users))
        self.assertEqual(signals["active_user_count"], 3)
        self.assertTrue(all(url.startswith("https://acme.okta.com/") for url in fake.requested))

    def test_a_next_link_to_another_host_is_never_followed(self):
        for link in (
            "https://evil.example/api/v1/users?after=p2",
            "http://acme.okta.com/api/v1/users?after=p2",
            "https://acme.okta.com.evil.example/api/v1/users?after=p2",
            "https://acme.okta.com@evil.example/api/v1/users?after=p2",
            "https://acme.okta.com:8443/api/v1/users?after=p2",
        ):
            users = _Response(payload=[{"id": "u1"}], headers={"Link": f'<{link}>; rel="next"'})
            signals, fake = _signals(_org(users=users))
            self.assertEqual(signals["active_user_count"], 1, link)
            self.assertTrue(all(url.startswith("https://acme.okta.com/") for url in fake.requested), link)

    def test_get_url_refuses_other_hosts(self):
        conn = OktaConnector(TOKEN, "acme.okta.com")
        with mock.patch.object(okta.requests, "get") as get:
            for url in ("https://evil.example/x", "https://acme.okta.com.evil.example/x", "http://acme.okta.com/x"):
                with self.assertRaises(ValueError):
                    conn._get_url(url)
            get.assert_not_called()


class ControlMappingTests(unittest.TestCase):
    def setUp(self):
        from engine.control_mapper import map_connector_findings
        self.map = map_connector_findings

    def test_unknown_signals_leave_controls_unassessed(self):
        unknown = {key: None for key in okta._SIGNAL_KEYS}
        unknown["not_measured"] = list(okta._SIGNAL_KEYS)
        self.assertEqual(self.map({"okta": unknown}, []), {})

    def test_measured_signals_still_map(self):
        mapped = self.map({"okta": {
            "mfa_enforced": False,
            "unique_user_ids": None,
            "auto_logoff_minutes": 120,
            "password_policy_strong": True,
        }}, [])
        self.assertEqual(mapped["TEC-007"]["status"], "Not Implemented")
        self.assertEqual(mapped["TEC-003"]["status"], "Partial")
        self.assertEqual(mapped["ADM-014"]["status"], "Implemented")
        self.assertNotIn("TEC-001", mapped)

    def test_demo_fixture_maps_as_before(self):
        mapped = self.map({"okta": okta.OKTA_DEMO_FINDINGS}, [])
        self.assertEqual(
            {cid: entry["status"] for cid, entry in mapped.items()},
            {"TEC-007": "Implemented", "TEC-001": "Implemented", "TEC-003": "Implemented", "ADM-014": "Implemented"},
        )


if __name__ == "__main__":
    unittest.main()
