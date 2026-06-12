"""App-level settings (M0 顶层). env_prefix=APP_ + LOG_LEVEL fallback"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class AppSettings(BaseAppSettings):
    """App-level meta settings (env / debug / version)."""

    model_config = SettingsConfigDict(env_prefix="APP_")

    env: str = Field(default="development", description="development / staging / production")
    log_level: str = Field(default="INFO", description="DEBUG / INFO / WARNING / ERROR")
