"""
SQL Agent — executes safe read-only SQL queries for analytics questions.
Only SELECT queries allowed. No DDL, DML, or multi-statement queries.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.logging import get_logger

logger = get_logger(__name__)

# Allowed tables for SQL agent queries
ALLOWED_TABLES = {
    "document_chunks", "crawled_pages", "conversations",
    "messages", "usage_meters", "tenant_usage",
}

_DANGEROUS_RE = re.compile(
    r'\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE)\b',
    re.I,
)


@dataclass
class SQLResult:
    success: bool
    rows: List[Dict[str, Any]]
    row_count: int
    error: Optional[str] = None


class SQLAgentTool:
    """Execute safe read-only SQL queries."""

    def is_safe(self, sql: str) -> bool:
        """Check if SQL is safe to execute."""
        if _DANGEROUS_RE.search(sql):
            return False
        if not sql.strip().upper().startswith("SELECT"):
            return False
        # Check only allowed tables are referenced
        tables_in_query = re.findall(r'\bFROM\s+(\w+)', sql, re.I)
        tables_in_query += re.findall(r'\bJOIN\s+(\w+)', sql, re.I)
        return all(t.lower() in ALLOWED_TABLES for t in tables_in_query)

    def execute(self, sql: str, db: Session, params: Dict = None) -> SQLResult:
        """Execute a safe SELECT query."""
        if not self.is_safe(sql):
            return SQLResult(success=False, rows=[], row_count=0, error="Query not allowed")
        try:
            result = db.execute(text(sql), params or {})
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result.fetchall()]
            return SQLResult(success=True, rows=rows, row_count=len(rows))
        except Exception as e:
            logger.warning("sql_agent_failed", error=str(e))
            return SQLResult(success=False, rows=[], row_count=0, error=str(e))


sql_agent_tool = SQLAgentTool()
