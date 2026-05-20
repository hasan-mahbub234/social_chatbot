"""Custom exception classes."""
from fastapi import status
from app.exceptions.error_codes import (
    AUTH_INVALID_TOKEN, RESOURCE_NOT_FOUND, RESOURCE_FORBIDDEN,
    VALIDATION_FAILED, AI_SERVICE_UNAVAILABLE, AI_HALLUCINATION_DETECTED,
    GOV_POLICY_VIOLATION, GOV_JAILBREAK_DETECTED, RISK_ESCALATED,
    RATE_LIMIT_EXCEEDED, INTERNAL_ERROR,
)


class AIAgentException(Exception):
    def __init__(self, message: str, code: str = INTERNAL_ERROR, status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(AIAgentException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, AUTH_INVALID_TOKEN, status.HTTP_401_UNAUTHORIZED)


class AuthorizationError(AIAgentException):
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, RESOURCE_FORBIDDEN, status.HTTP_403_FORBIDDEN)


class ResourceNotFoundError(AIAgentException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, RESOURCE_NOT_FOUND, status.HTTP_404_NOT_FOUND)


class ValidationError(AIAgentException):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, VALIDATION_FAILED, status.HTTP_422_UNPROCESSABLE_ENTITY)


class RateLimitError(AIAgentException):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, RATE_LIMIT_EXCEEDED, status.HTTP_429_TOO_MANY_REQUESTS)


class AIServiceError(AIAgentException):
    def __init__(self, message: str = "AI service error"):
        super().__init__(message, AI_SERVICE_UNAVAILABLE, status.HTTP_503_SERVICE_UNAVAILABLE)


class HallucinationError(AIAgentException):
    def __init__(self, message: str = "Hallucination detected"):
        super().__init__(message, AI_HALLUCINATION_DETECTED, status.HTTP_400_BAD_REQUEST)


class GovernanceViolationError(AIAgentException):
    def __init__(self, message: str = "Policy violation"):
        super().__init__(message, GOV_POLICY_VIOLATION, status.HTTP_400_BAD_REQUEST)


class JailbreakError(AIAgentException):
    def __init__(self, message: str = "Jailbreak attempt detected"):
        super().__init__(message, GOV_JAILBREAK_DETECTED, status.HTTP_400_BAD_REQUEST)


class EscalationError(AIAgentException):
    def __init__(self, message: str = "Request escalated"):
        super().__init__(message, RISK_ESCALATED, status.HTTP_400_BAD_REQUEST)
