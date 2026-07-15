"""Async database session management for the Kitty red teaming framework.

Provides a configured SQLAlchemy async engine, session factory, and
convenience functions for initialization and teardown.

The default database URL can be overridden via the ``KITTY_DATABASE_URL``
environment variable.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kitty.database.models import Base

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

SQLITE_PREFIX = "sqlite+aiosqlite:///"
_DEFAULT_DB_PATH = Path.home() / ".kitty" / "kitty.db"

DEFAULT_DATABASE_URL: str = os.environ.get(
    "KITTY_DATABASE_URL",
    f"{SQLITE_PREFIX}{_DEFAULT_DB_PATH.as_posix()}",
)
"""Default async database URL, overridable via ``KITTY_DATABASE_URL`` env var."""

# ------------------------------------------------------------------
# Engine and session factory
# ------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Return the global async engine, creating it if necessary.

    Returns:
        The configured :class:`AsyncEngine`.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DEFAULT_DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
        logger.debug("Created async engine for %s", DEFAULT_DATABASE_URL)
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the global session factory, creating it if necessary.

    Returns:
        The configured :class:`async_sessionmaker`.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session as a context manager.

    The session is automatically closed when the generator is done.

    Yields:
        An :class:`AsyncSession` instance.

    Example:
        .. code-block:: python

            async with get_session() as session:
                result = await session.execute(...)
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize the database schema.

    For SQLite, this creates all tables if they do not exist.
    For MySQL/PostgreSQL, metadata is created but migrations
    should be handled externally.
    """
    engine = _get_engine()
    db_url = str(engine.url)

    async with engine.begin() as conn:
        if db_url.startswith(SQLITE_PREFIX):
            # SQLite: create tables directly.
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Created all database tables (SQLite)")
        else:
            # MySQL/PostgreSQL: create metadata only.
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Created database metadata for %s", db_url)

    # Touch the session factory so it's ready.
    _get_session_factory()


async def close_db() -> None:
    """Dispose of the global engine and release resources.

    Call this at application shutdown.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.debug("Disposed database engine")
    _engine = None
    _session_factory = None
