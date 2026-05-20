"""Exception handling middleware."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging
import traceback

logger = logging.getLogger(__name__)


class ExceptionMiddleware(BaseHTTPMiddleware):
    """Catch and handle exceptions."""

    async def dispatch(self, request: Request, call_next):
        """Handle exceptions from endpoint."""
        try:
            return await call_next(request)
        except Exception as e:
            request_id = getattr(request.state, "request_id", "unknown")
            logger.error(
                f"[{request_id}] Exception: {str(e)}",
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                },
                exc_info=True,
            )

            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
            )
