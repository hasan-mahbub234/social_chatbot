"""
RAG engine — compatibility shim.

The old engine.py defined a Document model pointing at a 'documents' table
with Vector(1536) that does not exist in the live schema. It was never called
by any production code path.

All retrieval  → app.rag.retriever.RAGRetriever
All ingestion  → app.rag.ingestion.DocumentIngestion
Product search → app.rag.product_retriever.ProductRetriever
"""
from app.rag.retriever import rag_retriever as rag_engine          # noqa: F401
from app.rag.ingestion import document_ingestion                    # noqa: F401
from app.rag.product_retriever import product_retriever             # noqa: F401

__all__ = ["rag_engine", "document_ingestion", "product_retriever"]
