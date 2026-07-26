# 📓 Notion Integration — Executive Agent

> A comprehensive, architecture-aware plan for adding Notion as a first-class integration to Executive Agent.
> Every file path, pattern, and convention below mirrors what is already live in the codebase.

---

## 🗺️ Table of Contents

1. [Why Notion?](#1-why-notion)
2. [How Notion Fits the Existing Architecture](#2-how-notion-fits-the-existing-architecture)
3. [Notion API Primer](#3-notion-api-primer)
4. [OAuth 2.0 Setup — Notion Developer Portal](#4-oauth-20-setup--notion-developer-portal)
5. [Backend Implementation — Step by Step](#5-backend-implementation--step-by-step)
6. [AI Agent Tools — What Gemini Can Do](#6-ai-agent-tools--what-gemini-can-do)
7. [Human-in-the-Loop (HITL) for Notion Write Actions](#7-human-in-the-loop-hitl-for-notion-write-actions)
8. [Flutter Frontend Changes](#8-flutter-frontend-changes)
9. [Database Schema Changes](#9-database-schema-changes)
10. [Environment Variables](#10-environment-variables)
11. [File Changelist (Every File Touched)](#11-file-changelist-every-file-touched)
12. [Voice Command Examples](#12-voice-command-examples)
13. [Testing Checklist](#13-testing-checklist)
14. [Future Roadmap](#14-future-roadmap)

---

## 1. Why Notion?

Business owners use Notion as their **second brain** — meeting notes, project wikis, CRM databases, SOPs, and personal journals all live there.  
Adding Notion to Executive Agent means the user can say things like:

> *"Add today's meeting summary to my Team Updates Notion page."*  
> *"Search my Notion wiki for our refund policy."*  
> *"Create a new task in my Project Tracker database for the investor deck."*  
> *"Show me all tasks assigned to me that are due this week."*

Without Notion, the agent is blind to a huge part of the user's knowledge base.  
With Notion, the agent can **read context** from the user's wiki, **create records** in databases, and **append live notes** to pages — all from a voice command.

---

## 2. How Notion Fits the Existing Architecture

The existing architecture follows a clean, layered pattern:

```
voice command
     │
     ▼
coordinator.py  (Gemini tool-calling loop)
     │
     ├── search_web()          → capabilities/search/
     ├── stage_email()         → providers/google/gmail/api.py
     ├── read_emails()         → providers/google/gmail/api.py
     ├── get/create_calendar() → providers/google/calendar/api.py
     └── search/list/get_doc() → capabilities/documents/
```

Notion slots in as **a new provider** (`providers/notion/`) alongside Google, and its tools are registered in the **same TOOLS list** inside `coordinator.py`.

```
coordinator.py
     │
     └── [NEW] Notion tools → providers/notion/api.py
```

This keeps the existing agent loop, HITL approval system, and SSE streaming **completely unchanged**. You are adding a new spoke to the wheel, not redesigning the wheel.

---

## 3. Notion API Primer

### Core Concepts

| Notion Concept | What It Is | API Object |
|---|---|---|
| **Page** | Any document, note, or wiki article | `page` |
| **Database** | A table / board / gallery of structured entries | `database` |
| **Database Row** | A single record inside a database (is itself a page) | `page` inside a `database` |
| **Block** | A unit of content on a page (paragraph, heading, todo, etc.) | `block` |
| **Property** | A typed column on a database (text, date, select, person, etc.) | part of `page.properties` |

### Key API Endpoints Used

| Action | Endpoint |
|---|---|
| Search pages & databases | `POST /search` |
| Read page metadata | `GET /pages/{page_id}` |
| Read page blocks (content) | `GET /blocks/{block_id}/children` |
| Append content to a page | `PATCH /blocks/{block_id}/children` |
| Create a database row | `POST /pages` (with `parent.database_id`) |
| Query a database | `POST /databases/{database_id}/query` |
| Update a page property | `PATCH /pages/{page_id}` |
| Create a new page | `POST /pages` (with `parent.page_id`) |

### Authentication

Notion uses **OAuth 2.0** with a workspace-level access token.  
The token is a single long-lived bearer token (no refresh token — they do not expire unless revoked).

Base URL: `https://api.notion.com/v1`  
Required header: `Authorization: Bearer {access_token}`  
Required header: `Notion-Version: 2022-06-28`

---

## 4. OAuth 2.0 Setup — Notion Developer Portal

### Step 1 — Create an Integration

1. Go to [https://www.notion.com/my-integrations](https://www.notion.com/my-integrations)
2. Click **"New integration"**.
3. Fill in:
   - **Name**: Executive Agent
   - **Logo**: (optional — upload the app icon)
   - **Associated workspace**: your workspace
4. Under **Capabilities**, check:
   - ✅ Read content
   - ✅ Update content
   - ✅ Insert content
   - ✅ Read user information (for assigning tasks)
5. Click **Submit**.

### Step 2 — Configure for Public OAuth (Multi-user)

> [!IMPORTANT]
> By default, Notion integrations are "internal" (single workspace, no OAuth flow).
> For a user-facing app, you must switch to "Public" mode so any Notion user can connect.

1. In your integration settings, click **"Public integration"** and fill in:
   - **Company name**: Your company
   - **Website**: Your app's website
   - **Privacy Policy URL**: Required by Notion
   - **Redirect URIs**: `http://localhost:8000/auth/notion/callback`  
     *(add your production URL too when deploying)*
2. Copy:
   - `OAuth client ID` → `NOTION_CLIENT_ID`
   - `OAuth client secret` → `NOTION_CLIENT_SECRET`

### Step 3 — Notion OAuth Flow

The OAuth flow is identical in structure to the existing Google flow:

```
Flutter → launches /auth/notion/login in browser
       → backend redirects to Notion's consent page
       → user selects which pages/databases to share
       → Notion redirects to /auth/notion/callback?code=...
       → backend exchanges code for access_token
       → token stored in db_client.py under provider='notion'
       → Flutter polls /auth/notion/status to confirm
```

**Notion OAuth endpoints:**

| Step | URL |
|---|---|
| Authorization | `https://api.notion.com/v1/oauth/authorize` |
| Token exchange | `https://api.notion.com/v1/oauth/token` (POST, Basic Auth) |

**Authorization URL parameters:**
```
client_id=NOTION_CLIENT_ID
redirect_uri=http://localhost:8000/auth/notion/callback
response_type=code
owner=user
state={csrf_state_value}
```

**Token exchange (POST to `/v1/oauth/token`):**
- Authentication: HTTP Basic Auth (`client_id:client_secret`, base64 encoded)
- Body: `{ "grant_type": "authorization_code", "code": "...", "redirect_uri": "..." }`
- Response contains: `access_token`, `workspace_name`, `workspace_icon`, `bot_id`

> [!NOTE]
> Unlike Google, Notion access tokens **do not expire** and there is no refresh token.
> Store the `access_token` in the `token_data` JSONB column in Supabase using the existing `store_tokens()` function with `provider='notion'`.

---

## 5. Backend Implementation — Step by Step

### 5.1 Install the Notion SDK

```bash
cd backend
pip install notion-client
```

Add to `requirements.txt`:
```
notion-client>=2.2.0
```

The `notion-client` package is the official Python SDK maintained by Notion.

---

### 5.2 New Directory: `backend/app/providers/notion/`

This mirrors the structure of `providers/google/`:

```
backend/app/providers/notion/
├── __init__.py
├── notion_auth.py      # OAuth URL builder & token exchange
├── notion_router.py    # FastAPI router: /auth/notion/*
└── api.py              # Notion tools exposed to Gemini
```

---

### 5.3 `notion_auth.py` — OAuth Helpers

```python
"""
app/providers/notion/notion_auth.py — Notion OAuth helpers.

Mirrors: app/providers/google/google_oauth.py
"""
from __future__ import annotations

import base64
import secrets
import httpx

from app.config.settings import settings


def get_notion_authorization_url() -> tuple[str, str]:
    """Return (authorization_url, state). state is used for CSRF protection."""
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.NOTION_CLIENT_ID,
        "redirect_uri": settings.NOTION_REDIRECT_URI,
        "response_type": "code",
        "owner": "user",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://api.notion.com/v1/oauth/authorize?{query}"
    return url, state


def exchange_notion_code(code: str) -> dict:
    """Exchange an authorization code for a Notion access token.

    Returns the full token payload from Notion (contains access_token,
    workspace_name, workspace_id, workspace_icon, bot_id).
    """
    credentials = base64.b64encode(
        f"{settings.NOTION_CLIENT_ID}:{settings.NOTION_CLIENT_SECRET}".encode()
    ).decode()

    response = httpx.post(
        "https://api.notion.com/v1/oauth/token",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.NOTION_REDIRECT_URI,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
```

---

### 5.4 `notion_router.py` — FastAPI Auth Endpoints

```python
"""
app/providers/notion/notion_router.py — FastAPI OAuth router for Notion.

Endpoints:
  GET /auth/notion/login      → Redirect to Notion consent page
  GET /auth/notion/callback   → Handle Notion redirect, store token
  GET /auth/notion/status     → Check if Notion is connected
  GET /auth/notion/disconnect → Clear stored Notion token
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.providers.notion.notion_auth import (
    get_notion_authorization_url,
    exchange_notion_code,
)
from app.repositories.db_client import store_tokens, is_connected, load_tokens, delete_tokens
from app.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])

_pending_states: dict[str, bool] = {}  # state -> True (placeholder)


@router.get("/notion/login")
async def notion_login() -> RedirectResponse:
    auth_url, state = get_notion_authorization_url()
    _pending_states[state] = True
    return RedirectResponse(url=auth_url)


@router.get("/notion/callback")
async def notion_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None
) -> HTMLResponse:
    if error:
        return HTMLResponse(
            content=_notion_html_page("Access Denied", f"Notion auth denied: {error}", False)
        )
    if not code or not state or state not in _pending_states:
        return HTMLResponse(
            content=_notion_html_page("Invalid Request", "Missing or invalid parameters.", False),
            status_code=400
        )
    _pending_states.pop(state, None)
    try:
        token_data = exchange_notion_code(code)
        store_tokens(user_id=settings.DEV_USER_ID, provider="notion", token_data=token_data)
        workspace = token_data.get("workspace_name", "your workspace")
        return HTMLResponse(
            content=_notion_html_page(
                "Connected!",
                f"Notion ({workspace}) connected. You may close this tab.",
                True
            )
        )
    except Exception as exc:
        logger.error("Notion token exchange failed: %s", exc)
        return HTMLResponse(
            content=_notion_html_page("Error", f"Token exchange failed: {exc}", False),
            status_code=500
        )


@router.get("/notion/status")
async def notion_status() -> dict:
    connected = is_connected(user_id=settings.DEV_USER_ID, provider="notion")
    if not connected:
        return {"connected": False}
    tokens = load_tokens(user_id=settings.DEV_USER_ID, provider="notion")
    return {
        "connected": True,
        "workspace_name": tokens.get("workspace_name", ""),
        "workspace_icon": tokens.get("workspace_icon", ""),
        "bot_id": tokens.get("bot_id", ""),
    }


@router.get("/notion/disconnect")
async def notion_disconnect() -> dict:
    delete_tokens(user_id=settings.DEV_USER_ID, provider="notion")
    return {"disconnected": True}


def _notion_html_page(title: str, message: str, success: bool) -> str:
    color = "#38B000" if success else "#E63946"
    icon = "✅" if success else "❌"
    return (
        f'<!DOCTYPE html><html><body style="font-family:sans-serif;background:#0d0d0d;'
        f'color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">'
        f'<div style="text-align:center;"><h1 style="color:{color};">{icon} {title}</h1>'
        f'<p>{message}</p></div></body></html>'
    )
```

---

### 5.5 `api.py` — Notion Tools (Gemini-Callable)

This is the most important file. Every function here will be registered in `TOOLS` and callable by Gemini's tool-calling mechanism.

```python
"""
app/providers/notion/api.py — Notion tools exposed to Gemini.

Tool contract (same rules as document_tools.py):
  • Docstrings must be precise — Gemini uses them to decide WHEN to call each tool.
  • Return type is str for read tools, dict for HITL staging tools.
  • Never raise exceptions — catch internally and return a user-friendly error string.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from notion_client import Client

from app.config.settings import settings
from app.repositories.db_client import load_tokens

logger = logging.getLogger(__name__)


def _get_notion_client() -> Client | None:
    """Return an authenticated Notion client, or None if not connected."""
    tokens = load_tokens(user_id=settings.DEV_USER_ID, provider="notion")
    if not tokens or not tokens.get("access_token"):
        return None
    return Client(auth=tokens["access_token"])


def _extract_plain_text(rich_text: list[dict]) -> str:
    """Extract plain text string from a Notion rich_text array."""
    return "".join(part.get("plain_text", "") for part in rich_text)


def _blocks_to_markdown(blocks: list[dict]) -> str:
    """Convert Notion blocks to a readable plain-text/markdown representation."""
    lines = []
    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype, {})
        rich = content.get("rich_text", [])
        text = _extract_plain_text(rich)

        if btype == "heading_1":
            lines.append(f"# {text}")
        elif btype == "heading_2":
            lines.append(f"## {text}")
        elif btype == "heading_3":
            lines.append(f"### {text}")
        elif btype == "bulleted_list_item":
            lines.append(f"• {text}")
        elif btype == "numbered_list_item":
            lines.append(f"1. {text}")
        elif btype == "to_do":
            checked = content.get("checked", False)
            mark = "✅" if checked else "☐"
            lines.append(f"{mark} {text}")
        elif btype == "quote":
            lines.append(f"> {text}")
        elif btype == "code":
            lang = content.get("language", "")
            lines.append(f"```{lang}\n{text}\n```")
        elif btype == "divider":
            lines.append("---")
        elif btype == "paragraph":
            lines.append(text)
        elif btype == "toggle":
            lines.append(f"▶ {text}")
        elif btype == "child_page":
            lines.append(f"[Sub-page: {content.get('title', 'Untitled')}]")
        elif btype == "image":
            caption = _extract_plain_text(content.get("caption", []))
            lines.append(f"[Image: {caption or 'no caption'}]")
    return "\n".join(lines)


def _content_to_blocks(content: str) -> list[dict]:
    """Convert simple markdown-like text into Notion API block objects."""
    blocks = []
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]}})
        elif stripped.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": [{"type": "text", "text": {"content": stripped[3:]}}]}})
        elif stripped.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": [{"type": "text", "text": {"content": stripped[4:]}}]}})
        elif stripped.startswith(("• ", "- ", "* ")):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]}})
        elif stripped.startswith("[ ] ") or stripped.startswith("☐ "):
            offset = 4 if stripped.startswith("[ ]") else 2
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": [{"type": "text", "text": {"content": stripped[offset:]}}], "checked": False}})
        elif stripped.startswith("[x] ") or stripped.startswith("✅ "):
            offset = 4 if stripped.startswith("[x]") else 3
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": [{"type": "text", "text": {"content": stripped[offset:]}}], "checked": True}})
        elif stripped.startswith("> "):
            blocks.append({"object": "block", "type": "quote",
                           "quote": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": [{"type": "text", "text": {"content": stripped}}]}})
    return blocks


def _build_notion_properties(properties: dict) -> dict:
    """
    Convert a simple {name: value} dict into Notion property format.

    Heuristic type detection:
      - value is bool          → checkbox
      - value is YYYY-MM-DD    → date
      - key is 'Name'/'title'  → title
      - otherwise              → rich_text (string)
    """
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    result = {}
    for name, value in properties.items():
        if isinstance(value, bool):
            result[name] = {"checkbox": value}
        elif isinstance(value, str) and date_pattern.match(value):
            result[name] = {"date": {"start": value}}
        elif name.lower() in ("name", "title"):
            result[name] = {"title": [{"type": "text", "text": {"content": str(value)}}]}
        else:
            result[name] = {"rich_text": [{"type": "text", "text": {"content": str(value)}}]}
    return result


# ── READ TOOLS ────────────────────────────────────────────────────────────────

def search_notion(query: str) -> str:
    """Search across all Notion pages and databases the user has shared with the integration.

    Use this whenever the user asks to find something in Notion — a document,
    a project page, a database, meeting notes, or any piece of content.
    Returns a list of matching pages/databases with their titles and URLs.

    Args:
        query: The search term or phrase to look for across all Notion content.

    Returns:
        A formatted list of matching Notion pages and databases, or a message
        indicating nothing was found.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected. Please go to Connectors and link your Notion account."
    try:
        results = client.search(query=query, page_size=10).get("results", [])
        if not results:
            return f"No Notion pages or databases found matching '{query}'."

        lines = [f"Found {len(results)} result(s) in Notion for '{query}':\n"]
        for item in results:
            obj_type = item.get("object", "")
            if obj_type == "page":
                raw_title = (
                    item.get("properties", {}).get("title", {}).get("title", [])
                    or item.get("properties", {}).get("Name", {}).get("title", [])
                )
                title = _extract_plain_text(raw_title) or "Untitled"
            elif obj_type == "database":
                title = _extract_plain_text(item.get("title", [])) or "Untitled Database"
            else:
                title = "Untitled"
            url = item.get("url", "")
            icon = "📄" if obj_type == "page" else "🗄️"
            lines.append(f"{icon} [{obj_type.capitalize()}] {title}\n   URL: {url}\n   ID: {item['id']}")
        return "\n".join(lines)
    except Exception as exc:
        logger.error("search_notion error: %s", exc)
        return f"Failed to search Notion: {exc}"


def read_notion_page(page_id: str) -> str:
    """Read the full content of a specific Notion page.

    Use this when the user wants to know what's on a specific Notion page,
    or when you have already identified the page_id from a previous search_notion call.
    Returns the page title and all its block content in a readable format.

    Args:
        page_id: The unique Notion page ID (obtained from search_notion results).

    Returns:
        The page title and full text content of the page, formatted for readability.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        page = client.pages.retrieve(page_id=page_id)
        title_prop = (
            page.get("properties", {}).get("title")
            or page.get("properties", {}).get("Name")
            or {}
        )
        title_list = title_prop.get("title", []) or title_prop.get("rich_text", [])
        title = _extract_plain_text(title_list) or "Untitled"

        blocks_response = client.blocks.children.list(block_id=page_id, page_size=100)
        blocks = blocks_response.get("results", [])
        content = _blocks_to_markdown(blocks)
        return f"# {title}\n\n{content}" if content else f"# {title}\n\n(This page has no text content.)"
    except Exception as exc:
        logger.error("read_notion_page error: %s", exc)
        return f"Failed to read Notion page: {exc}"


def query_notion_database(database_id: str, filter_description: str | None = None) -> str:
    """Query a Notion database and return its entries.

    Use this when the user wants to see records from a Notion database, such as
    a task tracker, CRM, project list, or any structured table.

    Args:
        database_id:        The unique ID of the Notion database (from search_notion or list_notion_databases).
        filter_description: Optional text description of what to filter by, e.g. 'Status = In Progress'.
                            This is a hint — for complex filters, perform a follow-up call.

    Returns:
        A formatted table of database entries showing all key properties.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        response = client.databases.query(database_id=database_id, page_size=20)
        rows = response.get("results", [])
        if not rows:
            return "The database is empty or no records match your query."

        lines = [f"Found {len(rows)} record(s):\n"]
        for row in rows:
            props = row.get("properties", {})
            row_lines = []
            for prop_name, prop_val in props.items():
                ptype = prop_val.get("type", "")
                if ptype == "title":
                    val = _extract_plain_text(prop_val.get("title", []))
                elif ptype == "rich_text":
                    val = _extract_plain_text(prop_val.get("rich_text", []))
                elif ptype == "select":
                    val = (prop_val.get("select") or {}).get("name", "—")
                elif ptype == "multi_select":
                    val = ", ".join(s["name"] for s in prop_val.get("multi_select", []))
                elif ptype == "status":
                    val = (prop_val.get("status") or {}).get("name", "—")
                elif ptype == "date":
                    date_obj = prop_val.get("date") or {}
                    val = date_obj.get("start", "—")
                elif ptype == "checkbox":
                    val = "✅" if prop_val.get("checkbox") else "☐"
                elif ptype == "people":
                    val = ", ".join(p.get("name", "") for p in prop_val.get("people", []))
                elif ptype == "url":
                    val = prop_val.get("url", "—")
                elif ptype == "email":
                    val = prop_val.get("email", "—")
                elif ptype == "number":
                    val = str(prop_val.get("number", "—"))
                else:
                    val = "(unsupported type)"
                if val and val not in ("—", ""):
                    row_lines.append(f"  {prop_name}: {val}")
            lines.append("\n".join(row_lines))
            lines.append("---")
        return "\n".join(lines)
    except Exception as exc:
        logger.error("query_notion_database error: %s", exc)
        return f"Failed to query Notion database: {exc}"


def list_notion_databases() -> str:
    """List all Notion databases accessible to the integration.

    Use this when the user asks to see their Notion databases, wants to know
    which trackers or tables are available, or before querying a database
    whose ID you do not yet know.

    Returns:
        A formatted list of database names and their IDs.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        results = client.search(
            filter={"value": "database", "property": "object"}, page_size=20
        ).get("results", [])
        if not results:
            return (
                "No Notion databases found. Make sure the integration has been "
                "granted access to at least one database in your Notion workspace."
            )
        lines = [f"Found {len(results)} database(s):\n"]
        for db in results:
            title = _extract_plain_text(db.get("title", [])) or "Untitled"
            lines.append(f"🗄️  {title}\n   ID: {db['id']}\n   URL: {db.get('url', '')}")
        return "\n".join(lines)
    except Exception as exc:
        logger.error("list_notion_databases error: %s", exc)
        return f"Failed to list Notion databases: {exc}"


# ── STAGING (HITL) TOOLS ──────────────────────────────────────────────────────

def stage_notion_page(
    parent_page_id: str,
    title: str,
    content: str,
) -> dict:
    """Stage a new Notion page for user review before creating it.

    ALWAYS use this tool instead of creating a page directly. The user will
    be shown the page draft and must explicitly approve it before it is created.

    Args:
        parent_page_id: The ID of the Notion page under which the new page will live.
        title:          The title for the new page.
        content:        The full text body of the new page (markdown-like formatting supported).

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "create_notion_page",
        "data": {
            "parent_page_id": parent_page_id,
            "title": title,
            "content": content,
        },
    }


def stage_notion_database_entry(
    database_id: str,
    properties: dict,
    content: str | None = None,
) -> dict:
    """Stage a new database entry (row) in a Notion database for user review before creating it.

    ALWAYS use this tool instead of writing directly to the database. The user will
    be shown the record draft and must approve before it is saved.

    Args:
        database_id: The ID of the target Notion database.
        properties:  A dict mapping property names to their values.
                     Title example:   {"Name": "My Task"}
                     Select example:  {"Status": "In Progress"}
                     Date example:    {"Due Date": "2026-08-15"}
                     Checkbox:        {"Done": False}
        content:     Optional body text to add to the entry page content.

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "create_notion_database_entry",
        "data": {
            "database_id": database_id,
            "properties": properties,
            "content": content,
        },
    }


def stage_notion_append(
    page_id: str,
    content: str,
) -> dict:
    """Stage an append operation — adding content to the bottom of an existing Notion page.

    ALWAYS use this tool to add notes, summaries, or bullet points to an existing page.
    The user will review the content before it is appended.

    Args:
        page_id: The ID of the Notion page to append content to.
        content: The text to add at the bottom of the page.
                 Supports: ## headings, • bullets, [ ] checkboxes, > quotes.

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "append_notion_page",
        "data": {
            "page_id": page_id,
            "content": content,
        },
    }
```

---

### 5.6 Execution Layer — `main.py` `/agent/execute-action` Endpoint

The existing `/agent/execute-action` endpoint already handles approved HITL actions.  
Add a new `elif` block inside that handler for each Notion action:

```python
# In main.py — inside the execute_action endpoint handler:

elif action == "create_notion_page":
    from app.providers.notion.api import _get_notion_client, _content_to_blocks
    client = _get_notion_client()
    data = action_data
    new_page = client.pages.create(
        parent={"page_id": data["parent_page_id"]},
        properties={
            "title": {
                "title": [{"type": "text", "text": {"content": data["title"]}}]
            }
        },
        children=_content_to_blocks(data["content"]),
    )
    result = {"page_url": new_page["url"], "page_id": new_page["id"]}

elif action == "create_notion_database_entry":
    from app.providers.notion.api import _get_notion_client, _build_notion_properties, _content_to_blocks
    client = _get_notion_client()
    data = action_data
    new_entry = client.pages.create(
        parent={"database_id": data["database_id"]},
        properties=_build_notion_properties(data["properties"]),
        children=_content_to_blocks(data.get("content") or ""),
    )
    result = {"page_url": new_entry["url"], "page_id": new_entry["id"]}

elif action == "append_notion_page":
    from app.providers.notion.api import _get_notion_client, _content_to_blocks
    client = _get_notion_client()
    data = action_data
    client.blocks.children.append(
        block_id=data["page_id"],
        children=_content_to_blocks(data["content"]),
    )
    result = {"appended": True, "page_id": data["page_id"]}
```

---

### 5.7 Register Notion Router in `main.py`

```python
# In main.py, alongside the existing auth_router include:
from app.providers.notion.notion_router import router as notion_auth_router

app.include_router(notion_auth_router, prefix="/auth")
```

---

### 5.8 Register Notion Tools in `coordinator.py`

```python
# At the top of coordinator.py, add:
from app.providers.notion.api import (
    search_notion,
    read_notion_page,
    query_notion_database,
    list_notion_databases,
    stage_notion_page,
    stage_notion_database_entry,
    stage_notion_append,
)

# Add to TOOLS list:
TOOLS: list[Any] = [
    search_web,
    stage_email,
    read_emails,
    get_calendar_events,
    create_calendar_event,
    search_my_documents,
    list_my_documents,
    get_document_summary,
    # ── Notion ──────────────────────────────────────────────────────────────
    search_notion,
    read_notion_page,
    query_notion_database,
    list_notion_databases,
    stage_notion_page,
    stage_notion_database_entry,
    stage_notion_append,
]
```

### 5.9 Update the System Instruction in `coordinator.py`

Append the following Notion section to the `SYSTEM_INSTRUCTION` string:

```
Notion rules:
- Use search_notion first when the user mentions any Notion content (a page,
  doc, tracker, database, note, or wiki) without giving an explicit page ID.
- Use read_notion_page to retrieve the full content of a page once you have its ID.
- Use query_notion_database to list records from a structured database.
- Use list_notion_databases when the user asks what databases they have.
- NEVER create, append, or modify Notion content without staging it first:
    • New page          → stage_notion_page
    • New DB record     → stage_notion_database_entry
    • Append to page    → stage_notion_append
- When staging a Notion action, stop the tool loop immediately and return so
  the user can review and approve the staged content.
- Notion content can be combined with other tools: e.g., read a Notion page
  with read_notion_page, then email a summary with stage_email.
```

---

## 6. AI Agent Tools — What Gemini Can Do

### Complete Tool Inventory

| Tool | Type | Description |
|---|---|---|
| `search_notion(query)` | Read | Full-text search across all shared Notion pages & databases |
| `read_notion_page(page_id)` | Read | Return full block content of a specific page |
| `query_notion_database(database_id, filter_description)` | Read | List and filter rows in a database |
| `list_notion_databases()` | Read | Show all databases the integration can access |
| `stage_notion_page(parent_page_id, title, content)` | **HITL Write** | Draft a new page for user approval |
| `stage_notion_database_entry(database_id, properties, content)` | **HITL Write** | Draft a new database row for user approval |
| `stage_notion_append(page_id, content)` | **HITL Write** | Stage content to be appended to an existing page |

### Cross-Tool Workflows Gemini Will Autonomously Orchestrate

| Voice Command | Tools Called | Outcome |
|---|---|---|
| "Read me our refund policy from Notion" | `search_notion` → `read_notion_page` | Policy text is read aloud |
| "Add today's meeting notes to our Team Updates page" | `search_notion` → `stage_notion_append` | User reviews & approves append |
| "Email a summary of the Q3 strategy page to Sarah" | `search_notion` → `read_notion_page` → `stage_email` | User approves email draft |
| "What tasks in my Project Tracker are In Progress?" | `list_notion_databases` → `query_notion_database` | Reads out active tasks |
| "Add a new task: Investor deck, due August 15th" | `list_notion_databases` → `stage_notion_database_entry` | User approves new row |
| "Create a meeting notes page under our Q3 Planning space" | `search_notion` → `stage_notion_page` | User reviews & approves creation |
| "Find the contract terms in Notion and compare to the invoice I uploaded" | `search_notion` + `search_my_documents` | Multi-source cross-reference answer |

---

## 7. Human-in-the-Loop (HITL) for Notion Write Actions

Notion write operations **must always go through the approval drawer**, matching the existing pattern used for emails. The approval payload format:

### Create Page
```json
{
  "type": "approval_required",
  "action": "create_notion_page",
  "data": {
    "parent_page_id": "abc123",
    "title": "Q3 Kickoff Meeting Notes",
    "content": "## Attendees\n• Alice\n• Bob\n\n## Action Items\n[ ] Send deck to investors"
  }
}
```

### Create Database Entry
```json
{
  "type": "approval_required",
  "action": "create_notion_database_entry",
  "data": {
    "database_id": "xyz789",
    "properties": {
      "Name": "Investor Deck",
      "Status": "In Progress",
      "Due Date": "2026-08-15"
    },
    "content": "Follow up from Q3 kickoff — deck must be ready before the board meeting."
  }
}
```

### Append to Page
```json
{
  "type": "approval_required",
  "action": "append_notion_page",
  "data": {
    "page_id": "def456",
    "content": "## July 23 Update\n• Shipped new onboarding flow\n• Next: add Notion integration"
  }
}
```

### Approval Drawer UI Requirements

The existing `approval_drawer.dart` already renders different card types based on the `action` field.  
Add three new cases for `create_notion_page`, `create_notion_database_entry`, and `append_notion_page`.

Each Notion card must display:

| Element | Details |
|---|---|
| **Header icon** | `Icons.note_alt_rounded` in amber `Color(0xFFFFB703)` |
| **Action label** | "New Notion Page", "New Database Entry", or "Append to Page" |
| **Target** | Page/database ID (resolve to a name if possible) |
| **Content preview** | Scrollable, monospace font, amber-bordered container |
| **"Approve" button** | `POST /agent/execute-action` with action + data payload |
| **"Edit" button** | Open text editor modal pre-filled with the content |
| **"Cancel" button** | Dismiss drawer, no backend call |

---

## 8. Flutter Frontend Changes

### 8.1 `connector.dart` — Add Notion to the Registry

```dart
// mobile_agent/lib/models/connector.dart
// Uncomment and finalise the Notion entry:

const List<ConnectorConfig> kConnectors = [
  ConnectorConfig(
    id: 'gmail',
    name: 'Gmail',
    description: 'Read, draft and send emails on your behalf.',
    icon: Icons.email_rounded,
    accentColor: Color(0xFF00B4D8),
  ),
  ConnectorConfig(
    id: 'google_calendar',
    name: 'Google Calendar',
    description: 'Create and read calendar events.',
    icon: Icons.calendar_month_rounded,
    accentColor: Color(0xFF38B000),
  ),
  ConnectorConfig(
    id: 'notion',
    name: 'Notion',
    description: 'Read pages, query databases, create notes and tasks.',
    icon: Icons.note_alt_rounded,
    accentColor: Color(0xFFFFB703),
  ),
];
```

---

### 8.2 `auth_service.dart` — Add Notion Auth Methods

```dart
// Add to AuthService class:

Future<bool> launchNotionLogin() async {
  final uri = Uri.parse('$_authBaseUrl/auth/notion/login');
  try {
    return await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (e) {
    debugPrint('AuthService: failed to launch Notion login — $e');
    return false;
  }
}

Future<NotionAuthStatus> getNotionStatus() async {
  try {
    final uri = Uri.parse('$_authBaseUrl/auth/notion/status');
    final response = await http.get(uri).timeout(const Duration(seconds: 8));
    if (response.statusCode == 200) {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      return NotionAuthStatus(
        connected: body['connected'] as bool? ?? false,
        workspaceName: body['workspace_name'] as String? ?? '',
        workspaceIcon: body['workspace_icon'] as String? ?? '',
      );
    }
    return const NotionAuthStatus(connected: false);
  } catch (e) {
    debugPrint('AuthService: failed to fetch Notion status — $e');
    return const NotionAuthStatus(connected: false, error: true);
  }
}

Future<bool> disconnectNotion() async {
  try {
    final uri = Uri.parse('$_authBaseUrl/auth/notion/disconnect');
    final response = await http.get(uri).timeout(const Duration(seconds: 8));
    return response.statusCode == 200;
  } catch (e) {
    debugPrint('AuthService: failed to disconnect Notion — $e');
    return false;
  }
}

// Add model below GoogleAuthStatus:
class NotionAuthStatus {
  final bool connected;
  final String workspaceName;
  final String workspaceIcon;
  final bool error;

  const NotionAuthStatus({
    required this.connected,
    this.workspaceName = '',
    this.workspaceIcon = '',
    this.error = false,
  });
}
```

---

### 8.3 `connectors_view.dart` — Dispatch by Connector ID

```dart
// Update _handleConnect() to dispatch by connector ID:

Future<void> _handleConnect(ConnectorConfig connector) async {
  bool launched = false;
  if (connector.id == 'notion') {
    launched = await _authService.launchNotionLogin();
  } else {
    launched = await _authService.launchGoogleLogin();
  }
  // ... rest of existing snackbar logic unchanged
}

// Update _refreshStatuses() to poll all connectors:
Future<void> _refreshStatuses() async {
  setState(() => _initialLoading = true);
  final googleStatus = await _authService.getGoogleStatus();
  final notionStatus = await _authService.getNotionStatus();
  if (mounted) {
    setState(() {
      _statusMap = {
        'gmail': googleStatus.connected,
        'google_calendar': googleStatus.connected,
        'notion': notionStatus.connected,
      };
      _initialLoading = false;
    });
  }
}

// Update _handleDisconnect() to dispatch by connector ID:
Future<void> _handleDisconnect(ConnectorConfig connector) async {
  final confirmed = await _showDisconnectDialog(connector.name);
  if (!confirmed || !mounted) return;
  if (connector.id == 'notion') {
    await _authService.disconnectNotion();
  } else {
    await _authService.disconnectGoogle();
  }
  await _refreshStatuses();
}
```

---

### 8.4 `approval_drawer.dart` — Notion Approval Cards

Add three new card builder methods. Example for the "Append to Page" card:

```dart
Widget _buildNotionAppendCard(Map<String, dynamic> data) {
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Row(children: [
        Icon(Icons.note_alt_rounded, color: const Color(0xFFFFB703), size: 28),
        const SizedBox(width: 12),
        Text('Append to Notion Page',
            style: GoogleFonts.outfit(fontWeight: FontWeight.w700, fontSize: 18)),
      ]),
      const SizedBox(height: 12),
      _infoChip('Page ID', data['page_id'] ?? ''),
      const SizedBox(height: 12),
      Text('Content to Add:',
          style: GoogleFonts.outfit(fontWeight: FontWeight.w600, color: Colors.white70)),
      const SizedBox(height: 6),
      Container(
        constraints: const BoxConstraints(maxHeight: 200),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: const Color(0xFFFFB703).withOpacity(0.3)),
        ),
        child: SingleChildScrollView(
          child: Text(data['content'] ?? '',
              style: GoogleFonts.jetBrainsMono(fontSize: 13, color: Colors.white)),
        ),
      ),
    ],
  );
}
```

Mirror this pattern for `_buildNotionCreatePageCard()` and `_buildNotionDatabaseEntryCard()`.

---

## 9. Database Schema Changes

**No new database tables are required.**

The existing `user_credentials` table in Supabase already handles the Notion token using `provider = 'notion'`. The `token_data` JSONB column stores the full Notion response payload:

```json
{
  "access_token": "secret_abc123...",
  "workspace_id": "workspace-uuid",
  "workspace_name": "Acme Corp",
  "workspace_icon": "https://notion.so/image/...",
  "bot_id": "bot-uuid"
}
```

The `db_client.py` functions `store_tokens`, `load_tokens`, `is_connected`, and `delete_tokens` all already accept any string for `provider` — **no changes needed to the repository layer at all**.

> [!TIP]
> The `/auth/notion/status` endpoint reads `workspace_name` and `workspace_icon` directly from the stored `token_data`. Display the workspace name in the connected Notion connector card so the user knows which workspace is linked.

---

## 10. Environment Variables

### Add to `backend/.env`

```dotenv
# ─── Notion OAuth 2.0 ────────────────────────────────────────────────────────
# 1. Go to: https://www.notion.com/my-integrations
# 2. Create a new Public integration named "Executive Agent"
# 3. Enable: Read content, Update content, Insert content, Read user info
# 4. Set redirect URI: http://localhost:8000/auth/notion/callback
# 5. Copy the OAuth Client ID and Secret below
NOTION_CLIENT_ID=your_notion_client_id
NOTION_CLIENT_SECRET=your_notion_client_secret
NOTION_REDIRECT_URI=http://localhost:8000/auth/notion/callback
```

### Add to `backend/app/config/settings.py`

```python
# ── Notion OAuth 2.0 ──────────────────────────────────────────────────────────
NOTION_CLIENT_ID: str = ""
NOTION_CLIENT_SECRET: str = ""
NOTION_REDIRECT_URI: str = "http://localhost:8000/auth/notion/callback"
```

---

## 11. File Changelist (Every File Touched)

### Backend — New Files (4)

| File | Purpose |
|---|---|
| `backend/app/providers/notion/__init__.py` | Python package marker |
| `backend/app/providers/notion/notion_auth.py` | OAuth URL builder & token exchange via httpx |
| `backend/app/providers/notion/notion_router.py` | FastAPI router: 4 endpoints at `/auth/notion/*` |
| `backend/app/providers/notion/api.py` | All 7 Gemini-callable Notion tools + helper functions |

### Backend — Modified Files (6)

| File | Change |
|---|---|
| `backend/app/config/settings.py` | Add `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET`, `NOTION_REDIRECT_URI` fields |
| `backend/app/ai/coordinator.py` | Import & register 7 Notion tools; append Notion block to `SYSTEM_INSTRUCTION` |
| `backend/app/main.py` | `include_router(notion_auth_router)`; add 3 `elif` branches in `execute-action` |
| `backend/.env` | Add Notion credentials section |
| `backend/.env.example` | Add Notion section with setup instructions |
| `backend/requirements.txt` | Add `notion-client>=2.2.0` |

### Flutter — Modified Files (4)

| File | Change |
|---|---|
| `mobile_agent/lib/models/connector.dart` | Uncomment & finalise Notion `ConnectorConfig` |
| `mobile_agent/lib/services/auth_service.dart` | Add `launchNotionLogin()`, `getNotionStatus()`, `disconnectNotion()`, `NotionAuthStatus` class |
| `mobile_agent/lib/views/connectors_view.dart` | Dispatch by `connector.id` in connect/disconnect/status; poll Notion status |
| `mobile_agent/lib/widgets/approval_drawer.dart` | Add 3 Notion card builder methods + route new action types |

**Total: 4 new files, 10 modified files.**

---

## 12. Voice Command Examples

### Read / Search

```
"What does our company wiki say about the onboarding process?"
"Search Notion for the investor pitch deck notes."
"Read me the Q3 OKRs page."
"What's in my Team Updates database?"
"Show me all tasks marked as In Progress."
"Find anything in Notion related to the Acme deal."
"List all my Notion databases."
```

### Create / Write

```
"Create a meeting notes page called 'Board Sync July 23' under our Q3 folder."
"Add a new task to my Project Tracker: 'Finalize Series A deck', due August 20th, status In Progress."
"Append a summary of today's call to our Weekly Team Updates page."
"Make a new Notion page summarizing the last 3 emails from Sarah."
"Create a CRM entry for the new client we spoke with today."
```

### Cross-Tool Multi-Agent Workflows

```
"Read the refund policy from Notion and email a copy to the client."
"Check if the contract terms on our Notion legal page match the invoice I uploaded."
"Search Notion for the Q2 retro notes and create a follow-up task for each action item."
"Schedule a meeting with the investor tomorrow and add the prep notes to our Investor Relations Notion page."
"Find the budget document in Notion, compare it to my uploaded expense report, and send me a summary by email."
```

---

## 13. Testing Checklist

### Backend Unit Tests

- [ ] `get_notion_authorization_url()` produces a valid URL with all required params
- [ ] `exchange_notion_code()` sends the correct Basic Auth header
- [ ] `search_notion()` returns formatted string when client returns results
- [ ] `search_notion()` returns a helpful "not connected" error when token is missing
- [ ] `read_notion_page()` converts all block types to readable text without crashing
- [ ] `query_notion_database()` handles all property types (title, select, date, checkbox, people, etc.)
- [ ] `stage_notion_page()` returns correct `approval_required` shape
- [ ] `stage_notion_database_entry()` returns correct `approval_required` shape
- [ ] `stage_notion_append()` returns correct `approval_required` shape
- [ ] `_content_to_blocks()` correctly converts headings, bullets, todos, and quotes
- [ ] `_build_notion_properties()` correctly detects bool, date, and title types

### Backend Integration Tests (requires live Notion credentials in `.env`)

- [ ] `GET /auth/notion/login` redirects to Notion's consent URL
- [ ] `GET /auth/notion/callback?code=...` stores token, returns success HTML page
- [ ] `GET /auth/notion/status` returns `{"connected": true, "workspace_name": "..."}`
- [ ] `GET /auth/notion/disconnect` clears token; subsequent `/status` returns `connected: false`
- [ ] Agent text endpoint with "Search Notion for X" triggers `search_notion` tool call in Gemini
- [ ] Agent text endpoint with "Add X to my Y page" triggers `stage_notion_append` → `approval_required`
- [ ] `POST /agent/execute-action` with `create_notion_page` creates a real page in Notion
- [ ] `POST /agent/execute-action` with `create_notion_database_entry` creates a real row
- [ ] `POST /agent/execute-action` with `append_notion_page` appends blocks to a real page

### Flutter Manual Tests

- [ ] Notion connector card appears in the Connectors screen with amber accent
- [ ] Tapping "Connect" opens the Notion consent page in the system browser
- [ ] After completing OAuth, "Check Status" shows connector as connected with workspace name displayed
- [ ] Tapping "Disconnect" removes the connection; card returns to disconnected state
- [ ] Approval drawer renders "Append to Notion Page" card correctly with content preview
- [ ] Approval drawer renders "Create Notion Page" card correctly
- [ ] Approval drawer renders "Create Database Entry" card with property list
- [ ] Approving a Notion action calls `/agent/execute-action` and displays success feedback
- [ ] Cancelling a Notion approval dismisses the drawer with no backend call

---

## 14. Future Roadmap

### Phase 2 — Enhanced Notion Features

| Feature | Description |
|---|---|
| **Property-Aware Querying** | Fetch database schema first so Gemini can construct precise API filters instead of relying on text hints |
| **Notion as a RAG Source** | Index shared Notion pages into the Supabase `pgvector` document store so `search_my_documents` searches both uploaded files AND Notion pages simultaneously |
| **Inline Property Editing** | Add a HITL `stage_notion_update` tool to modify existing row properties (e.g., "mark the investor deck task as Done") |
| **Page Archiving** | Add HITL `stage_notion_archive` to move pages to Notion's trash after user approval |
| **Relations & Rollups** | Handle Notion `relation` property type to follow cross-database links |

### Phase 3 — Notion as an Agent Memory Store

| Feature | Description |
|---|---|
| **Agent Action Log** | After every completed voice command, auto-append a compact summary to a dedicated "Executive Agent Log" Notion page |
| **Preference Sync** | Store user preferences (tone, email signature, working hours) in a Notion settings database |
| **Watcher: DB Changes** | Extend the Watcher system (`app/watchers/`) to poll a Notion database and push a notification when a row's status changes |

### Phase 4 — Advanced Cross-Tool Automations

| Feature | Description |
|---|---|
| **Meeting → Notes Pipeline** | After a Google Calendar event ends, prompt the user to dictate notes and auto-append them to the linked Notion page |
| **Email → Task Pipeline** | When a flagged email arrives, suggest creating a Notion task with the email body pre-filled as context |
| **Notion → Calendar Sync** | Read due dates from a Notion database and create Google Calendar reminders for upcoming deadlines |
| **Document → Notion** | After uploading a document, offer to create a Notion page with a summary and key excerpts |

---

## Quick Reference Card

```
Notion Integration at a Glance
───────────────────────────────────────────────────────────
New Files (Backend):
  providers/notion/__init__.py
  providers/notion/notion_auth.py
  providers/notion/notion_router.py
  providers/notion/api.py

Modified Files (Backend):
  config/settings.py          → + NOTION_CLIENT_ID/SECRET/REDIRECT_URI
  ai/coordinator.py           → + 7 tools + Notion system instruction
  main.py                     → + include router + 3 execute-action branches
  .env / .env.example         → + Notion credentials section
  requirements.txt            → + notion-client>=2.2.0

Modified Files (Flutter):
  models/connector.dart       → + Notion ConnectorConfig entry
  services/auth_service.dart  → + 3 Notion auth methods + NotionAuthStatus
  views/connectors_view.dart  → + Notion dispatch in connect/disconnect/status
  widgets/approval_drawer.dart → + 3 Notion card renderers

OAuth Portal:  https://www.notion.com/my-integrations → Public integration
Token storage: user_credentials table (provider='notion') — no expiry
HITL tools:    stage_notion_page / stage_notion_database_entry / stage_notion_append
Execute:       create_notion_page / create_notion_database_entry / append_notion_page
───────────────────────────────────────────────────────────
```

---

*Last updated: 2026-07-23 | Architected for Executive Agent v1.x*
