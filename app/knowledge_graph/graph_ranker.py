"""
Graph Ranker — re-ranks retrieval results using graph connectivity signals.

Products with more graph connections (related products, collection memberships,
brand associations) are ranked higher because they are more central to the
knowledge base and more likely to be relevant.

Ranking formula:
  final_score = relevance × 0.55 + completeness × 0.35 + graph_boost × 0.10
  graph_boost = min(0.10, neighbor_count × 0.02)
"""
from typing import Any, Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)


class GraphRanker:
    """
    Re-rank retrieval results using graph connectivity.

    Chunks from highly-connected entities (many graph neighbors)
    receive a small boost. This rewards content that is well-integrated
    into the knowledge base over isolated chunks.
    """

    def rerank(
        self,
        chunks: List[Dict[str, Any]],
        graph_neighbors: Dict[str, int],
    ) -> List[Dict[str, Any]]:
        """
        Re-rank chunks using graph neighbor counts.

        Args:
            chunks: retrieval results with 'similarity' scores
            graph_neighbors: {node_id_or_title: neighbor_count}

        Returns:
            chunks sorted by graph-boosted score, descending
        """
        if not chunks or not graph_neighbors:
            return chunks

        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            title = str(meta.get("title", "")).lower().strip()
            source = chunk.get("source", "")

            # Look up neighbor count by title or source
            neighbor_count = 0
            for key, count in graph_neighbors.items():
                if key.lower() in title or key.lower() in source.lower():
                    neighbor_count = max(neighbor_count, count)

            graph_boost = min(0.10, neighbor_count * 0.02)
            base_similarity = chunk.get("similarity", 0.0)
            chunk["graph_boost"] = graph_boost
            chunk["graph_score"] = base_similarity + graph_boost

        ranked = sorted(chunks, key=lambda c: c.get("graph_score", c.get("similarity", 0)), reverse=True)

        logger.debug(
            "graph_reranked",
            total=len(ranked),
            boosted=sum(1 for c in ranked if c.get("graph_boost", 0) > 0),
        )
        return ranked

    def get_neighbor_counts(
        self,
        chunks: List[Dict[str, Any]],
        organization_id: str,
    ) -> Dict[str, int]:
        """
        Get graph neighbor counts for chunk entities.
        Uses the entity_graph from the crawler module (already wired).
        """
        counts: Dict[str, int] = {}
        try:
            from app.crawler.entity_graph import entity_graph
            for chunk in chunks:
                meta = chunk.get("metadata") or {}
                title = meta.get("title", "")
                if not title:
                    continue
                node_id = entity_graph._url_to_node_id(chunk.get("source", ""))
                neighbors = entity_graph.get_neighbors(organization_id, node_id, max_depth=1)
                counts[title] = len(neighbors)
        except Exception:
            pass
        return counts


graph_ranker = GraphRanker()
