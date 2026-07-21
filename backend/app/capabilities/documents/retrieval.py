"""
app/capabilities/documents/retrieval.py — Hybrid semantic + keyword document retrieval.

Strategy:
  1. Dense retrieval  — pgvector cosine similarity (weight: 0.70)
  2. Sparse retrieval — PostgreSQL tsvector keyword search (weight: 0.30)
  3. Merge + deduplicate by chunk ID
  4. Rerank by combined score
  5. Filter by min_similarity threshold
  6. Enrich with document display names
  7. Return top-K RetrievedChunk objects

When Supabase is not configured, falls back to local implementations in
document_repository.py (pure-Python cosine similarity + keyword matching).

Edge cases handled:
  • No documents uploaded        → returns [] immediately
  • Embedding API failure        → falls back to keyword-only search
  • All chunks below threshold   → returns [] (prevents hallucination)
  • Query too long (>8K chars)   → truncated to first 4K chars before embedding
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.capabilities.documents.embedding import get_embedding_provider
from app.capabilities.documents.models import RetrievedChunk
from app.config.settings import settings
from app.repositories.document_repository import (
    load_document_records,
    search_chunks_vector,
    search_chunks_fulltext,
)

logger = logging.getLogger(__name__)

_VECTOR_WEIGHT = 0.70
_KEYWORD_WEIGHT = 0.30


def search_documents(
    user_id: str,
    query: str,
    top_k: int | None = None,
    document_id: str | None = None,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """
    Main retrieval entry point. Returns a ranked list of relevant document chunks.

    Args:
        user_id:     The user whose documents are searched.
        query:       Natural-language search query or question.
        top_k:       Number of chunks to return (default: settings.DOCUMENTS_TOP_K_RETRIEVAL).
        document_id: If set, restricts search to chunks from this specific document.
        min_score:   Minimum combined score threshold (default: settings.DOCUMENTS_MIN_SIMILARITY).

    Returns:
        List of RetrievedChunk, sorted by descending relevance score. May be empty.
    """
    top_k = top_k or settings.DOCUMENTS_TOP_K_RETRIEVAL
    min_score = min_score if min_score is not None else settings.DOCUMENTS_MIN_SIMILARITY

    # ── Guard: no documents exist ──────────────────────────────────────────────
    records = load_document_records(user_id)
    ready_records = [r for r in records if r.status == "ready"]
    if not ready_records:
        logger.info("No ready documents found for user=%s — returning empty.", user_id)
        return []

    # Build a document_name lookup: id → display_name
    doc_name_map: dict[str, str] = {r.id: r.display_name for r in ready_records}

    # ── Guard: scope to specific document if requested ────────────────────────
    if document_id and document_id not in doc_name_map:
        logger.warning("Requested document_id=%s not found or not ready.", document_id)
        return []

    # ── Truncate overly long queries ───────────────────────────────────────────
    if len(query) > 4000:
        logger.warning("Query truncated from %d to 4000 chars for embedding.", len(query))
        query = query[:4000]

    # ── Dense retrieval (vector similarity) ───────────────────────────────────
    vector_rows: list[dict] = []
    embedding_failed = False
    try:
        provider = get_embedding_provider()
        query_embedding = provider.embed_query(query)
        vector_rows = search_chunks_vector(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=top_k * 2,  # over-fetch; reranker will trim
            document_id=document_id,
        )
        logger.debug("Vector search returned %d candidates.", len(vector_rows))
    except Exception as exc:
        logger.warning("Vector search failed (%s) — falling back to keyword-only.", exc)
        embedding_failed = True

    # ── Sparse retrieval (full-text keyword search) ───────────────────────────
    keyword_rows = search_chunks_fulltext(
        user_id=user_id,
        query_text=query,
        top_k=top_k * 2,
        document_id=document_id,
    )
    logger.debug("Keyword search returned %d candidates.", len(keyword_rows))

    # ── Merge & rerank ────────────────────────────────────────────────────────
    # Build a score map: chunk_id → combined_score
    score_map: dict[str, float] = {}
    meta_map: dict[str, dict] = {}

    if not embedding_failed:
        for row in vector_rows:
            cid = str(row["id"])
            score_map[cid] = score_map.get(cid, 0.0) + row.get("similarity", 0.0) * _VECTOR_WEIGHT
            meta_map[cid] = row

    # Normalise keyword ranks (they are unbounded) to 0-1 range
    max_kw_rank = max((r.get("rank", 0) for r in keyword_rows), default=1.0) or 1.0
    for row in keyword_rows:
        cid = str(row["id"])
        norm_rank = row.get("rank", 0) / max_kw_rank
        score_map[cid] = score_map.get(cid, 0.0) + norm_rank * _KEYWORD_WEIGHT
        if cid not in meta_map:
            meta_map[cid] = row

    # Sort by combined score
    ranked = sorted(score_map.items(), key=lambda x: x[1], reverse=True)

    # Apply threshold and build output
    results: list[RetrievedChunk] = []
    for cid, score in ranked[:top_k]:
        if score < min_score:
            logger.debug("Chunk %s dropped (score=%.3f < threshold=%.3f).", cid, score, min_score)
            continue
        row = meta_map[cid]
        doc_id = str(row.get("document_id", ""))
        results.append(
            RetrievedChunk(
                chunk_id=cid,
                document_id=doc_id,
                document_name=doc_name_map.get(doc_id, "Unknown Document"),
                chunk_index=row.get("chunk_index", 0),
                content=row.get("content", ""),
                page_number=row.get("page_number"),
                similarity_score=round(score, 4),
                retrieval_method="keyword_only" if embedding_failed else "hybrid",
            )
        )

    logger.info(
        "Retrieval for user=%s query=%r → %d chunk(s) returned (threshold=%.2f).",
        user_id, query[:60], len(results), min_score,
    )
    return results


def format_chunks_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """
    Format retrieved chunks into a structured context block for LLM injection.
    Designed to be embedded directly in a Gemini system prompt or user message.
    """
    if not chunks:
        return "(No relevant document content found.)"

    sections: list[str] = ["=== RETRIEVED DOCUMENT CONTEXT ==="]
    current_doc = ""
    for i, chunk in enumerate(chunks, start=1):
        if chunk.document_name != current_doc:
            current_doc = chunk.document_name
            sections.append(f"\n📄 Document: {current_doc}")
        page_str = f" [Page {chunk.page_number}]" if chunk.page_number else ""
        score_str = f" (relevance: {chunk.similarity_score:.2f})"
        sections.append(f"--- Chunk {i}{page_str}{score_str} ---")
        sections.append(chunk.content)

    sections.append("=== END DOCUMENT CONTEXT ===")
    return "\n".join(sections)
