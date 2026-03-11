"""
Correlation ID middleware.

- Generates a UUID4 per request (or inherits X-Correlation-ID from caller).
- Sets it in the ContextVar so all downstream code reads it automatically.
- Injects it into every response header as X-Correlation-ID.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.utils.correlation import set_correlation_id
from src.utils.logger import get_logger

logger = get_logger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Honour an upstream correlation ID if provided, else generate one
        incoming = request.headers.get(CORRELATION_HEADER)
        cid = set_correlation_id(incoming)

        logger.debug(
            "Request started",
            extra={"method": request.method, "path": request.url.path},
        )

        response: Response = await call_next(request)
        response.headers[CORRELATION_HEADER] = cid
        return response
