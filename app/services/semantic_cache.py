"""Semantic cache service for intelligent response caching."""
from app.services.embedding import embedding_service
from app.core.redis_client import redis_client
from app.core.config import settings
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SemanticCacheService:
    """Service for semantic caching of responses."""

    async def get_cached_response(
        self, query: str, agent_id: str, similarity_threshold: float = None
    ) -> Optional[Dict[str, Any]]:
        """Get cached response for semantically similar query."""
        if similarity_threshold is None:
            similarity_threshold = settings.SIMILARITY_THRESHOLD

        try:
            # Generate embedding for query
            query_embedding = await embedding_service.embed_text(query)

            # Get cached queries for this agent
            cache_key = f"semantic_cache:{agent_id}"
            cached_queries = await redis_client.get(cache_key)

            if not cached_queries:
                return None

            cached_data = json.loads(cached_queries)

            # Find best matching cached response
            best_match = None
            best_similarity = 0

            for cached_item in cached_data:
                similarity = embedding_service._cosine_similarity(
                    query_embedding, cached_item["embedding"]
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = cached_item

            # Return best match if above threshold
            if best_match and best_similarity >= similarity_threshold:
                logger.info(
                    f"Semantic cache hit with similarity {best_similarity:.2f}"
                )
                return {
                    "response": best_match["response"],
                    "similarity": best_similarity,
                    "cached": True,
                }

            return None
        except Exception as e:
            logger.error(f"Error retrieving cached response: {e}")
            return None

    async def cache_response(
        self,
        query: str,
        response: str,
        agent_id: str,
        metadata: Dict[str, Any] = None,
    ):
        """Cache response with semantic embedding."""
        try:
            # Generate embedding for query
            query_embedding = await embedding_service.embed_text(query)

            # Get existing cache for agent
            cache_key = f"semantic_cache:{agent_id}"
            cached_queries = await redis_client.get(cache_key)

            if cached_queries:
                cached_data = json.loads(cached_queries)
            else:
                cached_data = []

            # Add new entry
            cached_data.append({
                "query": query,
                "response": response,
                "embedding": query_embedding,
                "metadata": metadata or {},
            })

            # Keep only last 100 entries per agent
            if len(cached_data) > 100:
                cached_data = cached_data[-100:]

            # Cache with 24-hour expiry
            await redis_client.set(
                cache_key, json.dumps(cached_data), ex=86400
            )

            logger.info(f"Response cached for agent {agent_id}")
        except Exception as e:
            logger.error(f"Error caching response: {e}")

    async def clear_cache(self, agent_id: str):
        """Clear semantic cache for agent."""
        try:
            cache_key = f"semantic_cache:{agent_id}"
            await redis_client.delete(cache_key)
            logger.info(f"Cleared semantic cache for agent {agent_id}")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")

    async def get_cache_stats(self, agent_id: str) -> Dict[str, Any]:
        """Get cache statistics for agent."""
        try:
            cache_key = f"semantic_cache:{agent_id}"
            cached_queries = await redis_client.get(cache_key)

            if not cached_queries:
                return {"size": 0, "entries": 0}

            cached_data = json.loads(cached_queries)
            return {
                "size": len(json.dumps(cached_data)),
                "entries": len(cached_data),
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}


# Global semantic cache service instance
semantic_cache_service = SemanticCacheService()
