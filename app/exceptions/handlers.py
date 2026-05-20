"""Custom exception handlers."""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import traceback
from app.core.logging import get_logger


logger = get_logger(__name__)


class AIAgentException(Exception):
    """Base exception for AI Agent platform."""
    
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(AIAgentException):
    """Authentication failed."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_ERROR", status.HTTP_401_UNAUTHORIZED)


class AuthorizationError(AIAgentException):
    """Authorization denied."""
    
    def __init__(self, message: str = "Authorization denied"):
        super().__init__(message, "AUTHZ_ERROR", status.HTTP_403_FORBIDDEN)


class ResourceNotFoundError(AIAgentException):
    """Resource not found."""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, "NOT_FOUND", status.HTTP_404_NOT_FOUND)


class ValidationError(AIAgentException):
    """Validation failed."""
    
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, "VALIDATION_ERROR", status.HTTP_422_UNPROCESSABLE_ENTITY)


class RateLimitError(AIAgentException):
    """Rate limit exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, "RATE_LIMIT", status.HTTP_429_TOO_MANY_REQUESTS)


class AIServiceError(AIAgentException):
    """AI service error."""
    
    def __init__(self, message: str = "AI service error"):
        super().__init__(message, "AI_SERVICE_ERROR", status.HTTP_503_SERVICE_UNAVAILABLE)


class RiskAssessmentError(AIAgentException):
    """Risk assessment failed."""
    
    def __init__(self, message: str = "Risk assessment failed"):
        super().__init__(message, "RISK_ASSESSMENT_ERROR", status.HTTP_400_BAD_REQUEST)


class HallucinationDetectedError(AIAgentException):
    """Hallucination detected in response."""
    
    def __init__(self, message: str = "Hallucination detected in AI response"):
        super().__init__(message, "HALLUCINATION_DETECTED", status.HTTP_400_BAD_REQUEST)


class EscalationError(AIAgentException):
    """Escalation failed."""
    
    def __init__(self, message: str = "Escalation failed"):
        super().__init__(message, "ESCALATION_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR)


async def ai_agent_exception_handler(request: Request, exc: AIAgentException):
    """Handle AI Agent exceptions."""
    logger.error(
        f"AI Agent Exception: {exc.code}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "message": exc.message,
            "code": exc.code,
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation exceptions."""
    logger.warning(
        "Validation error",
        extra={
            "path": request.url.path,
            "errors": exc.errors(),
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Validation failed",
                "details": exc.errors(),
            }
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(
        f"Unhandled exception: {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "traceback": traceback.format_exc(),
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
            }
        }
    )


def add_exception_handlers(app: FastAPI):
    """Register exception handlers."""
    app.add_exception_handler(AIAgentException, ai_agent_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
