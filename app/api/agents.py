"""Agent management routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID as PyUUID
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.agent import Agent, RiskPolicy
from app.models.organization import Organization
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    RiskPolicyCreate,
    RiskPolicyResponse,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new AI agent."""
    try:
        # Verify organization exists and user is owner or member
        org = db.query(Organization).filter(
            Organization.id == agent.organization_id,
        ).first()
        
        if not org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization not found",
            )

        # Allow org owner or member of that org
        is_owner = str(org.owner_id) == str(current_user.id)
        is_member = str(current_user.organization_id) == str(agent.organization_id) if current_user.organization_id else False
        if not is_owner and not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to create agent in this organization",
            )

        # Create agent
        new_agent = Agent(
            name=agent.name,
            description=agent.description,
            organization_id=agent.organization_id,
            model=agent.model,
            system_prompt=agent.system_prompt,
            temperature=str(agent.temperature),
            max_tokens=str(agent.max_tokens),
            enable_rag=agent.enable_rag,
            enable_semantic_cache=agent.enable_semantic_cache,
            enable_risk_assessment=agent.enable_risk_assessment,
            enable_escalation=agent.enable_escalation,
        )

        db.add(new_agent)
        db.commit()
        db.refresh(new_agent)

        logger.info(f"Created agent: {new_agent.id}")
        return new_agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating agent",
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: PyUUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get agent details."""
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        # Verify user has access to organization
        if agent.organization_id != current_user.organization_id and agent.organization_id != current_user.id:
            org = db.query(Organization).filter(
                Organization.id == agent.organization_id,
                Organization.owner_id == current_user.id,
            ).first()
            
            if not org:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this agent",
                )

        return agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting agent",
        )


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: PyUUID,
    agent_update: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update agent configuration."""
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        # Verify authorization - only owner can update
        org = db.query(Organization).filter(
            Organization.id == agent.organization_id,
            Organization.owner_id == current_user.id,
        ).first()

        if not org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this agent",
            )

        # Update fields
        update_data = agent_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(agent, key, value)

        db.commit()
        db.refresh(agent)

        logger.info(f"Updated agent: {agent_id}")
        return agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating agent",
        )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: PyUUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an agent."""
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        # Verify authorization
        org = db.query(Organization).filter(
            Organization.id == agent.organization_id,
            Organization.owner_id == current_user["user_id"],
        ).first()

        if not org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this agent",
            )

        db.delete(agent)
        db.commit()

        logger.info(f"Deleted agent: {agent_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting agent",
        )


@router.get("/{agent_id}/policies", response_model=list[RiskPolicyResponse])
async def get_agent_policies(
    agent_id: PyUUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get risk policies for an agent."""
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        policies = db.query(RiskPolicy).filter(
            RiskPolicy.agent_id == agent_id
        ).all()

        return policies
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting policies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting policies",
        )
