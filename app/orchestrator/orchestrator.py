"""Central AI Orchestrator — full multi-tenant SaaS pipeline."""
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.core.logging import get_logger
from app.core.config import settings
from app.orchestrator.model_router import model_router
from app.orchestrator.request_router import request_router
from app.orchestrator.response_pipeline import response_pipeline
from app.orchestrator.context_manager import context_manager
from app.orchestrator.fallback_manager import fallback_manager
from app.governance.governance_service import governance_service
from app.risk.risk_engine import risk_engine
from app.cache.semantic_cache import semantic_cache
from app.rag.retriever import rag_retriever
from app.hallucination.validator import hallucination_validator
from app.services.llm import llm_service
from app.observability.metrics import metrics_collector
from app.tenancy.context import tenant_resolver, TenantContext
from app.quota.enforcer import quota_enforcer, QUOTA_CONVERSATIONS, QUOTA_TOKENS
from app.feature_flags.service import feature_flag_service, FEATURE_GPT4O, FEATURE_ADVANCED_GOVERNANCE, FEATURE_HALLUCINATION, FEATURE_RAG, FEATURE_SEMANTIC_CACHE
from app.billing.metering import usage_metering_service
from app.core.constants import GPT4O, GPT4O_MINI
from app.query_intelligence.retrieval_planner import retrieval_planner
import time

logger = get_logger(__name__)

FAST_PATH_SYSTEM_PROMPT = "You are a friendly AI assistant. Be warm, brief, and natural."


class AIOrchestrator:
    """
    Multi-tenant AI orchestration pipeline.

    Pipeline:
    1.  Resolve tenant context
    2.  Quota check
    3.  Feature flags
    4.  Intent classification
    5a. FAST PATH (greetings/small talk) — skip steps 5b-10
    5b. Semantic cache lookup
    6.  Governance evaluation
    7.  Risk scoring
    8.  RAG retrieval
    9.  LLM execution
    10. Hallucination validation (only when RAG context exists)
    11. Billing metering
    12. Cache response
    13. Return structured response
    """

    async def process(
        self,
        query: str,
        agent_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        organization_id: UUID,
        db: Session,
        context: Optional[Dict[str, Any]] = None,
        is_new_conversation: bool = False,
    ) -> Dict[str, Any]:
        start_time = time.time()
        trace_id = f"{conversation_id}-{int(start_time)}"
        org_id = str(organization_id)

        try:
            # 1. Resolve tenant
            tenant: TenantContext = tenant_resolver.resolve(org_id, db)

            if not tenant.is_active:
                return await fallback_manager.safe_fallback("Organization is inactive")

            if not tenant.is_billable:
                return {
                    "content": "Your subscription is inactive. Please update your billing to continue.",
                    "blocked": True,
                    "reason": "subscription_inactive",
                    "tokens_used": 0,
                    "cost": 0.0,
                    "from_cache": False,
                }

            # 2. Quota check
            conv_quota = await quota_enforcer.check(
                tenant, QUOTA_CONVERSATIONS, db,
                increment_by=1.0 if is_new_conversation else 0.0,
            )
            if not conv_quota.allowed:
                metrics_collector.increment_counter("quota_blocked_conversations")
                return {
                    "content": conv_quota.message,
                    "blocked": True,
                    "reason": "quota_exceeded",
                    "quota_type": "conversations",
                    "tokens_used": 0,
                    "cost": 0.0,
                    "from_cache": False,
                }

            # 3. Feature flags
            gpt4o_allowed = feature_flag_service.is_enabled(FEATURE_GPT4O, tenant, db)
            rag_allowed = feature_flag_service.is_enabled(FEATURE_RAG, tenant, db)
            cache_allowed = feature_flag_service.is_enabled(FEATURE_SEMANTIC_CACHE, tenant, db)
            hallucination_allowed = feature_flag_service.is_enabled(FEATURE_HALLUCINATION, tenant, db)
            advanced_gov = feature_flag_service.is_enabled(FEATURE_ADVANCED_GOVERNANCE, tenant, db)

            # 4. Intent classification + Query Intelligence
            normalized = await request_router.normalize(query, context or {})
            intent = normalized.get("intent", "general")
            is_fast_path = normalized.get("is_fast_path", False)

            # Run query intelligence pipeline (multilingual → typo → rewrite → plan)
            # Only for non-fast-path queries to avoid overhead on greetings/small talk
            retrieval_plan = None
            if not is_fast_path:
                try:
                    has_history = bool(context and context.get("has_history"))
                    retrieval_plan = retrieval_planner.plan(
                        query=query,
                        has_conversation_history=has_history,
                    )
                    # Override intent from query intelligence if more specific
                    if retrieval_plan.intent not in ("general",):
                        intent = retrieval_plan.intent
                    logger.info(
                        "query_intelligence_applied",
                        route=retrieval_plan.route,
                        intent=retrieval_plan.intent,
                        transformations=retrieval_plan.transformations_applied,
                        pipeline_ms=retrieval_plan.pipeline_ms,
                    )
                except Exception as qi_err:
                    logger.warning("query_intelligence_failed", error=str(qi_err))

            selected_model = await model_router.select(
                intent=intent, query=query, risk_level="low",
            )
            if selected_model == GPT4O and not gpt4o_allowed:
                selected_model = GPT4O_MINI
                metrics_collector.increment_counter("model_downgraded_plan_gate")

            # 5a. FAST PATH — greetings, small talk, identity
            # Skips: embedding, cache lookup, governance, risk, RAG, hallucination
            if is_fast_path:
                fast_messages = [
                    {"role": "system", "content": FAST_PATH_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ]
                ai_response = await llm_service.generate_response(
                    messages=fast_messages, model=selected_model
                )
                result = await response_pipeline.build(
                    query=query, response=ai_response, model=selected_model,
                    sources={}, hallucination_result=None, risk_result=None, trace_id=trace_id,
                )
                latency_ms = int((time.time() - start_time) * 1000)
                metrics_collector.record_histogram("response_latency_ms", latency_ms)
                metrics_collector.increment_counter("requests_processed")
                logger.info("fast_path_response", intent=intent, latency_ms=latency_ms)
                return {**result, "from_cache": False, "trace_id": trace_id, "plan": tenant.plan_name, "model_used": selected_model}

            # 5b. Semantic cache lookup (skipped for fast path and contextual queries)
            CONTEXT_PRONOUNS = {"this", "that", "it", "these", "those", "the product", "this product"}
            is_contextual = any(p in query.lower() for p in CONTEXT_PRONOUNS) or len(query.split()) <= 6
            if cache_allowed and not is_contextual:
                cached = await semantic_cache.get(query, str(agent_id))
                if cached:
                    metrics_collector.increment_counter("cache_hits")
                    logger.info("cache_hit", trace_id=trace_id)
                    await usage_metering_service.record_chat(
                        organization_id=org_id, user_id=str(user_id),
                        agent_id=str(agent_id), conversation_id=str(conversation_id),
                        model="cache", input_tokens=0, output_tokens=0, cost_usd=0.0,
                        duration_ms=int((time.time() - start_time) * 1000),
                        from_cache=True, db=db, is_new_conversation=is_new_conversation,
                    )
                    return {**cached, "from_cache": True, "trace_id": trace_id}

            metrics_collector.increment_counter("cache_misses")

            # 6. Governance evaluation
            if settings.ENABLE_GOVERNANCE:
                gov_result = await governance_service.evaluate(query, org_id, advanced=advanced_gov)
                if not gov_result["allowed"]:
                    logger.warning("governance_blocked", trace_id=trace_id, reason=gov_result["reason"])
                    return await fallback_manager.governance_block(gov_result)

            # 7. Risk scoring
            risk_result = None
            if settings.ENABLE_RISK_ASSESSMENT:
                risk_result = await risk_engine.score(query, str(user_id), org_id)
                if risk_result["escalate"]:
                    logger.warning("risk_escalated", trace_id=trace_id, score=risk_result["risk_score"])
                    return await fallback_manager.risk_escalation(risk_result, str(conversation_id), db)

                # Re-select model with actual risk level
                risk_level = risk_result["risk_category"]
                selected_model = await model_router.select(intent=intent, query=query, risk_level=risk_level)
                if selected_model == GPT4O and not gpt4o_allowed:
                    selected_model = GPT4O_MINI

            # 8. Retrieval — structured path OR full RAG
            rag_context: List[str] = []
            sources: Dict[str, Any] = {}
            needs_rag = normalized.get("needs_rag", True)
            used_structured = False

            if rag_allowed and needs_rag:
                # 8a. Structured execution — for price/availability queries
                # Bypasses embedding + vector search entirely.
                # Uses direct DB keyword lookup + metadata extraction.
                # Reduces input tokens from ~1500 to ~150 for simple queries.
                from app.structured.executor import structured_executor
                if structured_executor.can_execute(intent, retrieval_plan):
                    struct_context, struct_prompt, used_structured = await structured_executor.execute(
                        query=query,
                        retrieval_plan=retrieval_plan,
                        organization_id=org_id,
                        db=db,
                    )
                    if used_structured:
                        rag_context = struct_context
                        sources = {"structured": True}
                        logger.info("structured_path_used", intent=intent, chunks=len(rag_context))

                # 8b. Full RAG — for all other intents or when structured lookup failed
                if not used_structured:
                    from app.memory.conversation_memory import conversation_memory
                    history = await conversation_memory.get(str(conversation_id), limit=6)

                    if retrieval_plan and retrieval_plan.transformations_applied:
                        rag_query = retrieval_plan.retrieval_query
                    else:
                        rag_query = self._build_rag_query(query, history)

                    if retrieval_plan:
                        top_k = retrieval_plan.top_k
                        threshold = retrieval_plan.threshold
                    else:
                        query_words = len(query.split())
                        from app.orchestrator.context_manager import _PRODUCT_DETAIL_KEYWORDS
                        is_product_q = any(kw in query.lower() for kw in _PRODUCT_DETAIL_KEYWORDS)
                        top_k = 8 if is_product_q else (3 if query_words <= 3 else (4 if query_words <= 8 else 6))
                        threshold = 0.25

                    if intent in ("reasoning", "comparison"):
                        rag_context, sources = await self._agentic_retrieve(
                            query=query, rag_query=rag_query, org_id=org_id,
                            agent_id=str(agent_id), conversation_id=str(conversation_id),
                            db=db, top_k=top_k, selected_model=selected_model,
                        )
                        if intent == "comparison" and retrieval_plan and retrieval_plan.entities:
                            try:
                                from app.knowledge_graph.graph_reasoner import graph_reasoner
                                entity_labels = [e.value for e in retrieval_plan.entities[:2]]
                                graph_result = await graph_reasoner.reason(
                                    query=query, entities=entity_labels,
                                    organization_id=org_id, db=db,
                                )
                                if graph_result.get("graph_context"):
                                    rag_context = [graph_result["graph_context"]] + rag_context
                            except Exception as ge:
                                logger.debug("graph_reasoning_skipped", error=str(ge))
                    else:
                        rag_results = await rag_retriever.retrieve(
                            query=rag_query, organization_id=org_id, db=db,
                            top_k=top_k, threshold=threshold,
                        )
                        rag_context = [r["content"] for r in rag_results]
                        sources = {str(i): r for i, r in enumerate(rag_results)}

                        # If RAG returned nothing, inject agent's website URL as minimal context
                        # so the bot can answer "give me the website link" without hallucinating
                        if not rag_context:
                            try:
                                import uuid as _uuid
                                from app.models.agent import Agent
                                agent_row = db.query(Agent).filter(
                                    Agent.id == _uuid.UUID(str(agent_id))
                                ).first()
                                if agent_row and agent_row.extra_data:
                                    website = agent_row.extra_data.get("website_url", "")
                                    if website:
                                        rag_context = [f"Store website: {website}"]
                            except Exception as _we:
                                logger.debug("website_url_fallback_failed", error=str(_we))

            # 9. Build context + LLM call
            personalization_hint = ""
            memory_facts = ""
            try:
                from app.memory.user_profile_memory import user_profile_memory
                from app.memory.semantic_memory import semantic_memory
                personalization_hint = await user_profile_memory.get_personalization_context(
                    str(user_id), org_id
                )
                memory_facts = await semantic_memory.format_for_prompt(
                    str(conversation_id), query
                )
            except Exception:
                pass

            messages = await context_manager.build_messages(
                query=query, conversation_id=str(conversation_id),
                rag_context=rag_context, db=db,
                agent_id=str(agent_id),
                personalization_hint=personalization_hint,
                memory_facts=memory_facts,
                # Structured path: use minimal prompt + skip history injection
                system_prompt=struct_prompt if used_structured else None,
                skip_history=used_structured,
            )
            ai_response = await llm_service.generate_response(
                messages=messages, model=selected_model,
            )

            # 10. Hallucination validation — disabled to save tokens/cost
            # Enable only on paid tier with sufficient token budget
            hallucination_result = None

            # 11. Build response
            result = await response_pipeline.build(
                query=query, response=ai_response, model=selected_model,
                sources=sources, hallucination_result=hallucination_result,
                risk_result=risk_result, trace_id=trace_id,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            # 12. Billing metering
            await usage_metering_service.record_chat(
                organization_id=org_id, user_id=str(user_id),
                agent_id=str(agent_id), conversation_id=str(conversation_id),
                model=selected_model,
                input_tokens=result.get("input_tokens", 0),
                output_tokens=result.get("output_tokens", 0),
                cost_usd=result.get("cost", 0.0),
                duration_ms=latency_ms, from_cache=False, db=db,
                is_new_conversation=is_new_conversation,
            )
            await quota_enforcer.check(
                tenant, QUOTA_TOKENS, db,
                increment_by=float(result.get("tokens_used", 0)),
            )

            # 13. Cache + observability + profile update
            if cache_allowed and not is_contextual:
                await semantic_cache.set(query, result, str(agent_id))

            # Update user profile from query signals (non-blocking)
            try:
                from app.memory.user_profile_memory import user_profile_memory
                from app.memory.semantic_memory import semantic_memory
                entities = [e.value for e in retrieval_plan.entities] if retrieval_plan else []
                constraints = retrieval_plan.constraints if retrieval_plan else {}
                await user_profile_memory.update_from_query(
                    user_id=str(user_id),
                    org_id=org_id,
                    query=query,
                    intent=intent,
                    entities=entities,
                    constraints=constraints,
                )
                await semantic_memory.extract_and_store(
                    conversation_id=str(conversation_id),
                    user_message=query,
                    assistant_response=result.get("content", ""),
                )
            except Exception:
                pass

            from app.workers.analytics_tasks import update_cost_tracking
            update_cost_tracking.delay(
                org_id, selected_model,
                result.get("input_tokens", 0),
                result.get("output_tokens", 0),
                result.get("cost", 0.0),
            )
            metrics_collector.record_histogram("response_latency_ms", latency_ms)
            metrics_collector.increment_counter("requests_processed")

            # Record latency and cost for eval framework
            try:
                from app.evals.latency_eval import latency_evaluator, LatencyMeasurement
                from app.evals.cost_eval import cost_evaluator, CostRecord
                sla_met = latency_evaluator.check_sla(latency_ms, False, False)
                latency_evaluator.record(LatencyMeasurement(
                    trace_id=trace_id,
                    query_intelligence_ms=retrieval_plan.pipeline_ms if retrieval_plan else 0.0,
                    retrieval_ms=0.0,   # tracked separately in retriever
                    llm_ms=0.0,         # tracked separately in llm_service
                    total_ms=latency_ms,
                    from_cache=False,
                    is_fast_path=False,
                    sla_met=sla_met,
                ))
                cost_evaluator.record(CostRecord(
                    organization_id=org_id,
                    model=selected_model,
                    input_tokens=result.get("input_tokens", 0),
                    output_tokens=result.get("output_tokens", 0),
                    cost_usd=result.get("cost", 0.0),
                    from_cache=False,
                ))
            except Exception:
                pass

            return {
                **result,
                "from_cache": False,
                "trace_id": trace_id,
                "plan": tenant.plan_name,
                "model_used": selected_model,
            }

        except Exception as e:
            logger.error("orchestrator_error", error=str(e), trace_id=trace_id)
            return await fallback_manager.safe_fallback(str(e))


    async def _agentic_retrieve(
        self,
        query: str,
        rag_query: str,
        org_id: str,
        agent_id: str,
        conversation_id: str,
        db,
        top_k: int,
        selected_model: str,
        max_loops: int = 3,
    ) -> tuple:
        """
        Multi-step agentic retrieval for reasoning and comparison intents.

        Loop:
          1. Retrieve chunks for current query
          2. Ask LLM (cheap model): is this context sufficient?
          3. If YES or max loops reached — return
          4. If NO — extract what's missing, refine query, loop

        Only triggered for intent=reasoning or intent=comparison.
        All other intents use single-step retrieval (faster, cheaper).
        Max 3 loops to prevent runaway cost.
        """
        current_query = rag_query
        rag_context: List[str] = []
        sources: Dict[str, Any] = {}

        for loop in range(max_loops):
            rag_results = await rag_retriever.retrieve(
                query=current_query,
                organization_id=org_id,
                db=db,
                top_k=top_k,
                threshold=0.25,
            )

            if not rag_results:
                logger.info("agentic_rag_no_results", loop=loop, query=current_query[:60])
                break

            rag_context = [r["content"] for r in rag_results]
            sources = {str(i): r for i, r in enumerate(rag_results)}

            # Last loop — return what we have without another LLM check
            if loop == max_loops - 1:
                break

            # Ask cheap model: is this context sufficient to answer the query?
            context_preview = "\n\n".join(rag_context[:2])[:800]
            check_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a retrieval quality checker. "
                        "Reply YES if the context fully answers the query. "
                        "Reply NO:<what is missing> if important information is absent. "
                        "Be very brief."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Query: {query}\n\nContext:\n{context_preview}",
                },
            ]
            try:
                check_response = await llm_service.generate_response(
                    messages=check_messages,
                    model=GPT4O_MINI,  # always use cheap model for the check
                )
                check_upper = check_response.upper()

                if "YES" in check_upper:
                    logger.info("agentic_rag_sufficient", loop=loop + 1)
                    break

                # Extract what's missing and refine the query
                missing = check_response.replace("NO:", "").replace("NO", "").strip()
                if missing:
                    current_query = f"{query} {missing}"
                    logger.info(
                        "agentic_rag_refining",
                        loop=loop + 1,
                        refined_query=current_query[:80],
                    )
                else:
                    break  # no useful refinement possible

            except Exception as e:
                logger.warning("agentic_rag_check_failed", error=str(e))
                break  # return what we have

        # Long-context fallback: if RAG returned nothing, route to smart model
        # with a broader prompt rather than returning an empty-context answer
        if not rag_context:
            logger.info("agentic_rag_long_context_fallback", query=query[:60])
            # Caller will use selected_model with empty context —
            # model_router should have already selected GPT4O for reasoning intent

        return rag_context, sources

    def _build_rag_query(self, query: str, history: List[Dict[str, str]]) -> str:
        """
        Build an enriched RAG query by injecting product context from conversation history.
        Only enriches short/ambiguous follow-up queries (1 content word or less).
        Self-contained queries with 2+ content words are returned as-is.
        """

        query_stripped = query.strip().rstrip('?').strip()

        # Self-contained check: query mentions a product name (capitalized OR known product words)
        # If the query has 2+ non-stop content words, treat it as self-contained
        import re
        stop_words = {"how", "much", "what", "is", "the", "are", "does", "do",
                      "price", "cost", "tell", "me", "about", "show", "its",
                      "a", "an", "of", "for", "and", "or", "in", "on", "at"}

        # Bengali pronoun-only queries (এটির দাম কত, ওটার price) — always enrich from history
        BENGALI_PRONOUNS = ("এটির", "এটা", "এটি",
                            "ওটার", "ওটা", "সেটার",
                            "সেটি", "সেটা", "এগুলো")
        has_bengali_pronoun = any(p in query for p in BENGALI_PRONOUNS)

        content_words = [w for w in re.findall(r'[a-zA-Z]+', query_stripped.lower())
                         if w not in stop_words and len(w) > 2]
        # If query has 2+ content words AND no Bengali pronouns, it's self-contained
        if len(content_words) >= 2 and not has_bengali_pronoun:
            return query

        if not history:
            return query

        # Detect location/city queries — these must NOT be enriched with product context
        location_keywords = {
            "store", "location", "shop", "branch", "outlet", "address", "where",
            "dhaka", "chittagong", "ctg", "sylhet", "narayanganj", "mirpur",
            "gulshan", "dhanmondi", "bashundhara", "jumuna", "wari", "airport",
        }
        query_words_lower = set(re.findall(r'[a-z]+', query_stripped.lower()))
        is_location_query = bool(query_words_lower & location_keywords)

        if is_location_query:
            # Check if previous user turn was also a location query
            last_user_topic = next(
                (m["content"] for m in reversed(history)
                 if m["role"] == "user" and m["content"].lower() != query.lower()),
                None
            )
            prev_is_location = bool(
                last_user_topic and
                set(re.findall(r'[a-z]+', last_user_topic.lower())) & location_keywords
            )
            if prev_is_location:
                enriched = f"store locations {query_stripped}"
            else:
                enriched = f"store location {query_stripped}"
            logger.info("rag_query_enriched_location", original=query, enriched=enriched)
            return enriched

        # Extract product name from last assistant reply
        last_assistant = next(
            (m["content"] for m in reversed(history) if m["role"] == "assistant"),
            None
        )

        subject = None
        if last_assistant:
            patterns = [
                r'(?:price|cost|material|color|colour|size|description|availability|stock|variant|detail)s?\s+of\s+(?:the\s+)?([A-Z][\w\s]{3,50}?)\s+(?:is|are|was|were)',
                r'[Ff]or\s+(?:the\s+)?([A-Z][\w\s]{3,50?}?),\s+the',
                r'^(?:The\s+)?([A-Z][\w\s]{3,50}?)\s+(?:is|are|features|comes|has|costs|retails)',
            ]
            for pattern in patterns:
                match = re.search(pattern, last_assistant)
                if match:
                    candidate = match.group(1).strip()
                    skip = {"the", "it", "this", "that", "there", "unfortunately",
                            "i", "materials used", "material", "price", "color", "size",
                            "no information", "turaag active"}
                    if candidate.lower() not in skip and len(candidate) > 3:
                        subject = candidate
                        break

        if subject:
            enriched = f"{subject} {query}"
            logger.info("rag_query_enriched_from_assistant",
                        original=query, subject=subject, enriched=enriched)
            return enriched

        # Fall back: use last user message that's more specific than current query
        last_user = next(
            (m["content"] for m in reversed(history)
             if m["role"] == "user"
             and m["content"].lower() != query.lower()
             and len(m["content"].split()) > len(query.split())),
            None
        )
        if last_user:
            enriched = f"{last_user} {query}"
            logger.info("rag_query_enriched_from_user",
                        original=query, enriched_len=len(enriched))
            return enriched

        return query

orchestrator = AIOrchestrator()
