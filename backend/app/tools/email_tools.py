"""
app/tools/email_tools.py — Gmail tools exposed to Gemini.

stage_email()         → Unchanged: stages a draft for human approval (HITL).
read_emails()         → Now fetches real emails from Gmail API.
send_email_via_gmail()→ Called by execute-action after user approval.
                        NOT exposed to Gemini directly (only stage_email is).
"""
from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from app.config import settings
from app.database.token_manager import get_google_credentials

logger = logging.getLogger(__name__)


# ── Tool exposed to Gemini ────────────────────────────────────────────────────

def stage_email(recipient: str, subject: str, body: str) -> dict:
    """Stage an email draft for the user to review before sending.

    ALWAYS use this tool instead of a direct 'send' action.  The user will
    be shown the draft and must explicitly approve it before delivery.

    Args:
        recipient: The email address of the intended recipient.
        subject:   The email subject line.
        body:      The full body text of the email.

    Returns:
        A dict with type='approval_required' and the staged draft data.
    """
    return {
        "type": "approval_required",
        "action": "send_email",
        "data": {
            "to": recipient,
            "subject": subject,
            "body": body,
        },
    }


def read_emails(max_results: int = 5) -> str:
    """Retrieve the most recent emails from the user's Gmail inbox.

    Args:
        max_results: Maximum number of emails to return (default 5, max 20).

    Returns:
        A plain-text summary of the most recent emails.
    """
    max_results = min(max_results, 20)
    user_id = settings.DEV_USER_ID

    try:
        creds = get_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        # List message IDs
        list_result = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, labelIds=["INBOX"])
            .execute()
        )

        messages = list_result.get("messages", [])
        if not messages:
            return "Your Gmail inbox is empty."

        summaries: list[str] = []
        for i, msg_meta in enumerate(messages, start=1):
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_meta["id"], format="metadata",
                     metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            snippet = msg.get("snippet", "")[:120]

            summaries.append(
                f"{i}. From: {headers.get('From', 'Unknown')}\n"
                f"   Subject: {headers.get('Subject', '(no subject)')}\n"
                f"   Date: {headers.get('Date', '')}\n"
                f"   Preview: {snippet}…"
            )

        return f"[Gmail Inbox — {len(summaries)} most recent]\n\n" + "\n\n".join(summaries)

    except RuntimeError as exc:
        # Not connected yet — return a helpful message
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read Gmail inbox")
        return f"Failed to read Gmail: {exc}"


# ── Called by execute-action (NOT exposed to Gemini) ─────────────────────────

def send_email_via_gmail(to: str, subject: str, body: str, user_id: str) -> str:
    """
    Send an email via Gmail after the user has approved the staged draft.

    This function is NOT a Gemini tool — it is called directly by the
    /agent/execute-action endpoint after user approval.

    Args:
        to:      Recipient email address.
        subject: Email subject line.
        body:    Plain-text email body.
        user_id: The user ID whose stored OAuth tokens to use.

    Returns:
        A confirmation message string.
    """
    creds = get_google_credentials(user_id)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # Build a RFC-2822 MIME message
    mime_msg = MIMEMultipart()
    mime_msg["to"] = to
    mime_msg["subject"] = subject
    mime_msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

    service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()

    logger.info("Email sent via Gmail to=%s subject=%r", to, subject)
    return f"✅ Email sent to {to} — Subject: '{subject}'"
