"""
Temporal Product Tracking — price history, stock history, promotion changes,
availability transitions, and timestamped snapshots.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Boolean, Text, Integer, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ProductSnapshot(Base):
    """
    Timestamped snapshot of a product entity state.
    One row per crawl per product URL.
    """
    __tablename__ = "product_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(String(255), nullable=False, index=True)
    url = Column(Text, nullable=False, index=True)
    canonical_url = Column(Text, nullable=True)
    handle = Column(String(255), nullable=True)
    crawl_job_id = Column(UUID(as_uuid=True), nullable=True)

    # Core fields at snapshot time
    title = Column(Text, nullable=True)
    price = Column(Float, nullable=True)
    compare_at_price = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    availability = Column(String(50), nullable=True)
    brand = Column(String(255), nullable=True)
    sku = Column(String(255), nullable=True)
    product_type = Column(String(255), nullable=True)

    # Attributes
    material = Column(Text, nullable=True)
    color = Column(Text, nullable=True)
    size_options = Column(Text, nullable=True)

    # Variant snapshot (full JSON)
    variants_json = Column(JSON, nullable=True)

    # Completeness
    completeness_score = Column(Float, nullable=True)
    extraction_sources = Column(JSON, nullable=True)

    # Change flags (set by comparison with previous snapshot)
    price_changed = Column(Boolean, default=False)
    availability_changed = Column(Boolean, default=False)
    variants_changed = Column(Boolean, default=False)
    is_promotion = Column(Boolean, default=False)   # compare_at_price > price

    snapshotted_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PriceHistory(Base):
    """
    Append-only price change log per product URL.
    One row per price change event.
    """
    __tablename__ = "product_price_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(String(255), nullable=False, index=True)
    url = Column(Text, nullable=False, index=True)
    sku = Column(String(255), nullable=True)

    old_price = Column(Float, nullable=True)
    new_price = Column(Float, nullable=False)
    currency = Column(String(10), nullable=True)
    compare_at_price = Column(Float, nullable=True)
    is_promotion = Column(Boolean, default=False)
    source = Column(String(50), nullable=True)      # shopify_json | graphql | etc.

    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StockHistory(Base):
    """
    Append-only stock/availability change log per product URL.
    """
    __tablename__ = "product_stock_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(String(255), nullable=False, index=True)
    url = Column(Text, nullable=False, index=True)
    sku = Column(String(255), nullable=True)
    variant_title = Column(String(255), nullable=True)

    old_availability = Column(String(50), nullable=True)
    new_availability = Column(String(50), nullable=False)
    old_stock_level = Column(Integer, nullable=True)
    new_stock_level = Column(Integer, nullable=True)
    source = Column(String(50), nullable=True)

    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Indexes for time-series queries
Index("ix_price_history_url_time", PriceHistory.url, PriceHistory.changed_at)
Index("ix_stock_history_url_time", StockHistory.url, StockHistory.changed_at)
Index("ix_snapshots_url_time", ProductSnapshot.url, ProductSnapshot.snapshotted_at)


# ── Temporal tracker service ──────────────────────────────────────────────────

class ProductTemporalTracker:
    """
    Compare a new ProductEntity snapshot against the previous one
    and persist change events.
    """

    def track(
        self,
        entity,           # ProductEntity
        organization_id: str,
        crawl_job_id: str,
        db,
    ) -> ProductSnapshot:
        """
        Create a snapshot and detect changes vs previous snapshot.
        Returns the new ProductSnapshot.
        """
        from app.crawler.completeness_engine import CompletenessScore

        def v(fv, default=None):
            return fv.value if fv else default

        score = CompletenessScore(entity)

        # Load previous snapshot
        prev = self._load_previous(entity.url, organization_id, db)

        new_price = v(entity.price)
        new_avail = v(entity.availability, "")
        new_variants = [
            {"sku": var.sku, "title": var.title, "price": var.price,
             "available": var.available, "options": var.options}
            for var in entity.variants
        ]
        compare_at = v(entity.compare_at_price)
        is_promo = bool(compare_at and new_price and float(compare_at) > float(new_price))

        price_changed = prev is not None and prev.price != new_price and new_price is not None
        avail_changed = prev is not None and prev.availability != new_avail
        variants_changed = prev is not None and self._variants_changed(prev.variants_json, new_variants)

        snapshot = ProductSnapshot(
            organization_id=organization_id,
            url=entity.url,
            canonical_url=entity.url,
            handle=v(entity.handle, ""),
            crawl_job_id=crawl_job_id or None,
            title=v(entity.title, ""),
            price=float(new_price) if new_price else None,
            compare_at_price=float(compare_at) if compare_at else None,
            currency=v(entity.currency, ""),
            availability=new_avail,
            brand=v(entity.brand, ""),
            sku=v(entity.sku, ""),
            product_type=v(entity.product_type, ""),
            material=v(entity.material, ""),
            color=v(entity.color, ""),
            size_options=v(entity.size_options, ""),
            variants_json=new_variants,
            completeness_score=round(score.total, 3),
            extraction_sources=entity.sources_used,
            price_changed=price_changed,
            availability_changed=avail_changed,
            variants_changed=variants_changed,
            is_promotion=is_promo,
        )
        db.add(snapshot)

        # Persist price change event
        if price_changed:
            db.add(PriceHistory(
                organization_id=organization_id,
                url=entity.url,
                sku=v(entity.sku, ""),
                old_price=prev.price,
                new_price=float(new_price),
                currency=v(entity.currency, ""),
                compare_at_price=float(compare_at) if compare_at else None,
                is_promotion=is_promo,
                source=entity.sources_used[0] if entity.sources_used else "",
            ))

        # Persist availability change events (per variant)
        if avail_changed or variants_changed:
            for var in entity.variants:
                prev_var = self._find_prev_variant(prev, var.sku) if prev else None
                prev_avail = prev_var.get("availability", "") if prev_var else None
                new_var_avail = "In Stock" if var.available else "Out of Stock"
                if prev_avail != new_var_avail:
                    db.add(StockHistory(
                        organization_id=organization_id,
                        url=entity.url,
                        sku=var.sku,
                        variant_title=var.title,
                        old_availability=prev_avail,
                        new_availability=new_var_avail,
                        source=var.source,
                    ))

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            from app.core.logging import get_logger
            get_logger(__name__).warning("temporal_track_commit_failed", url=entity.url, error=str(e))

        return snapshot

    def get_price_history(
        self, url: str, organization_id: str, db, limit: int = 50
    ):
        return (
            db.query(PriceHistory)
            .filter(PriceHistory.url == url, PriceHistory.organization_id == organization_id)
            .order_by(PriceHistory.changed_at.desc())
            .limit(limit)
            .all()
        )

    def get_stock_history(
        self, url: str, organization_id: str, db, sku: str = "", limit: int = 50
    ):
        q = (
            db.query(StockHistory)
            .filter(StockHistory.url == url, StockHistory.organization_id == organization_id)
        )
        if sku:
            q = q.filter(StockHistory.sku == sku)
        return q.order_by(StockHistory.changed_at.desc()).limit(limit).all()

    def _load_previous(self, url: str, org_id: str, db) -> ProductSnapshot | None:
        return (
            db.query(ProductSnapshot)
            .filter(ProductSnapshot.url == url, ProductSnapshot.organization_id == org_id)
            .order_by(ProductSnapshot.snapshotted_at.desc())
            .first()
        )

    def _variants_changed(self, prev_variants, new_variants) -> bool:
        if not prev_variants and not new_variants:
            return False
        if not prev_variants or not new_variants:
            return True
        prev_skus = {v.get("sku") for v in prev_variants if v.get("sku")}
        new_skus = {v.get("sku") for v in new_variants if v.get("sku")}
        if prev_skus != new_skus:
            return True
        prev_avail = {v.get("sku"): v.get("available") for v in prev_variants}
        new_avail = {v.get("sku"): v.get("available") for v in new_variants}
        return prev_avail != new_avail

    def _find_prev_variant(self, prev: ProductSnapshot, sku: str):
        if not prev or not prev.variants_json:
            return None
        for v in prev.variants_json:
            if v.get("sku") == sku:
                return v
        return None


product_temporal_tracker = ProductTemporalTracker()
