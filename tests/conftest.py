"""Pytest configuration and fixtures."""
import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.core.config import settings

# Test database
TEST_DATABASE_URL = "sqlite:///./test.db"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_db(test_engine):
    """Create test database session."""
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    session = TestSessionLocal()
    yield session
    session.close()


@pytest.fixture
def mock_openai(monkeypatch):
    """Mock OpenAI client."""
    async def mock_completion(*args, **kwargs):
        class MockChoice:
            def __init__(self):
                self.message = type('Message', (), {'content': 'Mock response'})()

        class MockResponse:
            def __init__(self):
                self.choices = [MockChoice()]

        return MockResponse()

    return mock_completion


@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis client."""
    class MockRedis:
        def __init__(self):
            self.data = {}

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value, ex=None):
            self.data[key] = value

        async def delete(self, key):
            if key in self.data:
                del self.data[key]

        async def exists(self, key):
            return key in self.data

    return MockRedis()
