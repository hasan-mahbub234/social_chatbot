"""AI Agent orchestration service."""
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from app.core.logging import get_logger
from app.services.llm import llm_service
from app.services.semantic_cache import semantic_cache_service as semantic_cache
from app.governance.engine import governance_engine
from app.services.risk_assessment import risk_assessment_service as risk_assessment_engine
from app.memory.manager import memory_manager
from app.observability.tracing import tracer


logger = get_logger(__name__)


class AgentState(str, Enum):
    """Agent execution state."""
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING = "waiting"
    COMPLETE = "complete"
    ERROR = "error"


class OrchestratorService:
    """Service that orchestrates AI agent workflows."""
    
    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
    
    async def initialize_session(
        self,
        agent_id: int,
        user_id: int,
        conversation_id: int,
        organization_id: int,
    ) -> str:
        """Initialize new agent session."""
        session_id = f"{agent_id}_{user_id}_{conversation_id}_{datetime.utcnow().timestamp()}"
        
        self.active_sessions[session_id] = {
            "agent_id": agent_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "organization_id": organization_id,
            "state": AgentState.IDLE,
            "created_at": datetime.utcnow(),
            "messages": [],
        }
        
        logger.info(f"Initialized session: {session_id}")
        return session_id
    
    async def process_message(
        self,
        session_id: str,
        message: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        """Process user message through orchestrator."""
        session = self.active_sessions.get(session_id)
        
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        logger.info(f"Processing message for session {session_id}")
        
        with tracer.trace(f"process_message_{session_id}", trace_id) as span:
            try:
                # Update session state
                session["state"] = AgentState.PROCESSING
                
                # Check semantic cache for similar queries
                cached_response = await semantic_cache.get(message)
                if cached_response:
                    logger.info("Found cached response")
                    return {
                        "response": cached_response,
                        "cached": True,
                        "trace_id": trace_id,
                    }
                
                # Risk assessment
                risk_result = await risk_assessment_engine.assess(
                    action=message,
                    user_id=session["user_id"],
                    organization_id=session["organization_id"],
                )
                
                span.set_attribute("risk_level", risk_result.risk_level)
                
                if not risk_result.safe:
                    logger.warning(f"Risk assessment blocked message: {risk_result.reason}")
                    session["state"] = AgentState.COMPLETE
                    return {
                        "response": f"This request cannot be processed: {risk_result.reason}",
                        "blocked": True,
                        "trace_id": trace_id,
                    }
                
                # Get response from LLM
                response = await llm_service.generate_response(
                    message=message,
                    conversation_history=session["messages"],
                    agent_id=session["agent_id"],
                )
                
                span.set_attribute("model", response.model)
                span.set_attribute("tokens", response.tokens_used)
                
                # Store in cache
                await semantic_cache.set(message, response.text)
                
                # Store memory
                await memory_manager.store_short_term(
                    conversation_id=session["conversation_id"],
                    agent_id=session["agent_id"],
                    content=f"Q: {message}\nA: {response.text}",
                )
                
                # Update session
                session["state"] = AgentState.COMPLETE
                session["messages"].append({
                    "role": "user",
                    "content": message,
                })
                session["messages"].append({
                    "role": "assistant",
                    "content": response.text,
                })
                
                return {
                    "response": response.text,
                    "cached": False,
                    "trace_id": trace_id,
                }
            
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                session["state"] = AgentState.ERROR
                span.end("error")
                raise
    
    async def escalate_conversation(
        self,
        session_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Escalate conversation to human agent."""
        session = self.active_sessions.get(session_id)
        
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        logger.warning(f"Escalating session {session_id}: {reason}")
        
        session["state"] = AgentState.COMPLETE
        session["escalated"] = True
        
        return {
            "escalated": True,
            "reason": reason,
            "conversation_id": session["conversation_id"],
        }
    
    async def end_session(self, session_id: str) -> bool:
        """End agent session."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            logger.info(f"Ended session: {session_id}")
            return True
        return False
    
    def get_session_state(self, session_id: str) -> Optional[Dict]:
        """Get current session state."""
        return self.active_sessions.get(session_id)


# Global orchestrator instance
orchestrator = OrchestratorService()
