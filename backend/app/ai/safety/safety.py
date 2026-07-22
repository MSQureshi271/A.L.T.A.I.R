"""
app/agents/safety.py — Safety classifier for task steps.

Evaluates if a TaskStep is safe, caution, or dangerous, and computes
scope warnings dynamically (e.g. counting bulk email deletions or checking
calendar event attendees).
"""
from __future__ import annotations

import datetime
import logging
from typing import Literal

from googleapiclient.discovery import build
from pydantic import BaseModel

from app.ai.planner.planner_schema import TaskStep
from app.config.settings import settings
from app.providers.google.token_manager import get_google_credentials

logger = logging.getLogger(__name__)

# Threshold for bulk action warnings
BULK_THRESHOLD_N = 5


class SafetyRating(BaseModel):
    """The safety classification and details for a plan step."""

    level: Literal["safe", "caution", "dangerous"]
    scope_warning: str | None = None
    requires_double_confirm: bool = False


def classify(step: TaskStep, context: dict) -> SafetyRating:
    """Evaluate a step's action and parameter scope to return its safety rating.

    Args:
        step:    The TaskStep to classify.
        context: Context dictionary containing user_id.

    Returns:
        A SafetyRating configuration.
    """
    action = step.action
    user_id = context.get("user_id", settings.DEV_USER_ID)

    # 1. Read-only actions are inherently safe
    if action in (
        "read_emails",
        "read_email_details",
        "get_events",
        "search_web",
        "clarify",
    ):
        return SafetyRating(level="safe")

    # 2. Destructive action: delete_email
    if action == "delete_email":
        email_id = step.parameters.get("email_id")
        sender = step.parameters.get("sender")
        subject = step.parameters.get("subject")

        if email_id:
            # Single email deletion — caution
            try:
                creds = get_google_credentials(user_id)
                service = build("gmail", "v1", credentials=creds, cache_discovery=False)
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=email_id, format="metadata",
                         metadataHeaders=["From", "Subject"])
                    .execute()
                )
                headers = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }
                from_val = headers.get("From", "Unknown Sender")
                sub_val = headers.get("Subject", "(no subject)")
                return SafetyRating(
                    level="caution",
                    scope_warning=f"You are about to delete the email from '{from_val}' with subject '{sub_val}'.",
                )
            except Exception as e:
                logger.warning("Could not fetch details for safety deletion check: %s", e)
                return SafetyRating(
                    level="caution",
                    scope_warning="You are about to delete an email.",
                )
        else:
            # Bulk email deletion check
            q_parts = []
            if sender:
                q_parts.append(f"from:{sender}")
            if subject:
                q_parts.append(f"subject:{subject}")

            if not q_parts:
                return SafetyRating(
                    level="dangerous",
                    scope_warning="You are about to perform a bulk email deletion with no filter criteria.",
                    requires_double_confirm=True,
                )

            q = " ".join(q_parts)
            try:
                creds = get_google_credentials(user_id)
                service = build("gmail", "v1", credentials=creds, cache_discovery=False)
                list_result = (
                    service.users()
                    .messages()
                    .list(userId="me", q=q, labelIds=["INBOX"])
                    .execute()
                )
                messages = list_result.get("messages", [])
                count = len(messages)

                if count > BULK_THRESHOLD_N:
                    return SafetyRating(
                        level="dangerous",
                        scope_warning=f"You are about to delete {count} emails matching '{q}' from your inbox.",
                        requires_double_confirm=True,
                    )
                elif count > 0:
                    return SafetyRating(
                        level="caution",
                        scope_warning=f"You are about to delete {count} email(s) matching '{q}' from your inbox.",
                    )
                else:
                    return SafetyRating(
                        level="safe",
                        scope_warning="No inbox emails found matching deletion criteria.",
                    )
            except Exception as e:
                logger.warning("Failed to count emails for bulk delete safety: %s", e)
                return SafetyRating(
                    level="dangerous",
                    scope_warning=f"You are about to delete emails matching: {q}.",
                    requires_double_confirm=True,
                )

    # 3. Destructive action: delete_event
    if action == "delete_event":
        event_id = step.parameters.get("event_id")
        title = step.parameters.get("title")

        try:
            creds = get_google_credentials(user_id)
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)

            event = None
            if event_id:
                event = service.events().get(calendarId="primary", eventId=event_id).execute()
            elif title:
                now = datetime.datetime.utcnow().isoformat() + "Z"
                events_result = (
                    service.events()
                    .list(calendarId="primary", timeMin=now, q=title, maxResults=5)
                    .execute()
                )
                events = events_result.get("items", [])
                if events:
                    event = events[0]

            if event:
                summary = event.get("summary", "Untitled Meeting")
                attendees = event.get("attendees", [])
                recurrence = event.get("recurrence", [])

                warnings = []
                level: Literal["safe", "caution", "dangerous"] = "caution"
                double_confirm = False

                if recurrence:
                    warnings.append("This is a recurring event series.")
                    level = "dangerous"
                    double_confirm = True
                if attendees:
                    count = len(attendees)
                    warnings.append(
                        f"It has {count} attendee(s) who will receive cancellation updates."
                    )
                    level = "dangerous"
                    double_confirm = True

                warning_msg = f"You are about to delete the event '{summary}'."
                if warnings:
                    warning_msg += " " + " ".join(warnings)

                return SafetyRating(
                    level=level,
                    scope_warning=warning_msg,
                    requires_double_confirm=double_confirm,
                )
            else:
                return SafetyRating(
                    level="caution",
                    scope_warning=f"You are about to delete the calendar event matching '{title or event_id}'.",
                )
        except Exception as e:
            logger.warning("Failed to inspect calendar event for safety: %s", e)
            return SafetyRating(
                level="caution",
                scope_warning="You are about to delete a calendar event.",
            )

    # 4. Writes that are not destructive (draft_email, create_event, reschedule_event)
    if action in ("draft_email", "create_event", "reschedule_event"):
        return SafetyRating(level="caution")

    # 5. Email attachment download — saves bytes to Document Library (medium risk)
    if action == "download_email_attachment":
        return SafetyRating(
            level="caution",
            scope_warning="This will download the selected attachment(s) from Gmail and save them to your Document Library.",
        )

    # 6. Email with document attachment — sends your documents externally (high risk)
    if action == "draft_email_with_attachment":
        return SafetyRating(
            level="caution",
            scope_warning="This will attach document(s) from your library to an outgoing email and send them to the recipient.",
        )

    return SafetyRating(level="safe")
