-- ══════════════════════════════════════════════════════════════════════════════
-- A.L.T.A.I.R. Document Intelligence — Supabase SQL Migration
-- Run this entire script once in Supabase Dashboard → SQL Editor.
-- ══════════════════════════════════════════════════════════════════════════════


-- Step 0: Enable the pgvector extension (required for vector columns & search)
CREATE EXTENSION IF NOT EXISTS vector;


-- ─────────────────────────────────────────────────────────────────────────────
-- Table: document_records
-- Stores metadata about each uploaded document.
-- Raw file bytes live in Supabase Storage (bucket: altair-documents).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.document_records (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    user_id         TEXT            NOT NULL,
    filename        TEXT            NOT NULL,       -- original uploaded filename
    display_name    TEXT            NOT NULL,       -- user-editable label (defaults to filename stem)
    file_type       TEXT            NOT NULL,       -- 'pdf' | 'docx' | 'txt' | 'csv' | 'md'
    mime_type       TEXT            NOT NULL,
    storage_path    TEXT            NOT NULL,       -- path in Supabase Storage bucket
    file_size_bytes BIGINT          NOT NULL,
    status          TEXT            NOT NULL DEFAULT 'processing',  -- 'processing' | 'ready' | 'error'
    page_count      INTEGER,
    chunk_count     INTEGER,
    error_message   TEXT,
    tags            TEXT[]          NOT NULL DEFAULT '{}',
    embedding_model TEXT            NOT NULL DEFAULT '',   -- e.g. 'gemini/gemini-embedding-2'
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT document_records_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_document_records_user_id ON public.document_records (user_id);
CREATE INDEX IF NOT EXISTS idx_document_records_status  ON public.document_records (status);


-- ─────────────────────────────────────────────────────────────────────────────
-- Table: document_chunks
-- Stores parsed, embedded text chunks for RAG retrieval.
-- Each row is one sliding-window chunk from a parent document.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    document_id     UUID            NOT NULL REFERENCES public.document_records(id) ON DELETE CASCADE,
    user_id         TEXT            NOT NULL,
    chunk_index     INTEGER         NOT NULL,          -- 0-based sequential order within the document
    content         TEXT            NOT NULL,           -- raw chunk text
    token_count     INTEGER         NOT NULL,
    page_number     INTEGER,                            -- originating page (PDF only; NULL for other types)
    embedding       vector(768),                        -- NOTE: dimension must match EMBEDDING_DIMENSIONS setting
    embedding_model TEXT            NOT NULL DEFAULT '', -- stored for future re-embedding migrations
    tsv_content     TSVECTOR        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,

    CONSTRAINT document_chunks_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON public.document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_user_id     ON public.document_chunks (user_id);
-- IVFFlat index for approximate nearest neighbour search (best for >1000 rows)
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding   ON public.document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- GIN index for full-text keyword search
CREATE INDEX IF NOT EXISTS idx_document_chunks_tsv         ON public.document_chunks USING GIN (tsv_content);


-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: match_document_chunks
-- Runs pgvector cosine-similarity nearest-neighbour search for a given user.
-- Called by retrieval.py for dense (semantic) retrieval.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding     vector(768),
    query_user_id       TEXT,
    match_count         INT     DEFAULT 8,
    filter_document_id  UUID    DEFAULT NULL
)
RETURNS TABLE (
    id              UUID,
    document_id     UUID,
    chunk_index     INT,
    content         TEXT,
    page_number     INT,
    similarity      FLOAT
)
LANGUAGE SQL STABLE
AS $$
    SELECT
        dc.id,
        dc.document_id,
        dc.chunk_index,
        dc.content,
        dc.page_number,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM public.document_chunks dc
    WHERE dc.user_id = query_user_id
      AND dc.embedding IS NOT NULL
      AND (filter_document_id IS NULL OR dc.document_id = filter_document_id)
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
$$;


-- ─────────────────────────────────────────────────────────────────────────────
-- RPC: search_document_chunks_fulltext
-- Runs PostgreSQL tsvector full-text keyword search for a given user.
-- Called by retrieval.py for sparse (keyword) retrieval.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION search_document_chunks_fulltext(
    query_text          TEXT,
    query_user_id       TEXT,
    match_count         INT     DEFAULT 8,
    filter_document_id  UUID    DEFAULT NULL
)
RETURNS TABLE (
    id              UUID,
    document_id     UUID,
    chunk_index     INT,
    content         TEXT,
    page_number     INT,
    rank            FLOAT
)
LANGUAGE SQL STABLE
AS $$
    SELECT
        dc.id,
        dc.document_id,
        dc.chunk_index,
        dc.content,
        dc.page_number,
        ts_rank(dc.tsv_content, plainto_tsquery('english', query_text))::FLOAT AS rank
    FROM public.document_chunks dc
    WHERE dc.user_id = query_user_id
      AND (filter_document_id IS NULL OR dc.document_id = filter_document_id)
      AND dc.tsv_content @@ plainto_tsquery('english', query_text)
    ORDER BY rank DESC
    LIMIT match_count;
$$;


-- ─────────────────────────────────────────────────────────────────────────────
-- Row Level Security (uncomment when Supabase Auth is live in Milestone 4)
-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER TABLE public.document_records ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.document_chunks  ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Users access own documents" ON public.document_records
--     FOR ALL USING (user_id = auth.uid()::text);
-- CREATE POLICY "Users access own chunks" ON public.document_chunks
--     FOR ALL USING (user_id = auth.uid()::text);
