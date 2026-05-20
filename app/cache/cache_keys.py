"""Cache key generators."""
import hashlib
from typing import Optional


def semantic_cache_key(agent_id: str) -> str:
    return f"semantic_cache:{agent_id}"


def session_cache_key(session_id: str) -> str:
    return f"session:{session_id}"


def token_cache_key(token: str) -> str:
    hashed = hashlib.sha256(token.encode()).hexdigest()[:16]
    return f"token:{hashed}"


def response_cache_key(query: str, agent_id: str) -> str:
    hashed = hashlib.md5(f"{agent_id}:{query}".encode()).hexdigest()
    return f"response:{hashed}"


def rate_limit_key(identifier: str, path: str = "") -> str:
    return f"rate_limit:{identifier}:{path}"


def embedding_cache_key(text: str) -> str:
    hashed = hashlib.md5(text.encode()).hexdigest()
    return f"embedding:{hashed}"


def org_cost_key(organization_id: str, period: str = "month") -> str:
    return f"org_cost:{organization_id}:{period}"
