"""
app/tools/calendar_tools.py — Google Calendar tools exposed to Gemini.

get_calendar_events()          → Fetches real upcoming events from Google Calendar.
create_calendar_event()        → Unchanged: stages an event for human approval (HITL).
create_google_calendar_event() → Called by execute-action after user approval.
                                  NOT exposed to Gemini directly.
"""
from __future__ import annotations

import datetime
import logging

from googleapiclient.discovery import build

from app.config import settings
from app.database.token_manager import get_google_credentials

logger = logging.getLogger(__name__)


def _get_primary_timezone(service) -> str:
    """Helper to fetch the primary calendar's time zone setting dynamically."""
    try:
        primary_cal = service.calendars().get(calendarId="primary").execute()
        return primary_cal.get("timeZone", "UTC")
    except Exception:
        logger.warning("Failed to fetch primary calendar time zone, defaulting to UTC")
        return "UTC"


# ── Tools exposed to Gemini ───────────────────────────────────────────────────

def get_calendar_events(days_ahead: int = 3) -> str:
    """Retrieve the user's upcoming Google Calendar events.

    Args:
        days_ahead: How many days into the future to look (default 3, max 14).

    Returns:
        A plain-text list of upcoming events.
    """
    days_ahead = min(days_ahead, 14)
    user_id = settings.DEV_USER_ID

    try:
        creds = get_google_credentials(user_id)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        now = datetime.datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + datetime.timedelta(days=days_ahead)).isoformat() + "Z"

        # Fetch local timezone dynamically so Google converts datetime values to user's zone
        user_tz = _get_primary_timezone(service)

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=15,
                singleEvents=True,
                orderBy="startTime",
                timeZone=user_tz,
            )
            .execute()
        )

        events = events_result.get("items", [])
        if not events:
            return f"No events found in the next {days_ahead} day(s)."

        lines: list[str] = [f"[Google Calendar — next {days_ahead} day(s)]"]
        for event in events:
            start = event.get("start", {})
            start_str = start.get("dateTime", start.get("date", "Unknown"))

            # Parse datetime for a friendlier format
            try:
                if "T" in start_str:
                    dt = datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    formatted = dt.strftime("%a %b %d, %H:%M")
                else:
                    dt = datetime.date.fromisoformat(start_str)
                    formatted = dt.strftime("%a %b %d (all day)")
            except ValueError:
                formatted = start_str

            summary = event.get("summary", "(No title)")
            location = event.get("location", "")
            attendee_count = len(event.get("attendees", []))

            line = f"• {formatted} — {summary}"
            if location:
                line += f" @ {location}"
            if attendee_count > 0:
                line += f" ({attendee_count} attendee{'s' if attendee_count != 1 else ''})"
            lines.append(line)

        return "\n".join(lines)

    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch Google Calendar events")
        return f"Failed to read Calendar: {exc}"


def create_calendar_event(
    title: str,
    date: str,
    time: str,
    duration_minutes: int = 60,
    attendees: str = "",
) -> dict:
    """Stage a new calendar event for the user to review before creating it.

    ALWAYS use this tool instead of creating an event directly.  The user
    must approve before the event is added to the calendar.

    Args:
        title:            The event title / meeting name.
        date:             The date string in YYYY-MM-DD format.
        time:             The start time string in HH:MM (24h) format.
        duration_minutes: Duration of the meeting in minutes (default 60).
        attendees:        Comma-separated list of attendee email addresses.

    Returns:
        A dict with type='approval_required' and the staged event data.
    """
    return {
        "type": "approval_required",
        "action": "create_calendar_event",
        "data": {
            "title": title,
            "date": date,
            "time": time,
            "duration_minutes": duration_minutes,
            "attendees": [a.strip() for a in attendees.split(",") if a.strip()],
        },
    }


# ── Called by execute-action (NOT exposed to Gemini) ─────────────────────────

def create_google_calendar_event(
    title: str,
    date: str,
    time: str,
    duration_minutes: int,
    attendees: list[str],
    user_id: str,
) -> str:
    """
    Create a real Google Calendar event after user approval.

    This function is NOT a Gemini tool — it is called directly by the
    /agent/execute-action endpoint after user approval.

    Args:
        title:            Event title.
        date:             Date in YYYY-MM-DD format.
        time:             Start time in HH:MM (24h) format.
        duration_minutes: Duration in minutes.
        attendees:        List of attendee email addresses.
        user_id:          User whose Google Calendar to write to.

    Returns:
        A confirmation message string.
    """
    creds = get_google_credentials(user_id)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    # Build start/end ISO datetimes without offsets (local datetime representation)
    start_dt_str = f"{date}T{time}:00"
    start_dt = datetime.datetime.fromisoformat(start_dt_str)
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

    # Fetch local timezone dynamically
    user_tz = _get_primary_timezone(service)

    # Google interprets start_dt in the context of user_tz timezone instead of UTC
    event_body: dict = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": user_tz},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": user_tz},
    }

    if attendees:
        event_body["attendees"] = [{"email": email} for email in attendees]

    created = (
        service.events()
        .insert(calendarId="primary", body=event_body, sendUpdates="all")
        .execute()
    )

    event_link = created.get("htmlLink", "")
    logger.info("Google Calendar event created: %s", event_link)
    return (
        f"✅ Calendar event '{title}' created on {date} at {time} "
        f"({duration_minutes} min). "
        + (f"Invites sent to {', '.join(attendees)}. " if attendees else "")
        + (f"View: {event_link}" if event_link else "")
    )

