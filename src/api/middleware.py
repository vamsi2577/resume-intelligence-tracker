"""
Middleware:
  - CorrelationIDMiddleware  — generates/attaches X-Correlation-ID + records metrics
  - exception_handlers       — maps service exceptions to HTTP responses
"""
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.utils.correlation import set_correlation_id
from src.utils.exceptions import DuplicateError, NotFoundError, ValidationError
from src.utils.logger import get_logger
from src.utils import metrics

logger = get_logger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(CORRELATION_HEADER)
        cid = set_correlation_id(incoming)

        logger.debug(
            "Request started",
            extra={"method": request.method, "path": request.url.path},
        )

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        metrics.record_request(
            endpoint=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        if response.status_code == 422:
            metrics.record_parse_failure(request.url.path)

        response.headers[CORRELATION_HEADER] = cid
        return response


# ── Exception → HTTP mappers (registered in main.py) ─────

async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc), "resource": exc.resource, "id": exc.id},
    )


async def duplicate_handler(request: Request, exc: DuplicateError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "existing_id": exc.existing_id},
    )


async def service_validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )
