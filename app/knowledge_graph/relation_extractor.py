"""
Relation Extractor — extracts entity relationships from text using
pattern matching and lightweight NLP.

Extracts:
  - Product → Category (belongs_to)
  - Product → Brand (made_by)
  - Product → Product (related_to, compatible_with, variant_of)
  - Product → Attribute (has_attribute)
  - Policy → Topic (covers)
"""
import re
from dataclasses import dataclass
from typing import List, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Relation:
    subject: str
    relation: str       # belongs_to | made_by | related_to | variant_of | has_attribute | covers
    obj: str
    confidence: float


# Relation patterns: (regex, subject_group, relation, object_group)
_PATTERNS: List[Tuple] = [
    # "X is a type of Y" / "X is a Y"
    (re.compile(r'([A-Z][a-zA-Z\s]{2,40})\s+is\s+a(?:\s+type\s+of)?\s+([a-z][a-z\s]{2,30})', re.I),
     1, "belongs_to", 2, 0.75),

    # "X by Brand" / "X from Brand"
    (re.compile(r'([A-Z][a-zA-Z\s]{2,40})\s+(?:by|from)\s+([A-Z][a-zA-Z]{2,30})', re.I),
     1, "made_by", 2, 0.80),

    # "X comes in Y" / "X available in Y"
    (re.compile(r'([A-Z][a-zA-Z\s]{2,40})\s+(?:comes?|available)\s+in\s+([a-z][a-z,\s/]{2,50})', re.I),
     1, "has_attribute", 2, 0.65),

    # "X and Y are similar" / "X is similar to Y"
    (re.compile(r'([A-Z][a-zA-Z\s]{2,40})\s+(?:is\s+)?similar\s+to\s+([A-Z][a-zA-Z\s]{2,40})', re.I),
     1, "related_to", 2, 0.70),

    # "X is a variant of Y"
    (re.compile(r'([A-Z][a-zA-Z\s]{2,40})\s+is\s+a\s+variant\s+of\s+([A-Z][a-zA-Z\s]{2,40})', re.I),
     1, "variant_of", 2, 0.85),

    # "X pairs well with Y" / "X goes with Y"
    (re.compile(r'([A-Z][a-zA-Z\s]{2,40})\s+(?:pairs?\s+well\s+with|goes?\s+with)\s+([A-Z][a-zA-Z\s]{2,40})', re.I),
     1, "compatible_with", 2, 0.70),

    # "return/shipping/warranty policy covers X"
    (re.compile(r'(return|shipping|warranty|refund)\s+policy\s+covers?\s+([a-z][a-z\s,]{2,60})', re.I),
     1, "covers", 2, 0.75),
]


class RelationExtractor:
    """Extract entity relationships from text content."""

    def extract(self, text: str) -> List[Relation]:
        """Extract all relations from a text block."""
        relations: List[Relation] = []
        if not text or len(text) < 20:
            return relations

        for pattern, subj_grp, relation, obj_grp, confidence in _PATTERNS:
            for m in pattern.finditer(text):
                subject = m.group(subj_grp).strip().rstrip(".,;")
                obj = m.group(obj_grp).strip().rstrip(".,;")
                if len(subject) > 2 and len(obj) > 2:
                    relations.append(Relation(
                        subject=subject,
                        relation=relation,
                        obj=obj,
                        confidence=confidence,
                    ))

        if relations:
            logger.debug("relations_extracted", count=len(relations), text_len=len(text))

        return relations

    def extract_from_chunks(self, chunks: List[dict]) -> List[Relation]:
        """Extract relations from a list of document chunks."""
        all_relations: List[Relation] = []
        for chunk in chunks:
            content = chunk.get("content", "")
            all_relations.extend(self.extract(content))
        return all_relations


relation_extractor = RelationExtractor()
