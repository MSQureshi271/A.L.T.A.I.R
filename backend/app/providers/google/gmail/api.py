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
import re
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


from googleapiclient.discovery import build

from app.config.settings import settings
from app.providers.google.token_manager import get_google_credentials

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


def _resolve_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    date_str = date_str.lower().strip()

    # Match YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str.replace("-", "/")

    # Match relative terms
    today = datetime.date.today()
    if date_str == "today":
        return today.strftime("%Y/%m/%d")
    if date_str == "yesterday":
        yesterday = today - datetime.timedelta(days=1)
        return yesterday.strftime("%Y/%m/%d")

    # Match "N days ago"
    match = re.match(r"^(\d+)\s+days?\s+ago$", date_str)
    if match:
        days = int(match.group(1))
        target_date = today - datetime.timedelta(days=days)
        return target_date.strftime("%Y/%m/%d")

    return date_str.replace("-", "/")


def read_emails(
    max_results: int = 5,
    sender: str | None = None,
    after_date: str | None = None,
    before_date: str | None = None,
) -> str:
    """Retrieve the most recent emails from the user's Gmail inbox.

    Args:
        max_results: Maximum number of emails to return (default 5, max 20).
        sender:      Optional email address or name to filter by (sender).
        after_date:  Optional start date filter (YYYY-MM-DD or relative e.g., 'yesterday', '2 days ago').
        before_date: Optional end date filter (YYYY-MM-DD or relative e.g., 'today').

    Returns:
        A plain-text summary of the most recent emails.
    """
    max_results = min(max_results, 20)
    user_id = settings.DEV_USER_ID

    try:
        creds = get_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        q_parts = []
        if sender:
            q_parts.append(f"from:{sender}")

        resolved_after = _resolve_date(after_date)
        if resolved_after:
            q_parts.append(f"after:{resolved_after}")

        resolved_before = _resolve_date(before_date)
        if resolved_before:
            q_parts.append(f"before:{resolved_before}")

        q = " ".join(q_parts) if q_parts else None

        # List message IDs
        list_result = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, labelIds=["INBOX"], q=q)
            .execute()
        )


        messages = list_result.get("messages", [])
        if not messages:
            return "No emails found matching your query." if q else "Your Gmail inbox is empty."

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
                f"{i}. [ID: {msg_meta['id']}]\n"
                f"   From: {headers.get('From', 'Unknown')}\n"
                f"   Subject: {headers.get('Subject', '(no subject)')}\n"
                f"   Date: {headers.get('Date', '')}\n"
                f"   Preview: {snippet}…"
            )

        return f"[Gmail Inbox — {len(summaries)} most recent]\n\n" + "\n\n".join(summaries)

    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read Gmail inbox")
        return f"Failed to read Gmail: {exc}"


def read_email_details(email_id: str) -> str:
    """Retrieve the complete text body of a specific Gmail message.

    Args:
        email_id: The unique ID of the email message to retrieve.

    Returns:
        The text body of the email message.
    """
    user_id = settings.DEV_USER_ID
    try:
        creds = get_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        msg = (
            service.users()
            .messages()
            .get(userId="me", id=email_id, format="full")
            .execute()
        )

        payload = msg.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        # Extract email body
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body += base64.urlsafe_b64decode(data.encode("UTF-8")).decode("UTF-8")
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data.encode("UTF-8")).decode("UTF-8")

        if not body:
            body = msg.get("snippet", "")

        return (
            f"From: {headers.get('From', 'Unknown')}\n"
            f"Subject: {headers.get('Subject', '(no subject)')}\n"
            f"Date: {headers.get('Date', '')}\n\n"
            f"{body}"
        )
    except Exception as exc:
        logger.exception("Failed to retrieve email details")
        return f"Failed to retrieve email details: {exc}"


def stage_delete_email(
    email_id: str = "",
    sender: str = "",
    subject: str = "",
) -> dict:
    """Stage an email deletion for the user to review before trashing it.

    ALWAYS use this tool when the user requests to delete messages. The user
    must explicitly approve before any messages are trashed.

    Args:
        email_id: The unique ID of the email to delete.
        sender:   Delete emails from this sender (for bulk deletion).
        subject:  Delete emails with this subject (for bulk deletion).

    Returns:
        A dict with type='approval_required' and the staged action data.
    """
    return {
        "type": "approval_required",
        "action": "delete_email",
        "data": {
            "email_id": email_id,
            "sender": sender,
            "subject": subject,
        },
    }


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


def delete_email_via_gmail(
    email_id: str,
    sender: str,
    subject: str,
    user_id: str,
    double_confirmed: bool = False,
) -> str:
    """Trash emails from Gmail after the user has approved the action.

    This function is NOT a Gemini tool — it is called directly by the
    /agent/execute-action endpoint after user approval.
    """
    creds = get_google_credentials(user_id)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    if email_id:
        service.users().messages().trash(userId="me", id=email_id).execute()
        return f"✅ Email with ID {email_id} has been moved to trash."

    # Bulk deletion
    q_parts = []
    if sender:
        q_parts.append(f"from:{sender}")
    if subject:
        q_parts.append(f"subject:{subject}")

    if not q_parts:
        return "❌ No email filter criteria provided. Deletion cancelled."

    q = " ".join(q_parts)
    list_result = (
        service.users()
        .messages()
        .list(userId="me", q=q, labelIds=["INBOX"])
        .execute()
    )
    messages = list_result.get("messages", [])

    if not messages:
        return f"No emails found matching query '{q}'."

    # Enforce bulk delete safety limit (N = 5)
    from app.ai.safety.safety import BULK_THRESHOLD_N
    if len(messages) > BULK_THRESHOLD_N and not double_confirmed:
        raise ValueError(
            f"Bulk deletion of {len(messages)} emails exceeds safe limit of {BULK_THRESHOLD_N} "
            f"and was not double-confirmed."
        )

    for msg in messages:
        service.users().messages().trash(userId="me", id=msg["id"]).execute()

    return f"✅ {len(messages)} email(s) matching '{q}' have been moved to trash."
