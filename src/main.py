import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.utils.logger import configure_root_logger, get_logger
from src.api.middleware import CorrelationIDMiddleware

logger = get_logger(__name__)


# ── Lifespan: startup / shutdown hooks ───────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_root_logger(settings.LOG_LEVEL)
    logger.info("Starting Resume Intelligence Tracker", extra={"env": settings.APP_ENV})
    yield
    logger.info("Shutting down Resume Intelligence Tracker")


# ── App factory ──────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="Resume Intelligence Tracker",
        description="Application logger and resume intelligence pipeline.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middleware (order matters: correlation ID first) ──
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────
    from src.api.health import router as health_router
    app.include_router(health_router)

    # from src.api.applications import router as applications_router
    # app.include_router(applications_router, prefix="/api/v1", tags=["applications"])

    # ── Global exception handler ─────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            extra={"path": request.url.path, "error": str(exc)},
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "path": request.url.path},
        )

    return app


app = create_app()
