"""Content extractor — extracts structured content from raw HTML/text."""
import re
from typing import Dict, Any, List
from app.core.logging import get_logger

logger = get_logger(__name__)


class ContentExtractor:
    """Extract structured content from web pages."""

    def extract(self, html: str, url: str = "") -> Dict[str, Any]:
        """Extract structured content from HTML using BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Remove unwanted elements first
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Find main content area
            main = (
                soup.find("main")
                or soup.find("article")
                or soup.find(id=re.compile(r"content|main|body", re.I))
                or soup.find(class_=re.compile(r"content|main|body", re.I))
                or soup.body
            )

            if not main:
                return {"text": "", "headings": [], "paragraphs": []}

            headings = [h.get_text(strip=True) for h in main.find_all(["h1", "h2", "h3"])]
            paragraphs = [p.get_text(strip=True) for p in main.find_all("p") if p.get_text(strip=True)]
            text = main.get_text(separator="\n", strip=True)

            return {
                "text": text,
                "headings": headings[:20],
                "paragraphs": paragraphs[:50],
                "url": url,
            }
        except Exception as e:
            logger.error("extractor_failed", error=str(e))
            return {"text": "", "headings": [], "paragraphs": []}

    def extract_faq(self, text: str) -> List[Dict[str, str]]:
        """Extract FAQ pairs from text."""
        faqs = []
        lines = text.split("\n")
        i = 0
        while i < len(lines) - 1:
            line = lines[i].strip()
            if line.endswith("?") and len(line) > 10:
                answer_lines = []
                j = i + 1
                while j < len(lines) and not lines[j].strip().endswith("?"):
                    if lines[j].strip():
                        answer_lines.append(lines[j].strip())
                    j += 1
                if answer_lines:
                    faqs.append({"question": line, "answer": " ".join(answer_lines[:3])})
                i = j
            else:
                i += 1
        return faqs


content_extractor = ContentExtractor()