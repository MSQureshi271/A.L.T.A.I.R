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


_UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$"
)


def _get_item_title(item: dict) -> str:
    """Extract page, database, or data_source title from a Notion API item."""
    obj_type = item.get("object", "")

    # 1. Databases and Data Sources have top-level title or name
    if obj_type in ("database", "data_source"):
        if "title" in item and isinstance(item["title"], list):
            title = _extract_plain_text(item["title"])
            if title:
                return title
        if "name" in item and isinstance(item["name"], str):
            return item["name"]

    # 2. Pages have properties where one property has type == "title"
    if obj_type == "page":
        props = item.get("properties", {})
        for _, prop_val in props.items():
            if isinstance(prop_val, dict) and prop_val.get("type") == "title":
                title = _extract_plain_text(prop_val.get("title", []))
                if title:
                    return title

    # 3. Fallback check top-level title if present
    if "title" in item and isinstance(item["title"], list):
        title = _extract_plain_text(item["title"])
        if title:
            return title

    return "Untitled"


def resolve_notion_id(query_or_id: str, expected_type: str = "page") -> str:
    """Resolve a Notion page/database title or ID to a valid Notion UUID.

    If query_or_id is already a 32/36-char UUID, returns it immediately.
    Otherwise, performs a Notion workspace search to find the matching ID.
    """
    if not query_or_id:
        return query_or_id

    clean_id = query_or_id.strip()
    if _UUID_REGEX.match(clean_id):
        logger.info("[resolve_notion_id] Input '%s' matches UUID pattern directly.", clean_id)
        return clean_id

    client = _get_notion_client()
    if not client:
        logger.warning("[resolve_notion_id] Notion client not connected. Returning raw query: '%s'", clean_id)
        return clean_id

    try:
        logger.info("[resolve_notion_id] Searching Notion workspace for query='%s', expected_type='%s'...", clean_id, expected_type)
        search_results = client.search(query=clean_id, page_size=20).get("results", [])
        logger.info("[resolve_notion_id] Search returned %d result(s).", len(search_results))

        for idx, item in enumerate(search_results):
            obj_type = item.get("object", "")
            item_id = item.get("id", "")
            title = _get_item_title(item)
            parent_info = item.get("parent", {})
            logger.info(
                "[resolve_notion_id]   Item #%d: object='%s', id='%s', title='%s', parent=%s",
                idx + 1, obj_type, item_id, title, parent_info
            )

        # Pass 1: Exact / substring title match of expected_type
        for item in search_results:
            obj_type = item.get("object", "")
            if expected_type == "data_source" and obj_type in ("database", "data_source"):
                title = _get_item_title(item)
                if title and title != "Untitled" and clean_id.lower() in title.lower():
                    matched_id = item["id"]
                    logger.info("[resolve_notion_id] Pass 1 MATCH: '%s' matched '%s' (object='%s', id='%s')", clean_id, title, obj_type, matched_id)
                    return matched_id
            elif expected_type == "page" and obj_type == "page":
                title = _get_item_title(item)
                if title and title != "Untitled" and clean_id.lower() in title.lower():
                    matched_id = item["id"]
                    logger.info("[resolve_notion_id] Pass 1 MATCH: '%s' matched '%s' (object='page', id='%s')", clean_id, title, matched_id)
                    return matched_id

        # Pass 2: First item in search results matching expected_type
        for item in search_results:
            obj_type = item.get("object", "")
            if expected_type == "data_source" and obj_type in ("database", "data_source"):
                matched_id = item["id"]
                logger.info("[resolve_notion_id] Pass 2 FALLBACK MATCH: object='%s', id='%s'", obj_type, matched_id)
                return matched_id
            if expected_type == "page" and obj_type == "page":
                matched_id = item["id"]
                logger.info("[resolve_notion_id] Pass 2 FALLBACK MATCH: object='page', id='%s'", matched_id)
                return matched_id

    except Exception as exc:  # noqa: BLE001
        logger.warning("[resolve_notion_id] Lookup failed for '%s': %s", clean_id, exc)

    logger.info("[resolve_notion_id] No search match found for '%s'. Returning raw string.", clean_id)
    return clean_id



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


def _parse_rich_text(text: str) -> list[dict]:
    """Parse inline markdown (bold, italic, code, links, strikethrough) into Notion rich_text objects."""
    if not text:
        return []

    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    bold_pattern = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
    italic_pattern = re.compile(r"\*([^*]+)\*|_([^_]+)_")
    code_pattern = re.compile(r"`([^`]+)`")
    strike_pattern = re.compile(r"~~([^~]+)~~")

    parts = []
    last_idx = 0
    for match in link_pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            parts.append({"text": text[last_idx:start]})
        parts.append({"text": match.group(1), "link": match.group(2)})
        last_idx = end
    if last_idx < len(text):
        parts.append({"text": text[last_idx:]})

    rich_text_list = []
    for part in parts:
        txt = part["text"]
        link_url = part.get("link")

        is_bold = bool(bold_pattern.search(txt))
        is_italic = bool(italic_pattern.search(txt))
        is_code = bool(code_pattern.search(txt))
        is_strike = bool(strike_pattern.search(txt))

        clean_txt = bold_pattern.sub(r"\1\2", txt)
        clean_txt = italic_pattern.sub(r"\1\2", clean_txt)
        clean_txt = code_pattern.sub(r"\1", clean_txt)
        clean_txt = strike_pattern.sub(r"\1", clean_txt)

        rich_obj = {
            "type": "text",
            "text": {
                "content": clean_txt,
                "link": {"url": link_url} if link_url else None,
            },
            "annotations": {
                "bold": is_bold,
                "italic": is_italic,
                "strikethrough": is_strike,
                "underline": False,
                "code": is_code,
                "color": "default",
            },
        }
        rich_text_list.append(rich_obj)

    return rich_text_list


def _content_to_blocks(content: str) -> list[dict]:
    """Convert rich markdown text into native Notion API block objects.

    Supports:
      - Headings 1-3 & Toggle Headings (# ▶ Heading)
      - Callout boxes with icons and colors (> [!NOTE], > [!WARNING], > [!IMPORTANT], > [!TIP])
      - Bulleted and Numbered lists
      - To-do checklists ([ ] / [x])
      - Blockquotes & Dividers (---)
      - Fenced Code Blocks (```python ... ```)
      - Inline Markdown Tables (| col1 | col2 |)
      - Rich Text Annotations (bold, italic, code, links)
    """
    if not content:
        return []

    blocks = []
    lines = content.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 1. Code blocks (fenced ```)
        if stripped.startswith("```"):
            lang = stripped[3:].strip() or "plain text"
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n and lines[i].strip().startswith("```"):
                i += 1
            code_content = "\n".join(code_lines)
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "language": lang.lower(),
                    "rich_text": [{"type": "text", "text": {"content": code_content}}],
                },
            })
            continue

        # 2. Markdown Tables (| col1 | col2 |)
        if stripped.startswith("|") and stripped.endswith("|"):
            table_rows = []
            while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                row_str = lines[i].strip()[1:-1]
                if not re.match(r"^[\s\-:|]+$", row_str):
                    cells = [cell.strip() for cell in row_str.split("|")]
                    row_cells = [_parse_rich_text(cell) for cell in cells]
                    table_rows.append({"type": "table_row", "table_row": {"cells": row_cells}})
                i += 1
            if table_rows:
                table_width = len(table_rows[0]["table_row"]["cells"])
                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": table_width,
                        "has_column_header": True,
                        "children": table_rows,
                    },
                })
            continue

        # 3. Callout boxes (> [!NOTE], > [!WARNING], > [!IMPORTANT], > [!TIP])
        if stripped.startswith("> [!"):
            callout_match = re.match(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION|INFO)\]\s*(.*)", stripped, re.IGNORECASE)
            if callout_match:
                ctype = callout_match.group(1).upper()
                callout_text = callout_match.group(2)
                icon_map = {
                    "NOTE": "💡",
                    "TIP": "📌",
                    "IMPORTANT": "🚨",
                    "WARNING": "⚠️",
                    "CAUTION": "🛑",
                    "INFO": "ℹ️",
                }
                color_map = {
                    "NOTE": "blue_background",
                    "TIP": "green_background",
                    "IMPORTANT": "red_background",
                    "WARNING": "yellow_background",
                    "CAUTION": "red_background",
                    "INFO": "gray_background",
                }
                blocks.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": _parse_rich_text(callout_text),
                        "icon": {"emoji": icon_map.get(ctype, "💡")},
                        "color": color_map.get(ctype, "default"),
                    },
                })
                i += 1
                continue

        # 4. Dividers
        if stripped in ("---", "***", "___"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # 5. Headings & Toggle Headings
        if stripped.startswith("# "):
            h_text = stripped[2:].strip()
            is_toggle = h_text.startswith("▶ ")
            if is_toggle:
                h_text = h_text[2:]
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": _parse_rich_text(h_text),
                    "is_toggleable": is_toggle,
                },
            })
            i += 1
            continue
        if stripped.startswith("## "):
            h_text = stripped[3:].strip()
            is_toggle = h_text.startswith("▶ ")
            if is_toggle:
                h_text = h_text[2:]
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": _parse_rich_text(h_text),
                    "is_toggleable": is_toggle,
                },
            })
            i += 1
            continue
        if stripped.startswith("### "):
            h_text = stripped[4:].strip()
            is_toggle = h_text.startswith("▶ ")
            if is_toggle:
                h_text = h_text[2:]
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": _parse_rich_text(h_text),
                    "is_toggleable": is_toggle,
                },
            })
            i += 1
            continue

        # 6. Bulleted & Numbered lists
        if stripped.startswith(("• ", "- ", "* ")):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _parse_rich_text(stripped[2:])},
            })
            i += 1
            continue
        num_match = re.match(r"^\d+\.\s+(.*)", stripped)
        if num_match:
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _parse_rich_text(num_match.group(1))},
            })
            i += 1
            continue

        # 7. To-Do checklists
        if stripped.startswith(("[ ] ", "[] ", "☐ ")):
            offset = 3 if stripped.startswith("[] ") else (4 if stripped.startswith("[ ] ") else 2)
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {"rich_text": _parse_rich_text(stripped[offset:]), "checked": False},
            })
            i += 1
            continue
        if stripped.startswith(("[x] ", "[X] ", "✅ ")):
            offset = 4 if stripped.startswith(("[x] ", "[X] ")) else 3
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {"rich_text": _parse_rich_text(stripped[offset:]), "checked": True},
            })
            i += 1
            continue

        # 8. Toggle blocks (▶ Collapsible header or > ▶ Collapsible header)
        if stripped.startswith(("▶ ", "> ▶ ")):
            offset = 4 if stripped.startswith("> ▶ ") else 2
            blocks.append({
                "object": "block",
                "type": "toggle",
                "toggle": {"rich_text": _parse_rich_text(stripped[offset:])},
            })
            i += 1
            continue

        # 9. Standard Quotes
        if stripped.startswith("> "):
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {"rich_text": _parse_rich_text(stripped[2:])},
            })
            i += 1
            continue

        # 10. Standard Paragraphs

        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": _parse_rich_text(stripped)},
        })
        i += 1

    return blocks



import json


def parse_properties_to_dict(raw_properties: Any) -> dict[str, Any]:
    """Safely convert and normalize raw property inputs into a Python dictionary.

    Raises ValueError if raw_properties cannot be converted to a valid dictionary.
    """
    if raw_properties is None:
        return {}
    if isinstance(raw_properties, dict):
        return raw_properties

    if isinstance(raw_properties, str):
        cleaned = raw_properties.strip()
        if not cleaned:
            return {}

        # 1. Try standard JSON parsing
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except Exception:  # noqa: BLE001
            pass

        # 2. Try parsing formatted strings like "{Decks: Finalizer, Due Date: 2026-07-17}"
        if cleaned.startswith("{") and cleaned.endswith("}"):
            cleaned = cleaned[1:-1].strip()

        result_dict = {}
        pairs = re.split(r",|\n", cleaned)
        for pair in pairs:
            if not pair.strip():
                continue
            if ":" in pair:
                k, v = pair.split(":", 1)
                result_dict[k.strip()] = v.strip()
            elif "=" in pair:
                k, v = pair.split("=", 1)
                result_dict[k.strip()] = v.strip()

        if result_dict:
            return result_dict

    raise ValueError(
        f"Invalid database properties format: expected a key-value dictionary, got {type(raw_properties).__name__}"
    )


def _get_datasource_schema(data_source_id: str) -> dict[str, str]:
    """Retrieve property name -> property type mapping for a data_source_id.

    Returns a dict like: {"Decks": "title", "Status": "status", "Due Date": "date"}.
    """
    client = _get_notion_client()
    if not client or not data_source_id:
        return {}

    try:
        if hasattr(client, "data_sources") and hasattr(client.data_sources, "retrieve"):
            ds_obj = client.data_sources.retrieve(data_source_id=data_source_id)
        else:
            ds_obj = client.request(path=f"data_sources/{data_source_id}", method="GET")

        props = ds_obj.get("properties", {})
        schema = {}
        for prop_name, prop_val in props.items():
            if isinstance(prop_val, dict):
                prop_type = prop_val.get("type", "")
                schema[prop_name] = prop_type
                schema[prop_name.lower()] = prop_type
        logger.info("[_get_datasource_schema] Retrieved schema for data_source '%s': %s", data_source_id, schema)
        return schema
    except Exception as exc:  # noqa: BLE001
        logger.warning("[_get_datasource_schema] Failed to fetch schema for data_source '%s': %s", data_source_id, exc)
        return {}


def _build_notion_properties(properties: Any, data_source_id: str | None = None) -> dict:
    """Convert a simple {name: value} dict into Notion property format using database schema.

    Ensures input is normalized to a Python dictionary before building.
    If data_source_id is provided, fetches the exact column types (title, status, select, date, etc.)
    from Notion's data_sources endpoint so custom column names like 'Decks' or 'Status' match Notion's schema.
    """
    props_dict = parse_properties_to_dict(properties)
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    schema = _get_datasource_schema(data_source_id) if data_source_id else {}

    result = {}
    for name, value in props_dict.items():
        prop_type = schema.get(name) or schema.get(name.lower(), "")
        str_val = str(value).strip() if value is not None else ""

        if prop_type == "title":
            result[name] = {"title": [{"type": "text", "text": {"content": str_val}}]}
        elif prop_type == "status":
            result[name] = {"status": {"name": str_val}}
        elif prop_type == "select":
            result[name] = {"select": {"name": str_val}}
        elif prop_type == "multi_select":
            items = [s.strip() for s in str_val.split(",") if s.strip()]
            result[name] = {"multi_select": [{"name": item} for item in items]}
        elif prop_type == "date":
            result[name] = {"date": {"start": str_val}}
        elif prop_type == "checkbox":
            bool_val = value if isinstance(value, bool) else str_val.lower() in ("true", "1", "yes", "checked")
            result[name] = {"checkbox": bool_val}
        elif prop_type == "number":
            try:
                num_val = float(str_val) if "." in str_val else int(str_val)
                result[name] = {"number": num_val}
            except ValueError:
                result[name] = {"number": None}
        elif prop_type == "url":
            result[name] = {"url": str_val}
        elif prop_type == "email":
            result[name] = {"email": str_val}
        elif prop_type == "phone_number":
            result[name] = {"phone_number": str_val}
        elif prop_type == "rich_text":
            result[name] = {"rich_text": [{"type": "text", "text": {"content": str_val}}]}
        else:
            # Fallback heuristic type detection
            if isinstance(value, bool):
                result[name] = {"checkbox": value}
            elif isinstance(value, str) and date_pattern.match(value):
                result[name] = {"date": {"start": value}}
            elif name.lower() in ("name", "title"):
                result[name] = {"title": [{"type": "text", "text": {"content": str_val}}]}
            else:
                result[name] = {"rich_text": [{"type": "text", "text": {"content": str_val}}]}

    logger.info("[_build_notion_properties] Built Notion properties payload: %s", result)
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
            title = _get_item_title(item)
            url = item.get("url", "")
            icon = "📄" if obj_type == "page" else "🗄️"
            type_label = "Data Source" if obj_type == "data_source" else obj_type.capitalize()
            lines.append(f"{icon} [{type_label}] {title}\n   URL: {url}\n   ID: {item['id']}")
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
        page_id: The unique Notion page ID or title string.

    Returns:
        The page title and full text content of the page, formatted for readability.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        resolved_id = resolve_notion_id(page_id, "page")
        page = client.pages.retrieve(page_id=resolved_id)
        title_prop = (
            page.get("properties", {}).get("title")
            or page.get("properties", {}).get("Name")
            or {}
        )
        title_list = title_prop.get("title", []) or title_prop.get("rich_text", [])
        title = _extract_plain_text(title_list) or "Untitled"

        blocks_response = client.blocks.children.list(block_id=resolved_id, page_size=100)
        blocks = blocks_response.get("results", [])
        content = _blocks_to_markdown(blocks)
        return f"# {title}\n\n{content}" if content else f"# {title}\n\n(This page has no text content.)"
    except Exception as exc:  # noqa: BLE001
        logger.error("read_notion_page error: %s", exc)
        return f"Failed to read Notion page: {exc}"


def resolve_datasource_id(target_id: str) -> str:
    """Resolve a Notion database name or ID to a Data Source ID via data_sources API.

    This function never uses deprecated /v1/databases endpoints.
    """
    logger.info("[resolve_datasource_id] Resolving data_source_id for target_id='%s'...", target_id)
    if not target_id:
        return target_id

    ds_id = resolve_notion_id(target_id, "data_source")
    logger.info("[resolve_datasource_id] Resolved target_id='%s' -> data_source_id='%s'", target_id, ds_id)
    return ds_id


def resolve_database_row_id(data_source_id: str, row_title_or_query: str) -> str | None:
    """Query a Notion data source to resolve a row title/query string into a valid 36-char Page ID."""
    logger.info("[resolve_database_row_id] Attempting row ID resolution: data_source_id='%s', row_title_or_query='%s'", data_source_id, row_title_or_query)
    if not data_source_id or not row_title_or_query:
        logger.info("[resolve_database_row_id] Missing data_source_id or row_title_or_query. Skipping row lookup.")
        return None

    client = _get_notion_client()
    if not client:
        logger.warning("[resolve_database_row_id] Notion client not connected. Cannot search database rows.")
        return None

    try:
        resolved_ds_id = resolve_datasource_id(data_source_id)
        if hasattr(client, "data_sources") and hasattr(client.data_sources, "query"):
            logger.info("[resolve_database_row_id] Querying data source '%s' rows...", resolved_ds_id)
            resp = client.data_sources.query(data_source_id=resolved_ds_id, page_size=50)
        else:
            logger.info("[resolve_database_row_id] Querying data source '%s' via request path...", resolved_ds_id)
            resp = client.request(path=f"data_sources/{resolved_ds_id}/query", method="POST", body={"page_size": 50})

        rows = resp.get("results", [])
        logger.info("[resolve_database_row_id] Data source query returned %d row(s). Searching for match...", len(rows))

        target = row_title_or_query.strip().lower()
        for idx, row in enumerate(rows):
            row_id = row.get("id")
            props = row.get("properties", {})
            for p_name, p_val in props.items():
                if p_val.get("type") == "title":
                    title_text = _extract_plain_text(p_val.get("title", [])).strip()
                    logger.info("[resolve_database_row_id]   Row #%d: id='%s', title_prop='%s', value='%s'", idx + 1, row_id, p_name, title_text)
                    if title_text and (target in title_text.lower() or title_text.lower() in target):
                        logger.info("[resolve_database_row_id] SUCCESS! Matched row_id='%s' for target '%s'", row_id, target)
                        return row_id
        logger.info("[resolve_database_row_id] No row title matched '%s' in data source '%s'.", target, resolved_ds_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[resolve_database_row_id] Exception while querying database rows: %s", exc)
    return None



def query_notion_database(database_id: str, filter_description: str | None = None) -> str:
    """Query a Notion database and return its entries via Notion Data Sources API.

    Use this when the user wants to see records from a Notion database, such as
    a task tracker, CRM, project list, or any structured table.

    Args:
        database_id:        The unique ID or title string of the Notion database.
        filter_description: Optional text description of what to filter by, e.g. 'Status = In Progress'.

    Returns:
        A formatted table of database entries showing key properties.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        data_source_id = resolve_datasource_id(database_id)
        logger.info("[query_notion_database] Executing query against data_source_id='%s'...", data_source_id)

        if hasattr(client, "data_sources") and hasattr(client.data_sources, "query"):
            logger.info("[query_notion_database] Calling client.data_sources.query(data_source_id='%s')...", data_source_id)
            response = client.data_sources.query(data_source_id=data_source_id, page_size=20)
        else:
            logger.info("[query_notion_database] Calling client.request('data_sources/%s/query')...", data_source_id)
            response = client.request(path=f"data_sources/{data_source_id}/query", method="POST", body={"page_size": 20})

        rows = response.get("results", [])
        logger.info("[query_notion_database] Data source query returned %d row(s).", len(rows))




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
    except Exception as exc:  # noqa: BLE001
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
        search_results = client.search(page_size=50).get("results", [])
        results = [db for db in search_results if db.get("object") in ("database", "data_source")]

        if not results:
            return (
                "No Notion databases found. Make sure the integration has been "
                "granted access to at least one database in your Notion workspace."
            )
        lines = [f"Found {len(results)} database(s):\n"]
        for db in results:
            title = _extract_plain_text(db.get("title", [])) or db.get("name") or "Untitled"
    except Exception as exc:  # noqa: BLE001
        logger.error("list_notion_databases error: %s", exc)
        return f"Failed to list Notion databases: {exc}"


def update_notion_database_entry(
    page_id: str,
    properties: dict,
    data_source_id: str | None = None,
) -> str:
    """Update properties of an existing Notion database entry (row).

    Args:
        page_id: The ID or title of the existing database page/row to update.
        properties: Dict of properties to update (e.g. {'Status': 'Completed'}).
        data_source_id: Optional parent data_source ID for schema resolution.

    Returns:
        Status message string.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        resolved_page_id = resolve_notion_id(page_id, "page")
        built_props = _build_notion_properties(properties, data_source_id=data_source_id)
        updated_page = client.pages.update(page_id=resolved_page_id, properties=built_props)
        return f"Updated Notion database entry '{page_id}'. URL: {updated_page.get('url', '')}"
    except Exception as exc:  # noqa: BLE001
        logger.error("update_notion_database_entry error: %s", exc)
        return f"Failed to update Notion database entry: {exc}"


def update_notion_page_content(
    page_id: str,
    old_str: str | None = None,
    new_str: str = "",
) -> str:
    """Update or replace text content in an existing Notion page using Markdown patch API.

    Args:
        page_id: The ID or title of the Notion page.
        old_str: If provided, performs targeted search-and-replace for old_str -> new_str.
        new_str: The replacement text or new page markdown content.

    Returns:
        Status message string.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        resolved_page_id = resolve_notion_id(page_id, "page")
        if old_str:
            body = {
                "type": "update_content",
                "update_content": {
                    "content_updates": [
                        {"old_str": old_str, "new_str": new_str}
                    ]
                },
            }
        else:
            body = {
                "type": "replace_content",
                "replace_content": {
                    "new_str": new_str
                },
            }

        client.request(
            path=f"pages/{resolved_page_id}/markdown",
            method="PATCH",
            body=body,
        )
        return f"Successfully updated content on Notion page '{page_id}'."
    except Exception as exc:  # noqa: BLE001
        logger.error("update_notion_page_content error: %s", exc)
        return f"Failed to update Notion page content: {exc}"


def update_notion_data_source(
    data_source_id: str,
    title: str | None = None,
) -> str:
    """Update title/metadata of an existing Notion data source.

    Args:
        data_source_id: The ID or title of the data source to update.
        title: New title for the data source.

    Returns:
        Status message string.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        resolved_ds_id = resolve_datasource_id(data_source_id)
        body = {}
        if title:
            body["title"] = [{"type": "text", "text": {"content": title}}]

        client.request(
            path=f"data_sources/{resolved_ds_id}",
            method="PATCH",
            body=body,
        )
        return f"Successfully updated Notion data source '{data_source_id}'."
    except Exception as exc:  # noqa: BLE001
        logger.error("update_notion_data_source error: %s", exc)
        return f"Failed to update Notion data source: {exc}"


def _find_todo_block_id_recursive(client: Any, parent_block_id: str, text_to_find: str) -> str | None:
    """Recursively search child blocks on a page/block for a to_do item matching text_to_find."""
    start_cursor = None
    target_lower = text_to_find.strip().lower()

    while True:
        kwargs = {"block_id": parent_block_id, "page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        resp = client.blocks.children.list(**kwargs)
        blocks = resp.get("results", [])

        for block in blocks:
            btype = block.get("type", "")
            if btype == "to_do":
                rich_text = (block.get("to_do") or {}).get("rich_text", [])
                block_text = _extract_plain_text(rich_text).strip()
                logger.info("[_find_todo_block_id_recursive] Checking to_do block id='%s', text='%s'", block["id"], block_text)
                if block_text and (target_lower in block_text.lower() or block_text.lower() in target_lower):
                    logger.info("[_find_todo_block_id_recursive] MATCH FOUND! block_id='%s' for text '%s'", block["id"], text_to_find)
                    return block["id"]

            if block.get("has_children", False):
                child_match = _find_todo_block_id_recursive(client, block["id"], text_to_find)
                if child_match:
                    return child_match

        if not resp.get("has_more", False):
            break
        start_cursor = resp.get("next_cursor")

    return None


def complete_notion_todo_item(
    page_id: str,
    item_text: str,
    completed: bool = True,
) -> str:
    """Find a specific to-do checklist block on a Notion page by text and toggle its checked status.

    Args:
        page_id: The ID or title of the Notion page containing the to-do item.
        item_text: The text of the to-do item to check or uncheck (e.g. 'Boil the milk').
        completed: True to mark checked/completed, False to mark unchecked.

    Returns:
        Status message string.
    """
    client = _get_notion_client()
    if not client:
        return "Notion is not connected."
    try:
        resolved_page_id = resolve_notion_id(page_id, "page")
        logger.info("[complete_notion_todo_item] Searching for to-do block matching '%s' on page '%s' (%s)...", item_text, page_id, resolved_page_id)

        target_block_id = _find_todo_block_id_recursive(client, resolved_page_id, item_text)
        if not target_block_id:
            return f"Could not find a to-do item matching '{item_text}' on Notion page '{page_id}'."

        client.blocks.update(
            block_id=target_block_id,
            to_do={"checked": completed},
        )
        status_str = "completed ✅" if completed else "uncompleted ☐"
        logger.info("[complete_notion_todo_item] SUCCESS! Marked to_do block '%s' as %s", target_block_id, status_str)
        return f"Successfully marked to-do item '{item_text}' as {status_str} on page '{page_id}'."
    except Exception as exc:  # noqa: BLE001
        logger.error("complete_notion_todo_item error: %s", exc)
        return f"Failed to update to-do item on Notion page: {exc}"


def stage_complete_notion_todo_item(
    page_id: str,
    item_text: str,
    completed: bool = True,
) -> dict:
    """Stage a to-do completion request for user approval in Flutter."""
    return {
        "type": "approval_required",
        "action": "complete_notion_todo_item",
        "data": {
            "page_id": page_id,
            "item_text": item_text,
            "completed": completed,
        },
    }



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
        parent_page_id: The ID or title of the parent Notion page.
        title:          The title for the new page.
        content:        The full text body of the new page.

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "create_notion_page",
        "data": {
            "parent_page_id": resolve_notion_id(parent_page_id, "page"),
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
        database_id: The ID or title of the target Notion database.
        properties:  A dict mapping property names to their values.
        content:     Optional body text to add to the entry page content.

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "create_notion_database_entry",
        "data": {
            "database_id": resolve_datasource_id(database_id),
            "properties": properties,
            "content": content,
        },
    }


def stage_update_notion_database_entry(
    page_id: str,
    properties: dict,
    data_source_id: str | None = None,
) -> dict:
    """Stage an update to an existing database entry (row) properties for user review.

    Args:
        page_id:        The ID or title of the Notion database row/page to update.
        properties:     Dict mapping property names to their updated values.
        data_source_id: Optional parent data_source ID for schema resolution.

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "update_notion_database_entry",
        "data": {
            "page_id": resolve_notion_id(page_id, "page"),
            "properties": properties,
            "data_source_id": resolve_datasource_id(data_source_id) if data_source_id else None,
        },
    }


def stage_update_notion_page_content(
    page_id: str,
    old_str: str | None = None,
    new_str: str = "",
) -> dict:
    """Stage an update to existing page text content for user review.

    Args:
        page_id: The ID or title of the Notion page to update.
        old_str: Text to find and replace (or None to replace entire page text).
        new_str: The replacement text or new page body text.

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "update_notion_page_content",
        "data": {
            "page_id": resolve_notion_id(page_id, "page"),
            "old_str": old_str,
            "new_str": new_str,
        },
    }


def stage_update_notion_data_source(
    data_source_id: str,
    title: str | None = None,
) -> dict:
    """Stage an update to an existing data source (database title/metadata) for user review.

    Args:
        data_source_id: The ID or title of the data source to update.
        title:          New title for the data source.

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "update_notion_data_source",
        "data": {
            "data_source_id": resolve_datasource_id(data_source_id),
            "title": title,
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
        page_id: The ID or title of the Notion page to append content to.
        content: The text to add at the bottom of the page.

    Returns:
        An approval_required dict that the Flutter UI will render as a review card.
    """
    return {
        "type": "approval_required",
        "action": "append_notion_page",
        "data": {
            "page_id": resolve_notion_id(page_id, "page"),
            "content": content,
        },
    }


