"""RAG V1 top-level settings (M0 P1-9 + X-3 落地: 末尾 `settings = Settings()` 全局单例)

来源: M0 plan 2026-06-10-rag-m0-infra.md Task 4
聚合: PostgresSettings / OpenSearchSettings / TEISettings / LangfuseSettings / MinIOSettings / LoggingSettings / AppSettings

r2 修订: 每子模型自管 env_prefix（POSTGRES_/OPENSEARCH_/TEI_/LANGFUSE_/MINIO_/LOG_/APP_）。
顶层 Settings 不再设 env_nested_delimiter，避免 3 层嵌套解析错位。
"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from app.configs.app import AppSettings
from app.configs.base import BaseAppSettings
from app.configs.db import DBSettings
from app.configs.postgres import PostgresSettings
from app.configs.opensearch import OpenSearchSettings
from app.configs.tei import TEISettings
from app.configs.langfuse import LangfuseSettings
from app.configs.minio import MinIOSettings
from app.configs.logging import LoggingSettings
from app.configs.app import AppSettings


class Settings(BaseAppSettings):
    """Top-level RAG V1 settings (运行时: env_file=.env).

    r2 实操修订: 故意不在这里设 env_file，依赖 BaseAppSettings 默认 ".env"；测试用 `from app.config import build_settings; build_settings(env_file=None)`.
    """

    app: AppSettings = Field(default_factory=AppSettings)
    db: DBSettings = Field(default_factory=DBSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    tei: TEISettings = Field(default_factory=TEISettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    log: LoggingSettings = Field(default_factory=LoggingSettings)


def build_settings(env_file: str | None = ".env"):
    """Build a fresh Settings class with custom env_file (r2 测试用).

    pydantic-settings 2.x 不支持直接传 env_file 到 Settings.__init__，
    用动态类 + model_config 覆盖。
    """
    class _CustomSettings(Settings):
        model_config = SettingsConfigDict(
            env_file=env_file,
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )
    return _CustomSettings()


# X-3 落地: 末尾全局单例（启动时构造一次，跨模块 import 直接用）
settings = Settings()


__all__ = ["Settings", "settings", "build_settings"]
