# A.L.T.A.I.R. — Email Attachments & Document-Attached Emails

> **Feature Specification & Implementation Plan**
> 
> Two tightly-coupled features that bridge the **Email** and **Document Library** capabilities, turning A.L.T.A.I.R. into a true personal filing system.

---

## Overview

### Feature 1 — Email Attachment Downloader
The user can ask the agent to download attachments from a specific email directly into the Document Library, where they are ingested, chunked, and embedded just like any manually uploaded file.

**Example prompts:**
- *"Download the attachment from the email I got from Sarah yesterday."*
- *"Save the PDF from the Q2 report email to my documents."*
- *"Grab the attachments from the last email from finance@acme.com."*

### Feature 2 — Send Email with Document Attachment
The user can ask the agent to send an email with one or more files from the Document Library attached directly to the outgoing email, without needing to upload anything manually.

**Example prompts:**
- *"Email the Q2 report to usman@acme.com."*
- *"Send the NDA document to Sarah with a brief covering note."*
- *"Forward the project brief to the team with a summary of its key points."*

---

## Architecture Decisions

### Why the Agent Must Be Prompted
Attachment downloading is **never** triggered automatically. The watcher engine may detect `has_attachment: true` on incoming emails, but it will only notify — it will never download. This preserves user privacy and prevents storage abuse. Only an explicit user voice/text prompt causes a download.

### HITL (Human-in-the-Loop) for Attachment Sending
Sending an email with a document attachment is a **destructive write action** (it sends data outside the system). It will always:
1. Show a confirmation card (the `approval_required` pattern) in the Flutter UI.
2. Display a preview of which document is being attached and to whom.
3. Require an explicit user tap to proceed.

### Storage Path for Downloaded Attachments
Gmail returns attachment data as base64-encoded bytes directly from the API. These bytes are passed to the existing `upload_document_file()` function in `document_repository.py`, so downloaded attachments follow exactly the same storage/ingestion pipeline as manually uploaded documents.

### Document Retrieval for Outbound Emails
The Gmail `send_email_via_gmail()` function already builds a `MIMEMultipart` message. Adding attachments means fetching the raw file bytes from Supabase Storage (or local fallback) and attaching them as `MIMEBase` parts — a standard `email.mime` operation requiring no new dependencies.

---

## Proposed Changes

---

### Phase 1 — Backend: Gmail Attachment Download

#### [MODIFY] gmail/api.py

**Add two new functions:**

1. **`list_email_attachments(email_id)`** — Read-only tool exposed to Gemini. Fetches the Gmail message, iterates over `payload.parts`, and returns a structured list of attachment metadata: `{ filename, mime_type, size_bytes, attachment_id }`. No download happens.

2. **`download_email_attachment(email_id, attachment_id, filename)`** — Write-action (requires confirmation). Fetches the attachment bytes via `service.users().messages().attachments().get(...)`, then calls the document ingestion pipeline:
   - Calls `parse_document(file_bytes, filename)` → `chunk_document()` → `embed_chunks()` → `upload_document_file()` → `save_document_record()`.
   - Returns the new `document_id`.

> **IMPORTANT:** `download_email_attachment` is a **write action** and must go through HITL (requires_confirmation = True). It triggers ingestion, which costs embedding API tokens and writes to the database/storage.

#### [MODIFY] document_repository.py

**Add `get_document_file_bytes(storage_path)`** — Retrieves raw file bytes from Supabase Storage (or local fallback) for a given `storage_path`. This is the inverse of `upload_document_file()` and is needed for sending document attachments in outgoing emails.

```python
def get_document_file_bytes(storage_path: str) -> bytes:
    """
    Fetch raw file bytes for a document.
    Used when attaching a document to an outgoing email.
    """
    sb = _get_supabase()
    if sb:
        response = sb.storage.from_(settings.DOCUMENTS_BUCKET).download(storage_path)
        return response  # bytes
    else:
        local_path = _DOC_FILES_DIR / Path(storage_path)
        return local_path.read_bytes()
```

---

### Phase 2 — Backend: Send Email with Document Attachment

#### [MODIFY] gmail/api.py

**Extend `send_email_via_gmail()`** to accept an optional `attachments: list[dict] | None` parameter. Each attachment dict has the shape:
```json
{
  "document_id": "uuid-...",
  "filename": "Q2_Report.pdf",
  "mime_type": "application/pdf",
  "storage_path": "user-id/uuid/Q2_Report.pdf"
}
```

The function fetches bytes for each attachment using `get_document_file_bytes(storage_path)` and attaches them as `MIMEBase` parts.

**Extend `stage_email()`** (the Gemini-facing staging function) to accept `document_names: list[str] | None = None`. When document names are provided, it resolves them to document records via `load_document_by_name()` and includes attachment metadata in the `approval_required` payload so the Flutter UI can display which documents will be sent.

#### [MODIFY] main.py

- **Add `/agent/execute-action` handler** for `"download_attachment"` action — calls `download_email_attachment()`, then fires the ingestion pipeline in a background task.
- **Extend `_execute_write_step_action()`** for `"draft_email"` — passes `attachments` list from parameters to `send_email_via_gmail()`.
- **Add `/agent/execute-action` handler** for a new `"send_email_with_attachment"` action that handles the confirmed delivery.

---

### Phase 3 — Agent Layer: Schema, Planner & Executor

#### [MODIFY] planner_schema.py

Add new actions to the `Literal` type definition:

```diff
action: Literal[
    "read_emails",
    "draft_email",
+   "list_email_attachments",
+   "download_email_attachment",
+   "draft_email_with_attachment",
    "delete_email",
    ...
]
```

| Action | Tool | requires_confirmation |
|---|---|---|
| `list_email_attachments` | `gmail` | `false` |
| `download_email_attachment` | `gmail` | `true` |
| `draft_email_with_attachment` | `gmail` | `true` |

#### [MODIFY] planner.py

Update `_PLANNER_SYSTEM_PROMPT` with:
- **New tool descriptions** for the three new actions under the `gmail` tool domain.
- **New DAG examples** showing multi-step patterns, e.g.:
  - *"Download the PDF from Sarah's email"* → Step 1: `read_emails` (find ID) → Step 2: `list_email_attachments` → Step 3: `download_email_attachment`.
  - *"Email the Q2 report to usman@acme.com"* → Step 1: `get_document_summary` (confirm doc exists) → Step 2: `draft_email_with_attachment`.
- **Planner rule** that `download_email_attachment` requires confirmation.
- **Planner rule** that `draft_email_with_attachment` requires confirmation.

#### [MODIFY] executor.py

- **`_READ_DISPATCH`**: Add `list_email_attachments`.
- **`_PARAM_ALIASES`**: Add parameter mappings for all three new actions.
- **`_WRITE_APPROVAL_MAP`**: Add `download_email_attachment` and `draft_email_with_attachment` mappings with their approval data shapes.

#### [MODIFY] safety.py

- Classify `download_email_attachment` as a write that **always requires confirmation** (medium risk — modifies document library).
- Classify `draft_email_with_attachment` as a write that **always requires confirmation** (high risk — sends external data).
- Do **not** add either to any auto-approve whitelist.

---

### Phase 4 — Flutter UI

#### [MODIFY] api_service.dart

Add API methods:
- `listEmailAttachments(String emailId)` → `GET /email/{email_id}/attachments`
- `downloadEmailAttachment(String emailId, String attachmentId, String filename)` → `POST /agent/execute-action` with `action: "download_attachment"`.

#### [NEW] approval_card_attachment.dart
A specialized HITL approval card widget shown when the agent stages a `download_email_attachment` action. Shows:
- 📎 Attachment filename and size.
- Source email sender + subject.
- **"Save to Documents"** and **"Cancel"** buttons.
- A loading shimmer while ingestion runs in the background after confirmation.

#### [MODIFY] voice_home_view.dart
Extend the existing approval card rendering logic (in `_buildApprovalCard()`) to handle two new action types:
- `download_attachment` → Render the new `ApprovalCardAttachment`.
- `send_email_with_attachment` → Extend the existing email approval card to show attached document pill badges (filename, file type icon) above the email body preview.

#### [MODIFY] documents_view.dart
When a document was originally sourced from a Gmail attachment (`source_type: "email_attachment"`), show a small **📧 From Email** badge on the document card — mirroring how documents know their source.

> **NOTE:** This badge is cosmetic only and requires adding a `source_type` field to the `DocumentRecord` model (backend `models.py`) and the Flutter `document.dart` model.

---

## Data Flow Diagrams

### Feature 1: Attachment Download Flow

```
User prompt: "Download PDF from Sarah's email"
       |
       v
[Planner] → DAG:
  Step 1 (read):     read_emails         → find email ID
  Step 2 (read):     list_email_attachments → confirm attachment_id, filename, size
  Step 3 (approval): download_email_attachment
       |
       v
[Flutter] shows confirmation card → User taps "Save to Documents"
       |
       v
[execute-action: download_attachment]
  1. Gmail API: attachments.get(email_id, attachment_id) → base64 bytes
  2. Document Engine: parse → chunk → embed
  3. Storage: upload_document_file()
  4. DB: save_document_record(source_type="email_attachment")
       |
       v
Document Library updates: 📄 Q2_Report.pdf — Ready
```

### Feature 2: Send Email with Document Attachment Flow

```
User prompt: "Email Q2 report to usman@acme.com"
       |
       v
[Planner] → DAG:
  Step 1 (read):     get_document_summary("Q2 report") → confirm doc exists
  Step 2 (approval): draft_email_with_attachment
       |
       v
[Executor: Step 1]
  load_document_by_name("Q2 report") → DocumentRecord {storage_path, filename, mime_type}
       |
       v
[Executor: Step 2 → approval_required payload]
  {
    type: "approval_required",
    action: "send_email_with_attachment",
    data: {
      to: "usman@acme.com",
      subject: "Q2 Financial Report",
      body: "Hi Usman, please find the Q2 report attached.",
      attachments: [{ document_id, filename, storage_path, mime_type }]
    }
  }
       |
       v
[Flutter] shows email card with 📎 Q2_Report.pdf pill → User taps "Send"
       |
       v
[execute-action: send_email_with_attachment]
  1. get_document_file_bytes(storage_path) → raw bytes
  2. MIMEMultipart → MIMEBase attachment
  3. Gmail API: messages.send()
       |
       v
"✅ Email sent to usman@acme.com with attachment: Q2_Report.pdf"
```

---

## New Backend Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/email/{email_id}/attachments` | List attachment metadata for a Gmail message |

The `POST /agent/execute-action` endpoint is **extended** (no new route) to handle:
- `"download_attachment"` — fetches, validates, ingests Gmail attachment bytes.
- `"send_email_with_attachment"` — fetches document bytes, builds MIME message, sends via Gmail.

---

## Schema Changes

### Backend — `models.py` (DocumentRecord)
```diff
+ source_type: str = "upload"        # "upload" | "email_attachment"
+ source_email_id: str | None = None # Gmail message ID if sourced from email
```

### Backend — `migrations.sql` (Supabase)
```sql
ALTER TABLE document_records ADD COLUMN source_type TEXT DEFAULT 'upload';
ALTER TABLE document_records ADD COLUMN source_email_id TEXT;
```

### Flutter — `document.dart`
```diff
+ final String sourceType;
+ final String? sourceEmailId;
+ bool get isFromEmail => sourceType == 'email_attachment';
```

---

## Safety & Privacy Rules

| Rule | Enforcement |
|---|---|
| Attachment download is never automatic | Watcher engine cannot call `download_email_attachment`. Only the executor, after explicit user approval, can. |
| File size limit enforced pre-download | `list_email_attachments` returns `size_bytes`. If a file exceeds `settings.MAX_UPLOAD_BYTES`, the executor rejects before downloading. |
| Supported MIME types only | Attachment ingestion passes through the same magic byte + MIME validation as manual uploads. Executables, encrypted PDFs, and unsupported formats are rejected with clean error messages. |
| Email with attachment always requires confirmation | `draft_email_with_attachment` is classified as high-risk in `safety.py`. Never auto-approved. |
| No document data leaked without approval | The staging step resolves document metadata (filename, size) without reading file bytes. Bytes are fetched only after explicit user confirmation. |

---

## Implementation Phases & Effort Estimate

| Phase | Scope | Key Files |
|---|---|---|
| **Phase 1** | Gmail attachment download backend | `gmail/api.py`, `document_repository.py`, `main.py`, `models.py`, `migrations.sql` |
| **Phase 2** | Send email with document attachment backend | `gmail/api.py`, `document_repository.py`, `main.py` |
| **Phase 3** | Agent layer (schema, planner, executor, safety) | `planner_schema.py`, `planner.py`, `executor.py`, `safety.py` |
| **Phase 4** | Flutter UI (approval cards, document badges) | `api_service.dart`, `voice_home_view.dart`, `documents_view.dart`, new `approval_card_attachment.dart` |

---

## Open Questions

> **Q1: Multi-attachment handling** — When an email has multiple attachments (e.g., 3 PDFs), should the agent download all of them in one step, or present each one for individual confirmation?
> *Recommended: batch confirmation — show all attachments in one card with individual checkboxes so the user can deselect any before saving.*

> **Q2: Attachment size cap** — What is the maximum file size for attachment ingestion? The existing manual upload limit is defined by `settings.MAX_UPLOAD_BYTES`. Should the same limit apply, or should email attachments have a separate, lower cap?

> **Q3: Document-to-email resolution** — When the user says *"email the Q2 report,"* should the agent use fuzzy-name matching (as `load_document_by_name()` currently does), or present a disambiguation card if multiple documents match?
> *Recommended: use existing fuzzy match for a single result; trigger a `clarify` step if 2+ documents match.*

> **Q4: Source badge visibility** — The `📧 From Email` source badge on document cards requires a DB migration (`ALTER TABLE`). Should this be included in the first implementation pass, or deferred?
