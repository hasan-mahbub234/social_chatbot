"""Seed initial data for development."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, init_db
from app.models.user import User
from app.models.organization import Organization
from app.models.agent import Agent
from app.core.security import hash_password
import uuid

def seed():
    init_db()
    db = SessionLocal()

    try:
        # Create admin user
        admin = User(
            email="admin@example.com",
            username="admin",
            hashed_password=hash_password("admin123!"),
            full_name="Platform Admin",
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.flush()

        # Create organization
        org = Organization(
            name="Demo Organization",
            description="Default demo organization",
            owner_id=admin.id,
            monthly_budget=500.0,
        )
        db.add(org)
        db.flush()

        # Link user to org
        admin.organization_id = org.id

        # Create demo agent
        agent = Agent(
            name="Demo Agent",
            description="Default AI agent for demo",
            organization_id=org.id,
            model="gpt-4o-mini",
            system_prompt="You are a helpful enterprise AI assistant.",
            temperature="0.7",
            max_tokens="2000",
            enable_rag=True,
            enable_semantic_cache=True,
            enable_risk_assessment=True,
            enable_escalation=True,
        )
        db.add(agent)
        db.commit()

        print(f"Seeded: admin@example.com / admin123!")
        print(f"Organization: {org.id}")
        print(f"Agent: {agent.id}")
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed()
