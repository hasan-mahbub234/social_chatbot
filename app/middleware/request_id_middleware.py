"""Request ID middleware for tracking."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from uuid import uuid4
import time


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to all requests."""

    async def dispatch(self, request: Request, call_next):
        """Add request ID to request and response."""
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        request.state.start_time = time.time()

        response = await call_next(request)
        
        # Add request ID and duration to response headers
        response.headers["X-Request-ID"] = request_id
        process_time = time.time() - request.state.start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        return response
