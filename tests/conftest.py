"""
Root conftest.py — shared fixtures for all tests.

Provides:
  - db:     per-test async DB session (fresh engine per test, avoids Windows event loop issues)
  - client: per-test HTTPX async client wrapping the FastAPI app
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.main import app
from src.utils.ratelimit import auth_limiter


@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """Auth rate limiting is on by default in the app; turn it off for tests so
    the shared test-client IP doesn't accumulate hits across cases. Tests that
    exercise the limiter re-enable it explicitly and reset the limiter."""
    prev = settings.RATE_LIMIT_ENABLED
    settings.RATE_LIMIT_ENABLED = False
    auth_limiter.reset()
    yield
    settings.RATE_LIMIT_ENABLED = prev
    auth_limiter.reset()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """
    Creates a fresh async engine + session for each test.
    Rolls back after the test — no data bleeds between tests.
    """
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """HTTPX async client wrapping the FastAPI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
