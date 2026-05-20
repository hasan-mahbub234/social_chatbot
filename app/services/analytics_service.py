"""Analytics service — aggregate usage and cost metrics."""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.usage import UsageLog, CostTracking
from app.core.logging import get_logger
from datetime import datetime, timedelta

logger = get_logger(__name__)


class AnalyticsService:
    """Aggregate and report usage analytics."""

    def get_org_usage(
        self,
        organization_id: str,
        db: Session,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get organization usage summary for last N days."""
        since = datetime.utcnow() - timedelta(days=days)

        result = db.query(
            func.sum(UsageLog.tokens_used).label("total_tokens"),
            func.sum(UsageLog.cost).label("total_cost"),
            func.count(UsageLog.id).label("total_requests"),
        ).filter(
            UsageLog.created_at >= since,
        ).first()

        return {
            "organization_id": organization_id,
            "period_days": days,
            "total_tokens": int(result.total_tokens or 0),
            "total_cost": float(result.total_cost or 0),
            "total_requests": int(result.total_requests or 0),
        }

    def get_agent_usage(self, agent_id: str, db: Session, days: int = 7) -> Dict[str, Any]:
        """Get per-agent usage summary."""
        since = datetime.utcnow() - timedelta(days=days)
        result = db.query(
            func.sum(UsageLog.tokens_used).label("tokens"),
            func.sum(UsageLog.cost).label("cost"),
            func.count(UsageLog.id).label("requests"),
        ).filter(
            UsageLog.agent_id == agent_id,
            UsageLog.created_at >= since,
        ).first()

        return {
            "agent_id": agent_id,
            "period_days": days,
            "total_tokens": int(result.tokens or 0),
            "total_cost": float(result.cost or 0),
            "total_requests": int(result.requests or 0),
        }


analytics_service = AnalyticsService()
