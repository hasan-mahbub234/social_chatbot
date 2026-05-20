"""
Query Rewriter — expands abbreviations, shorthand, and colloquial terms
into retrieval-friendly full-form queries.

Examples:
  "ctg?"          → "Chittagong"
  "poly shirt"    → "polyester shirt"
  "return policy?"→ "return and exchange policy"
  "bd taka price" → "price in BDT Bangladesh Taka"

Runs BEFORE embedding so the vector search gets a clean, expanded query.
Does NOT change the user-facing display — only the retrieval query.
"""
import re
from typing import Dict, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# Abbreviation → full form map
# Covers Bangladesh-specific shorthand, ecommerce terms, and common chat abbreviations
ABBREVIATION_MAP: Dict[str, str] = {
    # Bangladesh cities / locations
    "ctg":          "Chittagong",
    "dhk":          "Dhaka",
    "sylhet":       "Sylhet",
    "khulna":       "Khulna",
    "rajshahi":     "Rajshahi",
    "barisal":      "Barisal",
    "mymensingh":   "Mymensingh",
    "narayanganj":  "Narayanganj",
    "gazipur":      "Gazipur",
    "bd":           "Bangladesh",

    # Material shorthand
    "poly":         "polyester",
    "cot":          "cotton",
    "linen":        "linen fabric",
    "denim":        "denim fabric",
    "fleece":       "fleece fabric",
    "jersey":       "jersey fabric",

    # Ecommerce shorthand
    "emi":          "installment payment",
    "cod":          "cash on delivery",
    "oos":          "out of stock",
    "instock":      "in stock",
    "avail":        "available",
    "qty":          "quantity",
    "pcs":          "pieces",
    "xl":           "extra large size",
    "xxl":          "double extra large size",
    "xxxl":         "triple extra large size",

    # Price / currency
    "tk":           "taka BDT",
    "bdt":          "BDT Bangladesh Taka",
    "usd":          "USD US Dollar",

    # Common chat shorthand
    "info":         "information",
    "desc":         "description",
    "spec":         "specifications",
    "specs":        "specifications",
    "img":          "image",
    "pic":          "picture",
    "pls":          "please",
    "plz":          "please",
    "asap":         "as soon as possible",
    "faq":          "frequently asked questions",
    "tnx":          "thank you",
    "thx":          "thank you",
    "w/":           "with",
    "w/o":          "without",
    "vs":           "versus comparison",
    "diff":         "difference",
}

# Phrase-level rewrites (checked before word-level)
PHRASE_REWRITES: Dict[str, str] = {
    "return policy":        "return and exchange policy refund",
    "exchange policy":      "return and exchange policy refund",
    "refund policy":        "return and exchange policy refund",
    "shipping policy":      "shipping delivery policy",
    "delivery time":        "shipping delivery time days",
    "how long delivery":    "shipping delivery time days",
    "free shipping":        "free shipping delivery",
    "cash on delivery":     "cash on delivery COD payment",
    "out of stock":         "out of stock unavailable",
    "in stock":             "in stock available",
    "size chart":           "size guide chart measurements",
    "size guide":           "size guide chart measurements",
    "wash care":            "washing care instructions",
    "care instruction":     "washing care instructions",
    "product detail":       "product details specifications description",
    "all variant":          "all variants sizes colors options",
    "color option":         "color options available colors",
    "size option":          "size options available sizes",
}


class QueryRewriter:
    """
    Rewrite raw user queries into retrieval-optimized form.

    Pipeline:
      1. Strip trailing punctuation / question marks
      2. Apply phrase-level rewrites (multi-word patterns)
      3. Apply word-level abbreviation expansion
      4. Normalize whitespace
    """

    def rewrite(self, query: str) -> str:
        """Return retrieval-optimized version of the query."""
        if not query or not query.strip():
            return query

        original = query.strip()
        q = original.lower()

        # Strip trailing punctuation that adds no meaning
        q = re.sub(r'[?!.]+$', '', q).strip()

        # Phrase-level rewrites first (longer patterns take priority)
        for phrase, replacement in PHRASE_REWRITES.items():
            if phrase in q:
                q = q.replace(phrase, replacement)

        # Word-level abbreviation expansion
        words = q.split()
        expanded = []
        for word in words:
            clean_word = re.sub(r'[^a-z0-9]', '', word)
            if clean_word in ABBREVIATION_MAP:
                expanded.append(ABBREVIATION_MAP[clean_word])
            else:
                expanded.append(word)
        q = " ".join(expanded)

        # Normalize whitespace
        q = re.sub(r'\s+', ' ', q).strip()

        if q != original.lower():
            logger.debug("query_rewritten", original=original[:60], rewritten=q[:60])

        return q

    def rewrite_for_bm25(self, query: str) -> str:
        """
        Additional rewrite specifically for BM25/FTS queries.
        Removes stop words that hurt ts_rank scoring.
        """
        rewritten = self.rewrite(query)
        # Remove words that confuse plainto_tsquery
        noise = {"please", "can", "you", "tell", "me", "about", "show", "give",
                 "what", "is", "the", "are", "does", "do", "a", "an", "of"}
        words = [w for w in rewritten.split() if w.lower() not in noise]
        return " ".join(words) if words else rewritten


query_rewriter = QueryRewriter()
