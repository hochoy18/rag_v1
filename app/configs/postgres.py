"""Postgres settings (M0/M1). env_prefix=POSTGRES_"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class PostgresSettings(BaseAppSettings):
    """Postgres connection settings."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    host: str = Field(default="postgres", description="Postgres host (service name in compose)")
    port: int = Field(default=5432, description="Postgres port")
    user: str = Field(default="rag_app", description="Postgres user")
    password: str = Field(description="Postgres password (required)")
    db: str = Field(default="rag", description="Postgres database name")

    @property
    def dsn(self) -> str:
        """SQLAlchemy/asyncpg DSN."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"
