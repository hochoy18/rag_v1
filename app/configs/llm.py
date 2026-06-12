"""LLM settings (M3 Task 1).

env_prefix=LLM_
"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class LLMSettings(BaseAppSettings):
    """LLM 客户端配置 (M3)."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    provider: str = Field(default="anthropic", description="LLM provider: anthropic/openai/local/minimax")
    model_name: str = Field(default="MiniMax-M3", description="模型名 (V1 minimax-cn/MiniMax-M3)")
    api_key: str | None = Field(default=None, description="API key (生产走 Vault)")
    base_url: str | None = Field(default=None, description="OpenAI 兼容 base URL (minimax-cn 走此)")
    max_tokens: int = Field(default=2048, description="max_tokens for generation")
    temperature: float = Field(default=0.0, description="V1 默认 0 (RAG 需 deterministic)")
    timeout_seconds: float = Field(default=60.0, description="HTTP request timeout")
    max_retries: int = Field(default=2, description="API call retry count")
