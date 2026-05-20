"""Governance engine for policy enforcement."""
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel
from app.core.logging import get_logger


logger = get_logger(__name__)


class PolicyLevel(str, Enum):
    """Policy enforcement levels."""
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class GovernancePolicy(BaseModel):
    """Governance policy definition."""
    id: str
    name: str
    description: str
    rules: List[Dict]
    level: PolicyLevel
    enabled: bool
    created_at: datetime
    updated_at: datetime


class GovernanceResult(BaseModel):
    """Governance evaluation result."""
    passed: bool
    policy_id: str
    policy_name: str
    level: PolicyLevel
    message: str
    violations: List[str]


class GovernanceEngine:
    """Enterprise governance engine."""
    
    def __init__(self):
        self.policies: Dict[str, GovernancePolicy] = {}
        self.audit_log: List[Dict] = []
    
    def add_policy(self, policy: GovernancePolicy):
        """Add governance policy."""
        self.policies[policy.id] = policy
        logger.info(f"Added governance policy: {policy.name}")
    
    def remove_policy(self, policy_id: str):
        """Remove governance policy."""
        if policy_id in self.policies:
            del self.policies[policy_id]
            logger.info(f"Removed governance policy: {policy_id}")
    
    async def evaluate(
        self,
        policy_id: str,
        context: Dict,
    ) -> GovernanceResult:
        """Evaluate request against policy."""
        policy = self.policies.get(policy_id)
        
        if not policy or not policy.enabled:
            return GovernanceResult(
                passed=True,
                policy_id=policy_id,
                policy_name=policy.name if policy else "Unknown",
                level=PolicyLevel.ALLOW,
                message="Policy not found or disabled",
                violations=[],
            )
        
        violations = []
        
        # Evaluate rules
        for rule in policy.rules:
            violation = self._evaluate_rule(rule, context)
            if violation:
                violations.append(violation)
        
        # Determine pass/fail
        passed = len(violations) == 0
        
        result = GovernanceResult(
            passed=passed,
            policy_id=policy_id,
            policy_name=policy.name,
            level=policy.level,
            message="Policy check passed" if passed else "Policy violations detected",
            violations=violations,
        )
        
        # Log audit
        await self._log_audit(policy_id, context, result)
        
        logger.info(
            f"Policy evaluation: {policy.name} - {'PASS' if passed else 'FAIL'}",
            extra={
                "policy_id": policy_id,
                "violations": violations,
            }
        )
        
        return result
    
    def _evaluate_rule(self, rule: Dict, context: Dict) -> Optional[str]:
        """Evaluate single rule."""
        rule_type = rule.get("type")
        
        if rule_type == "field_check":
            return self._check_field(rule, context)
        elif rule_type == "value_check":
            return self._check_value(rule, context)
        elif rule_type == "pattern_check":
            return self._check_pattern(rule, context)
        
        return None
    
    def _check_field(self, rule: Dict, context: Dict) -> Optional[str]:
        """Check if required field exists."""
        field = rule.get("field")
        if field not in context:
            return f"Required field missing: {field}"
        return None
    
    def _check_value(self, rule: Dict, context: Dict) -> Optional[str]:
        """Check field value."""
        field = rule.get("field")
        expected = rule.get("expected")
        actual = context.get(field)
        
        if actual != expected:
            return f"Field '{field}' expected '{expected}', got '{actual}'"
        return None
    
    def _check_pattern(self, rule: Dict, context: Dict) -> Optional[str]:
        """Check field pattern."""
        import re
        
        field = rule.get("field")
        pattern = rule.get("pattern")
        value = context.get(field)
        
        if not re.match(pattern, str(value)):
            return f"Field '{field}' does not match pattern '{pattern}'"
        return None
    
    async def _log_audit(
        self,
        policy_id: str,
        context: Dict,
        result: GovernanceResult,
    ):
        """Log governance audit."""
        self.audit_log.append({
            "timestamp": datetime.utcnow(),
            "policy_id": policy_id,
            "result": result.dict(),
            "context": context,
        })


# Global governance engine instance
governance_engine = GovernanceEngine()
