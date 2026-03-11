"""GET /metrics — returns current in-memory metrics snapshot."""
from fastapi import APIRouter
from src.utils.metrics import get_snapshot

router = APIRouter(tags=["observability"])


@router.get("/metrics")
async def metrics():
    return get_snapshot()
