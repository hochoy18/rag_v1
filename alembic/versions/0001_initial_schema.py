"""initial schema (M1)

Revision ID: 0001
Revises:
Create Date: 2026-06-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create 4 核心表 (users / auth_sessions / chat_sessions / ingest_jobs).

    r2 修订:
      - NP-1: auth_sessions.is_revoked
      - NP-2: users partial unique index uq_users_username_active
      - NP-3: auth_sessions.expires_at_hard 索引
      - P1-1: ingest_jobs.payload_hash UNIQUE
    """
    # ===== users =====
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    # r2 NP-2: partial unique index (username 复用)
    op.execute(
        "CREATE UNIQUE INDEX uq_users_username_active ON users(username) WHERE deleted_at IS NULL"
    )
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_index("ix_users_email", "users", ["email"])

    # ===== auth_sessions =====
    op.create_table(
        "auth_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at_sliding", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_hard", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("is_revoked", sa.Boolean, nullable=False, server_default=sa.text("false")),  # r2 NP-1
        sa.Column("ip_address", INET, nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at_hard", "auth_sessions", ["expires_at_hard"])  # r2 NP-3
    op.create_index("ix_auth_sessions_is_revoked", "auth_sessions", ["is_revoked"])

    # ===== chat_sessions =====
    op.create_table(
        "chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thread_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_metadata", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("thread_id", name="uq_chat_sessions_thread_id"),
    )
    op.create_index("ix_chat_sessions_user_active_updated", "chat_sessions", ["user_id", "is_active", "updated_at"])
    op.create_index("ix_chat_sessions_last_message_at", "chat_sessions", ["last_message_at"])

    # ===== ingest_jobs =====
    op.create_table(
        "ingest_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("chunks_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default=sa.text("3")),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("payload_hash", name="uq_ingest_jobs_payload_hash"),  # P1-1
        sa.CheckConstraint(
            "source IN ('file', 'url', 'confluence')",
            name="ck_ingest_jobs_source",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'indexed', 'failed')",
            name="ck_ingest_jobs_status",
        ),
        sa.CheckConstraint(
            "retry_count >= 0 AND max_retries >= 0",
            name="ck_ingest_jobs_retry_nonneg",
        ),
    )
    op.create_index("ix_ingest_jobs_user_id", "ingest_jobs", ["user_id"])
    op.create_index("ix_ingest_jobs_status", "ingest_jobs", ["status"])
    op.create_index("ix_ingest_jobs_next_retry_at", "ingest_jobs", ["next_retry_at"])
    op.create_index("ix_ingest_jobs_completed_at", "ingest_jobs", ["completed_at"])


def downgrade() -> None:
    """Drop 4 表 (回滚)."""
    op.drop_table("ingest_jobs")
    op.drop_table("chat_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
