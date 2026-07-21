# A.L.T.A.I.R. Document Intelligence Feature — Architecture & Implementation Plan

> **Feature**: Intelligent Document Upload, Storage, and Cross-Feature RAG Pipeline
> **Status**: Planning
> **Scope**: Backend (Python / FastAPI) + Flutter Frontend (Upload UI)

---

## 1. Problem Statement & Vision

A.L.T.A.I.R. currently operates with ephemeral, session-scoped information. A business owner wants to upload a contract, a financial report, or a client proposal **once**, and then reference it across any workflow:

- *"Draft an email to Marcus summarizing the key clauses from the NDA I uploaded."*
- *"Check my Q2 report and tell me if the revenue target was met."*
- *"When creating a calendar invite for the investor meeting, pull the context from the pitch deck."*

This requires a **persistent, queryable document store** deeply integrated into the coordinator agent's context window and the planner's tool system — not just a file storage bucket.

---

## 2. Core Design Decisions

### 2.1 Storage: Two-Tier Strategy

Documents require **two separate stores** serving fundamentally different purposes:

| Tier | Purpose | Technology |
|---|---|---|
| **File Store** | Raw document persistence (PDF, DOCX, images, etc.) | Supabase Storage (S3-compatible) |
| **Vector Store** | Semantic search over document content (embeddings) | Supabase `pgvector` extension |

A file-only storage would force us to re-parse every document on every query, creating unbearable latency and prohibitive token costs for large files. A vector-only approach discards the original file needed for rendering in the UI and for re-parsing if the embedding model changes.

### 2.2 Ingestion Pipeline: Offline Processing

Document upload **must not block the user**. A heavy PDF (100 pages, scanned) could take 30-60 seconds to process. The upload endpoint returns immediately with a `processing` status, and a background task handles all chunking, embedding generation, and vector upsert work.

```
Upload Request  →  Store Raw File  →  Return 202 Accepted
                           ↓
                 Background Task (async)
                           ↓
          Parse → Chunk → Embed → Upsert pgvector
                           ↓
                   Mark doc as "ready"
```

### 2.3 Retrieval: Hybrid Semantic + Keyword Search

Pure vector similarity search has known failure modes — it can miss exact named entities (e.g., "Invoice #INV-2025-003") that do not appear close together in the embedding space. We will use a **hybrid search** strategy:

- **Dense retrieval**: `pgvector` cosine similarity for semantic queries.
- **Sparse retrieval / keyword fallback**: PostgreSQL `tsvector` full-text search.
- **Reranking**: Retrieved chunks from both approaches merged and reranked by relevance score before injection into the prompt.

### 2.4 How Documents Reach Gemini

We **do not** pass the entire document file to Gemini for every query. Instead:

1. The agent's query triggers a vector similarity search against the user's document corpus.
2. The top-K most relevant chunks (typically K=5–10) are retrieved.
3. These chunks are injected into the prompt as a structured context block, similar to how `resolve_memory_context()` currently works.
4. For small documents (<32K tokens), Gemini **native file API** (`files.upload`) can be used to pass the raw PDF directly — no chunking required.

This dual strategy handles both small precise documents (use native file API) and large document corpora (use RAG chunks).

---

## 3. Directory Structure

The feature lives in `app/capabilities/documents/` — consistent with the existing domain architecture.

```
backend/app/
├── capabilities/
│   ├── documents/                      # [NEW] Document Intelligence domain
│   │   ├── __init__.py
│   │   ├── ingestion.py                # Parsing, chunking, embedding pipeline
│   │   ├── retrieval.py                # Vector + keyword hybrid search
│   │   ├── document_tools.py           # Gemini-callable tool functions
│   │   └── models.py                   # Pydantic schemas (DocumentRecord, Chunk)
├── repositories/
│   └── document_repository.py          # [NEW] CRUD for document_records table
```

---

## 4. Database Schema

Run the following in Supabase SQL Editor:

```sql
-- Enable vector extension (run once per project)
CREATE EXTENSION IF NOT EXISTS vector;


-- ─────────────────────────────────────────────────────────────────────────────
-- Table: document_records
-- Stores metadata about each uploaded document.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE public.document_records (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    user_id         TEXT            NOT NULL,
    filename        TEXT            NOT NULL,
    display_name    TEXT            NOT NULL,        -- user-editable label
    file_type       TEXT            NOT NULL,        -- 'pdf', 'docx', 'txt', 'image', 'csv'
    mime_type       TEXT            NOT NULL,
    storage_path    TEXT            NOT NULL,        -- path in Supabase Storage bucket
    file_size_bytes BIGINT          NOT NULL,
    status          TEXT            NOT NULL DEFAULT 'processing',  -- 'processing' | 'ready' | 'error'
    page_count      INTEGER,
    error_message   TEXT,
    tags            TEXT[]          NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT document_records_pkey PRIMARY KEY (id)
);

CREATE INDEX idx_document_records_user_id ON public.document_records (user_id);
CREATE INDEX idx_document_records_status  ON public.document_records (status);


-- ─────────────────────────────────────────────────────────────────────────────
-- Table: document_chunks
-- Stores parsed, embedded text chunks for RAG retrieval.
-- Each row is one piece of a document (e.g., one paragraph/page segment).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE public.document_chunks (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    document_id     UUID            NOT NULL REFERENCES public.document_records(id) ON DELETE CASCADE,
    user_id         TEXT            NOT NULL,
    chunk_index     INTEGER         NOT NULL,          -- sequential ordering within the doc
    content         TEXT            NOT NULL,           -- raw text of the chunk
    token_count     INTEGER         NOT NULL,
    page_number     INTEGER,
    embedding       vector(768),                        -- Gemini text-embedding-004 output
    tsv_content     TSVECTOR        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,

    CONSTRAINT document_chunks_pkey PRIMARY KEY (id)
);

CREATE INDEX idx_document_chunks_document_id ON public.document_chunks (document_id);
CREATE INDEX idx_document_chunks_user_id     ON public.document_chunks (user_id);
CREATE INDEX idx_document_chunks_embedding   ON public.document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_document_chunks_tsv         ON public.document_chunks USING GIN (tsv_content);


-- ─────────────────────────────────────────────────────────────────────────────
-- Row Level Security (enable when Supabase Auth is live in M4)
-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER TABLE public.document_records ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.document_chunks  ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Users access own documents" ON public.document_records
--     USING (user_id = auth.uid()::text);
-- CREATE POLICY "Users access own chunks" ON public.document_chunks
--     USING (user_id = auth.uid()::text);
```

> **Why `vector(768)`?** Gemini's `text-embedding-004` model outputs 768-dimensional vectors by default. If you switch embedding models later (e.g. OpenAI's `text-embedding-3-large` at 3072 dims), you will need to re-embed all chunks and alter the column.

---

## 5. Supabase Storage Bucket

In the Supabase Dashboard → Storage:

1. Create a new private bucket named `altair-documents`.
2. Configure the bucket policy: **Private** (files accessible server-side only via service role key, never directly by the client app).
3. Do **NOT** create a public URL policy — the raw file is served through the backend API, not directly from the CDN.

Files are stored at the path:
```
{user_id}/{document_id}/{original_filename}
```

---

## 6. Implementation Plan

### 6.1 Backend Changes (Phase 1 — Core Pipeline)

#### [NEW] `app/capabilities/documents/models.py`
Pydantic data models for the document domain:
```python
class DocumentRecord(BaseModel):
    id: UUID
    user_id: str
    filename: str
    display_name: str
    file_type: str
    mime_type: str
    storage_path: str
    file_size_bytes: int
    status: Literal["processing", "ready", "error"]
    page_count: int | None
    error_message: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime

class DocumentChunk(BaseModel):
    id: UUID
    document_id: UUID
    user_id: str
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None
    embedding: list[float] | None
```

---

#### [NEW] `app/capabilities/documents/ingestion.py`
The document processing pipeline. This runs in a background thread after upload:

```
parse_document(file_bytes, mime_type)
    └── extract_text_by_type()
          ├── PDF      → pypdf (text extraction) + pytesseract (fallback OCR)
          ├── DOCX     → python-docx
          ├── CSV      → csv.DictReader → formatted text representation
          ├── TXT/MD   → direct decode
          └── Image    → pytesseract OCR

chunk_text(full_text, chunk_size=512, overlap=64)
    └── Returns list[str] with sliding window token-aware chunking

embed_chunks(chunks: list[str]) → list[list[float]]
    └── Batched calls to Gemini text-embedding-004
        (batch size ≤ 100 per API call)

upsert_chunks(document_id, user_id, chunks, embeddings)
    └── Bulk upsert into document_chunks table via Supabase
```

**Chunking strategy:**
- Chunk size: `512 tokens` with `64-token overlap` (overlap preserves cross-boundary context).
- Chunks respect paragraph and sentence boundaries first.
- Token counting uses a lightweight estimation (words × 1.3) to avoid loading a full tokenizer.
- Maximum file size enforced at API boundary: `50 MB`.
- Maximum parsed text length: `4,000,000 characters` before chunking (safety guard).

---

#### [NEW] `app/capabilities/documents/retrieval.py`
Handles all similarity and hybrid search queries:

```python
def search_documents(
    user_id: str,
    query: str,
    top_k: int = 8,
    document_ids: list[str] | None = None,  # scope to specific docs
    min_score: float = 0.35,
) -> list[RetrievedChunk]:
    """
    1. Embed query text using text-embedding-004.
    2. Run pgvector cosine similarity search on document_chunks.
    3. Run PostgreSQL full-text tsvector search on same table.
    4. Merge and deduplicate by chunk id.
    5. Rerank by combined score (vector_score * 0.7 + keyword_score * 0.3).
    6. Return top_k results above min_score threshold.
    """
```

Edge cases handled:
- **No documents uploaded**: Returns empty list immediately.
- **Embedding API failure**: Falls back to keyword-only search.
- **All chunks below min_score**: Returns empty list with a log warning (prevents hallucination from irrelevant chunks).
- **Query too long (>8K tokens)**: Query is truncated to first 512 tokens before embedding.

---

#### [NEW] `app/capabilities/documents/document_tools.py`
Gemini-callable tool functions, registered with the coordinator agent:

```python
def search_my_documents(query: str, document_name: str | None = None) -> str:
    """
    Search through the user's uploaded documents and return relevant excerpts.
    Use this when the user references a document, report, contract, or any
    uploaded file to extract specific information from it.

    Args:
        query: The specific question or information to look for.
        document_name: Optional name of a specific document to search within.
    """

def list_my_documents() -> str:
    """
    List all documents the user has uploaded, with their names, types, and
    upload dates. Use this to show the user their document library.
    """

def get_document_summary(document_name: str) -> str:
    """
    Generate a concise summary of a specific uploaded document.
    Uses Gemini native file API for small docs, RAG summary for large ones.
    """
```

---

#### [NEW] `app/repositories/document_repository.py`
Thin repository layer for CRUD operations on `document_records` and `document_chunks`. Follows the same pattern as `watcher_repository.py`.

```python
def save_document_record(user_id, record: DocumentRecord) -> str  # returns document_id
def load_document_records(user_id) -> list[DocumentRecord]
def load_document_record_by_id(user_id, document_id) -> DocumentRecord | None
def load_document_by_name(user_id, display_name) -> DocumentRecord | None  # fuzzy match
def update_document_status(document_id, status, error_message, page_count)
def delete_document_record(user_id, document_id)  # also deletes chunks via CASCADE
def insert_chunks_batch(chunks: list[DocumentChunk]) -> None  # bulk upsert
def search_chunks_vector(user_id, query_embedding, top_k, document_id_filter) -> list
def search_chunks_fulltext(user_id, query_terms, top_k, document_id_filter) -> list
```

---

#### [MODIFY] `app/config/settings.py`
Add new configuration values:

```python
# ── Document Intelligence ─────────────────────────────────────────────────────
DOCUMENTS_BUCKET: str = "altair-documents"
DOCUMENTS_MAX_FILE_SIZE_MB: int = 50
DOCUMENTS_CHUNK_SIZE_TOKENS: int = 512
DOCUMENTS_CHUNK_OVERLAP_TOKENS: int = 64
DOCUMENTS_TOP_K_RETRIEVAL: int = 8
EMBEDDING_MODEL: str = "text-embedding-004"
```

---

#### [MODIFY] `app/main.py`
Add four new API endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agent/documents/upload` | Upload a document (multipart) → returns `{document_id, status: "processing"}` |
| `GET`  | `/agent/documents` | List all user documents with metadata |
| `GET`  | `/agent/documents/{document_id}` | Get status / metadata for a single document |
| `DELETE` | `/agent/documents/{document_id}` | Delete a document and all its chunks |

The `POST /upload` endpoint:
1. Validates file size and MIME type.
2. Uploads raw bytes to Supabase Storage.
3. Creates a `document_records` row with `status="processing"`.
4. Fires the ingestion pipeline as a background task (`asyncio.create_task`).
5. Returns `202 Accepted` immediately with the new `document_id`.

---

#### [MODIFY] `app/ai/coordinator.py`
Register document tools so Gemini can call them:

```python
from app.capabilities.documents.document_tools import (
    search_my_documents,
    list_my_documents,
    get_document_summary,
)

TOOLS: list[Any] = [
    search_web,
    stage_email,
    read_emails,
    get_calendar_events,
    create_calendar_event,
    # ── Document Intelligence ───────────────────────
    search_my_documents,
    list_my_documents,
    get_document_summary,
]
```

Also update `SYSTEM_INSTRUCTION` to include document grounding rules:
```
- When the user references a document, contract, report, or uploaded file, 
  always call search_my_documents before answering. NEVER fabricate content 
  from documents — only quote from retrieved chunks.
- If search_my_documents returns no relevant results, tell the user explicitly 
  and ask them to re-check the document name or rephrase their question.
```

---

### 6.2 New Python Dependencies

Add to `requirements.txt`:

```
# Document Intelligence
pypdf>=4.0.0                  # PDF text extraction
python-docx>=1.1.0            # DOCX parsing
pytesseract>=0.3.13           # OCR fallback for scanned PDFs / images
Pillow>=10.0.0                # Image processing for OCR
tiktoken>=0.7.0               # Token counting for chunking
```

> **Note on pytesseract**: Requires Tesseract OCR binary installed on the host OS. On production (Docker / Cloud Run), add `tesseract-ocr` to the Dockerfile apt install list.

---

### 6.3 Flutter Changes (Phase 2 — Upload UI)

The Flutter side only needs a simple document picker and status display — no parsing logic lives in the client.

**New screens / widgets:**
1. **Documents Library Screen** (`views/documents_screen.dart`) — Lists all uploaded documents with status chips (Processing / Ready / Error).
2. **Upload FAB** — `FilePicker` integration to pick files from device storage or Google Drive. Calls `POST /agent/documents/upload`.
3. **Document Status Card** (`widgets/document_status_card.dart`) — Shows filename, type icon, size, and current processing status with a shimmer effect while processing.
4. **Upload Progress** — Small persistent banner showing upload progress % when a file is being transmitted.

No new dependencies are strictly required. Use Flutter's built-in `http` package (multipart) and `file_picker` (already in scope from Milestone 1).

---

## 7. Cross-Feature Integration Points

This is where the feature becomes truly production-grade:

### 7.1 Email Drafting + Documents
When the coordinator drafts an email, Gemini can automatically call `search_my_documents` in the same agentic loop before calling `stage_email`:

*"Draft an email to the investor team referencing the Q2 projections from the pitch deck"*
```
1. search_my_documents(query="Q2 projections", document_name="pitch deck")
2. stage_email(recipient=..., body="...{retrieved chunk}...")
```

### 7.2 Watcher Actions + Documents
A future watcher action type `attach_document_summary` could be configured:
*"When I receive an email from Usman, pull a summary of the contract document and include it in my notification."*
This requires extending `WatcherAction` with a `parameters_json` schema that references `document_id`.

### 7.3 Calendar Events + Documents
*"Create a calendar event for the board meeting and add the agenda from the uploaded document as the event description."*
```
1. search_my_documents(query="board meeting agenda")
2. create_calendar_event(description="{retrieved_text}")
```

### 7.4 Planner DAG + Documents
Document retrieval is a **read-only, safe** tool — it can be placed in Phase 1 (parallel read stage) of any TaskPlan, feeding its output as a `{{step_N_result}}` interpolation token into downstream write steps (email drafting, etc.).

---

## 8. Edge Cases & Production Hardening

### 8.1 File Type & Security
| Risk | Mitigation |
|---|---|
| Malicious file (e.g., PDF with embedded JavaScript) | Extract text only — never execute or render with a browser engine |
| MIME type spoofing (e.g., `.exe` renamed to `.pdf`) | Validate MIME type with `python-magic` against actual binary header, not just extension |
| Extremely large files (>50 MB) | Enforce size limit in the FastAPI endpoint before any I/O begins (check `Content-Length` header) |
| Password-protected PDFs | Detect and return a descriptive error: `status="error"`, `error_message="Document is password-protected"` |
| Corrupted / unreadable files | Wrap the entire parse pipeline in try/except; set `status="error"` with a user-friendly message |

### 8.2 Ingestion Reliability
| Risk | Mitigation |
|---|---|
| Background ingestion task crashes | Use a `try/except` in the background task that updates `status="error"` before re-raising |
| Embedding API rate limit exceeded | Implement exponential backoff (3 retries, 1s / 4s / 16s) with `tenacity` library |
| Partial ingestion (some chunks stored, then failure) | Delete all existing chunks for `document_id` before beginning upsert; if error, re-delete as cleanup |
| Server restart mid-ingestion | On startup, query for any `status="processing"` records older than 10 minutes and re-queue them |

### 8.3 Vector Search Quality
| Risk | Mitigation |
|---|---|
| Empty or near-duplicate chunks | Deduplicate chunks by content hash before upsert |
| All retrieved chunks below relevance threshold | Return `[]` and log a warning — do NOT pass irrelevant chunks to the LLM |
| Cross-user data leak | `user_id` filter is applied at the SQL level on every query — never rely on application-layer filtering alone |
| Stale embeddings after model upgrade | Store `embedding_model` version string in `document_chunks` for future re-embedding migrations |

### 8.4 Capacity & Costs
| Concern | Approach |
|---|---|
| pgvector index size on Supabase free tier | IVFFlat index only created after >1,000 rows (Supabase best practice). Use `probes=10` for recall/speed balance |
| Token cost of embedding 100K-chunk corpus | Gemini `text-embedding-004` is currently free for up to 1M tokens/month. Add monitoring. |
| Storage cost of large PDFs | Compressed upload via `python-multipart` + Supabase Storage (S3-tier pricing). Alert user if they exceed a configurable quota (default: 500 MB) |

---

## 9. Implementation Phases & Sequencing

### Phase 1 — Core Backend (Week 1)
- [ ] Add Supabase Storage bucket `altair-documents`.
- [ ] Run Supabase SQL schema migrations.
- [ ] Implement `models.py`, `ingestion.py` (PDF + TXT only initially), `retrieval.py`, `document_tools.py`.
- [ ] Implement `document_repository.py`.
- [ ] Add `/agent/documents/upload`, `/agent/documents` endpoints in `main.py`.
- [ ] Register `search_my_documents` and `list_my_documents` in `coordinator.py`.
- [ ] Write test script `app/scratch/test_documents.py` to validate upload → ingest → search pipeline end-to-end.

### Phase 2 — Extended Format Support (Week 2)
- [ ] Add DOCX, CSV, and image OCR support in `ingestion.py`.
- [ ] Add `get_document_summary` tool using Gemini native file API for small docs.
- [ ] Add startup re-queue for stuck `processing` records.
- [ ] Add MIME type validation with `python-magic`.

### Phase 3 — Flutter UI (Week 2-3)
- [ ] Implement Documents Library Screen.
- [ ] Implement upload picker, multipart POST, and status polling.
- [ ] Add Document status card widget.

### Phase 4 — Cross-Feature Integration (Week 3)
- [ ] Test email drafting with document context.
- [ ] Test calendar event creation with document context.
- [ ] Test planner DAG with document retrieval as Phase 1 step.
- [ ] Add document reference in watcher action schema.

---

## 10. Open Questions & Decisions Required

> [!IMPORTANT]
> **Q1: OCR Strategy** — `pytesseract` requires the Tesseract binary pre-installed and adds significant Docker image size (~200 MB). Do you want OCR for scanned PDFs from day one, or start with text-native PDFs only and add OCR in Phase 2?

> [!IMPORTANT]
> **Q2: Embedding Model** — Gemini `text-embedding-004` is the natural choice given the existing Gemini API key. However, if the project later moves to a multi-cloud strategy, OpenAI or Cohere embeddings may be preferable for portability. Lock this decision in before Phase 1 to avoid re-embedding costs later.

> [!IMPORTANT]
> **Q3: Document Quota Per User** — What is the desired maximum storage per user account? Options: 100 MB / 500 MB / 2 GB. This affects Supabase Storage costs and should be enforced at the upload endpoint.

> [!NOTE]
> **Q4: Re-embedding on Model Update** — Should there be an admin API endpoint to trigger re-embedding of all user documents when the embedding model is upgraded? This is low-priority but should be designed for in the schema (i.e., storing `embedding_model` per chunk).
