-- ══════════════════════════════════════════════════════════════════════════════
-- A.L.T.A.I.R. Document Intelligence — Phase 2 Supabase Migration
-- Run this in Supabase Dashboard → SQL Editor AFTER the Phase 1 migration.
-- ══════════════════════════════════════════════════════════════════════════════


-- ─────────────────────────────────────────────────────────────────────────────
-- Add Gemini Files API tracking columns to document_records.
-- These are used to cache the Gemini Files API upload URI so that
-- get_document_summary() can use full-context native generation without
-- re-uploading on every call (files expire after 48h on Google's side).
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.document_records
    ADD COLUMN IF NOT EXISTS gemini_file_uri      TEXT         NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gemini_file_name     TEXT         NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gemini_file_expiry_at TIMESTAMPTZ;


-- Optional: index for quick lookup of expired gemini file refs (cleanup job).
CREATE INDEX IF NOT EXISTS idx_document_records_gemini_expiry
    ON public.document_records (gemini_file_expiry_at)
    WHERE gemini_file_uri != '';
