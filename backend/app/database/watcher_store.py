"""
app/database/watcher_store.py — Database store layer for Watchers.

Wraps the generic db_client CRUD operations for watchers, triggers,
actions, event deduplication, and execution logs.
"""
from __future__ import annotations

import logging
from typing import Any

from app.database.db_client import (
    db_delete_item,
    db_load_items,
    db_store_item,
)

logger = logging.getLogger(__name__)


def save_watcher(
    user_id: str,
    watcher_id: str,
    description: str,
    enabled: bool = True,
) -> None:
    """Insert or update the core watcher record."""
    item = {
        "id": watcher_id,
        "user_id": user_id,
        "description": description,
        "enabled": enabled,
    }
    db_store_item("watchers", item, ["id"])


def save_watcher_trigger(
    user_id: str,
    watcher_id: str,
    provider: str,
    event_type: str,
    condition_json: dict[str, Any],
) -> None:
    """Insert or update the watcher trigger condition."""
    item = {
        "watcher_id": watcher_id,
        "user_id": user_id,
        "provider": provider,
        "event_type": event_type,
        "condition_json": condition_json,
    }
    db_store_item("watcher_triggers", item, ["watcher_id"])


def save_watcher_action(
    user_id: str,
    watcher_id: str,
    action_type: str,
    parameters_json: dict[str, Any],
    execution_order: int,
) -> None:
    """Insert a watcher action record."""
    item = {
        "watcher_id": watcher_id,
        "user_id": user_id,
        "action_type": action_type,
        "parameters_json": parameters_json,
        "execution_order": execution_order,
    }
    db_store_item("watcher_actions", item, ["watcher_id", "action_type"])


def delete_watcher(user_id: str, watcher_id: str) -> None:
    """Delete a watcher and all its cascade dependencies."""
    db_delete_item("watchers", user_id, {"id": watcher_id})
    db_delete_item("watcher_triggers", user_id, {"watcher_id": watcher_id})
    db_delete_item("watcher_actions", user_id, {"watcher_id": watcher_id})
    db_delete_item("watcher_history", user_id, {"watcher_id": watcher_id})


def load_watchers(user_id: str) -> list[dict[str, Any]]:
    """Retrieve all watchers for a user, populated with trigger and actions."""
    watchers_list = db_load_items("watchers", user_id)
    triggers_list = db_load_items("watcher_triggers", user_id)
    actions_list = db_load_items("watcher_actions", user_id)

    # Index triggers and actions by watcher_id for fast lookup
    trigger_map = {t["watcher_id"]: t for t in triggers_list}
    actions_map: dict[str, list[dict[str, Any]]] = {}
    for action in actions_list:
        actions_map.setdefault(action["watcher_id"], []).append(action)

    hydrated = []
    for w in watchers_list:
        watcher_id = w["id"]
        trigger = trigger_map.get(watcher_id, {})
        actions = actions_map.get(watcher_id, [])
        actions.sort(key=lambda a: a.get("execution_order", 0))

        hydrated.append(
            {
                "id": watcher_id,
                "user_id": w["user_id"],
                "description": w["description"],
                "enabled": w["enabled"],
                "trigger": {
                    "provider": trigger.get("provider", ""),
                    "event_type": trigger.get("event_type", ""),
                    "condition_json": trigger.get("condition_json", {}),
                },
                "actions": [
                    {
                        "action_type": a["action_type"],
                        "parameters_json": a.get("parameters_json", {}),
                        "execution_order": a["execution_order"],
                    }
                    for a in actions
                ],
            }
        )

    return hydrated


# ── Event Deduplication Operations ───────────────────────────────────────────

def is_event_processed(user_id: str, event_hash_id: str) -> bool:
    """Return True if the event was already processed for this user."""
    items = db_load_items("processed_events", user_id)
    return any(item["id"] == event_hash_id for item in items)


def mark_event_processed(
    user_id: str,
    event_hash_id: str,
    provider: str,
    external_event_id: str,
) -> None:
    """Record that an event has been processed."""
    item = {
        "id": event_hash_id,
        "user_id": user_id,
        "provider": provider,
        "external_event_id": external_event_id,
    }
    db_store_item("processed_events", item, ["id"])


# ── Execution History Operations ──────────────────────────────────────────────

def log_watcher_history(user_id: str, history_entry: dict[str, Any]) -> None:
    """Log an execution run entry to watcher_history."""
    history_entry["user_id"] = user_id
    db_store_item("watcher_history", history_entry, ["id"])


def load_watcher_history(user_id: str, watcher_id: str) -> list[dict[str, Any]]:
    """Load execution run history logs for a specific watcher."""
    items = db_load_items("watcher_history", user_id)
    watcher_logs = [item for item in items if item["watcher_id"] == watcher_id]
    # Sort logs by started_at descending (newest first)
    watcher_logs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return watcher_logs
