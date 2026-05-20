"""
Web Search Tool — fetches live web results for queries beyond the knowledge base.

Used as last resort when:
  - RAG returns 0 results
  - Query is about current events / live data
  - User explicitly asks to search the web

Uses DuckDuckGo Instant Answer API (no API key required) as default.
Can be upgraded to Bing/Google Search API in production.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WebSearchResult:
    success: bool
    query: str
    results: List[Dict[str, Any]] = field(default_factory=list)
    answer: Optional[str] = None
    error: Optional[str] = None


class WebSearchTool:
    """Fetch live web search results."""

    def can_handle(self, query: str) -> bool:
        lower = query.lower()
        return any(k in lower for k in (
            "search the web", "google", "latest", "current", "today",
            "news", "recent", "live", "real-time",
        ))

    async def search(self, query: str, max_results: int = 3) -> WebSearchResult:
        """Search the web using DuckDuckGo Instant Answer API."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": "1",
                        "skip_disambig": "1",
                    },
                )
                if resp.status_code != 200:
                    return WebSearchResult(success=False, query=query, error=f"HTTP {resp.status_code}")

                data = resp.json()
                results = []

                # Instant answer
                if data.get("AbstractText"):
                    results.append({
                        "title":   data.get("Heading", ""),
                        "snippet": data["AbstractText"][:500],
                        "url":     data.get("AbstractURL", ""),
                        "source":  "DuckDuckGo",
                    })

                # Related topics
                for topic in data.get("RelatedTopics", [])[:max_results]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title":   topic.get("Text", "")[:100],
                            "snippet": topic.get("Text", "")[:300],
                            "url":     topic.get("FirstURL", ""),
                            "source":  "DuckDuckGo",
                        })

                answer = data.get("AbstractText") or data.get("Answer", "")

                return WebSearchResult(
                    success=True,
                    query=query,
                    results=results[:max_results],
                    answer=answer[:500] if answer else None,
                )

        except ImportError:
            return WebSearchResult(success=False, query=query, error="httpx not installed")
        except Exception as e:
            logger.warning("web_search_failed", query=query[:60], error=str(e))
            return WebSearchResult(success=False, query=query, error=str(e))


web_search_tool = WebSearchTool()
