"""Conversation service — business logic for conversations."""
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.conversation import Conversation
from app.models.message import Message
from app.core.logging import get_logger

logger = get_logger(__name__)


class ConversationService:
    """Manage conversation lifecycle."""

    def create(self, agent_id: UUID, user_id: UUID, title: Optional[str], db: Session) -> Conversation:
        conv = Conversation(agent_id=agent_id, user_id=user_id, title=title)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv

    def get(self, conversation_id: UUID, user_id: UUID, db: Session) -> Optional[Conversation]:
        return db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()

    def get_messages(
        self, conversation_id: UUID, db: Session, skip: int = 0, limit: int = 50
    ) -> List[Message]:
        return (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def add_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        db: Session,
        tokens_used: int = 0,
        cost: float = 0.0,
        model_used: str = None,
        sources: Dict = None,
        hallucination_score: float = None,
        from_cache: bool = False,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tokens_used=tokens_used,
            cost=cost,
            model_used=model_used,
            sources=sources or {},
            hallucination_score=hallucination_score,
            from_cache=from_cache,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    def archive(self, conversation_id: UUID, db: Session) -> bool:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv:
            conv.is_archived = True
            db.commit()
            return True
        return False


conversation_service = ConversationService()
