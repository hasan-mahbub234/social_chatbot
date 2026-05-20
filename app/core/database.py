"""Database configuration and session management."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Create database engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,
    future=True,
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

# Create base class for models
Base = declarative_base()


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    import app.models  # noqa: F401 — side-effect import registers all tables
    Base.metadata.create_all(bind=engine)

    # Create document_chunks table (raw SQL — pgvector type not in SQLAlchemy model)
    with engine.connect() as conn:
        conn.execute(__import__('sqlalchemy').text("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id          SERIAL PRIMARY KEY,
                organization_id UUID NOT NULL,
                content     TEXT NOT NULL,
                embedding   vector(768),
                source      TEXT DEFAULT '',
                chunk_index INTEGER DEFAULT 0,
                metadata    JSONB DEFAULT '{}',
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(__import__('sqlalchemy').text("""
            CREATE INDEX IF NOT EXISTS ix_document_chunks_org
            ON document_chunks (organization_id)
        """))
        conn.commit()



@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Enable pgvector extension on connection."""
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.close()
    except Exception as e:
        logger.warning(f"Could not enable pgvector: {e}")
