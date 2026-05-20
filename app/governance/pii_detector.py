"""PII detector using regex patterns."""
import re
from typing import Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)

PII_PATTERNS = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "phone": r"\b(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "date_of_birth": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    "passport": r"\b[A-Z]{1,2}\d{6,9}\b",
}


class PIIDetector:
    """Detect personally identifiable information in text."""

    def detect(self, text: str) -> Dict[str, List[str]]:
        """Return dict of PII type → list of matches."""
        findings: Dict[str, List[str]] = {}
        for pii_type, pattern in PII_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                findings[pii_type] = matches
        return findings

    def has_pii(self, text: str) -> bool:
        return bool(self.detect(text))

    def redact(self, text: str) -> str:
        """Replace PII with redacted placeholders."""
        for pii_type, pattern in PII_PATTERNS.items():
            text = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", text, flags=re.IGNORECASE)
        return text


pii_detector = PIIDetector()
