"""Tests for RAG engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_text_chunker_splits_long_text():
    """Test chunker splits text into correct chunks."""
    from app.rag.chunker import TextChunker

    chunker = TextChunker(chunk_size=100, overlap=20)
    text = "A" * 250
    chunks = chunker.chunk(text)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


@pytest.mark.asyncio
async def test_text_chunker_short_text():
    """Test chunker returns single chunk for short text."""
    from app.rag.chunker import TextChunker

    chunker = TextChunker(chunk_size=1000, overlap=100)
    text = "Short text"
    chunks = chunker.chunk(text)
    assert len(chunks) == 1
    assert chunks[0] == text


@pytest.mark.asyncio
async def test_chunker_with_metadata():
    """Test chunker attaches metadata to chunks."""
    from app.rag.chunker import TextChunker

    chunker = TextChunker(chunk_size=50, overlap=10)
    result = chunker.chunk_with_metadata("Hello world " * 20, source="test.txt")
    assert all("source" in c for c in result)
    assert all("chunk_index" in c for c in result)


@pytest.mark.asyncio
async def test_context_builder_formats_results():
    """Test context builder formats RAG results."""
    from app.rag.context_builder import ContextBuilder

    builder = ContextBuilder()
    results = [
        {"content": "Python is a programming language.", "source": "docs.txt", "similarity": 0.95},
        {"content": "FastAPI is a web framework.", "source": "api.txt", "similarity": 0.88},
    ]
    context = builder.build(results)
    assert "Python is a programming language" in context
    assert "FastAPI is a web framework" in context
    assert "Source 1" in context


@pytest.mark.asyncio
async def test_metadata_filters_apply():
    """Test metadata filters correctly filter results."""
    from app.rag.metadata_filters import MetadataFilters

    filters = MetadataFilters()
    results = [
        {"content": "doc1", "source": "file.pdf", "metadata": {"file_type": "pdf"}},
        {"content": "doc2", "source": "file.txt", "metadata": {"file_type": "txt"}},
    ]
    filtered = filters.apply(results, {"file_type": "pdf"})
    assert len(filtered) == 1
    assert filtered[0]["content"] == "doc1"
