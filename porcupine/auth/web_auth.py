"""
Supabase Auth for the Streamlit web UI.

Supports:
  - Email + password login
  - TOTP MFA (verify if enrolled; enroll on first login)
  - Session stored in st.session_state (survives reruns, cleared on logout)

Auth state machine:
  None / "login"   →  email + password form
  "mfa_verify"     →  6-digit TOTP form (factor already enrolled)
  "mfa_enroll"     →  QR code + verify (first time setup)
  cleared          →  authenticated, session in st.session_state["auth_session"]
"""

from __future__ import annotations

import io
import os

import streamlit as st
from supabase import create_client, Client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _secret(key: str) -> str:
    """Read from st.secrets (Streamlit Cloud) with .env fallback."""
    try:
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, "")


@st.cache_resource
def _client() -> Client:
    url = _secret("SUPABASE_URL")
    key = _secret("SUPABASE_KEY")
    if not url or not key:
        st.error("SUPABASE_URL and SUPABASE_KEY are not configured.")
        st.stop()
    return create_client(url, key)


def get_session() -> dict | None:
    """Return the current session dict or None."""
    return st.session_state.get("auth_session")


def logout() -> None:
    for k in ("auth_session", "auth_state",
              "_mfa_factor_id", "_mfa_challenge_id", "_enroll_data"):
        st.session_state.pop(k, None)
    try:
        _client().auth.sign_out()
    except Exception:
        pass


def _store_session(resp) -> None:
    """Persist a Supabase auth response into session state."""
    session = getattr(resp, "session", resp)
    user    = getattr(resp, "user", None) or getattr(session, "user", None)
    st.session_state["auth_session"] = {
        "access_token": getattr(session, "access_token", None),
        "user_id":      str(user.id) if user else "",
        "email":        getattr(user, "email", "") if user else "",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_auth_gate() -> bool:
    """
    Render the login UI if the user is not authenticated.
    Returns True when authenticated (caller should continue rendering the app).
    Returns False and calls st.stop() if not yet authenticated.
    """
    if get_session():
        return True

    state = st.session_state.get("auth_state", "login")

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 🦔 Porcupine")
        st.caption("Prediction market signal engine — invite only")
        st.divider()

        if state == "login":
            _login_step()
        elif state == "mfa_verify":
            _mfa_step()
        elif state == "mfa_enroll":
            _enroll_step()

    st.stop()
    return False  # unreachable but makes type checkers happy


# ---------------------------------------------------------------------------
# Step 1: email + password
# ---------------------------------------------------------------------------

def _login_step() -> None:
    st.subheader("Sign in")

    with st.form("login_form"):
        email    = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password")
        submit   = st.form_submit_button("Sign in", use_container_width=True, type="primary")

    if not submit:
        return

    if not email or not password:
        st.error("Email and password are required.")
        return

    with st.spinner("Signing in…"):
        try:
            resp = _client().auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:
            err = str(exc)
            if "invalid" in err.lower() or "credentials" in err.lower():
                st.error("Incorrect email or password.")
            else:
                st.error(f"Sign-in failed: {err}")
            return

    # Check whether MFA is required for this session
    try:
        aal       = _client().auth.mfa.get_authenticator_assurance_level()
        current   = getattr(aal, "current_level", "aal1")
        next_lvl  = getattr(aal, "next_level",    "aal1")
    except Exception:
        current, next_lvl = "aal1", "aal1"

    if next_lvl == "aal2" and current == "aal1":
        # MFA enrolled — need to verify before granting access
        try:
            factors      = _client().auth.mfa.list_factors()
            totp_list    = getattr(factors, "totp", []) or []
            if totp_list:
                factor_id = totp_list[0].id
                challenge = _client().auth.mfa.challenge({"factor_id": factor_id})
                st.session_state["_mfa_factor_id"]   = factor_id
                st.session_state["_mfa_challenge_id"] = challenge.id
                st.session_state["auth_state"]        = "mfa_verify"
                st.rerun()
                return
        except Exception:
            pass  # MFA check failed — fall through to normal session

    # No MFA or MFA unenrolled — store session and optionally prompt enrollment
    _store_session(resp)

    # Offer MFA enrollment on first login (no existing factors)
    try:
        factors   = _client().auth.mfa.list_factors()
        totp_list = getattr(factors, "totp", []) or []
        if not totp_list:
            st.session_state["auth_state"] = "mfa_enroll"
            st.rerun()
            return
    except Exception:
        pass

    st.rerun()


# ---------------------------------------------------------------------------
# Step 2a: verify MFA
# ---------------------------------------------------------------------------

def _mfa_step() -> None:
    st.subheader("Two-factor authentication")
    st.caption("Enter the 6-digit code from your authenticator app.")

    with st.form("mfa_form"):
        code   = st.text_input("Authentication code", placeholder="000000", max_chars=6)
        verify = st.form_submit_button("Verify", use_container_width=True, type="primary")
        back   = st.form_submit_button("← Back to login")

    if back:
        st.session_state["auth_state"] = "login"
        st.session_state.pop("auth_session", None)
        st.rerun()

    if not verify:
        return

    if not code.isdigit() or len(code) != 6:
        st.error("Enter the 6-digit code from your authenticator app.")
        return

    factor_id    = st.session_state.get("_mfa_factor_id")
    challenge_id = st.session_state.get("_mfa_challenge_id")

    with st.spinner("Verifying…"):
        try:
            resp = _client().auth.mfa.verify({
                "factor_id":    factor_id,
                "challenge_id": challenge_id,
                "code":         code,
            })
        except Exception as exc:
            st.error(f"Invalid code — {exc}")
            return

    _store_session(resp)
    for k in ("_mfa_factor_id", "_mfa_challenge_id", "auth_state"):
        st.session_state.pop(k, None)
    st.rerun()


# ---------------------------------------------------------------------------
# Step 2b: enroll MFA (first login)
# ---------------------------------------------------------------------------

def _enroll_step() -> None:
    st.subheader("Set up two-factor authentication")
    st.caption(
        "Scan the QR code with Google Authenticator, Authy, or any TOTP app. "
        "You can skip this and set it up later."
    )

    enroll = st.session_state.get("_enroll_data")
    if not enroll:
        try:
            resp  = _client().auth.mfa.enroll({"factor_type": "totp", "friendly_name": "Porcupine"})
            enroll = {
                "factor_id": resp.id,
                "uri":       resp.totp.uri,
                "secret":    resp.totp.secret,
            }
            st.session_state["_enroll_data"] = enroll
        except Exception as exc:
            st.error(f"Could not start MFA setup: {exc}")
            if st.button("Skip for now"):
                st.session_state.pop("auth_state", None)
                st.rerun()
            return

    # Render QR code
    try:
        import qrcode
        qr  = qrcode.make(enroll["uri"])
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        st.image(buf.getvalue(), width=200)
    except Exception:
        st.caption("Could not render QR code — enter the secret manually:")
        st.code(enroll["uri"])

    st.caption(f"Manual entry secret: `{enroll.get('secret', '')}`")
    st.divider()

    with st.form("enroll_form"):
        code    = st.text_input("Enter code to confirm", placeholder="000000", max_chars=6)
        confirm = st.form_submit_button("Enable MFA", use_container_width=True, type="primary")
        skip    = st.form_submit_button("Skip for now")

    if skip:
        st.session_state.pop("_enroll_data", None)
        st.session_state.pop("auth_state", None)
        st.rerun()

    if not confirm:
        return

    if not code.isdigit() or len(code) != 6:
        st.error("Enter the 6-digit code from your authenticator app.")
        return

    with st.spinner("Verifying…"):
        try:
            factor_id = enroll["factor_id"]
            challenge = _client().auth.mfa.challenge({"factor_id": factor_id})
            _client().auth.mfa.verify({
                "factor_id":    factor_id,
                "challenge_id": challenge.id,
                "code":         code,
            })
        except Exception as exc:
            st.error(f"Could not verify code: {exc}")
            return

    st.session_state.pop("_enroll_data", None)
    st.session_state.pop("auth_state", None)
    st.success("MFA enabled. You're all set.")
    st.rerun()
