"""Exceptions package."""
from app.exceptions.custom_exceptions import (
    AIAgentException,
    AuthenticationError,
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
    RateLimitError,
    AIServiceError,
    HallucinationError,
    GovernanceViolationError,
    JailbreakError,
    EscalationError,
)
from app.exceptions.handlers import (
    ai_agent_exception_handler,
    validation_exception_handler,
    general_exception_handler,
    add_exception_handlers,
)

__all__ = [
    "AIAgentException",
    "AuthenticationError",
    "AuthorizationError",
    "ResourceNotFoundError",
    "ValidationError",
    "RateLimitError",
    "AIServiceError",
    "HallucinationError",
    "GovernanceViolationError",
    "JailbreakError",
    "EscalationError",
    "add_exception_handlers",
]
