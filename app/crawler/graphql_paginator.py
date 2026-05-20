"""
GraphQL Pagination & Cursor Engine

Handles recursive edge/node traversal with cursor-based pagination.
Supports:
  - Shopify Storefront API (edges/nodes/pageInfo pattern)
  - Generic Relay-style pagination
  - hasNextPage / endCursor continuation
  - Retry-safe checkpoints (cursor stored in Redis)
  - Rate-limit awareness with exponential backoff
"""
from __future__ import annotations
import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx
from app.core.logging import get_logger

logger = get_logger(__name__)

# Pagination config
DEFAULT_PAGE_SIZE = 50
MAX_PAGES = 100
RATE_LIMIT_DELAY = 0.5      # seconds between requests
RETRY_DELAYS = [1, 2, 4, 8] # exponential backoff

# Redis key for cursor checkpoints
CURSOR_KEY_PREFIX = "graphql_cursor"
CURSOR_TTL = 3600 * 6       # 6 hours


# ── Standard GraphQL queries ──────────────────────────────────────────────────

SHOPIFY_PRODUCTS_QUERY = """
query GetProducts($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        title
        handle
        vendor
        productType
        tags
        description
        priceRange {
          minVariantPrice { amount currencyCode }
          maxVariantPrice { amount currencyCode }
        }
        variants(first: 100) {
          edges {
            node {
              id
              title
              sku
              barcode
              availableForSale
              price { amount currencyCode }
              selectedOptions { name value }
              weight
            }
          }
        }
      }
    }
  }
}
"""

SHOPIFY_PRODUCT_BY_HANDLE_QUERY = """
query GetProduct($handle: String!) {
  product(handle: $handle) {
    id
    title
    handle
    vendor
    productType
    tags
    description
    priceRange {
      minVariantPrice { amount currencyCode }
    }
    variants(first: 250) {
      edges {
        node {
          id
          title
          sku
          barcode
          availableForSale
          price { amount currencyCode }
          compareAtPrice { amount currencyCode }
          selectedOptions { name value }
          weight
        }
      }
    }
    metafields(first: 20) {
      edges {
        node {
          namespace
          key
          value
        }
      }
    }
  }
}
"""


class GraphQLPaginator:
    """
    Paginate through GraphQL connections using cursor-based pagination.
    Stores checkpoints in Redis for retry-safe resumption.
    """

    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers={"Content-Type": "application/json"},
            )
        return self._http_client

    # ── Public API ────────────────────────────────────────────────────────────

    async def paginate_products(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        checkpoint_key: Optional[str] = None,
        query: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Async generator that yields one product node at a time.
        Resumes from checkpoint if available.
        """
        cursor = self._load_checkpoint(checkpoint_key) if checkpoint_key else None
        page = 0

        while page < MAX_PAGES:
            variables: Dict[str, Any] = {"first": page_size}
            if cursor:
                variables["after"] = cursor

            response = await self._execute_with_retry(
                endpoint=endpoint,
                query=query or SHOPIFY_PRODUCTS_QUERY,
                variables=variables,
                headers=headers or {},
            )

            if not response:
                break

            connection = self._extract_connection(response)
            if not connection:
                break

            edges = connection.get("edges", [])
            for edge in edges:
                node = edge.get("node", {})
                if node:
                    yield node

            page_info = connection.get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

            if checkpoint_key and cursor:
                self._save_checkpoint(checkpoint_key, cursor)

            if not has_next or not cursor:
                break

            page += 1
            await asyncio.sleep(RATE_LIMIT_DELAY)

        if checkpoint_key:
            self._clear_checkpoint(checkpoint_key)

    async def fetch_product_by_handle(
        self,
        endpoint: str,
        handle: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single product by handle via GraphQL."""
        response = await self._execute_with_retry(
            endpoint=endpoint,
            query=SHOPIFY_PRODUCT_BY_HANDLE_QUERY,
            variables={"handle": handle},
            headers=headers or {},
        )
        if not response:
            return None
        return response.get("data", {}).get("product")

    async def execute_custom(
        self,
        endpoint: str,
        query: str,
        variables: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute a custom GraphQL query and return the full response."""
        return await self._execute_with_retry(
            endpoint=endpoint,
            query=query,
            variables=variables or {},
            headers=headers or {},
        )

    async def paginate_generic(
        self,
        endpoint: str,
        query: str,
        connection_path: List[str],
        headers: Optional[Dict[str, str]] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        checkpoint_key: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Generic paginator for any Relay-style GraphQL connection.

        Args:
            connection_path: JSON path to the connection object.
                             e.g. ["data", "catalog", "products"]
        """
        cursor = self._load_checkpoint(checkpoint_key) if checkpoint_key else None
        page = 0

        while page < MAX_PAGES:
            variables: Dict[str, Any] = {"first": page_size}
            if cursor:
                variables["after"] = cursor

            response = await self._execute_with_retry(
                endpoint=endpoint,
                query=query,
                variables=variables,
                headers=headers or {},
            )
            if not response:
                break

            # Navigate to connection using path
            connection = response
            for key in connection_path:
                if isinstance(connection, dict):
                    connection = connection.get(key, {})
                else:
                    connection = {}
                    break

            if not isinstance(connection, dict):
                break

            edges = connection.get("edges", [])
            nodes = connection.get("nodes", [])  # some APIs use nodes directly

            items = [e.get("node", e) for e in edges] if edges else nodes
            for item in items:
                if item:
                    yield item

            page_info = connection.get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

            if checkpoint_key and cursor:
                self._save_checkpoint(checkpoint_key, cursor)

            if not has_next or not cursor:
                break

            page += 1
            await asyncio.sleep(RATE_LIMIT_DELAY)

        if checkpoint_key:
            self._clear_checkpoint(checkpoint_key)

    # ── Execution with retry ──────────────────────────────────────────────────

    async def _execute_with_retry(
        self,
        endpoint: str,
        query: str,
        variables: Dict,
        headers: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """Execute a GraphQL request with exponential backoff retry."""
        client = await self._client()
        last_error = None

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            try:
                resp = await client.post(
                    endpoint,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )

                # Rate limit handling
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", delay * 2 or 2))
                    logger.warning("graphql_rate_limited", endpoint=endpoint, retry_after=retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if resp.status_code != 200:
                    logger.warning("graphql_non_200", endpoint=endpoint, status=resp.status_code)
                    last_error = f"HTTP {resp.status_code}"
                    continue

                data = resp.json()

                # GraphQL-level errors
                errors = data.get("errors", [])
                if errors:
                    error_msgs = [e.get("message", "") for e in errors]
                    logger.warning("graphql_errors", endpoint=endpoint, errors=error_msgs[:3])
                    # Throttle error from Shopify
                    if any("throttled" in m.lower() for m in error_msgs):
                        await asyncio.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                        continue
                    # Non-throttle errors — return partial data if available
                    if not data.get("data"):
                        last_error = str(error_msgs)
                        continue

                return data

            except httpx.TimeoutException:
                last_error = "timeout"
                logger.warning("graphql_timeout", endpoint=endpoint, attempt=attempt)
            except Exception as e:
                last_error = str(e)
                logger.warning("graphql_request_failed", endpoint=endpoint, error=str(e))

        logger.error("graphql_all_retries_failed", endpoint=endpoint, last_error=last_error)
        return None

    # ── Connection extraction ─────────────────────────────────────────────────

    def _extract_connection(self, response: Dict) -> Optional[Dict]:
        """Find the first Relay-style connection in a GraphQL response."""
        data = response.get("data", {})
        if not data:
            return None
        return self._find_connection(data)

    def _find_connection(self, obj: Any, depth: int = 0) -> Optional[Dict]:
        """Recursively find a dict with edges + pageInfo."""
        if depth > 5:
            return None
        if isinstance(obj, dict):
            if "edges" in obj and "pageInfo" in obj:
                return obj
            if "nodes" in obj and "pageInfo" in obj:
                return obj
            for val in obj.values():
                result = self._find_connection(val, depth + 1)
                if result:
                    return result
        return None

    # ── Checkpoint management ─────────────────────────────────────────────────

    def _save_checkpoint(self, key: str, cursor: str):
        try:
            from app.core.redis_client import sync_redis_client as r
            r.setex(f"{CURSOR_KEY_PREFIX}:{key}", CURSOR_TTL, cursor)
        except Exception:
            pass

    def _load_checkpoint(self, key: str) -> Optional[str]:
        try:
            from app.core.redis_client import sync_redis_client as r
            val = r.get(f"{CURSOR_KEY_PREFIX}:{key}")
            if val:
                return val.decode() if isinstance(val, bytes) else val
        except Exception:
            pass
        return None

    def _clear_checkpoint(self, key: str):
        try:
            from app.core.redis_client import sync_redis_client as r
            r.delete(f"{CURSOR_KEY_PREFIX}:{key}")
        except Exception:
            pass

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


graphql_paginator = GraphQLPaginator()
