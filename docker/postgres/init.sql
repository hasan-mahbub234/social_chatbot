-- PostgreSQL initialization script
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Document chunks table for RAG
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL,
    agent_id UUID,
    content TEXT NOT NULL,
    embedding vector(768),
    source VARCHAR(500),
    chunk_index INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
    ON document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS document_chunks_org_idx ON document_chunks(organization_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO aiagent;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO aiagent;
