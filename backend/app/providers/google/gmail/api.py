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
from email.mime.base import MIMEBase
from email import encoders as email_encoders
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


def list_email_attachments(email_id: str) -> str:
    """List all file attachments in a specific Gmail email message.

    Use this BEFORE download_email_attachment to discover which files are
    available and their sizes. Returns metadata only — no bytes are downloaded.

    Args:
        email_id: The unique Gmail message ID (obtained from read_emails).

    Returns:
        A plain-text list of attachments with filename, MIME type, size, and attachment_id.
    """
    user_id = settings.DEV_USER_ID
    try:
        creds = get_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()
        payload = msg.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        parts = payload.get("parts", [])
        attachments = []

        def _extract_parts(parts_list: list) -> None:
            for part in parts_list:
                filename = part.get("filename", "")
                if filename:
                    body_data = part.get("body", {})
                    attachment_id = body_data.get("attachmentId", "")
                    size_bytes = body_data.get("size", 0)
                    mime_type = part.get("mimeType", "application/octet-stream")
                    attachments.append({
                        "filename": filename,
                        "mime_type": mime_type,
                        "size_bytes": size_bytes,
                        "attachment_id": attachment_id,
                    })
                # Recurse into nested multipart parts
                if part.get("parts"):
                    _extract_parts(part["parts"])

        _extract_parts(parts)

        if not attachments:
            return f"No attachments found in email [{email_id}] — Subject: {headers.get('Subject', '(no subject)')}"

        lines = [
            f"Email: {headers.get('Subject', '(no subject)')} (from {headers.get('From', 'Unknown')})",
            f"Found {len(attachments)} attachment(s):\n",
        ]
        for i, att in enumerate(attachments, start=1):
            size_kb = att["size_bytes"] / 1024
            lines.append(
                f"  {i}. {att['filename']} ({att['mime_type']}, {size_kb:.1f} KB)\n"
                f"     attachment_id: {att['attachment_id']}"
            )

        # Encode full metadata as JSON comment for executor to parse downstream
        import json  # noqa: PLC0415
        lines.append(f"\n[ATTACHMENT_METADATA]:{json.dumps(attachments)}")
        return "\n".join(lines)

    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list email attachments for email_id=%s", email_id)
        return f"Failed to list attachments: {exc}"


def stage_email_with_attachment(
    recipient: str,
    subject: str,
    body: str,
    document_names: list[str],
) -> dict:
    """Stage an email draft with one or more documents attached, for user review before sending.

    Use this when the user asks to email a file from their Document Library.
    ALWAYS call this instead of sending directly — the user must approve.

    If a document name is ambiguous (multiple documents match), returns an
    ambiguity_question instead so the user can clarify.

    Args:
        recipient:      Recipient email address.
        subject:        Email subject line.
        body:           Plain-text email body.
        document_names: List of document name(s) to attach (fuzzy name match is used).

    Returns:
        A dict with type='approval_required' (with attachments list) or
        type='clarification_needed' if document names are ambiguous.
    """
    from app.repositories.document_repository import load_document_records, load_document_by_name  # noqa: PLC0415

    user_id = settings.DEV_USER_ID
    resolved_attachments = []
    clarifications_needed = []

    for name in document_names:
        # First try single fuzzy match
        record = load_document_by_name(user_id, name)
        if record:
            resolved_attachments.append({
                "document_id": record.id,
                "filename": record.filename,
                "display_name": record.display_name,
                "mime_type": record.mime_type,
                "storage_path": record.storage_path,
                "file_size_bytes": record.file_size_bytes,
            })
        else:
            # Check for multiple partial matches (2+ results → clarify)
            all_records = load_document_records(user_id)
            needle = name.strip().lower()
            partial = [
                r for r in all_records
                if needle in r.display_name.lower() or needle in r.filename.lower()
            ]
            if len(partial) >= 2:
                options = ", ".join(f"'{r.display_name}'" for r in partial[:5])
                clarifications_needed.append(
                    f"Multiple documents match '{name}': {options}. Which one did you mean?"
                )
            else:
                clarifications_needed.append(
                    f"No document named '{name}' found in your library."
                )

    if clarifications_needed:
        return {
            "type": "clarification_needed",
            "question": " ".join(clarifications_needed),
        }

    return {
        "type": "approval_required",
        "action": "send_email_with_attachment",
        "data": {
            "to": recipient,
            "subject": subject,
            "body": body,
            "attachments": resolved_attachments,
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


def send_email_via_gmail(
    to: str,
    subject: str,
    body: str,
    user_id: str,
    attachments: list[dict] | None = None,
) -> str:
    """
    Send an email via Gmail after the user has approved the staged draft.

    This function is NOT a Gemini tool — it is called directly by the
    /agent/execute-action endpoint after user approval.

    Args:
        to:          Recipient email address.
        subject:     Email subject line.
        body:        Plain-text email body.
        user_id:     The user ID whose stored OAuth tokens to use.
        attachments: Optional list of dicts with keys:
                     {document_id, filename, mime_type, storage_path, display_name}.
                     Each document's raw bytes are fetched from storage and attached.

    Returns:
        A confirmation message string.
    """
    from app.repositories.document_repository import get_document_file_bytes  # noqa: PLC0415

    creds = get_google_credentials(user_id)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # Build a RFC-2822 MIME message
    mime_msg = MIMEMultipart()
    mime_msg["to"] = to
    mime_msg["subject"] = subject
    mime_msg.attach(MIMEText(body, "plain"))

    # Attach documents from Document Library
    attached_names: list[str] = []
    if attachments:
        for att in attachments:
            storage_path = att.get("storage_path", "")
            filename = att.get("filename", "attachment")
            mime_type = att.get("mime_type", "application/octet-stream")
            try:
                file_bytes = get_document_file_bytes(storage_path)
                main_type, sub_type = (mime_type.split("/", 1) + ["octet-stream"])[:2]
                part = MIMEBase(main_type, sub_type)
                part.set_payload(file_bytes)
                email_encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=filename)
                mime_msg.attach(part)
                attached_names.append(att.get("display_name", filename))
                logger.info("Attached document '%s' (%d bytes) to email.", filename, len(file_bytes))
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to attach document '%s': %s", filename, exc)
                raise RuntimeError(f"Could not attach '{filename}': {exc}") from exc

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

    service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()

    if attached_names:
        names_str = ", ".join(f"'{n}'" for n in attached_names)
        logger.info("Email sent via Gmail to=%s subject=%r with attachments: %s", to, subject, names_str)
        return f"✅ Email sent to {to} — Subject: '{subject}' — Attachments: {names_str}"

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


# ── Internal: Gmail Attachment Ingestion ─────────────────────────────────────


def _ingest_attachment_bytes(
    user_id: str,
    email_id: str,
    attachment_id: str,
    filename: str,
    mime_type: str,
) -> str:
    """
    Download a Gmail attachment by ID and ingest it into the Document Library.

    This is an INTERNAL function — called by the /agent/execute-action endpoint
    after the user has confirmed the download on the approval card. It is NOT
    exposed to Gemini.

    Flow:
      1. Fetch raw bytes from Gmail API (attachments.get).
      2. Validate tier-based size quota (settings.upload_limit_bytes).
      3. Pass bytes through the standard document ingestion pipeline:
         parse → chunk → embed → upload_document_file → save_document_record.
      4. Return the new document_id on success.

    Args:
        user_id:       The user whose Gmail tokens and document library to use.
        email_id:      The Gmail message ID the attachment belongs to.
        attachment_id: The Gmail attachment ID from list_email_attachments.
        filename:      The original filename of the attachment.
        mime_type:     The MIME type reported by Gmail for this attachment.

    Returns:
        A string: "document_id:<uuid>" on success for downstream interpolation.

    Raises:
        RuntimeError: On quota violation, unsupported format, or API/storage errors.
    """
    from app.config.settings import settings as _s  # noqa: PLC0415
    from app.capabilities.documents.ingestion import (  # noqa: PLC0415
        is_supported, detect_file_type, validate_magic_bytes, run_ingestion_pipeline,
    )
    from app.capabilities.documents.models import DocumentRecord  # noqa: PLC0415
    from app.repositories.document_repository import upload_document_file, save_document_record  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    creds = get_google_credentials(user_id)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # Fetch raw attachment bytes from Gmail
    att_response = (
        service.users().messages().attachments()
        .get(userId="me", messageId=email_id, id=attachment_id)
        .execute()
    )
    raw_b64 = att_response.get("data", "")
    # Gmail uses URL-safe base64 with padding stripped — restore padding
    file_bytes = base64.urlsafe_b64decode(raw_b64 + "==")

    if not file_bytes:
        raise RuntimeError(f"Empty attachment data received for '{filename}'.")

    # Tier-based size quota
    limit = _s.upload_limit_bytes
    if limit > 0 and len(file_bytes) > limit:
        limit_mb = limit / (1024 * 1024)
        actual_mb = len(file_bytes) / (1024 * 1024)
        raise RuntimeError(
            f"Attachment '{filename}' ({actual_mb:.1f} MB) exceeds your tier upload limit "
            f"of {limit_mb:.0f} MB. Upgrade to a higher tier to save larger files."
        )

    # Validate format support and magic bytes
    if not is_supported(mime_type, filename):
        raise RuntimeError(
            f"File type '{mime_type}' ({filename}) is not supported for ingestion. "
            "Supported formats: PDF, DOCX, TXT, MD, CSV."
        )
    file_type = detect_file_type(mime_type, filename)
    validate_magic_bytes(file_bytes, file_type)

    # Build document record and upload raw file to storage
    document_id = str(uuid.uuid4())
    from pathlib import Path as _Path  # noqa: PLC0415
    display_name = _Path(filename).stem

    storage_path = upload_document_file(user_id, document_id, filename, file_bytes, mime_type)

    record = DocumentRecord(
        id=document_id,
        user_id=user_id,
        filename=filename,
        display_name=display_name,
        file_type=file_type,
        mime_type=mime_type,
        storage_path=storage_path,
        file_size_bytes=len(file_bytes),
        status="processing",
        source_type="email_attachment",
        source_email_id=email_id,
    )
    save_document_record(record)

    # Run the embedding + chunking pipeline synchronously
    # (called from a background task in main.py so this blocks only the BG thread)
    run_ingestion_pipeline(
        document_id=document_id,
        user_id=user_id,
        file_bytes=file_bytes,
        mime_type=mime_type,
        filename=filename,
    )

    logger.info(
        "Gmail attachment ingested: email_id=%s filename=%s document_id=%s",
        email_id, filename, document_id,
    )
    return f"document_id:{document_id}"
