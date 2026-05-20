"""Crawler engine — distributed async crawl pipeline with concurrency, budget, and DB tracking."""
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from sqlalchemy import text
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_PAGES_DEFAULT = 100
FETCH_CONCURRENCY = 20       # concurrent fetches per crawl job
CRAWL_DELAY_SECONDS = 0.3    # polite delay between requests per domain


class CrawlerEngine:
    """Orchestrate distributed website crawling with DB job tracking and RAG ingestion."""

    def __init__(self):
        self._robot_parsers: Dict[str, RobotFileParser] = {}

    async def crawl(
        self,
        start_url: str,
        organization_id: str,
        db,
        job_id: str = None,
        max_pages: int = MAX_PAGES_DEFAULT,
        max_depth: int = 5,
        max_js_renders: int = 20,
        respect_robots: bool = True,
        recrawl_interval_hours: int = 24,
    ) -> Dict[str, Any]:
        """Full crawl pipeline: discover → fetch → extract → validate → ingest."""
        import uuid as _uuid
        if job_id is None:
            job_id = str(_uuid.uuid4())

        # Ensure a CrawlJob row exists (may already exist when called from Celery task)
        from app.models.crawl_job import CrawlJob as CrawlJobModel, CrawledPage, CrawlError, CrawlMetric

        # Auto-migrate V2 columns if not yet applied (safe no-op if already present)
        self._ensure_v2_columns(db)

        existing = db.query(CrawlJobModel).filter(CrawlJobModel.id == job_id).first()
        if not existing:
            job_row = CrawlJobModel(
                id=job_id,
                organization_id=organization_id,
                start_url=start_url,
                status="crawling",
                max_pages=max_pages,
                max_depth=max_depth,
                max_js_renders=max_js_renders,
                respect_robots=respect_robots,
                started_at=datetime.utcnow(),
            )
            db.add(job_row)
            db.commit()

        from app.crawler.scraper import web_scraper
        from app.crawler.content_cleaner import content_cleaner
        from app.crawler.page_hashing import page_hasher
        from app.crawler.url_frontier import url_frontier, SKIP_URL_PATTERNS
        from app.crawler.raw_html_storage import raw_html_storage
        from app.crawler.extraction_validator import extraction_validator
        from app.rag.ingestion import document_ingestion
        from app.core.redis_client import sync_redis_client

        domain = urlparse(start_url).netloc
        rp = await self._get_robot_parser(start_url) if respect_robots else None

        # Seed frontier from sitemap
        from app.crawler.sitemap_parser import sitemap_parser
        sitemap_urls = await sitemap_parser.get_urls(start_url)
        seed_urls = sitemap_urls if sitemap_urls else [start_url]
        # Filter to same domain
        seed_urls = [u for u in seed_urls if urlparse(u).netloc == domain]
        if not seed_urls:
            seed_urls = [start_url]

        url_frontier.push_sync(sync_redis_client, job_id, seed_urls, domain)

        # For Shopify stores: also seed all products via /products.json API
        # (sitemap often only has 13 blog/policy pages, missing all products)
        shopify_product_urls = await self._discover_shopify_products(start_url, domain)
        if shopify_product_urls:
            url_frontier.push_sync(sync_redis_client, job_id, shopify_product_urls, domain)
            logger.info("shopify_products_seeded", job_id=job_id, count=len(shopify_product_urls))

        total_seeded = url_frontier.size_sync(sync_redis_client, job_id)
        logger.info("frontier_seeded", job_id=job_id, count=total_seeded)

        semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
        ingested = skipped = errors = js_renders = 0
        fetch_times: List[float] = []
        qualities: List[float] = []
        start_time = time.monotonic()

        async def process_url(url: str, depth: int):
            nonlocal ingested, skipped, errors, js_renders

            if rp and not rp.can_fetch("*", url):
                return

            async with semaphore:
                await asyncio.sleep(CRAWL_DELAY_SECONDS)
                t0 = time.monotonic()
                try:
                    use_browser = js_renders < max_js_renders
                    page = await web_scraper.scrape(url, use_browser_if_needed=use_browser)
                    fetch_ms = (time.monotonic() - t0) * 1000
                    fetch_times.append(fetch_ms)

                    if page is None:
                        skipped += 1
                        logger.info("page_skipped", url=url, reason="fetch_failed")
                        return

                    if page.get("used_browser"):
                        js_renders += 1

                    raw_html = page.pop("raw_html", "")
                    resp_headers = page.get("response_headers", {})
                    url_hash = page.get("url_hash", "")

                    # Skip unchanged pages
                    if page_hasher.is_unchanged(url, raw_html):
                        skipped += 1
                        logger.info("page_skipped", url=url, reason="unchanged")
                        return

                    # Store raw HTML to S3
                    s3_key = await raw_html_storage.store(
                        organization_id=organization_id,
                        job_id=job_id,
                        url=url,
                        html=raw_html,
                        status_code=page.get("status_code", 200),
                        headers=resp_headers,
                        url_hash=url_hash,
                    )

                    clean_text = content_cleaner.clean(page.get("content", ""))
                    if not clean_text or len(clean_text) < 30:
                        skipped += 1
                        logger.info("page_skipped", url=url, reason="no_content",
                                    content_len=len(clean_text) if clean_text else 0)
                        return

                    title = page.get("title", "")
                    content_type = page.get("content_type", "page")
                    platform = page.get("platform", "generic")
                    quality = page.get("extraction_quality", 0.5)
                    qualities.append(quality)

                    indexed_text = f"{title}\nURL: {url}\n{clean_text}" if title else f"URL: {url}\n{clean_text}"
                    ingest_result = await document_ingestion.ingest(
                        content=indexed_text,
                        organization_id=organization_id,
                        db=db,
                        source=url,
                        metadata={
                            "title": title, "url": url,
                            "type": content_type, "platform": platform,
                            "crawl_depth": depth, "job_id": job_id,
                        },
                    )

                    # Persist crawled page record
                    try:
                        crawled_page = CrawledPage(
                            job_id=job_id,
                            organization_id=organization_id,
                            url=str(url),
                            status_code=page.get("status_code"),
                            content_type=content_type,
                            platform=platform,
                            page_type=content_type,
                            title=title,
                            content_hash=page_hasher.hash(raw_html),
                            etag=resp_headers.get("ETag", ""),
                            last_modified=resp_headers.get("Last-Modified", ""),
                            extraction_quality=quality,
                            used_browser=page.get("used_browser", False),
                            s3_raw_key=s3_key,
                            crawl_depth=depth,
                            chunks_created=ingest_result.get("chunks_created", 0),
                            completeness_score=page.get("completeness_score"),
                            extraction_sources=page.get("extraction_sources", []),
                        )
                        db.add(crawled_page)
                        db.commit()
                    except Exception as db_err:
                        logger.warning("crawled_page_log_failed", url=url, error=str(db_err))
                        db.rollback()

                    page_hasher.store(url, raw_html)
                    ingested += 1
                    logger.info("page_ingested", url=url, quality=quality, chunks=ingest_result.get("chunks_created"))

                    # Temporal tracking + observability (product pages only)
                    if content_type == "product":
                        try:
                            from app.crawler.entity_model import ProductEntity
                            from app.crawler.completeness_engine import CompletenessScore
                            from app.models.product_history import product_temporal_tracker
                            from app.observability.crawler_observability import crawler_observability
                            from app.crawler.entity_graph import entity_graph

                            # Reconstruct entity from page for tracking
                            _entity = ProductEntity(url=url, organization_id=organization_id)
                            _entity.merge(platform, {
                                "title": title,
                                "availability": "In Stock",
                            })
                            _score = CompletenessScore(_entity)

                            # Temporal snapshot
                            product_temporal_tracker.track(
                                entity=_entity,
                                organization_id=organization_id,
                                crawl_job_id=job_id,
                                db=db,
                            )

                            # Observability metrics
                            crawler_observability.record_extraction(
                                org_id=organization_id,
                                url=url,
                                completeness_score=page.get("completeness_score", _score.total),
                                sources_used=page.get("extraction_sources", [platform]),
                                missing_fields=_score.missing_fields,
                                extraction_quality=quality,
                                used_browser=page.get("used_browser", False),
                                used_llm="llm" in page.get("extraction_sources", []),
                                latency_ms=page.get("fetch_time_ms", 0),
                            )

                            # Register in entity graph
                            entity_graph.register_product(
                                org_id=organization_id,
                                url=url,
                                title=title,
                                metadata={"platform": platform, "job_id": job_id},
                            )
                        except Exception as obs_err:
                            logger.debug("observability_failed", url=url, error=str(obs_err))

                    # Discover links and push to frontier
                    if depth < max_depth:
                        links = [urljoin(url, l) for l in page.get("links", [])]
                        url_frontier.push_sync(sync_redis_client, job_id, links, domain)

                except Exception as e:
                    errors += 1
                    logger.error("page_failed", url=url, error=str(e))
                    try:
                        db.rollback()
                        err = CrawlError(
                            job_id=job_id,
                            organization_id=organization_id,
                            url=str(url),
                            error_type=type(e).__name__,
                            error_message=str(e)[:500],
                        )
                        db.add(err)
                        db.commit()
                    except Exception as db_err:
                        logger.warning("crawl_error_log_failed", url=url, error=str(db_err))
                        db.rollback()

        # Main crawl loop — batch pop from frontier
        depth = 0
        while True:
            if ingested + skipped + errors >= max_pages:
                break
            if time.monotonic() - start_time > 3600:  # 1h budget
                logger.warning("crawl_budget_exceeded", job_id=job_id)
                break

            batch = url_frontier.pop_batch_sync(sync_redis_client, job_id, batch_size=FETCH_CONCURRENCY)
            if not batch:
                break

            await asyncio.gather(*[process_url(url, depth) for url in batch])
            depth += 1

        # Record metrics
        elapsed = time.monotonic() - start_time
        ppm = (ingested / elapsed * 60) if elapsed > 0 else 0
        metric = CrawlMetric(
            job_id=job_id,
            organization_id=organization_id,
            pages_per_minute=round(ppm, 2),
            avg_fetch_time_ms=round(sum(fetch_times) / len(fetch_times), 2) if fetch_times else 0,
            avg_extraction_quality=round(sum(qualities) / len(qualities), 3) if qualities else 0,
            browser_render_count=js_renders,
            success_rate=round(ingested / max(ingested + errors, 1), 3),
        )
        db.add(metric)
        db.commit()

        # Cleanup frontier
        url_frontier.cleanup_sync(sync_redis_client, job_id)

        result = {
            "start_url": start_url,
            "pages_ingested": ingested,
            "pages_skipped": skipped,
            "errors": errors,
            "js_renders": js_renders,
            "elapsed_seconds": round(elapsed, 1),
            "pages_per_minute": round(ppm, 2),
        }
        logger.info("crawl_complete", job_id=job_id, **result)
        return result

    async def _discover_shopify_products(self, start_url: str, domain: str) -> List[str]:
        """Fetch all product URLs from Shopify /products.json (paginated)."""
        import httpx
        from urllib.parse import urlparse
        parsed = urlparse(start_url)
        base = f"{parsed.scheme}://{domain}"
        urls = []
        page = 1
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                while True:
                    resp = await client.get(f"{base}/products.json", params={"limit": 250, "page": page})
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    products = data.get("products", [])
                    if not products:
                        break
                    for p in products:
                        handle = p.get("handle", "")
                        if handle:
                            urls.append(f"{base}/products/{handle}")
                    if len(products) < 250:
                        break  # last page
                    page += 1
                    if page > 20:  # safety cap: 5000 products max
                        break
        except Exception as e:
            logger.debug("shopify_products_json_failed", domain=domain, error=str(e))
        return urls

    async def _get_robot_parser(self, start_url: str) -> Optional[RobotFileParser]:
        domain = urlparse(start_url).netloc
        if domain in self._robot_parsers:
            return self._robot_parsers[domain]
        rp = RobotFileParser()
        parsed = urlparse(start_url)
        rp.set_url(f"{parsed.scheme}://{domain}/robots.txt")
        try:
            await asyncio.wait_for(asyncio.to_thread(rp.read), timeout=8.0)
            self._robot_parsers[domain] = rp
            return rp
        except Exception as e:
            logger.warning("robots_txt_fetch_failed", domain=domain, error=str(e))
            # Cache a permissive parser so we don't retry on every page
            self._robot_parsers[domain] = None
            return None

    def _ensure_v2_columns(self, db) -> None:
        """
        Idempotently repair schema and add V2 columns.
        Safe to call on every crawl start.
        """
        # Step 1: ensure uuid-ossp extension exists
        try:
            db.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
            db.commit()
        except Exception:
            db.rollback()

        # Step 2: if document_chunks.id is integer/serial (old schema), drop and recreate
        try:
            result = db.execute(text("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'document_chunks' AND column_name = 'id'
            """)).fetchone()
            if result and result[0] in ('integer', 'bigint'):
                db.execute(text("DROP TABLE IF EXISTS document_chunks CASCADE"))
                db.commit()
                logger.info("document_chunks_dropped_old_schema")
        except Exception:
            db.rollback()

        # Step 3: create document_chunks with correct schema if missing
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    organization_id VARCHAR(255) NOT NULL,
                    content         TEXT NOT NULL,
                    embedding       vector(768),
                    source          TEXT,
                    chunk_index     INTEGER DEFAULT 0,
                    metadata        JSONB DEFAULT '{}',
                    created_at      TIMESTAMP DEFAULT NOW()
                )
            """))
            db.commit()
        except Exception:
            db.rollback()

        # Step 4: fix embedding dimension 384 → 768 if needed
        try:
            db.execute(text(
                "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(768)"
            ))
            db.commit()
        except Exception:
            db.rollback()

        # Step 5: ensure indexes
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS document_chunks_org_idx ON document_chunks (organization_id)",
        ]:
            try:
                db.execute(text(idx_sql))
                db.commit()
            except Exception:
                db.rollback()

        # Step 6: V2 columns on crawled_pages
        v2_columns = [
            ("completeness_score", "FLOAT"),
            ("extraction_sources", "JSONB"),
        ]
        for col_name, col_type in v2_columns:
            try:
                db.execute(text(
                    f"ALTER TABLE crawled_pages ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                db.commit()
            except Exception:
                db.rollback()

        # Step 7: Phase 2 history tables
        phase2_tables = [
            """
            CREATE TABLE IF NOT EXISTS product_snapshots (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id VARCHAR(255) NOT NULL,
                url TEXT NOT NULL,
                canonical_url TEXT,
                handle VARCHAR(255),
                crawl_job_id UUID,
                title TEXT,
                price FLOAT,
                compare_at_price FLOAT,
                currency VARCHAR(10),
                availability VARCHAR(50),
                brand VARCHAR(255),
                sku VARCHAR(255),
                product_type VARCHAR(255),
                material TEXT,
                color TEXT,
                size_options TEXT,
                variants_json JSONB,
                completeness_score FLOAT,
                extraction_sources JSONB,
                price_changed BOOLEAN DEFAULT FALSE,
                availability_changed BOOLEAN DEFAULT FALSE,
                variants_changed BOOLEAN DEFAULT FALSE,
                is_promotion BOOLEAN DEFAULT FALSE,
                snapshotted_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS product_price_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id VARCHAR(255) NOT NULL,
                url TEXT NOT NULL,
                sku VARCHAR(255),
                old_price FLOAT,
                new_price FLOAT NOT NULL,
                currency VARCHAR(10),
                compare_at_price FLOAT,
                is_promotion BOOLEAN DEFAULT FALSE,
                source VARCHAR(50),
                changed_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS product_stock_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id VARCHAR(255) NOT NULL,
                url TEXT NOT NULL,
                sku VARCHAR(255),
                variant_title VARCHAR(255),
                old_availability VARCHAR(50),
                new_availability VARCHAR(50) NOT NULL,
                old_stock_level INTEGER,
                new_stock_level INTEGER,
                source VARCHAR(50),
                changed_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """,
        ]
        for ddl in phase2_tables:
            try:
                db.execute(text(ddl))
                db.commit()
            except Exception:
                db.rollback()


crawler_engine = CrawlerEngine()
