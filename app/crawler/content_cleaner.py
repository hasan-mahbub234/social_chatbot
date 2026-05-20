"""Content cleaner — normalizes scraped text preserving tables, lists, unicode, and currency symbols."""
import re
from app.core.logging import get_logger

logger = get_logger(__name__)

# Noise patterns to remove
NOISE_PATTERNS = [
    re.compile(r'[\w\.-]+@[\w\.-]+\.\w+'),                    # emails
    re.compile(r'cookie\s*(policy|consent|banner)', re.I),    # cookie banners
    re.compile(r'accept\s+all\s+cookies', re.I),
    re.compile(r'privacy\s+policy\s*\|', re.I),
    re.compile(r'©\s*\d{4}.*?rights\s+reserved', re.I),
    re.compile(r'powered\s+by\s+\w+', re.I),
]

# Navigation noise lines
NAV_PATTERNS = re.compile(
    r'^(home|menu|navigation|skip to|back to top|read more|learn more|'
    r'click here|subscribe|follow us|share|tweet|pin it|like|comment)$',
    re.I
)


class ContentCleaner:
    """Clean and normalize scraped text for RAG embedding."""

    def clean(self, text: str) -> str:
        if not text:
            return ""

        # Remove noise patterns
        for pattern in NOISE_PATTERNS:
            text = pattern.sub(" ", text)

        # Preserve pipe-delimited tables (from semantic DOM extraction)
        # Normalize whitespace but keep table rows intact
        lines = text.split("\n")
        cleaned_lines = []
        seen = set()

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Deduplicate lines
            line_key = re.sub(r'\s+', ' ', line.lower())
            if line_key in seen and len(line) < 100:
                continue
            seen.add(line_key)

            # Skip pure navigation noise
            if NAV_PATTERNS.match(line):
                continue

            # Keep table rows (contain |)
            if "|" in line:
                cleaned_lines.append(line)
                continue

            # Keep Q:/A: FAQ pairs
            if line.startswith(("Q:", "A:", "FAQ")):
                cleaned_lines.append(line)
                continue

            # Keep price lines
            if re.search(r'[\d][\d.,]*\s*[৳$£€¥₹]|[৳$£€¥₹]\s*[\d][\d.,]*', line):
                cleaned_lines.append(line)
                continue

            # Keep lines with meaningful length
            if len(line) > 10:
                cleaned_lines.append(line)
                continue

            # Keep short uppercase headings
            if line and line[0].isupper() and len(line) < 40:
                cleaned_lines.append(line)

        text = "\n".join(cleaned_lines)

        # Normalize label+value pairs: a short label line followed by its value
        # e.g. "Materials\n78% Recycled Polyester" -> "Materials: 78% Recycled Polyester"
        text = self._normalize_label_value_pairs(text)

        # Normalize unicode whitespace
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Keep: unicode letters, digits, punctuation, currency symbols
        # Bengali (৳ \u09F3, \u0980-\u09FF), Arabic (\u0600-\u06FF),
        # CJK (\u4e00-\u9fff), currency (\u20A6-\u20CF, £€¥$)
        text = re.sub(
            r"[^\w\s.,!?;:()/\-\'\"$%#+@&|\u0980-\u09FF\u0600-\u06FF"
            r"\u4e00-\u9fff\u09F3\u20A6-\u20CF\u00A3\u20AC\u00A5\n]",
            " ",
            text
        )
        text = re.sub(r'[ \t]{2,}', ' ', text)
        return text.strip()

    def _normalize_label_value_pairs(self, text: str) -> str:
        """
        Convert DOM-extracted label+value pairs into structured 'Label: Value' format.
        Detects short label lines (known product attribute headings) followed by
        their value on the next line and merges them.

        Before: 'Materials\n78% Recycled Polyester, 22% Elastane'
        After:  'Materials: 78% Recycled Polyester, 22% Elastane'
        """
        LABEL_KEYWORDS = re.compile(
            r'^(Materials?|Fabric|Composition|Care|Wash|Shipping|Delivery|'
            r'Return|Exchange|Refund|Features?|Description|Details?|'
            r'Dimensions?|Weight|Warranty|SKU|Barcode|Brand|Type|Tags?)\s*$',
            re.I
        )
        lines = text.split("\n")
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if LABEL_KEYWORDS.match(line.strip()) and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Only merge if next line looks like a value (not another label)
                if next_line and not LABEL_KEYWORDS.match(next_line) and len(next_line) > 3:
                    result.append(f"{line.strip()}: {next_line}")
                    i += 2
                    continue
            result.append(line)
            i += 1
        return "\n".join(result)

    def clean_html_entities(self, text: str) -> str:
        replacements = {
            "&amp;": "&", "&lt;": "<", "&gt;": ">",
            "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
        }
        for entity, char in replacements.items():
            text = text.replace(entity, char)
        return text


content_cleaner = ContentCleaner()
