"""
app/main.py  —  FastAPI application entry point.

Routes:
  GET  /health                  → server health check
  POST /agent/text              → run agent on plain-text command (JSON)
  POST /agent/execute-action    → execute an approved staged action (real APIs)
  GET  /auth/google/login       → initiate Google OAuth flow
  GET  /auth/google/callback    → Google OAuth callback (stores tokens)
  GET  /auth/google/status      → check Google connection status (Flutter UI)
  GET  /auth/google/disconnect  → clear stored Google tokens

Streaming via Server-Sent Events (SSE) lets Flutter / any HTTP client
consume the live agent log as it runs.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Body, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.agents.coordinator import run_agent, run_agent_audio
from app.auth.router import router as auth_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Executive Agent API",
    description="Multi-agent productivity backend powered by Gemini 2.0 Flash.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGINS_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/auth")

# ── Request / Response models ─────────────────────────────────────────────────

class TextCommandRequest(BaseModel):
    text: str = Field(..., min_length=1, description="The transcribed voice command.")


class ExecuteActionRequest(BaseModel):
    action: str = Field(..., description="The action type, e.g. 'send_email'.")
    data: dict = Field(..., description="The (possibly user-edited) action payload.")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health() -> dict:
    """Returns 200 OK with basic server info."""
    return {"status": "ok", "version": "0.2.0"}


@app.post("/agent/text", tags=["Agent"])
async def agent_text(
    body: Annotated[TextCommandRequest, Body()],
) -> StreamingResponse:
    """
    Accepts a plain-text command and streams the agent's execution log back
    as Server-Sent Events (SSE).

    Each SSE line is a JSON object:

        data: {"type": "log",              "message": "..."}
        data: {"type": "result",           "text": "..."}
        data: {"type": "approval_required","action": "...","data": {...}}
        data: {"type": "error",            "message": "..."}
        data: {"type": "done"}
    """
    def event_stream():
        try:
            for event in run_agent(body.text):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in agent loop")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering for SSE
        },
    )


@app.post("/agent/voice", tags=["Agent"])
async def agent_voice(
    file: Annotated[UploadFile, File(description="Recorded audio file from the device microphone.")],
) -> StreamingResponse:
    """
    Accepts a raw audio file (m4a, wav, webm) and streams the agent's
    execution log back as Server-Sent Events (SSE).

    Gemini processes the audio natively — no separate STT service required.
    SSE event shapes are identical to /agent/text.
    """
    audio_bytes = await file.read()
    mime_type = file.content_type or "audio/m4a"

    # Save a local copy of the received audio file for developer inspection
    try:
        # Determine appropriate file extension from mime type
        ext = "wav" if "wav" in mime_type else "m4a"
        save_path = f"latest_received_command.{ext}"
        with open(save_path, "wb") as f:
            f.write(audio_bytes)
        logger.info("Saved copy of received voice command to backend/%s", save_path)
    except Exception as exc:
        logger.error("Failed to save copy of received audio: %s", exc)

    def event_stream():
        try:
            for event in run_agent_audio(audio_bytes, mime_type):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in audio agent loop")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/agent/execute-action", tags=["Agent"])
async def execute_action(
    body: Annotated[ExecuteActionRequest, Body()],
) -> dict:
    """
    Called after the user approves a staged action in the Flutter UI.

    Dispatches to the real Google Workspace API functions.
    """
    action = body.action
    data = body.data
    user_id = settings.DEV_USER_ID

    logger.info("Executing approved action: %s | data=%s", action, data)

    if action == "send_email":
        # Import here to avoid circular dependency issues at startup
        from app.tools.email_tools import send_email_via_gmail  # noqa: PLC0415
        try:
            message = send_email_via_gmail(
                to=data.get("to", ""),
                subject=data.get("subject", ""),
                body=data.get("body", ""),
                user_id=user_id,
            )
            return {"status": "success", "message": message}
        except RuntimeError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gmail send failed")
            raise HTTPException(status_code=500, detail=f"Gmail send failed: {exc}") from exc

    elif action == "create_calendar_event":
        from app.tools.calendar_tools import create_google_calendar_event  # noqa: PLC0415
        try:
            message = create_google_calendar_event(
                title=data.get("title", "Meeting"),
                date=data.get("date", ""),
                time=data.get("time", "09:00"),
                duration_minutes=int(data.get("duration_minutes", 60)),
                attendees=data.get("attendees", []),
                user_id=user_id,
            )
            return {"status": "success", "message": message}
        except RuntimeError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Calendar event creation failed")
            raise HTTPException(status_code=500, detail=f"Calendar error: {exc}") from exc

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


# ── Dev entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
    )
