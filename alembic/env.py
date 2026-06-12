"""Alembic env (M1 Task 4).

r2 修订:
  - 从 app.config.settings 读 DATABASE_URL
  - target_metadata = Base.metadata (含 4 张表)
  - 离线模式 (offline migration) 走 raw SQL
  - 在线模式 (online migration) 走 async engine 桥接 (M0 review P1-11)
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# app.config 需在 import alembic 之前 import (避免循环)
from app.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import *  # noqa: F401, F403, E402  # 注册所有 model 到 Base.metadata

# Alembic Config
config = context.config

# 关键修订: sqlalchemy.url 从 settings 读
config.set_main_option("sqlalchemy.url", settings.db.database_url)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata (M1: 4 张表)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (raw SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with given connection (sync)."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
