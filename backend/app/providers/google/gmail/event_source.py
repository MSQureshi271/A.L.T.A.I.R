"""
app/connectors/gmail_event_source.py — Gmail Event Ingestion Source.
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


class GmailEventSource(EventSource):
    """Event source that pulls and normalizes Gmail messages."""

    @property
    def provider(self) -> str:
        return "gmail"

    def poll_events(self, user_id: str, last_checked: datetime) -> list[Event]:
        """Poll user inbox for new messages received since `last_checked`."""
        try:
            creds = get_google_credentials(user_id)
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            # Query messages since epoch timestamp
            epoch_seconds = int(last_checked.timestamp())
            q = f"after:{epoch_seconds}"

            list_result = (
                service.users()
                .messages()
                .list(userId="me", q=q, labelIds=["INBOX"])
                .execute()
            )

            messages = list_result.get("messages", [])
            events: list[Event] = []

            for msg_meta in messages:
                msg_id = msg_meta["id"]

                # Fetch full message body
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )

                payload = msg.get("payload", {})
                headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

                # Evaluate attachment existence
                has_attachment = False
                parts = payload.get("parts", [])
                if parts:
                    for part in parts:
                        if part.get("filename"):
                            has_attachment = True
                            break

                sender = headers.get("from", "Unknown Sender")
                subject = headers.get("subject", "(no subject)")
                snippet = msg.get("snippet", "")

                internal_date_ms = int(msg.get("internalDate", 0))
                # timezone-aware UTC datetime
                event_time = datetime.fromtimestamp(internal_date_ms / 1000.0, tz=timezone.utc)

                # Skip if event occurred before last checked window (guard against clock mismatch)
                if event_time <= last_checked:
                    continue

                event_hash_id = hashlib.sha256(f"gmail_{msg_id}".encode("utf-8")).hexdigest()

                events.append(
                    Event(
                        id=event_hash_id,
                        provider="gmail",
                        event_type="email_received",
                        timestamp=event_time,
                        attributes={
                            "sender": sender,
                            "subject": subject,
                            "body": snippet,
                            "has_attachment": has_attachment,
                        },
                        raw_payload=msg,
                    )
                )

            return events

        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to poll Gmail events for user=%s", user_id)
            return []
