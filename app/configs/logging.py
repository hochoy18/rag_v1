"""Logging settings (M0 P1-6 r1 修订). env_prefix=LOG_"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class LoggingSettings(BaseAppSettings):
    """structlog logging config."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = Field(default="INFO", description="Log level: DEBUG / INFO / WARNING / ERROR")
    json_format: bool = Field(default=True, description="JSON log output (prod) vs console (dev)")
    include_timestamp: bool = Field(default=True, description="Include timestamp in log records")
    include_trace_id: bool = Field(default=True, description="Include Langfuse trace_id in log records")
