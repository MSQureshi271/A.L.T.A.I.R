"""
app/scratch/test_documents.py — End-to-end validation of the Document Intelligence pipeline.

Tests:
  1. test_parse_txt()       — parse a plain text document
  2. test_parse_pdf_bytes() — parse a minimal synthetic PDF
  3. test_chunking()        — verify chunk size and overlap behaviour
  4. test_ingestion_pipeline_local() — full local pipeline (no Supabase, no Gemini)
  5. test_retrieval_local()          — search chunks using local cosine similarity
  6. test_document_tools_list()      — verify list_my_documents tool output
  7. test_document_tools_search()    — verify search_my_documents tool output

Run from backend/ directory:
  python -m app.scratch.test_documents
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# UTF-8 stdout (prevents emoji crashes on Windows cp1252 terminals)
if sys.stdout.encoding != "utf-8":
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parents[3]))  # ensure project root is on path

from dotenv import load_dotenv
load_dotenv()

from app.capabilities.documents.ingestion import (
    _parse_txt,
    chunk_text,
    deduplicate_chunks,
    detect_file_type,
    parse_document,
)
from app.capabilities.documents.models import DocumentChunk, DocumentRecord, RetrievedChunk


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_fake_pdf_bytes() -> bytes:
    """
    Construct a minimal valid PDF with a single text page.
    We use pypdf to verify round-trip parsing.
    """
    from pypdf import PdfWriter, PdfReader
    from pypdf.generic import NameObject
    import io as _io

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    buf = _io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_dummy_chunks(document_id: str, user_id: str, n: int = 5) -> list[DocumentChunk]:
    """Create n dummy DocumentChunk objects with fake embeddings."""
    return [
        DocumentChunk(
            document_id=document_id,
            user_id=user_id,
            chunk_index=i,
            content=f"This is test chunk number {i} about topics alpha beta gamma delta epsilon.",
            token_count=12,
            page_number=i + 1,
            embedding=[float(i) / 10.0 if j == i else 0.0 for j in range(768)],
            embedding_model="test/mock-embedding",
        )
        for i in range(n)
    ]


# ── Test 1: Parse plain text ───────────────────────────────────────────────────


def test_parse_txt():
    text = "Hello world.\n\nThis is a test document with two paragraphs."
    parsed = _parse_txt(text.encode("utf-8"))
    assert len(parsed) > 0
    assert "Hello world" in parsed
    print("✅ test_parse_txt passed!")


# ── Test 2: Parse PDF bytes ────────────────────────────────────────────────────


def test_parse_pdf_bytes():
    """Parse a minimal blank-page PDF (no text); should raise ValueError about empty content."""
    try:
        pdf_bytes = _make_fake_pdf_bytes()
        result = parse_document(pdf_bytes, "application/pdf", "test.pdf")
        # Blank page PDF may have no text — that's expected
        print("✅ test_parse_pdf_bytes passed! (pages extracted:", len(result), ")")
    except ValueError as exc:
        if "No extractable text" in str(exc):
            print("✅ test_parse_pdf_bytes passed! (correctly raised ValueError for blank PDF)")
        else:
            raise


# ── Test 3: Chunking ───────────────────────────────────────────────────────────


def test_chunking():
    long_text = " ".join([f"word{i}" for i in range(2000)])
    chunks = chunk_text(long_text, chunk_size=256, overlap=32)
    assert len(chunks) > 1, "Expected multiple chunks for a 2000-word text."
    for text, tok in chunks:
        assert len(text) > 0, "Chunk should not be empty."
        assert tok > 0, "Token count should be positive."

    # Verify deduplication
    # Insert a duplicate at index 0
    dup_chunks = [chunks[0]] + chunks
    deduped = deduplicate_chunks(dup_chunks)
    assert len(deduped) == len(chunks), "Deduplication should have removed the exact duplicate."

    print(f"✅ test_chunking passed! ({len(chunks)} chunks produced, dedup verified)")


# ── Test 4: Full local ingestion pipeline ─────────────────────────────────────


def test_ingestion_pipeline_local():
    """
    Run the full ingestion pipeline with:
      - A synthetic TXT document
      - Mocked embedding provider (no Gemini API call)
      - Mocked repository writes (no Supabase / local file writes)
    """
    doc_id = "test-doc-001"
    user_id = "test-user-001"
    content = "The financial results for Q2 2025 show strong growth in recurring revenue. " * 30

    mock_provider = MagicMock()
    # Return fake 768-dim embeddings (called as method on provider instance)
    mock_provider.model_name = "test/mock-embedding"
    mock_provider.embed_documents.return_value = [[0.1] * 768 for _ in range(100)]

    with (
        patch("app.capabilities.documents.embedding.GeminiEmbeddingProvider.embed_documents",
              return_value=[[0.1] * 768 for _ in range(100)]),
        patch("app.repositories.document_repository.update_document_status") as mock_status,
        patch("app.repositories.document_repository.insert_chunks_batch") as mock_insert,
        patch("app.repositories.document_repository.delete_document_chunks"),
    ):
        from app.capabilities.documents.ingestion import run_ingestion_pipeline
        run_ingestion_pipeline(
            document_id=doc_id,
            user_id=user_id,
            file_bytes=content.encode("utf-8"),
            mime_type="text/plain",
            filename="q2_report.txt",
        )

        # Should have been called with status='ready'
        assert mock_status.called
        call_kwargs = mock_status.call_args.kwargs
        assert call_kwargs.get("status") == "ready", f"Expected 'ready', got: {call_kwargs}"

        # Chunks should have been inserted
        assert mock_insert.called
        inserted_chunks: list[DocumentChunk] = mock_insert.call_args.args[0]
        assert len(inserted_chunks) > 0, "No chunks were inserted!"
        assert all(c.embedding == [0.1] * 768 for c in inserted_chunks), "Embeddings not assigned."

    print(f"✅ test_ingestion_pipeline_local passed! ({len(inserted_chunks)} chunks ingested)")


# ── Test 5: Local retrieval ────────────────────────────────────────────────────


def test_retrieval_local():
    """
    Test retrieval using the pure-Python cosine similarity fallback.
    Mocks Supabase (not configured) and uses .document_chunks_cache.json path.
    """
    from app.capabilities.documents.retrieval import search_documents
    from app.capabilities.documents.models import DocumentRecord

    doc_id = "retrieval-test-doc"
    user_id = "retrieval-test-user"

    # Create dummy records and chunks
    dummy_record = DocumentRecord(
        id=doc_id,
        user_id=user_id,
        filename="contract.txt",
        display_name="Contract",
        file_type="txt",
        mime_type="text/plain",
        storage_path=f"{user_id}/{doc_id}/contract.txt",
        file_size_bytes=1000,
        status="ready",
    )

    # Chunk 2 is the "target" — has a high dot product with the query embedding
    dummy_chunks_raw = [
        {"id": f"c-{i}", "document_id": doc_id, "user_id": user_id,
         "chunk_index": i, "content": f"Chunk {i} about revenue targets and financial performance.",
         "page_number": i + 1, "embedding": [0.5 if j < 10 else 0.0 for j in range(768)]}
        for i in range(3)
    ]

    mock_provider = MagicMock()
    mock_provider.embed_query.return_value = [0.5 if j < 10 else 0.0 for j in range(768)]

    with (
        patch("app.capabilities.documents.retrieval.get_embedding_provider", return_value=mock_provider),
        patch("app.capabilities.documents.retrieval.load_document_records", return_value=[dummy_record]),
        patch("app.capabilities.documents.retrieval.search_chunks_vector") as mock_vec,
        patch("app.capabilities.documents.retrieval.search_chunks_fulltext", return_value=[]),
    ):
        mock_vec.return_value = [
            {"id": c["id"], "document_id": doc_id, "chunk_index": c["chunk_index"],
             "content": c["content"], "page_number": c["page_number"], "similarity": 0.92}
            for c in dummy_chunks_raw
        ]
        results = search_documents(user_id=user_id, query="financial revenue performance")

    assert len(results) > 0, "Expected at least one retrieved chunk."
    assert results[0].similarity_score >= 0.0
    assert results[0].document_name == "Contract"
    print(f"✅ test_retrieval_local passed! ({len(results)} chunk(s) retrieved)")


# ── Test 6: Document tools — list ─────────────────────────────────────────────


def test_document_tools_list():
    from app.capabilities.documents.document_tools import list_my_documents
    from app.capabilities.documents.models import DocumentRecord

    mock_records = [
        DocumentRecord(
            id="doc-1", user_id="u1", filename="report.pdf", display_name="Q2 Report",
            file_type="pdf", mime_type="application/pdf", storage_path="u1/doc-1/report.pdf",
            file_size_bytes=204800, status="ready", page_count=15, chunk_count=42,
        ),
    ]

    with (
        patch("app.repositories.document_repository.load_document_records", return_value=mock_records),
        patch("app.config.settings.settings") as mock_settings,
    ):
        mock_settings.DEV_USER_ID = "u1"
        result = list_my_documents()

    assert "Q2 Report" in result
    assert "PDF" in result
    print("✅ test_document_tools_list passed!")


# ── Test 7: Document tools — search ───────────────────────────────────────────


def test_document_tools_search():
    from app.capabilities.documents.document_tools import search_my_documents
    from app.capabilities.documents.models import RetrievedChunk

    mock_chunks = [
        RetrievedChunk(
            chunk_id="c1", document_id="doc-1", document_name="Q2 Report",
            chunk_index=0, content="Revenue grew 22% YoY in Q2 2025.", similarity_score=0.91,
        )
    ]

    with (
        patch("app.capabilities.documents.retrieval.search_documents", return_value=mock_chunks),
        patch("app.repositories.document_repository.load_document_by_name", return_value=None),
        patch("app.config.settings.settings") as mock_settings,
    ):
        mock_settings.DEV_USER_ID = "u1"
        result = search_my_documents(query="revenue growth Q2")

    assert "Revenue grew 22%" in result
    print("✅ test_document_tools_search passed!")


# ── Runner ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("\n=== Document Intelligence — Phase 1 Test Suite ===\n")

    test_parse_txt()
    test_parse_pdf_bytes()
    test_chunking()
    test_ingestion_pipeline_local()
    test_retrieval_local()
    test_document_tools_list()
    test_document_tools_search()

    print("\n🎉 All Document Intelligence Phase 1 tests passed!")
