"""LLM / Embedding 抽象层 (M3).

来源: 2026-06-10-rag-m3-llm-embed.md 修完版

r3 实施层说明 (M3 范围):
- LLM 客户端: ChatAnthropic 工厂 (V1 单模型 minimax-cn/MiniMax-M3)
- Embedding 客户端: TEI HTTP (bge-m3 dim=1024, 端口 80 容器内 / 18080 主机)
- 4 prompt YAML (query_rewrite / answer_rag / chitchat / route_classify)
- 7 节点 pipeline (本轮只搭骨架, 实际编排在 M7 graph)

不包含 (其他 M 负责): M7 graph nodes / M8 API 调用 / M10 Langfuse callback
"""
from app.llm.factory import build_chat_model, build_embeddings
from app.llm.teienv import TEIEmbeddings
from app.configs.llm import LLMSettings  # avoid circular import
from app.llm.prompts.loader import load_prompt

__all__ = [
    "build_chat_model",
    "build_embeddings",
    "TEIEmbeddings",
    "LLMSettings",
    "load_prompt",
]
