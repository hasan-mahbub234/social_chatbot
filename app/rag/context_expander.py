"""
Context Expander — expands retrieved chunks with surrounding context.

When a retrieved chunk is too short or references surrounding content,
this expander fetches adjacent chunks to provide complete context.

Used for:
  - Policy documents (need full section, not just a sentence)
  - FAQ answers (need both Q and A)
  - Product specs (need full spec block)
  - Tables (need header row + data rows)
"""
from typing import Any, Dict, List
from sqlalchemy.orm import Session
from app.core.logging import get_logger

logger = get_logger(__name__)

# Chunks shorter than this are candidates for expansion
SHORT_CHUNK_THRESHOLD = 200

# Chunk types that always benefit from expansion
ALWAYS_EXPAND_TYPES = {"table", "faq", "documentation"}


class ContextExpander:
    """
    Expand short or incomplete chunks with surrounding context.
    """

    def expand(
        self,
        chunks: List[Dict[str, Any]],
        organization_id: str,
        db: Session,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Expand chunks that need more context.
        Returns expanded chunks (content may be longer).
        """
        from app.rag.parent_retriever import parent_retriever

        expanded = []
        for chunk in chunks:
            content = chunk.get("content", "")
            meta = chunk.get("metadata") or {}
            chunk_type = meta.get("chunk_type", "text")

            should_expand = (
                force
                or len(content) < SHORT_CHUNK_THRESHOLD
                or chunk_type in ALWAYS_EXPAND_TYPES
            )

            if should_expand and chunk.get("source"):
                expanded_content = parent_retriever.expand_with_siblings(
                    chunk=chunk,
                    organization_id=organization_id,
                    db=db,
                    window=1,
                )
                if len(expanded_content) > len(content):
                    expanded_chunk = {**chunk, "content": expanded_content, "expanded": True}
                    expanded.append(expanded_chunk)
                    continue

            expanded.append(chunk)

        return expanded

    def should_expand(self, chunk: Dict[str, Any]) -> bool:
        """Check if a chunk should be expanded."""
        content = chunk.get("content", "")
        meta = chunk.get("metadata") or {}
        chunk_type = meta.get("chunk_type", "text")
        return len(content) < SHORT_CHUNK_THRESHOLD or chunk_type in ALWAYS_EXPAND_TYPES


context_expander = ContextExpander()
