"""
app/tools/memory_tools.py  —  Gemini memory tools.

These tools are registered to Gemini. When Gemini wants to save a contact,
setting preference, routine, or semantic knowledge fact, it calls these tools.
Because write actions need user validation, they all stage approvals.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def save_contact(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    company: str | None = None,
    notes: str | None = None,
) -> dict:
    """Stage saving or updating a structured contact in user memory.

    ALWAYS use this tool when the user tells you a contact's email, phone,
    or notes, or asks you to remember a contact.

    Args:
        name:    The full name of the contact.
        email:   Optional email address.
        phone:   Optional phone number.
        company: Optional company name.
        notes:   Optional descriptive notes (e.g. "my accountant").
    """
    return {
        "type": "approval_required",
        "action": "save_contact",
        "data": {
            "name": name,
            "email": email or "",
            "phone": phone or "",
            "company": company or "",
            "notes": notes or "",
        },
    }


def save_preference(category: str, key: str, value: str) -> dict:
    """Stage saving or updating a preference or setting in user memory.

    ALWAYS use this tool when the user states a preference, communication rules,
    or email signature.

    Args:
        category: The category name (e.g., 'email', 'calendar', 'theme').
        key:      The specific preference key (e.g., 'signature', 'default_duration').
        value:    The preference value (can be a string, number, or JSON string).
    """
    return {
        "type": "approval_required",
        "action": "save_preference",
        "data": {
            "category": category,
            "key": key,
            "value": value,
        },
    }


def save_routine(name: str, steps: list[str]) -> dict:
    """Stage saving or updating a reusable workflow routine in user memory.

    ALWAYS use this tool when the user defines a routine or trigger-phrase
    with a sequence of actions.

    Args:
        name:  The name of the routine (e.g. 'weekly_review').
        steps: Ordered list of tool steps (e.g., ['calendar', 'gmail', 'search']).
    """
    return {
        "type": "approval_required",
        "action": "save_routine",
        "data": {
            "name": name,
            "steps": ",".join(steps),
        },
    }


def save_knowledge(text: str, importance: int = 1) -> dict:
    """Stage saving a free-form unstructured fact in user memory.

    ALWAYS use this tool when the user tells you a random fact to remember
    that does not fit structured contacts or preference settings.

    Args:
        text:       The fact text content.
        importance: Numerical score 1 (low) to 5 (high) depending on importance.
    """
    return {
        "type": "approval_required",
        "action": "save_knowledge",
        "data": {
            "text": text,
            "importance": importance,
        },
    }


def delete_memory(category: str, key: str) -> dict:
    """Stage deleting an existing memory record.

    Args:
        category: The memory category ('contacts', 'preferences', 'routines', 'knowledge').
        key:      The uniqueness key (contact name, preference key, routine name, or knowledge text).
    """
    return {
        "type": "approval_required",
        "action": "delete_memory",
        "data": {
            "category": category,
            "key": key,
        },
    }
