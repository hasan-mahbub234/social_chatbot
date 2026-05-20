## ProjectDetails.md

## Overview

Enterprise AI Chatbot is a production-grade, multi-tenant SaaS AI chatbot platform built with FastAPI for modern business communication automation.

The platform provides:

- AI-powered conversational automation
- Multi-tenant SaaS architecture
- RAG-based knowledge retrieval
- Governance & hallucination protection
- Voice + image understanding
- AI orchestration pipelines
- Billing & quota management
- Human escalation workflows
- Multi-channel messaging support
- Enterprise observability & analytics

The system is designed to support:

- Website AI chatbots
- WhatsApp AI automation
- Instagram DM automation
- Facebook Messenger automation
- Slack/chat integrations
- AI support assistants
- AI sales assistants
- AI internal knowledge assistants

The platform uses Retrieval-Augmented Generation (RAG) instead of fine-tuning for business knowledge isolation.

---

# Core Architecture

| Component               | Technology                |
| ----------------------- | ------------------------- |
| Version                 | 2.0.0                     |
| Python                  | 3.12+                     |
| Framework               | FastAPI 0.114.2 + Uvicorn |
| Database                | PostgreSQL 15 + pgvector  |
| Cache & Queue           | Redis 7 + Celery 5        |
| Primary AI Provider     | OpenAI                    |
| Development AI Provider | Groq AI                   |
| Billing                 | Stripe                    |
| Storage                 | AWS S3                    |
| Deployment              | AWS EC2 / Docker          |
| Architecture            | Multi-tenant SaaS         |

---

# AI Models Configuration

| Task                              | Recommended Model                       |
| --------------------------------- | --------------------------------------- |
| Chat replies                      | GPT-4o-mini                             |
| Premium smart replies             | GPT-4o                                  |
| Embeddings/RAG (Production)       | text-embedding-3-small                  |
| Voice transcription               | gpt-4o-mini-transcribe / Whisper        |
| Development inference (local/dev) | Groq AI                                 |
| Development embeddings            | sentence-transformers/all-mpnet-base-v2 |

---

# AI Provider Strategy

## Production Environment (AWS Deployment)

Production deployment uses:

- OpenAI GPT models
- OpenAI embeddings (`text-embedding-3-small`)
- OpenAI transcription APIs
- AWS infrastructure
- pgvector vector database

### Production Goals

- High-quality embeddings
- Stable semantic search
- Better multilingual retrieval
- Managed inference
- Enterprise-grade reliability

---

## Development Environment

During development, the system uses:

- Groq AI models for fast inference
- `sentence-transformers/all-mpnet-base-v2` for local embeddings

This reduces development cost significantly.

### Development Benefits

- Lower API cost
- Faster testing
- Local embedding generation
- Rapid prototyping
- Cheap experimentation

---

# Backend Project Structure

```bash
enterprise-ai-chatbot/
├── app/
│
│   ├── main.py
│
│   ├── api/
│   │   ├── auth.py
│   │   ├── agents.py
│   │   ├── conversations.py
│   │   ├── uploads.py
│   │   ├── voice.py
│   │   ├── webhooks.py
│   │   ├── billing.py
│   │   ├── subscriptions.py
│   │   ├── plans.py
│   │   ├── usage.py
│   │   ├── quotas.py
│   │   ├── analytics.py
│   │   ├── governance.py
│   │   ├── hallucination.py
│   │   ├── risk.py
│   │   ├── organizations.py
│   │   ├── health.py
│   │   └── admin.py
│
│   ├── core/
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── database.py
│   │   ├── dependencies.py
│   │   ├── permissions.py
│   │   ├── security.py
│   │   ├── logging.py
│   │   ├── secrets.py
│   │   ├── redis_client.py
│   │   ├── rate_limiter.py
│   │   └── middleware_config.py
│
│   ├── models/
│   │   ├── user.py
│   │   ├── organization.py
│   │   ├── organization_member.py
│   │   ├── agent.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── uploaded_file.py
│   │   ├── embedding.py
│   │   ├── audit_log.py
│   │   ├── governance_log.py
│   │   ├── hallucination_log.py
│   │   ├── risk_assessment.py
│   │   ├── escalation.py
│   │   ├── subscription.py
│   │   ├── invoice.py
│   │   ├── payment.py
│   │   ├── usage_meter.py
│   │   ├── api_usage.py
│   │   ├── feature_flag.py
│   │   └── cache_entry.py
│
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── agent.py
│   │   ├── organization.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── upload.py
│   │   ├── billing.py
│   │   ├── governance.py
│   │   ├── hallucination.py
│   │   ├── risk.py
│   │   └── common.py
│
│   ├── orchestrator/
│   │   ├── orchestrator.py
│   │   ├── request_router.py
│   │   ├── model_router.py
│   │   ├── context_manager.py
│   │   ├── response_pipeline.py
│   │   ├── fallback_manager.py
│   │   └── service.py
│
│   ├── rag/
│   │   ├── engine.py
│   │   ├── retriever.py
│   │   ├── embeddings.py
│   │   ├── vector_store.py
│   │   ├── ingestion.py
│   │   ├── chunker.py
│   │   ├── reranker.py
│   │   ├── metadata_filters.py
│   │   ├── context_builder.py
│   │   └── sync_manager.py
│
│   ├── crawler/
│   │   ├── engine.py
│   │   ├── scraper.py
│   │   ├── extractor.py
│   │   ├── sitemap_parser.py
│   │   ├── product_detector.py
│   │   ├── content_cleaner.py
│   │   ├── sync_manager.py
│   │   └── page_hashing.py
│
│   ├── governance/
│   │   ├── governance_service.py
│   │   ├── pii_detector.py
│   │   ├── moderation.py
│   │   ├── jailbreak_detector.py
│   │   ├── compliance_rules.py
│   │   ├── engine.py
│   │   └── policy_engine.py
│
│   ├── hallucination/
│   │   ├── validator.py
│   │   ├── contradiction_checker.py
│   │   ├── confidence_scorer.py
│   │   ├── unsupported_claim_detector.py
│   │   └── regeneration.py
│
│   ├── risk/
│   │   ├── risk_engine.py
│   │   ├── fraud_detection.py
│   │   ├── abuse_detector.py
│   │   ├── escalation_rules.py
│   │   └── scoring.py
│
│   ├── memory/
│   │   ├── memory_manager.py
│   │   ├── conversation_memory.py
│   │   ├── rolling_summary.py
│   │   └── summarizer.py
│
│   ├── cache/
│   │   ├── semantic_cache.py
│   │   ├── session_cache.py
│   │   ├── token_cache.py
│   │   ├── response_cache.py
│   │   ├── cache_keys.py
│   │   ├── decorators.py
│   │   └── manager.py
│
│   ├── billing/
│   │   ├── service.py
│   │   ├── metering.py
│   │   ├── analytics.py
│   │   └── webhook_handler.py
│
│   ├── quota/
│   │   └── enforcer.py
│
│   ├── feature_flags/
│   │   └── service.py
│
│   ├── plans/
│   │   ├── definitions.py
│   │   └── seeder.py
│
│   ├── integrations/
│   │   ├── whatsapp.py
│   │   ├── instagram.py
│   │   ├── messenger.py
│   │   ├── slack.py
│   │   ├── webhooks.py
│   │   ├── email.py
│   │   ├── s3.py
│   │   └── manager.py
│
│   ├── services/
│   │   ├── llm.py
│   │   ├── openai_service.py
│   │   ├── groq_service.py
│   │   ├── embedding_service.py
│   │   ├── voice_service.py
│   │   ├── upload_service.py
│   │   ├── analytics_service.py
│   │   ├── response_service.py
│   │   ├── conversation_service.py
│   │   ├── hallucination_validator.py
│   │   ├── risk_assessment.py
│   │   ├── semantic_cache.py
│   │   └── orchestrator.py
│
│   ├── middleware/
│   │   ├── auth_middleware.py
│   │   ├── logging_middleware.py
│   │   ├── rate_limit_middleware.py
│   │   ├── tenant_rate_limit.py
│   │   ├── request_id_middleware.py
│   │   ├── security_headers.py
│   │   ├── exception_middleware.py
│   │   ├── cors.py
│   │   └── request_tracking.py
│
│   ├── observability/
│   │   ├── metrics.py
│   │   ├── tracing.py
│   │   ├── dashboards.py
│   │   ├── audit_logger.py
│   │   ├── performance_monitor.py
│   │   └── cost_tracking.py
│
│   ├── workers/
│   │   ├── celery_config.py
│   │   ├── tasks.py
│   │   ├── embedding_tasks.py
│   │   ├── crawler_tasks.py
│   │   ├── governance_tasks.py
│   │   ├── hallucination_tasks.py
│   │   ├── risk_tasks.py
│   │   ├── analytics_tasks.py
│   │   ├── cleanup_tasks.py
│   │   └── queues.py
│
│   ├── tenancy/
│   │   ├── context.py
│   │   └── dependencies.py
│
│   ├── prompts/
│   │   ├── governance/
│   │   ├── hallucination/
│   │   ├── rag/
│   │   ├── risk/
│   │   ├── summarization/
│   │   └── templates.py
│
│   ├── utils/
│   │   ├── helpers.py
│   │   ├── validators.py
│   │   ├── retry.py
│   │   ├── file_utils.py
│   │   ├── json_utils.py
│   │   ├── token_counter.py
│   │   └── time_utils.py
│
│   └── exceptions/
│       ├── custom_exceptions.py
│       ├── error_codes.py
│       └── handlers.py
│
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── infrastructure/
│   ├── docker-compose.yml
│   ├── ecs/
│   └── terraform/
│
├── docker/
│   ├── fastapi/
│   ├── celery/
│   ├── nginx/
│   └── postgres/
│
├── scripts/
│   ├── seed_data.py
│   ├── setup.sh
│   ├── start.sh
│   ├── migrate.sh
│   └── ingest_documents.py
│
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   ├── prod.txt
│   ├── test.txt
│   └── ai-heavy.txt
│
├── tests/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── Makefile
└── .env.example
```

---

# System Architecture Flow

```text
Client Request
      ↓
API Gateway / FastAPI
      ↓
Authentication & Tenant Resolution
      ↓
Quota & Plan Validation
      ↓
Governance Pipeline
      ↓
Risk Assessment
      ↓
Semantic Cache Lookup
      ↓
Intent Classification
      ↓
AI Model Router
      ↓
RAG Retrieval
      ↓
LLM Execution
      ↓
Hallucination Validation
      ↓
Response Builder
      ↓
Billing Metering
      ↓
Analytics & Observability
      ↓
Final AI Response
```

---

# AI Orchestration Pipeline

The `AIOrchestrator.process()` method executes:

1. Tenant resolution
2. Subscription validation
3. Quota enforcement
4. Feature access resolution
5. Semantic cache lookup
6. Governance evaluation
7. Risk scoring
8. Intent classification
9. AI model routing
10. RAG retrieval
11. LLM execution
12. Hallucination validation
13. Response generation
14. Billing metering
15. Observability tracking
16. Cache persistence

---

# RAG Knowledge System

## Supported Data Sources

- Website URLs
- PDFs
- DOCX files
- FAQs
- Policies
- Blogs
- Product pages
- Manual text input

---

## RAG Flow

```text
Data Source
    ↓
Crawler / File Upload
    ↓
Content Extraction
    ↓
Text Cleaning
    ↓
Chunking
    ↓
Embedding Generation
    ↓
pgvector Storage
    ↓
Semantic Retrieval
    ↓
LLM Context Injection
```

---

# Embedding Strategy

## Development

Uses:

- `sentence-transformers/all-mpnet-base-v2`

Reason:

- Free local embeddings
- Cheap experimentation
- Faster testing

---

## Production

Uses:

- `text-embedding-3-small`

Reason:

- Better multilingual quality
- Better semantic similarity
- Lower operational complexity
- Managed embedding infrastructure

---

# Governance Pipeline

The governance system runs on every request.

## Components

### Jailbreak Detection

Detects:

- Prompt injection
- System override attempts
- Role manipulation attacks

---

### Moderation

Detects:

- Toxic content
- Abuse
- Unsafe instructions

---

### PII Detection

Detects:

- Email
- Phone number
- Credit card
- Passwords
- Tokens
- API keys

---

### Compliance Engine

Supports:

- Enterprise rules
- Content policies
- Business restrictions

---

# Hallucination Detection

The hallucination engine validates responses against retrieved context.

## Components

- Contradiction detection
- Unsupported claim detection
- Semantic confidence scoring
- Regeneration system

---

# Human Escalation System

Features:

- Human takeover
- Conversation locking
- AI pause/resume
- Moderator assignment
- Escalation tracking

---

# Multi-Channel Integrations

Supported integrations:

- WhatsApp Cloud API
- Instagram DM
- Facebook Messenger
- Website live chat
- Slack
- Generic webhooks

Future support:

- Telegram
- Discord
- TikTok messaging

---

# Voice & Multimedia AI

Supported features:

- Voice transcription
- AI voice replies
- Image understanding
- Multilingual support

---

# Subscription Plans

| Feature             | free | Growth | Dediacted (Client Infa) |
| ------------------- | ---- | ------ | ----------------------- |
| Conversations/month | 100  | 5,000  | clients demand          |
| AI Agents           | 1    | 5      | clients demand          |
| Storage             | 50MB | 5GB    | clients demand          |
| Voice Minutes       | 0    | 120    | clients demand          |
| API Calls/day       | 200  | 10,000 | clients demand          |
| Team Members        | 1    | 5      | clients demand          |
| GPT-4o Access       | ✗    | ✓      | ✓                       |
| Voice AI            | ✗    | ✓      | ✓                       |
| Advanced Governance | ✗    | ✗      | ✓                       |
| Webhooks            | ✗    | ✓      | ✓                       |
| Analytics Dashboard | ✗    | ✓      | ✓                       |

---

# Celery Task Queues

| Queue           | Purpose                  |
| --------------- | ------------------------ |
| ai_processing   | AI response generation   |
| embeddings      | Embedding generation     |
| crawler         | Website crawling         |
| governance      | Governance checks        |
| hallucination   | Hallucination validation |
| risk_assessment | Risk scoring             |
| analytics       | Metrics aggregation      |
| cleanup         | Cleanup jobs             |
| escalation      | Human escalation         |

---

# Database Architecture

## Core Tables

- users
- organizations
- organization_members
- agents
- conversations
- messages
- uploaded_files
- embeddings
- audit_logs
- governance_logs
- hallucination_logs
- risk_assessments
- subscriptions
- invoices
- payments
- usage_meters
- feature_flags
- cache_entries

---

# Infrastructure Recommendation

## Initial MVP Infrastructure

| Service          | Infrastructure   |
| ---------------- | ---------------- |
| EC2              | t3.small         |
| OS               | Ubuntu 24.04 LTS |
| Reverse Proxy    | Nginx            |
| Database         | PostgreSQL 15    |
| Queue            | Redis 7          |
| Background Tasks | Celery           |
| Storage          | AWS S3           |

---

# Infrastructure Evolution

## Phase 1 — MVP

- Single EC2
- Docker Compose
- Shared infrastructure

---

## Phase 2 — Growth

- Managed PostgreSQL
- Dedicated Redis
- ECS migration
- Multi-worker scaling

---

## Phase 3 — Enterprise Scale

- Kubernetes / EKS
- Distributed workers
- Dedicated GPU inference
- Multi-region deployment

---

# Environment Variables

```env
# Core
DATABASE_URL=postgresql://user:pass@localhost:5432/enterprise_ai_chatbot
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key

# OpenAI
OPENAI_API_KEY=sk-...

# Groq AI (Development)
GROQ_API_KEY=gsk_...

# Embeddings
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Development Embeddings
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2

# Stripe
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...

# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=enterprise-ai-chatbot

# Governance
ENABLE_GOVERNANCE=True
HALLUCINATION_THRESHOLD=60
RISK_ESCALATION_THRESHOLD=70
```

---

# Development Commands

```bash
make install
make dev
make run
make worker
make beat
make flower
make migrate
make seed
make test
make lint
make docker-up
make ingest
```

---

# Key Technologies

| Technology            | Purpose                |
| --------------------- | ---------------------- |
| FastAPI               | Backend framework      |
| PostgreSQL + pgvector | Vector search          |
| Redis                 | Cache & queues         |
| Celery                | Async tasks            |
| OpenAI                | Production AI          |
| Groq AI               | Development AI         |
| Docker                | Containerization       |
| AWS EC2               | Hosting                |
| Stripe                | Billing                |
| Whisper               | Voice transcription    |
| sentence-transformers | Development embeddings |

---

# Observability

The platform includes:

- Structured logging
- Prometheus metrics
- Request tracing
- AI cost tracking
- SaaS analytics
- Hallucination analytics
- Cache analytics
- Sentry integration

---

# RBAC Roles

| Role   | Permissions            |
| ------ | ---------------------- |
| Owner  | Full access            |
| Admin  | Agent + org management |
| Member | Conversation access    |
| Viewer | Read-only access       |

---

# Middleware Stack

1. Authentication middleware
2. Request ID middleware
3. Logging middleware
4. Rate limit middleware
5. Tenant rate limiter
6. Security headers middleware
7. Exception middleware
8. CORS middleware

---

# RAG Evolution — Retrieval Intelligence Platform

The platform has been upgraded from Classic RAG to a 5-layer Retrieval Intelligence Platform. All changes are backward-compatible. No infrastructure migration required except running `alembic upgrade head` for the BM25 index.

---

## What Changed and Why

The core problem before this upgrade was disconnected intelligence layers. `knowledge_fusion`, `entity_graph`, `product_retriever`, and `completeness_engine` were all built and working but the main `retriever.py` and `orchestrator.py` did not use most of them. The keyword search was fake hybrid (ILIKE table scan with no ranking). The reranker re-embedded everything for zero accuracy gain. Chunks were embedded without context so attribute chunks like `"100% POLYESTER WOVEN"` had no product identity in their vector.

---

## 5-Layer Retrieval Architecture

```text
Layer 1 — Core Retrieval
  Hybrid Search: pgvector cosine similarity + PostgreSQL ts_rank BM25
  Real TF-IDF weighted full-text search via generated tsvector column + GIN index

Layer 2 — Contextual Embeddings
  Anthropic-style contextual retrieval
  Context header (Title / Type / Platform / Source / Section) prepended before embedding
  Original content stored unchanged — only the embedding vector is richer

Layer 3 — Knowledge Intelligence
  knowledge_fusion wired into product_retriever after entity reconstruction
  entity_graph affinity scoring added to ranking formula
  Ranking: relevance×0.55 + completeness×0.35 + graph_boost×0.10

Layer 4 — Agentic RAG
  Multi-step retrieval loop in orchestrator for reasoning/comparison intents
  LLM checks sufficiency after each retrieval step (max 3 loops)
  Refines query based on what is missing before next retrieval pass

Layer 5 — Long-Context Fallback
  When agentic RAG returns 0 results, routes to smart model (GPT-4o / Groq 70B)
  model_router already selects GPT4O for reasoning intent — fallback is automatic
```

---

## Files Changed

### New File — `alembic/versions/004_fts_bm25_index.py`

Adds a `tsvector` generated column and GIN index to `document_chunks`.

```sql
ALTER TABLE document_chunks
    ADD COLUMN fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

CREATE INDEX ix_document_chunks_fts ON document_chunks USING GIN(fts);
```

Apply with: `alembic upgrade head`

---

### Updated — `app/rag/retriever.py`

`_keyword_search()` replaced from ILIKE to real PostgreSQL BM25:

```python
# Before (fake hybrid — sequential table scan, no ranking)
content ILIKE '%word%'

# After (real BM25 — TF-IDF weighted, GIN-indexed)
fts @@ plainto_tsquery('english', :query)
ORDER BY ts_rank(fts, ...) DESC
```

Falls back to ILIKE automatically if migration 004 has not been applied yet.

Also wires `retrieval_observability.record_retrieval()` at the end of every `retrieve()` call to track quality metrics in real time.

---

### Updated — `app/rag/product_retriever.py`

Three changes in one file:

**1. BM25 keyword search** — same replacement as `retriever.py`, with identical fallback pattern.

**2. Knowledge fusion wired** — after `_reconstruct_entity()`, calls `knowledge_fusion.fuse()` with all chunk sources. Enriches each `ProductEntity` with confidence-aware field resolution and conflict detection before ranking.

**3. Entity graph affinity scoring** — ranking formula upgraded:

```python
# Before
relevance * 0.6 + completeness * 0.4

# After
relevance * 0.55 + completeness * 0.35 + graph_boost * 0.10
# graph_boost = min(0.10, len(graph_neighbors) * 0.02)
```

Products with more graph connections (related products, collection memberships) rank higher.

---

### Updated — `app/rag/ingestion.py`

Added `_build_context_header()` — prepends a short context header before embedding each chunk. The header is NOT stored, only used to produce a richer embedding vector.

```python
# Before — chunk embedded in isolation
"100% POLYESTER WOVEN"

# After — chunk embedded with context header
"Title: Wave Riders Woven Swim Shorts
Type: product
Platform: shopify
Source: /products/wave-riders-swim-shorts
Section: product_spec

100% POLYESTER WOVEN"
```

This is Anthropic's contextual retrieval technique. Attribute chunks that previously had no product identity in their vector now embed with full context. Dramatically improves recall for material, shipping, care instruction, and variant chunks.

---

### Rewritten — `app/rag/reranker.py`

Complete rewrite. Old reranker re-embedded all chunks and computed cosine similarity again — identical to what the vector store already did, just slower.

New reranker uses `BAAI/bge-reranker-base` cross-encoder:

```python
# Old approach (wrong)
query_vector ↔ chunk_vector   # independent, approximate, redundant

# New approach (correct)
(query + chunk) → relevance   # joint scoring, fundamentally more accurate
```

Cross-encoder is loaded once as a singleton. Falls back to similarity sort (not re-embedding) when unavailable. Works in both dev (local model) and prod (same model, Cohere optional upgrade).

---

### Replaced — `app/rag/engine.py`

The old `engine.py` defined a `Document` model pointing at a `documents` table with `Vector(1536)` that does not exist in the live schema. It was never called by any production code path. Replaced with a 4-line compatibility shim:

```python
from app.rag.retriever import rag_retriever as rag_engine
from app.rag.ingestion import document_ingestion
from app.rag.product_retriever import product_retriever
```

---

### Updated — `app/rag/chunker.py`

Added `CHUNK_SIZE_BY_TYPE` — dynamic chunk sizes based on content type:

| Chunk Type    | Size  | Reason                                          |
| ------------- | ----- | ----------------------------------------------- |
| product_spec  | 800   | Small — precise field retrieval (price/SKU)     |
| faq           | 1200  | Medium — Q+A pairs need both question and answer |
| table         | 1500  | Medium — table rows need surrounding header     |
| documentation | 3000  | Large — technical docs need surrounding context |
| article       | 2500  | Large — narrative flow breaks badly when small  |
| text / page   | 2000  | Default general content                         |

`chunk_with_metadata()` now detects chunk type first, then re-splits oversized chunks using the type-appropriate limit. Added `parent_chunk_index` field to every chunk for future parent-child retrieval — retrieve the small child chunk for precision, fetch the parent for full context when needed.

---

### New File — `app/observability/retrieval_observability.py`

Tracks RAG quality metrics in real time. Exposed via `GET /api/v1/product/retrieval-health`.

| Metric                          | What it tells you                                        |
| ------------------------------- | -------------------------------------------------------- |
| no_result_rate                  | % of queries returning 0 chunks — retrieval failure     |
| low_confidence_rate             | % of queries with top similarity < 0.5 — poor match     |
| bm25_hit_rate                   | % of queries where BM25 added results vector missed     |
| reranker_usage_rate             | % of queries that used cross-encoder reranker           |
| cache_hit_rate                  | % of queries served from semantic cache                 |
| avg_top_similarity              | Average best similarity score across all queries        |
| hallucination_rate              | % of queries where hallucination was detected           |
| hallucination_no_context_rate   | Hallucinations with no RAG context = retrieval failure  |
| hallucination_with_context_rate | Hallucinations despite context = LLM or prompt issue    |

---

### Updated — `app/api/products.py`

Added `GET /api/v1/product/retrieval-health` endpoint:

```
GET /api/v1/product/retrieval-health
```

Returns the full retrieval observability summary. Use this to:
- Confirm BM25 is working after migration 004 (`bm25_hit_rate > 0`)
- Detect retrieval failures (`no_result_rate > 0.1` = problem)
- Correlate hallucinations with retrieval quality
- Monitor reranker adoption rate

---

### Updated — `app/orchestrator/orchestrator.py`

Added `_agentic_retrieve()` method — multi-step retrieval loop for complex queries:

```text
Query (intent=reasoning or comparison)
  ↓
Step 1: RAG retrieve (top_k chunks)
  ↓
LLM check (GPT-4o-mini): "Is this context sufficient?"
  ↓ YES → return context
  ↓ NO  → extract what's missing → refine query → Step 2
  ↓
Step 2: RAG retrieve (refined query)
  ↓
LLM check again
  ↓ YES → return context
  ↓ NO  → Step 3 (max 3 loops)
  ↓
Return best context found
  ↓
If 0 results → long-context fallback (GPT-4o / Groq 70B)
```

Only triggered for `intent=reasoning` or `intent=comparison`. All other intents use the existing single-step path unchanged — no performance impact on normal queries.

---

## Retrieval Pipeline — Before vs After

```text
BEFORE
  Query → embed → vector search → ILIKE keyword → merge → cosine rerank → context

AFTER
  Query → embed (contextual) → vector search → BM25 ts_rank → merge
        → cross-encoder rerank → knowledge fusion → graph affinity score
        → dynamic chunk assembly → context
        [reasoning/comparison only: multi-step agentic loop]
```

---

## How to Apply

```bash
# 1. Apply BM25 database migration
alembic upgrade head

# 2. Install cross-encoder (if not already installed)
pip install sentence-transformers

# 3. Restart the application
make run

# 4. Verify BM25 is working
curl -H "Authorization: Bearer <token>" \
     http://localhost:8000/api/v1/product/retrieval-health
# Expect: bm25_hit_rate > 0 after first few queries

# 5. Re-ingest existing content for contextual embeddings
# (existing chunks use old embeddings — re-crawl or re-upload to get contextual ones)
# New content ingested after the upgrade automatically gets contextual embeddings
```

---

## Key Technologies Added

| Technology              | Purpose                                      |
| ----------------------- | -------------------------------------------- |
| PostgreSQL tsvector     | Real BM25 full-text search with ts_rank      |
| BAAI/bge-reranker-base  | Cross-encoder reranker (joint query+chunk)   |
| Contextual embeddings   | Anthropic-style context header before embed  |
| knowledge_fusion        | Cross-source entity field merging (wired)    |
| entity_graph            | Graph affinity scoring in ranking (wired)    |
| RetrievalObservability  | Real-time retrieval quality dashboard        |
| Agentic RAG loop        | Multi-step retrieval for reasoning intents   |
| Dynamic chunking        | Content-type-aware chunk size limits         |
| parent_chunk_index      | Parent-child retrieval foundation            |
