"""Unit tests for app.config (M0 Task 4 TDD RED)."""
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.configs.postgres import PostgresSettings
from app.configs.opensearch import OpenSearchSettings
from app.configs.tei import TEISettings


class TestSettingsAggregate:
    """Settings 顶层聚合测试."""

    def test_settings_loads_with_all_submodels(self, monkeypatch):
        """Given 完整 env，Settings 应能加载所有子模型."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "test_pw")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_DATABASE_URL", "postgresql://x:y@h:5432/d")
        monkeypatch.setenv("MINIO_SECRET_KEY", "minio_test")

        s = Settings()

        assert s.postgres.host == "postgres"
        assert s.postgres.port == 5432
        assert s.postgres.password == "test_pw"
        assert s.opensearch.url == "http://opensearch:9200"
        assert s.tei.embed_dim == 1024
        assert s.langfuse.host == "http://langfuse:3000"
        assert s.minio.bucket == "rag-backups"

    def test_settings_postgres_dsn_format(self, monkeypatch):
        """PostgresSettings.dsn 格式正确."""
        monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
        ps = PostgresSettings(password="pw", host="db", port=5432, user="u", db="d")
        assert ps.dsn == "postgresql+asyncpg://u:pw@db:5432/d"

    def test_settings_missing_required_field_raises(self, monkeypatch):
        """缺 postgres.password 应抛 ValidationError."""
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        with pytest.raises(ValidationError):
            Settings()

    def test_settings_opensearch_default_bulk_size(self):
        """OpenSearchSettings.bulk_size 默认 500 (M4 r2 P0-3)."""
        os = OpenSearchSettings(url="http://x:9200")
        assert os.bulk_size == 500
        assert os.refresh_interval == "30s"

    def test_settings_tei_embed_dim_is_1024(self):
        """TEISettings.embed_dim 默认 1024 (bge-m3)."""
        tei = TEISettings()
        assert tei.embed_dim == 1024
        assert tei.model_id == "BAAI/bge-m3"
