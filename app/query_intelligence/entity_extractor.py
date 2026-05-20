"""
Entity Extractor — identifies product names, brands, SKUs, categories,
and named entities from queries for targeted retrieval.

Examples:
  "Wave Riders Swim Shorts price"
  → entities: [{type: product, value: "Wave Riders Swim Shorts"}]

  "TRGM032486 availability"
  → entities: [{type: sku, value: "TRGM032486"}]

  "Turaag Active hoodie"
  → entities: [{type: brand, value: "Turaag Active"}, {type: category, value: "hoodie"}]
"""
import re
from dataclasses import dataclass
from typing import List
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractedEntity:
    entity_type: str    # product | brand | sku | category | location | attribute
    value: str
    confidence: float


# SKU pattern — uppercase letters + digits, 6-20 chars
_SKU_RE = re.compile(r'\b([A-Z]{2,6}\d{4,12}(?:-[A-Z0-9]+)?)\b')

# Known brand names (extend as needed)
_KNOWN_BRANDS = {
    "turaag", "turaag active", "adidas", "nike", "puma", "reebok",
    "h&m", "zara", "uniqlo", "levis", "wrangler", "gap",
}

# Product category keywords
_CATEGORY_KEYWORDS = {
    "shirt", "tshirt", "t-shirt", "hoodie", "sweatshirt", "pant", "trouser",
    "shorts", "jacket", "coat", "dress", "saree", "kurta", "panjabi",
    "shoe", "sneaker", "sandal", "bag", "backpack", "wallet", "cap", "hat",
    "sock", "underwear", "bra", "legging", "jogger", "polo", "vest",
}

# Location keywords
_LOCATION_KEYWORDS = {
    "dhaka", "chittagong", "ctg", "sylhet", "khulna", "rajshahi",
    "gulshan", "dhanmondi", "mirpur", "bashundhara", "uttara", "motijheel",
    "narayanganj", "gazipur", "wari", "old dhaka",
}


class EntityExtractor:
    """Extract named entities from queries for targeted retrieval."""

    def extract(self, query: str) -> List[ExtractedEntity]:
        """Extract all entities from a query."""
        entities: List[ExtractedEntity] = []
        lower = query.lower()

        # SKU detection (highest confidence)
        for m in _SKU_RE.finditer(query):
            entities.append(ExtractedEntity(
                entity_type="sku",
                value=m.group(1),
                confidence=0.95,
            ))

        # Brand detection
        for brand in _KNOWN_BRANDS:
            if brand in lower:
                entities.append(ExtractedEntity(
                    entity_type="brand",
                    value=brand.title(),
                    confidence=0.90,
                ))

        # Category detection
        for cat in _CATEGORY_KEYWORDS:
            if re.search(rf'\b{re.escape(cat)}\b', lower):
                entities.append(ExtractedEntity(
                    entity_type="category",
                    value=cat,
                    confidence=0.85,
                ))

        # Location detection
        for loc in _LOCATION_KEYWORDS:
            if re.search(rf'\b{re.escape(loc)}\b', lower):
                entities.append(ExtractedEntity(
                    entity_type="location",
                    value=loc.title(),
                    confidence=0.90,
                ))

        # Capitalized product names (Title Case multi-word phrases)
        for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b', query):
            candidate = m.group(1)
            # Skip if already captured as brand/location
            if not any(e.value.lower() == candidate.lower() for e in entities):
                entities.append(ExtractedEntity(
                    entity_type="product",
                    value=candidate,
                    confidence=0.75,
                ))

        if entities:
            logger.debug("entities_extracted", count=len(entities), query=query[:60])

        return entities

    def get_sku(self, query: str) -> str:
        """Extract SKU from query if present."""
        m = _SKU_RE.search(query)
        return m.group(1) if m else ""

    def get_product_name(self, query: str) -> str:
        """Extract the most likely product name from query."""
        entities = self.extract(query)
        products = [e for e in entities if e.entity_type in ("product", "sku")]
        if products:
            return max(products, key=lambda e: e.confidence).value
        return ""


entity_extractor = EntityExtractor()
