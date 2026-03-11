"""
Health check endpoint — liveness + readiness.

GET /health
- 200  { status: "healthy", db: "ok", ... }
- 503  { status: "degraded", db: "unreachable" | "timeout", ... }
"""
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.db.session import AsyncSessionFactory
from src.core.config import settings
from src.utils.correlation import get_correlation_id
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

DB_PING_TIMEOUT = 3  # seconds


async def _check_db() -> str:
    try:
        async with asyncio.timeout(DB_PING_TIMEOUT):
            async with AsyncSessionFactory() as session:
                await session.execute(text("SELECT 1"))
        return "ok"
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as exc:
        logger.warning("DB health check failed", extra={"error": str(exc)})
        return "unreachable"


@router.get("/health", tags=["health"])
async def health_check():
    db_status = await _check_db()
    healthy = db_status == "ok"

    payload = {
        "status": "healthy" if healthy else "degraded",
        "db": db_status,
        "env": settings.APP_ENV,
        "correlation_id": get_correlation_id() or None,
    }

    logger.info("Health check", extra={"db": db_status, "healthy": healthy})
    return JSONResponse(content=payload, status_code=200 if healthy else 503)
