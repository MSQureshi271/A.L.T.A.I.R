"""
app/providers/notion/notion_router.py — FastAPI OAuth router for Notion.

Endpoints:
  GET /auth/notion/login      → Redirect to Notion consent page
  GET /auth/notion/callback   → Handle Notion redirect, store token
  GET /auth/notion/status     → Check if Notion is connected
  GET /auth/notion/disconnect → Clear stored Notion token
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.providers.notion.notion_auth import (
    get_notion_authorization_url,
    exchange_notion_code,
)
from app.repositories.db_client import store_tokens, is_connected, load_tokens, delete_tokens
from app.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])

_pending_states: dict[str, bool] = {}


@router.get("/notion/login")
async def notion_login() -> RedirectResponse:
    auth_url, state = get_notion_authorization_url()
    _pending_states[state] = True
    return RedirectResponse(url=auth_url)


@router.get("/notion/callback")
async def notion_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    if error:
        return HTMLResponse(
            content=_notion_html_page("Access Denied", f"Notion auth denied: {error}", False)
        )

    if not code or not state or state not in _pending_states:
        return HTMLResponse(
            content=_notion_html_page("Invalid Request", "Missing or invalid parameters.", False),
            status_code=400,
        )

    _pending_states.pop(state, None)

    try:
        token_data = exchange_notion_code(code)
        store_tokens(user_id=settings.DEV_USER_ID, provider="notion", token_data=token_data)
        workspace = token_data.get("workspace_name", "your workspace")
        return HTMLResponse(
            content=_notion_html_page(
                "Connected!",
                f"Notion ({workspace}) connected. You may close this tab.",
                True,
            )
        )
    except Exception as exc:
        logger.error("Notion token exchange failed: %s", exc)
        return HTMLResponse(
            content=_notion_html_page("Error", f"Token exchange failed: {exc}", False),
            status_code=500,
        )


@router.get("/notion/status")
async def notion_status() -> dict:
    connected = is_connected(user_id=settings.DEV_USER_ID, provider="notion")
    if not connected:
        return {"connected": False}
    tokens = load_tokens(user_id=settings.DEV_USER_ID, provider="notion") or {}
    return {
        "connected": True,
        "workspace_name": tokens.get("workspace_name", ""),
        "workspace_icon": tokens.get("workspace_icon", ""),
        "bot_id": tokens.get("bot_id", ""),
    }


@router.get("/notion/disconnect")
async def notion_disconnect() -> dict:
    delete_tokens(user_id=settings.DEV_USER_ID, provider="notion")
    return {"disconnected": True}


def _notion_html_page(title: str, message: str, success: bool) -> str:
    color = "#38B000" if success else "#E63946"
    icon = "✅" if success else "❌"
    return (
        f'<!DOCTYPE html><html><body style="font-family:sans-serif;background:#0d0d0d;'
        f'color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">'
        f'<div style="text-align:center;"><h1 style="color:{color};">{icon} {title}</h1>'
        f'<p>{message}</p></div></body></html>'
    )
