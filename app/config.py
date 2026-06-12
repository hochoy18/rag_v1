"""RAG V1 top-level settings (M0 P1-9 + X-3 落地: 末尾 `settings = Settings()` 全局单例)

来源: M0 plan 2026-06-10-rag-m0-infra.md Task 4
聚合: PostgresSettings / OpenSearchSettings / TEISettings / LangfuseSettings / MinIOSettings / LoggingSettings / AppSettings
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.configs.base import BaseAppSettings
from app.configs.postgres import PostgresSettings
from app.configs.opensearch import OpenSearchSettings
from app.configs.tei import TEISettings
from app.configs.langfuse import LangfuseSettings
from app.configs.minio import MinIOSettings
from app.configs.logging import LoggingSettings
from app.configs.app import AppSettings


class Settings(BaseAppSettings):
    """Top-level RAG V1 settings (聚合所有子模型).

    r2 修订: 每子模型自管 env_prefix（POSTGRES_/OPENSEARCH_/TEI_/LANGFUSE_/MINIO_/LOG_/APP_）。
    顶层 Settings 不再设 env_nested_delimiter，避免 3 层嵌套解析错位。
    """

    app: AppSettings = Field(default_factory=AppSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    tei: TEISettings = Field(default_factory=TEISettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    log: LoggingSettings = Field(default_factory=LoggingSettings)


# X-3 落地: 末尾全局单例（启动时构造一次，跨模块 import 直接用）
settings = Settings()
