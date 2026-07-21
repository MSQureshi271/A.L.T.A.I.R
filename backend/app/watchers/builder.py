"""
app/agents/watcher_builder.py — Watcher trigger DSL builder using Gemini.

Compiles natural language trigger descriptions into structured DSL JSON
rules, insulating the main Planner agent from DSL implementation details.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings

logger = logging.getLogger(__name__)


# ── Pydantic models for structured schema enforcement ───────────────────────

class DSLRule(BaseModel):
    field: str = Field(
        description="The field name to evaluate, e.g. 'sender', 'subject', 'body', 'has_attachment', 'title'."
    )
    operator: Literal[
        "equals", "not_equals", "contains", "not_contains", "exists", "greater_than", "less_than"
    ] = Field(description="The evaluation operator.")
    value: Any = Field(description="The target literal value to compare against.")


class DSLCondition(BaseModel):
    conjunction: Literal["AND", "OR"] = Field(
        default="AND",
        description="How rules are joined logically.",
    )
    rules: list[DSLRule] = Field(
        default_factory=list,
        description="List of conditional rules.",
    )


# ── System Instruction ────────────────────────────────────────────────────────

_BUILDER_SYSTEM_PROMPT = """
You are the Watcher Trigger Compiler for A.L.T.A.I.R.

Your job is to read a provider name and a user's natural language condition, and translate them into a structured JSON condition object.

━━━ PROVIDER ATTRIBUTIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Provider: gmail
  Available attributes for condition rules:
  - "sender": string representing sender email address or display name
  - "subject": string representing email subject line
  - "body": string email body preview snippet
  - "has_attachment": boolean if email has attachments

Provider: calendar
  Available attributes for condition rules:
  - "title": string meeting/event title
  - "description": string meeting/event description
  - "attendee_count": integer count of attendees
  - "is_recurring": boolean if it is a recurring event series

━━━ INSTRUCTIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Match the field name, operator, and value exactly based on the provider options.
2. Be case-insensitive when extracting values.
3. If no rules can be clearly deduced, return an empty rules list.
"""


def compile_trigger_dsl(provider: str, description: str) -> dict[str, Any]:
    """Call Gemini to translate a natural language condition into structured trigger DSL."""
    if not description or not description.strip():
        return {"conjunction": "AND", "rules": []}

    try:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = (
            f"PROVIDER: {provider}\n"
            f"CONDITION DESCRIPTION: {description}"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_BUILDER_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=DSLCondition,
                temperature=0.0,
            ),
        )

        raw_json = response.text.strip()
        parsed = json.loads(raw_json)
        logger.info("WatcherBuilder successfully compiled DSL: %s", parsed)
        return parsed

    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compile trigger DSL via Gemini")
        # Fail-safe default: return empty trigger rules
        return {"conjunction": "AND", "rules": []}
