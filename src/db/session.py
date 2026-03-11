"""
Async SQLAlchemy engine and session factory.

Usage in route/service:
    async def endpoint(db: AsyncSession = Depends(get_db)):
        ...
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── Engine ────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",  # SQL logging in dev only
    pool_pre_ping=True,                       # drop stale connections
    pool_size=5,
    max_overflow=10,
)

# ── Session factory ───────────────────────────────────────
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── FastAPI dependency ────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an AsyncSession and guarantees cleanup.
    Inject via:  db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
