"""
app/scratch/test_watchers_engine.py — Integration and validation suite for Watchers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.agents.watcher_builder import compile_trigger_dsl
from app.agents.watcher_dsl import evaluate_condition
from app.agents.watcher_engine import execute_watcher_on_event
from app.agents.watcher_event import Event
from app.database.watcher_store import (
    is_event_processed,
    load_watcher_history,
    mark_event_processed,
)


def test_builder_offline():
    with patch("app.agents.watcher_builder.genai.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = (
            '{"conjunction": "AND", "rules": [{"field": "sender", '
            '"operator": "contains", "value": "Amazon"}]}'
        )
        mock_client.return_value.models.generate_content.return_value = mock_response

        dsl = compile_trigger_dsl("gmail", "emails from Amazon")
        assert dsl["conjunction"] == "AND"
        assert dsl["rules"][0]["field"] == "sender"
        assert dsl["rules"][0]["value"] == "Amazon"
        print("test_builder_offline passed!")


def test_dsl_evaluation():
    event = Event(
        id="evt_123",
        provider="gmail",
        event_type="email_received",
        timestamp=datetime.now(timezone.utc),
        attributes={"sender": "amazon.com", "subject": "pricing update"},
        raw_payload={},
    )

    cond_ok = {
        "conjunction": "AND",
        "rules": [
            {"field": "sender", "operator": "contains", "value": "amazon"},
            {"field": "subject", "operator": "contains", "value": "pricing"},
        ],
    }
    cond_fail = {
        "conjunction": "AND",
        "rules": [
            {"field": "sender", "operator": "contains", "value": "google"},
        ],
    }

    assert evaluate_condition(cond_ok, event) is True
    assert evaluate_condition(cond_fail, event) is False
    print("test_dsl_evaluation passed!")


def test_engine_run():
    user_id = "test_user"
    watcher_id = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

    # Persist mock watcher config to DB/cache to satisfy foreign key constraints
    from app.database.watcher_store import save_watcher, delete_watcher
    save_watcher(user_id, watcher_id, "Watch inbox", enabled=True)

    watcher = {
        "id": watcher_id,
        "user_id": user_id,
        "description": "Watch inbox",
        "enabled": True,
        "trigger": {
            "provider": "gmail",
            "condition_json": {
                "rules": [{"field": "sender", "operator": "contains", "value": "amazon"}]
            },
        },
        "actions": [
            {"action_type": "notify", "parameters_json": {}, "execution_order": 0},
        ],
    }

    event = Event(
        id="evt_789",
        provider="gmail",
        event_type="email_received",
        timestamp=datetime.now(timezone.utc),
        attributes={"sender": "amazon.com", "subject": "your invoice"},
        raw_payload={},
    )

    try:
        history_entry = execute_watcher_on_event(watcher, event)
        assert history_entry["status"] == "completed"
        assert history_entry["matched_events"] == 1
        assert history_entry["actions_executed"] == 1

        logs = load_watcher_history(user_id, watcher_id)
        assert len(logs) > 0
        assert logs[0]["status"] == "completed"
    finally:
        delete_watcher(user_id, watcher_id)

    print("test_engine_run passed!")


def test_deduplication():
    import time
    user_id = "test_user"
    event_id = f"evt_hash_{int(time.time())}"

    assert is_event_processed(user_id, event_id) is False
    mark_event_processed(user_id, event_id, "gmail", f"ext_{int(time.time())}")
    assert is_event_processed(user_id, event_id) is True
    print("test_deduplication passed!")


if __name__ == "__main__":
    test_builder_offline()
    test_dsl_evaluation()
    test_engine_run()
    test_deduplication()
    print("\nAll watcher engine validation checks completed successfully!")
