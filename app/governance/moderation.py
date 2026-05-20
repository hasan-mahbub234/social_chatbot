"""Content moderation — toxicity and profanity detection."""
from typing import Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)

TOXIC_KEYWORDS = [
    "kill", "murder", "suicide", "bomb", "weapon", "explosive",
    "hack", "exploit", "malware", "ransomware", "phishing",
    "drug", "cocaine", "heroin", "meth",
]

SENSITIVE_TOPICS = [
    "self-harm", "violence", "terrorism", "child abuse",
    "illegal weapons", "drug trafficking",
]


class ModerationService:
    """Rule-based content moderation."""

    def moderate(self, text: str) -> Dict[str, any]:
        """Check text for toxic or unsafe content."""
        lower = text.lower()
        flagged_keywords: List[str] = []
        flagged_topics: List[str] = []

        for kw in TOXIC_KEYWORDS:
            if kw in lower:
                flagged_keywords.append(kw)

        for topic in SENSITIVE_TOPICS:
            if topic in lower:
                flagged_topics.append(topic)

        is_flagged = bool(flagged_keywords or flagged_topics)
        severity = "critical" if flagged_topics else ("high" if flagged_keywords else "low")

        return {
            "is_safe": not is_flagged,
            "flagged": is_flagged,
            "flagged_keywords": flagged_keywords,
            "flagged_topics": flagged_topics,
            "severity": severity,
            "categories": {
                "toxic": bool(flagged_keywords),
                "sensitive_topic": bool(flagged_topics),
            },
        }


moderation_service = ModerationService()
