"""
app/tools/search_tools.py — Google Search Grounding tool exposed to Gemini.

Fetches live search results from Google Search using Gemini's native Search Grounding capability
and returns a cited summary of the results.
"""
from __future__ import annotations

import logging
from google import genai
from google.genai import types
from app.config.settings import settings

logger = logging.getLogger(__name__)


def search_web(query: str) -> str:
    """Search the internet for current information and return a concise summary.

    Use this tool whenever the user asks about recent events, market data,
    news, stock prices, weather, or any fact that may have changed recently.

    Args:
        query: The search query string.

    Returns:
        A short plain-text summary of the top search results including citations/sources.
    """
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured in settings.")
        return "Search failed: Gemini API key is missing on the server."

    logger.info("Executing Google Search Grounding for query: %r", query)
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Search the web for: {query}. Summarize the key facts and list sources.",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
            ),
        )
        return response.text or "No search results returned."
    except Exception as exc:
        logger.exception("Google Search Grounding failed")
        return f"Web search error: {exc}"
