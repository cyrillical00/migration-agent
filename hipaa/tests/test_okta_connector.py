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


if __name__ == "__main__":
    unittest.main()
