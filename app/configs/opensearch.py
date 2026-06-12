"""OpenSearch settings (M0/M4/M7). env_prefix=OPENSEARCH_"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class OpenSearchSettings(BaseAppSettings):
    """OpenSearch connection settings (RAG V1 vector store)."""

    model_config = SettingsConfigDict(env_prefix="OPENSEARCH_")

    url: str = Field(default="http://opensearch:9200", description="OpenSearch URL")
    username: str = Field(default="", description="OpenSearch username (空 = 单节点 dev)")
    password: str = Field(default="", description="OpenSearch password (空 = 单节点 dev)")
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    bulk_size: int = Field(default=500, description="Bulk index batch size (M4 r2 P0-3)")
    refresh_interval: str = Field(default="30s", description="Index refresh interval")
    ensure_index_on_startup: bool = Field(default=True, description="Auto-create index on startup")
