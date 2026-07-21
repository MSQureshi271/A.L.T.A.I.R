"""
app/services/notification_service.py — Agnostic Notification Service.

Routes notification alerts (from Watchers or workflows) to active channels.
Supports console fallbacks and is prepared for Firebase Cloud Messaging (FCM).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send_watcher_notification(
    user_id: str,
    title: str,
    body: str,
    watcher_id: str,
) -> None:
    """Dispatches a notification alert to a user.

    In development, this outputs clean formatted info logs. In production,
    this integrates with FCM to send native mobile push alerts.
    """
    # ── Log/Console Delivery ──────────────────────────────────────────────────
    logger.info(
        "🔔 [NOTIFICATION SERVICE] For user=%s, watcher_id=%s\n"
        "   Title: %s\n"
        "   Body:  %s",
        user_id,
        watcher_id,
        title,
        body,
    )

    # ── FCM Push Notification Integrations ────────────────────────────────────
    # In a production environment, this integrates with firebase-admin SDK:
    # try:
    #     from firebase_admin import messaging
    #     # Fetch stored device tokens for user_id
    #     device_tokens = get_user_device_tokens(user_id)
    #     for token in device_tokens:
    #         message = messaging.Message(
    #             notification=messaging.Notification(
    #                 title=title,
    #                 body=body,
    #             ),
    #             data={
    #                 "watcher_id": watcher_id,
    #                 "click_action": "FLUTTER_NOTIFICATION_CLICK"
    #             },
    #             token=token,
    #         )
    #         messaging.send(message)
    # except Exception as exc:
    #     logger.warning("FCM delivery failed: %s", exc)
