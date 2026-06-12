"""Prompt 加载器 (M3 Task 3).

4 prompt YAML:
- query_rewrite: 把用户 query 改写为更适于检索的 query
- answer_rag: 拿到 chunks 后生成 answer
- chitchat: 不查 RAG 直接闲聊
- route_classify: 判断 query 是 RAG 还是 chitchat

V1: 把 prompt 直接放 prompts/ 目录 .yaml 文件, 启动时读入内存缓存
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROMPTS_DIR = Path(__file__).parent

# 默认 4 prompt (V1 走 literal, V1.1 走 Langfuse 远端加载)
DEFAULT_PROMPTS: dict[str, str] = {
    "route_classify": """\
You are a query router. Decide if the user query requires a RAG (retrieval-augmented) search or is chitchat.

Reply with ONLY one of: RAG or CHITCHAT.

Examples:
- "What is the refund policy?" -> RAG
- "Hi, how are you?" -> CHITCHAT
- "Summarize the Q3 financial report" -> RAG
- "Tell me a joke" -> CHITCHAT

Query: {query}
""",
    "query_rewrite": """\
You are a search query rewriter. Rewrite the user query to be more specific and aligned with how documents would be phrased.

Keep the language. Do NOT add facts. Keep it under 50 words.

Query: {query}

Rewritten query:""",
    "answer_rag": """\
You are a helpful assistant. Use ONLY the provided context to answer the question. If the context is insufficient, say "I don't have enough information."

Context:
{context}

Question: {query}

Answer:""",
    "chitchat": """\
You are a friendly assistant. Respond naturally and briefly.

User: {query}

Response:""",
}


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    """Load prompt by name (from YAML file or DEFAULT_PROMPTS fallback).

    V1: 优先读 prompts/<name>.yaml, 找不到走 DEFAULT_PROMPTS.
    V1.1: Langfuse 远端加载, 失败 fallback 默认.
    """
    yaml_path = PROMPTS_DIR / f"{name}.yaml"
    if yaml_path.exists():
        with open(yaml_path) as f:
            data: Any = yaml.safe_load(f)
            if isinstance(data, dict) and "template" in data:
                return str(data["template"])
            if isinstance(data, str):
                return data
    if name in DEFAULT_PROMPTS:
        return DEFAULT_PROMPTS[name]
    raise KeyError(f"prompt not found: {name}")


def format_prompt(name: str, **kwargs: str) -> str:
    """Load + format prompt with kwargs."""
    template = load_prompt(name)
    return template.format(**kwargs)


__all__ = ["load_prompt", "format_prompt", "DEFAULT_PROMPTS"]
