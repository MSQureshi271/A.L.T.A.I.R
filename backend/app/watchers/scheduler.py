"""
app/agents/watcher_scheduler.py — Watchers Poller Event Ingestion Loop.

Periodically queries connector event sources, filters updates, checks for
deduplication hashes, and invokes the Watcher Execution Engine.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import logging
import time

from app.watchers.engine import execute_watcher_on_event
from app.config.settings import settings
from app.providers.google.calendar.event_source import CalendarEventSource
from app.providers.google.gmail.event_source import GmailEventSource
from app.repositories.db_client import db_load_items, db_store_item
from app.repositories.watcher_repository import (
    is_event_processed,
    load_watchers,
    log_watcher_history,
    mark_event_processed,
)

logger = logging.getLogger(__name__)

# Register available Event sources
_EVENT_SOURCES = [
    GmailEventSource(),
    CalendarEventSource(),
]

# Check interval (default 5 minutes, can be smaller in local development)
POLL_INTERVAL_SECONDS = 300


async def start_scheduler_loop() -> None:
    """Invoked in background via lifespan to query event sources periodically."""
    logger.info("Watcher Scheduler background task active.")
    # Add a short startup delay to let the FastAPI server initialize fully
    await asyncio.sleep(5)

    while True:
        try:
            user_id = settings.DEV_USER_ID
            await run_poll_cycle(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error occurred in watcher scheduler execution cycle")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def run_poll_cycle(user_id: str) -> None:
    """Ingest and route events for a specific user ID."""
    watchers = load_watchers(user_id)
    enabled_watchers = [w for w in watchers if w.get("enabled", True)]

    if not enabled_watchers:
        return

    # Map providers -> active watchers for user
    watchers_by_provider: dict[str, list[dict]] = {}
    for w in enabled_watchers:
        provider = w["trigger"]["provider"]
        watchers_by_provider.setdefault(provider, []).append(w)

    for source in _EVENT_SOURCES:
        provider = source.provider
        provider_watchers = watchers_by_provider.get(provider, [])
        if not provider_watchers:
            continue

        # Skip polling if push notifications/webhooks are active
        if provider == "gmail" and settings.GOOGLE_PUBSUB_TOPIC:
            logger.debug("Gmail push watch active. Skipping polling cycle to conserve quotas.")
            continue
        if provider == "calendar" and settings.WEBHOOK_BASE_URL:
            logger.debug("Calendar webhook active. Skipping polling cycle to conserve quotas.")
            continue

        # Get the timestamp checkpoint when we last checked this provider
        last_checked = _get_checkpoint(user_id, provider)
        run_start_time = datetime.now(timezone.utc)

        t_start = time.time()
        new_events = source.poll_events(user_id, last_checked)
        connector_latency = int((time.time() - t_start) * 1000)

        if not new_events:
            _save_checkpoint(user_id, provider, run_start_time)
            continue

        logger.info(
            "Ingested %d new event(s) for user=%s provider=%s",
            len(new_events),
            user_id,
            provider,
        )

        for event in new_events:
            # Deduplication Check
            if is_event_processed(user_id, event.id):
                continue

            for watcher in provider_watchers:
                try:
                    # Run logic matching and log metrics
                    res = execute_watcher_on_event(watcher, event)
                    res["connector_latency_ms"] = connector_latency
                    # Store update metrics in logging
                    log_watcher_history(user_id, res)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "Scheduler failed executing watcher=%s on event=%s",
                        watcher["id"],
                        event.id,
                    )

            # Record event processed registry hash
            mark_event_processed(user_id, event.id, provider, event.id)

        # Slide checkpoints window forward
        _save_checkpoint(user_id, provider, run_start_time)


# ── Persistence Checkpoints Helpers ──────────────────────────────────────────

def _get_checkpoint(user_id: str, provider: str) -> datetime:
    """Retrieve the datetime when this provider event source was last evaluated."""
    try:
        items = db_load_items("watcher_checkpoints", user_id)
        for item in items:
            if item.get("provider") == provider:
                return datetime.fromisoformat(item["last_checked"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read watcher checkpoint: %s", exc)

    # Defaults to 10 minutes ago
    return datetime.now(timezone.utc) - timedelta(minutes=10)


def _save_checkpoint(user_id: str, provider: str, checkpoint: datetime) -> None:
    """Save the checkpoint datetime to state cache."""
    item = {
        "user_id": user_id,
        "provider": provider,
        "last_checked": checkpoint.isoformat(),
    }
    try:
        db_store_item("watcher_checkpoints", item, ["user_id", "provider"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed storing checkpoint state: %s", exc)
