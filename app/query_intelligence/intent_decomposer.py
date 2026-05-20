"""
Intent Decomposer — breaks complex queries into structured retrieval intents.

Examples:
  "best waterproof running shoes under 100"
  → {
      category: "running shoes",
      features: ["waterproof"],
      price_max: 100,
      intent: "product_search"
    }

  "compare hoodie vs sweatshirt material"
  → {
      entities: ["hoodie", "sweatshirt"],
      attribute: "material",
      intent: "comparison"
    }

  "return policy for online orders"
  → {
      topic: "return policy",
      context: "online orders",
      intent: "policy_lookup"
    }
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DecomposedIntent:
    """Structured representation of a decomposed query."""
    intent: str                             # product_search | comparison | policy_lookup | faq | support | general
    original_query: str
    retrieval_query: str                    # optimized query for retrieval
    entities: List[str] = field(default_factory=list)       # product names, brands
    attributes: List[str] = field(default_factory=list)     # material, color, size
    constraints: Dict[str, Any] = field(default_factory=dict)  # price_max, size, color
    sub_queries: List[str] = field(default_factory=list)    # for multi-part queries
    requires_comparison: bool = False
    requires_structured_data: bool = False  # needs price/availability fields
    confidence: float = 1.0


# Price constraint patterns
_PRICE_MAX_RE = re.compile(r'(?:under|below|less than|max|maximum|within)\s*(?:tk\.?|bdt\.?|৳|\$)?\s*(\d[\d,]*)', re.I)
_PRICE_MIN_RE = re.compile(r'(?:above|over|more than|min|minimum|at least)\s*(?:tk\.?|bdt\.?|৳|\$)?\s*(\d[\d,]*)', re.I)
_PRICE_RANGE_RE = re.compile(r'(\d[\d,]*)\s*(?:to|-)\s*(\d[\d,]*)\s*(?:tk\.?|bdt\.?|৳|\$)?', re.I)

# Comparison signals
_COMPARISON_RE = re.compile(r'\b(vs\.?|versus|compare|difference|better|which is|between)\b', re.I)

# Attribute keywords
_ATTRIBUTE_KEYWORDS = {
    "material", "fabric", "color", "colour", "size", "weight", "dimension",
    "price", "cost", "availability", "stock", "shipping", "delivery",
    "return", "warranty", "care", "wash", "feature", "specification",
}

# Policy / info intents
_POLICY_KEYWORDS = {"policy", "policies", "terms", "condition", "rule", "guideline",
                    "return", "refund", "exchange", "shipping", "delivery", "warranty"}

# Support intents
_SUPPORT_KEYWORDS = {"not working", "broken", "issue", "problem", "error", "help",
                     "wrong", "damaged", "missing", "complaint", "defect"}


class IntentDecomposer:
    """Decompose complex queries into structured retrieval intents."""

    def decompose(self, query: str) -> DecomposedIntent:
        """Decompose a query into a structured intent object."""
        q = query.strip()
        lower = q.lower()

        intent = self._classify(lower)
        constraints = self._extract_constraints(lower)
        entities = self._extract_entities(q)
        attributes = self._extract_attributes(lower)
        requires_comparison = bool(_COMPARISON_RE.search(lower))
        requires_structured = intent in ("product_search", "price_query", "availability_query")

        # Build optimized retrieval query
        retrieval_query = self._build_retrieval_query(q, intent, entities, attributes, constraints)

        # Decompose multi-part queries (joined by "and", comma)
        sub_queries = self._split_sub_queries(q, intent)

        result = DecomposedIntent(
            intent=intent,
            original_query=q,
            retrieval_query=retrieval_query,
            entities=entities,
            attributes=attributes,
            constraints=constraints,
            sub_queries=sub_queries,
            requires_comparison=requires_comparison,
            requires_structured_data=requires_structured,
        )

        logger.debug(
            "intent_decomposed",
            intent=intent,
            entities=entities[:3],
            constraints=constraints,
            query=q[:60],
        )
        return result

    def _classify(self, lower: str) -> str:
        if _COMPARISON_RE.search(lower):
            return "comparison"
        if any(k in lower for k in _POLICY_KEYWORDS):
            return "policy_lookup"
        if any(k in lower for k in _SUPPORT_KEYWORDS):
            return "support"
        if re.search(r'\b(price|cost|how much|rate)\b', lower):
            return "price_query"
        if re.search(r'\b(available|in stock|stock|availability)\b', lower):
            return "availability_query"
        if re.search(r'\b(show|find|search|looking for|want|need|buy|get)\b', lower):
            return "product_search"
        if re.search(r'\b(what|how|why|when|where|explain|tell me)\b', lower):
            return "faq"
        return "general"

    def _extract_constraints(self, lower: str) -> Dict[str, Any]:
        constraints: Dict[str, Any] = {}

        # Price max
        m = _PRICE_MAX_RE.search(lower)
        if m:
            constraints["price_max"] = int(m.group(1).replace(",", ""))

        # Price min
        m = _PRICE_MIN_RE.search(lower)
        if m:
            constraints["price_min"] = int(m.group(1).replace(",", ""))

        # Price range
        m = _PRICE_RANGE_RE.search(lower)
        if m and "price_max" not in constraints:
            constraints["price_min"] = int(m.group(1).replace(",", ""))
            constraints["price_max"] = int(m.group(2).replace(",", ""))

        # Size constraint
        size_m = re.search(r'\b(xs|s|m|l|xl|xxl|xxxl|small|medium|large|extra large)\b', lower)
        if size_m:
            constraints["size"] = size_m.group(1).upper()

        # Color constraint
        color_m = re.search(r'\b(black|white|red|blue|green|yellow|grey|gray|navy|pink|purple|orange|brown)\b', lower)
        if color_m:
            constraints["color"] = color_m.group(1)

        return constraints

    def _extract_entities(self, query: str) -> List[str]:
        """Extract capitalized product names and known product terms."""
        entities = []
        # Capitalized multi-word phrases (product names)
        for m in re.finditer(r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b', query):
            candidate = m.group(1)
            if len(candidate) > 2 and candidate.lower() not in {"I", "The", "A", "An"}:
                entities.append(candidate)
        return list(dict.fromkeys(entities))[:5]  # deduplicate, cap at 5

    def _extract_attributes(self, lower: str) -> List[str]:
        """Extract attribute keywords from query."""
        return [kw for kw in _ATTRIBUTE_KEYWORDS if kw in lower]

    def _build_retrieval_query(
        self, query: str, intent: str,
        entities: List[str], attributes: List[str],
        constraints: Dict[str, Any],
    ) -> str:
        """Build an optimized retrieval query from decomposed parts."""
        parts = [query]

        # For product search with constraints, append constraint terms
        if intent == "product_search" and constraints:
            if "price_max" in constraints:
                parts.append(f"price under {constraints['price_max']}")
            if "color" in constraints:
                parts.append(constraints["color"])
            if "size" in constraints:
                parts.append(f"size {constraints['size']}")

        # For comparison, ensure both entities are in the query
        if intent == "comparison" and len(entities) >= 2:
            parts.append(f"compare {' '.join(entities[:2])}")

        return " ".join(parts)

    def _split_sub_queries(self, query: str, intent: str) -> List[str]:
        """Split compound queries into individual sub-queries."""
        if intent not in ("product_search", "faq"):
            return []
        # Split on " and " only for clearly compound queries
        parts = re.split(r'\s+and\s+', query, flags=re.I)
        if len(parts) > 1 and all(len(p.strip()) > 5 for p in parts):
            return [p.strip() for p in parts]
        return []


intent_decomposer = IntentDecomposer()
