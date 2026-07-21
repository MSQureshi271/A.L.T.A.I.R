"""
app/agents/watcher_event.py — The unified and immutable Event model.
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class Event(BaseModel):
    """Normalized, immutable representation of an ingestion event."""

    id: str = Field(
        description="Unique event ID, e.g., sha256(provider + external_event_id)"
    )
    provider: str = Field(
        description="The source platform provider, e.g., 'gmail', 'calendar'"
    )
    event_type: str = Field(
        description="Type of the event, e.g., 'email_received', 'event_cancelled'"
    )
    timestamp: datetime = Field(
        description="The original timestamp when the event occurred"
    )
    attributes: dict = Field(
        default_factory=dict,
        description="Normalized key-value attributes evaluated by the DSL rules",
    )
    raw_payload: dict = Field(
        default_factory=dict,
        description="The original unprocessed API event payload for debugging context",
    )

    model_config = {
        "frozen": True,  # Enforces immutability
    }
