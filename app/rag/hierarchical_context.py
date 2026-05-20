"""
Hierarchical Context — builds LLM context using parent-child chunk hierarchy.

Instead of concatenating raw chunks, this builds a structured context
that preserves document hierarchy: section headers → content → details.
"""
from typing import Any, Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)


class HierarchicalContext:
    """
    Build structured LLM context from hierarchically retrieved chunks.

    Groups chunks by source document, orders them by chunk_index,
    and formats them with source attribution.
    """

    def build(
        self,
        chunks: List[Dict[str, Any]],
        max_chars: int = 8000,
    ) -> str:
        """
        Build hierarchical context string from chunks.
        Groups by source, orders by chunk_index within each source.
        """
        if not chunks:
            return ""

        # Group by source
        by_source: Dict[str, List[Dict]] = {}
        for chunk in chunks:
            source = chunk.get("source", "unknown")
            by_source.setdefault(source, []).append(chunk)

        # Sort each group by chunk_index
        for source in by_source:
            by_source[source].sort(key=lambda c: c.get("chunk_index", 0))

        parts = []
        total_chars = 0

        for source, source_chunks in by_source.items():
            # Source header
            source_label = source.split("/")[-1] if "/" in source else source
            header = f"[{source_label}]"
            content_parts = []

            for chunk in source_chunks:
                content = chunk.get("content", "").strip()
                if not content:
                    continue
                if total_chars + len(content) > max_chars:
                    # Truncate last chunk to fit
                    remaining = max_chars - total_chars
                    if remaining > 100:
                        content_parts.append(content[:remaining] + "...")
                    break
                content_parts.append(content)
                total_chars += len(content)

            if content_parts:
                parts.append(header + "\n" + "\n\n".join(content_parts))

            if total_chars >= max_chars:
                break

        return "\n\n---\n\n".join(parts)

    def build_for_comparison(
        self,
        entity_chunks: Dict[str, List[Dict[str, Any]]],
        max_chars_per_entity: int = 2000,
    ) -> str:
        """
        Build side-by-side context for comparison queries.
        entity_chunks: {entity_name: [chunks]}
        """
        parts = []
        for entity_name, chunks in entity_chunks.items():
            sorted_chunks = sorted(chunks, key=lambda c: c.get("chunk_index", 0))
            content = "\n\n".join(
                c.get("content", "")[:max_chars_per_entity // len(chunks)]
                for c in sorted_chunks[:3]
            )
            parts.append(f"[{entity_name}]\n{content}")
        return "\n\n===\n\n".join(parts)


hierarchical_context = HierarchicalContext()
