"""Policy engine — manages and evaluates governance policies."""
from typing import Dict, List, Any, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class PolicyEngine:
    """Evaluate requests against registered governance policies."""

    def __init__(self):
        self._policies: Dict[str, Dict] = {}

    def register(self, policy_id: str, policy: Dict[str, Any]):
        """Register a governance policy."""
        self._policies[policy_id] = policy
        logger.info("policy_registered", policy_id=policy_id)

    def evaluate(self, policy_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate context against a specific policy."""
        policy = self._policies.get(policy_id)
        if not policy or not policy.get("enabled", True):
            return {"passed": True, "violations": [], "policy_id": policy_id}

        violations = []
        for rule in policy.get("rules", []):
            result = self._evaluate_rule(rule, context)
            if result:
                violations.append(result)

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "policy_id": policy_id,
            "policy_name": policy.get("name", ""),
            "action": policy.get("action", "allow"),
        }

    def evaluate_all(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate context against all registered policies."""
        return [self.evaluate(pid, context) for pid in self._policies]

    def _evaluate_rule(self, rule: Dict, context: Dict) -> Optional[str]:
        rule_type = rule.get("type")
        field = rule.get("field", "")
        value = context.get(field)

        if rule_type == "required" and not value:
            return f"Required field missing: {field}"
        if rule_type == "max_length" and value and len(str(value)) > rule.get("max", 10000):
            return f"Field '{field}' exceeds max length"
        if rule_type == "forbidden_value" and value in rule.get("values", []):
            return f"Forbidden value in field '{field}'"
        return None


policy_engine = PolicyEngine()
