"""Semantic cache — Redis-backed similarity-based response cache."""
import json
import re
from typing import Optional, Dict, Any, List
from app.core.redis_client import redis_client
from app.cache.cache_keys import semantic_cache_key
from app.services.embedding import embedding_service
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_ENTRIES = 100
CACHE_TTL = 3600  # 1 hour
CACHE_HIT_THRESHOLD = 0.97  # only near-identical queries hit cache


def _extract_entities(text: str) -> frozenset:
    """Extract capitalized words as named entities for cache key scoping."""
    return frozenset(re.findall(r'\b[A-Z][a-z]{2,}\b', text))


class SemanticCache:
    """Cache responses by semantic similarity of queries."""

    async def get(self, query: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return cached response only if semantically near-identical AND same entities."""
        try:
            key = semantic_cache_key(agent_id)
            raw = await redis_client.get(key)
            if not raw:
                return None

            entries: List[Dict] = json.loads(raw)
            query_emb = await embedding_service.embed_text(query)
            query_entities = _extract_entities(query)

            best_match = None
            best_sim = 0.0

            for entry in entries:
                # Entity guard — different named entities = different question
                entry_entities = frozenset(entry.get("entities", []))
                if query_entities and entry_entities and query_entities != entry_entities:
                    continue

                sim = embedding_service._cosine_similarity(query_emb, entry["embedding"])
                if sim > best_sim:
                    best_sim = sim
                    best_match = entry

            if best_match and best_sim >= CACHE_HIT_THRESHOLD:
                logger.info("semantic_cache_hit", similarity=best_sim)
                return {**best_match["response"], "similarity": best_sim}

            return None
        except Exception as e:
            logger.warning("semantic_cache_get_failed", error=str(e))
            return None

    async def set(self, query: str, response: Dict[str, Any], agent_id: str):
        """Cache response with query embedding and extracted entities."""
        try:
            key = semantic_cache_key(agent_id)
            raw = await redis_client.get(key)
            entries: List[Dict] = json.loads(raw) if raw else []

            query_emb = await embedding_service.embed_text(query)
            entities = list(_extract_entities(query))
            entries.append({
                "query": query,
                "embedding": query_emb,
                "entities": entities,
                "response": response,
            })

            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]

            await redis_client.set(key, json.dumps(entries), ex=CACHE_TTL)
            logger.info("semantic_cache_set", agent_id=agent_id)
        except Exception as e:
            logger.warning("semantic_cache_set_failed", error=str(e))

    async def invalidate(self, agent_id: str):
        """Clear all cached entries for an agent."""
        await redis_client.delete(semantic_cache_key(agent_id))

    async def clear_all(self):
        """Clear ALL semantic cache entries across all agents."""
        try:
            keys = await redis_client.client.keys("semantic_cache:*")
            if keys:
                await redis_client.client.delete(*keys)
            logger.info("semantic_cache_cleared_all", keys_deleted=len(keys))
        except Exception as e:
            logger.warning("semantic_cache_clear_all_failed", error=str(e))

    async def stats(self, agent_id: str) -> Dict[str, Any]:
        """Return cache statistics."""
        try:
            raw = await redis_client.get(semantic_cache_key(agent_id))
            if not raw:
                return {"entries": 0, "size_bytes": 0}
            entries = json.loads(raw)
            return {"entries": len(entries), "size_bytes": len(raw)}
        except Exception:
            return {"entries": 0, "size_bytes": 0}


semantic_cache = SemanticCache()
