"""
app/auth/router.py — FastAPI OAuth router.

Endpoints:
  GET  /auth/google/login      → Redirect to Google consent page
  GET  /auth/google/callback   → Handle Google redirect, store tokens
  GET  /auth/google/status     → Check if Google is connected (for Flutter UI)
  GET  /auth/google/disconnect → Clear stored Google tokens
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.google_oauth import get_authorization_url, exchange_code
from app.database.db_client import store_tokens, is_connected, load_tokens
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])

# In-memory CSRF state store mapping state -> code_verifier.
_pending_states: dict[str, str] = {}


# ── Google Auth ───────────────────────────────────────────────────────────────

@router.get("/google/login")
async def google_login() -> RedirectResponse:
    """
    Initiate the Google OAuth flow.

    Flutter opens this URL in the system browser via url_launcher.
    The user sees Google's consent screen and grants permissions.
    """
    try:
        auth_url, state, code_verifier = get_authorization_url()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _pending_states[state] = code_verifier
    logger.info("Redirecting to Google OAuth consent page.")
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """
    Google redirects here after the user grants or denies consent.

    On success:   exchanges the code for tokens, stores them, shows a
                  'Connected!' page the user can close.
    On denial:    shows an error page.
    """
    # ── User denied consent ───────────────────────────────────────────────────
    if error:
        logger.warning("Google OAuth denied: %s", error)
        return HTMLResponse(content=_html_page(
            title="Access Denied",
            message=f"Google authentication was denied: {error}",
            success=False,
        ))

    # ── Validate required params ──────────────────────────────────────────────
    if not code or not state:
        return HTMLResponse(content=_html_page(
            title="Invalid Callback",
            message="Missing code or state parameter.",
            success=False,
        ), status_code=400)

    # ── CSRF check ────────────────────────────────────────────────────────────
    if state not in _pending_states:
        logger.warning("Google callback received unknown state: %s", state)
        return HTMLResponse(content=_html_page(
            title="Security Error",
            message="Invalid state token. Please try connecting again.",
            success=False,
        ), status_code=400)
    
    code_verifier = _pending_states.pop(state, None)

    # ── Exchange code for tokens ──────────────────────────────────────────────
    try:
        token_data = exchange_code(code=code, state=state, code_verifier=code_verifier)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Token exchange failed")
        return HTMLResponse(content=_html_page(
            title="Connection Failed",
            message=f"Failed to exchange auth code: {exc}",
            success=False,
        ), status_code=500)

    # ── Persist tokens ────────────────────────────────────────────────────────
    user_id = settings.DEV_USER_ID
    store_tokens(user_id=user_id, provider="google", token_data=token_data)
    logger.info("Google tokens stored for user=%s", user_id)

    return HTMLResponse(content=_html_page(
        title="Google Connected! ✅",
        message=(
            "Your Google Workspace account has been successfully connected. "
            "Executive Agent can now read your Gmail and Google Calendar. "
            "You can close this tab and return to the app."
        ),
        success=True,
    ))


@router.get("/google/status")
async def google_status() -> dict:
    """
    Returns the current Google connection status.
    Called by Flutter Settings screen on load.
    """
    user_id = settings.DEV_USER_ID
    connected = is_connected(user_id=user_id, provider="google")
    token_data = load_tokens(user_id, "google") if connected else None

    # Extract the scopes granted (first 3 for display)
    scopes: list[str] = []
    if token_data and token_data.get("scopes"):
        raw_scopes = token_data["scopes"].split()
        # Show only meaningful scope names, not full URLs
        scopes = [s.split("/")[-1] for s in raw_scopes if "/" in s][:4]

    return {
        "connected": connected,
        "provider": "google",
        "scopes": scopes,
    }


@router.get("/google/disconnect")
async def google_disconnect() -> dict:
    """Remove stored Google tokens (effectively disconnects the account)."""
    from app.database.db_client import _read_cache, _write_cache, _get_supabase  # noqa: PLC0415

    user_id = settings.DEV_USER_ID
    sb = _get_supabase()

    if sb:
        sb.table("user_credentials").delete().eq("user_id", user_id).eq("provider", "google").execute()
    else:
        cache = _read_cache()
        if user_id in cache and "google" in cache[user_id]:
            del cache[user_id]["google"]
            _write_cache(cache)

    logger.info("Google tokens cleared for user=%s", user_id)
    return {"status": "disconnected", "provider": "google"}


# ── HTML response templates ───────────────────────────────────────────────────

def _html_page(title: str, message: str, success: bool) -> str:
    color = "#38B000" if success else "#E63946"
    icon = "✅" if success else "❌"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0F0F12; color: #F8F9FA;
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
    }}
    .card {{
      background: #1E1E24; border: 1px solid rgba(255,255,255,0.08);
      border-radius: 20px; padding: 40px; max-width: 420px; text-align: center;
    }}
    .icon {{ font-size: 56px; margin-bottom: 20px; }}
    h1 {{ color: {color}; font-size: 22px; margin-bottom: 12px; }}
    p {{ color: #ADB5BD; line-height: 1.6; font-size: 14px; }}
    .close-hint {{
      margin-top: 24px; padding: 10px 20px;
      background: rgba(255,255,255,0.05); border-radius: 10px;
      font-size: 12px; color: #6C757D;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
    <div class="close-hint">You can safely close this tab.</div>
  </div>
</body>
</html>"""
