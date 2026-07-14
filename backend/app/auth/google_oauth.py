"""
app/auth/google_oauth.py — Google OAuth 2.0 helpers with PKCE support.

Uses google-auth-oauthlib Flow to:
  1. Generate the Google consent screen URL.
  2. Exchange the authorization code for access + refresh tokens.
  3. Return a structured token dict for storage.
"""
from __future__ import annotations

import os
import logging

# Allow OAuth over HTTP for local development.
# IMPORTANT: Remove this in production — HTTPS is required.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from google_auth_oauthlib.flow import Flow  # noqa: E402

from app.config import settings

logger = logging.getLogger(__name__)

# All Google Workspace permissions the app needs
SCOPES: list[str] = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def _build_client_config() -> dict:
    """Build the OAuth2 client config dict from settings."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env. "
            "See .env.example for instructions."
        )
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def create_flow(code_verifier: str | None = None) -> Flow:
    """Create a google-auth-oauthlib Flow configured for this app."""
    return Flow.from_client_config(
        _build_client_config(),
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        code_verifier=code_verifier,
    )


def get_authorization_url() -> tuple[str, str, str]:
    """
    Generate the Google OAuth consent screen URL, a CSRF state token, and code_verifier.

    Returns:
        (authorization_url, state, code_verifier)
    """
    flow = create_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",   # Request a refresh token
        include_granted_scopes="true",
        prompt="consent",        # Always show consent screen → guarantees refresh_token
    )
    logger.info("Generated Google authorization URL (state=%s)", state[:8] + "…")
    return auth_url, state, flow.code_verifier


def exchange_code(code: str, state: str, code_verifier: str | None = None) -> dict:
    """
    Exchange the OAuth authorization *code* for access + refresh tokens.

    Returns:
        A dict containing: access_token, refresh_token, expires_at, scopes.
    """
    flow = create_flow(code_verifier=code_verifier)
    # Reconstruct the state so the library can validate it
    flow.state = state
    flow.fetch_token(code=code)
    creds = flow.credentials

    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at": creds.expiry.isoformat() if creds.expiry else None,
        "scopes": " ".join(creds.scopes or []),
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }
    logger.info("Successfully exchanged auth code for Google tokens.")
    return token_data
