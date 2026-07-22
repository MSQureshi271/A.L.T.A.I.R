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

import asyncio
from contextlib import asynccontextmanager
import json
import logging
from typing import Annotated


import uvicorn
from fastapi import FastAPI, BackgroundTasks, Body, File, Form, HTTPException, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from app.config.settings import settings
from app.ai.coordinator import run_agent, run_agent_audio
from app.ai.planner.planner import plan as planner_plan
from app.ai.executor.executor import execute_plan, save_active_plan, load_active_plan, load_active_plan_record
from app.ai.planner.planner_schema import TaskPlan, TaskStep

from app.providers.google.oauth import router as auth_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the watcher scheduler loop & document recovery
    import asyncio
    from app.watchers.scheduler import start_scheduler_loop  # noqa: PLC0415
    task = asyncio.create_task(start_scheduler_loop())
    asyncio.create_task(recover_stuck_documents())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def recover_stuck_documents() -> None:
    """Scans for document records stuck in 'processing' state on server startup and marks them as error."""
    try:
        from app.repositories.document_repository import load_document_records, update_document_status  # noqa: PLC0415
        user_id = settings.DEV_USER_ID
        records = load_document_records(user_id)
        stuck_records = [r for r in records if r.status == "processing"]
        if stuck_records:
            logger.info("Found %d stuck document(s) in 'processing' state on startup. Recovering...", len(stuck_records))
            for rec in stuck_records:
                update_document_status(
                    document_id=rec.id,
                    status="error",
                    error_message="Ingestion was interrupted by a server restart. Please re-upload the document.",
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stuck document recovery failed: %s", exc)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Executive Agent API",
    description="Multi-agent productivity backend powered by Gemini 2.0 Flash.",
    version="0.2.0",
    lifespan=lifespan,
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
    history: list[dict] = Field(
        default_factory=list,
        description="Prior conversation turns [{role, text}]. Max 20 entries."
    )


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
    async def event_stream():
        try:
            # ── Step 1: Planner produces a structured task plan ──────────────
            try:
                task_plan = planner_plan(body.text, history=body.history)
            except Exception as plan_exc:  # noqa: BLE001
                logger.warning("Planner failed (%s) — falling back to coordinator", plan_exc)
                # Fallback: run the old coordinator loop if the planner fails
                for event in run_agent(body.text, history=body.history):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                return

            # Emit the plan so Flutter can show a preview card
            yield f"data: {json.dumps({'type': 'plan', 'plan': task_plan.model_dump()}, ensure_ascii=False)}\n\n"

            # ── Step 2: Executor processes the plan ───────────────────────────
            async for event in execute_plan(task_plan, user_text=body.text, history=body.history):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in agent pipeline")
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


@app.post("/agent/voice", tags=["Agent"])
async def agent_voice(
    file: Annotated[UploadFile, File(description="Recorded audio file from the device microphone.")],
    history: Annotated[str, Form(description="Serialized JSON history list.")] = "[]",
) -> StreamingResponse:
    """
    Accepts a raw audio file (m4a, wav, webm) and a conversation history,
    streams the transcribed user text first, then the task plan, and
    finally the execution logs and results.
    """
    audio_bytes = await file.read()
    mime_type = file.content_type or "audio/m4a"

    try:
        history_list = json.loads(history)
    except Exception:
        history_list = []

    # Save a local copy of the received audio file for developer inspection
    try:
        ext = "wav" if "wav" in mime_type else "m4a"
        save_path = f"latest_received_command.{ext}"
        with open(save_path, "wb") as f:
            f.write(audio_bytes)
        logger.info("Saved copy of received voice command to backend/%s", save_path)
    except Exception as exc:
        logger.error("Failed to save copy of received audio: %s", exc)

    async def event_stream():
        try:
            # ── Pass 1: Transcribe the audio via Gemini multimodal ─────────────
            yield f"data: {json.dumps({'type': 'log', 'message': '🎙️  Processing audio transcription…'}, ensure_ascii=False)}\n\n"
            
            if not settings.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is not set.")
                
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[

                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                inline_data=types.Blob(
                                    data=audio_bytes,
                                    mime_type=mime_type,
                                )
                            ),
                            types.Part(
                                text=(
                                    "Transcribe the user's voice command in the audio exactly. "
                                    "Do not add any greeting, explanation, or commentary. "
                                    "Output only the transcription."
                                )
                            ),
                        ],
                    )
                ],
            )
            
            transcript_text = response.text.strip() if response.text else ""
            if not transcript_text:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Could not transcribe the audio.'}, ensure_ascii=False)}\n\n"
                return

            # Yield the final transcript text so Flutter can show it in a chat bubble
            yield f"data: {json.dumps({'type': 'transcript', 'text': transcript_text}, ensure_ascii=False)}\n\n"

            # ── Pass 2: Produce the structured plan ───────────────────────────
            yield f"data: {json.dumps({'type': 'log', 'message': f'🧠 Planner → planning: \"{transcript_text}\"'}, ensure_ascii=False)}\n\n"
            
            try:
                task_plan = planner_plan(transcript_text, history=history_list)
            except Exception as plan_exc:
                logger.warning("Planner failed (%s) — falling back to direct response", plan_exc)
                # Fallback to direct agent run loop
                for event in run_agent(transcript_text, history=history_list):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'plan', 'plan': task_plan.model_dump()}, ensure_ascii=False)}\n\n"

            # ── Pass 3: Execute the plan ──────────────────────────────────────
            async for event in execute_plan(task_plan, user_text=transcript_text, history=history_list):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


        except Exception as exc:
            logger.exception("Unhandled error in audio agent pipeline")
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
        from app.providers.google.gmail.api import send_email_via_gmail  # noqa: PLC0415
        try:
            message = send_email_via_gmail(
                to=data.get("to", ""),
                subject=data.get("subject", ""),
                body=data.get("body", ""),
                user_id=user_id,
                attachments=data.get("attachments") or None,
            )
            return {"status": "success", "message": message}
        except RuntimeError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gmail send failed")
            raise HTTPException(status_code=500, detail=f"Gmail send failed: {exc}") from exc

    elif action == "send_email_with_attachment":
        from app.providers.google.gmail.api import send_email_via_gmail  # noqa: PLC0415
        try:
            message = send_email_via_gmail(
                to=data.get("to", "") or data.get("recipient", ""),
                subject=data.get("subject", ""),
                body=data.get("body", ""),
                user_id=user_id,
                attachments=data.get("attachments") or [],
            )
            return {"status": "success", "message": message}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gmail send with attachment failed")
            raise HTTPException(status_code=500, detail=f"Gmail send with attachment failed: {exc}") from exc

    elif action == "download_attachment":
        from app.providers.google.gmail.api import _ingest_attachment_bytes  # noqa: PLC0415
        try:
            attachments_to_save = [
                a for a in (data.get("attachments") or [])
                if a.get("selected", True)
            ]
            if not attachments_to_save:
                return {"status": "success", "message": "No attachments selected for download."}

            results = []
            for att in attachments_to_save:
                doc_ref = _ingest_attachment_bytes(
                    user_id=user_id,
                    email_id=att.get("email_id", data.get("email_id", "")),
                    attachment_id=att["attachment_id"],
                    filename=att["filename"],
                    mime_type=att.get("mime_type", "application/octet-stream"),
                )
                results.append(f"{att['filename']} → {doc_ref}")
            return {"status": "success", "message": "✅ " + "; ".join(results)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Attachment download failed")
            raise HTTPException(status_code=500, detail=f"Attachment download failed: {exc}") from exc

    elif action == "delete_email":
        from app.providers.google.gmail.api import delete_email_via_gmail  # noqa: PLC0415
        try:
            message = delete_email_via_gmail(
                email_id=data.get("email_id", ""),
                sender=data.get("sender", ""),
                subject=data.get("subject", ""),
                user_id=user_id,
                double_confirmed=data.get("double_confirmed", False),
            )
            return {"status": "success", "message": message}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gmail delete failed")
            raise HTTPException(status_code=500, detail=f"Gmail delete failed: {exc}") from exc

    elif action == "create_calendar_event":
        from app.providers.google.calendar.api import create_google_calendar_event  # noqa: PLC0415
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

    elif action == "reschedule_calendar_event":
        from app.providers.google.calendar.api import reschedule_google_calendar_event  # noqa: PLC0415
        try:
            message = reschedule_google_calendar_event(
                event_id=data.get("event_id", ""),
                title=data.get("title", ""),
                new_date=data.get("new_date", ""),
                new_time=data.get("new_time", ""),
                new_duration_minutes=int(data.get("new_duration_minutes", 60) or 60),
                user_id=user_id,
            )
            return {"status": "success", "message": message}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Calendar event reschedule failed")
            raise HTTPException(status_code=500, detail=f"Calendar reschedule error: {exc}") from exc

    elif action == "delete_calendar_event":
        from app.providers.google.calendar.api import delete_google_calendar_event  # noqa: PLC0415
        try:
            message = delete_google_calendar_event(
                event_id=data.get("event_id", ""),
                title=data.get("title", ""),
                user_id=user_id,
            )
            return {"status": "success", "message": message}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Calendar event deletion failed")
            raise HTTPException(status_code=500, detail=f"Calendar deletion error: {exc}") from exc

    elif action == "save_contact":
        from app.capabilities.memory.memory_manager import save_contact as mem_save_contact  # noqa: PLC0415
        try:
            mem_save_contact(
                user_id=user_id,
                name=data.get("name", ""),
                email=data.get("email"),
                phone=data.get("phone"),
                company=data.get("company"),
                notes=data.get("notes"),
            )
            return {"status": "success", "message": f"Remembered contact '{data.get('name')}'."}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to save contact: {exc}") from exc

    elif action == "save_preference":
        from app.capabilities.memory.memory_manager import save_preference as mem_save_pref  # noqa: PLC0415
        try:
            val = data.get("value")
            try:
                val = json.loads(val)
            except Exception:  # noqa: BLE001
                pass
            mem_save_pref(
                user_id=user_id,
                category=data.get("category", ""),
                key=data.get("key", ""),
                value=val,
            )
            return {"status": "success", "message": f"Remembered preference '{data.get('category')}/{data.get('key')}'."}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to save preference: {exc}") from exc

    elif action == "save_routine":
        from app.capabilities.memory.memory_manager import save_routine as mem_save_routine  # noqa: PLC0415
        try:
            steps = [s.strip() for s in data.get("steps", "").split(",") if s.strip()]
            mem_save_routine(
                user_id=user_id,
                name=data.get("name", ""),
                steps=steps,
            )
            return {"status": "success", "message": f"Remembered routine '{data.get('name')}'."}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to save routine: {exc}") from exc

    elif action == "save_knowledge":
        from app.capabilities.memory.memory_manager import save_knowledge as mem_save_knowledge  # noqa: PLC0415
        try:
            mem_save_knowledge(
                user_id=user_id,
                text=data.get("text", ""),
                importance=int(data.get("importance", 1)),
            )
            return {"status": "success", "message": "Fact stored in long-term memory."}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to save fact: {exc}") from exc

    elif action == "delete_memory":
        try:
            category = data.get("category", "")
            key = data.get("key", "")
            if category == "contacts":
                from app.capabilities.memory.memory_manager import delete_contact  # noqa: PLC0415
                delete_contact(user_id, key)
            elif category == "preferences":
                parts = key.split("/")
                if len(parts) == 2:
                    from app.capabilities.memory.memory_manager import delete_preference  # noqa: PLC0415
                    delete_preference(user_id, parts[0], parts[1])
            elif category == "routines":
                from app.capabilities.memory.memory_manager import delete_routine  # noqa: PLC0415
                delete_routine(user_id, key)
            elif category == "knowledge":
                from app.capabilities.memory.memory_manager import delete_knowledge  # noqa: PLC0415
                delete_knowledge(user_id, key)
            return {"status": "success", "message": f"Forgot '{key}'."}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to forget: {exc}") from exc

        from app.repositories.watcher_repository import save_watcher, save_watcher_trigger, save_watcher_action  # noqa: PLC0415
        from app.watchers.builder import compile_trigger_dsl  # noqa: PLC0415
        import uuid  # noqa: PLC0415
        try:
            watcher_id = str(uuid.uuid4())
            provider = data.get("provider", "gmail")
            desc = data.get("description", "")
            actions_list = data.get("actions", ["notify"])
            if isinstance(actions_list, str):
                actions_list = [a.strip() for a in actions_list.split(",") if a.strip()]

            condition_json = compile_trigger_dsl(provider, desc)
            save_watcher(user_id, watcher_id, desc, enabled=True)

            event_type = "email_received" if provider == "gmail" else "event_updated"
            save_watcher_trigger(user_id, watcher_id, provider, event_type, condition_json)

            for idx, action_type in enumerate(actions_list):
                save_watcher_action(user_id, watcher_id, action_type, {}, idx)

            # Register push/webhook watch subscription
            if provider == "gmail":
                from app.providers.google.gmail.watch import register_gmail_watch  # noqa: PLC0415
                register_gmail_watch(user_id)
            elif provider == "calendar":
                from app.providers.google.calendar.watch import register_calendar_watch  # noqa: PLC0415
                register_calendar_watch(user_id)

            return {
                "status": "success",
                "message": f"Successfully created Watcher '{desc}' to monitor {provider}."
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create watcher")
            raise HTTPException(status_code=500, detail=f"Failed to create watcher: {exc}") from exc

        from app.repositories.watcher_repository import delete_watcher, load_watchers  # noqa: PLC0415
        try:
            watcher_id = data.get("watcher_id")
            desc = data.get("description", "")

            if not watcher_id and desc:
                watchers = load_watchers(user_id)
                for w in watchers:
                    if desc.lower() in w["description"].lower():
                        watcher_id = w["id"]
                        desc = w["description"]
                        break

            if not watcher_id:
                raise ValueError(f"No watcher matching '{desc or watcher_id}' found.")

            delete_watcher(user_id, watcher_id)
            return {"status": "success", "message": f"Successfully deleted Watcher '{desc or watcher_id}'."}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to delete watcher")
            raise HTTPException(status_code=500, detail=f"Failed to delete watcher: {exc}") from exc

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@app.get("/agent/memory", tags=["Memory"])
async def get_all_memory() -> dict:
    """Retrieve all structured and unstructured memories for the user."""
    from app.capabilities.memory.memory_manager import (  # noqa: PLC0415
        load_contacts,
        load_preferences,
        load_routines,
        load_knowledge,
    )
    user_id = settings.DEV_USER_ID
    return {
        "contacts": load_contacts(user_id),
        "preferences": load_preferences(user_id),
        "routines": load_routines(user_id),
        "knowledge": load_knowledge(user_id),
    }


@app.delete("/agent/memory", tags=["Memory"])
async def delete_memory_entry(category: str, key: str) -> dict:
    """Delete a memory record matching the category and key."""
    user_id = settings.DEV_USER_ID
    try:
        if category == "contacts":
            from app.capabilities.memory.memory_manager import delete_contact  # noqa: PLC0415
            delete_contact(user_id, key)
        elif category == "preferences":
            parts = key.split("/")
            if len(parts) == 2:
                from app.capabilities.memory.memory_manager import delete_preference  # noqa: PLC0415
                delete_preference(user_id, parts[0], parts[1])
        elif category == "routines":
            from app.capabilities.memory.memory_manager import delete_routine  # noqa: PLC0415
            delete_routine(user_id, key)
        elif category == "knowledge":
            from app.capabilities.memory.memory_manager import delete_knowledge  # noqa: PLC0415
            delete_knowledge(user_id, key)
        return {"status": "success", "message": f"Successfully deleted memory: {key}"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Step Resumption Endpoint ──────────────────────────────────────────────────

class ResumePlanRequest(BaseModel):
    plan_id: str
    step_id: int
    edited_data: dict | None = None


def _execute_write_step_action(action: str, parameters: dict, user_id: str) -> str:
    """Invokes the real write action python tool function."""
    if action == "draft_email":
        from app.providers.google.gmail.api import send_email_via_gmail  # noqa: PLC0415
        # Support attachments if the plan carried resolved attachment metadata
        attachments = parameters.get("attachments") or None
        return send_email_via_gmail(
            to=parameters.get("recipient", ""),
            subject=parameters.get("subject", ""),
            body=parameters.get("body", ""),
            user_id=user_id,
            attachments=attachments,
        )
    elif action == "draft_email_with_attachment":
        from app.providers.google.gmail.api import send_email_via_gmail  # noqa: PLC0415
        return send_email_via_gmail(
            to=parameters.get("recipient", "") or parameters.get("to", ""),
            subject=parameters.get("subject", ""),
            body=parameters.get("body", ""),
            user_id=user_id,
            attachments=parameters.get("attachments") or [],
        )
    elif action == "send_email_with_attachment":
        # Called from resume-plan after user approves the HITL card
        from app.providers.google.gmail.api import send_email_via_gmail  # noqa: PLC0415
        return send_email_via_gmail(
            to=parameters.get("to", ""),
            subject=parameters.get("subject", ""),
            body=parameters.get("body", ""),
            user_id=user_id,
            attachments=parameters.get("attachments") or [],
        )
    elif action == "download_attachment":
        # Called from resume-plan after user approves the attachment download card
        from app.providers.google.gmail.api import _ingest_attachment_bytes  # noqa: PLC0415
        # parameters.attachments is the list from the batch confirmation card
        # Each entry: {email_id, attachment_id, filename, mime_type, selected: True/False}
        attachments_to_save = [
            a for a in (parameters.get("attachments") or [])
            if a.get("selected", True)  # deselected items have selected=False
        ]
        if not attachments_to_save:
            return "No attachments selected for download."
        results = []
        for att in attachments_to_save:
            doc_ref = _ingest_attachment_bytes(
                user_id=user_id,
                email_id=att.get("email_id", parameters.get("email_id", "")),
                attachment_id=att["attachment_id"],
                filename=att["filename"],
                mime_type=att.get("mime_type", "application/octet-stream"),
            )
            results.append(f"{att['filename']} → {doc_ref}")
        return "✅ " + "; ".join(results)
    elif action == "delete_email":
        from app.providers.google.gmail.api import delete_email_via_gmail  # noqa: PLC0415
        return delete_email_via_gmail(
            email_id=parameters.get("email_id", ""),
            sender=parameters.get("sender"),
            subject=parameters.get("subject"),
            user_id=user_id
        )
    elif action == "create_event":
        from app.providers.google.calendar.api import create_google_calendar_event  # noqa: PLC0415
        return create_google_calendar_event(
            title=parameters.get("title", "Meeting"),
            date=parameters.get("date", ""),
            time=parameters.get("time", "09:00"),
            duration_minutes=int(parameters.get("duration_minutes", 60)),
            attendees=parameters.get("attendees", []),
            user_id=user_id
        )
    elif action == "reschedule_event":
        from app.providers.google.calendar.api import reschedule_google_calendar_event  # noqa: PLC0415
        return reschedule_google_calendar_event(
            event_id=parameters.get("event_id", ""),
            title=parameters.get("title", ""),
            new_date=parameters.get("new_date", ""),
            new_time=parameters.get("new_time", ""),
            new_duration_minutes=int(parameters.get("new_duration_minutes", 60) or 60),
            user_id=user_id
        )
    elif action == "delete_event":
        from app.providers.google.calendar.api import delete_google_calendar_event  # noqa: PLC0415
        return delete_google_calendar_event(
            event_id=parameters.get("event_id", ""),
            title=parameters.get("title", ""),
            user_id=user_id
        )
    elif action == "save_contact":
        from app.capabilities.memory.memory_manager import save_contact as mem_save_contact  # noqa: PLC0415
        mem_save_contact(
            user_id=user_id,
            name=parameters.get("name", ""),
            email=parameters.get("email"),
            phone=parameters.get("phone"),
            company=parameters.get("company"),
            notes=parameters.get("notes"),
        )
        return f"Remembered contact '{parameters.get('name')}'."
    elif action == "save_preference":
        from app.capabilities.memory.memory_manager import save_preference as mem_save_pref  # noqa: PLC0415
        val = parameters.get("value")
        try:
            val = json.loads(val)
        except Exception:  # noqa: BLE001
            pass
        mem_save_pref(
            user_id=user_id,
            category=parameters.get("category", ""),
            key=parameters.get("key", ""),
            value=val,
        )
        return f"Remembered preference '{parameters.get('category')}/{parameters.get('key')}'."
    elif action == "save_routine":
        from app.capabilities.memory.memory_manager import save_routine as mem_save_routine  # noqa: PLC0415
        steps_val = parameters.get("steps", "")
        steps = steps_val if isinstance(steps_val, list) else [s.strip() for s in steps_val.split(",") if s.strip()]
        mem_save_routine(
            user_id=user_id,
            name=parameters.get("name", ""),
            steps=steps,
        )
        return f"Remembered routine '{parameters.get('name')}'."
    elif action == "save_knowledge":
        from app.capabilities.memory.memory_manager import save_knowledge as mem_save_knowledge  # noqa: PLC0415
        mem_save_knowledge(
            user_id=user_id,
            text=parameters.get("text", ""),
            importance=int(parameters.get("importance", 1)),
        )
        return "Fact stored in long-term memory."
    elif action == "delete_memory":
        category = parameters.get("category", "")
        key = parameters.get("key", "")
        if category == "contacts":
            from app.capabilities.memory.memory_manager import delete_contact  # noqa: PLC0415
            delete_contact(user_id, key)
        elif category == "preferences":
            parts = key.split("/")
            if len(parts) == 2:
                from app.capabilities.memory.memory_manager import delete_preference  # noqa: PLC0415
                delete_preference(user_id, parts[0], parts[1])
        elif category == "routines":
            from app.capabilities.memory.memory_manager import delete_routine  # noqa: PLC0415
            delete_routine(user_id, key)
        elif category == "knowledge":
            from app.capabilities.memory.memory_manager import delete_knowledge  # noqa: PLC0415
            delete_knowledge(user_id, key)
        return f"Forgot '{key}'."

    elif action == "create_watcher":
        from app.repositories.watcher_repository import save_watcher, save_watcher_trigger, save_watcher_action  # noqa: PLC0415
        from app.watchers.builder import compile_trigger_dsl  # noqa: PLC0415
        import uuid  # noqa: PLC0415
        watcher_id = str(uuid.uuid4())
        provider = parameters.get("provider", "gmail")
        desc = parameters.get("description", "")
        actions_list = parameters.get("actions", ["notify"])
        if isinstance(actions_list, str):
            actions_list = [a.strip() for a in actions_list.split(",") if a.strip()]

        condition_json = compile_trigger_dsl(provider, desc)
        save_watcher(user_id, watcher_id, desc, enabled=True)

        event_type = "email_received" if provider == "gmail" else "event_updated"
        save_watcher_trigger(user_id, watcher_id, provider, event_type, condition_json)

        for idx, action_type in enumerate(actions_list):
            save_watcher_action(user_id, watcher_id, action_type, {}, idx)

        # Register push/webhook watch subscription
        if provider == "gmail":
            from app.providers.google.gmail.watch import register_gmail_watch  # noqa: PLC0415
            register_gmail_watch(user_id)
        elif provider == "calendar":
            from app.providers.google.calendar.watch import register_calendar_watch  # noqa: PLC0415
            register_calendar_watch(user_id)

        return f"Successfully created Watcher '{desc}' to monitor {provider}."

    elif action == "delete_watcher":
        from app.repositories.watcher_repository import delete_watcher, load_watchers  # noqa: PLC0415
        watcher_id = parameters.get("watcher_id")
        desc = parameters.get("description", "")

        if not watcher_id and desc:
            watchers = load_watchers(user_id)
            for w in watchers:
                if desc.lower() in w["description"].lower():
                    watcher_id = w["id"]
                    desc = w["description"]
                    break

        if not watcher_id:
            raise ValueError(f"No watcher matching '{desc or watcher_id}' found.")

        delete_watcher(user_id, watcher_id)
        return f"Successfully deleted Watcher '{desc or watcher_id}'."

    else:
        raise ValueError(f"Unknown action: {action}")


@app.post("/agent/resume-plan", tags=["Agent"])
async def resume_plan(body: ResumePlanRequest) -> StreamingResponse:
    """
    Called when the user approves a paused workflow step in Flutter.
    Runs the approved action, updates plan status, and streams the remaining execution logs.
    """
    user_id = settings.DEV_USER_ID
    logger.info("Resuming plan %s, approved step %d", body.plan_id, body.step_id)

    async def resume_stream():
        try:
            # 1. Load active plan record
            record = load_active_plan_record(body.plan_id)
            if not record:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Active plan not found.'})}\n\n"
                return

            plan_json = record.get("plan_json")
            user_text = record.get("user_text", "")
            history = record.get("history", [])

            plan = TaskPlan.model_validate(plan_json)

            # 2. Locate step
            step = next((s for s in plan.steps if s.step_id == body.step_id), None)
            if not step:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Step {body.step_id} not found in plan.'})}\n\n"
                return

            if step.status != "running" or not step.requires_confirmation:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Step {body.step_id} is not awaiting approval.'})}\n\n"
                return

            # 3. Apply edits if provided
            if body.edited_data:
                logger.info("Applying user edits to step parameters: %s", body.edited_data)
                if step.action == "draft_email":
                    step.parameters["recipient"] = body.edited_data.get("to", step.parameters.get("recipient"))
                    step.parameters["subject"] = body.edited_data.get("subject", step.parameters.get("subject"))
                    step.parameters["body"] = body.edited_data.get("body", step.parameters.get("body"))
                elif step.action == "create_event":
                    step.parameters["title"] = body.edited_data.get("title", step.parameters.get("title"))
                    step.parameters["date"] = body.edited_data.get("date", step.parameters.get("date"))
                    step.parameters["time"] = body.edited_data.get("time", step.parameters.get("time"))
                    step.parameters["duration_minutes"] = int(body.edited_data.get("duration_minutes", step.parameters.get("duration_minutes") or 60))
                    step.parameters["attendees"] = body.edited_data.get("attendees", step.parameters.get("attendees"))
                else:
                    for k, v in body.edited_data.items():
                        if k not in ["plan_id", "step_id", "safety_warning", "requires_double_confirm", "safety_level"]:
                            step.parameters[k] = v

            # 4. Execute the approved step
            yield f"data: {json.dumps({'type': 'log', 'message': f'⚡ Executing approved action: {step.description}'}, ensure_ascii=False)}\n\n"
            
            try:
                # Execute tool function in worker thread
                result_text = await asyncio.to_thread(_execute_write_step_action, step.action, step.parameters, user_id)
                step.status = "completed"
                step.output = result_text
                yield f"data: {json.dumps({'type': 'log', 'message': f'✅ {result_text}'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'tool_result', 'step_id': step.step_id, 'result': result_text}, ensure_ascii=False)}\n\n"
            except Exception as exc:  # noqa: BLE001
                logger.exception("Approved step execution failed")
                step.status = "failed"
                save_active_plan(plan)
                yield f"data: {json.dumps({'type': 'error', 'message': f'Action execution failed: {exc}'}, ensure_ascii=False)}\n\n"
                return

            save_active_plan(plan)

            # 5. Resume execution of the rest of the plan
            async for event in execute_plan(plan, user_text=user_text, history=history):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in plan resumption")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        resume_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Watchers REST APIs ────────────────────────────────────────────────────────


@app.get("/agent/watchers", tags=["Watchers"])
async def get_watchers() -> list[dict]:
    """Retrieve all watchers for the active user."""
    from app.repositories.watcher_repository import load_watchers  # noqa: PLC0415
    return load_watchers(settings.DEV_USER_ID)


@app.post("/agent/watchers/{watcher_id}/toggle", tags=["Watchers"])
async def toggle_watcher(watcher_id: str) -> dict:
    """Toggle a watcher state (enabled/disabled)."""
    from app.repositories.watcher_repository import load_watchers, save_watcher  # noqa: PLC0415
    user_id = settings.DEV_USER_ID
    watchers = load_watchers(user_id)
    target = None
    for w in watchers:
        if w["id"] == watcher_id:
            target = w
            break
    if not target:
        raise HTTPException(status_code=404, detail="Watcher not found")

    new_state = not target["enabled"]
    save_watcher(user_id, watcher_id, target["description"], enabled=new_state)
    return {"status": "success", "enabled": new_state}


@app.delete("/agent/watchers/{watcher_id}", tags=["Watchers"])
async def delete_watcher_endpoint(watcher_id: str) -> dict:
    """Delete a watcher configuration."""
    from app.repositories.watcher_repository import delete_watcher  # noqa: PLC0415
    delete_watcher(settings.DEV_USER_ID, watcher_id)
    return {"status": "success", "message": "Watcher deleted."}


@app.get("/agent/watchers/{watcher_id}/history", tags=["Watchers"])
async def get_watcher_history_endpoint(watcher_id: str) -> list[dict]:
    """Retrieve execution log history for a watcher."""
    from app.repositories.watcher_repository import load_watcher_history  # noqa: PLC0415
    return load_watcher_history(settings.DEV_USER_ID, watcher_id)


@app.post("/webhook/google/gmail", tags=["Webhooks"])
async def webhook_google_gmail(payload: dict = Body(...)) -> dict:
    """Receives Gmail push notifications from Google Cloud Pub/Sub."""
    logger.info("Received Gmail webhook event: %s", payload)

    user_id = settings.DEV_USER_ID
    from app.providers.google.gmail.event_source import GmailEventSource
    from app.repositories.watcher_repository import load_watchers
    from app.watchers.engine import execute_watcher_on_event
    from app.repositories.db_client import db_load_items, db_store_item
    from datetime import datetime, timezone

    # 1. Fetch checkpoints
    checkpoints = db_load_items("watcher_checkpoints", user_id)
    last_checked = datetime.now(timezone.utc)
    for c in checkpoints:
        if c.get("provider") == "gmail":
            last_checked = datetime.fromisoformat(c["last_checked"])
            break

    # 2. Poll new events
    source = GmailEventSource()
    events = source.poll_events(user_id, last_checked)

    if events:
        new_checkpoint = max(e.timestamp for e in events)
        db_store_item("watcher_checkpoints", {
            "user_id": user_id,
            "provider": "gmail",
            "last_checked": new_checkpoint.isoformat(),
        }, ["user_id", "provider"])

        watchers = load_watchers(user_id)
        gmail_watchers = [w for w in watchers if w["enabled"] and w.get("trigger", {}).get("provider") == "gmail"]

        for w in gmail_watchers:
            for event in events:
                execute_watcher_on_event(w, event)

    return {"status": "processed"}


@app.post("/webhook/google/calendar", tags=["Webhooks"])
async def webhook_google_calendar(
    payload: dict = Body(None),
    x_goog_resource_state: str | None = Header(None, alias="X-Goog-Resource-State"),
) -> dict:
    """Receives primary calendar sync notifications from Google Calendar API."""
    logger.info("Received Calendar webhook event resource-state: %s", x_goog_resource_state)
    if x_goog_resource_state == "sync":
        return {"status": "sync_acknowledged"}

    user_id = settings.DEV_USER_ID
    from app.providers.google.calendar.event_source import CalendarEventSource
    from app.repositories.watcher_repository import load_watchers
    from app.watchers.engine import execute_watcher_on_event
    from app.repositories.db_client import db_load_items, db_store_item
    from datetime import datetime, timezone

    # 1. Fetch checkpoints
    checkpoints = db_load_items("watcher_checkpoints", user_id)
    last_checked = datetime.now(timezone.utc)
    for c in checkpoints:
        if c.get("provider") == "calendar":
            last_checked = datetime.fromisoformat(c["last_checked"])
            break

    # 2. Poll new events
    source = CalendarEventSource()
    events = source.poll_events(user_id, last_checked)

    if events:
        new_checkpoint = max(e.timestamp for e in events)
        db_store_item("watcher_checkpoints", {
            "user_id": user_id,
            "provider": "calendar",
            "last_checked": new_checkpoint.isoformat(),
        }, ["user_id", "provider"])

        watchers = load_watchers(user_id)
        cal_watchers = [w for w in watchers if w["enabled"] and w.get("trigger", {}).get("provider") == "calendar"]

        for w in cal_watchers:
            for event in events:
                execute_watcher_on_event(w, event)

    return {"status": "processed"}


# ── Email Attachment Endpoints ─────────────────────────────────────────────────


@app.get("/email/{email_id}/attachments", tags=["Email"])
async def get_email_attachments(email_id: str) -> dict:
    """
    List the file attachments in a specific Gmail message.

    Returns structured metadata (filename, mime_type, size_bytes, attachment_id)
    without downloading any bytes. Used by the Flutter batch-confirmation card
    to show the user which attachments they can save to the Document Library.
    """
    from app.providers.google.gmail.api import list_email_attachments  # noqa: PLC0415
    import json as _json  # noqa: PLC0415

    result_text = list_email_attachments(email_id)

    # Parse the structured [ATTACHMENT_METADATA] JSON block embedded in the result
    attachments: list[dict] = []
    marker = "[ATTACHMENT_METADATA]:"
    if marker in result_text:
        try:
            json_str = result_text.split(marker, 1)[1].strip()
            attachments = _json.loads(json_str)
            # Inject the parent email_id into each attachment record for the Flutter card
            for att in attachments:
                att["email_id"] = email_id
        except Exception:  # noqa: BLE001
            pass

    return {
        "email_id": email_id,
        "attachments": attachments,
        "summary": result_text.split(marker)[0].strip(),
    }


# ── Document Intelligence Endpoints ───────────────────────────────────────────


_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/csv",
}


@app.post("/agent/documents/upload", tags=["Documents"], status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    display_name: str | None = Form(default=None),
    tags: str = Form(default=""),
) -> dict:
    """
    Upload a document for ingestion into the RAG pipeline.
    Returns 202 Accepted immediately; parsing + embedding run in the background.
    Poll GET /agent/documents/{document_id} to check when status changes to 'ready'.
    """
    from app.capabilities.documents.ingestion import is_supported, detect_file_type  # noqa: PLC0415
    from app.capabilities.documents.models import DocumentRecord  # noqa: PLC0415
    from app.capabilities.documents.ingestion import run_ingestion_pipeline  # noqa: PLC0415
    from app.repositories.document_repository import save_document_record, upload_document_file  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    user_id = settings.DEV_USER_ID
    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"

    # Validate MIME type
    if mime_type not in _ALLOWED_MIME_TYPES:
        from app.capabilities.documents.ingestion import SUPPORTED_EXTENSIONS  # noqa: PLC0415
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=(
                    f"Unsupported file type '{mime_type}'. "
                    f"Supported formats: PDF, DOCX, TXT, MD, CSV."
                ),
            )

    # Validate file size (50 MB hard limit)
    max_bytes = settings.DOCUMENTS_MAX_FILE_SIZE_MB * 1024 * 1024 if hasattr(settings, 'DOCUMENTS_MAX_FILE_SIZE_MB') else 50 * 1024 * 1024
    file_bytes = await file.read()
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {getattr(settings, 'DOCUMENTS_MAX_FILE_SIZE_MB', 50)} MB.",
        )
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Resolve display name
    resolved_display_name = (display_name or Path(filename).stem).strip()
    file_type = detect_file_type(mime_type, filename)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Create document record
    import uuid as _uuid  # noqa: PLC0415
    document_id = str(_uuid.uuid4())

    # Upload raw file to storage
    storage_path = upload_document_file(user_id, document_id, filename, file_bytes, mime_type)

    record = DocumentRecord(
        id=document_id,
        user_id=user_id,
        filename=filename,
        display_name=resolved_display_name,
        file_type=file_type,
        mime_type=mime_type,
        storage_path=storage_path,
        file_size_bytes=len(file_bytes),
        status="processing",
        tags=tag_list,
    )
    save_document_record(record)

    # Queue background ingestion
    background_tasks.add_task(
        run_ingestion_pipeline,
        document_id=document_id,
        user_id=user_id,
        file_bytes=file_bytes,
        mime_type=mime_type,
        filename=filename,
    )

    logger.info("Document upload accepted: id=%s name=%s", document_id, resolved_display_name)
    return {
        "status": "processing",
        "document_id": document_id,
        "display_name": resolved_display_name,
        "file_type": file_type,
        "file_size_bytes": len(file_bytes),
        "message": "Document uploaded successfully. Parsing and embedding are running in the background.",
    }


@app.get("/agent/documents", tags=["Documents"])
async def list_documents() -> list[dict]:
    """List all uploaded documents for the current user."""
    from app.repositories.document_repository import load_document_records  # noqa: PLC0415
    records = load_document_records(settings.DEV_USER_ID)
    return [r.model_dump(exclude={"embedding"}) for r in records]


@app.get("/agent/documents/{document_id}", tags=["Documents"])
async def get_document(document_id: str) -> dict:
    """Get metadata and status of a specific document."""
    from app.repositories.document_repository import load_document_record_by_id  # noqa: PLC0415
    record = load_document_record_by_id(settings.DEV_USER_ID, document_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    return record.model_dump(exclude={"embedding"})


@app.delete("/agent/documents/{document_id}", tags=["Documents"])
async def delete_document(document_id: str) -> dict:
    """Delete a document and all its indexed chunks."""
    from app.repositories.document_repository import (  # noqa: PLC0415
        load_document_record_by_id,
        delete_document_record,
        delete_document_file,
    )
    record = load_document_record_by_id(settings.DEV_USER_ID, document_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    # Delete raw file from storage
    delete_document_file(record.storage_path)
    # Delete DB record + chunks (CASCADE)
    delete_document_record(settings.DEV_USER_ID, document_id)

    logger.info("Deleted document id=%s name=%s", document_id, record.display_name)
    return {"status": "success", "message": f"Document '{record.display_name}' deleted."}


# ── Dev entry point ───────────────────────────────────────────────────────────


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
    )
