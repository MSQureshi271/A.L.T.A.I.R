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

    # ── Supabase ─────────────────────────────────────────────────────────────
    # Get these from: Supabase Dashboard → Project Settings → API
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    # Service role key bypasses RLS — only used server-side to write tokens
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # ── Development ───────────────────────────────────────────────────────────
    # Hardcoded dev user UUID used until Supabase Auth is implemented in M4.
    # All tool calls and token lookups use this ID for now.
    DEV_USER_ID: str = "00000000-0000-0000-0000-000000000001"


# Single shared instance used everywhere in the app.
settings = Settings()
