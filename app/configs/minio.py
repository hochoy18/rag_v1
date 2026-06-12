"""MinIO settings (M0/M12 backup). env_prefix=MINIO_"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class MinIOSettings(BaseAppSettings):
    """MinIO S3-compatible object storage (M12 backup target)."""

    model_config = SettingsConfigDict(env_prefix="MINIO_")

    endpoint: str = Field(default="minio:9000", description="MinIO endpoint")
    access_key: str = Field(default="minio_admin", description="MinIO access key")
    secret_key: str = Field(description="MinIO secret key (required)")
    bucket: str = Field(default="rag-backups", description="Default backup bucket")
    secure: bool = Field(default=False, description="Use HTTPS (False for dev single-node)")
