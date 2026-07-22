"""
app/scratch/test_document_integrations.py — End-to-end integration tests for Phase 4.

Tests:
  1. test_planner_document_email_dag()       — Planner generates multi-step plan (document search + draft email)
  2. test_executor_parameter_interpolation() — Executor interpolates $step_1 document text into downstream step
  3. test_watcher_attach_document_summary()  — Watcher engine executes attach_document_summary action
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# UTF-8 stdout on Windows
if sys.stdout.encoding != "utf-8":
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parents[2]))

from dotenv import load_dotenv
load_dotenv()

from app.ai.planner.planner_schema import TaskPlan, TaskStep
from app.ai.executor.executor import _interpolate_value, execute_plan
from app.watchers.engine import _execute_action
from app.capabilities.documents.models import DocumentRecord, DocumentChunk, RetrievedChunk


# ── Test 1: Planner DAG with Document Retrieval ──────────────────────────────


def test_planner_document_email_dag():
    """Verify that Planner can parse document + email request into a valid 2-step plan."""
    from app.ai.planner.planner import plan as planner_plan

    mock_gemini_response = {
        "intent_summary": "Search Q2 report and draft an email summarizing the financial results.",
        "steps": [
            {
                "step_id": 1,
                "tool": "documents",
                "action": "search_my_documents",
                "parameters": {"query": "Q2 financial results revenue growth"},
                "requires_confirmation": False,
                "depends_on": [],
                "description": "Search Q2 financial report"
            },
            {
                "step_id": 2,
                "tool": "gmail",
                "action": "draft_email",
                "parameters": {
                    "recipient": "finance@acme.com",
                    "subject": "Q2 Financial Summary",
                    "body": "Here is the summary from the document: $step_1"
                },
                "requires_confirmation": True,
                "depends_on": [1],
                "description": "Draft summary email"
            }
        ]
    }

    import json
    mock_response_obj = MagicMock()
    mock_response_obj.text = json.dumps(mock_gemini_response)

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response_obj
        mock_client_cls.return_value = mock_client

        plan = planner_plan("Draft an email to finance@acme.com with summary of Q2 report")

    assert len(plan.steps) == 2
    assert plan.steps[0].tool == "documents"
    assert plan.steps[0].action == "search_my_documents"
    assert plan.steps[0].requires_confirmation is False
    assert plan.steps[1].tool == "gmail"
    assert plan.steps[1].action == "draft_email"
    assert plan.steps[1].requires_confirmation is True
    assert "$step_1" in plan.steps[1].parameters["body"]

    print("✅ test_planner_document_email_dag passed!")


# ── Test 2: Executor Parameter Interpolation with Document Output ─────────────


def test_executor_parameter_interpolation():
    """Verify $step_1 and {{step_1_result}} handlebar interpolation with document output."""
    step_outputs = {
        1: "[Document: Q2 Report]\n• Revenue grew 22% YoY.\n• Operating margin expanded by 350 bps."
    }

    # Test $step_1 syntax
    val1 = "Here are the findings: $step_1"
    interp1 = _interpolate_value(val1, step_outputs)
    assert "Revenue grew 22%" in interp1

    # Test {{step_1_result}} handlebars syntax
    val2 = "Summary:\n{{step_1_result}}"
    interp2 = _interpolate_value(val2, step_outputs)
    assert "Revenue grew 22%" in interp2

    print("✅ test_executor_parameter_interpolation passed!")


# ── Test 3: Watcher Action with Document Summary ─────────────────────────────


def test_watcher_attach_document_summary():
    """Verify attach_document_summary watcher action fetches document summary and notifies."""
    user_id = "test-user-001"
    watcher_id = "watcher-doc-123"

    params = {"document_name": "Q2 Report"}
    context = {
        "event_type": "mail_received",
        "watcher_description": "Emails from Usman",
        "attributes": {"sender": "usman@acme.com", "subject": "Q2 Update Request"}
    }

    mock_summary = "Document: Q2 Report (PDF, 1.2 MB)\n• Revenue: $4.2M\n• Growth: +22%"

    with (
        patch("app.capabilities.documents.document_tools.get_document_summary", return_value=mock_summary),
        patch("app.watchers.engine.send_watcher_notification") as mock_notify,
    ):
        result = _execute_action(user_id, watcher_id, "attach_document_summary", params, context)

    assert result == "Document summary notification sent"
    assert mock_notify.called
    assert mock_notify.call_args[0][0] == user_id
    assert "Document Context:" in mock_notify.call_args[0][2]
    assert "Q2 Report" in mock_notify.call_args[0][2]

    print("✅ test_watcher_attach_document_summary passed!")


# ── Runner ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("\n=== Document Intelligence — Phase 4 Cross-Feature Integration Test Suite ===\n")

    test_planner_document_email_dag()
    test_executor_parameter_interpolation()
    test_watcher_attach_document_summary()

    print("\n🎉 All Document Intelligence Phase 4 tests passed!")
