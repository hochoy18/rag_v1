"""LLM 工厂 (M3 Task 1).

r3 实施层: V1 仅支持 anthropic provider (ChatAnthropic 工厂).
openai 兼容 (minimax-cn 走 OpenAI 兼容) 走 base_url 参数.
"""
from __future__ import annotations

from typing import Any

from app.configs.llm import LLMSettings


def build_chat_model(settings: LLMSettings | None = None, **overrides: Any):
    """Build a chat model instance.

    V1 仅支持 anthropic provider.
    openai 兼容: 设 base_url 后 ChatOpenAI 走 OpenAI 兼容端点 (minimax-cn).
    """
    from app.config import settings as app_settings
    cfg = settings or app_settings.llm

    # 应用 overrides
    model_name = overrides.get("model_name", cfg.model_name)
    api_key = overrides.get("api_key", cfg.api_key)
    base_url = overrides.get("base_url", cfg.base_url)
    max_tokens = overrides.get("max_tokens", cfg.max_tokens)
    temperature = overrides.get("temperature", cfg.temperature)
    timeout = overrides.get("timeout_seconds", cfg.timeout_seconds)
    max_retries = overrides.get("max_retries", cfg.max_retries)

    if cfg.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model_name,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )
    elif cfg.provider in ("openai", "local", "minimax"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,  # minimax-cn 走 OpenAI 兼容 base_url
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )
    else:
        raise ValueError(f"unsupported LLM provider: {cfg.provider}")


def build_embeddings():
    """Build TEI embedding client (M3).

    V1 用 TEIEmbeddings (本模块) 跑 bge-m3.
    """
    from app.llm.teienv import TEIEmbeddings
    from app.config import settings as app_settings
    tei = app_settings.tei
    return TEIEmbeddings(
        base_url=tei.base_url,
        batch_size=tei.batch_size,
        dim=tei.dim,
        timeout_seconds=tei.timeout_seconds,
    )
