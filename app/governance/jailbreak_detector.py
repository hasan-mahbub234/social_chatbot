"""Jailbreak and prompt injection detector."""
import re
from typing import Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)

JAILBREAK_PATTERNS = [
    r"ignore (all |previous |prior )?instructions",
    r"disregard (your |all |previous )?instructions",
    r"you are now (a |an )?(?!assistant)",
    r"act as (if you are|a|an) (?!assistant)",
    r"pretend (you are|to be)",
    r"forget (your |all )?rules",
    r"bypass (your |all )?restrictions",
    r"jailbreak",
    r"dan mode",
    r"developer mode",
    r"do anything now",
    r"no restrictions",
    r"override (safety|guidelines|rules)",
    r"system prompt",
    r"<\|.*?\|>",  # Token injection patterns
    r"\[INST\]",
    r"###\s*(instruction|system)",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore the above",
    r"ignore previous",
    r"new instruction",
    r"---\s*instruction",
    r"human:\s*ignore",
    r"assistant:\s*sure",
]


class JailbreakDetector:
    """Detect jailbreak attempts and prompt injection."""

    def detect(self, text: str) -> Dict[str, any]:
        """Detect jailbreak patterns in text."""
        lower = text.lower()
        triggered: List[str] = []

        for pattern in JAILBREAK_PATTERNS:
            if re.search(pattern, lower):
                triggered.append(pattern)

        for pattern in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, lower):
                triggered.append(f"injection:{pattern}")

        is_jailbreak = len(triggered) > 0
        confidence = min(1.0, len(triggered) * 0.3)

        return {
            "is_jailbreak": is_jailbreak,
            "confidence": confidence,
            "triggered_patterns": triggered,
            "risk_level": "critical" if is_jailbreak else "low",
        }


jailbreak_detector = JailbreakDetector()
