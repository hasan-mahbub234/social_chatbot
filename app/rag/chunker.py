"""Semantic chunker — splits content by headings, sections, FAQ groups, and spec blocks."""
import re
from typing import List, Dict, Any
from app.core.constants import MAX_CHUNK_SIZE, CHUNK_OVERLAP


HEADING_RE = re.compile(r'^(#{1,6}\s+.+|[A-Z][A-Z\s]{3,50}:?\s*)$')
FAQ_Q_RE = re.compile(r'^Q:\s*.+', re.I)
FAQ_A_RE = re.compile(r'^A:\s*.+', re.I)
TABLE_ROW_RE = re.compile(r'.+\|.+')
SECTION_BREAK_RE = re.compile(r'^\s*[-=]{3,}\s*$')

# Dynamic chunk sizes by content type.
# Small chunks = precise field retrieval (product specs, FAQs).
# Large chunks = full context needed (policies, documentation, articles).
CHUNK_SIZE_BY_TYPE: Dict[str, int] = {
    "product_spec":  800,    # small — precise: price/SKU/availability fields
    "faq":          1200,    # medium — Q+A pairs need both question and answer
    "table":        1500,    # medium — table rows need surrounding header context
    "documentation":3000,    # large — technical docs need surrounding context
    "article":      2500,    # large — narrative flow breaks badly when split small
    "text":         2000,    # default general content
    "page":         2000,    # default page content
}


class SemanticChunker:
    """
    Semantic chunking strategy:
    1. Split on headings / section breaks
    2. Keep FAQ Q+A pairs together
    3. Keep table rows together
    4. Keep product spec groups together
    5. Fall back to sentence-boundary splitting for oversized sections
    """

    def __init__(self, chunk_size: int = MAX_CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> List[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text.strip()]

        # Keep store/location/contact pages as a single chunk — never split them
        # These pages must be retrieved whole to answer "how many stores" questions
        if self._is_atomic_page(text):
            # If it fits within 2× chunk_size, keep as one chunk
            if len(text) <= self.chunk_size * 2:
                return [text.strip()]

        sections = self._split_into_sections(text)
        chunks = []
        for section in sections:
            if len(section) <= self.chunk_size:
                if section.strip():
                    chunks.append(section.strip())
            else:
                chunks.extend(self._split_large_section(section))

        return self._merge_small_chunks(chunks)

    def _is_atomic_page(self, text: str) -> bool:
        """Detect pages that must stay as one chunk (store locations, contact, about)."""
        text_lower = text.lower()
        # Store location pages: multiple addresses in one page
        location_signals = (
            text_lower.count("opening hours") >= 2 or
            text_lower.count("google map") >= 2 or
            text_lower.count("shop no") >= 2 or
            text_lower.count("floor") >= 3
        )
        return location_signals

    def _split_into_sections(self, text: str) -> List[str]:
        """Split text into semantic sections by headings, FAQ pairs, tables."""
        lines = text.split("\n")
        sections: List[str] = []
        current: List[str] = []
        in_table = False
        in_faq = False

        for line in lines:
            is_heading = bool(HEADING_RE.match(line.strip())) and len(line.strip()) < 80
            is_faq_q = bool(FAQ_Q_RE.match(line.strip()))
            is_table_row = bool(TABLE_ROW_RE.match(line.strip()))
            is_break = bool(SECTION_BREAK_RE.match(line))

            # Table block: keep together
            if is_table_row:
                if not in_table and current:
                    sections.append("\n".join(current))
                    current = []
                in_table = True
                current.append(line)
                continue
            elif in_table:
                in_table = False
                sections.append("\n".join(current))
                current = []

            # FAQ block: keep Q+A together
            if is_faq_q:
                if current and not in_faq:
                    sections.append("\n".join(current))
                    current = []
                in_faq = True
                current.append(line)
                continue
            elif in_faq and FAQ_A_RE.match(line.strip()):
                current.append(line)
                sections.append("\n".join(current))
                current = []
                in_faq = False
                continue
            elif in_faq:
                in_faq = False

            # Heading or section break → start new section
            if (is_heading or is_break) and current:
                sections.append("\n".join(current))
                current = [line] if is_heading else []
                continue

            current.append(line)

        if current:
            sections.append("\n".join(current))

        return [s for s in sections if s.strip()]

    def _split_large_section(self, text: str) -> List[str]:
        """Split oversized section at sentence boundaries with overlap."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            if end < len(text):
                # Try sentence boundary
                last_period = max(chunk.rfind(". "), chunk.rfind(".\n"))
                if last_period > self.chunk_size // 2:
                    chunk = chunk[:last_period + 1]
                    end = start + last_period + 1
            chunks.append(chunk.strip())
            start = end - self.overlap
        return [c for c in chunks if c]

    def _merge_small_chunks(self, chunks: List[str]) -> List[str]:
        """Merge consecutive tiny chunks to avoid embedding noise."""
        merged = []
        buffer = ""
        for chunk in chunks:
            if len(buffer) + len(chunk) + 1 <= self.chunk_size // 2:
                buffer = (buffer + "\n" + chunk).strip()
            else:
                if buffer:
                    merged.append(buffer)
                buffer = chunk
        if buffer:
            merged.append(buffer)
        return merged

    def chunk_with_metadata(self, text: str, source: str = "", content_type: str = "page") -> List[Dict[str, Any]]:
        """
        Chunk text and return metadata-enriched chunk dicts.

        Dynamic sizing: each chunk is re-evaluated after type detection and
        re-split if it exceeds the type-appropriate size limit.
        parent_chunk_index enables parent-child retrieval — retrieve the small
        child chunk for precision, fetch the parent for full context when needed.
        """
        raw_chunks = self.chunk(text)
        result: List[Dict[str, Any]] = []

        for parent_idx, chunk in enumerate(raw_chunks):
            chunk_type = self._detect_chunk_type(chunk)
            type_limit = CHUNK_SIZE_BY_TYPE.get(chunk_type, self.chunk_size)

            if len(chunk) > type_limit:
                # Re-split oversized chunk using type-appropriate size
                sub_chunks = self._split_large_section_with_size(chunk, type_limit)
                for sub in sub_chunks:
                    result.append({
                        "content":           sub,
                        "chunk_index":       len(result),
                        "source":            source,
                        "total_chunks":      -1,   # fixed after loop
                        "chunk_type":        chunk_type,
                        "content_type":      content_type,
                        "parent_chunk_index":parent_idx,
                    })
            else:
                result.append({
                    "content":           chunk,
                    "chunk_index":       len(result),
                    "source":            source,
                    "total_chunks":      -1,
                    "chunk_type":        chunk_type,
                    "content_type":      content_type,
                    "parent_chunk_index":parent_idx,
                })

        # Fix total_chunks now that we know the final count
        total = len(result)
        for item in result:
            item["total_chunks"] = total

        return result

    def _split_large_section_with_size(self, text: str, size: int) -> List[str]:
        """Split a section using a specific size limit (used for dynamic chunking)."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + size
            chunk = text[start:end]
            if end < len(text):
                last_period = max(chunk.rfind(". "), chunk.rfind(".\n"))
                if last_period > size // 2:
                    chunk = chunk[:last_period + 1]
                    end = start + last_period + 1
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - self.overlap
        return chunks

    def _detect_chunk_type(self, chunk: str) -> str:
        if FAQ_Q_RE.search(chunk):
            return "faq"
        if TABLE_ROW_RE.search(chunk):
            return "table"
        if re.search(r'Price:|SKU:|Brand:|Availability:', chunk):
            return "product_spec"
        if re.search(r'#{1,6}\s', chunk):
            return "documentation"
        return "text"


# Drop-in replacement for existing text_chunker
class TextChunker(SemanticChunker):
    pass


text_chunker = SemanticChunker()
