"""
app/agents/memory_manager.py  —  The A.L.T.A.I.R. Memory Manager.

Manages CRUD operations for the four persistent memory tables (contacts,
preferences, routines, knowledge) using the hybrid db_client layer.

Also provides the Memory Resolver pre-pass to format all stored facts
for injection into the Planner Agent's prompt context.
"""
from __future__ import annotations

import logging
from typing import Any

from app.database.db_client import db_store_item, db_load_items, db_delete_item

logger = logging.getLogger(__name__)

# ── 1. Contacts (Layer 2 Fact) ────────────────────────────────────────────────

def save_contact(
    user_id: str,
    name: str,
    email: str | None = None,
    phone: str | None = None,
    company: str | None = None,
    notes: str | None = None,
) -> None:
    """Save or update a structured contact."""
    item = {
        "user_id": user_id,
        "name": name.strip(),
        "email": email.strip() if email else None,
        "phone": phone.strip() if phone else None,
        "company": company.strip() if company else None,
        "notes": notes.strip() if notes else None,
    }
    db_store_item("contacts", item, conflict_fields=["user_id", "name"])


def load_contacts(user_id: str) -> list[dict[str, Any]]:
    """Retrieve all contacts for the user."""
    return db_load_items("contacts", user_id)


def delete_contact(user_id: str, name: str) -> None:
    """Delete a contact by name."""
    db_delete_item("contacts", user_id, {"name": name.strip()})


# ── 2. Preferences (Layer 3 Settings) ─────────────────────────────────────────

def save_preference(
    user_id: str,
    category: str,
    key: str,
    value: Any,
) -> None:
    """Save or update a structured setting preference."""
    item = {
        "user_id": user_id,
        "category": category.strip().lower(),
        "key": key.strip().lower(),
        "value": value,
    }
    db_store_item("preferences", item, conflict_fields=["user_id", "category", "key"])


def load_preferences(user_id: str) -> list[dict[str, Any]]:
    """Retrieve all preferences for the user."""
    return db_load_items("preferences", user_id)


def delete_preference(user_id: str, category: str, key: str) -> None:
    """Delete a preference by category and key."""
    db_delete_item(
        "preferences",
        user_id,
        {"category": category.strip().lower(), "key": key.strip().lower()},
    )


# ── 3. Routines (Layer 4 Workflows) ───────────────────────────────────────────

def save_routine(
    user_id: str,
    name: str,
    steps: list[str],
) -> None:
    """Save or update a reusable workflow routine."""
    item = {
        "user_id": user_id,
        "name": name.strip().lower(),
        "steps": steps,
    }
    db_store_item("routines", item, conflict_fields=["user_id", "name"])


def load_routines(user_id: str) -> list[dict[str, Any]]:
    """Retrieve all routines for the user."""
    return db_load_items("routines", user_id)


def delete_routine(user_id: str, name: str) -> None:
    """Delete a routine by name."""
    db_delete_item("routines", user_id, {"name": name.strip().lower()})


# ── 4. Knowledge (Layer 5 Semantic Notes) ─────────────────────────────────────

def save_knowledge(
    user_id: str,
    text: str,
    importance: int = 1,
) -> None:
    """Save a free-form text fact.
    Note: For local fallback, we save to JSON.
    In real Supabase settings, pgvector embedding generation would run here.
    """
    item = {
        "user_id": user_id,
        "text": text.strip(),
        "importance": min(max(importance, 1), 5),
    }
    # For local fallback simplicity, conflict field is user_id + text
    db_store_item("knowledge", item, conflict_fields=["user_id", "text"])


def load_knowledge(user_id: str) -> list[dict[str, Any]]:
    """Retrieve all knowledge entries."""
    return db_load_items("knowledge", user_id)


def delete_knowledge(user_id: str, text: str) -> None:
    """Delete a knowledge entry matching text."""
    db_delete_item("knowledge", user_id, {"text": text.strip()})


# ── Memory Resolver pre-pass ──────────────────────────────────────────────────

def resolve_memory_context(user_id: str) -> str:
    """
    Retrieve all structured memory layers and format them into an injected text
    block for the Planner Agent's system context.
    """
    contacts = load_contacts(user_id)
    prefs = load_preferences(user_id)
    routines = load_routines(user_id)
    knowledge = load_knowledge(user_id)

    if not contacts and not prefs and not routines and not knowledge:
        return "(No prior user contacts, preferences, routines, or facts stored in memory.)"

    lines = ["=== USER PERSISTENT MEMORY CONTEXT ==="]

    if contacts:
        lines.append("--- Stored Contacts & Roles ---")
        for c in contacts:
            details = []
            if c.get("email"):
                details.append(f"email: {c['email']}")
            if c.get("phone"):
                details.append(f"phone: {c['phone']}")
            if c.get("company"):
                details.append(f"company: {c['company']}")
            if c.get("notes"):
                details.append(f"notes: {c['notes']}")
            
            det_str = f" ({', '.join(details)})" if details else ""
            lines.append(f"• Contact name: {c['name']}{det_str}")
        lines.append("")

    if prefs:
        lines.append("--- Stored Preferences & Rules ---")
        for p in prefs:
            lines.append(f"• Category '{p['category']}': key '{p['key']}' = {p['value']}")
        lines.append("")

    if routines:
        lines.append("--- Reusable Routines (Workflows) ---")
        for r in routines:
            lines.append(f"• Routine name: {r['name']} -> executes steps: {r['steps']}")
        lines.append("")

    if knowledge:
        lines.append("--- Semantic Knowledge (General Facts) ---")
        for k in knowledge:
            lines.append(f"• Fact: \"{k['text']}\" (Importance: {k.get('importance', 1)})")
        lines.append("")

    lines.append("======================================")
    return "\n".join(lines).strip()
