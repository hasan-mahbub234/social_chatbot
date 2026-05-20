"""
Graph Reasoner — uses the knowledge graph to answer relationship,
comparison, and compatibility queries that pure vector retrieval struggles with.

Examples:
  "What products are similar to Wave Riders Swim Shorts?"
  → graph traversal: Wave Riders → related_to → [other swim shorts]

  "Which hoodie goes with navy joggers?"
  → graph traversal: navy joggers → compatible_with → [hoodies]

  "What category does the Turaag Active polo belong to?"
  → graph traversal: polo → belongs_to → [polo shirts, topwear]
"""
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.knowledge_graph.graph_builder import graph_builder, KnowledgeGraph
from app.knowledge_graph.graph_retriever import graph_retriever
from app.core.logging import get_logger

logger = get_logger(__name__)


class GraphReasoner:
    """
    Answer relationship queries using graph traversal.

    Produces structured reasoning context that the LLM can use
    to answer comparison, compatibility, and recommendation queries.
    """

    async def reason(
        self,
        query: str,
        entities: List[str],
        organization_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Perform graph-based reasoning for a query.

        Returns:
          {
            "reasoning_type": "comparison" | "recommendation" | "relationship",
            "graph_context": str,       # formatted context for LLM injection
            "related_entities": [...],
            "reasoning_path": [...],    # how we got to the answer
          }
        """
        if not entities:
            return {"reasoning_type": "none", "graph_context": "", "related_entities": []}

        query_lower = query.lower()

        # Comparison query
        if len(entities) >= 2 and any(k in query_lower for k in ("vs", "versus", "compare", "difference", "better")):
            return await self._comparison_reason(entities[0], entities[1], organization_id, db)

        # Recommendation query
        if any(k in query_lower for k in ("similar", "like", "recommend", "alternative", "other")):
            return await self._recommendation_reason(entities[0], organization_id, db)

        # Relationship query
        if any(k in query_lower for k in ("goes with", "pairs with", "compatible", "match")):
            return await self._compatibility_reason(entities[0], organization_id, db)

        # Default: fetch related entities
        related_chunks = await graph_retriever.retrieve_related(entities, organization_id, db)
        graph_context = self._format_context(related_chunks)
        return {
            "reasoning_type": "related",
            "graph_context": graph_context,
            "related_entities": [c.get("metadata", {}).get("title", "") for c in related_chunks[:5]],
            "reasoning_path": [f"entity:{e}" for e in entities],
        }

    async def _comparison_reason(
        self,
        entity_a: str,
        entity_b: str,
        organization_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Build side-by-side comparison context."""
        context_map = await graph_retriever.get_comparison_context(
            entity_a, entity_b, organization_id, db
        )
        parts = []
        for entity, chunks in context_map.items():
            if chunks:
                content = "\n".join(c["content"][:400] for c in chunks[:2])
                parts.append(f"[{entity}]\n{content}")

        graph_context = "\n\n===\n\n".join(parts) if parts else ""
        return {
            "reasoning_type": "comparison",
            "graph_context": graph_context,
            "related_entities": [entity_a, entity_b],
            "reasoning_path": [f"compare:{entity_a}", f"compare:{entity_b}"],
        }

    async def _recommendation_reason(
        self,
        entity: str,
        organization_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Find similar/related products via graph."""
        related_chunks = await graph_retriever.retrieve_related(
            [entity], organization_id, db, max_hops=1
        )
        graph_context = self._format_context(related_chunks)
        related = list({c.get("metadata", {}).get("title", "") for c in related_chunks if c.get("metadata", {}).get("title")})
        return {
            "reasoning_type": "recommendation",
            "graph_context": graph_context,
            "related_entities": related[:5],
            "reasoning_path": [f"similar_to:{entity}"],
        }

    async def _compatibility_reason(
        self,
        entity: str,
        organization_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Find compatible/pairing products via graph."""
        related_chunks = await graph_retriever.retrieve_related(
            [entity], organization_id, db, max_hops=1
        )
        # Filter to compatible_with edges only
        compatible_chunks = [
            c for c in related_chunks
            if c.get("graph_source") and "compatible" in str(c.get("metadata", {}))
        ] or related_chunks  # fallback to all related

        graph_context = self._format_context(compatible_chunks)
        return {
            "reasoning_type": "compatibility",
            "graph_context": graph_context,
            "related_entities": [c.get("metadata", {}).get("title", "") for c in compatible_chunks[:5]],
            "reasoning_path": [f"compatible_with:{entity}"],
        }

    def _format_context(self, chunks: List[Dict[str, Any]]) -> str:
        if not chunks:
            return ""
        parts = []
        for chunk in chunks[:5]:
            title = chunk.get("metadata", {}).get("title", "")
            content = chunk.get("content", "")[:300]
            label = f"[{title}]" if title else "[Related]"
            parts.append(f"{label}\n{content}")
        return "\n\n".join(parts)


graph_reasoner = GraphReasoner()
