"""AI Orchestrator Engine - coordinates all AI operations."""
from app.services.llm import llm_service
from app.services.embedding import embedding_service
from app.services.semantic_cache import semantic_cache_service
from app.services.risk_assessment import risk_assessment_service
from app.services.hallucination_validator import hallucination_validator
from sqlalchemy.orm import Session
from app.models.message import Message
from app.models.risk_assessment import RiskAssessment
from app.models.escalation import Escalation
from app.models.agent import Agent
from app.models.usage import UsageLog
from decimal import Decimal
import logging
from typing import Dict, List, Any
from datetime import datetime
from uuid import UUID

logger = logging.getLogger(__name__)


class AIOrchestrator:
    """Orchestrator for managing AI agent operations with governance."""

    async def process_message(
        self,
        conversation_id: UUID,
        agent_id: UUID,
        user_input: str,
        user_id: UUID,
        db: Session,
    ) -> Dict[str, Any]:
        """Process user message through AI agent with full governance."""
        try:
            logger.info(f"Processing message for agent {agent_id}")

            # 1. Get agent configuration
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            # 2. Check semantic cache
            cached_response = None
            if agent.enable_semantic_cache:
                cached_response = await semantic_cache_service.get_cached_response(
                    user_input, str(agent_id)
                )

            if cached_response:
                logger.info("Using cached response")
                return {
                    "content": cached_response["response"],
                    "tokens_used": 0,
                    "cost": 0.0,
                    "from_cache": True,
                    "similarity": cached_response["similarity"],
                }

            # 3. Assess input risk
            input_risk_assessment = None
            if agent.enable_risk_assessment:
                input_risk = await risk_assessment_service.assess_pii_risk(user_input)
                if input_risk["is_escalated"]:
                    logger.warning(f"Input risk detected: {input_risk}")
                    raise ValueError(f"Input contains sensitive information")

            # 4. Generate AI response
            messages = [
                {"role": "user", "content": user_input},
            ]

            ai_response = await llm_service.generate_response(
                messages=messages,
                model=agent.model,
                temperature=float(agent.temperature),
                max_tokens=int(agent.max_tokens),
                system_prompt=agent.system_prompt,
            )

            # 5. Calculate tokens and cost
            input_tokens = llm_service.count_tokens(user_input)
            output_tokens = llm_service.count_tokens(ai_response)
            total_tokens = input_tokens + output_tokens

            cost = llm_service.estimate_cost(input_tokens, output_tokens, agent.model)

            # 6. Validate for hallucinations
            hallucination_result = None
            if agent.enable_risk_assessment:
                hallucination_result = await hallucination_validator.validate_response(
                    user_input, ai_response, []
                )
                logger.info(
                    f"Hallucination score: {hallucination_result['hallucination_score']}"
                )

            # 7. Comprehensive risk assessment
            risk_result = None
            if agent.enable_risk_assessment:
                risk_result = await risk_assessment_service.comprehensive_risk_assessment(
                    str(agent.organization_id),
                    user_input,
                    ai_response,
                    total_tokens,
                    cost,
                    agent.model,
                )
                logger.info(f"Risk assessment: {risk_result['overall_risk_level']}")

            # 8. Handle escalations
            escalation_id = None
            if risk_result and risk_result["is_escalated"] and agent.enable_escalation:
                escalation = Escalation(
                    reason="Risk assessment escalation",
                    severity=risk_result["overall_risk_level"],
                    status="pending",
                    context=risk_result,
                )
                db.add(escalation)
                db.commit()
                escalation_id = escalation.id
                logger.info(f"Created escalation {escalation_id}")

            # 9. Cache response semantically
            if agent.enable_semantic_cache:
                await semantic_cache_service.cache_response(
                    user_input,
                    ai_response,
                    str(agent_id),
                    metadata={"hallucination_score": hallucination_result.get("hallucination_score") if hallucination_result else None},
                )

            # 10. Log usage
            usage_log = UsageLog(
                user_id=user_id,
                agent_id=agent_id,
                endpoint="/chat",
                method="POST",
                status_code=200,
                tokens_used=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=Decimal(str(cost)),
            )
            db.add(usage_log)
            db.commit()

            return {
                "content": ai_response,
                "tokens_used": total_tokens,
                "cost": cost,
                "from_cache": False,
                "hallucination_score": hallucination_result.get("hallucination_score") if hallucination_result else None,
                "risk_level": risk_result.get("overall_risk_level") if risk_result else "low",
                "is_escalated": escalation_id is not None,
                "escalation_id": str(escalation_id) if escalation_id else None,
            }

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise

    async def get_rag_context(
        self,
        query: str,
        documents: List[str],
        similarity_threshold: float = 0.7,
    ) -> List[str]:
        """Get relevant context from documents using semantic search."""
        try:
            relevant_docs = await embedding_service.similarity_search(
                query, documents, similarity_threshold
            )
            return [doc for doc, score in relevant_docs]
        except Exception as e:
            logger.error(f"Error getting RAG context: {e}")
            return []

    async def batch_process_messages(
        self,
        agent_id: UUID,
        messages_data: List[Dict[str, Any]],
        user_id: UUID,
        db: Session,
    ) -> List[Dict[str, Any]]:
        """Process multiple messages in batch."""
        results = []
        for msg_data in messages_data:
            try:
                result = await self.process_message(
                    msg_data["conversation_id"],
                    agent_id,
                    msg_data["content"],
                    user_id,
                    db,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing message in batch: {e}")
                results.append({"error": str(e)})
        return results


# Global orchestrator instance
ai_orchestrator = AIOrchestrator()
