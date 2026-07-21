"""
app/connectors/calendar_event_source.py — Calendar Event Ingestion Source.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging

from googleapiclient.discovery import build

from app.watchers.models import Event
from app.watchers.event_source import EventSource
from app.providers.google.token_manager import get_google_credentials

logger = logging.getLogger(__name__)


class CalendarEventSource(EventSource):
    """Event source that pulls and normalizes Google Calendar events."""

    @property
    def provider(self) -> str:
        return "calendar"

    def poll_events(self, user_id: str, last_checked: datetime) -> list[Event]:
        """Poll calendar for new or updated events since `last_checked`."""
        try:
            creds = get_google_credentials(user_id)
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)

            # Format timestamp to UTC RFC 3339 format
            # Ensure last_checked is timezone-aware in UTC
            if last_checked.tzinfo is None:
                last_checked = last_checked.replace(tzinfo=timezone.utc)
            else:
                last_checked = last_checked.astimezone(timezone.utc)

            updated_min = last_checked.isoformat().replace("+00:00", "Z")

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    updatedMin=updated_min,
                    singleEvents=True,
                    maxResults=20,
                )
                .execute()
            )

            items = events_result.get("items", [])
            events: list[Event] = []

            for item in items:
                event_id = item.get("id")
                updated_str = item.get("updated")

                if not updated_str or not event_id:
                    continue

                # Parse update timestamp
                event_time = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))

                # Skip if updated before or at last checked timestamp
                if event_time <= last_checked:
                    continue

                title = item.get("summary", "Untitled Meeting")
                description = item.get("description", "")
                attendees = item.get("attendees", [])
                recurrence = item.get("recurrence", [])
                status = item.get("status", "")

                # Set type based on status (Google Calendar marks deleted events as status='cancelled')
                event_type = "event_cancelled" if status == "cancelled" else "event_updated"

                event_hash_id = hashlib.sha256(
                    f"calendar_{event_id}_{updated_str}".encode("utf-8")
                ).hexdigest()

                events.append(
                    Event(
                        id=event_hash_id,
                        provider="calendar",
                        event_type=event_type,
                        timestamp=event_time,
                        attributes={
                            "title": title,
                            "description": description,
                            "attendee_count": len(attendees),
                            "is_recurring": len(recurrence) > 0,
                            "status": status,
                        },
                        raw_payload=item,
                    )
                )

            return events

        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to poll Calendar events for user=%s", user_id)
            return []
