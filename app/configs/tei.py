"""TEI (Text Embeddings Inference) settings (M0/M3/M4).

字段名对齐 M3 plan `EmbeddingSettings` (2026-06-10-rag-m3-llm-embed.md Task 1):
  - base_url (str)  ← M3 plan 字段（用 str 而非 HttpUrl, 避免 pydantic HttpUrl 解析吃端口）
  - batch_size (32)
  - dim (1024, bge-m3 硬约束)
  - timeout_seconds (60)

env_prefix=TEI_
"""
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from app.configs.base import BaseAppSettings


class TEISettings(BaseAppSettings):
    """TEI bge-m3 embedding service settings (M0/M3/M4).

    r2 实操修订:
      1. 字段名对齐 M3 plan EmbeddingSettings (url→base_url, max_batch_size→batch_size, embed_dim→dim, timeout→timeout_seconds)
         避免 M3 实施 EmbeddingSettings 时字段冲突。
      2. base_url 用 str 而非 HttpUrl —— pydantic HttpUrl 解析 "http://tei:80" 时省略默认端口
         导致 "http://tei/" (无端口)，但 TEI 容器内端口确实是 80 显式，行为歧义。
    """

    model_config = SettingsConfigDict(env_prefix="TEI_")

    base_url: str = Field(
        default="http://tei:80",
        description="TEI service URL (container port 80; host 18080 mapped via compose)",
    )
    batch_size: int = Field(default=32, description="Max batch size per embed call (P0-3 与 TEI 服务端协调)")
    dim: int = Field(default=1024, description="Embedding dim (bge-m3 = 1024, 硬约束)")
    timeout_seconds: float = Field(default=60.0, description="HTTP request timeout")
