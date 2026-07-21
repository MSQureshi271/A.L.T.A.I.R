"""
app/agents/watcher_engine.py — Execution Engine for Watchers.

Evaluates matched events against watcher trigger conditions, executes
action sequences, and logs latency metrics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any
import uuid

from google import genai
from google.genai import types

from app.watchers.dsl import evaluate_condition
from app.watchers.models import Event
from app.config.settings import settings
from app.repositories.db_client import db_store_item
from app.repositories.watcher_repository import log_watcher_history
from app.services.notification import send_watcher_notification

logger = logging.getLogger(__name__)


def execute_watcher_on_event(
    watcher: dict[str, Any],
    event: Event,
) -> dict[str, Any]:
    """Evaluate trigger condition and run actions for a single watcher and event."""
    watcher_id = watcher["id"]
    user_id = watcher["user_id"]
    description = watcher["description"]

    # 1. Initialize run logging metrics
    history_entry = {
        "id": str(uuid.uuid4()),
        "watcher_id": watcher_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "matched_events": 1,
        "actions_executed": 0,
        "retry_count": 0,
        "dsl_latency_ms": 0,
        "connector_latency_ms": 0,
        "duration_ms": 0,
    }

    t_start = time.time()

    try:
        # 2. Evaluate Condition DSL rules
        t_dsl_start = time.time()
        trigger = watcher.get("trigger", {})
        condition_json = trigger.get("condition_json", {})

        matched = evaluate_condition(condition_json, event)
        history_entry["dsl_latency_ms"] = int((time.time() - t_dsl_start) * 1000)

        if not matched:
            # Condition didn't match, record skipped state and exit
            history_entry["status"] = "completed"
            history_entry["result"] = "Skipped: Condition did not match event attributes."
            history_entry["matched_events"] = 0
            history_entry["completed_at"] = datetime.now(timezone.utc).isoformat()
            history_entry["duration_ms"] = int((time.time() - t_start) * 1000)
            log_watcher_history(user_id, history_entry)
            return history_entry

        # 3. Execute Action pipeline sequentially
        actions = watcher.get("actions", [])
        execution_context = {
            "event_id": event.id,
            "provider": event.provider,
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "attributes": event.attributes,
            "watcher_description": description,
        }

        results = []
        for action in actions:
            action_type = action.get("action_type")
            params = action.get("parameters_json", {})

            res = _execute_action(user_id, watcher_id, action_type, params, execution_context)
            results.append(res)
            history_entry["actions_executed"] += 1

        history_entry["status"] = "completed"
        history_entry["result"] = f"Fired: {', '.join(results)}"

    except Exception as exc:  # noqa: BLE001
        logger.exception("Error executing watcher=%s on event=%s", watcher_id, event.id)
        history_entry["status"] = "failed"
        history_entry["error"] = str(exc)

    history_entry["completed_at"] = datetime.now(timezone.utc).isoformat()
    history_entry["duration_ms"] = int((time.time() - t_start) * 1000)
    log_watcher_history(user_id, history_entry)
    return history_entry


def _execute_action(
    user_id: str,
    watcher_id: str,
    action_type: str,
    params: dict[str, Any],
    context: dict[str, Any],
) -> str:
    """Dispatches execution for a singular action block type."""
    if action_type == "notify":
        title = f"Watcher Alert: {context.get('watcher_description', 'Rule matched')}"

        attrs = context.get("attributes", {})
        if "sender" in attrs:
            body = f"New email from {attrs['sender']}: {attrs.get('subject', '')}"
        elif "title" in attrs:
            body = (
                f"Calendar event: {attrs['title']} "
                f"({attrs.get('attendee_count', 0)} attendees)"
            )
        else:
            body = f"Event matched: {context.get('event_type')}"

        send_watcher_notification(user_id, title, body, watcher_id)
        return "Notification sent"

    if action_type == "summarize":
        if not settings.GEMINI_API_KEY:
            return "Skipped summary (no api key)"

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        attrs = context.get("attributes", {})

        prompt = (
            "Summarize the following event attributes in a single concise sentence "
            "suitable for a push notification body:\n"
            f"{attrs}"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )
        summary = response.text.strip() if response.text else "Event matched."
        send_watcher_notification(user_id, "Watcher Summary Alert", summary, watcher_id)
        return f"Summary sent: {summary}"

    if action_type == "save_memory":
        fact = {
            "user_id": user_id,
            "key": f"watcher_fact_{int(time.time())}",
            "value": {"event": context},
            "memory_type": "watcher_fact",
        }
        db_store_item("user_memory", fact, ["user_id", "key"])
        return "Fact stored in memory"

    raise ValueError(f"Unsupported action type: {action_type}")
