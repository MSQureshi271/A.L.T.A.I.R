"""
app/agents/planner_schema.py  —  Pydantic models for the structured task plan.

The Planner Agent produces a TaskPlan JSON object that the Executor consumes.
Both the Planner (Gemini JSON mode) and the Executor import these models.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class TaskStep(BaseModel):
    """A single step in the task plan."""

    step_id: int = Field(
        description="Unique sequential identifier for this step, starting at 1."
    )
    tool: Literal["gmail", "calendar", "search", "memory", "none"] = Field(
        description="Which tool/service this step uses."
    )
    action: Literal[
        "read_emails",
        "draft_email",
        "delete_email",
        "read_email_details",
        "get_events",
        "create_event",
        "reschedule_event",
        "delete_event",
        "search_web",
        "clarify",
        "save_contact",
        "save_preference",
        "save_routine",
        "save_knowledge",
        "delete_memory",
    ] = Field(description="The specific action to perform within the tool.")

    parameters: dict = Field(
        default_factory=dict,
        description="Key-value arguments for the action.",
    )
    requires_confirmation: bool = Field(
        default=True,
        description=(
            "True for write/send/create/delete actions that need user approval. "
            "False for read-only lookups that can execute immediately."
        ),
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description="step_ids that must complete before this step runs.",
    )
    description: str = Field(
        description="One short sentence (under 15 words) describing this step for the UI."
    )


class TaskPlan(BaseModel):
    """A structured plan for fulfilling the user's command."""

    intent_summary: str = Field(
        description="One sentence summarising what the user wants to accomplish."
    )
    steps: list[TaskStep] = Field(
        default_factory=list,
        description="Ordered list of steps to execute. Empty if ambiguity_question is set.",
    )
    ambiguity_question: str | None = Field(
        default=None,
        description=(
            "If the request is too ambiguous to plan, ask the user this one specific "
            "question. When set, steps must be empty."
        ),
    )
