"""
Graph Builder — constructs an in-memory entity relationship graph from
document chunks and product entities.

Nodes: products, categories, brands, policies, FAQs
Edges: belongs_to, related_to, has_variant, compatible_with, mentioned_with

The graph is built per-organization and cached in Redis.
Used by graph_retriever for relationship-aware retrieval and
graph_ranker for affinity scoring.
"""
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_CACHE_TTL = 3600          # 1 hour
GRAPH_CACHE_KEY = "knowledge_graph:{org_id}"


class GraphNode:
    __slots__ = ("node_id", "node_type", "label", "metadata")

    def __init__(self, node_id: str, node_type: str, label: str, metadata: Dict = None):
        self.node_id = node_id
        self.node_type = node_type      # product | category | brand | policy | faq
        self.label = label
        self.metadata = metadata or {}


class GraphEdge:
    __slots__ = ("source_id", "target_id", "relation", "weight")

    def __init__(self, source_id: str, target_id: str, relation: str, weight: float = 1.0):
        self.source_id = source_id
        self.target_id = target_id
        self.relation = relation        # belongs_to | related_to | has_variant | mentioned_with
        self.weight = weight


class KnowledgeGraph:
    """In-memory knowledge graph for an organization."""

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        # Adjacency: node_id → {neighbor_id: relation}
        self._adj: Dict[str, Dict[str, str]] = {}

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node
        if node.node_id not in self._adj:
            self._adj[node.node_id] = {}

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)
        self._adj.setdefault(edge.source_id, {})[edge.target_id] = edge.relation
        self._adj.setdefault(edge.target_id, {})[edge.source_id] = edge.relation

    def neighbors(self, node_id: str) -> Dict[str, str]:
        """Return {neighbor_id: relation} for a node."""
        return self._adj.get(node_id, {})

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [
                {"id": n.node_id, "type": n.node_type, "label": n.label, "meta": n.metadata}
                for n in self.nodes.values()
            ],
            "edges": [
                {"src": e.source_id, "tgt": e.target_id, "rel": e.relation, "w": e.weight}
                for e in self.edges
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeGraph":
        g = cls()
        for n in data.get("nodes", []):
            g.add_node(GraphNode(n["id"], n["type"], n["label"], n.get("meta", {})))
        for e in data.get("edges", []):
            g.add_edge(GraphEdge(e["src"], e["tgt"], e["rel"], e.get("w", 1.0)))
        return g


class GraphBuilder:
    """
    Build a KnowledgeGraph from document chunks.

    Extracts entities and relationships from chunk metadata and content,
    then caches the graph in Redis per organization.
    """

    def _node_id(self, label: str, node_type: str) -> str:
        clean = re.sub(r'[^a-z0-9]', '_', label.lower().strip())
        return f"{node_type}:{clean}"

    def build_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        organization_id: str,
    ) -> KnowledgeGraph:
        """Build graph from a list of document chunks."""
        graph = KnowledgeGraph()
        seen_pairs: Set[Tuple[str, str]] = set()

        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            content = chunk.get("content", "")
            source = chunk.get("source", "")

            # Product node
            title = meta.get("title", "")
            if title:
                product_id = self._node_id(title, "product")
                graph.add_node(GraphNode(
                    node_id=product_id,
                    node_type="product",
                    label=title,
                    metadata={"url": source, "sku": meta.get("sku", "")},
                ))

                # Brand node + edge
                brand = meta.get("brand", "")
                if brand:
                    brand_id = self._node_id(brand, "brand")
                    graph.add_node(GraphNode(brand_id, "brand", brand))
                    pair = (product_id, brand_id)
                    if pair not in seen_pairs:
                        graph.add_edge(GraphEdge(product_id, brand_id, "made_by", 0.9))
                        seen_pairs.add(pair)

                # Category node + edge
                product_type = meta.get("product_type", "") or meta.get("type", "")
                if product_type and product_type not in ("product", "page"):
                    cat_id = self._node_id(product_type, "category")
                    graph.add_node(GraphNode(cat_id, "category", product_type))
                    pair = (product_id, cat_id)
                    if pair not in seen_pairs:
                        graph.add_edge(GraphEdge(product_id, cat_id, "belongs_to", 0.8))
                        seen_pairs.add(pair)

                # Co-mention edges: products mentioned together in same chunk
                mentioned = self._extract_product_mentions(content)
                for mention in mentioned:
                    if mention.lower() != title.lower():
                        mention_id = self._node_id(mention, "product")
                        graph.add_node(GraphNode(mention_id, "product", mention))
                        pair = tuple(sorted([product_id, mention_id]))
                        if pair not in seen_pairs:
                            graph.add_edge(GraphEdge(product_id, mention_id, "mentioned_with", 0.4))
                            seen_pairs.add(pair)

            # Policy / FAQ nodes
            chunk_type = meta.get("chunk_type", "")
            if chunk_type == "faq" and content:
                faq_id = self._node_id(content[:40], "faq")
                graph.add_node(GraphNode(faq_id, "faq", content[:60]))

            elif chunk_type in ("documentation", "text") and any(
                kw in content.lower() for kw in ("policy", "return", "shipping", "warranty")
            ):
                policy_label = self._extract_policy_label(content)
                if policy_label:
                    policy_id = self._node_id(policy_label, "policy")
                    graph.add_node(GraphNode(policy_id, "policy", policy_label))

        logger.info(
            "knowledge_graph_built",
            org=organization_id,
            nodes=len(graph.nodes),
            edges=len(graph.edges),
        )
        return graph

    def _extract_product_mentions(self, content: str) -> List[str]:
        """Extract Title Case product names from content."""
        return [
            m.group(0) for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b', content)
            if len(m.group(0)) > 5
        ][:5]

    def _extract_policy_label(self, content: str) -> str:
        for kw in ("return policy", "shipping policy", "warranty policy", "refund policy"):
            if kw in content.lower():
                return kw.title()
        return ""

    async def get_or_build(
        self,
        organization_id: str,
        chunks: List[Dict[str, Any]],
    ) -> KnowledgeGraph:
        """Return cached graph or build and cache a new one."""
        cache_key = GRAPH_CACHE_KEY.format(org_id=organization_id)
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(cache_key)
            if raw:
                return KnowledgeGraph.from_dict(json.loads(raw))
        except Exception:
            pass

        graph = self.build_from_chunks(chunks, organization_id)

        try:
            from app.core.redis_client import redis_client
            await redis_client.set(cache_key, json.dumps(graph.to_dict()), ex=GRAPH_CACHE_TTL)
        except Exception:
            pass

        return graph

    async def invalidate(self, organization_id: str) -> None:
        """Invalidate cached graph (call after re-crawl or re-ingest)."""
        try:
            from app.core.redis_client import redis_client
            await redis_client.delete(GRAPH_CACHE_KEY.format(org_id=organization_id))
        except Exception:
            pass


graph_builder = GraphBuilder()
