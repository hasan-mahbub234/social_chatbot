"""Request tracking middleware."""
import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from app.core.logging import get_logger


logger = get_logger(__name__)


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """Track all requests with unique IDs."""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and response."""
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Track start time
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate elapsed time
        elapsed_time = time.time() - start_time
        
        # Log request
        logger.info(
            f"{request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_time": elapsed_time,
                "client_host": request.client.host if request.client else None,
            }
        )
        
        # Add headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(elapsed_time)
        
        return response
