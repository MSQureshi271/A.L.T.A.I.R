"""
app/scratch/test_safety.py — Safety classifier unit checks.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agents.planner_schema import TaskStep
from app.agents.safety import classify


def test_classify_safe():
    step = TaskStep(
        step_id=1,
        tool="gmail",
        action="read_emails",
        parameters={"max_results": 5},
        requires_confirmation=False,
        description="Read emails",
    )
    rating = classify(step, {"user_id": "test_user"})
    assert rating.level == "safe"
    print("test_classify_safe passed!")


def test_classify_caution():
    step = TaskStep(
        step_id=2,
        tool="gmail",
        action="draft_email",
        parameters={"recipient": "bob@cpa.com", "subject": "Draft", "body": "Hello"},
        requires_confirmation=True,
        description="Draft email",
    )
    rating = classify(step, {"user_id": "test_user"})
    assert rating.level == "caution"
    print("test_classify_caution passed!")


@patch("app.agents.safety.build")
@patch("app.agents.safety.get_google_credentials")
def test_classify_dangerous_bulk_email(mock_get_creds, mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": f"msg_{i}"} for i in range(12)]
    }

    step = TaskStep(
        step_id=3,
        tool="gmail",
        action="delete_email",
        parameters={"sender": "amazon.com"},
        requires_confirmation=True,
        description="Delete bulk emails",
    )
    rating = classify(step, {"user_id": "test_user"})
    assert rating.level == "dangerous"
    assert rating.requires_double_confirm is True
    assert "12 emails" in rating.scope_warning
    print("test_classify_dangerous_bulk_email passed!")


@patch("app.agents.safety.build")
@patch("app.agents.safety.get_google_credentials")
def test_classify_dangerous_calendar_delete(mock_get_creds, mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.events().get().execute.return_value = {
        "summary": "Big Meeting",
        "attendees": [{"email": "alice@company.com"}, {"email": "bob@company.com"}],
        "recurrence": ["RRULE:FREQ=DAILY;COUNT=5"],
    }

    step = TaskStep(
        step_id=4,
        tool="calendar",
        action="delete_event",
        parameters={"event_id": "event123"},
        requires_confirmation=True,
        description="Delete event",
    )
    rating = classify(step, {"user_id": "test_user"})
    assert rating.level == "dangerous"
    assert rating.requires_double_confirm is True
    assert "attendee" in rating.scope_warning
    assert "recurring" in rating.scope_warning
    print("test_classify_dangerous_calendar_delete passed!")


if __name__ == "__main__":
    test_classify_safe()
    test_classify_caution()
    test_classify_dangerous_bulk_email()
    test_classify_dangerous_calendar_delete()
    print("\nAll safety classifier unit tests passed!")
