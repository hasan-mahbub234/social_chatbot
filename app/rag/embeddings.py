"""RAG embeddings — wraps embedding service for RAG use."""
from typing import List
from app.services.embedding import embedding_service
from app.core.logging import get_logger

logger = get_logger(__name__)


class RAGEmbeddings:
    """Generate and manage embeddings for RAG pipeline."""

    async def embed_chunks(self, chunks: List[str]) -> List[List[float]]:
        """Embed a list of text chunks."""
        return await embedding_service.embed_batch(chunks)

    async def embed_query(self, query: str) -> List[float]:
        """Embed a search query."""
        return await embedding_service.embed_text(query)

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        return embedding_service._cosine_similarity(vec1, vec2)


rag_embeddings = RAGEmbeddings()
