"""Embedding service — OpenAI in production, sentence-transformers in development."""
import math
import json
from typing import List, Tuple, Optional
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton — loaded once per process, never reloaded
_LOCAL_MODEL = None


def _get_local_model():
    """Return the singleton SentenceTransformer, loading it once on first call."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = settings.LOCAL_EMBEDDING_MODEL
            _LOCAL_MODEL = SentenceTransformer(model_name)
            logger.info("local_embedding_model_loaded", model=model_name)
        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
    return _LOCAL_MODEL


class EmbeddingService:
    """Unified embedding service — OpenAI or local sentence-transformers."""

    def __init__(self):
        self._openai_client = None

    @property
    def _is_local(self) -> bool:
        return settings.AI_PROVIDER == "groq" or settings.EMBEDDING_PROVIDER == "local"

    def _get_openai(self):
        if self._openai_client is None:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        try:
            if self._is_local:
                return _get_local_model().encode(text, convert_to_numpy=True).tolist()
            else:
                client = self._get_openai()
                response = await client.embeddings.create(
                    input=text, model=settings.OPENAI_EMBEDDINGS_MODEL
                )
                return response.data[0].embedding
        except Exception as e:
            logger.error("embed_text_failed", error=str(e))
            raise

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        try:
            if self._is_local:
                return _get_local_model().encode(texts, convert_to_numpy=True).tolist()
            else:
                client = self._get_openai()
                response = await client.embeddings.create(
                    input=texts, model=settings.OPENAI_EMBEDDINGS_MODEL
                )
                return [item.embedding for item in response.data]
        except Exception as e:
            logger.error("embed_batch_failed", error=str(e))
            raise

    async def similarity_search(
        self, query: str, documents: List[str], threshold: float = None
    ) -> List[Tuple[str, float]]:
        """Find similar documents to query."""
        threshold = threshold or settings.SIMILARITY_THRESHOLD
        query_emb = await self.embed_text(query)
        doc_embs = await self.embed_batch(documents)
        results = [
            (doc, self._cosine_similarity(query_emb, emb))
            for doc, emb in zip(documents, doc_embs)
            if self._cosine_similarity(query_emb, emb) >= threshold
        ]
        return sorted(results, key=lambda x: x[1], reverse=True)

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)

    async def cache_embedding(self, key: str, embedding: List[float]):
        try:
            from app.core.redis_client import redis_client
            await redis_client.set(f"embedding:{key}", json.dumps(embedding), ex=86400)
        except Exception as e:
            logger.warning("embedding_cache_failed", error=str(e))

    async def get_cached_embedding(self, key: str) -> Optional[List[float]]:
        try:
            from app.core.redis_client import redis_client
            cached = await redis_client.get(f"embedding:{key}")
            return json.loads(cached) if cached else None
        except Exception:
            return None


embedding_service = EmbeddingService()
