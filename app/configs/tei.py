"""TEI (Text Embeddings Inference) settings (M0/M3/M4). env_prefix=TEI_"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class TEISettings(BaseAppSettings):
    """TEI bge-m3 embedding service settings."""

    model_config = SettingsConfigDict(env_prefix="TEI_")

    url: str = Field(default="http://tei:80", description="TEI service URL (container port 80)")
    model_id: str = Field(default="BAAI/bge-m3", description="HF model id")
    embed_dim: int = Field(default=1024, description="Embedding dim (bge-m3 = 1024)")
    max_batch_size: int = Field(default=32, description="Max batch size per embed call")
    timeout: int = Field(default=60, description="HTTP request timeout")
