"""
LLM Fallback Structured Extraction Layer

Used ONLY when all structured extraction passes (JSON-LD, hydration, network
intercept, DOM scan) fail to produce a complete entity.

Design principles:
  - Cost gate: only called when completeness score < threshold after all other passes
  - Token budget: HTML is truncated to 3000 chars of visible text before sending
  - Structured output: requests JSON with a fixed schema
  - Caching: LLM results are cached by content hash to avoid re-extraction
  - Provider-aware: uses the configured AI provider (OpenAI or Groq)
"""
from __future__ import annotations
import hashlib
import json
import re
from typing import Any, Dict, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# Only call LLM if completeness score is below this threshold
LLM_TRIGGER_THRESHOLD = 0.50

# Max visible text chars to send to LLM (controls token cost)
MAX_TEXT_CHARS = 3000

EXTRACTION_PROMPT = """\
You are a product data extraction assistant. Extract structured product information from the text below.

Return ONLY a valid JSON object with these fields (omit fields you cannot find):
{
  "title": "product name",
  "price": 0.00,
  "currency": "USD",
  "availability": "In Stock or Out of Stock",
  "brand": "brand name",
  "sku": "SKU code",
  "product_type": "category",
  "description": "product description",
  "material": "material/fabric",
  "color": "color options",
  "size_options": "available sizes",
  "shipping_info": "shipping details",
  "return_policy": "return/exchange policy",
  "care_instructions": "care/wash instructions",
  "variants": [
    {"sku": "", "title": "Size/Color", "price": 0.00, "available": true}
  ]
}

Product page text:
{text}
"""


class LLMExtractor:
    """
    Fallback LLM-based structured extraction.
    Only invoked when completeness score is below LLM_TRIGGER_THRESHOLD.
    """

    def __init__(self):
        self._cache: Dict[str, Dict] = {}   # content_hash → extracted dict

    async def extract(
        self,
        html: str,
        url: str,
        entity=None,   # ProductEntity — used to check if LLM is worth calling
    ) -> Optional[Dict]:
        """
        Extract product data using LLM.
        Returns entity merge dict or None if extraction fails / not warranted.
        """
        from app.crawler.completeness_engine import CompletenessScore
        if entity is not None:
            score = CompletenessScore(entity)
            if score.total >= LLM_TRIGGER_THRESHOLD:
                logger.debug("llm_extractor_skipped", url=url, score=score.total)
                return None

        visible_text = self._extract_visible_text(html)
        if len(visible_text) < 100:
            return None

        # Cache check
        content_hash = hashlib.md5(visible_text[:2000].encode()).hexdigest()
        if content_hash in self._cache:
            logger.debug("llm_extractor_cache_hit", url=url)
            return self._cache[content_hash]

        truncated = visible_text[:MAX_TEXT_CHARS]
        prompt = EXTRACTION_PROMPT.format(text=truncated)

        try:
            result = await self._call_llm(prompt, url)
            if result:
                self._cache[content_hash] = result
                logger.info("llm_extractor_success", url=url, fields=list(result.keys()))
            return result
        except Exception as e:
            logger.warning("llm_extractor_failed", url=url, error=str(e))
            return None

    async def _call_llm(self, prompt: str, url: str) -> Optional[Dict]:
        """Call the configured LLM provider and parse JSON response."""
        from app.core.config import settings

        if settings.AI_PROVIDER == "groq" and settings.GROQ_API_KEY:
            return await self._call_groq(prompt)
        elif settings.OPENAI_API_KEY:
            return await self._call_openai(prompt)
        else:
            logger.warning("llm_extractor_no_provider_configured")
            return None

    async def _call_openai(self, prompt: str) -> Optional[Dict]:
        from app.core.config import settings
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": settings.OPENAI_MINI_MODEL,   # gpt-4o-mini for cost efficiency
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 1000,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse_json_response(content)

    async def _call_groq(self, prompt: str) -> Optional[Dict]:
        from app.core.config import settings
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": settings.GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 1000,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse_json_response(content)

    def _parse_json_response(self, content: str) -> Optional[Dict]:
        """Parse LLM response, handling markdown code blocks."""
        # Strip markdown code fences
        content = re.sub(r"```(?:json)?\s*", "", content).strip()
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                return None
            # Validate: must have at least title or price
            if not data.get("title") and not data.get("price"):
                return None
            return data
        except json.JSONDecodeError:
            # Try to extract JSON from mixed content
            match = re.search(r'\{.*\}', content, re.S)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return None

    def _extract_visible_text(self, html: str) -> str:
        """Extract clean visible text from HTML for LLM input."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "nav", "footer",
                             "header", "aside", "form", "iframe", "svg"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            # Collapse excessive whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text
        except Exception:
            # Fallback: strip tags with regex
            text = re.sub(r'<[^>]+>', ' ', html)
            return re.sub(r'\s+', ' ', text).strip()


llm_extractor = LLMExtractor()
