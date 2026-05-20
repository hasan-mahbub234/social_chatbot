"""Page hasher — detects unchanged pages to avoid redundant re-ingestion."""
import hashlib
from typing import Dict, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# In-memory hash store (use Redis in production for persistence)
_page_hashes: Dict[str, str] = {}


class PageHasher:
    """Track content hashes to skip unchanged pages. Can be extended with Redis."""

    def hash(self, content: str) -> str:
        """Generate SHA-256 hash of content."""
        return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()

    def is_unchanged(self, url: str, content: str) -> bool:
        """Return True if page content has not changed since last crawl."""
        new_hash = self.hash(content)
        return _page_hashes.get(url) == new_hash

    def store(self, url: str, content: str):
        """Store content hash for a URL."""
        _page_hashes[url] = self.hash(content)

    def invalidate(self, url: str):
        """Remove stored hash to force re-crawl."""
        _page_hashes.pop(url, None)

    def clear_org(self, organization_id: str):
        """Clear all hashes (used when org data is reset)."""
        _page_hashes.clear()
        logger.info("page_hashes_cleared")


page_hasher = PageHasher()