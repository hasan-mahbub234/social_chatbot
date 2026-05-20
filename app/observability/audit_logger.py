"""Audit logger — structured audit trail for all actions."""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from app.core.logging import get_logger
from uuid import UUID

logger = get_logger(__name__)


class AuditLogger:
    """Log all significant actions to the audit trail."""

    def log(
        self,
        db: Session,
        action: str,
        resource_type: str,
        organization_id: str,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ):
        """Write audit log entry to database."""
        try:
            entry = AuditLog(
                user_id=user_id,
                organization_id=organization_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                changes=changes or {},
                ip_address=ip_address,
            )
            db.add(entry)
            db.commit()
            logger.info("audit_logged", action=action, resource=resource_type)
        except Exception as e:
            logger.error("audit_log_failed", action=action, error=str(e))

    def log_governance(
        self,
        db: Session,
        organization_id: str,
        policy_name: str,
        policy_type: str,
        action_taken: str,
        severity: str,
        description: str,
        is_blocked: bool = False,
        details: Dict = None,
    ):
        """Log governance event."""
        from app.models.governance_log import GovernanceLog
        try:
            entry = GovernanceLog(
                organization_id=organization_id,
                policy_name=policy_name,
                policy_type=policy_type,
                action_taken=action_taken,
                severity=severity,
                description=description,
                is_blocked=is_blocked,
                details=details or {},
            )
            db.add(entry)
            db.commit()
        except Exception as e:
            logger.error("governance_log_failed", error=str(e))


audit_logger = AuditLogger()
