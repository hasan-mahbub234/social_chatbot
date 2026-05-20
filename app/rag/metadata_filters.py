"""Metadata filters for RAG retrieval."""
from typing import Dict, Any, List, Optional


class MetadataFilters:
    """Build and apply metadata filters for RAG search."""

    def build(
        self,
        organization_id: str,
        agent_id: Optional[str] = None,
        file_type: Optional[str] = None,
        source: Optional[str] = None,
        date_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build filter dict for vector store queries."""
        filters: Dict[str, Any] = {"organization_id": organization_id}
        if agent_id:
            filters["agent_id"] = agent_id
        if file_type:
            filters["file_type"] = file_type
        if source:
            filters["source"] = source
        if date_from:
            filters["date_from"] = date_from
        return filters

    def apply(self, results: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """Post-filter results by metadata."""
        filtered = results
        if "file_type" in filters:
            filtered = [r for r in filtered if r.get("metadata", {}).get("file_type") == filters["file_type"]]
        if "source" in filters:
            filtered = [r for r in filtered if filters["source"] in r.get("source", "")]
        return filtered


metadata_filters = MetadataFilters()
