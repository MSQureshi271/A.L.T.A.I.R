"""
app/capabilities/documents/document_tools.py — Gemini-callable document tools.

These functions are registered in the coordinator's TOOLS list and exposed
to Gemini via function calling. They are the sole document interface for the
agentic loop — the coordinator never accesses the repository directly.

Tool contract (important for good Gemini calling behaviour):
  • Docstrings must be precise — Gemini uses them to decide WHEN to call each tool.
  • Return type is always str (formatted text for Gemini to synthesize from).
  • Never raise exceptions — catch internally and return a user-friendly error string.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Tool: search_my_documents ─────────────────────────────────────────────────


def search_my_documents(query: str, document_name: str | None = None) -> str:
    """
    Search through the user's uploaded documents and return the most relevant excerpts.

    Use this tool whenever the user references a document, report, contract, proposal,
    spreadsheet, or any uploaded file to extract specific information from it.
    Also use it when the user asks a question that might be answered by their documents.

    Args:
        query:         The specific question or piece of information to search for.
        document_name: Optional. Name or partial name of a specific document to search
                       within. If omitted, searches across ALL uploaded documents.

    Returns:
        Formatted text containing the most relevant excerpts from matching documents,
        or a message indicating no relevant content was found.
    """
    from app.config.settings import settings  # noqa: PLC0415
    from app.capabilities.documents.retrieval import search_documents, format_chunks_for_prompt  # noqa: PLC0415
    from app.repositories.document_repository import load_document_by_name  # noqa: PLC0415

    user_id = settings.DEV_USER_ID
    target_doc_id: str | None = None

    try:
        # Resolve document name to ID if provided
        if document_name:
            record = load_document_by_name(user_id, document_name)
            if not record:
                return (
                    f"No document named '{document_name}' was found in your library. "
                    f"Use list_my_documents() to see your available documents."
                )
            if record.status == "processing":
                return (
                    f"The document '{record.display_name}' is still being processed. "
                    f"Please try again in a moment."
                )
            if record.status == "error":
                return (
                    f"The document '{record.display_name}' failed to process "
                    f"and cannot be searched. Error: {record.error_message or 'Unknown error'}"
                )
            target_doc_id = record.id

        chunks = search_documents(
            user_id=user_id,
            query=query,
            document_id=target_doc_id,
        )

        if not chunks:
            scope = f"in '{document_name}'" if document_name else "across your document library"
            return (
                f"No relevant content found {scope} for the query: '{query}'. "
                f"Try rephrasing your question or check the document name with list_my_documents()."
            )

        return format_chunks_for_prompt(chunks)

    except Exception as exc:  # noqa: BLE001
        logger.exception("search_my_documents failed for query=%r", query)
        return f"An error occurred while searching your documents: {exc}"


# ── Tool: list_my_documents ───────────────────────────────────────────────────


def list_my_documents() -> str:
    """
    List all documents the user has uploaded, including their names, file types,
    sizes, upload dates, and current processing status.

    Use this tool when the user asks what documents they have uploaded, wants to
    manage their document library, or when you need to verify a document name
    before searching within it.

    Returns:
        A formatted list of all uploaded documents with their metadata.
    """
    from app.config.settings import settings  # noqa: PLC0415
    from app.repositories.document_repository import load_document_records  # noqa: PLC0415

    user_id = settings.DEV_USER_ID

    try:
        records = load_document_records(user_id)

        if not records:
            return (
                "You have no documents uploaded yet. "
                "You can upload documents via the A.L.T.A.I.R. app to use them in your workflows."
            )

        lines = [f"📚 Your Document Library ({len(records)} document(s)):", ""]
        for rec in records:
            size_str = _format_size(rec.file_size_bytes)
            status_emoji = {"ready": "✅", "processing": "⏳", "error": "❌"}.get(rec.status, "❓")
            page_str = f" | {rec.page_count} page(s)" if rec.page_count else ""
            chunk_str = f" | {rec.chunk_count} chunks" if rec.chunk_count and rec.status == "ready" else ""
            lines.append(
                f"{status_emoji} **{rec.display_name}** ({rec.file_type.upper()}, {size_str}{page_str}{chunk_str})"
            )
            lines.append(f"   Uploaded: {rec.created_at[:10] if rec.created_at else 'N/A'}")
            if rec.status == "error" and rec.error_message:
                lines.append(f"   ⚠️  Error: {rec.error_message}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as exc:  # noqa: BLE001
        logger.exception("list_my_documents failed")
        return f"An error occurred while loading your document library: {exc}"


# ── Tool: get_document_summary ────────────────────────────────────────────────


def get_document_summary(document_name: str) -> str:
    """
    Generate a concise summary of a specific uploaded document.

    Use this when the user asks for an overview, summary, or key highlights of
    a particular document without asking a specific question about its content.

    Args:
        document_name: The name or partial name of the document to summarize.

    Returns:
        A concise summary of the document's main content and key points.
    """
    from app.config.settings import settings  # noqa: PLC0415
    from app.capabilities.documents.retrieval import search_documents, format_chunks_for_prompt  # noqa: PLC0415
    from app.repositories.document_repository import load_document_by_name  # noqa: PLC0415

    user_id = settings.DEV_USER_ID

    try:
        record = load_document_by_name(user_id, document_name)
        if not record:
            return (
                f"No document named '{document_name}' was found. "
                f"Use list_my_documents() to see your available documents."
            )
        if record.status != "ready":
            return (
                f"The document '{record.display_name}' is not yet available "
                f"(status: {record.status}). Please try again shortly."
            )

        from app.repositories.document_repository import load_document_chunks_by_index  # noqa: PLC0415
        from app.capabilities.documents.models import RetrievedChunk  # noqa: PLC0415

        doc_info = (
            f"Document: {record.display_name} ({record.file_type.upper()}, "
            f"{_format_size(record.file_size_bytes)}"
            f"{f', {record.page_count} pages' if record.page_count else ''})\n\n"
        )

        # Small/Medium document: fetch sequential chunks 0..25 to preserve full chronological structure
        if record.chunk_count is not None and record.chunk_count <= 25:
            seq_chunks = load_document_chunks_by_index(user_id, record.id, max_chunks=25)
            if seq_chunks:
                retrieved_chunks = [
                    RetrievedChunk(
                        chunk_id=str(c.get("id", "")),
                        document_id=record.id,
                        document_name=record.display_name,
                        chunk_index=c.get("chunk_index", 0),
                        content=c.get("content", ""),
                        page_number=c.get("page_number"),
                        similarity_score=1.0,
                        retrieval_method="full_document_sequence",
                    )
                    for c in seq_chunks
                ]
                return doc_info + format_chunks_for_prompt(retrieved_chunks)

        # Large document: fallback to RAG cross-section retrieval
        chunks = search_documents(
            user_id=user_id,
            query="main topics overview key points summary conclusion",
            document_id=record.id,
            top_k=15,
            min_score=0.0,  # Accept all chunks for summary purposes
        )

        if not chunks:
            return f"The document '{record.display_name}' was processed but no content could be retrieved."

        return doc_info + format_chunks_for_prompt(chunks)

    except Exception as exc:  # noqa: BLE001
        logger.exception("get_document_summary failed for document_name=%r", document_name)
        return f"An error occurred while summarizing '{document_name}': {exc}"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    return f"{size_bytes / 1024 ** 3:.1f} GB"
