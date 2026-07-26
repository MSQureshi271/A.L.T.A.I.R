"""
app/providers/notion/notion_auth.py — Notion OAuth helpers.

Mirrors the pattern of app/providers/google/google_oauth.py
"""
from __future__ import annotations

import base64
import secrets
import httpx

from app.config.settings import settings


def get_notion_authorization_url() -> tuple[str, str]:
    """Return (authorization_url, state). state is used for CSRF protection."""
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.NOTION_CLIENT_ID,
        "redirect_uri": settings.NOTION_REDIRECT_URI,
        "response_type": "code",
        "owner": "user",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://api.notion.com/v1/oauth/authorize?{query}"
    return url, state


def exchange_notion_code(code: str) -> dict:
    """Exchange an authorization code for a Notion access token.

    Returns the full token payload from Notion (contains access_token,
    workspace_name, workspace_id, workspace_icon, bot_id).
    """
    credentials = base64.b64encode(
        f"{settings.NOTION_CLIENT_ID}:{settings.NOTION_CLIENT_SECRET}".encode()
    ).decode()

    response = httpx.post(
        "https://api.notion.com/v1/oauth/token",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.NOTION_REDIRECT_URI,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
