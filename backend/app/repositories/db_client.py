"""
app/database/db_client.py — Token storage layer.

Strategy:
  • If SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are configured → use Supabase.
  • Otherwise → fall back to a local JSON file (.token_cache.json) so dev work
    can continue before the Supabase project is fully set up.

Supabase SQL (run once in your Supabase Dashboard → SQL Editor):
─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id   TEXT        NOT NULL,
    provider  TEXT        NOT NULL,   -- 'google' | 'microsoft'
    token_data JSONB      NOT NULL,   -- full token payload
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, provider)
);

-- Row Level Security (enable after M4 when real auth is added)
-- ALTER TABLE user_credentials ENABLE ROW LEVEL SECURITY;
─────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Path to the local fallback token cache file (inside backend/ directory)
_CACHE_FILE = Path(__file__).parents[3] / ".token_cache.json"


# ── Supabase client (lazy-initialised) ───────────────────────────────────────

_supabase_client = None


def _get_supabase():
    """Return a Supabase client, or None if Supabase is not configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        logger.warning(
            "Supabase not configured — using local .token_cache.json as token store. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env to enable Supabase."
        )
        return None

    try:
        from supabase import create_client  # noqa: PLC0415
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
        logger.info("Supabase client initialised successfully.")
        return _supabase_client
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create Supabase client: %s", exc)
        return None


# ── Local file fallback ───────────────────────────────────────────────────────

def _read_cache() -> dict:
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _write_cache(data: dict) -> None:
    _CACHE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def store_tokens(user_id: str, provider: str, token_data: dict[str, Any]) -> None:
    """Persist OAuth tokens for *user_id* and *provider*."""
    sb = _get_supabase()

    if sb:
        sb.table("user_credentials").upsert(
            {
                "user_id": user_id,
                "provider": provider,
                "token_data": token_data,
            },
            on_conflict="user_id,provider",
        ).execute()
        logger.info("Tokens stored in Supabase for user=%s provider=%s", user_id, provider)
    else:
        cache = _read_cache()
        cache.setdefault(user_id, {})[provider] = token_data
        _write_cache(cache)
        logger.info(
            "Tokens stored in local cache for user=%s provider=%s", user_id, provider
        )


def load_tokens(user_id: str, provider: str) -> dict[str, Any] | None:
    """Load OAuth tokens.  Returns None if not found."""
    sb = _get_supabase()

    if sb:
        result = (
            sb.table("user_credentials")
            .select("token_data")
            .eq("user_id", user_id)
            .eq("provider", provider)
            .maybe_single()
            .execute()
        )
        if result.data:
            return result.data["token_data"]
        return None
    else:
        cache = _read_cache()
        return cache.get(user_id, {}).get(provider)


def is_connected(user_id: str, provider: str) -> bool:
    """Return True if tokens exist for this user + provider."""
    tokens = load_tokens(user_id, provider)
    return tokens is not None and bool(tokens.get("refresh_token"))


# ── Generic Memory Database Layer (Supabase + Local Cache Fallback) ──────────

_MEM_CACHE_FILE = Path(__file__).parents[3] / ".memory_cache.json"


def _read_mem_cache() -> dict:
    if not _MEM_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_MEM_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _write_mem_cache(data: dict) -> None:
    _MEM_CACHE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def db_store_item(table: str, item: dict[str, Any], conflict_fields: list[str]) -> None:
    """Store/upsert a record in Supabase or fall back to local JSON cache."""
    sb = _get_supabase()
    user_id = item.get("user_id", "DEV_USER_ID")

    if sb:
        try:
            on_conflict = ",".join(conflict_fields)
            sb.table(table).upsert(item, on_conflict=on_conflict).execute()
            logger.info("Stored record in Supabase table=%s keys=%s", table, conflict_fields)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Supabase store failed for table=%s", table)
            raise RuntimeError(f"Database error: {exc}") from exc
    else:
        cache = _read_mem_cache()
        user_cache = cache.setdefault(user_id, {})
        table_cache = user_cache.setdefault(table, [])

        # Check for matching uniqueness to overwrite/update
        updated = False
        for i, existing in enumerate(table_cache):
            # If all conflict fields match, replace it
            match = True
            for field in conflict_fields:
                if existing.get(field) != item.get(field):
                    match = False
                    break
            if match:
                table_cache[i] = item
                updated = True
                break

        if not updated:
            table_cache.append(item)

        _write_mem_cache(cache)
        logger.info("Stored record in local memory cache table=%s", table)


def db_load_items(table: str, user_id: str) -> list[dict[str, Any]]:
    """Retrieve all records for a user in a given table."""
    sb = _get_supabase()

    if sb:
        try:
            result = sb.table(table).select("*").eq("user_id", user_id).execute()
            return result.data or []
        except Exception as exc:  # noqa: BLE001
            logger.exception("Supabase load failed for table=%s", table)
            return []
    else:
        cache = _read_mem_cache()
        return cache.get(user_id, {}).get(table, [])


def db_delete_item(table: str, user_id: str, criteria: dict[str, Any]) -> None:
    """Delete matching records from Supabase or local cache."""
    sb = _get_supabase()

    if sb:
        try:
            q = sb.table(table).delete().eq("user_id", user_id)
            for k, v in criteria.items():
                q = q.eq(k, v)
            q.execute()
            logger.info("Deleted record in Supabase table=%s matching=%s", table, criteria)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Supabase delete failed for table=%s", table)
            raise RuntimeError(f"Database error: {exc}") from exc
    else:
        cache = _read_mem_cache()
        user_cache = cache.get(user_id, {})
        table_cache = user_cache.get(table, [])

        # Filter out items that match ALL deletion criteria
        new_table_cache = []
        for item in table_cache:
            match = True
            for k, v in criteria.items():
                if item.get(k) != v:
                    match = False
                    break
            if not match:
                new_table_cache.append(item)

        user_cache[table] = new_table_cache
        _write_mem_cache(cache)
        logger.info("Deleted record in local cache table=%s matching=%s", table, criteria)

