"""SQLAlchemy 2.0 declarative base + TimestampMixin (M1 Task 2).

r2 修订: server_default=func.now() + onupdate=func.now() (P1-15 禁止 client-side default)
        bulk update 走 session.execute(update(...).values(...)) 时 updated_at 不会自动更新
        (需显式 updated_at=func.now() in values)
"""
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base (M1)."""
    pass


class TimestampMixin:
    """created_at + updated_at columns (P1-15 server-side defaults).

    r2 修订 (P0-7 docstring): updated_at only auto-updates on ORM-level dirty detection
    (session.execute(update(Model)) with dirty tracking, or session.add()).

    For bulk update via session.execute(update(...).values(...)), updated_at
    will NOT auto-update — you must pass updated_at=func.now() explicitly.
    See M4 ingest_jobs worker (UPDATE ingest_jobs SET status=..., chunks_count=...).
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),  # 仅 ORM dirty 时触发
        nullable=False,
    )
