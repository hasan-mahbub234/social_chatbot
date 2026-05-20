"""Conversation and chat routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID as PyUUID
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.agent import Agent
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationResponse,
    ConversationDetailResponse,
    ChatRequest,
    ChatResponse,
    MessageResponse,
)
from app.orchestrator.orchestrator import orchestrator
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conv: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new conversation."""
    try:
        # Verify agent exists
        agent = db.query(Agent).filter(Agent.id == conv.agent_id).first()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        # Create conversation
        new_conversation = Conversation(
            agent_id=conv.agent_id,
            user_id=current_user.id,
            title=conv.title,
        )

        db.add(new_conversation)
        db.commit()
        db.refresh(new_conversation)

        logger.info(f"Created conversation: {new_conversation.id}")
        return new_conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating conversation",
        )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: PyUUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get conversation details with messages."""
    try:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"],
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Get messages
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).all()

        return {
            **conversation.__dict__,
            "messages": messages,
            "message_count": len(messages),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting conversation",
        )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: PyUUID,
    conv_update: ConversationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update conversation."""
    try:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"],
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Update fields
        update_data = conv_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(conversation, key, value)

        db.commit()
        db.refresh(conversation)

        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating conversation: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating conversation",
        )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: PyUUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete conversation."""
    try:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"],
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        db.delete(conversation)
        db.commit()

        logger.info(f"Deleted conversation: {conversation_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting conversation",
        )


@router.post("/chat/send", response_model=ChatResponse)
async def send_message(
    chat_request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send message to agent."""
    try:
        # Get or create conversation
        if chat_request.conversation_id:
            conversation = db.query(Conversation).filter(
                Conversation.id == chat_request.conversation_id,
                Conversation.user_id == current_user["user_id"],
            ).first()
            if not conversation:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found",
                )
        else:
            conversation = Conversation(
                agent_id=chat_request.agent_id,
                user_id=current_user["user_id"],
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

        # Process message through orchestrator
        result = await orchestrator.process(
            query=chat_request.message,
            agent_id=chat_request.agent_id,
            conversation_id=conversation.id,
            user_id=current_user["user_id"],
            organization_id=current_user.get("organization_id", current_user["user_id"]),
            db=db,
            context=chat_request.context,
        )

        # Store user message
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=chat_request.message,
            tokens_used=0,
            cost=0.0,
        )
        db.add(user_message)

        # Store AI response
        ai_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=result["content"],
            tokens_used=result.get("tokens_used", 0),
            cost=result.get("cost", 0.0),
        )
        db.add(ai_message)
        db.commit()
        db.refresh(ai_message)

        return {
            "conversation_id": conversation.id,
            "message_id": ai_message.id,
            "role": "assistant",
            "content": result["content"],
            "tokens_used": result.get("tokens_used", 0),
            "cost": result.get("cost", 0.0),
            "sources": result.get("sources", {}),
            "created_at": ai_message.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending message",
        )


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: PyUUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get messages in conversation."""
    try:
        # Verify conversation ownership
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"],
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).offset(skip).limit(limit).all()

        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting messages",
        )
