"""Embedding service — wraps sentence-transformers for local embeddings."""
from sentence_transformers import SentenceTransformer
from typing import List
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """Local embedding generation using sentence-transformers."""

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            logger.info("embedding_model_loaded", model=settings.EMBEDDING_MODEL)
        return self._model

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        return self.model.encode(text, convert_to_numpy=True).tolist()

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return [e.tolist() for e in self.model.encode(texts, convert_to_numpy=True)]

    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Cosine similarity between two vectors."""
        import math
        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)


embedding_service_v2 = EmbeddingService()
