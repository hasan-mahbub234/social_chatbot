"""Admin API — superuser operations for platform management."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from app.core.database import get_db
from app.core.dependencies import get_current_superuser
from app.models.user import User
from app.models.organization import Organization
from app.models.subscription import Subscription, SubscriptionPlan
from app.models.usage_meter import UsageMeter
from app.feature_flags.service import feature_flag_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class FeatureFlagOverride(BaseModel):
    feature_key: str
    organization_id: str
    is_enabled: bool


class PlanAssign(BaseModel):
    organization_id: str
    plan_name: str


@router.get("/stats")
async def platform_stats(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """Get platform-wide statistics."""
    total_orgs = db.query(func.count(Organization.id)).scalar() or 0
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_subs = db.query(func.count(Subscription.id)).filter(
        Subscription.status.in_(["active", "trialing"])
    ).scalar() or 0

    return {
        "total_organizations": total_orgs,
        "total_users": total_users,
        "active_subscriptions": active_subs,
    }


@router.get("/organizations")
async def list_organizations(
    limit: int = 50,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """List all organizations."""
    orgs = db.query(Organization).order_by(Organization.created_at.desc()).limit(limit).all()
    return [
        {
            "id": str(o.id),
            "name": o.name,
            "is_active": o.is_active,
            "created_at": o.created_at.isoformat(),
        }
        for o in orgs
    ]


@router.post("/feature-flags/override")
async def set_feature_flag(
    data: FeatureFlagOverride,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """Set a feature flag override for an organization."""
    flag = feature_flag_service.set_override(
        feature_key=data.feature_key,
        organization_id=data.organization_id,
        is_enabled=data.is_enabled,
        db=db,
    )
    return {
        "feature_key": flag.key,
        "organization_id": str(flag.organization_id),
        "is_enabled": flag.is_enabled,
    }


@router.post("/plans/assign")
async def assign_plan(
    data: PlanAssign,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """Manually assign a plan to an organization."""
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == data.plan_name).first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan '{data.plan_name}' not found")

    sub = db.query(Subscription).filter(
        Subscription.organization_id == data.organization_id
    ).first()

    if sub:
        sub.plan_id = plan.id
        sub.status = "active"
    else:
        sub = Subscription(
            organization_id=data.organization_id,
            plan_id=plan.id,
            status="active",
        )
        db.add(sub)

    db.commit()
    return {"message": f"Plan '{data.plan_name}' assigned to org {data.organization_id}"}


@router.delete("/organizations/{org_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_organization(
    org_id: str,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """Deactivate an organization."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.is_active = False
    db.commit()


# ── Evaluation Endpoints ──────────────────────────────────────────────────────

class BenchmarkRequest(BaseModel):
    organization_id: str
    top_k: int = 5
    custom_queries: Optional[List[Dict[str, Any]]] = None


@router.post("/evals/retrieval-benchmark")
async def run_retrieval_benchmark(
    req: BenchmarkRequest,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """Run retrieval benchmark against gold queries. Returns pass/fail report."""
    from app.evals.retrieval_benchmark import retrieval_benchmark
    report = await retrieval_benchmark.run(
        organization_id=req.organization_id,
        db=db,
        top_k=req.top_k,
        custom_queries=req.custom_queries,
    )
    return {
        "passed": report.passed,
        "total_queries": report.total_queries,
        "recall_at_k": report.recall_at_k,
        "no_result_rate": report.no_result_rate,
        "avg_top_similarity": report.avg_top_similarity,
        "avg_latency_ms": report.avg_latency_ms,
        "threshold_violations": report.threshold_violations,
        "failed_queries": report.failures[:10],
    }


@router.get("/evals/latency")
async def get_latency_summary(
    current_user: User = Depends(get_current_superuser),
):
    """Get pipeline latency summary with P50/P95/P99 percentiles."""
    from app.evals.latency_eval import latency_evaluator
    summary = latency_evaluator.get_summary()
    return {
        "total_measurements": summary.total_measurements,
        "avg_total_ms": summary.avg_total_ms,
        "p50_ms": summary.p50_ms,
        "p95_ms": summary.p95_ms,
        "p99_ms": summary.p99_ms,
        "sla_compliance_rate": summary.sla_compliance_rate,
        "avg_retrieval_ms": summary.avg_retrieval_ms,
        "avg_llm_ms": summary.avg_llm_ms,
        "avg_query_intelligence_ms": summary.avg_qi_ms,
        "slow_queries_count": len(summary.slow_queries),
    }


@router.get("/evals/cost")
async def get_cost_summary(
    organization_id: str = Query(...),
    monthly_budget: float = Query(500.0),
    current_user: User = Depends(get_current_superuser),
):
    """Get AI cost summary and monthly projection for an organization."""
    from app.evals.cost_eval import cost_evaluator
    summary = cost_evaluator.get_summary(
        organization_id=organization_id,
        monthly_budget=monthly_budget,
    )
    return {
        "total_cost_usd": summary.total_cost_usd,
        "total_queries": summary.total_queries,
        "avg_cost_per_query": summary.avg_cost_per_query,
        "cache_savings_usd": summary.cache_savings_usd,
        "cost_by_model": summary.cost_by_model,
        "monthly_projection_usd": summary.monthly_projection_usd,
        "budget_utilization_pct": summary.budget_utilization_pct,
        "most_expensive_model": summary.most_expensive_model,
    }


@router.get("/evals/retrieval-tuning")
async def get_retrieval_tuning_recommendations(
    current_user: User = Depends(get_current_superuser),
):
    """Get automated retrieval tuning recommendations based on failure patterns."""
    from app.retrieval_learning.retrieval_tuning import retrieval_tuner
    return await retrieval_tuner.get_recommendations()


@router.get("/knowledge-graph/{organization_id}/stats")
async def get_knowledge_graph_stats(
    organization_id: str,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """Get knowledge graph statistics for an organization."""
    from app.knowledge_graph.graph_retriever import graph_retriever
    from app.knowledge_graph.graph_builder import graph_builder
    chunks = graph_retriever._fetch_all_chunks(organization_id, db, limit=200)
    graph = await graph_builder.get_or_build(organization_id, chunks)
    node_types: Dict[str, int] = {}
    for node in graph.nodes.values():
        node_types[node.node_type] = node_types.get(node.node_type, 0) + 1
    return {
        "total_nodes": len(graph.nodes),
        "total_edges": len(graph.edges),
        "node_types": node_types,
    }


@router.delete("/knowledge-graph/{organization_id}/cache")
async def invalidate_knowledge_graph(
    organization_id: str,
    current_user: User = Depends(get_current_superuser),
):
    """Invalidate cached knowledge graph for an organization."""
    from app.knowledge_graph.graph_builder import graph_builder
    await graph_builder.invalidate(organization_id)
    return {"message": f"Knowledge graph cache invalidated for org {organization_id}"}
