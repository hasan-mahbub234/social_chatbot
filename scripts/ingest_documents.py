"""Ingest documents into RAG vector store."""
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, init_db
from app.rag.ingestion import document_ingestion


async def ingest_file(filepath: str, organization_id: str, source: str = None):
    """Ingest a single file into the vector store."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    db = SessionLocal()
    try:
        result = await document_ingestion.ingest(
            content=content,
            organization_id=organization_id,
            db=db,
            source=source or os.path.basename(filepath),
        )
        print(f"Ingested {filepath}: {result['chunks_created']} chunks")
        return result
    finally:
        db.close()


async def main():
    init_db()

    # Example: ingest all .txt files in a directory
    docs_dir = sys.argv[1] if len(sys.argv) > 1 else "./docs"
    org_id = sys.argv[2] if len(sys.argv) > 2 else "00000000-0000-0000-0000-000000000001"

    if not os.path.exists(docs_dir):
        print(f"Directory not found: {docs_dir}")
        return

    for filename in os.listdir(docs_dir):
        if filename.endswith((".txt", ".md")):
            filepath = os.path.join(docs_dir, filename)
            await ingest_file(filepath, org_id)


if __name__ == "__main__":
    asyncio.run(main())
