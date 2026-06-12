"""DB settings (M1 Task 1).

env_prefix=DB_ 避免与 POSTGRES_* 冲突
- DATABASE_URL 是 SQLAlchemy 2.0 asyncpg 标准 URL 格式
- pool_size 10 / max_overflow 20: V1 单副本 30 连接（PG max=100 占 30%）
- pool_recycle 1800: 防 stale connection
- pool_pre_ping: 防 PG 端断连
- statement_cache_size=0: 兼容 pgbouncer transaction pool
"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class DBSettings(BaseAppSettings):
    """Database connection settings (M1)."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    database_url: str = Field(
        default="postgresql+asyncpg://rag_app:_PLACEHOLDER_PW@postgres:5432/rag",
        description="SQLAlchemy 2.0 asyncpg URL",
    )
    pool_size: int = Field(default=10, description="Connection pool size")
    max_overflow: int = Field(default=20, description="Max overflow connections")
    pool_recycle_seconds: int = Field(default=1800, description="Connection recycle (stale prevention)")
    pool_pre_ping: bool = Field(default=True, description="Pre-ping connections before use")
    echo: bool = Field(default=False, description="SQLAlchemy echo SQL statements")
