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
from typing import Any, AsyncGenerator, Generator

from app.ai.planner.planner_schema import TaskPlan, TaskStep
from app.ai.safety.safety import SafetyRating
from app.config.settings import settings
from app.repositories.db_client import db_store_item, db_load_items
from app.providers.google.gmail.api import read_emails, read_email_details, list_email_attachments
from app.providers.google.calendar.api import get_calendar_events
from app.capabilities.search.search_tools import search_web
from app.capabilities.documents.document_tools import (
    search_my_documents,
    get_document_summary,
    list_my_documents,
)
from app.providers.notion.api import (
    search_notion,
    read_notion_page,
    query_notion_database,
    list_notion_databases,
)

logger = logging.getLogger(__name__)

# ── Tool dispatch tables ──────────────────────────────────────────────────────

# Read-only tools: called immediately, no confirmation required.
_READ_DISPATCH: dict[str, callable] = {
    "read_emails": read_emails,
    "read_email_details": read_email_details,
    "list_email_attachments": list_email_attachments,
    "get_events": get_calendar_events,
    "search_web": search_web,
    "search_my_documents": search_my_documents,
    "get_document_summary": get_document_summary,
    "list_my_documents": list_my_documents,
    "search_notion": search_notion,
    "read_notion_page": read_notion_page,
    "query_notion_database": query_notion_database,
    "list_notion_databases": list_notion_databases,
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
    "list_email_attachments": {"email_id": "email_id"},
    "get_events": {"days_ahead": "days_ahead"},
    "search_web": {"query": "query"},
    "search_my_documents": {"query": "query", "document_name": "document_name"},
    "get_document_summary": {"document_name": "document_name"},
    "list_my_documents": {},
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
    "search_notion": {"query": "query"},
    "read_notion_page": {"page_id": "page_id"},
    "query_notion_database": {
        "database_id": "database_id",
        "filter_description": "filter_description",
    },
    "list_notion_databases": {},
    "create_notion_page": {
        "parent_page_id": "parent_page_id",
        "title": "title",
        "content": "content",
    },
    "create_notion_database_entry": {
        "database_id": "database_id",
        "properties": "properties",
        "content": "content",
    },
    "append_notion_page": {
        "page_id": "page_id",
        "content": "content",
    },
    "update_notion_database_entry": {
        "page_id": "page_id",
        "entry_id": "page_id",
        "row_id": "page_id",
        "entry_title": "page_id",
        "row_title": "page_id",
        "title": "page_id",
        "properties": "properties",
        "data_source_id": "data_source_id",
        "database_id": "data_source_id",
    },

    "update_notion_page_content": {
        "page_id": "page_id",
        "old_str": "old_str",
        "new_str": "new_str",
    },
    "update_notion_data_source": {
        "data_source_id": "data_source_id",
        "title": "title",
    },
    "complete_notion_todo_item": {
        "page_id": "page_id",
        "item_text": "item_text",
        "completed": "completed",
    },
}

# Write-action → approval data shape mapping.
# Maps action name → (execute-action key, parameter remapping).
_WRITE_APPROVAL_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "draft_email": (
        "send_email",
        {"recipient": "to", "subject": "subject", "body": "body"},
    ),
    "draft_email_with_attachment": (
        "send_email_with_attachment",
        {
            "recipient": "to",
            "subject": "subject",
            "body": "body",
            "document_names": "document_names",
        },
    ),
    "download_email_attachment": (
        "download_attachment",
        {"email_id": "email_id", "attachments": "attachments"},
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
    "create_notion_page": (
        "create_notion_page",
        {"parent_page_id": "parent_page_id", "title": "title", "content": "content"},
    ),
    "create_notion_database_entry": (
        "create_notion_database_entry",
        {"database_id": "database_id", "properties": "properties", "content": "content"},
    ),
    "append_notion_page": (
        "append_notion_page",
        {"page_id": "page_id", "content": "content"},
    ),
    "update_notion_database_entry": (
        "update_notion_database_entry",
        {"page_id": "page_id", "properties": "properties", "data_source_id": "data_source_id"},
    ),
    "update_notion_page_content": (
        "update_notion_page_content",
        {"page_id": "page_id", "old_str": "old_str", "new_str": "new_str"},
    ),
    "update_notion_data_source": (
        "update_notion_data_source",
        {"data_source_id": "data_source_id", "title": "title"},
    ),
    "complete_notion_todo_item": (
        "complete_notion_todo_item",
        {"page_id": "page_id", "item_text": "item_text", "completed": "completed"},
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
    """Recursively interpolate references to previous step outputs (e.g. $step_1, $step_1.key, {{step_1_result}})."""
    if isinstance(val, str):
        # Pre-process handlebar or suffix syntaxes like {{step_1}}, {{step_1_result}}, $step_1_result -> $step_1
        normalized_val = re.sub(r"\{\{?\s*\$?(?:step_)?(\d+)(?:_result|\.result|\.output)?\s*\}\}?", r"$step_\1", val)
        normalized_val = re.sub(r"\$step_(\d+)(?:_result|\.result|\.output)\b", r"$step_\1", normalized_val)

        # 1. Exact match case: replace the whole value with the output object (preserves non-string types)
        exact_match = re.match(r"^\$step_(\d+)(?:\.(.+))?$", normalized_val)
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

        return re.sub(pattern, replace_match, normalized_val)

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

            from app.ai.safety.safety import classify  # noqa: PLC0415
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

            # If staging an email with document attachment, resolve document_names -> attachments metadata
            if step.action == "draft_email_with_attachment" or "document_names" in step.parameters:
                from app.repositories.document_repository import load_document_records, load_document_by_name  # noqa: PLC0415

                doc_names = step.parameters.get("document_names") or []
                if isinstance(doc_names, str):
                    doc_names = [d.strip() for d in doc_names.split(",") if d.strip()]

                resolved_attachments = []
                clarifications = []
                for name in doc_names:
                    rec = load_document_by_name(user_id, name)
                    if rec:
                        resolved_attachments.append({
                            "document_id": rec.id,
                            "filename": rec.filename,
                            "display_name": rec.display_name,
                            "mime_type": rec.mime_type,
                            "storage_path": rec.storage_path,
                            "file_size_bytes": rec.file_size_bytes,
                        })
                    else:
                        all_recs = load_document_records(user_id)
                        needle = name.strip().lower()
                        matches = [
                            r for r in all_recs
                            if needle in r.display_name.lower() or needle in r.filename.lower()
                        ]
                        if len(matches) == 1:
                            r = matches[0]
                            resolved_attachments.append({
                                "document_id": r.id,
                                "filename": r.filename,
                                "display_name": r.display_name,
                                "mime_type": r.mime_type,
                                "storage_path": r.storage_path,
                                "file_size_bytes": r.file_size_bytes,
                            })
                        elif len(matches) > 1:
                            opts = ", ".join(f"'{r.display_name}'" for r in matches[:5])
                            clarifications.append(
                                f"Multiple documents match '{name}': {opts}. Which one did you mean?"
                            )
                        else:
                            clarifications.append(
                                f"No document named '{name}' found in your Document Library."
                            )

                if clarifications:
                    step.status = "failed"
                    save_active_plan(plan)
                    yield {"type": "result", "text": " ".join(clarifications)}
                    return

                data["attachments"] = resolved_attachments
                step.parameters["attachments"] = resolved_attachments

            # Resolve human titles / Notion IDs before emitting approval payload
            if step.action in ("update_notion_database_entry", "update_notion_page_content", "update_notion_data_source", "complete_notion_todo_item"):
                from app.providers.notion.api import resolve_notion_id, resolve_datasource_id, resolve_database_row_id  # noqa: PLC0415
                logger.info(
                    "[PRE-STAGING DEBUGS] Staging step %d (%s) — initial parameters: %s, data: %s",
                    step.step_id, step.action, step.parameters, data
                )


                if step.action == "update_notion_database_entry":
                    raw_page = str(
                        step.parameters.get("page_id")
                        or step.parameters.get("entry_id")
                        or step.parameters.get("row_id")
                        or step.parameters.get("title")
                        or step.parameters.get("entry_title")
                        or data.get("page_id")
                        or ""
                    ).strip()

                    raw_ds = str(
                        step.parameters.get("data_source_id")
                        or step.parameters.get("database_id")
                        or data.get("data_source_id")
                        or ""
                    ).strip()

                    logger.info("[PRE-STAGING DEBUGS] Extracted raw values: raw_page='%s', raw_ds='%s'", raw_page, raw_ds)

                    # If raw_page is empty, check if row title was passed inside properties dict!
                    if not raw_page:
                        props = step.parameters.get("properties", {})
                        if isinstance(props, dict):
                            for candidate_key in ("Name", "Title", "Decks", "Entry", "Page", "Topic", "Item"):
                                if candidate_key in props and isinstance(props[candidate_key], str) and props[candidate_key].strip():
                                    raw_page = props[candidate_key].strip()
                                    logger.info("[PRE-STAGING DEBUGS] Extracted raw_page from properties['%s'] -> '%s'", candidate_key, raw_page)
                                    break

                    # 1. Resolve data_source_id
                    resolved_ds = ""
                    if raw_ds:
                        resolved_ds = resolve_datasource_id(raw_ds)
                        logger.info("[PRE-STAGING DEBUGS] Resolved raw_ds '%s' -> '%s'", raw_ds, resolved_ds)
                    else:
                        for s_step in plan.steps:
                            if s_step.action == "query_notion_database":
                                db_param = str(s_step.parameters.get("database_id", "")).strip()
                                if db_param:
                                    resolved_ds = resolve_datasource_id(db_param)
                                    logger.info("[PRE-STAGING DEBUGS] Inferred raw_ds from Step %d query ('%s') -> '%s'", s_step.step_id, db_param, resolved_ds)
                                    break

                    if resolved_ds:
                        step.parameters["data_source_id"] = resolved_ds
                        data["data_source_id"] = resolved_ds

                    # 2. Resolve page_id (database row UUID)
                    resolved_page = ""
                    if raw_page:
                        if resolved_ds:
                            row_id = resolve_database_row_id(resolved_ds, raw_page)
                            if row_id:
                                resolved_page = row_id
                                logger.info("[PRE-STAGING DEBUGS] Resolved row_id via database query: '%s' -> '%s'", raw_page, resolved_page)
                        if not resolved_page:
                            resolved_page = resolve_notion_id(raw_page, "page")
                            logger.info("[PRE-STAGING DEBUGS] Resolved raw_page via workspace search: '%s' -> '%s'", raw_page, resolved_page)
                    else:
                        logger.warning("[PRE-STAGING DEBUGS] raw_page is still empty after property checks!")


                    if resolved_page:
                        step.parameters["page_id"] = resolved_page
                        data["page_id"] = resolved_page

                    logger.info(
                        "[PRE-STAGING DEBUGS] FINAL STAGED DATA for update_notion_database_entry: page_id='%s', data_source_id='%s', properties=%s",
                        data.get("page_id"), data.get("data_source_id"), data.get("properties")
                    )

                elif step.action == "update_notion_page_content":
                    raw_page = str(step.parameters.get("page_id") or data.get("page_id") or "").strip()
                    if raw_page:
                        resolved_page = resolve_notion_id(raw_page, "page")
                        step.parameters["page_id"] = resolved_page
                        data["page_id"] = resolved_page

                elif step.action == "update_notion_data_source":
                    raw_ds = str(step.parameters.get("data_source_id") or data.get("data_source_id") or "").strip()
                    if raw_ds:
                        resolved_ds = resolve_datasource_id(raw_ds)
                        step.parameters["data_source_id"] = resolved_ds
                        data["data_source_id"] = resolved_ds

                elif step.action == "complete_notion_todo_item":
                    raw_page = str(step.parameters.get("page_id") or data.get("page_id") or "").strip()
                    if raw_page:
                        resolved_page = resolve_notion_id(raw_page, "page")
                        step.parameters["page_id"] = resolved_page
                        data["page_id"] = resolved_page



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
            if accumulated_results:
                has_raw_context = any(
                    "Retrieved Document Context" in r or "Document:" in r or "chunk_index" in r
                    for r in accumulated_results
                )
                if has_raw_context and user_text:
                    final_text = _synthesize_final_response(user_text, accumulated_results)
                else:
                    final_text = "\n\n".join(accumulated_results)
            else:
                final_text = "Done."

            yield {"type": "result", "text": final_text}
            for event in _emit_history_update(user_text, final_text, history):
                yield event
            return

        # Fallback deadlock safety check
        save_active_plan(plan)
        yield {"type": "error", "message": "Dependency graph execution stalled. Aborting."}
        return


# ── Response Synthesis ────────────────────────────────────────────────────────


def _synthesize_final_response(user_text: str, tool_outputs: list[str]) -> str:
    """
    Synthesize raw tool outputs (e.g. RAG document chunks, search results)
    into a clean, direct, executive response that directly answers the user's question.
    """
    from google import genai  # noqa: PLC0415
    from google.genai import types  # noqa: PLC0415

    context_block = "\n\n".join(tool_outputs)
    prompt = f"""You are A.L.T.A.I.R., an executive AI assistant.

The user asked: "{user_text}"

The system retrieved the following document context / tool results:
{context_block}

INSTRUCTIONS:
- Directly answer the user's question based ON THE RETRIEVED CONTEXT above.
- Do NOT output debug header blocks like "--- Retrieved Document Context ---" or similarity scores unless specifically asked.
- Provide a clean, executive, professional answer in markdown format.
"""
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return resp.text.strip() if resp.text else context_block
    except Exception as exc:  # noqa: BLE001
        logger.warning("Response synthesis failed (%s) — falling back to raw output", exc)
        return context_block


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

