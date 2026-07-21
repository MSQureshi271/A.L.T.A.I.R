"""
app/providers/google/calendar/watch.py — Google Calendar Push Watch Sync management.
"""
from __future__ import annotations

import logging
import uuid
from googleapiclient.discovery import build

from app.config.settings import settings
from app.providers.google.token_manager import get_google_credentials

logger = logging.getLogger(__name__)


def register_calendar_watch(user_id: str) -> dict | None:
    """Subscribes to primary Google Calendar events update notifications."""
    if not settings.WEBHOOK_BASE_URL:
        logger.info("WEBHOOK_BASE_URL not configured. Calendar push watch skipped (polling active).")
        return None

    try:
        creds = get_google_credentials(user_id)
        if not creds:
            logger.warning("No Google credentials found. Calendar watch skipped.")
            return None

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        channel_id = str(uuid.uuid4())
        webhook_url = f"{settings.WEBHOOK_BASE_URL.rstrip('/')}/webhook/google/calendar"

        body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
        }
        res = service.events().watch(calendarId="primary", body=body).execute()
        logger.info("Successfully registered Calendar watch subscription: %s", res)
        return res
    except Exception as exc:
        logger.error("Failed to register Calendar watch: %s", exc)
        return None


def stop_calendar_watch(user_id: str, channel_id: str, resource_id: str) -> None:
    """Stops the active Google Calendar watch subscription channel."""
    try:
        creds = get_google_credentials(user_id)
        if not creds:
            return
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        body = {
            "id": channel_id,
            "resourceId": resource_id,
        }
        service.channels().stop(body=body).execute()
        logger.info("Successfully stopped Calendar watch subscription channel: %s", channel_id)
    except Exception as exc:
        logger.error("Failed to stop Calendar watch channel: %s", exc)
