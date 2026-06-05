import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.core.config import settings
# Import the model registry so every table (incl. users) is on Base.metadata
# before any FK is resolved — see src/models/__init__.py.
from src import models as _models  # noqa: F401
from src.utils.logger import configure_root_logger, get_logger
from src.api.middleware import (
    CorrelationIDMiddleware,
    not_found_handler,
    duplicate_handler,
    service_validation_handler,
)
from src.utils.exceptions import DuplicateError, NotFoundError, ValidationError

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_root_logger(settings.LOG_LEVEL)
    logger.info("Starting Resume Intelligence Tracker", extra={"env": settings.APP_ENV})
    yield
    logger.info("Shutting down Resume Intelligence Tracker")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Resume Intelligence Tracker",
        description="Application logger and resume intelligence pipeline.",
        version="0.3.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middleware (correlation ID first) ─────────────────
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Application-Id",
            "X-Duplicate-Warning",
            "X-Metadata",
            "X-Correlation-ID",
            "X-Environment",
        ],
    )

    # ── Exception handlers ────────────────────────────────
    app.add_exception_handler(NotFoundError, not_found_handler)
    app.add_exception_handler(DuplicateError, duplicate_handler)
    app.add_exception_handler(ValidationError, service_validation_handler)

    # ── Routers ───────────────────────────────────────────
    from src.api.health import router as health_router
    from src.api.applications import router as applications_router
    from src.api.metrics import router as metrics_router
    from src.api.resume_generator import router as resume_generator_router
    from src.api.base_resume import router as base_resume_router
    from src.api.generation_history import router as generation_history_router
    from src.api.auth import router as auth_router
    from src.api.admin import router as admin_router

    app.include_router(health_router)
    app.include_router(applications_router)
    app.include_router(metrics_router)
    app.include_router(resume_generator_router)
    app.include_router(base_resume_router)
    app.include_router(generation_history_router)
    app.include_router(auth_router)
    app.include_router(admin_router)

    # Email watcher (n8n integration) is optional. Disabled by default
    # in the unified product; flip ENABLE_EMAIL_WATCHER=true to expose
    # POST /api/v1/applications/email-event.
    if settings.ENABLE_EMAIL_WATCHER:
        from src.api.email_watcher import router as email_watcher_router
        app.include_router(email_watcher_router)
        logger.info("Email watcher router enabled")
    else:
        logger.info("Email watcher router disabled (ENABLE_EMAIL_WATCHER=false)")

    # ── Dashboard ─────────────────────────────────────────
    dashboard_dir = Path(__file__).parent.parent / "dashboard"
    if dashboard_dir.exists():
        app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

    @app.get("/", include_in_schema=False)
    async def root():
        return FileResponse(str(dashboard_dir / "index.html"))

    # ── Global fallback exception handler ─────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        from src.utils.correlation import get_correlation_id

        cid = get_correlation_id()
        logger.error(
            "Unhandled exception",
            extra={"path": request.url.path, "error": str(exc)},
            exc_info=True,
        )
        # Surface the correlation id in the body and header so a user can
        # quote it when reporting the failure; it joins to the structured
        # logs and (for résumé gen) the resume_generations audit row.
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "path": request.url.path,
                "correlation_id": cid,
            },
            headers={"X-Correlation-ID": cid} if cid else None,
        )

    return app


app = create_app()
