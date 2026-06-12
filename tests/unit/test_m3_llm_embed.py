"""M3 LLM/Embedding 实施层 TDD (Task 1-3 最小集).

来源: 2026-06-10-rag-m3-llm-embed.md 修完版

r3 实施层: 用磁盘 .env.example 作 fixture, 避免 *** 字面量陷阱.
"""
import os
import re
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SITE_PACKAGES = "/home/hochoy/.hermes/profiles/coder/home/.local/lib/python3.11/site-packages"
if SITE_PACKAGES not in sys.path:
    sys.path.insert(0, SITE_PACKAGES)


# 5 service 测试 fixture: 用 .env.example (已含完整字段)
ENV_EXAMPLE = Path("/home/hochoy/projects/apps/rag_v1/.env.example")


@pytest.fixture
def tmp_env_file(tmp_path, monkeypatch):
    """tmp_path 写完整 .env (从 .env.example 复制 + 替换占位).

    r3 实施层修订: 临时把磁盘 .env rename + monkeypatch 全部必填 env,
    防止 build_settings 子模型 env_file 继承读到 .env.example 缺字段.
    """
    if not ENV_EXAMPLE.exists():
        pytest.skip(".env.example not found")
    content = ENV_EXAMPLE.read_text()
    replacements = {
        "CHANGEME": "TESTVAL",
        "your-secret-key-here": "test-secret",
        "your-password-here": "test-password",
        "your-salt-here": "test-salt",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)
    # monkeypatch 全部必填 env (确保子模型从 process env 也能拿到)
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-postgres-pw")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-lf-key")
    monkeypatch.setenv("LANGFUSE_DATABASE_URL", "postgresql://u:***@h:5432/d")
    monkeypatch.setenv("LANGFUSE_NEXTAUTH_SECRET", "test-lf-nextauth")
    monkeypatch.setenv("LANGFUSE_NEXTAUTH_URL", "http://localhost:3000")
    monkeypatch.setenv("LANGFUSE_SALT", "test-lf-salt")
    monkeypatch.setenv("MINIO_SECRET_KEY", "test-minio")
    monkeypatch.setenv("TEI_BASE_URL", "http://tei:80")
    monkeypatch.setenv("TEI_BATCH_SIZE", "32")
    monkeypatch.setenv("TEI_DIM", "1024")
    monkeypatch.setenv("TEI_TIMEOUT_SECONDS", "60")
    # 临时把磁盘 .env 改名 (避免子模型继承 env_file 读到)
    real_env = Path(".env")
    backup = Path(".env.bak")
    if real_env.exists():
        real_env.rename(backup)
    try:
        env_file = tmp_path / ".env"
        env_file.write_text(content)
        yield env_file
    finally:
        if backup.exists():
            backup.rename(real_env)


class TestLLMSettings:
    """app.configs.llm.LLMSettings: V1 minimax-cn 配置."""

    def test_llm_settings_defaults(self):
        from app.configs.llm import LLMSettings
        s = LLMSettings()
        assert s.provider == "anthropic"
        assert s.model_name == "MiniMax-M3"
        assert s.max_tokens == 2048
        assert s.temperature == 0.0
        assert s.timeout_seconds == 60.0
        assert s.max_retries == 2

    def test_llm_settings_env_prefix(self, monkeypatch):
        """LLM_ 前缀的 env 应被解析."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL_NAME", "gpt-4o")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.minimax.cn/v1")
        from app.configs.llm import LLMSettings
        s = LLMSettings()
        assert s.provider == "openai"
        assert s.model_name == "gpt-4o"
        assert s.base_url == "https://api.minimax.cn/v1"

    def test_llm_settings_in_top_settings(self, tmp_env_file):
        """Settings 顶层应聚合 llm 字段."""
        from app.config import build_settings
        s = build_settings(env_file=str(tmp_env_file))
        assert hasattr(s, "llm"), "Settings must have llm field"
        # 走 .env.example 默认
        assert s.llm.model_name == "MiniMax-M3"
        assert s.llm.provider == "anthropic"


class TestTEIEmbeddings:
    """app.llm.teienv.TEIEmbeddings: TEI HTTP 客户端 (bge-m3 dim=1024)."""

    def test_tei_init_defaults(self):
        from app.llm.teienv import TEIEmbeddings
        t = TEIEmbeddings(base_url="http://tei:80")
        assert t.batch_size == 32
        assert t.dim == 1024
        assert t.timeout_seconds == 60.0

    def test_tei_post_single_batch(self):
        from app.llm.teienv import TEIEmbeddings
        fake_response = MagicMock()
        fake_response.read.return_value = b'[[0.1, 0.2, 0.3]]'
        fake_response.__enter__ = MagicMock(return_value=fake_response)
        fake_response.__exit__ = MagicMock(return_value=False)
        t = TEIEmbeddings(base_url="http://tei:80", dim=3)
        with patch("urllib.request.urlopen", return_value=fake_response):
            result = t._post(["hello"])
        assert result == [[0.1, 0.2, 0.3]]

    def test_tei_embed_documents_batched(self):
        """多文档自动分批 (batch_size=2)."""
        from app.llm.teienv import TEIEmbeddings
        t = TEIEmbeddings(base_url="http://tei:80", batch_size=2, dim=2)

        call_count = {"n": 0}

        def fake_urlopen(req, **kwargs):
            import json as _json
            data = _json.loads(req.data.decode())
            n = len(data["inputs"])
            call_count["n"] += 1
            resp = MagicMock()
            resp.read.return_value = _json.dumps([[0.1, 0.2]] * n).encode("utf-8")
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = t.embed_documents(["a", "b", "c", "d", "e"])
        assert call_count["n"] == 3, f"expected 3 batches, got {call_count['n']}"
        assert len(result) == 5

    def test_tei_embed_query(self):
        from app.llm.teienv import TEIEmbeddings
        t = TEIEmbeddings(base_url="http://tei:80", dim=3)
        fake_response = MagicMock()
        fake_response.read.return_value = b'[[0.5, 0.6, 0.7]]'
        fake_response.__enter__ = MagicMock(return_value=fake_response)
        fake_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=fake_response):
            result = t.embed_query("test query")
        assert result == [0.5, 0.6, 0.7]
        assert isinstance(result, list)
        assert isinstance(result[0], float)

    def test_tei_health_check_true(self):
        from app.llm.teienv import TEIEmbeddings
        t = TEIEmbeddings(base_url="http://tei:80")
        fake_response = MagicMock()
        fake_response.status = 200
        fake_response.__enter__ = MagicMock(return_value=fake_response)
        fake_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=fake_response):
            assert t.health_check() is True

    def test_tei_health_check_false(self):
        from app.llm.teienv import TEIEmbeddings
        t = TEIEmbeddings(base_url="http://tei:80")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            assert t.health_check() is False

    def test_tei_url_error_raises_runtime(self):
        from app.llm.teienv import TEIEmbeddings
        t = TEIEmbeddings(base_url="http://tei:80", dim=3)
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            with pytest.raises(RuntimeError):
                t._post(["test"])


class TestPromptLoader:
    """app.llm.prompts.loader: 4 prompt 加载."""

    def test_4_default_prompts(self):
        from app.llm.prompts.loader import DEFAULT_PROMPTS
        assert "route_classify" in DEFAULT_PROMPTS
        assert "query_rewrite" in DEFAULT_PROMPTS
        assert "answer_rag" in DEFAULT_PROMPTS
        assert "chitchat" in DEFAULT_PROMPTS

    def test_load_prompt_default(self):
        from app.llm.prompts.loader import load_prompt
        p = load_prompt("route_classify")
        assert isinstance(p, str)
        assert "RAG" in p and "CHITCHAT" in p

    def test_load_prompt_not_found(self):
        from app.llm.prompts.loader import load_prompt
        with pytest.raises(KeyError):
            load_prompt("nonexistent_prompt_xyz")

    def test_format_prompt_kwargs(self):
        from app.llm.prompts.loader import format_prompt
        result = format_prompt("chitchat", query="How are you?")
        assert "How are you?" in result


class TestBuildEmbeddings:
    """app.llm.factory.build_embeddings: 走 TEIEmbeddings."""

    def test_build_embeddings_uses_tei(self, tmp_env_file):
        from app.llm import build_embeddings
        from app.llm.teienv import TEIEmbeddings
        from app.config import build_settings
        s = build_settings(env_file=str(tmp_env_file))
        # 用 settings 实例 (避免全局单例)
        from app.llm import factory
        emb = factory.build_embeddings()
        assert isinstance(emb, TEIEmbeddings)
        assert emb.dim == 1024
        assert emb.batch_size == 32
