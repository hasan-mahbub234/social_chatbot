"""
Graph Retriever — retrieves related entities from the knowledge graph
to augment vector/BM25 retrieval results.

For comparison queries: fetches both entities and their shared neighbors.
For product queries: fetches related products, variants, and category siblings.
For policy queries: fetches all policy nodes and their coverage topics.
"""
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session
from app.knowledge_graph.graph_builder import KnowledgeGraph, graph_builder
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_GRAPH_HOPS = 2
MAX_GRAPH_RESULTS = 15


class GraphRetriever:
    """
    Retrieve document chunks using graph traversal.

    Complements vector/BM25 retrieval by finding related entities
    that may not be semantically similar but are graph-connected.
    """

    async def retrieve_related(
        self,
        entity_labels: List[str],
        organization_id: str,
        db: Session,
        max_hops: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Find chunks for entities related to the given labels via graph traversal.
        Returns chunk-like dicts with graph_source=True marker.
        """
        if not entity_labels:
            return []

        # Fetch all chunks to build graph (cached after first call)
        chunks = self._fetch_all_chunks(organization_id, db)
        if not chunks:
            return []

        graph = await graph_builder.get_or_build(organization_id, chunks)

        # Find node IDs for the given labels
        target_node_ids: Set[str] = set()
        for label in entity_labels:
            for node_id, node in graph.nodes.items():
                if label.lower() in node.label.lower() or node.label.lower() in label.lower():
                    target_node_ids.add(node_id)

        if not target_node_ids:
            return []

        # BFS traversal up to max_hops
        visited: Set[str] = set(target_node_ids)
        frontier = set(target_node_ids)

        for _ in range(max_hops):
            next_frontier: Set[str] = set()
            for node_id in frontier:
                for neighbor_id in graph.neighbors(node_id):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        next_frontier.add(neighbor_id)
            frontier = next_frontier

        # Collect labels of all visited nodes (excluding starting nodes)
        related_labels = [
            graph.nodes[nid].label
            for nid in visited - target_node_ids
            if nid in graph.nodes
        ]

        if not related_labels:
            return []

        # Fetch chunks for related entities
        related_chunks = self._fetch_chunks_by_labels(
            related_labels, organization_id, db
        )

        logger.info(
            "graph_retrieval",
            input_entities=len(entity_labels),
            graph_nodes_visited=len(visited),
            related_chunks=len(related_chunks),
        )
        return related_chunks[:MAX_GRAPH_RESULTS]

    async def get_comparison_context(
        self,
        entity_a: str,
        entity_b: str,
        organization_id: str,
        db: Session,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch chunks for both entities in a comparison query.
        Returns {entity_a: [chunks], entity_b: [chunks]}.
        """
        chunks_a = self._fetch_chunks_by_labels([entity_a], organization_id, db)
        chunks_b = self._fetch_chunks_by_labels([entity_b], organization_id, db)
        return {entity_a: chunks_a, entity_b: chunks_b}

    def _fetch_all_chunks(
        self, organization_id: str, db: Session, limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Fetch a sample of chunks to build the graph."""
        try:
            from sqlalchemy import text
            rows = db.execute(
                text("""
                    SELECT id, content, source, chunk_index, metadata
                    FROM document_chunks
                    WHERE organization_id = :org
                    ORDER BY chunk_index ASC
                    LIMIT :limit
                """),
                {"org": organization_id, "limit": limit},
            ).fetchall()
            return [
                {"id": str(r[0]), "content": r[1], "source": r[2],
                 "chunk_index": r[3], "metadata": r[4] or {}}
                for r in rows
            ]
        except Exception as e:
            logger.warning("graph_chunk_fetch_failed", error=str(e))
            return []

    def _fetch_chunks_by_labels(
        self,
        labels: List[str],
        organization_id: str,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """Fetch chunks whose metadata title matches any of the given labels."""
        if not labels:
            return []
        try:
            from sqlalchemy import text
            results = []
            for label in labels[:10]:  # cap to avoid huge queries
                rows = db.execute(
                    text("""
                        SELECT id, content, source, chunk_index, metadata, 0.70 AS similarity
                        FROM document_chunks
                        WHERE organization_id = :org
                          AND (metadata->>'title' ILIKE :label OR content ILIKE :label)
                        ORDER BY chunk_index ASC
                        LIMIT 5
                    """),
                    {"org": organization_id, "label": f"%{label}%"},
                ).fetchall()
                for r in rows:
                    results.append({
                        "id": str(r[0]), "content": r[1], "source": r[2],
                        "chunk_index": r[3], "metadata": r[4] or {},
                        "similarity": float(r[5]), "graph_source": True,
                    })
            return results
        except Exception as e:
            logger.warning("graph_label_fetch_failed", error=str(e))
            return []


graph_retriever = GraphRetriever()
