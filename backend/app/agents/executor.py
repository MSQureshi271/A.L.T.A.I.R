"""
app/agents/executor.py  —  The A.L.T.A.I.R. Executor.

Receives a TaskPlan from the Planner and processes each step:
  • requires_confirmation=False  → execute the tool immediately, collect result.
  • requires_confirmation=True   → yield an approval_required event and stop.
                                   The user will approve via /agent/execute-action.

The Executor never calls Gemini — it only dispatches Python functions.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncGenerator

from app.agents.planner_schema import TaskPlan, TaskStep
from app.agents.safety import SafetyRating
from app.config import settings
from app.database.db_client import db_store_item, db_load_items
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
    "create_watcher": {
        "provider": "provider",
        "description": "description",
        "actions": "actions",
    },
    "delete_watcher": {
        "watcher_id": "watcher_id",
        "description": "description",
    },
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
    "create_watcher": (
        "create_watcher",
        {
            "provider": "provider",
            "description": "description",
            "actions": "actions",
        },
    ),
    "delete_watcher": (
        "delete_watcher",
        {
            "watcher_id": "watcher_id",
            "description": "description",
        },
    ),
}


# ── Plan Persistence Helpers ──────────────────────────────────────────────────

def save_active_plan(
    plan: TaskPlan,
    user_text: str | None = None,
    history: list[dict] | None = None,
) -> None:
    """Persist the current TaskPlan state, along with user_text and history."""
    if not plan.plan_id:
        import uuid
        plan.plan_id = str(uuid.uuid4())

    # Map current execution state to overall plan status
    completed = all(s.status == "completed" for s in plan.steps)
    failed = any(s.status == "failed" for s in plan.steps)
    awaiting = any(s.status == "running" and s.requires_confirmation for s in plan.steps)

    status = "running"
    if failed:
        status = "failed"
    elif completed:
        status = "completed"
    elif awaiting:
        status = "awaiting_approval"

    # Merge with existing record to preserve user_text and history if not provided
    existing_user_text = ""
    existing_history = []
    existing = load_active_plan_record(plan.plan_id)
    if existing:
        existing_user_text = existing.get("user_text", "")
        existing_history = existing.get("history", [])

    item = {
        "plan_id": plan.plan_id,
        "user_id": settings.DEV_USER_ID,
        "status": status,
        "plan_json": plan.model_dump(),
        "user_text": user_text if user_text is not None else existing_user_text,
        "history": history if history is not None else existing_history,
    }
    db_store_item("active_plans", item, conflict_fields=["plan_id"])


def load_active_plan(plan_id: str) -> TaskPlan | None:
    """Load a persisted plan by plan_id."""
    record = load_active_plan_record(plan_id)
    if record:
        plan_json = record.get("plan_json")
        if plan_json:
            return TaskPlan.model_validate(plan_json)
    return None


def load_active_plan_record(plan_id: str) -> dict | None:
    """Load a raw plan record dict by plan_id, unwrapping plan_json context."""
    records = db_load_items("active_plans", settings.DEV_USER_ID)
    for r in records:
        if r.get("plan_id") == plan_id:
            raw_json = r.get("plan_json", {})
            if isinstance(raw_json, dict) and "plan" in raw_json:
                return {
                    "plan_id": plan_id,
                    "plan_json": raw_json.get("plan"),
                    "user_text": raw_json.get("user_text", ""),
                    "history": raw_json.get("history", []),
                }
            return {
                "plan_id": plan_id,
                "plan_json": raw_json,
                "user_text": r.get("user_text") or "",
                "history": r.get("history") or [],
            }
    return None





# ── Parameter Interpolation ───────────────────────────────────────────────────

def _interpolate_value(val: Any, step_outputs: dict[int, Any]) -> Any:
    """Recursively interpolate references to previous step outputs (e.g. $step_1.email_id)."""
    if isinstance(val, str):
        # 1. Exact match case: replace the whole value with the output object (preserves non-string types)
        exact_match = re.match(r"^\$step_(\d+)(?:\.(.+))?$", val)
        if exact_match:
            step_id = int(exact_match.group(1))
            key_path = exact_match.group(2)

            if step_id not in step_outputs:
                return val

            output_val = step_outputs[step_id]
            if key_path:
                if isinstance(output_val, dict):
                    keys = key_path.split(".")
                    curr = output_val
                    for k in keys:
                        if isinstance(curr, dict) and k in curr:
                            curr = curr[k]
                        else:
                            return None
                    return curr
                elif hasattr(output_val, key_path):
                    return getattr(output_val, key_path)
                return None
            return output_val

        # 2. Substring substitution case: find all $step_X or $step_X.key and replace with stringified results
        pattern = r"\$step_(\d+)(?:\.([a-zA-Z_0-9\.]+))?"

        def replace_match(m: re.Match) -> str:
            step_id = int(m.group(1))
            key_path = m.group(2)
            if step_id not in step_outputs:
                return m.group(0)

            output_val = step_outputs[step_id]
            if key_path:
                if isinstance(output_val, dict):
                    keys = key_path.split(".")
                    curr = output_val
                    for k in keys:
                        if isinstance(curr, dict) and k in curr:
                            curr = curr[k]
                        else:
                            return ""
                    return str(curr)
                return ""
            return str(output_val)

        return re.sub(pattern, replace_match, val)

    elif isinstance(val, dict):
        return {k: _interpolate_value(v, step_outputs) for k, v in val.items()}
    elif isinstance(val, list):
        return [_interpolate_value(item, step_outputs) for item in val]
    return val



# ── Main entry point ──────────────────────────────────────────────────────────

async def execute_plan(
    plan: TaskPlan,
    user_text: str,
    history: list[dict] | None = None,
    user_id: str = settings.DEV_USER_ID,
) -> AsyncGenerator[dict, None]:
    """
    Execute a TaskPlan as a DAG, yielding SSE-compatible event dicts.
    """
    # ── Ambiguity: planner couldn't form a plan ───────────────────────────────
    if plan.ambiguity_question:
        yield {
            "type": "log",
            "message": "❓ Need more information before planning…",
        }
        yield {"type": "result", "text": plan.ambiguity_question}
        for event in _emit_history_update(user_text, plan.ambiguity_question, history):
            yield event
        return

    if not plan.steps:
        yield {"type": "result", "text": "I understood your request but could not form a plan. Could you rephrase?"}
        return

    if not plan.plan_id:
        import uuid
        plan.plan_id = str(uuid.uuid4())

    save_active_plan(plan, user_text=user_text, history=history)

    yield {
        "type": "log",
        "message": f"📋 Plan ready (ID: {plan.plan_id}) — {len(plan.steps)} step(s): {plan.intent_summary}",
    }

    accumulated_results: list[str] = []
    step_outputs: dict[int, Any] = {}

    # Initialize results from already completed steps (for resumed executions)
    for s in plan.steps:
        if s.status == "completed":
            step_outputs[s.step_id] = s.output
            accumulated_results.append(f"[{s.description}]\n{s.output}")

    while True:
        # 1. Identify ready steps (pending and dependencies met)
        ready_read_steps: list[TaskStep] = []
        ready_write_steps: list[TaskStep] = []

        for step in plan.steps:
            if step.status == "pending":
                deps_ok = True
                for dep_id in step.depends_on:
                    dep_step = next((s for s in plan.steps if s.step_id == dep_id), None)
                    if not dep_step or dep_step.status != "completed":
                        deps_ok = False
                        break
                if deps_ok:
                    if step.requires_confirmation:
                        ready_write_steps.append(step)
                    else:
                        ready_read_steps.append(step)

        # 2. Execute read-only steps in parallel
        if ready_read_steps:
            yield {
                "type": "log",
                "message": f"⚡ Running {len(ready_read_steps)} read action(s) concurrently...",
            }

            for s in ready_read_steps:
                s.status = "running"
            save_active_plan(plan)

            async def run_one(s: TaskStep):
                s.parameters = _interpolate_value(s.parameters, step_outputs)
                res = await _dispatch_read_action_async(s)
                return s.step_id, res

            tasks = [run_one(s) for s in ready_read_steps]
            results = await asyncio.gather(*tasks)

            for step_id, res in results:
                s = next(x for x in plan.steps if x.step_id == step_id)
                if res.startswith("Failed") or res.startswith("Error"):
                    s.status = "failed"
                    yield {"type": "log", "message": f"⚠️  Step {step_id} failed: {res}"}
                else:
                    s.status = "completed"
                    s.output = res
                    step_outputs[step_id] = res
                    yield {"type": "tool_result", "step_id": step_id, "result": res}
                    accumulated_results.append(f"[{s.description}]\n{res}")

            save_active_plan(plan)
            continue  # Check for newly ready steps

        # 3. Stage the first ready write step
        if ready_write_steps:
            step = ready_write_steps[0]
            step.parameters = _interpolate_value(step.parameters, step_outputs)
            step.status = "running"
            save_active_plan(plan)

            from app.agents.safety import classify  # noqa: PLC0415
            safety_rating = classify(step, {"user_id": user_id})

            if safety_rating.level == "dangerous" or safety_rating.scope_warning:
                yield {
                    "type": "safety_warning",
                    "message": safety_rating.scope_warning,
                    "requires_double_confirm": safety_rating.requires_double_confirm,
                    "level": safety_rating.level,
                }

            mapping = _WRITE_APPROVAL_MAP.get(step.action)
            if mapping is None:
                step.status = "failed"
                save_active_plan(plan)
                yield {
                    "type": "error",
                    "message": f"Unknown write action '{step.action}' — cannot stage for approval.",
                }
                return

            execute_action_key, param_remap = mapping
            data = {target: step.parameters.get(source, "") for source, target in param_remap.items()}
            data["plan_id"] = plan.plan_id
            data["step_id"] = step.step_id

            if safety_rating:
                data["safety_warning"] = safety_rating.scope_warning
                data["requires_double_confirm"] = safety_rating.requires_double_confirm
                data["safety_level"] = safety_rating.level

            yield {
                "type": "log",
                "message": f"🚦 Staging '{step.action}' (Step {step.step_id}) for your approval…",
            }
            yield {
                "type": "approval_required",
                "action": execute_action_key,
                "data": data,
            }
            return  # Pause execution, wait for approval

        # 4. Final state check
        failed_steps = [s for s in plan.steps if s.status == "failed"]
        if failed_steps:
            save_active_plan(plan)
            yield {"type": "error", "message": f"Plan execution failed at step(s): {[s.step_id for s in failed_steps]}"}
            return

        completed_steps = [s for s in plan.steps if s.status == "completed"]
        if len(completed_steps) == len(plan.steps):
            save_active_plan(plan)
            final_text = "\n\n".join(accumulated_results) if accumulated_results else "Done."
            yield {"type": "result", "text": final_text}
            for event in _emit_history_update(user_text, final_text, history):
                yield event
            return

        # Fallback deadlock safety check
        save_active_plan(plan)
        yield {"type": "error", "message": "Dependency graph execution stalled. Aborting."}
        return


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _dispatch_read_action_async(step: TaskStep) -> str:
    """Execute a read-only action asynchronously in a thread pool."""
    fn = _READ_DISPATCH.get(step.action)
    if fn is None:
        return f"Error: unknown read action '{step.action}'"

    aliases = _PARAM_ALIASES.get(step.action, {})
    kwargs = {aliases.get(k, k): v for k, v in step.parameters.items() if v is not None}

    try:
        # Execute blocking function in background thread
        result = await asyncio.to_thread(fn, **kwargs)
        return str(result)
    except TypeError as exc:
        logger.warning("Tool call %s failed with bad args: %s", step.action, exc)
        try:
            result = await asyncio.to_thread(fn)
            return str(result)
        except Exception as e:
            return f"Failed to execute {step.action}: {e}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Tool %s raised an exception", step.action)
        return f"Failed to execute {step.action}: {exc}"


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
    updated = updated[-20:]  # cap at 20 entries
    yield {"type": "history_update", "history": updated}

