"""The login callback must only accept a token from the page it served."""
import http.client
import json
import sys
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth import session  # noqa: E402
from auth.session import _CallbackHandler  # noqa: E402

STATE = "state-for-this-login"
OWN_ORIGIN = f"http://localhost:{session.CALLBACK_PORT}"


class CallbackHandlerTests(unittest.TestCase):
    def setUp(self):
        _CallbackHandler.captured = {}
        _CallbackHandler.state = STATE
        self.server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        _CallbackHandler.captured = {}
        _CallbackHandler.state = ""

    def _request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read().decode()
        finally:
            conn.close()

    def _post(self, payload, origin=OWN_ORIGIN, content_type="application/json", path="/token"):
        headers = {"Content-Type": content_type}
        if origin is not None:
            headers["Origin"] = origin
        body = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
        return self._request("POST", path, body=body, headers=headers)[0]

    def test_page_carries_the_state_and_is_only_served_on_the_callback_path(self):
        status, body = self._request("GET", "/callback")
        self.assertEqual(status, 200)
        self.assertIn(json.dumps(STATE), body)
        self.assertEqual(self._request("GET", "/")[0], 404)
        self.assertEqual(self._request("GET", "/token")[0], 404)

    def test_token_from_our_page_is_accepted(self):
        self.assertEqual(self._post({"access_token": "tok", "type": "magiclink", "state": STATE}), 200)
        self.assertEqual(_CallbackHandler.captured, {"access_token": "tok"})

    def test_token_without_the_state_is_refused(self):
        for payload in (
            {"access_token": "planted"},
            {"access_token": "planted", "state": ""},
            {"access_token": "planted", "state": "guess"},
            {"access_token": "planted", "state": None},
            {"access_token": "planted", "state": ["x"]},
        ):
            self.assertEqual(self._post(payload), 403, payload)
        self.assertEqual(_CallbackHandler.captured, {})

    def test_nothing_is_accepted_before_a_login_sets_a_state(self):
        _CallbackHandler.state = ""
        self.assertEqual(self._post({"access_token": "planted", "state": ""}), 403)
        self.assertEqual(_CallbackHandler.captured, {})

    def test_other_origins_and_form_posts_are_refused(self):
        good = {"access_token": "planted", "state": STATE}
        self.assertEqual(self._post(good, origin="https://evil.example"), 403)
        self.assertEqual(self._post(good, origin="null"), 403)
        self.assertEqual(self._post(good, content_type="text/plain"), 403)
        self.assertEqual(self._post(good, content_type="application/x-www-form-urlencoded"), 403)
        self.assertEqual(self._post(good, path="/callback"), 404)
        self.assertEqual(_CallbackHandler.captured, {})

    def test_malformed_bodies_are_refused(self):
        self.assertEqual(self._post("not json"), 400)
        self.assertEqual(self._post("[]"), 400)
        self.assertEqual(self._post({"state": STATE}), 400)
        self.assertEqual(self._post({"access_token": 5, "state": STATE}), 400)
        self.assertEqual(self._post("x" * (session._MAX_TOKEN_BODY + 1)), 400)
        self.assertEqual(_CallbackHandler.captured, {})

    def test_only_the_token_is_kept(self):
        self.assertEqual(self._post({"access_token": "tok", "state": STATE, "user_id": "someone-else"}), 200)
        self.assertEqual(_CallbackHandler.captured, {"access_token": "tok"})


class LoginBindingTests(unittest.TestCase):
    """login() must not store a session for a different account than the one asked for."""

    def _login(self, returned_email):
        user = mock.Mock()
        user.user.id = "user-1"
        user.user.email = returned_email
        client = mock.Mock()
        client.auth.get_user.return_value = user

        def fake_serve(server):
            _CallbackHandler.captured = {"access_token": "tok"}
            server.server_close()

        with mock.patch.object(session, "SUPABASE_URL", "https://project.example"), \
                mock.patch.object(session, "SUPABASE_KEY", "not-a-real-key"), \
                mock.patch.object(session, "create_client", return_value=client), \
                mock.patch.object(session, "CALLBACK_PORT", 0), \
                mock.patch.object(session.webbrowser, "open"), \
                mock.patch.object(session, "_serve_until_captured", side_effect=fake_serve), \
                mock.patch.object(session, "save_session") as save:
            try:
                result = session.login("pat@example.org")
            except RuntimeError as exc:
                return exc, save
            return result, save

    def test_matching_account_is_saved(self):
        result, save = self._login("Pat@Example.org")
        self.assertEqual(result["user_id"], "user-1")
        save.assert_called_once_with("tok", "user-1", "Pat@Example.org")
        self.assertTrue(_CallbackHandler.state)

    def test_token_for_another_account_is_not_saved(self):
        for returned in ("mallory@example.org", "", None):
            result, save = self._login(returned)
            self.assertIsInstance(result, RuntimeError, returned)
            save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
