"""Unit tests for app.config (M0 Task 4 TDD RED→GREEN).

r2 实操修订: 字段名对齐 M3 plan EmbeddingSettings
  - TEI: url→base_url, max_batch_size→batch_size, embed_dim→dim, timeout→timeout_seconds

r2 修订: 测试用 monkeypatch 喂完整 env + tmp_path .env 提供"部分填"路径。
"""
import pytest
from pydantic import ValidationError

from app.config import build_settings
from app.configs.postgres import PostgresSettings
from app.configs.opensearch import OpenSearchSettings
from app.configs.tei import TEISettings


# Fixture 通用 env（避开 *** 字面量，用 _TEST_PW 标记）
@pytest.fixture
def full_env(monkeypatch):
    """Provide all required env vars."""
    envs = {
        "POSTGRES_PASSWORD": "_TEST_PW",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_DATABASE_URL": "postgresql://u:pw@h:5432/d",
        "LANGFUSE_NEXTAUTH_SECRET": "nextauth-test",
        "LANGFUSE_NEXTAUTH_URL": "http://localhost:3000",
        "LANGFUSE_SALT": "salt-test",
        "MINIO_SECRET_KEY": "minio-test",
        "TEI_BASE_URL": "http://tei:80",
        "TEI_BATCH_SIZE": "32",
        "TEI_DIM": "1024",
        "TEI_TIMEOUT_SECONDS": "60",
    }
    for k, v in envs.items():
        monkeypatch.setenv(k, v)
    return envs


class TestSettingsAggregate:
    """Settings 顶层聚合测试."""

    def test_settings_loads_with_all_submodels(self, full_env):
        """Given 完整 env，Settings 应能加载所有子模型."""
        s = build_settings(env_file=None)  # env_file=None 避免磁盘 .env 干扰

        assert s.postgres.host == "postgres"
        assert s.postgres.port == 5432
        assert s.postgres.password == "_TEST_PW"
        assert s.opensearch.url == "http://opensearch:9200"
        assert s.tei.dim == 1024
        assert s.tei.batch_size == 32
        assert s.tei.base_url == "http://tei:80"
        assert s.langfuse.host == "http://langfuse:3000"
        assert s.minio.bucket == "rag-backups"

    def test_settings_postgres_dsn_format(self):
        """PostgresSettings.dsn 格式正确."""
        ps = PostgresSettings(password="pw", host="db", port=5432, user="u", db="d")
        assert ps.dsn == "postgresql+asyncpg://u:pw@db:5432/d"

    def test_settings_missing_required_field_raises(self, tmp_path):
        """缺 langfuse.secret_key 应抛 ValidationError.

        r2 修订: pydantic-settings 子类 model_config env_file=None 在子模型不继承，
        用 tmp_path 写"部分填" .env + 临时把磁盘 .env 改名 .env.bak 测缺字段路径。
        """
        import os
        env_path = ".env"
        backup = env_path + ".bak"
        if os.path.exists(env_path):
            os.rename(env_path, backup)
        try:
            partial_env = tmp_path / ".env"
            partial_env.write_text("POSTGRES_PASSWORD=_part_test\n")  # 缺 langfuse 全套必填
            with pytest.raises(ValidationError):
                build_settings(env_file=str(partial_env))
        finally:
            if os.path.exists(backup):
                os.rename(backup, env_path)

    def test_settings_opensearch_default_bulk_size(self):
        """OpenSearchSettings.bulk_size 默认 500 (M4 r2 P0-3)."""
        os = OpenSearchSettings(url="http://x:9200")
        assert os.bulk_size == 500
        assert os.refresh_interval == "30s"

    def test_settings_tei_dim_is_1024(self):
        """TEISettings.dim 默认 1024 (bge-m3 硬约束)."""
        tei = TEISettings()
        assert tei.dim == 1024
        assert tei.batch_size == 32
