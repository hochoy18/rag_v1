"""Async engine + session factory (M1 Task 3).

r2 修订: connect_args 兼容 pgbouncer transaction pool
        pool_size 10 / max_overflow 20 (V1 单副本 30 连接 / PG max=100 占 30%)
        pool_recycle 1800 + pool_pre_ping=True 防 stale connection
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)

from app.config import settings


def _build_engine() -> AsyncEngine:
    """Build async engine (lazy import settings for testability)."""
    cfg = settings.db
    return create_async_engine(
        cfg.database_url,
        pool_size=cfg.pool_size,
        max_overflow=cfg.max_overflow,
        pool_recycle=cfg.pool_recycle_seconds,
        pool_pre_ping=cfg.pool_pre_ping,
        echo=cfg.echo,
        # pgbouncer transaction pool 兼容: 关闭 prepared statement cache
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )


# 懒初始化 (避免 import 时连接)
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def engine() -> AsyncEngine:
    """Get or create the global async engine."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the global async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            engine(), expire_on_commit=False,
        )
    return _async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield AsyncSession per request."""
    factory = async_session_factory()
    async with factory() as session:
        yield session


# Aliases for convenience (P0-5: 统一暴露面)
async_session = async_session_factory  # 同 async_session_factory()
