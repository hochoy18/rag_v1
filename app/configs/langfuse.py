"""Langfuse settings (M0/M10). env_prefix=LANGFUSE_

r1 修复 P1-3: 补 NEXTAUTH_SECRET / NEXTAUTH_URL / SALT (Langfuse 容器 env) + LangfuseSettings 字段
"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class LangfuseSettings(BaseAppSettings):
    """Langfuse LLM observability settings."""

    model_config = SettingsConfigDict(env_prefix="LANGFUSE_")

    host: str = Field(default="http://langfuse:3000", description="Langfuse Web URL")
    public_key: str = Field(default="pk-lf-CHANGEME", description="Langfuse public key (项目级)")
    secret_key: str = Field(description="Langfuse secret key (required)")
    database_url: str = Field(description="Langfuse Postgres URL (container env)")

    # Langfuse 容器自身需要的 env (M0 P1-3 补)
    nextauth_secret: str = Field(default="CHANGEME_nextauth", description="NEXTAUTH_SECRET")
    nextauth_url: str = Field(default="http://localhost:3000", description="NEXTAUTH_URL")
    salt: str = Field(default="CHANGEME_salt", description="SALT")
