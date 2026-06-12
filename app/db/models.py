"""SQLAlchemy 2.0 ORM models - 4 张核心表 (M1 Task 2).

来源: 2026-06-10-rag-m1-schema.md §4 表结构定义 + r2 修复:
  - NP-1 r2: auth_sessions.is_revoked 字段
  - NP-2 r2: users partial unique index
  - NP-3 r2: auth_sessions.expires_at_hard 索引

不包含 (其他 M 负责): M7 PostgresCheckpointer (不同表) / M2 auth 业务逻辑
"""
import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.sqltypes import Enum as SAEnum

from app.db.base import Base, TimestampMixin


# ============ Enums ============
class IngestSource(str, enum.Enum):
    """ingest_jobs.source 枚举 (M4/M5/M6)."""
    file = "file"
    url = "url"
    confluence = "confluence"


class IngestStatus(str, enum.Enum):
    """ingest_jobs.status 状态机 (M4 r2 修订: pending/running/indexed/failed)."""
    pending = "pending"
    running = "running"
    indexed = "indexed"
    failed = "failed"


# ============ User ============
class User(Base, TimestampMixin):
    """用户表 (M1 §4 users + r2 NP-2 partial unique index)."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"),
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )

    # Relationships
    auth_sessions: Mapped[List["AuthSession"]] = relationship(
        back_populates="user", foreign_keys="AuthSession.user_id",
    )
    chat_sessions: Mapped[List["ChatSession"]] = relationship(
        back_populates="user", foreign_keys="ChatSession.user_id",
    )
    ingest_jobs: Mapped[List["IngestJob"]] = relationship(
        back_populates="user", foreign_keys="IngestJob.user_id",
    )

    # r2 NP-2 partial unique index: username 复用 (deleted_at IS NULL 时 UNIQUE)
    __table_args__ = (
        Index(
            "uq_users_username_active",
            "username",
            postgresql_where=text("deleted_at IS NULL"),
            unique=True,
        ),
        Index("ix_users_deleted_at", "deleted_at"),
        Index("ix_users_email", "email"),
    )


# ============ AuthSession ============
class AuthSession(Base):
    """鉴权会话表 (M1 §4 auth_sessions + r2 NP-1/NP-3)."""
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at_sliding: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    expires_at_hard: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # r2 NP-1: is_revoked (M2 logout / login 软吊销)
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"),
    )
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="auth_sessions", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        # r2 NP-3: expires_at_hard 索引 (M2 cleanup job)
        Index("ix_auth_sessions_expires_at_hard", "expires_at_hard"),
        Index("ix_auth_sessions_is_revoked", "is_revoked"),
    )


# ============ ChatSession ============
class ChatSession(Base, TimestampMixin):
    """聊天会话表 (M1 §4 chat_sessions)."""
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    session_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict, server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="chat_sessions", foreign_keys=[user_id])

    __table_args__ = (
        # P1-2: M8 API 列表排序
        Index("ix_chat_sessions_user_active_updated", "user_id", "is_active", "updated_at"),
        Index("ix_chat_sessions_last_message_at", "last_message_at"),
    )


# ============ IngestJob ============
class IngestJob(Base, TimestampMixin):
    """Ingest 任务表 (M1 §4 ingest_jobs).

    r2 修订: status 改用 SAEnum(IngestStatus) with native_enum=False
             用 VARCHAR + CHECK 约束（避免 PG 枚举类型迁移痛点）
    """
    __tablename__ = "ingest_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'"),
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    chunks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default=text("3"))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="ingest_jobs", foreign_keys=[user_id])

    __table_args__ = (
        # P1-1: payload_hash UNIQUE (M4 ON CONFLICT (payload_hash) DO NOTHING)
        UniqueConstraint("payload_hash", name="uq_ingest_jobs_payload_hash"),
        CheckConstraint(
            "source IN ('file', 'url', 'confluence')",
            name="ck_ingest_jobs_source",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'indexed', 'failed')",
            name="ck_ingest_jobs_status",
        ),
        CheckConstraint(
            "retry_count >= 0 AND max_retries >= 0",
            name="ck_ingest_jobs_retry_nonneg",
        ),
        Index("ix_ingest_jobs_user_id", "user_id"),
        Index("ix_ingest_jobs_status", "status"),
        Index("ix_ingest_jobs_next_retry_at", "next_retry_at"),
        Index("ix_ingest_jobs_completed_at", "completed_at"),
    )


# ============ 一次性 import 时收集所有 model 到 Base.metadata ============
__all__ = [
    "Base",
    "User",
    "AuthSession",
    "ChatSession",
    "IngestJob",
    "IngestSource",
    "IngestStatus",
]
