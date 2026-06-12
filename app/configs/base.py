"""Base settings (M0 P1-9 公共 BaseSettings).

r2 修订: env_prefix 模式 —— 每子模型显式 env_prefix="POSTGRES_" 之类
让 env 形如 POSTGRES_HOST / POSTGRES_PASSWORD 直接映射到子模型 host/password 字段
（避免 pydantic-settings 默认 env_nested_delimiter='_' 把 'LANGFUSE_SECRET_KEY'
解析成 {langfuse: {secret: {key: ...}} 的 3 层嵌套路径）。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    """Common base for all sub-configs (env 前缀 / dotenv 加载策略)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
