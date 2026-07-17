"""
app/agents/executor.py  —  The A.L.T.A.I.R. Executor.

Receives a TaskPlan from the Planner and processes each step:
  • requires_confirmation=False  → execute the tool immediately, collect result.
  • requires_confirmation=True   → yield an approval_required event and stop.
                                   The user will approve via /agent/execute-action.

The Executor never calls Gemini — it only dispatches Python functions.
"""
from __future__ import annotations

import logging
from collections.abc import Generator

from app.agents.planner_schema import TaskPlan, TaskStep
from app.agents.safety import SafetyRating
from app.config import settings
from app.tools.email_tools import read_emails, read_email_details
from app.tools.calendar_tools import get_calendar_events
from app.tools.search_tools import search_web

logger = logging.getLogger(__name__)

# ── Tool dispatch tables ──────────────────────────────────────────────────────

# Read-only tools: called immediately, no confirmation required.
_READ_DISPATCH: dict[str, callable] = {
    "read_emails": read_emails,
    "read_email_details": read_email_details,
    "get_events": get_calendar_events,
    "search_web": search_web,
}

# Parameter key mapping: (tool, action) → how to map step.parameters to the
# Python function kwargs. Handles naming mismatches between schema and function.
_PARAM_ALIASES: dict[str, dict[str, str]] = {
    "read_emails": {
        "max_results": "max_results",
        "sender": "sender",
        "after_date": "after_date",
        "before_date": "before_date",
    },
    "read_email_details": {"email_id": "email_id"},

    "get_events": {"days_ahead": "days_ahead"},
    "search_web": {"query": "query"},
    "save_contact": {
        "name": "name",
        "email": "email",
        "phone": "phone",
        "company": "company",
        "notes": "notes",
    },
    "save_preference": {"category": "category", "key": "key", "value": "value"},
    "save_routine": {"name": "name", "steps": "steps"},
    "save_knowledge": {"text": "text", "importance": "importance"},
    "delete_memory": {"category": "category", "key": "key"},
}

# Write-action → approval data shape mapping.
# Maps action name → (execute-action key, parameter remapping).
_WRITE_APPROVAL_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "draft_email": (
        "send_email",
        {"recipient": "to", "subject": "subject", "body": "body"},
    ),
    "delete_email": (
        "delete_email",
        {"email_id": "email_id", "sender": "sender", "subject": "subject"},
    ),
    "create_event": (
        "create_calendar_event",
        {
            "title": "title",
            "date": "date",
            "time": "time",
            "duration_minutes": "duration_minutes",
            "attendees": "attendees",
        },
    ),
    "reschedule_event": (
        "reschedule_calendar_event",
        {
            "event_id": "event_id",
            "title": "title",
            "new_date": "new_date",
            "new_time": "new_time",
            "new_duration_minutes": "new_duration_minutes",
        },
    ),
    "delete_event": (
        "delete_calendar_event",
        {"event_id": "event_id", "title": "title"},
    ),
    "save_contact": (
        "save_contact",
        {
            "name": "name",
            "email": "email",
            "phone": "phone",
            "company": "company",
            "notes": "notes",
        },
    ),
    "save_preference": (
        "save_preference",
        {"category": "category", "key": "key", "value": "value"},
    ),
    "save_routine": (
        "save_routine",
        {"name": "name", "steps": "steps"},
    ),
    "save_knowledge": (
        "save_knowledge",
        {"text": "text", "importance": "importance"},
    ),
    "delete_memory": (
        "delete_memory",
        {"category": "category", "key": "key"},
    ),
}




# ── Main entry point ──────────────────────────────────────────────────────────

def execute_plan(
    plan: TaskPlan,
    user_text: str,
    history: list[dict] | None = None,
    user_id: str = settings.DEV_USER_ID,
) -> Generator[dict, None, None]:
    """
    Execute a TaskPlan step by step, yielding SSE-compatible event dicts.

    Yields:
        {"type": "log",              "message": str}
        {"type": "tool_result",      "step_id": int, "result": str}
        {"type": "approval_required","action": str, "data": dict}
        {"type": "result",           "text": str}
        {"type": "history_update",   "history": list[dict]}
        {"type": "error",            "message": str}

    Args:
        plan:      The TaskPlan produced by the Planner.
        user_text: Original user command (for history update).
        history:   Prior conversation history (for history update).
        user_id:   The user ID whose credentials to use.
    """
    # ── Ambiguity: planner couldn't form a plan ───────────────────────────────
    if plan.ambiguity_question:
        yield {
            "type": "log",
            "message": "❓ Need more information before planning…",
        }
        yield {"type": "result", "text": plan.ambiguity_question}
        yield from _emit_history_update(
            user_text, plan.ambiguity_question, history
        )
        return

    if not plan.steps:
        yield {"type": "result", "text": "I understood your request but could not form a plan. Could you rephrase?"}
        return

    yield {
        "type": "log",
        "message": f"📋 Plan ready — {len(plan.steps)} step(s): {plan.intent_summary}",
    }

    # Accumulate read-only results for the final summary
    accumulated_results: list[str] = []
    completed_step_ids: set[int] = set()

    for step in _topological_order(plan.steps):
        # ── Check dependencies ────────────────────────────────────────────
        missing = [d for d in step.depends_on if d not in completed_step_ids]
        if missing:
            yield {
                "type": "error",
                "message": f"Step {step.step_id} depends on steps {missing} which did not complete.",
            }
            return

        yield {
            "type": "log",
            "message": f"▶️  Step {step.step_id}: {step.description}",
        }

        # ── Write action: requires user approval ──────────────────────────
        if step.requires_confirmation:
            from app.agents.safety import classify
            safety_rating = classify(step, {"user_id": user_id})

            if safety_rating.level == "dangerous" or safety_rating.scope_warning:
                yield {
                    "type": "safety_warning",
                    "message": safety_rating.scope_warning,
                    "requires_double_confirm": safety_rating.requires_double_confirm,
                    "level": safety_rating.level,
                }

            yield from _emit_approval(step, safety_rating)
            return  # Pause — Flutter resumes via /agent/execute-action

        # ── Read-only action: execute immediately ─────────────────────────
        result_text = _dispatch_read_action(step)
        if result_text.startswith("Failed") or result_text.startswith("Error"):
            yield {"type": "log", "message": f"⚠️  {result_text}"}
        else:
            yield {
                "type": "tool_result",
                "step_id": step.step_id,
                "result": result_text,
            }

        accumulated_results.append(f"[{step.description}]\n{result_text}")
        completed_step_ids.add(step.step_id)

    # ── All read-only steps completed — emit summary ──────────────────────
    final_text = "\n\n".join(accumulated_results) if accumulated_results else "Done."
    yield {"type": "result", "text": final_text}
    yield from _emit_history_update(user_text, final_text, history)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _topological_order(steps: list[TaskStep]) -> list[TaskStep]:
    """Return steps in topological order respecting depends_on edges.
    Falls back to sequential order if no dependencies exist (common case).
    """
    if not any(s.depends_on for s in steps):
        return steps  # fast path: linear plan

    step_map = {s.step_id: s for s in steps}
    visited: set[int] = set()
    order: list[TaskStep] = []

    def visit(sid: int) -> None:
        if sid in visited:
            return
        visited.add(sid)
        for dep in step_map[sid].depends_on:
            if dep in step_map:
                visit(dep)
        order.append(step_map[sid])

    for step in steps:
        visit(step.step_id)

    return order


def _dispatch_read_action(step: TaskStep) -> str:
    """Execute a read-only action and return the result string."""
    fn = _READ_DISPATCH.get(step.action)
    if fn is None:
        return f"Error: unknown read action '{step.action}'"

    aliases = _PARAM_ALIASES.get(step.action, {})
    kwargs = {aliases.get(k, k): v for k, v in step.parameters.items() if v is not None}

    try:
        result = fn(**kwargs)
        return str(result)
    except TypeError as exc:
        logger.warning("Tool call %s failed with bad args: %s", step.action, exc)
        return fn()  # retry with defaults
    except Exception as exc:  # noqa: BLE001
        logger.exception("Tool %s raised an exception", step.action)
        return f"Failed to execute {step.action}: {exc}"


def _emit_approval(
    step: TaskStep,
    safety_rating: SafetyRating | None = None,
) -> Generator[dict, None, None]:
    """Yield an approval_required event for a write action."""
    mapping = _WRITE_APPROVAL_MAP.get(step.action)
    if mapping is None:
        yield {
            "type": "error",
            "message": f"Unknown write action '{step.action}' — cannot stage for approval.",
        }
        return

    execute_action_key, param_remap = mapping
    data = {target: step.parameters.get(source, "") for source, target in param_remap.items()}

    if safety_rating:
        data["safety_warning"] = safety_rating.scope_warning
        data["requires_double_confirm"] = safety_rating.requires_double_confirm
        data["safety_level"] = safety_rating.level

    yield {
        "type": "log",
        "message": f"🚦 Staging '{step.action}' for your approval…",
    }
    yield {
        "type": "approval_required",
        "action": execute_action_key,
        "data": data,
    }


def _emit_history_update(
    user_text: str,
    model_response: str,
    history: list[dict] | None,
) -> Generator[dict, None, None]:
    """Append this turn to the conversation history and emit history_update."""
    updated = list(history or [])
    if user_text:
        updated.append({"role": "user", "text": user_text})
    if model_response:
        updated.append({"role": "model", "text": model_response})
    updated = updated[-20:]  # cap at 20 entries (10 pairs)
    yield {"type": "history_update", "history": updated}
