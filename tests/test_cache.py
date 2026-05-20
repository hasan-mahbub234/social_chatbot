"""Tests for cache layer."""
import pytest
from unittest.mock import AsyncMock, patch
import json


@pytest.mark.asyncio
async def test_cache_keys_are_deterministic():
    """Test cache key generation is deterministic."""
    from app.cache.cache_keys import semantic_cache_key, response_cache_key

    key1 = semantic_cache_key("agent-123")
    key2 = semantic_cache_key("agent-123")
    assert key1 == key2

    rkey1 = response_cache_key("same query", "agent-123")
    rkey2 = response_cache_key("same query", "agent-123")
    assert rkey1 == rkey2


@pytest.mark.asyncio
async def test_cache_keys_differ_for_different_inputs():
    """Test cache keys differ for different inputs."""
    from app.cache.cache_keys import response_cache_key

    key1 = response_cache_key("query A", "agent-1")
    key2 = response_cache_key("query B", "agent-1")
    assert key1 != key2


@pytest.mark.asyncio
async def test_semantic_cache_miss():
    """Test semantic cache returns None on miss."""
    from app.cache.semantic_cache import SemanticCache

    cache = SemanticCache()

    with patch("app.cache.semantic_cache.redis_client") as mock_redis:
        mock_redis.get = AsyncMock(return_value=None)

        result = await cache.get("test query", "agent-123")
        assert result is None


@pytest.mark.asyncio
async def test_session_cache_set_get():
    """Test session cache stores and retrieves data."""
    from app.cache.session_cache import SessionCache

    cache = SessionCache()
    test_data = {"user_id": "123", "role": "admin"}

    with patch("app.cache.session_cache.redis_client") as mock_redis:
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(test_data))

        await cache.set("session-abc", test_data)
        result = await cache.get("session-abc")

        assert result == test_data


@pytest.mark.asyncio
async def test_token_cache_blacklist():
    """Test token cache blacklisting."""
    from app.cache.token_cache import TokenCache

    cache = TokenCache()

    with patch("app.cache.token_cache.redis_client") as mock_redis:
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({"blacklisted": True}))

        await cache.invalidate("some-token")
        is_blacklisted = await cache.is_blacklisted("some-token")
        assert is_blacklisted is True
