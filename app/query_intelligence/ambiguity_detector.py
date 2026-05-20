"""
Ambiguity Detector — identifies queries that are too vague to retrieve well
and generates clarification signals or fallback strategies.
"""
import re
from dataclasses import dataclass
from typing import List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AmbiguityResult:
    is_ambiguous: bool
    ambiguity_type: Optional[str]   # too_short | pronoun_only | no_entity | multi_meaning
    confidence: float               # 0.0 = clear, 1.0 = very ambiguous
    suggestion: Optional[str]       # suggested clarification prompt
    fallback_query: Optional[str]   # best-effort retrieval query


# Queries that are pronouns only — need conversation context
_PRONOUN_ONLY_RE = re.compile(
    r'^(it|this|that|these|those|the product|this product|the item|that item)\s*\??$',
    re.I,
)

# Very short queries (1-2 words) that lack context
_TOO_SHORT_RE = re.compile(r'^\s*\w{1,3}\s*\??$')


class AmbiguityDetector:
    """Detect ambiguous queries and suggest retrieval strategies."""

    def detect(self, query: str, has_conversation_history: bool = False) -> AmbiguityResult:
        q = query.strip()
        lower = q.lower()

        # Pronoun-only queries — always ambiguous without history
        if _PRONOUN_ONLY_RE.match(lower):
            if has_conversation_history:
                return AmbiguityResult(
                    is_ambiguous=False,
                    ambiguity_type=None,
                    confidence=0.2,
                    suggestion=None,
                    fallback_query=q,
                )
            return AmbiguityResult(
                is_ambiguous=True,
                ambiguity_type="pronoun_only",
                confidence=0.9,
                suggestion="Could you clarify which product you're asking about?",
                fallback_query=None,
            )

        # Too short without context
        if _TOO_SHORT_RE.match(lower) and not has_conversation_history:
            return AmbiguityResult(
                is_ambiguous=True,
                ambiguity_type="too_short",
                confidence=0.7,
                suggestion=None,
                fallback_query=q,  # try anyway
            )

        # Multi-meaning terms (context-dependent)
        multi_meaning = {
            "polo": ["polo shirt", "polo sport"],
            "fit": ["fit size", "fit style"],
            "free": ["free shipping", "free size"],
        }
        for term, meanings in multi_meaning.items():
            if re.search(rf'\b{term}\b', lower) and len(q.split()) <= 3:
                return AmbiguityResult(
                    is_ambiguous=True,
                    ambiguity_type="multi_meaning",
                    confidence=0.5,
                    suggestion=None,
                    fallback_query=f"{q} {meanings[0]}",
                )

        return AmbiguityResult(
            is_ambiguous=False,
            ambiguity_type=None,
            confidence=0.0,
            suggestion=None,
            fallback_query=q,
        )


ambiguity_detector = AmbiguityDetector()
