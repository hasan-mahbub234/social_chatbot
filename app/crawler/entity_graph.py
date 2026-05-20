"""
Entity Graph Layer — product ↔ variants ↔ collections ↔ reviews ↔ API endpoints

Maintains an in-memory + Redis-backed graph of product relationships.
Supports:
  - product → variant edges (by SKU)
  - product → collection edges
  - product → related products (cross-sell, upsell)
  - canonical entity linking (dedup by handle/SKU)
  - shared SKU detection across pages
  - graph traversal for context-enriched retrieval
"""
from __future__ import annotations
import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_KEY_PREFIX = "entity_graph"
GRAPH_TTL = 86400 * 7   # 7 days


class EdgeType(str, Enum):
    HAS_VARIANT    = "has_variant"
    IN_COLLECTION  = "in_collection"
    RELATED_TO     = "related_to"
    SHARES_SKU     = "shares_sku"
    CROSS_SELL     = "cross_sell"
    UPSELL         = "upsell"
    HAS_REVIEW     = "has_review"
    SERVED_BY_API  = "served_by_api"


@dataclass
class GraphNode:
    node_id: str
    node_type: str          # product | variant | collection | review | api_endpoint
    url: str
    canonical_url: str
    title: str = ""
    sku: str = ""
    handle: str = ""
    organization_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class EntityGraph:
    """
    Product entity graph with Redis persistence.

    Graph structure (per org):
      Nodes: products, variants, collections, reviews, api_endpoints
      Edges: typed relationships with weights

    Redis keys:
      entity_graph:{org}:node:{node_id}       → node JSON
      entity_graph:{org}:edges:{node_id}      → set of edge JSONs
      entity_graph:{org}:sku_index:{sku}      → set of node_ids
      entity_graph:{org}:handle_index:{handle}→ node_id
      entity_graph:{org}:collection:{coll_id} → set of product node_ids
    """

    def __init__(self):
        self._local_nodes: Dict[str, Dict[str, GraphNode]] = {}   # org → node_id → node
        self._local_edges: Dict[str, Dict[str, List[GraphEdge]]] = {}  # org → node_id → edges

    # ── Node management ───────────────────────────────────────────────────────

    def add_node(self, org_id: str, node: GraphNode) -> str:
        """Add or update a node. Returns node_id."""
        self._local_nodes.setdefault(org_id, {})[node.node_id] = node
        self._persist_node(org_id, node)
        return node.node_id

    def get_node(self, org_id: str, node_id: str) -> Optional[GraphNode]:
        local = self._local_nodes.get(org_id, {}).get(node_id)
        if local:
            return local
        return self._load_node(org_id, node_id)

    def get_node_by_url(self, org_id: str, url: str) -> Optional[GraphNode]:
        node_id = self._url_to_node_id(url)
        return self.get_node(org_id, node_id)

    def get_node_by_handle(self, org_id: str, handle: str) -> Optional[GraphNode]:
        """Resolve canonical node by Shopify handle."""
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:handle_index:{handle}"
            node_id = r.get(key)
            if node_id:
                nid = node_id.decode() if isinstance(node_id, bytes) else node_id
                return self.get_node(org_id, nid)
        except Exception:
            pass
        # Fallback: scan local
        for node in self._local_nodes.get(org_id, {}).values():
            if node.handle == handle:
                return node
        return None

    # ── Edge management ───────────────────────────────────────────────────────

    def add_edge(self, org_id: str, edge: GraphEdge):
        """Add a directed edge between two nodes."""
        self._local_edges.setdefault(org_id, {}).setdefault(edge.source_id, []).append(edge)
        self._persist_edge(org_id, edge)

    def get_edges(
        self,
        org_id: str,
        node_id: str,
        edge_type: Optional[EdgeType] = None,
    ) -> List[GraphEdge]:
        """Get all edges from a node, optionally filtered by type."""
        local = self._local_edges.get(org_id, {}).get(node_id, [])
        if not local:
            local = self._load_edges(org_id, node_id)
        if edge_type:
            return [e for e in local if e.edge_type == edge_type]
        return local

    def get_neighbors(
        self,
        org_id: str,
        node_id: str,
        edge_type: Optional[EdgeType] = None,
        max_depth: int = 1,
    ) -> List[GraphNode]:
        """BFS traversal from node_id up to max_depth hops."""
        visited: Set[str] = {node_id}
        frontier = [node_id]
        result: List[GraphNode] = []

        for _ in range(max_depth):
            next_frontier = []
            for nid in frontier:
                for edge in self.get_edges(org_id, nid, edge_type):
                    if edge.target_id not in visited:
                        visited.add(edge.target_id)
                        next_frontier.append(edge.target_id)
                        node = self.get_node(org_id, edge.target_id)
                        if node:
                            result.append(node)
            frontier = next_frontier
            if not frontier:
                break

        return result

    # ── Product-specific operations ───────────────────────────────────────────

    def register_product(
        self,
        org_id: str,
        url: str,
        title: str,
        handle: str = "",
        sku: str = "",
        collection_urls: Optional[List[str]] = None,
        related_urls: Optional[List[str]] = None,
        api_endpoints: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> GraphNode:
        """Register a product and all its relationships in the graph."""
        node_id = self._url_to_node_id(url)
        node = GraphNode(
            node_id=node_id,
            node_type="product",
            url=url,
            canonical_url=url,
            title=title,
            sku=sku,
            handle=handle,
            organization_id=org_id,
            metadata=metadata or {},
        )
        self.add_node(org_id, node)

        # Index by handle
        if handle:
            self._index_handle(org_id, handle, node_id)

        # Index by SKU
        if sku:
            self._index_sku(org_id, sku, node_id)

        # Collection edges
        for coll_url in (collection_urls or []):
            coll_id = self._url_to_node_id(coll_url)
            coll_node = self.get_node(org_id, coll_id) or GraphNode(
                node_id=coll_id, node_type="collection",
                url=coll_url, canonical_url=coll_url,
                organization_id=org_id,
            )
            self.add_node(org_id, coll_node)
            self.add_edge(org_id, GraphEdge(
                source_id=node_id, target_id=coll_id,
                edge_type=EdgeType.IN_COLLECTION,
            ))
            self._index_collection(org_id, coll_id, node_id)

        # Related product edges
        for rel_url in (related_urls or []):
            rel_id = self._url_to_node_id(rel_url)
            self.add_edge(org_id, GraphEdge(
                source_id=node_id, target_id=rel_id,
                edge_type=EdgeType.RELATED_TO, weight=0.8,
            ))

        # API endpoint edges
        for ep_url in (api_endpoints or []):
            ep_id = self._url_to_node_id(ep_url)
            ep_node = GraphNode(
                node_id=ep_id, node_type="api_endpoint",
                url=ep_url, canonical_url=ep_url,
                organization_id=org_id,
            )
            self.add_node(org_id, ep_node)
            self.add_edge(org_id, GraphEdge(
                source_id=node_id, target_id=ep_id,
                edge_type=EdgeType.SERVED_BY_API,
            ))

        return node

    def register_variant(
        self,
        org_id: str,
        product_url: str,
        variant_sku: str,
        variant_url: str = "",
        metadata: Optional[Dict] = None,
    ) -> GraphNode:
        """Register a variant node and link it to its parent product."""
        product_id = self._url_to_node_id(product_url)
        variant_id = f"variant:{org_id}:{variant_sku}"
        variant_node = GraphNode(
            node_id=variant_id,
            node_type="variant",
            url=variant_url or product_url,
            canonical_url=product_url,
            sku=variant_sku,
            organization_id=org_id,
            metadata=metadata or {},
        )
        self.add_node(org_id, variant_node)
        self.add_edge(org_id, GraphEdge(
            source_id=product_id, target_id=variant_id,
            edge_type=EdgeType.HAS_VARIANT,
        ))
        self._index_sku(org_id, variant_sku, variant_id)
        return variant_node

    def find_by_sku(self, org_id: str, sku: str) -> List[GraphNode]:
        """Find all nodes (products + variants) sharing a SKU."""
        node_ids = self._get_sku_index(org_id, sku)
        nodes = []
        for nid in node_ids:
            node = self.get_node(org_id, nid)
            if node:
                nodes.append(node)
        return nodes

    def detect_shared_skus(self, org_id: str) -> Dict[str, List[str]]:
        """
        Detect SKUs that appear on multiple product pages.
        Returns {sku: [url1, url2, ...]} for SKUs with > 1 product.
        """
        shared: Dict[str, List[str]] = {}
        try:
            from app.core.redis_client import sync_redis_client as r
            pattern = f"{GRAPH_KEY_PREFIX}:{org_id}:sku_index:*"
            for key in r.scan_iter(pattern):
                sku = key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
                node_ids = r.smembers(key)
                if len(node_ids) > 1:
                    urls = []
                    for nid in node_ids:
                        nid_str = nid.decode() if isinstance(nid, bytes) else nid
                        node = self.get_node(org_id, nid_str)
                        if node:
                            urls.append(node.url)
                    if len(urls) > 1:
                        shared[sku] = urls
        except Exception as e:
            logger.warning("shared_sku_detection_failed", error=str(e))
        return shared

    def get_collection_products(self, org_id: str, collection_url: str) -> List[GraphNode]:
        """Get all products in a collection."""
        coll_id = self._url_to_node_id(collection_url)
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:collection:{coll_id}"
            node_ids = r.smembers(key)
            nodes = []
            for nid in node_ids:
                nid_str = nid.decode() if isinstance(nid, bytes) else nid
                node = self.get_node(org_id, nid_str)
                if node:
                    nodes.append(node)
            return nodes
        except Exception:
            return []

    def get_related_products(
        self, org_id: str, product_url: str, max_results: int = 5
    ) -> List[GraphNode]:
        """Get related products via graph traversal."""
        node_id = self._url_to_node_id(product_url)
        neighbors = self.get_neighbors(
            org_id, node_id,
            edge_type=EdgeType.RELATED_TO,
            max_depth=2,
        )
        return [n for n in neighbors if n.node_type == "product"][:max_results]

    def resolve_canonical(self, org_id: str, url: str) -> str:
        """Resolve a URL to its canonical product URL via the graph."""
        node = self.get_node_by_url(org_id, url)
        if node:
            return node.canonical_url
        return url

    # ── Persistence helpers ───────────────────────────────────────────────────

    def _persist_node(self, org_id: str, node: GraphNode):
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:node:{node.node_id}"
            r.setex(key, GRAPH_TTL, json.dumps({
                "node_id": node.node_id, "node_type": node.node_type,
                "url": node.url, "canonical_url": node.canonical_url,
                "title": node.title, "sku": node.sku, "handle": node.handle,
                "organization_id": node.organization_id, "metadata": node.metadata,
            }))
        except Exception:
            pass

    def _load_node(self, org_id: str, node_id: str) -> Optional[GraphNode]:
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:node:{node_id}"
            raw = r.get(key)
            if raw:
                d = json.loads(raw)
                return GraphNode(**d)
        except Exception:
            pass
        return None

    def _persist_edge(self, org_id: str, edge: GraphEdge):
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:edges:{edge.source_id}"
            r.sadd(key, json.dumps({
                "source_id": edge.source_id, "target_id": edge.target_id,
                "edge_type": edge.edge_type.value, "weight": edge.weight,
                "metadata": edge.metadata,
            }))
            r.expire(key, GRAPH_TTL)
        except Exception:
            pass

    def _load_edges(self, org_id: str, node_id: str) -> List[GraphEdge]:
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:edges:{node_id}"
            members = r.smembers(key)
            edges = []
            for m in members:
                d = json.loads(m)
                edges.append(GraphEdge(
                    source_id=d["source_id"], target_id=d["target_id"],
                    edge_type=EdgeType(d["edge_type"]),
                    weight=d.get("weight", 1.0),
                    metadata=d.get("metadata", {}),
                ))
            self._local_edges.setdefault(org_id, {})[node_id] = edges
            return edges
        except Exception:
            return []

    def _index_handle(self, org_id: str, handle: str, node_id: str):
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:handle_index:{handle}"
            r.setex(key, GRAPH_TTL, node_id)
        except Exception:
            pass

    def _index_sku(self, org_id: str, sku: str, node_id: str):
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:sku_index:{sku}"
            r.sadd(key, node_id)
            r.expire(key, GRAPH_TTL)
        except Exception:
            pass

    def _index_collection(self, org_id: str, coll_id: str, product_node_id: str):
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:collection:{coll_id}"
            r.sadd(key, product_node_id)
            r.expire(key, GRAPH_TTL)
        except Exception:
            pass

    def _get_sku_index(self, org_id: str, sku: str) -> Set[str]:
        try:
            from app.core.redis_client import sync_redis_client as r
            key = f"{GRAPH_KEY_PREFIX}:{org_id}:sku_index:{sku}"
            members = r.smembers(key)
            return {m.decode() if isinstance(m, bytes) else m for m in members}
        except Exception:
            return set()

    @staticmethod
    def _url_to_node_id(url: str) -> str:
        return hashlib.md5(url.rstrip("/").encode()).hexdigest()


entity_graph = EntityGraph()
