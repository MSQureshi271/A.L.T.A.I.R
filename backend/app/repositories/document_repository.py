"""
app/repositories/document_repository.py — CRUD + Storage for the Document domain.

Dual-mode storage:
  • Supabase configured → uses Supabase Tables (document_records, document_chunks)
    + Supabase Storage for raw files + pgvector RPC functions for vector search.
  • Supabase NOT configured → local file fallback:
      - Raw files  → backend/.document_files/{user_id}/{document_id}/
      - Records    → .memory_cache.json (via db_client)
      - Chunks     → .document_chunks_cache.json (separate file; chunks can be large)
      - Vector search → pure-Python cosine similarity over in-memory float lists.
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.repositories.db_client import _get_supabase  # shared Supabase client
from app.capabilities.documents.models import DocumentChunk, DocumentRecord, RetrievedChunk

logger = logging.getLogger(__name__)

# ── Local fallback paths ──────────────────────────────────────────────────────

_BACKEND_DIR = Path(__file__).parents[2]  # points to backend/
_DOC_FILES_DIR = _BACKEND_DIR / ".document_files"
_CHUNKS_CACHE_FILE = _BACKEND_DIR / ".document_chunks_cache.json"
_RECORDS_TABLE = "document_records"


# ── Helper: local chunks cache ─────────────────────────────────────────────────

def _read_chunks_cache() -> dict:
    if not _CHUNKS_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CHUNKS_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_chunks_cache(data: dict) -> None:
    _CHUNKS_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── Document Records ──────────────────────────────────────────────────────────


def save_document_record(record: DocumentRecord) -> str:
    """
    Persist a DocumentRecord.  Assigns a new UUID id if the record has none.
    Returns the document_id (UUID string).
    """
    sb = _get_supabase()
    if not record.id:
        record.id = str(uuid.uuid4())

    item = record.model_dump(exclude={"embedding"})  # embedding is in chunks table
    item.pop("chunk_count", None)  # computed field

    now_iso = datetime.now(timezone.utc).isoformat()
    if not item.get("created_at"):
        item["created_at"] = now_iso
    item["updated_at"] = now_iso

    if sb:
        try:
            sb.table(_RECORDS_TABLE).upsert(item, on_conflict="id").execute()
            logger.info("Saved document record id=%s to Supabase.", record.id)
        except Exception as exc:
            logger.exception("Supabase save_document_record failed: %s", exc)
            raise RuntimeError(f"Database error saving document record: {exc}") from exc
    else:
        from app.repositories.db_client import db_store_item  # noqa: PLC0415
        db_store_item(_RECORDS_TABLE, item, conflict_fields=["id"])

    return record.id


def load_document_records(user_id: str) -> list[DocumentRecord]:
    """Retrieve all document records for a user, newest first."""
    sb = _get_supabase()
    raw: list[dict] = []

    if sb:
        try:
            result = (
                sb.table(_RECORDS_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            raw = result.data or []
        except Exception as exc:
            logger.exception("Supabase load_document_records failed: %s", exc)
            return []
    else:
        from app.repositories.db_client import db_load_items  # noqa: PLC0415
        raw = db_load_items(_RECORDS_TABLE, user_id)

    return [_row_to_record(r) for r in raw]


def load_document_record_by_id(user_id: str, document_id: str) -> DocumentRecord | None:
    """Retrieve a single document record by ID."""
    sb = _get_supabase()

    if sb:
        try:
            result = (
                sb.table(_RECORDS_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .eq("id", document_id)
                .maybe_single()
                .execute()
            )
            return _row_to_record(result.data) if result.data else None
        except Exception as exc:
            logger.exception("Supabase load_document_record_by_id failed: %s", exc)
            return None
    else:
        from app.repositories.db_client import db_load_items  # noqa: PLC0415
        rows = db_load_items(_RECORDS_TABLE, user_id)
        for r in rows:
            if r.get("id") == document_id:
                return _row_to_record(r)
        return None


def load_document_by_name(user_id: str, display_name: str) -> DocumentRecord | None:
    """
    Fuzzy-match a document by its display_name.
    Case-insensitive exact match first, then contains match.
    """
    records = load_document_records(user_id)
    needle = display_name.strip().lower()
    # 1. Exact (case-insensitive)
    for r in records:
        if r.display_name.lower() == needle:
            return r
    # 2. Contains
    for r in records:
        if needle in r.display_name.lower() or needle in r.filename.lower():
            return r
    return None


def update_document_status(
    document_id: str,
    status: str,
    page_count: int | None = None,
    chunk_count: int | None = None,
    error_message: str | None = None,
    embedding_model: str = "",
) -> None:
    """Update the processing status of a document record."""
    sb = _get_supabase()
    patch: dict[str, Any] = {"status": status}
    if page_count is not None:
        patch["page_count"] = page_count
    if chunk_count is not None:
        patch["chunk_count"] = chunk_count
    if error_message is not None:
        patch["error_message"] = error_message
    if embedding_model:
        patch["embedding_model"] = embedding_model
    patch["updated_at"] = _now_iso()

    if sb:
        try:
            sb.table(_RECORDS_TABLE).update(patch).eq("id", document_id).execute()
        except Exception as exc:
            logger.exception("Supabase update_document_status failed: %s", exc)
    else:
        from app.repositories.db_client import _read_mem_cache, _write_mem_cache  # noqa: PLC0415
        cache = _read_mem_cache()
        for user_cache in cache.values():
            for rec in user_cache.get(_RECORDS_TABLE, []):
                if rec.get("id") == document_id:
                    rec.update(patch)
        _write_mem_cache(cache)


def delete_document_record(user_id: str, document_id: str) -> None:
    """
    Delete a document record and all its associated chunks.
    Raw file deletion from Storage is handled separately (see delete_document_file).
    """
    sb = _get_supabase()

    if sb:
        try:
            # Chunks are deleted via CASCADE on the FK relationship.
            sb.table(_RECORDS_TABLE).delete().eq("id", document_id).eq("user_id", user_id).execute()
            logger.info("Deleted document record id=%s from Supabase.", document_id)
        except Exception as exc:
            logger.exception("Supabase delete_document_record failed: %s", exc)
            raise RuntimeError(f"Database error deleting document: {exc}") from exc
    else:
        from app.repositories.db_client import db_delete_item  # noqa: PLC0415
        db_delete_item(_RECORDS_TABLE, user_id, {"id": document_id})
        # Remove chunks from local cache
        cache = _read_chunks_cache()
        cache.pop(document_id, None)
        _write_chunks_cache(cache)


# ── Document Chunks ───────────────────────────────────────────────────────────


def insert_chunks_batch(chunks: list[DocumentChunk]) -> None:
    """Bulk-insert a list of DocumentChunk objects. Replaces any existing chunks for the document."""
    if not chunks:
        return

    sb = _get_supabase()
    rows = []
    for c in chunks:
        row = {
            "document_id": c.document_id,
            "user_id": c.user_id,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "token_count": c.token_count,
            "page_number": c.page_number,
            "embedding": c.embedding,
            "embedding_model": c.embedding_model,
        }
        if c.id:
            row["id"] = c.id
        rows.append(row)

    if sb:
        try:
            # Supabase upsert in batches of 500 to avoid request size limits
            batch_size = 500
            for i in range(0, len(rows), batch_size):
                sb.table("document_chunks").insert(rows[i : i + batch_size]).execute()
            logger.info("Inserted %d chunks for document_id=%s.", len(rows), chunks[0].document_id)
        except Exception as exc:
            logger.exception("Supabase insert_chunks_batch failed: %s", exc)
            raise RuntimeError(f"Database error inserting chunks: {exc}") from exc
    else:
        cache = _read_chunks_cache()
        doc_id = chunks[0].document_id
        cache[doc_id] = []
        for row in rows:
            row["id"] = str(uuid.uuid4())
            cache[doc_id].append(row)
        _write_chunks_cache(cache)
        logger.info("Stored %d chunks locally for document_id=%s.", len(rows), doc_id)


def delete_document_chunks(document_id: str) -> None:
    """Remove all stored chunks for a document (called before re-ingestion)."""
    sb = _get_supabase()

    if sb:
        try:
            sb.table("document_chunks").delete().eq("document_id", document_id).execute()
        except Exception as exc:
            logger.warning("Supabase delete_document_chunks failed (non-fatal): %s", exc)
    else:
        cache = _read_chunks_cache()
        cache.pop(document_id, None)
        _write_chunks_cache(cache)


def load_document_chunks_by_index(user_id: str, document_id: str, max_chunks: int = 25) -> list[dict]:
    """Retrieve chunks for a document in sequential order by chunk_index."""
    sb = _get_supabase()
    if sb:
        try:
            result = (
                sb.table("document_chunks")
                .select("id, document_id, chunk_index, content, page_number")
                .eq("user_id", user_id)
                .eq("document_id", document_id)
                .order("chunk_index", desc=False)
                .limit(max_chunks)
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.exception("load_document_chunks_by_index failed: %s", exc)
            return []
    else:
        cache = _read_chunks_cache()
        chunks = cache.get(document_id, [])
        user_chunks = [c for c in chunks if c.get("user_id") == user_id]
        user_chunks.sort(key=lambda c: c.get("chunk_index", 0))
        return user_chunks[:max_chunks]


# ── Vector & Fulltext Search ──────────────────────────────────────────────────


def search_chunks_vector(
    user_id: str,
    query_embedding: list[float],
    top_k: int = 8,
    document_id: str | None = None,
) -> list[dict]:
    """
    Run cosine-similarity nearest-neighbour search.
    Returns list of dicts with keys: id, document_id, chunk_index, content, page_number, similarity.
    """
    sb = _get_supabase()

    if sb:
        try:
            params: dict[str, Any] = {
                "query_embedding": query_embedding,
                "query_user_id": user_id,
                "match_count": top_k,
            }
            if document_id:
                params["filter_document_id"] = document_id
            result = sb.rpc("match_document_chunks", params).execute()
            return result.data or []
        except Exception as exc:
            logger.error("Supabase vector search RPC failed: %s", exc)
            return []
    else:
        return _local_vector_search(user_id, query_embedding, top_k, document_id)


def search_chunks_fulltext(
    user_id: str,
    query_text: str,
    top_k: int = 8,
    document_id: str | None = None,
) -> list[dict]:
    """
    Run PostgreSQL full-text keyword search.
    Returns list of dicts with keys: id, document_id, chunk_index, content, page_number, rank.
    """
    sb = _get_supabase()

    if sb:
        try:
            params: dict[str, Any] = {
                "query_text": query_text,
                "query_user_id": user_id,
                "match_count": top_k,
            }
            if document_id:
                params["filter_document_id"] = document_id
            result = sb.rpc("search_document_chunks_fulltext", params).execute()
            return result.data or []
        except Exception as exc:
            logger.error("Supabase fulltext search RPC failed: %s", exc)
            return []
    else:
        return _local_fulltext_search(user_id, query_text, top_k, document_id)


# ── Supabase Storage (raw files) ──────────────────────────────────────────────


def upload_document_file(user_id: str, document_id: str, filename: str, file_bytes: bytes, mime_type: str) -> str:
    """
    Upload a raw file to Supabase Storage or local fallback.
    Returns the storage_path string.
    """
    storage_path = f"{user_id}/{document_id}/{filename}"
    sb = _get_supabase()

    if sb:
        try:
            sb.storage.from_(settings.DOCUMENTS_BUCKET).upload(
                storage_path,
                file_bytes,
                file_options={"content-type": mime_type, "upsert": "true"},
            )
            logger.info("Uploaded file to Supabase Storage: %s", storage_path)
        except Exception as exc:
            logger.exception("Supabase Storage upload failed: %s", exc)
            raise RuntimeError(f"File storage error: {exc}") from exc
    else:
        local_path = _DOC_FILES_DIR / user_id / document_id / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(file_bytes)
        logger.info("Stored file locally: %s", local_path)

    return storage_path


def delete_document_file(storage_path: str) -> None:
    """Delete a raw file from Supabase Storage or local fallback."""
    sb = _get_supabase()

    if sb:
        try:
            sb.storage.from_(settings.DOCUMENTS_BUCKET).remove([storage_path])
            logger.info("Deleted file from Supabase Storage: %s", storage_path)
        except Exception as exc:
            logger.warning("Supabase Storage delete failed (non-fatal): %s", exc)
    else:
        local_path = _DOC_FILES_DIR / Path(storage_path)
        if local_path.exists():
            local_path.unlink()


# ── Local fallback implementations ────────────────────────────────────────────


def _local_vector_search(
    user_id: str,
    query_embedding: list[float],
    top_k: int,
    document_id: str | None,
) -> list[dict]:
    """Pure-Python cosine similarity over locally cached chunk embeddings."""
    cache = _read_chunks_cache()
    results: list[dict] = []

    target_docs = [document_id] if document_id else list(cache.keys())

    for doc_id in target_docs:
        chunks = cache.get(doc_id, [])
        for chunk in chunks:
            if chunk.get("user_id") != user_id:
                continue
            emb = chunk.get("embedding")
            if not emb:
                continue
            sim = _cosine_similarity(query_embedding, emb)
            results.append({
                "id": chunk.get("id", ""),
                "document_id": doc_id,
                "chunk_index": chunk.get("chunk_index", 0),
                "content": chunk.get("content", ""),
                "page_number": chunk.get("page_number"),
                "similarity": sim,
            })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


def _local_fulltext_search(
    user_id: str,
    query_text: str,
    top_k: int,
    document_id: str | None,
) -> list[dict]:
    """Simple keyword search over locally cached chunk content."""
    cache = _read_chunks_cache()
    query_words = set(query_text.lower().split())
    results: list[dict] = []

    target_docs = [document_id] if document_id else list(cache.keys())

    for doc_id in target_docs:
        chunks = cache.get(doc_id, [])
        for chunk in chunks:
            if chunk.get("user_id") != user_id:
                continue
            content = chunk.get("content", "").lower()
            hits = sum(1 for w in query_words if w in content)
            if hits > 0:
                rank = hits / max(1, len(query_words))
                results.append({
                    "id": chunk.get("id", ""),
                    "document_id": doc_id,
                    "chunk_index": chunk.get("chunk_index", 0),
                    "content": chunk.get("content", ""),
                    "page_number": chunk.get("page_number"),
                    "rank": rank,
                })

    results.sort(key=lambda x: x["rank"], reverse=True)
    return results[:top_k]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Utilities ─────────────────────────────────────────────────────────────────


def _row_to_record(row: dict) -> DocumentRecord:
    """Convert a raw DB/cache row dict to a DocumentRecord Pydantic model."""
    return DocumentRecord(
        id=str(row.get("id", "")),
        user_id=row.get("user_id", ""),
        filename=row.get("filename", ""),
        display_name=row.get("display_name", row.get("filename", "")),
        file_type=row.get("file_type", ""),
        mime_type=row.get("mime_type", ""),
        storage_path=row.get("storage_path", ""),
        file_size_bytes=row.get("file_size_bytes", 0),
        status=row.get("status", "processing"),
        page_count=row.get("page_count"),
        chunk_count=row.get("chunk_count"),
        error_message=row.get("error_message"),
        tags=row.get("tags") or [],
        embedding_model=row.get("embedding_model", ""),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )


def _now_iso() -> str:
    from datetime import datetime, timezone  # noqa: PLC0415
    return datetime.now(timezone.utc).isoformat()
