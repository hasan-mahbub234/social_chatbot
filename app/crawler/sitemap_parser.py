"""Sitemap parser — discovers URLs from sitemap.xml or sitemap_index.xml."""
import httpx
from typing import List
from urllib.parse import urljoin
from app.core.logging import get_logger

logger = get_logger(__name__)


class SitemapParser:
    """Parse XML sitemaps to discover crawlable URLs, handling sitemap indexes."""

    async def get_urls(self, base_url: str) -> List[str]:
        """Fetch and parse sitemap, return list of page URLs."""
        candidates = [
            urljoin(base_url, "/sitemap.xml"),
            urljoin(base_url, "/sitemap_index.xml"),
            urljoin(base_url, "/wp-sitemap.xml"),
            urljoin(base_url, "/sitemap_index.xsl"),
        ]
        _headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            async with httpx.AsyncClient(
                timeout=10,
                follow_redirects=True,
                http2=True,
                headers=_headers,
            ) as client:
                for sitemap_url in candidates:
                    urls = await self._fetch_and_parse(client, sitemap_url)
                    if urls:
                        logger.info("sitemap_found", url=sitemap_url, count=len(urls))
                        return urls
            logger.warning("sitemap_not_found", base_url=base_url)
            return []
        except Exception as e:
            logger.warning("sitemap_fetch_failed", base_url=base_url, error=str(e))
            return []

    async def _fetch_and_parse(self, client: httpx.AsyncClient, url: str, depth: int = 0) -> List[str]:
        """Recursively resolve sitemap indexes."""
        if depth > 2:
            return []
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
        except Exception:
            return []

        import re
        from html import unescape
        locs = re.findall(r"<loc>(.*?)</loc>", resp.text, re.IGNORECASE)
        locs = [unescape(u.strip()) for u in locs if u.strip()]

        # If any loc points to another sitemap (ends with .xml), recurse
        if any(u.endswith(".xml") for u in locs):
            urls: List[str] = []
            for loc in locs:
                if loc.endswith(".xml"):
                    urls.extend(await self._fetch_and_parse(client, loc, depth + 1))
                else:
                    urls.append(loc)
            return urls[:1000]  # increased limit
        return locs[:1000]


sitemap_parser = SitemapParser()