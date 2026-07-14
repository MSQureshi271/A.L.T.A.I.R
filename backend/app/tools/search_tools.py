"""
app/tools/search_tools.py — Mock web-search tool exposed to Gemini.

In Milestone 3 this will be replaced with a real Google Search Grounding
or Serper API call.  For now it returns plausible-looking mock data so we
can validate the full function-calling loop end-to-end.
"""
from __future__ import annotations

import datetime


def search_web(query: str) -> str:
    """Search the internet for current information and return a concise summary.

    Use this tool whenever the user asks about recent events, market data,
    news, stock prices, weather, or any fact that may have changed recently.

    Args:
        query: The search query string.

    Returns:
        A short plain-text summary of the top search results.
    """
    today = datetime.date.today().strftime("%B %d, %Y")
    return (
        f"[Mock Search — {today}]\n"
        f"Search query: '{query}'\n"
        "Results summary: Based on the latest available data, the information "
        "you requested is trending positively. Key highlights include recent "
        "developments that align with current market and industry standards. "
        "(Real results will appear once the Google Search Grounding API is "
        "connected in Milestone 3.)"
    )
