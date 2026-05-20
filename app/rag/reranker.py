"""
Reranker — cross-encoder for production accuracy, embedding fallback for dev.

Cross-encoder vs embedding similarity:
  Embedding:     query_vector ↔ chunk_vector  (independent, approximate)
  Cross-encoder: (query + chunk) → relevance  (joint, much more accurate)

Provider strategy:
  AI_PROVIDER=groq  (dev)  → BAAI/bge-reranker-base  (local, free, sentence-transformers)
  AI_PROVIDER=openai (prod) → BAAI/bge-reranker-base  (same — Cohere optional upgrade)

The old reranker re-embedded all chunks and computed cosine similarity again.
That gave zero accuracy gain over the vector store result — just added latency.
"""
from typing import List, Dict, Any
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Singleton cross-encoder — loaded once per process
_CROSS_ENCODER = None
_CROSS_ENCODER_LOAD_ATTEMPTED = False


def _get_cross_encoder():
    """Return singleton CrossEncoder, loading it once on first call."""
    global _CROSS_ENCODER, _CROSS_ENCODER_LOAD_ATTEMPTED
    if _CROSS_ENCODER_LOAD_ATTEMPTED:
        return _CROSS_ENCODER
    _CROSS_ENCODER_LOAD_ATTEMPTED = True
    try:
        from sentence_transformers import CrossEncoder
        _CROSS_ENCODER = CrossEncoder(
            "BAAI/bge-reranker-base",
            max_length=512,
        )
        logger.info("cross_encoder_loaded", model="BAAI/bge-reranker-base")
    except ImportError:
        logger.warning(
            "cross_encoder_unavailable",
            reason="sentence-transformers not installed — run: pip install sentence-transformers",
        )
    except Exception as e:
        logger.warning("cross_encoder_load_failed", error=str(e))
    return _CROSS_ENCODER


class Reranker:
    """
    Cross-encoder reranker.

    Scores each (query, chunk) pair jointly — fundamentally different from
    embedding similarity which scores query and chunk independently.

    Falls back to sorting by existing similarity score (no re-embedding)
    when the cross-encoder is unavailable. This is still better than the
    old approach of re-embedding everything.
    """

    async def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Rerank results using cross-encoder. Falls back to similarity sort."""
        if not results:
            return []

        model = _get_cross_encoder()

        if model is not None:
            return self._cross_encode(query, results, top_k, model)

        # Fallback: sort by existing similarity score — no re-embedding
        logger.debug("reranker_fallback_similarity_sort")
        return sorted(
            results,
            key=lambda x: x.get("similarity", 0),
            reverse=True,
        )[:top_k]

    def _cross_encode(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int,
        model,
    ) -> List[Dict[str, Any]]:
        """Score (query, chunk) pairs jointly using cross-encoder."""
        try:
            # Truncate chunk content to 400 chars for speed — cross-encoder
            # is most useful for the first ~300 chars of each chunk
            pairs = [(query, r["content"][:400]) for r in results]
            scores = model.predict(pairs)

            for result, score in zip(results, scores):
                result["rerank_score"] = float(score)

            reranked = sorted(
                results,
                key=lambda x: x.get("rerank_score", 0),
                reverse=True,
            )
            logger.debug(
                "cross_encoder_reranked",
                input_count=len(results),
                output_count=min(top_k, len(reranked)),
                top_score=round(reranked[0]["rerank_score"], 3) if reranked else 0,
            )
            return reranked[:top_k]

        except Exception as e:
            logger.warning("cross_encoder_predict_failed", error=str(e))
            return sorted(
                results,
                key=lambda x: x.get("similarity", 0),
                reverse=True,
            )[:top_k]


reranker = Reranker()
