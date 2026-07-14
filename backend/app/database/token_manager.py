"""
app/database/token_manager.py — Google credential refresh utility.

Called by every tool function before it builds a Google API service client.
Automatically refreshes expired tokens and persists the new access token,
so tool calls never fail silently due to expiry.
"""
from __future__ import annotations

import datetime
import logging

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.config import settings
from app.database.db_client import load_tokens, store_tokens

logger = logging.getLogger(__name__)

# Refresh tokens this many seconds before they actually expire to avoid
# race conditions where the token expires mid-request.
_REFRESH_BUFFER_SECONDS = 300  # 5 minutes


def get_google_credentials(user_id: str) -> Credentials:
    """
    Load stored Google OAuth tokens for *user_id*, refresh if needed,
    and return a valid :class:`google.oauth2.credentials.Credentials` object.

    Raises:
        RuntimeError: If no tokens are stored (user hasn't authenticated yet).
    """
    token_data = load_tokens(user_id, "google")
    if not token_data:
        raise RuntimeError(
            "Google Workspace is not connected. "
            "Open the app Settings and tap 'Connect Google' to authenticate."
        )

    # Build Credentials from stored data
    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=token_data.get("scopes", "").split(),
    )

    # Parse expiry if stored
    expires_at_str = token_data.get("expires_at")
    if expires_at_str:
        try:
            creds.expiry = datetime.datetime.fromisoformat(expires_at_str)
        except ValueError:
            creds.expiry = None

    # Refresh if expired or expiring soon
    needs_refresh = (
        not creds.token
        or creds.expiry is None
        or creds.expiry
        <= datetime.datetime.utcnow() + datetime.timedelta(seconds=_REFRESH_BUFFER_SECONDS)
    )

    if needs_refresh:
        logger.info("Google token expired or expiring soon — refreshing for user=%s", user_id)
        try:
            creds.refresh(Request())
            # Persist refreshed token data
            token_data.update(
                {
                    "access_token": creds.token,
                    "expires_at": creds.expiry.isoformat() if creds.expiry else None,
                }
            )
            store_tokens(user_id, "google", token_data)
            logger.info("Google token refreshed and stored for user=%s", user_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to refresh Google token: %s", exc)
            raise RuntimeError(
                "Google token refresh failed — please re-authenticate in Settings."
            ) from exc

    return creds
