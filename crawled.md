# Enterprise AI Crawler & Scraping System — Complete Architecture

## Overview

This is a production-grade distributed web crawling and scraping system built into the Enterprise AI Agent Platform. Its sole purpose is to crawl websites, extract structured content, and ingest it into the RAG (Retrieval-Augmented Generation) vector store so AI agents can answer questions about that content.

The system crawled **612 pages** from `turaag.com` in **27 minutes** at **22.5 pages/minute** with **0 browser renders** (all static extraction), ingesting product data, store locations, policies, and blog content into pgvector for AI retrieval.

---

## System Architecture — End to End

```
API Request (POST /api/v1/knowledge/crawl)
         │
         ▼
  CrawlerEngine.crawl()
         │
         ├── 1. Create CrawlJob in PostgreSQL
         │
         ├── 2. URL Discovery
         │       ├── SitemapParser → /sitemap.xml, /sitemap_index.xml, /wp-sitemap.xml
         │       └── Shopify Products API → /products.json?limit=250&page=N (paginated)
         │
         ├── 3. URL Frontier (Redis Sorted Set)
         │       ├── Canonical URL normalization (strip utm_*, fbclid, sort, filter)
         │       ├── Deduplication (Redis SET of MD5 hashes)
         │       ├── Priority scoring (products=0, faq=5, blog=10, collections=15)
         │       └── Skip patterns (cart, checkout, login, .pdf, .jpg, .css, .js...)
         │
         ├── 4. Async Fetch Loop (asyncio.Semaphore(20) concurrent)
         │       ├── 0.3s polite delay per request
         │       ├── robots.txt compliance (RobotFileParser per domain)
         │       ├── 1h crawl budget guard
         │       └── asyncio.gather() — batch of 20 URLs processed in parallel
         │
         ├── 5. WebScraper.scrape() per URL
         │       ├── Shopify product? → _try_shopify_json() [highest priority]
         │       ├── Static fetch → aiohttp with ETag/Last-Modified conditional requests
         │       ├── Platform detection → quality scoring
         │       └── JS-heavy + low quality? → BrowserPool.render() [Playwright]
         │
         ├── 6. UniversalExtractor.extract() — 5-pass pipeline
         │       ├── Pass 1: JSON-LD / Schema.org structured data
         │       ├── Pass 2: Platform-specific HTML (Shopify, WooCommerce, WordPress...)
         │       ├── Pass 3: trafilatura (article/blog extraction)
         │       ├── Pass 4: readability fallback
         │       └── Pass 5: Text density scoring (generic fallback)
         │
         ├── 7. ExtractionValidator.validate() — quality scoring
         │       ├── Structured data platforms → quality = 0.9 (skip DOM checks)
         │       ├── JSON-LD extracted → quality = 0.85
         │       └── Generic → check missing DOM signals, FAQ, tables
         │
         ├── 8. ContentCleaner.clean() — normalize for embedding
         │       ├── Remove emails, cookie banners, nav noise
         │       ├── Deduplicate lines
         │       └── Preserve tables (|), FAQ pairs (Q:/A:), price lines, unicode
         │
         ├── 9. PageHasher.is_unchanged() — skip re-ingestion
         │       └── SHA-256 hash comparison (in-memory dict)
         │
         ├── 10. RawHTMLStorage.store() → AWS S3
         │        └── gzip-compressed JSON: {url, html, headers, status, timestamp}
         │            Key: crawler/raw/{org_id}/{date}/{job_id}/{url_hash}.json.gz
         │
         ├── 11. DocumentIngestion.ingest() → RAG Pipeline
         │        ├── SemanticChunker.chunk() — split by headings/FAQ/tables/specs
         │        ├── EmbeddingService.embed_batch() — sentence-transformers/all-mpnet-base-v2
         │        └── VectorStore.upsert() → pgvector (document_chunks table)
         │
         ├── 12. Link Discovery → push new URLs to frontier
         │        └── urljoin() + domain filter + frontier.push_sync()
         │
         ├── 13. DB Persistence per page
         │        ├── CrawledPage record (url, status, quality, s3_key, chunks_created)
         │        └── CrawlError record on failure (with rollback safety)
         │
         └── 14. CrawlMetric recorded at job completion
                  └── pages/min, avg fetch time, extraction quality, success rate
```

---

## Component Details

### 1. Entry Points

**API** — `POST /api/v1/knowledge/crawl`
- Tries Celery worker first (checks active workers via inspector)
- Falls back to synchronous execution if no worker running
- Returns `task_id` for async tracking or immediate result for sync

**Celery Tasks** — `app/workers/crawler_tasks.py`
- `crawl_website(url, org_id, max_pages, max_depth, max_js_renders)` — primary task, queue: `crawler`, max_retries: 2, retry delay: 60s
- `crawl_sitemap(url, org_id)` — discovers sitemap URLs and enqueues individual page tasks
- `recrawl_scheduled(org_id)` — hourly beat task, re-crawls jobs past `next_crawl_at`

---

### 2. URL Discovery — `app/crawler/sitemap_parser.py` + engine

**SitemapParser**
- Tries 4 sitemap candidates: `/sitemap.xml`, `/sitemap_index.xml`, `/wp-sitemap.xml`, `/sitemap_index.xsl`
- Recursively resolves sitemap indexes (depth ≤ 2)
- Returns up to 1000 URLs
- Uses `httpx.AsyncClient` with 10s timeout

**Shopify Product Discovery** — `engine._discover_shopify_products()`
- Paginates through `/products.json?limit=250&page=N`
- Extracts product handles → builds `/products/{handle}` URLs
- Safety cap: 20 pages = 5000 products max
- Runs after sitemap seeding — fills the gap when sitemaps only list blog/policy pages

---

### 3. URL Frontier — `app/crawler/url_frontier.py`

**Storage**: Redis Sorted Set (`crawler:frontier:{job_id}`)
**Deduplication**: Redis Set of MD5 hashes (`crawler:seen:{job_id}`)

**URL Normalization** (canonical form):
- Lowercase scheme + host
- Strip trailing slash
- Remove tracking parameters: `utm_*`, `fbclid`, `gclid`, `sort`, `filter`, `session`, `replytocom`, `ref`, `_ga`, `mc_cid`, `mc_eid`
- Remove URL fragment

**Priority Scoring** (lower = crawled first):
| Priority | URL patterns |
|----------|-------------|
| 0 | /product/, /products/, /service/, /pricing, /docs/ |
| 5 | /faq, /policy, /about, /contact |
| 10 | /blog/, /article/, /news/, /post/ |
| 15 | /collection/, /collections/, /category/ |
| 25 | everything else |

**Skip Patterns** (never crawled):
- `/cart`, `/checkout`, `/account`, `/login`, `/register`, `/wishlist`, `/compare`
- `/cdn/`, `/wp-admin`, `/wp-login`, `/feed/`, `/search`, `/order/`, `/user/`
- File extensions: `.xml`, `.pdf`, `.zip`, `.txt`, `.md`, `.jpg`, `.jpeg`, `.png`, `.gif`, `.svg`, `.css`, `.js`, `.ico`, `.woff`, `.woff2`, `.ttf`, `.mp4`, `.mp3`

**Sync vs Async**: Both interfaces provided — sync for Celery workers, async for FastAPI context.

---

### 4. Async Fetch Engine — `app/crawler/scraper.py`

**WebScraper**
- `aiohttp.ClientSession` with `TCPConnector(limit=50, ttl_dns_cache=300, keepalive_timeout=30)`
- `asyncio.Semaphore(50)` — max 50 concurrent fetches
- `Accept-Encoding: gzip, deflate` — brotli excluded (not installed)
- Brotli error fallback: retries with `Accept-Encoding: identity`

**Conditional HTTP Requests** (incremental crawling):
- Stores `ETag` and `Last-Modified` per URL in memory
- Sends `If-None-Match` and `If-Modified-Since` on subsequent requests
- HTTP 304 → returns `None` (page unchanged, skip re-ingestion)

**Shopify Product Path** (highest priority):
1. Detects `/products/{slug}` URL pattern
2. Fetches `{base}/products/{slug}.json` → structured product data
3. Fetches HTML page → extracts links for discovery + metafields
4. Builds rich content: title, price range, availability, options, SKU, brand, tags, variants, description, materials/wash/shipping metafields
5. Returns `extraction_quality: 0.95`

**Hybrid Rendering Decision**:
```
Shopify/WooCommerce platform detected?
  YES → quality = 0.9, skip browser entirely
  NO  → validate extraction quality
        quality < 0.5 AND JS markers present?
          YES → BrowserPool.render() [Playwright]
          NO  → use static result
```

**JS Markers** that justify browser rendering:
`__next_f`, `data-reactroot`, `ng-version`, `v-app`, `__nuxt`, `ember-application`

---

### 5. Browser Pool — `app/crawler/scraper.py` (BrowserPool)

- 3 persistent Chromium instances (never launched per-request)
- `asyncio.Semaphore(3)` — max 3 concurrent renders
- `_initialized = True` set before try block — never retries on failure
- `_available = False` if init fails (Windows SelectorEventLoop, missing Playwright)
- Per-domain failure tracking — disables browser for domains that fail once
- Windows fix: `asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())` at module load
- Launch args: `--no-sandbox --disable-dev-shm-usage --disable-gpu --disable-extensions`
- Wait condition: `networkidle`, timeout: 25s

---

### 6. Universal Extractor — `app/crawler/universal_extractor.py`

**Platform Detection** (checked in order):
- Shopify: `Shopify.theme` or `/cdn/shop/` in HTML
- WooCommerce: `woocommerce` in HTML or `wp-content/plugins/woocommerce`
- WordPress: `wp-content` or `wp-includes`
- Next.js: `__next_f` or `_next/static`
- Magento: `Magento` or `mage/cookies`
- GitBook: `gitbook` in HTML or URL
- Zendesk: `zendesk` in HTML or URL
- Discourse: `discourse` in HTML or `discourse-cdn`

**5-Pass Extraction Pipeline**:

**Pass 1 — JSON-LD / Schema.org** (highest quality)
- Parses all `<script type="application/ld+json">` blocks
- Priority order: Product → Article → BlogPosting → NewsArticle → FAQPage → LocalBusiness → Restaurant → Event → Organization → WebPage
- Handles `@graph` arrays and nested schemas
- Normalizes to structured text: `Product: X\nPrice: Y\nAvailability: Z\nDescription: ...`
- Augments with semantic DOM content (tables, accordions)

**Pass 2 — Platform-Specific HTML**
- WooCommerce: `.price` span → bdi tags for price, `.woocommerce-tabs` for description, attribute tables
- WordPress: `.entry-content`, `.post-content`, `article`, `main .content`
- Shopify HTML: `<article>` or `.article` divs (for blog pages)
- Magento: `.product-info-main`, `.product.attribute.description`
- GitBook/Zendesk/Discourse: `article`, `main`, `.markdown-body`, `.article-body`
- Next.js: `<main>` or `#__next`
- Generic: OpenGraph product tags → text density scoring

**Pass 3 — trafilatura**
- `include_tables=True, favor_recall=True`
- Used for article/blog content extraction
- Requires `trafilatura` package

**Pass 4 — readability**
- Mozilla Readability algorithm
- Fallback for long-form articles
- Requires `readability-lxml` package

**Pass 5 — Text Density Scoring**
- Removes script/style/nav/footer/header/aside/form/iframe
- Tries `<main>`, `<article>`, `<section>` first
- Falls back to div scoring: `score = len(text) × (1 - link_density)`

**Semantic DOM Extraction** (runs after Pass 1 and 2):
- Tables → pipe-delimited rows: `Header1 | Header2 | Header3`
- `<details>/<summary>` accordions → `Q: label\nA: body`
- FAQ divs (class contains `faq|accordion|collapse`) → `Q:/A:` pairs
- Tab panels (`role="tabpanel"`) → kept even if hidden

---

### 7. Extraction Validator — `app/crawler/extraction_validator.py`

**Quality Score** (0.0 to 1.0):
| Condition | Score |
|-----------|-------|
| Shopify / WooCommerce platform | 0.9 (skip all DOM checks) |
| JSON-LD product/article/faq extracted | 0.85 |
| Content < 150 chars | 0.1 |
| Missing 2+ product DOM signals | -0.30 |
| Missing FAQ/accordion content | -0.15 |
| Missing table content | -0.10 |

**Browser Render Trigger**: `score < 0.5 AND JS framework markers present`
- Both conditions required — prevents over-triggering on Shopify pages

---

### 8. Content Cleaner — `app/crawler/content_cleaner.py`

**Removes**:
- Email addresses
- Cookie banners, privacy policy noise
- Copyright notices, "Powered by X"
- Navigation noise: home, menu, skip to, back to top, read more, subscribe, follow us
- Duplicate lines (case-insensitive deduplication)

**Preserves**:
- Pipe-delimited table rows (`|`)
- FAQ pairs (`Q:`, `A:`)
- Price lines (৳, $, £, €, ¥, ₹)
- Lines > 10 characters
- Short uppercase headings (< 40 chars)
- Unicode: Bengali (৳, \u0980-\u09FF), Arabic (\u0600-\u06FF), CJK (\u4e00-\u9fff)
- Currency symbols: ৳ £ € ¥ $ ₹

---

### 9. Page Hasher — `app/crawler/page_hashing.py`

- SHA-256 hash of raw HTML content
- In-memory dict: `{url: hash}`
- `is_unchanged(url, content)` → True if hash matches → skip re-ingestion
- `store(url, content)` → update hash after successful ingestion
- `clear_org(org_id)` → force full re-crawl on next run
- Note: resets on server restart (Redis persistence recommended for production)

---

### 10. Raw HTML Storage — `app/crawler/raw_html_storage.py`

**Purpose**: Store every fetched page for debugging, reprocessing, and pipeline replay

**Storage**: AWS S3 (or MinIO)
**Format**: gzip-compressed JSON
**Key pattern**: `crawler/raw/{org_id}/{YYYY/MM/DD}/{job_id}/{url_md5}.json.gz`
**Compression**: gzip level 6 (~70-80% size reduction)

**Stored fields**:
```json
{
  "url": "https://example.com/products/item",
  "status_code": 200,
  "headers": {"Content-Type": "text/html", "ETag": "..."},
  "html": "<html>...</html>",
  "fetched_at": "2026-05-18T07:25:12.123456"
}
```

---

### 11. Semantic Chunker — `app/rag/chunker.py`

**Strategy**: Semantic splitting, not character-count splitting

**Atomic Page Detection** (never split):
- Pages with ≥ 2 occurrences of "opening hours" or "google map"
- Pages with ≥ 2 occurrences of "shop no" or ≥ 3 occurrences of "floor"
- Store location pages kept as single chunk (up to 8000 chars)

**Splitting Rules** (in order):
1. Headings (`# H1`, `## H2`, `ALL CAPS HEADING:`) → new section
2. Section breaks (`---`, `===`) → new section
3. FAQ Q+A pairs → kept together as one chunk
4. Table rows → kept together as one chunk
5. Oversized sections → sentence-boundary split with 200-char overlap

**Chunk Merging**: Consecutive tiny chunks merged until `chunk_size / 2` reached

**Chunk Type Metadata** (stored per chunk):
- `faq` — contains Q:/A: pairs
- `table` — contains pipe-delimited rows
- `product_spec` — contains Price:/SKU:/Brand:/Availability:
- `documentation` — contains markdown headings
- `text` — general content

**Chunk Size**: 4000 chars (from `MAX_CHUNK_SIZE`), overlap: 200 chars

---

### 12. RAG Ingestion Pipeline — `app/rag/ingestion.py`

```
clean_text
    → SemanticChunker.chunk_with_metadata()
    → EmbeddingService.embed_batch()  [sentence-transformers/all-mpnet-base-v2, dim=768]
    → VectorStore.upsert()  [pgvector, document_chunks table]
```

**Metadata stored per chunk**:
```json
{
  "title": "Wave Riders Woven Swim Shorts",
  "url": "https://turaag.com/products/wave-riders-swim-shorts",
  "type": "product",
  "platform": "shopify",
  "crawl_depth": 0,
  "job_id": "uuid",
  "chunk_index": 0,
  "total_chunks": 2,
  "chunk_type": "product_spec"
}
```

---

### 13. Database Models — `app/models/crawl_job.py`

**crawl_jobs** — one row per crawl job
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| organization_id | String | Multi-tenant isolation |
| start_url | Text | Root URL crawled |
| status | String | pending/queued/crawling/extracting/embedding/completed/failed/cancelled |
| max_pages | Integer | Crawl budget (pages) |
| max_depth | Integer | Link discovery depth limit |
| max_js_renders | Integer | Browser render budget |
| pages_ingested | Integer | Successfully ingested |
| pages_skipped | Integer | Unchanged or too short |
| pages_failed | Integer | Error count |
| next_crawl_at | DateTime | Scheduled re-crawl time |
| result_summary | JSON | Full result dict |

**crawled_pages** — one row per successfully crawled URL
| Column | Type | Description |
|--------|------|-------------|
| job_id | UUID FK | Parent job |
| url | Text | Page URL |
| content_hash | String(64) | SHA-256 for change detection |
| etag | String | HTTP ETag for conditional requests |
| last_modified | String | HTTP Last-Modified |
| extraction_quality | Float | 0.0-1.0 quality score |
| used_browser | Boolean | Whether Playwright was used |
| s3_raw_key | Text | S3 path to raw HTML |
| chunks_created | Integer | RAG chunks created |

**crawl_errors** — one row per failed URL
**crawl_metrics** — aggregated stats per job (pages/min, avg fetch time, quality, success rate)

---

### 14. Celery Worker Architecture

**Queues** (independently scalable):
| Queue | Tasks |
|-------|-------|
| `crawler` | crawl_website, crawl_sitemap, recrawl_scheduled |
| `crawler_fetch` | (reserved for future fetch workers) |
| `crawler_extract` | (reserved for future extraction workers) |
| `crawler_embed` | (reserved for future embedding workers) |

**Beat Schedule**:
- `crawler-recrawl-check` — every hour, checks `next_crawl_at` for due jobs

**Task Config**:
- `max_retries: 2`, retry delay: 60s
- `task_time_limit: 30min`, soft limit: 25min
- `worker_prefetch_multiplier: 4`

---

## Shopify-Specific Extraction Flow

Shopify stores get special treatment because their sitemaps are incomplete:

```
1. SitemapParser → finds 13 blog/policy URLs (typical Shopify sitemap)
2. _discover_shopify_products() → /products.json?limit=250&page=1,2,3...
   → discovers ALL product handles (e.g. 600+ products)
3. For each /products/{handle} URL:
   a. Fetch /products/{handle}.json → structured product data
      - title, vendor, product_type, tags
      - variants: price, availability, SKU per size/color
      - options: Size values, Color values
      - body_html: description
   b. Fetch /products/{handle} HTML → extract links + metafields
      - CSS selectors: [data-tab], .product__accordion, [class*='metafield']
      - Fuzzy label scan: material|fabric|wash|care|shipping|return
   c. Build content string:
      Product: Wave Riders Woven Swim Shorts
      Price: 1390.00 BDT
      Availability: In Stock
      Color: Black
      Size: S, M, L, XL, XXL, XXXL
      Brand: Turaag Active
      Type: Swim Shorts
      SKU: TRGM032486
      Tags: mens, swim, summer
      
      Description:
      Dive into style and functionality...
      
      Variants:
        - Black / S: 1390.00 BDT, In Stock, SKU: TRGM032486-S
        - Black / M: 1390.00 BDT, In Stock, SKU: TRGM032486-M
        ...
      
      Materials:
      100% POLYESTER WOVEN
      
      Shipping:
      [shipping info from metafields]
```

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Concurrent fetches | 20 (semaphore) |
| Crawl delay | 0.3s per request |
| Crawl budget | 1 hour max |
| Pages/minute (observed) | 22.5 |
| Total pages (turaag.com) | 612 ingested, 9 skipped, 6 errors |
| Browser renders | 0 (all static on Shopify) |
| Embedding model | sentence-transformers/all-mpnet-base-v2 (768 dim) |
| Chunk size | 4000 chars with 200 char overlap |
| S3 compression | gzip level 6 (~75% reduction) |

---

## Incremental Re-Crawl Strategy

1. **ETag/Last-Modified**: HTTP conditional requests on every re-crawl
   - Server returns 304 → skip page entirely (no fetch, no ingest)
2. **Content Hash**: SHA-256 of raw HTML
   - Hash unchanged → skip re-ingestion even if 304 not supported
3. **Scheduled Re-Crawl**: `next_crawl_at = completed_at + 24h`
   - Celery beat checks hourly, enqueues due jobs
4. **Manual Re-Crawl**: Delete source via `DELETE /api/v1/knowledge/source?source={url}` then re-crawl

---

## Security & Compliance

- **robots.txt**: Fetched and cached per domain, checked before every URL fetch
- **User-Agent**: `Mozilla/5.0 (compatible; EnterpriseAIBot/2.0; +https://example.com/bot)`
- **Rate limiting**: 0.3s delay between requests per domain
- **Domain isolation**: Only crawls URLs matching the start URL's domain
- **Multi-tenant isolation**: All DB records scoped by `organization_id`
- **Crawl budget**: Max pages + 1h time limit prevents runaway crawls

---

## File Structure

```
app/crawler/
├── engine.py              # Main orchestrator — crawl loop, DB tracking, metrics
├── scraper.py             # aiohttp fetch engine + Playwright browser pool
├── universal_extractor.py # 5-pass extraction pipeline
├── url_frontier.py        # Redis sorted set priority queue
├── sitemap_parser.py      # XML sitemap discovery (recursive)
├── content_cleaner.py     # Text normalization for embedding
├── extraction_validator.py # Quality scoring, browser trigger logic
├── page_hashing.py        # SHA-256 change detection
├── raw_html_storage.py    # S3 gzip storage
├── product_detector.py    # Signal-based product/pricing page classifier
└── sync_manager.py        # Legacy job state (superseded by DB models)

app/rag/
├── chunker.py             # Semantic chunker (heading/FAQ/table aware)
├── ingestion.py           # Chunk → embed → upsert pipeline
├── embeddings.py          # Embedding service wrapper
├── retriever.py           # Vector search + keyword boost + source fetch
└── vector_store.py        # pgvector upsert/search

app/models/
└── crawl_job.py           # crawl_jobs, crawled_pages, crawl_errors, crawl_metrics

app/workers/
└── crawler_tasks.py       # Celery tasks: crawl_website, crawl_sitemap, recrawl_scheduled
```
