"""Context builder — formats RAG results into LLM-ready context."""
from typing import List, Dict, Any


class ContextBuilder:
    """Build formatted context string from RAG results."""

    def build(self, results: List[Dict[str, Any]], max_tokens: int = 3000) -> str:
        """Build context string from retrieved chunks."""
        if not results:
            return ""

        parts = []
        total_chars = 0
        char_limit = max_tokens * 4  # ~4 chars per token

        for i, result in enumerate(results):
            content = result.get("content", "")
            source = result.get("source", "")
            similarity = result.get("similarity", 0)

            chunk = f"[Source {i+1}: {source} (relevance: {similarity:.2f})]\n{content}"

            if total_chars + len(chunk) > char_limit:
                break

            parts.append(chunk)
            total_chars += len(chunk)

        return "\n\n---\n\n".join(parts)

    def build_citations(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build citation metadata from results."""
        return {
            str(i): {
                "source": r.get("source", ""),
                "similarity": r.get("similarity", 0),
                "chunk_index": r.get("chunk_index", 0),
            }
            for i, r in enumerate(results)
        }


context_builder = ContextBuilder()
