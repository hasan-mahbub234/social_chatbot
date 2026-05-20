"""Typo corrector — fixes common misspellings before retrieval."""
import re
from typing import Dict
from app.core.logging import get_logger

logger = get_logger(__name__)

# Common misspellings in ecommerce/fashion queries
TYPO_MAP: Dict[str, str] = {
    "shiping":      "shipping",
    "shpping":      "shipping",
    "delivry":      "delivery",
    "deliveri":     "delivery",
    "returnn":      "return",
    "refundd":      "refund",
    "availble":     "available",
    "availabel":    "available",
    "avaliable":    "available",
    "prodcut":      "product",
    "prodect":      "product",
    "materail":     "material",
    "materiel":     "material",
    "colur":        "color",
    "colour":       "color",
    "sizee":        "size",
    "prise":        "price",
    "prce":         "price",
    "waranty":      "warranty",
    "warrenty":     "warranty",
    "guarentee":    "guarantee",
    "guarntee":     "guarantee",
    "discont":      "discount",
    "discound":     "discount",
    "exchagne":     "exchange",
    "exchnage":     "exchange",
    "polcy":        "policy",
    "plicy":        "policy",
    "tshrit":       "tshirt",
    "tshit":        "tshirt",
    "hoddie":       "hoodie",
    "hoodei":       "hoodie",
    "trouser":      "trouser",
    "trousser":     "trouser",
    "snekar":       "sneaker",
    "sneker":       "sneaker",
    "backpak":      "backpack",
    "backpack":     "backpack",
}


class TypoCorrector:
    """Fix common misspellings in queries before retrieval."""

    def correct(self, query: str) -> str:
        if not query or not query.strip():
            return query

        words = query.split()
        corrected = []
        changed = False

        for word in words:
            clean = re.sub(r'[^a-z]', '', word.lower())
            if clean in TYPO_MAP:
                corrected.append(TYPO_MAP[clean])
                changed = True
            else:
                corrected.append(word)

        result = " ".join(corrected)
        if changed:
            logger.debug("typo_corrected", original=query[:60], corrected=result[:60])
        return result


typo_corrector = TypoCorrector()
