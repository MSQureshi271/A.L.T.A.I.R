"""
app/providers/google/gmail/watch.py — Gmail Push Watch Subscription management.
"""
from __future__ import annotations

import logging
from googleapiclient.discovery import build

from app.config.settings import settings
from app.providers.google.token_manager import get_google_credentials

logger = logging.getLogger(__name__)


def register_gmail_watch(user_id: str) -> dict | None:
    """Subscribes Gmail to Google Cloud Pub/Sub push notifications."""
    if not settings.GOOGLE_PUBSUB_TOPIC:
        logger.info("GOOGLE_PUBSUB_TOPIC not configured. Gmail push watch skipped (polling active).")
        return None

    try:
        creds = get_google_credentials(user_id)
        if not creds:
            logger.warning("No Google credentials found. Gmail watch skipped.")
            return None

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        body = {
            "topicName": settings.GOOGLE_PUBSUB_TOPIC,
            "labelIds": ["INBOX"],
        }
        res = service.users().watch(userId="me", body=body).execute()
        logger.info("Successfully registered Gmail watch subscription: %s", res)
        return res
    except Exception as exc:
        logger.error("Failed to register Gmail watch: %s", exc)
        return None


def stop_gmail_watch(user_id: str) -> None:
    """Stops the active Gmail watch subscription."""
    try:
        creds = get_google_credentials(user_id)
        if not creds:
            return
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        service.users().stop(userId="me").execute()
        logger.info("Successfully stopped Gmail watch subscription.")
    except Exception as exc:
        logger.error("Failed to stop Gmail watch: %s", exc)
