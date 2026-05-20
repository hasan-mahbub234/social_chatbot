"""URL Frontier — Redis sorted set priority queue for distributed crawling."""
import re
import hashlib
from typing import Optional, List, Tuple
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
from app.core.logging import get_logger

logger = get_logger(__name__)

# Parameters to strip for canonical URL normalization
STRIP_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                "fbclid", "gclid", "sort", "filter", "session", "replytocom", "ref",
                "_ga", "mc_cid", "mc_eid"}

SKIP_URL_PATTERNS = (
    "/cart", "/checkout", "/account", "/login", "/register",
    "/wishlist", "/compare", "/cdn/", "/customer_authentication",
    "/tag/", "/order/", "/user/", "/search", "/wp-login",
    "/wp-admin", "/feed/",
    # Non-HTML file extensions
    ".xml", ".pdf", ".zip", ".txt", ".md",
    ".jpg", ".jpeg", ".png", ".gif", ".svg",
    ".css", ".js", ".ico", ".woff", ".woff2", ".ttf", ".mp4", ".mp3",
)

# Priority map (lower = higher priority)
URL_PRIORITIES = {
    "product": 0, "products": 0, "service": 0, "services": 0,
    "pricing": 0, "price": 0, "docs": 0, "documentation": 0,
    "faq": 5, "policy": 5, "policies": 5, "about": 5, "contact": 5,
    "blog": 10, "article": 10, "news": 10, "post": 10,
    # collections are important for Shopify — they link to products
    "collection": 15, "collections": 15, "category": 15,
    "tag": 50,
}


class URLFrontier:
    """Distributed URL frontier backed by Redis sorted sets."""

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _queue_key(self, job_id: str) -> str:
        return f"crawler:frontier:{job_id}"

    def _seen_key(self, job_id: str) -> str:
        return f"crawler:seen:{job_id}"

    def normalize(self, url: str) -> str:
        """Canonical URL: lowercase scheme+host, strip tracking params, remove fragment."""
        try:
            parsed = urlparse(url.strip())
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            path = parsed.path.rstrip("/") or "/"
            params = {k: v for k, v in parse_qs(parsed.query).items()
                      if k.lower() not in STRIP_PARAMS}
            query = urlencode({k: v[0] for k, v in sorted(params.items())})
            return urlunparse((scheme, netloc, path, "", query, ""))
        except Exception:
            return url

    def url_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def priority(self, url: str) -> int:
        url_lower = url.lower()
        for segment, p in URL_PRIORITIES.items():
            if f"/{segment}/" in url_lower or url_lower.endswith(f"/{segment}"):
                return p
        return 25

    def should_skip(self, url: str) -> bool:
        return any(p in url.lower() for p in SKIP_URL_PATTERNS)

    # ── Sync methods (used from Celery workers) ──────────────────────────

    def push_sync(self, redis_sync, job_id: str, urls: List[str], base_domain: str):
        """Push URLs into Redis sorted set (sync, for Celery)."""
        pipe = redis_sync.pipeline()
        seen_key = self._seen_key(job_id)
        queue_key = self._queue_key(job_id)
        added = 0
        for url in urls:
            if self.should_skip(url):
                continue
            if urlparse(url).netloc != base_domain:
                continue
            norm = self.normalize(url)
            h = self.url_hash(norm)
            if not redis_sync.sismember(seen_key, h):
                pipe.sadd(seen_key, h)
                pipe.zadd(queue_key, {norm: self.priority(norm)})
                added += 1
        pipe.execute()
        return added

    def pop_batch_sync(self, redis_sync, job_id: str, batch_size: int = 20) -> List[str]:
        """Pop highest-priority URLs (lowest score) from frontier (sync)."""
        queue_key = self._queue_key(job_id)
        items = redis_sync.zpopmin(queue_key, batch_size)
        # Decode bytes → str if Redis client returns bytes
        return [
            (url.decode("utf-8") if isinstance(url, bytes) else url)
            for url, _ in items
        ]

    def size_sync(self, redis_sync, job_id: str) -> int:
        return redis_sync.zcard(self._queue_key(job_id))

    def cleanup_sync(self, redis_sync, job_id: str):
        redis_sync.delete(self._queue_key(job_id))
        redis_sync.delete(self._seen_key(job_id))

    # ── Async methods (used from FastAPI / async context) ────────────────

    async def push(self, job_id: str, urls: List[str], base_domain: str) -> int:
        r = self._redis.client
        seen_key = self._seen_key(job_id)
        queue_key = self._queue_key(job_id)
        added = 0
        for url in urls:
            if self.should_skip(url):
                continue
            if urlparse(url).netloc != base_domain:
                continue
            norm = self.normalize(url)
            h = self.url_hash(norm)
            if not await r.sismember(seen_key, h):
                await r.sadd(seen_key, h)
                await r.zadd(queue_key, {norm: self.priority(norm)})
                added += 1
        return added

    async def pop_batch(self, job_id: str, batch_size: int = 20) -> List[str]:
        r = self._redis.client
        items = await r.zpopmin(self._queue_key(job_id), batch_size)
        return [url for url, _ in items]

    async def size(self, job_id: str) -> int:
        return await self._redis.client.zcard(self._queue_key(job_id))

    async def cleanup(self, job_id: str):
        r = self._redis.client
        await r.delete(self._queue_key(job_id))
        await r.delete(self._seen_key(job_id))


url_frontier = URLFrontier()
