"""
app/agents/coordinator.py  —  The Gemini Orchestrator / Router Agent.

This is the core of the multi-agent system.  It:
  1. Receives the user command as plain text OR raw audio bytes.
  2. Passes it to Gemini 2.5 Flash together with all registered tools.
  3. Runs a synchronous tool-calling loop until Gemini produces a final
     text answer OR one of the staging tools returns an approval_required
     payload that must be shown to the user.
  4. Streams log events back to the caller via a generator so the Flutter
     UI can display live progress.

Audio is passed directly to Gemini as a multimodal Part — no separate
Speech-to-Text service required.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any

from google import genai
from google.genai import types

from app.config import settings
from app.tools.search_tools import search_web
from app.tools.email_tools import stage_email, read_emails
from app.tools.calendar_tools import get_calendar_events, create_calendar_event

logger = logging.getLogger(__name__)

# ── All Python functions that Gemini is allowed to call ──────────────────────
TOOLS: list[Any] = [
    search_web,
    stage_email,
    read_emails,
    get_calendar_events,
    create_calendar_event,
]

# ── Local dispatch table  (function_name -> callable) ────────────────────────
_TOOL_MAP: dict[str, Any] = {fn.__name__: fn for fn in TOOLS}

SYSTEM_INSTRUCTION = """
You are Executive Agent, an elite AI productivity assistant for a busy
business owner.  Your job is to understand voice commands and execute them
using the tools available to you.

Core rules:
- NEVER send emails or create calendar events without calling the staging
  tool first (stage_email / create_calendar_event).  The user MUST approve
  before any action takes effect.
- When a staging tool is called, stop generating further tool calls and
  return immediately so the user can review the draft.
- Be concise and professional in your final text responses.
- If a request requires information you do not have, ask the user one
  clear, specific follow-up question.
""".strip()


def _build_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set.  Add it to your backend/.env file."
        )
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def run_agent(
    user_text: str,
) -> Generator[dict, None, None]:
    """Run the agentic loop from a plain-text command.

    Yields dicts with the following shapes:

        {"type": "log",    "message": str}
        {"type": "result", "text": str}
        {"type": "approval_required", "action": str, "data": dict}
        {"type": "error",  "message": str}
    """
    try:
        client = _build_client()
    except RuntimeError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    yield {"type": "log", "message": "🧠 Coordinator → parsing your command…"}

    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part(text=user_text)],
        )
    ]

    yield from _run_loop(client, contents)


def run_agent_audio(
    audio_bytes: bytes,
    mime_type: str,
) -> Generator[dict, None, None]:
    """Run the agentic loop from raw audio bytes (Gemini native multimodal).

    Gemini listens to the audio, understands the intent, and triggers the
    same tool-calling loop as the text path — no STT service needed.

    Args:
        audio_bytes: Raw bytes of the recorded audio file.
        mime_type:   MIME type of the audio (e.g. 'audio/m4a', 'audio/wav').
    """
    try:
        client = _build_client()
    except RuntimeError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    yield {"type": "log", "message": "🎙️  Audio received — sending to Gemini for transcription…"}

    contents: list[types.Content] = [
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
                        "Listen to the voice command in the audio above and execute "
                        "the appropriate tools to fulfil the request."
                    )
                ),
            ],
        )
    ]

    yield from _run_loop(client, contents)


def _run_loop(
    client: genai.Client,
    contents: list[types.Content],
) -> Generator[dict, None, None]:
    """Shared Gemini tool-calling loop used by both text and audio entry points."""
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=TOOLS,
        temperature=0.0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True
        ),
    )

    max_iterations = 6  # Safety guard against infinite loops
    for iteration in range(max_iterations):
        yield {
            "type": "log",
            "message": f"🔄 Iteration {iteration + 1}: calling Gemini…",
        }

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        finish_reason = candidate.finish_reason

        # Collect all parts from this response turn
        response_parts: list[types.Part] = list(candidate.content.parts)

        # Check whether Gemini returned function calls
        function_calls = [
            p.function_call
            for p in response_parts
            if p.function_call is not None
        ]

        if not function_calls:
            # Gemini produced a plain text answer — we're done
            final_text = "".join(
                p.text for p in response_parts if p.text
            ).strip()
            yield {"type": "log", "message": "✅ Final answer ready."}
            yield {"type": "result", "text": final_text}
            return

        # ── Execute each function call ────────────────────────────────────
        # Append the model turn to history first
        contents.append(
            types.Content(role="model", parts=response_parts)
        )

        function_response_parts: list[types.Part] = []

        for fc in function_calls:
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            yield {
                "type": "log",
                "message": f"🛠️  Executing tool: {tool_name}({_args_preview(tool_args)})",
            }

            if tool_name not in _TOOL_MAP:
                tool_result = {"error": f"Unknown tool: {tool_name}"}
            else:
                try:
                    raw = _TOOL_MAP[tool_name](**tool_args)
                except Exception as exc:  # noqa: BLE001
                    raw = {"error": str(exc)}

                # ── Human-in-the-loop intercept ───────────────────────────
                if isinstance(raw, dict) and raw.get("type") == "approval_required":
                    yield {
                        "type": "approval_required",
                        "action": raw["action"],
                        "data": raw["data"],
                    }
                    return  # Stop loop — user must approve first

                tool_result = raw

            function_response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_name,
                        response={"result": tool_result},
                    )
                )
            )

        # Append tool results to history and loop
        contents.append(
            types.Content(role="user", parts=function_response_parts)
        )

    # Fell out of the loop — return whatever the last response text was
    last_text = (
        "".join(p.text for p in response_parts if p.text).strip()  # type: ignore[possibly-undefined]
        or "Agent reached maximum iterations without a final answer."
    )
    yield {"type": "result", "text": last_text}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _args_preview(args: dict) -> str:
    """Return a short human-readable preview of tool arguments."""
    preview = json.dumps(args, ensure_ascii=False)
    return preview[:120] + "…" if len(preview) > 120 else preview
