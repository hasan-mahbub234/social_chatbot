"""
Query Expander — adds synonyms and related terms to improve retrieval recall.

Examples:
  "tee"           → "tee tshirt t-shirt shirt topwear"
  "hoodie"        → "hoodie sweatshirt pullover fleece top"
  "sneaker"       → "sneaker shoe footwear trainer"
  "under 2k"      → "under 2000 price below 2000 BDT"

Expansion runs AFTER rewriting. The expanded query is used for BM25 search
only — vector search uses the original rewritten query to avoid embedding drift.
"""
import re
from typing import Dict, List, Set
from app.core.logging import get_logger

logger = get_logger(__name__)

# Synonym groups — each key expands to include all values in its group
SYNONYM_GROUPS: Dict[str, List[str]] = {
    # Clothing categories
    "tshirt":       ["tshirt", "t-shirt", "tee", "shirt", "topwear", "top"],
    "shirt":        ["shirt", "tshirt", "t-shirt", "top", "topwear"],
    "hoodie":       ["hoodie", "sweatshirt", "pullover", "fleece", "hooded"],
    "pant":         ["pant", "pants", "trouser", "trousers", "bottom", "lower"],
    "shorts":       ["shorts", "short pant", "half pant", "bermuda"],
    "jacket":       ["jacket", "coat", "outerwear", "windbreaker", "blazer"],
    "dress":        ["dress", "frock", "gown", "maxi"],
    "saree":        ["saree", "sari", "sharee"],
    "kurta":        ["kurta", "panjabi", "punjabi", "tunic"],
    "shoe":         ["shoe", "shoes", "footwear", "sneaker", "trainer", "boot"],
    "bag":          ["bag", "backpack", "handbag", "purse", "tote"],

    # Materials
    "cotton":       ["cotton", "cot", "100% cotton", "pure cotton"],
    "polyester":    ["polyester", "poly", "synthetic", "microfiber"],
    "denim":        ["denim", "jeans", "jean fabric"],
    "linen":        ["linen", "linen fabric", "breathable fabric"],

    # Attributes
    "waterproof":   ["waterproof", "water resistant", "water repellent", "rain proof"],
    "breathable":   ["breathable", "air flow", "ventilated", "moisture wicking"],
    "stretchable":  ["stretchable", "stretch", "elastic", "flexible", "4-way stretch"],
    "slim fit":     ["slim fit", "slim", "fitted", "skinny fit"],
    "regular fit":  ["regular fit", "regular", "standard fit", "classic fit"],
    "oversized":    ["oversized", "loose fit", "baggy", "relaxed fit"],

    # Colors
    "black":        ["black", "dark", "jet black", "charcoal"],
    "white":        ["white", "off white", "cream", "ivory"],
    "navy":         ["navy", "navy blue", "dark blue", "midnight blue"],
    "grey":         ["grey", "gray", "charcoal grey", "ash"],

    # Ecommerce terms
    "return":       ["return", "exchange", "refund", "return policy"],
    "shipping":     ["shipping", "delivery", "dispatch", "courier"],
    "discount":     ["discount", "sale", "offer", "promo", "deal", "coupon"],
    "available":    ["available", "in stock", "stock", "availability"],
    "price":        ["price", "cost", "rate", "amount", "charge"],
    "size":         ["size", "sizing", "measurement", "dimension", "fit"],
    "variant":      ["variant", "variation", "option", "color", "size option"],
    "material":     ["material", "fabric", "composition", "textile", "cloth"],
    "warranty":     ["warranty", "guarantee", "quality assurance"],
    "care":         ["care", "wash", "washing", "maintenance", "cleaning"],
}

# Price range patterns → normalized form
PRICE_PATTERNS = [
    (re.compile(r'under\s+(\d+)k', re.I),   lambda m: f"under {int(m.group(1))*1000} price below {int(m.group(1))*1000} BDT"),
    (re.compile(r'below\s+(\d+)k', re.I),   lambda m: f"below {int(m.group(1))*1000} price under {int(m.group(1))*1000} BDT"),
    (re.compile(r'under\s+(\d+)', re.I),    lambda m: f"under {m.group(1)} price below {m.group(1)} BDT"),
    (re.compile(r'(\d+)\s*-\s*(\d+)\s*tk', re.I), lambda m: f"price {m.group(1)} to {m.group(2)} BDT taka"),
]


class QueryExpander:
    """
    Expand queries with synonyms and related terms to improve BM25 recall.

    The expanded query is used for keyword/BM25 search only.
    Vector search uses the original (non-expanded) query to avoid embedding drift.
    """

    def __init__(self):
        # Build reverse lookup: word → canonical group key
        self._word_to_group: Dict[str, str] = {}
        for key, synonyms in SYNONYM_GROUPS.items():
            for syn in synonyms:
                self._word_to_group[syn.lower()] = key

    def expand(self, query: str) -> str:
        """Return query expanded with synonyms for BM25 search."""
        if not query or not query.strip():
            return query

        q = query.lower().strip()

        # Apply price range normalization
        for pattern, replacer in PRICE_PATTERNS:
            q = pattern.sub(replacer, q)

        # Find matching synonym groups
        added_terms: Set[str] = set()
        words = re.findall(r'[a-z0-9\-]+', q)

        for word in words:
            group_key = self._word_to_group.get(word)
            if group_key and group_key not in added_terms:
                added_terms.add(group_key)
                # Add synonyms not already in query
                for syn in SYNONYM_GROUPS[group_key]:
                    if syn.lower() not in q:
                        q = q + " " + syn
                        break  # add only one synonym to avoid over-expansion

        expanded = re.sub(r'\s+', ' ', q).strip()

        if expanded != query.lower().strip():
            logger.debug("query_expanded", original=query[:60], expanded=expanded[:80])

        return expanded

    def get_synonyms(self, term: str) -> List[str]:
        """Return all synonyms for a term."""
        group_key = self._word_to_group.get(term.lower())
        if group_key:
            return SYNONYM_GROUPS[group_key]
        return [term]


query_expander = QueryExpander()
