"""
Supabase Auth session management.

Flow:
1. User runs `porcupine auth login` — we call supabase.auth.sign_in_with_otp()
   which sends a magic link to their email.
2. After clicking the link, Supabase redirects to a local callback URL
   (http://localhost:54321/callback) — we spin up a temporary HTTP server to
   capture the token fragment.
3. The access_token and user_id are stored in the OS keychain via `keyring`.
4. Subsequent commands load the token from keychain silently.

Windows keyring backend: Windows Credential Manager (built-in, no extra deps).
The service name used is "porcupine" and the username is the user's email.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import keyring
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

KEYRING_SERVICE = "porcupine"
KEYRING_TOKEN_KEY = "access_token"
KEYRING_USER_ID_KEY = "user_id"
KEYRING_EMAIL_KEY = "email"

CALLBACK_PORT = 54321
CALLBACK_PATH = "/callback"
TOKEN_PATH = "/token"

# The only pages allowed to hand a token to the callback server are its own.
_OWN_ORIGINS = {
    f"http://localhost:{CALLBACK_PORT}",
    f"http://127.0.0.1:{CALLBACK_PORT}",
}
_MAX_TOKEN_BODY = 16 * 1024


# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------

def save_session(access_token: str, user_id: str, email: str) -> None:
    """Persist session to OS keychain."""
    keyring.set_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY, access_token)
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER_ID_KEY, user_id)
    keyring.set_password(KEYRING_SERVICE, KEYRING_EMAIL_KEY, email)


def load_session() -> Optional[dict]:
    """
    Load stored session from OS keychain.

    Returns:
        Dict with keys {access_token, user_id, email} or None if not logged in.
    """
    access_token = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
    user_id = keyring.get_password(KEYRING_SERVICE, KEYRING_USER_ID_KEY)
    email = keyring.get_password(KEYRING_SERVICE, KEYRING_EMAIL_KEY)
    if access_token and user_id:
        return {"access_token": access_token, "user_id": user_id, "email": email}
    return None


def clear_session() -> None:
    """Remove stored session from OS keychain."""
    for key in (KEYRING_TOKEN_KEY, KEYRING_USER_ID_KEY, KEYRING_EMAIL_KEY):
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass


def require_session() -> dict:
    """
    Return the stored session or raise a clear error if not logged in.

    Use this in CLI commands that require authentication.
    """
    session = load_session()
    if not session:
        raise RuntimeError(
            "Not logged in. Run: porcupine auth login"
        )
    return session


# ---------------------------------------------------------------------------
# Magic link auth flow
# ---------------------------------------------------------------------------

_CALLBACK_PAGE = """<!DOCTYPE html>
<html><head><title>Porcupine Auth</title></head>
<body>
<script>
  const hash = window.location.hash.substring(1);
  const params = new URLSearchParams(hash);
  const token = params.get('access_token');
  const type  = params.get('type');
  if (!token) {
    document.body.innerHTML = '<p>Waiting for the magic link. Click the link in your email.</p>';
  } else {
    fetch('/token', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({access_token: token, type: type, state: __STATE__})
    }).then((r) => {
      document.body.innerHTML = r.ok
        ? '<h2>Login successful. You can close this tab.</h2>'
        : '<h2>Login was not accepted. Run porcupine auth login again.</h2>';
    });
  }
</script>
<p>Completing login...</p>
</body></html>"""


class _CallbackHandler(BaseHTTPRequestHandler):
    """
    Minimal HTTP handler to capture the Supabase magic link redirect.

    Supabase appends the token as a URL fragment (#access_token=...) which
    browsers don't send to the server. We serve a tiny HTML page that reads
    the fragment via JavaScript and POSTs it back to us.

    The port is reachable by every local process and, through the browser, by
    any web page that is open while a login is waiting. A token is therefore
    accepted only from our own page: the POST must carry the per-login `state`
    that page was served with, be JSON, and not come from another origin.
    """

    captured: dict = {}
    # Random value set by login() for each attempt.
    state: str = ""

    def _refuse(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        """Serve the fragment-capture page."""
        if urllib.parse.urlsplit(self.path).path != CALLBACK_PATH:
            self._refuse(404)
            return
        html = _CALLBACK_PAGE.replace("__STATE__", json.dumps(_CallbackHandler.state))
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_POST(self):
        """Receive the POSTed token from the JavaScript fragment reader."""
        if urllib.parse.urlsplit(self.path).path != TOKEN_PATH:
            self._refuse(404)
            return

        origin = self.headers.get("Origin")
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if (origin is not None and origin not in _OWN_ORIGINS) or content_type != "application/json":
            self._refuse(403)
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0 or length > _MAX_TOKEN_BODY:
            self._refuse(400)
            return

        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            data = None
        if not isinstance(data, dict):
            self._refuse(400)
            return

        state = data.get("state")
        expected = _CallbackHandler.state
        if (
            not expected
            or not isinstance(state, str)
            or not hmac.compare_digest(state.encode(), expected.encode())
        ):
            self._refuse(403)
            return

        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            self._refuse(400)
            return

        _CallbackHandler.captured = {"access_token": token}
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass  # suppress server logs


def login(email: str) -> dict:
    """
    Initiate Supabase magic link login for the given email.

    1. Sends OTP (magic link) to the email via Supabase Auth.
    2. Starts a local callback server on port 54321.
    3. Opens the user's browser to the Supabase-generated link.
    4. Waits (up to 120s) for the user to click the link and return.
    5. Exchanges the captured fragment token for a full session and checks
       that it belongs to `email`.
    6. Persists the session to keychain.

    Args:
        email: User's email address (must be pre-invited in Supabase).

    Returns:
        Dict with {access_token, user_id, email}.

    Raises:
        RuntimeError: On timeout or Supabase API error.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    redirect_url = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"
    client.auth.sign_in_with_otp({
        "email": email,
        "options": {"email_redirect_to": redirect_url},
    })

    # Start callback server in a background thread
    _CallbackHandler.captured = {}
    _CallbackHandler.state = secrets.token_urlsafe(32)
    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    server.timeout = 120  # 2 minutes to complete browser flow

    thread = threading.Thread(target=_serve_until_captured, args=(server,), daemon=True)
    thread.start()

    # Open browser to callback URL so user knows where to look
    webbrowser.open(redirect_url)

    thread.join(timeout=130)

    access_token = _CallbackHandler.captured.get("access_token")
    if not access_token:
        raise RuntimeError(
            "Login timed out. Click the magic link in your email within 2 minutes."
        )

    # Get user details from the token
    client.auth.set_session(access_token, "")
    user = client.auth.get_user(access_token)
    user_id = user.user.id
    user_email = user.user.email or ""

    # The token must belong to the account this login was started for. A
    # token for any other account was not produced by this magic link.
    if user_email.strip().lower() != email.strip().lower():
        raise RuntimeError(
            f"The sign-in that came back was not for {email}. Nothing was saved; "
            "run porcupine auth login again."
        )

    save_session(access_token, user_id, user_email)
    return {"access_token": access_token, "user_id": user_id, "email": user_email}


def _serve_until_captured(server: HTTPServer) -> None:
    """Serve requests until access_token is captured or timeout."""
    while not _CallbackHandler.captured.get("access_token"):
        server.handle_request()
    server.server_close()
