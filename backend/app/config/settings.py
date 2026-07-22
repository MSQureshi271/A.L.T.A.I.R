"""
app/config.py  —  Centralised settings loaded from the .env file.

Usage:
    from app.config import settings
    print(settings.GEMINI_API_KEY)
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Gemini AI ────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""

    # ── Server ───────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True

    # ── CORS — comma-separated list of allowed origins ────────────────────────
    CORS_ORIGINS: str = "http://localhost,http://localhost:8080"
    CORS_ORIGINS_REGEX: str = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ── Google OAuth 2.0 (Workspace: Gmail + Calendar) ───────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Must be registered in Google Cloud Console → Credentials → OAuth 2.0
    # For Android Emulator testing: run `adb reverse tcp:8000 tcp:8000` so
    # localhost:8000 inside the emulator maps to host machine port 8000.
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # ── Webhook Push Settings (Phase 7) ──────────────────────────────────────
    WEBHOOK_BASE_URL: str = ""  # e.g. "https://xxxxxx.ngrok-free.app"
    GOOGLE_PUBSUB_TOPIC: str = ""  # e.g. "projects/my-project/topics/my-topic"

    # ── Supabase ─────────────────────────────────────────────────────────────
    # Get these from: Supabase Dashboard → Project Settings → API
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    # Service role key bypasses RLS — only used server-side to write tokens
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # ── Document Intelligence ─────────────────────────────────────────────────
    # Supabase Storage bucket name for raw document files.
    DOCUMENTS_BUCKET: str = "altair-documents"
    # Chunking parameters (in approximate tokens; 1 token ≈ 0.75 words).
    DOCUMENTS_CHUNK_SIZE_TOKENS: int = 512
    DOCUMENTS_CHUNK_OVERLAP_TOKENS: int = 64
    # Number of chunks returned per RAG retrieval call.
    DOCUMENTS_TOP_K_RETRIEVAL: int = 8
    # Minimum cosine similarity score to include a chunk in retrieval results.
    DOCUMENTS_MIN_SIMILARITY: float = 0.35

    # ── Embedding Provider ────────────────────────────────────────────────────
    # Provider selection: 'gemini' | 'openai' | 'cohere' (extend embedding.py).
    EMBEDDING_PROVIDER: str = "gemini"
    # Model identifier passed to the provider SDK. Change this to switch models.
    # Gemini default: "gemini-embedding-2"
    EMBEDDING_MODEL: str = "gemini-embedding-2"
    # Output vector dimensions. Must match the Supabase vector(N) column size.
    # Changing this requires a DB migration (ALTER TABLE + full re-embed).
    EMBEDDING_DIMENSIONS: int = 768

    # ── Upload Quotas (Tiered Architecture) ───────────────────────────────────
    # USER_TIER controls which limit is enforced at upload / attachment ingestion time.
    # Values: 'basic' | 'medium' | 'premium'
    # Set USER_TIER in .env to upgrade a user (Milestone 4: this will come from Supabase Auth).
    USER_TIER: str = "premium"            # default: no cap during development
    UPLOAD_QUOTA_MB_BASIC: int = 10       # 10 MB per file — Basic tier
    UPLOAD_QUOTA_MB_MEDIUM: int = 50      # 50 MB per file — Medium tier
    UPLOAD_QUOTA_MB_PREMIUM: int = 0      # 0 = unlimited — Premium tier

    @property
    def upload_limit_bytes(self) -> int:
        """Returns the per-file upload byte limit based on USER_TIER.
        Returns 0 for premium (no limit).
        """
        tier = self.USER_TIER.lower()
        if tier == "basic":
            return self.UPLOAD_QUOTA_MB_BASIC * 1024 * 1024
        if tier == "medium":
            return self.UPLOAD_QUOTA_MB_MEDIUM * 1024 * 1024
        return 0  # premium / unknown — no cap

    # ── Development ───────────────────────────────────────────────────────────
    # Hardcoded dev user UUID used until Supabase Auth is implemented in M4.
    # All tool calls and token lookups use this ID for now.
    DEV_USER_ID: str = "00000000-0000-0000-0000-000000000001"


# Single shared instance used everywhere in the app.
settings = Settings()
