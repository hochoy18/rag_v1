"""M1 unit tests: models + DBSettings + session + alembic env.

来源: 2026-06-10-rag-m1-schema.md Task 1/2/3/4 TDD RED->GREEN

r3 实施层修订: 所有占位符用 _TEST_ 前缀避开 hermes-agent 对 *** 字面量的 client-side sanitize
"""
import subprocess
from pathlib import Path

import pytest

from app.config import build_settings
from app.configs.db import DBSettings
from app.configs import DBSettings as DBSettingsAlias


# 占位符常量 (避开 *** 字面量)
_TEST_PW = "_TEST_POSTGRES_PW"
_TEST_LF_KEY = "_TEST_LF_KEY"
_TEST_LF_DB = "postgresql://u:_TEST_LF_PW@h:5432/d"
_TEST_LF_AUTH = "_TEST_LF_AUTH_SECRET"
_TEST_LF_URL = "http://localhost:3000"
_TEST_LF_SALT = "_TEST_LF_SALT"
_TEST_MINIO = "_TEST_MINIO_PW"


def _setup_test_env(monkeypatch):
    """monkeypatch 全部必填 env."""
    monkeypatch.setenv("POSTGRES_PASSWORD", _TEST_PW)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", _TEST_LF_KEY)
    monkeypatch.setenv("LANGFUSE_DATABASE_URL", _TEST_LF_DB)
    monkeypatch.setenv("LANGFUSE_NEXTAUTH_SECRET", _TEST_LF_AUTH)
    monkeypatch.setenv("LANGFUSE_NEXTAUTH_URL", _TEST_LF_URL)
    monkeypatch.setenv("LANGFUSE_SALT", _TEST_LF_SALT)
    monkeypatch.setenv("MINIO_SECRET_KEY", _TEST_MINIO)
    monkeypatch.setenv("TEI_BASE_URL", "http://tei:80")
    monkeypatch.setenv("TEI_BATCH_SIZE", "32")
    monkeypatch.setenv("TEI_DIM", "1024")
    monkeypatch.setenv("TEI_TIMEOUT_SECONDS", "60")


class TestDBSettings:
    """Task 1: DBSettings."""

    def test_db_settings_loads_from_env(self, monkeypatch):
        """DB_DATABASE_URL env 应被解析."""
        monkeypatch.setenv("DB_DATABASE_URL", "postgresql+asyncpg://u:_PW@h:5432/d")
        s = DBSettings()
        assert s.database_url == "postgresql+asyncpg://u:_PW@h:5432/d"

    def test_db_settings_defaults(self):
        """默认值应符合 V1 (pool_size=10/max_overflow=20/recycle=1800)."""
        s = DBSettings()
        assert s.pool_size == 10
        assert s.max_overflow == 20
        assert s.pool_recycle_seconds == 1800
        assert s.pool_pre_ping is True
        assert s.echo is False

    def test_db_settings_in_top_settings(self, monkeypatch, tmp_path):
        """Settings 顶层应聚合 db 字段."""
        _setup_test_env(monkeypatch)
        # 临时把磁盘 .env 改名
        real_env = Path(".env")
        backup = Path(".env.bak")
        if real_env.exists():
            real_env.rename(backup)
        try:
            # 用空 tmp_path .env, Settings 走 monkeypatch env
            env_file = tmp_path / ".env"
            env_file.write_text("# empty\n")
            s = build_settings(env_file=str(env_file))
            assert hasattr(s, "db"), "Settings must have db field"
            assert isinstance(s.db, DBSettingsAlias)
            assert s.db.pool_size == 10
        finally:
            if backup.exists():
                backup.rename(real_env)


class TestModels:
    """Task 2: SQLAlchemy 4 张表 ORM."""

    def test_user_model_has_columns(self):
        from app.db.models import User
        cols = {c.name for c in User.__table__.columns}
        assert "id" in cols
        assert "username" in cols
        assert "password_hash" in cols
        assert "created_at" in cols
        assert "updated_at" in cols
        assert "deleted_at" in cols  # P1-5

    def test_user_username_unique_partial_index(self):
        """r2 NP-2: users 应有 partial unique index uq_users_username_active."""
        from app.db.models import User
        indexes = list(User.__table__.indexes)
        def is_partial(idx) -> bool:
            kw = getattr(idx, "dialect_kwargs", None) or {}
            return kw.get("postgresql_where") is not None or kw.get("where") is not None
        has_username = [i for i in indexes if any(c.name == "username" for c in i.columns)]
        partial_with_username = [i for i in has_username if is_partial(i)]
        assert len(partial_with_username) >= 1, \
            f"expected partial unique index on username, got {[i.name for i in indexes]}"

    def test_auth_session_has_is_revoked(self):
        """r2 NP-1: auth_sessions 应有 is_revoked 字段."""
        from app.db.models import AuthSession
        cols = {c.name for c in AuthSession.__table__.columns}
        assert "is_revoked" in cols, "r2 NP-1: is_revoked missing"

    def test_auth_session_has_expires_at_hard_index(self):
        """r2 NP-3: auth_sessions.expires_at_hard 应有索引."""
        from app.db.models import AuthSession
        indexes = list(AuthSession.__table__.indexes)
        assert any("expires_at_hard" in [c.name for c in i.columns] for i in indexes), \
            "r2 NP-3: expires_at_hard index missing"

    def test_ingest_job_payload_hash_unique(self):
        """P1-1: ingest_jobs.payload_hash UNIQUE."""
        from app.db.models import IngestJob
        constraints = list(IngestJob.__table__.constraints)
        unique = [c for c in constraints if hasattr(c, "columns") and any(col.name == "payload_hash" for col in c.columns)]
        assert len(unique) >= 1, "P1-1: payload_hash UNIQUE missing"

    def test_ingest_job_status_default_pending(self):
        """ingest_jobs.status 默认 pending."""
        from app.db.models import IngestJob
        status_col = IngestJob.__table__.columns["status"]
        assert "pending" in str(status_col.server_default.arg), f"status server_default: {status_col.server_default.arg}"

    def test_ingest_job_status_check_constraint(self):
        """status CHECK 约束应包含 4 个状态 (M4 r2 修订)."""
        from app.db.models import IngestJob
        constraints = list(IngestJob.__table__.constraints)
        check = [c for c in constraints if type(c).__name__ == "CheckConstraint" and "status" in str(c.sqltext)]
        assert len(check) >= 1, "ingest_jobs status CHECK missing"
        assert "indexed" in str(check[0].sqltext), "M4 r2 P1-5: indexed status missing"

    def test_4_models_registered_in_metadata(self):
        """Base.metadata 应含 4 张表."""
        from app.db.base import Base
        from app.db.models import User, AuthSession, ChatSession, IngestJob
        assert "users" in Base.metadata.tables
        assert "auth_sessions" in Base.metadata.tables
        assert "chat_sessions" in Base.metadata.tables
        assert "ingest_jobs" in Base.metadata.tables


class TestAlembic:
    """Task 4: alembic env.py + initial migration."""

    def test_alembic_env_syntax(self):
        """alembic/env.py 应可解析无 SyntaxError."""
        env = {"PYTHONPATH": "/home/hochoy/.hermes/profiles/coder/home/.local/lib/python3.11/site-packages"}
        r = subprocess.run(
            ["python3", "-c", "import ast; ast.parse(open('/home/hochoy/projects/apps/rag_v1/alembic/env.py').read()); print('SYNTAX OK')"],
            capture_output=True, text=True, env=env
        )
        assert r.returncode == 0, f"env.py syntax error: {r.stderr}"
        assert "SYNTAX OK" in r.stdout

    def test_alembic_ini_exists(self):
        assert Path("/home/hochoy/projects/apps/rag_v1/alembic.ini").exists()

    def test_initial_migration_exists(self):
        versions_dir = Path("/home/hochoy/projects/apps/rag_v1/alembic/versions")
        migrations = list(versions_dir.glob("0001_*.py"))
        assert len(migrations) >= 1, "no 0001 migration found"

    def test_initial_migration_creates_4_tables(self):
        content = (Path("/home/hochoy/projects/apps/rag_v1/alembic/versions/0001_initial_schema.py")).read_text()
        for table in ["users", "auth_sessions", "chat_sessions", "ingest_jobs"]:
            assert f'create_table(\n        "{table}"' in content, \
                f"0001 missing create_table for {table}"

    def test_initial_migration_contains_r2_fixes(self):
        content = (Path("/home/hochoy/projects/apps/rag_v1/alembic/versions/0001_initial_schema.py")).read_text()
        assert "is_revoked" in content, "r2 NP-1: is_revoked missing"
        assert "uq_users_username_active" in content, "r2 NP-2: uq_users_username_active missing"
        assert "ix_auth_sessions_expires_at_hard" in content, "r2 NP-3: ix_auth_sessions_expires_at_hard missing"
