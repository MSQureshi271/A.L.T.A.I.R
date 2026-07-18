"""
app/agents/context_resolver.py — Context resolver agent.

Constructs the SessionContext object by evaluating active plans, silent calendar 
prefetching, and scanning conversation logs to identify mentioned people/emails.
"""
from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel
from app.database.db_client import db_load_items
from app.tools.calendar_tools import prefetch_upcoming_events


class SessionContext(BaseModel):
    last_mentioned_people: list[dict[str, str]]  # [{"name": "Sarah", "email": "sarah@acme.com"}]
    upcoming_events: list[dict[str, Any]]         # next 3 calendar events
    last_action: dict[str, Any] | None            # action executed in the last turn
    active_plan_id: str | None                    # active/paused plan ID


def resolve_session_context(history: list[dict], user_id: str) -> SessionContext:
    """Evaluate active plans, prefetch calendar events, and scan history for context."""
    # 1. Fetch upcoming events silently
    events = prefetch_upcoming_events(user_id, limit=3)

    # 2. Fetch contacts and active plans from Supabase or local cache
    db_contacts = db_load_items("contacts", user_id)
    db_plans = db_load_items("active_plans", user_id)

    # 3. Find active plan ID & last completed action
    active_plan_id = None
    last_action = None

    if db_plans:
        # Sort or find plans with running or awaiting_approval status
        active_plans = [p for p in db_plans if p.get("status") in ["running", "awaiting_approval"]]
        if active_plans:
            active_plan_id = active_plans[0].get("plan_id")

        # Gather all completed steps from all plans to find the last action taken
        completed_steps = []
        for p in db_plans:
            plan_json = p.get("plan_json", {})
            if isinstance(plan_json, dict) and "plan" in plan_json:
                plan_data = plan_json.get("plan", {})
            else:
                plan_data = plan_json

            steps = plan_data.get("steps", []) if isinstance(plan_data, dict) else []
            for s in steps:
                if s.get("status") == "completed":
                    completed_steps.append(s)

        if completed_steps:
            # Pick the last completed step
            last_s = completed_steps[-1]
            last_action = {
                "tool": last_s.get("tool"),
                "action": last_s.get("action"),
                "description": last_s.get("description"),
                "output": last_s.get("output"),
            }

    # 4. Extract mentioned people from history
    mentioned_people: list[dict[str, str]] = []
    seen_emails: set[str] = set()

    email_pattern = re.compile(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")

    # Walk history backwards (most recent first)
    for msg in reversed(history):
        text = msg.get("text", "")
        if not text:
            continue

        # Extract email addresses
        emails = email_pattern.findall(text)
        for email in emails:
            email_lower = email.lower()
            if email_lower not in seen_emails:
                seen_emails.add(email_lower)

                # Check if this email exists in our contact list
                contact_name = None
                for c in db_contacts:
                    if c.get("email") and c.get("email").lower() == email_lower:
                        contact_name = c.get("name")
                        break

                # Fallback: extract preceding capitalized name in text context
                if not contact_name:
                    words = text.split()
                    for idx, w in enumerate(words):
                        if email in w and idx > 0:
                            prev = words[idx - 1].strip("()<>[],. ")
                            if prev.istitle():
                                contact_name = prev
                                break

                mentioned_people.append({
                    "name": contact_name or email.split("@")[0].capitalize(),
                    "email": email,
                })

        # Check for direct mentions of contact names in history text
        for c in db_contacts:
            name = c.get("name")
            if name and name.lower() in text.lower():
                email = c.get("email", "")
                if email and email.lower() not in seen_emails:
                    seen_emails.add(email.lower())
                    mentioned_people.append({
                        "name": name,
                        "email": email,
                    })

        if len(mentioned_people) >= 3:
            break

    return SessionContext(
        last_mentioned_people=mentioned_people[:3],
        upcoming_events=events,
        last_action=last_action,
        active_plan_id=active_plan_id,
    )
