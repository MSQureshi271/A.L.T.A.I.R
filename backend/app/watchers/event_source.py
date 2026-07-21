"""
app/connectors/event_source.py — Event Source base interface.
"""
from __future__ import annotations

import abc
from datetime import datetime

from app.watchers.models import Event


class EventSource(abc.ABC):
    """Abstract interface for all event ingestion sources (pollers, webhooks)."""

    @property
    @abc.abstractmethod
    def provider(self) -> str:
        """Return the provider identifier, e.g. 'gmail', 'calendar'."""
        pass

    @abc.abstractmethod
    def poll_events(
        self,
        user_id: str,
        last_checked: datetime,
    ) -> list[Event]:
        """Query the provider API for events since `last_checked` and normalize them.

        Args:
            user_id:      The user account ID.
            last_checked: The timestamp of the last successful check run.

        Returns:
            A list of immutable, normalized Event objects.
        """
        pass
