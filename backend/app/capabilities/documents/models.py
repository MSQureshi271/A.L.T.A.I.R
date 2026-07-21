"""
app/capabilities/documents/models.py — Pydantic data models for Document Intelligence.

These schemas are the canonical data contracts shared between the ingestion
pipeline, the repository layer, the retrieval engine, and the API endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    """Metadata record for an uploaded document (maps to document_records table)."""

    id: str = ""                          # UUID as string; empty before DB insert
    user_id: str
    filename: str                          # original filename from the upload
    display_name: str                      # user-editable, defaults to filename stem
    file_type: str                         # 'pdf' | 'docx' | 'txt' | 'csv' | 'md'
    mime_type: str
    storage_path: str                      # path inside the Supabase Storage bucket
    file_size_bytes: int
    status: Literal["processing", "ready", "error"] = "processing"
    page_count: int | None = None
    chunk_count: int | None = None
    error_message: str | None = None
    tags: list[str] = Field(default_factory=list)
    embedding_model: str = ""              # e.g. "gemini/text-embedding-004" — stored for future re-embed migrations

    created_at: str = ""
    updated_at: str = ""


class DocumentChunk(BaseModel):
    """A single processed text chunk from a document (maps to document_chunks table)."""

    id: str | None = None                  # UUID assigned by DB on insert
    document_id: str
    user_id: str
    chunk_index: int                       # 0-based sequential position within the document
    content: str                           # raw text of this chunk
    token_count: int                       # estimated token count
    page_number: int | None = None         # originating page (PDF only)
    embedding: list[float] | None = None   # vector produced by the embedding provider
    embedding_model: str = ""              # provider + model that produced this embedding


class RetrievedChunk(BaseModel):
    """A chunk returned by the retrieval engine, enriched with document metadata."""

    chunk_id: str
    document_id: str
    document_name: str                     # display_name of the parent DocumentRecord
    chunk_index: int
    content: str
    page_number: int | None = None
    similarity_score: float                # 0.0–1.0; higher = more relevant
    retrieval_method: str = "hybrid"       # 'vector' | 'fulltext' | 'hybrid'
