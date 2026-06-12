# M3 Plan · LLM 工厂 + TEI Embedding 客户端 + Langfuse 观测

> 所属：RAG V1 M0–M12 实施路线 · 第 3 步
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §8 核心 LLM 编排栈](../specs/2026-06-10-rag-v1-scope.md#8-依赖版本清单) · [决策总表 #8/#9/#10](../specs/2026-06-10-rag-v1-scope.md#0-决策总表)
> 脑暴基线：`session 20260608_145040_7202e5` msg 195 §1（保留 langchain 决策）+ msg 195 §6（决策 #8/#9/#10 落点）
> 估时：2 个工作日（Tasks ~6h + 调试 ~6h + 文档 ~4h）（P2-4 修订）
> 范本目的：给 M0/M1/M2/M4–M12 提供"单里程碑"计划的结构样板

**r2-2026-06-11 范本影响通知**（r2 review 验证下游传导已生效）：
- M7 graph：使用 `make_llm("classify")` / `"rewrite"` / `"rerank"` / `"answer"` / `"answer_chitchat"` + 7 节点 KNOWN_NODES 注册
- M10 obs-langfuse：使用 `make_llm("judge")` 节点 + `get_callback_handler(sample_rate=...)` 工厂
- M11 eval-ragas：使用 `make_llm("judge")` 节点 + `LangchainLLMWrapper(judge_llm)` 包装

---

## Goal

把 v1-scope 决策 #8/#9/#10 落成可执行代码契约：
1. 一个 `make_llm(node: str)` 工厂，**注册表**机制管理 7 节点（classify / rewrite / rerank / answer / judge / summarize / answer_chitchat）——P1-5 修订，共用 `ChatAnthropic` 抽象 + Langfuse callback 注入
2. 一个 `TEIEmbedder` 异步客户端，封装 httpx 调自部署 `text-embeddings-inference` 容器（bge-m3, dim=1024, batch=32），**含 dim 硬断言**——P0-3 修订
3. 端到端 smoke：`embed("hello") → vector[1024]` 跑通；`llm.invoke("hi")` 跑通；Langfuse 看板能看到 trace

**不包含**（其他 M 负责）：M7 graph 编排节点函数、M4–M6 ingest pipeline 用 embed、M10 Langfuse 业务级 trace

---

## Architecture

### 仓库布局（apps/rag_v1/）

```
apps/
└── rag_v1/                          # RAG V1 项目根
    ├── infra/                       # 基础设施配置（M0 启动）
    │   └── docker-compose.yml       # PG + OpenSearch + TEI + Langfuse
    │
    ├── app/                         # 应用代码（Python 包）
    │   ├── __init__.py
    │   ├── llm/                     # LLM 工厂 + 节点 prompt
    │   │   ├── __init__.py
    │   │   ├── factory.py           # make_llm(node) → ChatAnthropic + Langfuse callback
    │   │   └── prompts.py           # 4 节点 prompt YAML 加载（mtime 热加载）
    │   ├── prompts/                 # prompt 资源目录
    │   │   ├── classify.yaml
    │   │   ├── rewrite.yaml
    │   │   ├── rerank.yaml
    │   │   ├── answer.yaml
    │   │   ├── judge.yaml           # M11 阶段实写，M3 占位（P1-5）
    │   │   ├── summarize.yaml       # M3 占位（P1-5）
    │   │   └── answer_chitchat.yaml # M3 占位（M7 闲聊分支，P1-5）
    │   ├── embedding/               # Embedding 客户端
    │   │   ├── __init__.py
    │   │   └── client.py            # TEIEmbedder.embed(texts)，含 dim 断言
    │   ├── observability/           # 观测
    │   │   ├── __init__.py
    │   │   ├── langfuse.py          # get_callback_handler() → CallbackHandler（双备 import）
    │   │   └── tracing.py           # @trace 装饰器
    │   ├── config.py                # Pydantic Settings 聚合（M0 已建）
    │   └── ...
    │
    ├── tests/                       # 测试（镜像 app/ 结构）
    │   ├── __init__.py
    │   ├── unit/
    │   │   ├── test_config.py
    │   │   ├── test_llm_factory.py
    │   │   ├── test_tei_embedder.py
    │   │   ├── test_langfuse_callback.py
    │   │   └── test_prompt_yaml_guard.py   # P2-2 新增：yaml ≥ 50 token 守门
    │   └── integration/
    │       └── test_m3_smoke.py     # 4 节点 parametrize 覆盖（P2-6）
    │
    ├── pyproject.toml               # 直接依赖清单（5 个新包 + 1 dev 工具）
    ├── .env.example                 # ANTHROPIC_API_KEY / LANGFUSE_* / TEI_URL
    └── README.md
```

**模块组织原则**：
- `app/`、`tests/` 互为镜像（`app/llm/factory.py` 对应 `tests/unit/test_llm_factory.py`）
- `infra/` 与代码解耦（只放 docker-compose / env 模板 / 初始化 SQL）
- `apps/rag_v1/` 是独立 Python 项目（有自己的 `pyproject.toml`、`venv`、`README`）

### M3 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M7 graph 节点 | `make_llm("classify"\|"rewrite"\|"rerank"\|"answer"\|"answer_chitchat")` | 7 节点共用工厂，注册表化（P1-5） |
| M4–M6 ingest pipeline | `TEIEmbedder.embed(texts)` | batch=32，含 dim 硬断言 |
| M10 Langfuse 集成 | `get_callback_handler()` 注入 invoke | M3 工厂已注（`with_config` 协议） |
| M11 RAGAS eval | `TEIEmbedder.embed`（golden set 离线 embed）+ `make_llm("judge")` | judge 节点 M3 注册表已占位 |

---

## Tech Stack

| 层 | 选型 | 版本（精确） |
|----|------|------------|
| LLM 抽象 | `langchain` | `==1.0.8` |
| LLM 协议 | `langchain-core` | `>=1.0.8,<1.1` |
| LLM 实现 | `langchain-anthropic` | `>=0.3,<1.0` |
| 观测 | `langfuse` | `>=2.50,<3` |
| Embedding HTTP | `httpx` | `>=0.27,<1` |
| 重试 | `tenacity` | `>=8.3,<10` |
| 配置 | `pydantic-settings` | `>=2.3,<3` |
| YAML 解析 | `pyyaml` | `>=6.0,<7`（P2-3） |
| LLM 模型 | minimax-cn `MiniMax-M3` | （非 Python 包，env 配） |
| Embedding 容器 | `ghcr.io/huggingface/text-embeddings-inference:1.5` | bge-m3, dim=1024, CPU |
| Embedding 端口 | `18080:80`（host 18080 → 容器 80）| **r2 已补**：M0 docker-compose 端口配置；避免与 8080/8081 冲突（host 端 `.env.example` 配 `TEI_URL=http://tei:80`，容器内端口 80）|
| 测试 | `pytest` / `pytest-asyncio` / `pytest-httpx` / `pytest-cov` | 见 §测试 |

**关键导入路径**（langchain 1.0.x / langfuse 2.50+，P1-2 双备）：`from langchain_anthropic import ChatAnthropic` / `from langchain_core.messages import HumanMessage, SystemMessage` / `from langfuse.langchain import CallbackHandler`（P1-2 加 fallback `from langfuse.callback.langchain`）/ `import httpx`（Embedding 自建）/ `import yaml`（P2-3 prompt 加载）。

**Python 导入规则**（从 `apps/rag_v1/` 内部）：
- `app.llm.factory` —— `app` 是 `apps/rag_v1/app/`
- `tests.unit.test_llm_factory` —— 跑测试时 `cd apps/rag_v1 && pytest`

**pyproject 依赖补完**（P1-3 + P2-3）：`dependencies` 段追加 `pyyaml>=6.0,<7`；`[project.optional-dependencies] dev` 段追加 `pytest-httpx>=0.30,<1` + `pytest-cov>=5.0,<7`。

---

## Files

**新增**（9 个源文件 + 6 个测试文件）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
| `app/__init__.py` | 包标识 |
| `app/llm/__init__.py` | 暴露 `make_llm` |
| `app/llm/factory.py` | 工厂实现 + **注册表** KNOWN_NODES（7 节点）+ 4 节点 prompt 加载 |
| `app/llm/prompts.py` | 7 节点 system prompt（YAML 加载 + mtime 热加载） |
| `app/prompts/classify.yaml` / `rewrite.yaml` / `rerank.yaml` / `answer.yaml` | 4 节点 prompt（**见 §4 草稿**） |
| `app/prompts/judge.yaml` / `summarize.yaml` / `answer_chitchat.yaml` | P1-5 占位：M11/M7 阶段实写 |
| `app/embedding/__init__.py` | 暴露 `TEIEmbedder` |
| `app/embedding/client.py` | TEI 客户端（**含 dim 硬断言**） |
| `app/observability/__init__.py` | 暴露 `get_callback_handler` |
| `app/observability/langfuse.py` | Langfuse callback 工厂（**双备 import**） |
| `app/observability/tracing.py` | `@trace` 装饰器 |
| `tests/__init__.py` | 测试包标识 |
| `tests/unit/__init__.py` | 单元测试包 |
| `tests/unit/test_config.py` | 配置块单测 |
| `tests/unit/test_llm_factory.py` | 工厂单测（**含 deterministic 强制**） |
| `tests/unit/test_tei_embedder.py` | 嵌入单测（mock httpx，**含 dim 断言**） |
| `tests/unit/test_langfuse_callback.py` | Langfuse 工厂单测（**含双备路径**） |
| `tests/unit/test_prompt_yaml_guard.py` | yaml ≥ 50 token 守门单测（P2-2 新增） |
| `tests/integration/__init__.py` | 集成测试包 |
| `tests/integration/test_m3_smoke.py` | 端到端：embed + llm + langfuse（**4 节点 parametrize**） |
| `.env.example` | 追加 `ANTHROPIC_API_KEY` / `LANGFUSE_*` / `TEI_URL` |

**修改**：
- `pyproject.toml`：追加 4 个新直接依赖（`langchain-anthropic` / `langfuse` / `httpx` / `tenacity` / `pyyaml`），dev 段追加 `pytest-httpx` + `pytest-cov`
- `app/config.py`（M0 已有）：追加 LLM/Embedding/Langfuse 配置块（**含 timeout / max_retries / sample_rate / flush / blocked_keys**）

**不修改**：`infra/docker-compose.yml`（TEI 容器是 M0 启动时已配的 M3 验收前置）、M2 auth（鉴权不参与 M3 路径）

---

## §4 · 4 节点 prompt YAML 草稿（P0-1 修订）

> DoD L283 强制"4 个 prompt yaml 文件（classify/rewrite/rerank/answer）各 ≥ 50 token，含 1-shot 示例"。
> 下列草稿为 M3 阶段定稿，M11 / M7 引用时按需扩展；`judge.yaml` / `summarize.yaml` / `answer_chitchat.yaml` 占位文件见 Files 表 L165-167。

```yaml
# app/prompts/classify.yaml
model: minimax-cn/MiniMax-M3
temperature: 0.0           # classify 要 deterministic（P1-1 工厂层强制 0.0）
max_tokens: 64
system_prompt: |
  你是 query 意图分类器。把用户 query 分到两类之一：
    - "retrieve"：需要查知识库（事实 / 流程 / 代码 / 配置）
    - "chitchat"：闲聊 / 寒暄 / 不需要事实回答
  严格只输出 JSON：{"intent": "retrieve" | "chitchat", "reason": "<1 句中文理由>"}
  ---
  1-shot 示例：
    Q: "你好"
    A: {"intent": "chitchat", "reason": "问候语无信息需求"}
    Q: "V1 决策 #8 选型理由？"
    A: {"intent": "retrieve", "reason": "需查决策表"}
```

```yaml
# app/prompts/rewrite.yaml
model: minimax-cn/MiniMax-M3
temperature: 0.2
max_tokens: 256
system_prompt: |
  你是 query 改写器。基于对话历史把当前 query 改写成 1-3 句、自包含的检索 query。
  规则：
    - 消解代词（"它" → "V1 决策 #8 选型"）
    - 补全主语/对象
    - 保留原 query 的意图
    - 不引入对话外的信息
  严格只输出改写后 query，不要解释，不要前缀。
  ---
  1-shot 示例：
    History: 用户问"V1 决策 #8 选什么"
    Q: "为什么选这个？"
    A: "V1 决策 #8 选择 langchain 1.0.x 的核心理由是什么"
```

```yaml
# app/prompts/rerank.yaml
model: minimax-cn/MiniMax-M3
temperature: 0.0           # rerank 要 deterministic（P1-1 工厂层强制 0.0）
max_tokens: 1024
system_prompt: |
  你是相关性评分员。给每个 chunk 打 0-10 分（10=直接回答 query 核心问题，0=完全无关）。
  输入格式：
    QUERY: <query>
    CHUNKS:
      [1] <chunk1>
      [2] <chunk2>
      ...
  严格只输出 JSON：{"scores": [[1, 8], [2, 3], ...]}，顺序与输入 chunks 对齐，每条为 [chunk_id, score]。
  不要解释，不要 markdown 包裹。
  ---
  1-shot 示例：
    QUERY: "TEIEmbedder dim 怎么断言"
    CHUNKS:
      [1] "TEI 容器返回向量，dim 由模型决定（bge-m3=1024）"
      [2] "postgres 接 pgvector 存 768 维"
    A: {"scores": [[1, 9], [2, 2]]}
```

```yaml
# app/prompts/answer.yaml
model: minimax-cn/MiniMax-M3
temperature: 0.3
max_tokens: 1024
system_prompt: |
  你是 RAG 回答助手。基于 <context> 块回答 <query>。
  规则：
    - 必须用 [1][2][3] 引用编号标注信息来自哪个 chunk
    - context 不足时直说"未找到足够信息"，不要编造
    - 中文回答，markdown 格式
    - 不要输出 context 原文整段
  严格按格式：
    ANSWER: <markdown 回答>
    SOURCES: [1, 2, 3]
  ---
  1-shot 示例：
    QUERY: "M3 范本目的是什么"
    CONTEXT:
      [1] "M3 计划是 RAG V1 路线唯一被显式标注为'范本'的里程碑"
      [2] "M3 给 M0/M1/M2/M4–M12 提供'单里程碑'计划的结构样板"
    A:
      ANSWER: M3 是 RAG V1 路线**唯一**被显式标注为"范本"的里程碑，给 M0/M1/M2/M4–M12 提供单里程碑计划的结构样板 [1][2]。
      SOURCES: [1, 2]
```

> 4 yaml 已含 ≥ 50 token + 1-shot 示例，满足 DoD 第 7 条（由 Task 6 守门测试强制）。
> Task 4 RED 段已含对应"锚定 yaml 实际字符串"断言（见 Task 4 `test_factory_binds_system_prompt` 强化）。

---

## Tasks（2-5 分钟/step 粒度）

### Task 1：Pydantic 配置块（M0 配置层追加）

**RED** · `tests/unit/test_config.py::test_llm_config_loads`
- 写测试：mock env vars → 加载 `Settings().llm` → 断言 `model == "minimax-cn/MiniMax-M3"`
- 跑测试 → 失败（配置不存在）
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_config.py::test_llm_config_loads`

**GREEN** · 改 `app/config.py`（P0-4 + P1-4 修订：含工程化 5 件套 + yaml 优先）：

```python
# 关键字段（plan 阶段定稿，测试按此断言；P1-4 修订 yaml model 唯一来源）
class LLMSettings(BaseSettings):
    temperature_default: float = 0.3   # P1-4 节点 yaml 缺省继承此值
    max_tokens_default: int = 1024     # P1-4 同上
    api_key: SecretStr
    timeout: int = 60                  # P0-4 单次 invoke 超时
    max_retries: int = 3               # P0-4 内部 retry
    rate_limit_rpm: int = 60           # P0-4 token bucket 限速

class EmbeddingSettings(BaseSettings):
    base_url: HttpUrl
    batch_size: int = 32               # P0-3 与 TEI 服务端 max_client_batch_size 协调
    dim: int = 1024                    # P0-3 bge-m3 硬约束，client 端 dim 断言用
    timeout_seconds: float = 60.0      # P0-3

class LangfuseSettings(BaseSettings):
    public_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    host: HttpUrl = HttpUrl("http://localhost:3000")
    sample_rate: float = 1.0           # P0-4 prod 改 0.1
    flush_at: int = 2                  # P0-4 攒 N 条 flush
    flush_interval: float = 5.0        # P0-4 每 N 秒 flush
    blocked_keys: list[str] = []       # P0-4 PII 字段不入 trace

class Settings(BaseSettings):
    llm: LLMSettings
    embedding: EmbeddingSettings
    langfuse: LangfuseSettings

settings = Settings()                  # X-3 全局单例
```

**REFACTOR** · 把 `Settings` 拆成子配置加载（M0 review P2-3 提议的 `configs/` 子目录决议待跨 M 拍板）

### Task 2：TEI 客户端实现（P0-3 修订）

**RED** · `tests/unit/test_tei_embedder.py::test_embed_single_text`
- mock httpx `/embed` 响应：`{"embeddings": [[0.1, 0.2, ...]]}`（dim=1024）
- 测 `TEIEmbedder().embed(["hello"])` → 1 个 vector，len=1024
- 跑测试 → 失败

**GREEN** · 实现 `app/embedding/client.py`（P0-3 + P2-5 修订），关键约束：

- batch_size 由 `EmbeddingSettings.batch_size` 控制（默认 32，与 TEI 服务端协调）
- normalize=true（L2 normalize，可直接走 cosine）；truncate=true（bge-m3 8192 token 上限截断）
- 4xx/5xx 分类：4xx 直接抛 `EmbeddingError`（不重试）；5xx 抛 `EmbeddingError` 触发 tenacity 3 次指数退避（1/2/4s）
- **dim 硬断言**（P0-3）：返回 dim ≠ `self.cfg.dim`（默认 1024）抛 `EmbeddingDimMismatch`
- 协议：`__aenter__` / `__aexit__` / `aclose`（P2-5），调用方 `async with TEIEmbedder() as e: ...`
- httpx timeout：`httpx.Timeout(self.cfg.timeout_seconds)`（默认 60s，P0-3）

完整实现见 review P0-3 段代码块；M3 阶段以 review 内代码为准。

**RED** · `test_embed_batches_at_batch_size`
- 传 70 条 text，`batch_size=32` → 断言 httpx 调 3 次（32+32+6）

**GREEN** · `_chunked(texts, batch_size)` 工具函数（如上）

**RED** · `test_embed_retries_on_5xx`
- mock 第 1 次 5xx、第 2 次 200 → 断言成功 + 调用 2 次

**GREEN** · 加 `@tenacity.retry` 装饰器（stop_after_attempt=3, wait_exponential）

**RED** · `test_embed_raises_on_dim_mismatch`（P0-3 新增）
- mock 返回 `{"embeddings": [[0.1] * 768]}`（错的 dim）
- 断言抛 `EmbeddingDimMismatch`

**RED** · `test_embedder_context_manager`（P2-5 新增）
- `async with TEIEmbedder() as e: ...` 验证 `aclose` 被调

### Task 3：Langfuse callback 工厂（P1-2 修订：双备 import 路径）

**RED** · `tests/unit/test_langfuse_callback.py::test_returns_handler_when_keys_set`
- mock env `LANGFUSE_PUBLIC_KEY=pk-test` / `LANGFUSE_SECRET_KEY=***` 调 `get_callback_handler()` → 断言返回 `CallbackHandler` 实例
- 跑测试 → 失败

**GREEN** · 实现 `app/observability/langfuse.py`（P1-2 双备 import + P0-4 sample_rate/blocked_keys）：

- import 顺序：先 `from langfuse.langchain import CallbackHandler`（2.50+ 主），失败回退 `from langfuse.callback.langchain import CallbackHandler`（旧版），两条都失败置 `CallbackHandler = None`（DoD 第 3 条降级）
- `get_callback_handler()`：env 缺 key 或 import 失败时返回 None；否则实例化 `CallbackHandler(public_key, secret_key, host, sample_rate=settings.langfuse.sample_rate, blocked_keys=settings.langfuse.blocked_keys)`

> **atexit flush**（P0-4）：M12 Hardening 加 atexit 调 `langfuse.flush()`，M3 范围内 langfuse 自身 background flush 够用（默认 5s 一次）。

**RED** · `test_returns_none_when_keys_missing`
- 删 env → 断言返回 None
- 跑测试 → 失败（当前会抛 KeyError）

**GREEN** · 加 None 兜底

**RED** · `test_callback_handler_import_paths_resolve`（P1-2 新增）
- 至少一条 import 路径能解析到 `CallbackHandler`（避免 DoD 第 4 条被 ImportError 阻塞）

### Task 4：LLM 工厂实现（P0-2 / P0-4 / P1-1 / P1-4 / P1-5 修订：注册表 + with_config + deterministic）

> **Task 拆解**（P1-6 修订）：原 Task 4 是 4-4c 合并体，约 20 分钟（5 + 10 + 5）。
> - Task 4a：`load_prompt_cfg` + mtime 热加载（5 分钟）
> - Task 4b：`make_llm` 注册表工厂 + 7 节点 + deterministic 强制（10 分钟）
> - Task 4c：callback 注入（5 分钟，受 P0-2 with_config 改写）

**RED** · `tests/unit/test_llm_factory.py::test_factory_creates_chat_anthropic`
- mock `ChatAnthropic` 构造 → 断言 `make_llm("answer")` 返回实例且 `temperature` 来自 prompt config

**GREEN** · `app/llm/factory.py`（P0-2 / P0-4 / P1-1 / P1-4 / P1-5 / P2-1 全部落入）关键约束：

- **注册表** `KNOWN_NODES = ("classify", "rewrite", "rerank", "answer", "judge", "summarize", "answer_chitchat")`（P1-5）；未知名抛 `ValueError`
- **deterministic 节点集** `_DETERMINISTIC_NODES = {"classify", "rerank", "judge"}`（P1-1）：强制 `temperature=0.0`，忽略 yaml 覆盖
- **yaml 优先**（P1-4）：`cfg.model / cfg.temperature / cfg.max_tokens` 从 yaml 读，缺省回退 `settings.llm.temperature_default/max_tokens_default`
- **超时+重试**（P0-4）：`ChatAnthropic(timeout=settings.llm.timeout, max_retries=settings.llm.max_retries)`
- **bind system_prompt**：`model.bind(system_message=cfg.system_prompt)`（langchain 1.0 bind 协议）
- **callback 注入**（P0-2 关键修复）：用 `bound.with_config({"callbacks": [handler]})` 注入，**不**写进 `model.callbacks` 字段（langchain 1.0+ 已弃用）
- **mtime 热加载**（P2-1）：`load_prompt_cfg(node)` 内部以 `(path, mtime)` 为 key 缓存 yaml，改文件自动失效
- 工厂级 `@lru_cache(maxsize=8)` 复用 7 节点实例；`_BOUND_CACHE` 给 RED 测试断言用

完整实现骨架见 review P0-2 段代码块。

**RED** · `test_factory_binds_system_prompt`（P0-1 强化：锚定 yaml 实际字符串）
- mock yaml → 断言 `make_llm("classify")` 后 invoke 时 system message 已绑定
- **强化断言**（避免假绿）：`_BOUND_CACHE["classify"].steps` 字符串里应含 `"query 意图分类器"`（锚定 §4 yaml 实际字符串）

**RED** · `test_callback_uses_with_config_not_callbacks_field`（P0-2 新增）
- 关键断言：`llm.callbacks` 为空（langchain 1.0+ 字段），callback 应在 `with_config` 注入的 config 里
- mock `get_callback_handler` → 返 `FakeHandler` → 调 `make_llm("answer")` → 验证 callback 走的是 `with_config` 协议路径

**RED** · `test_classify_and_rerank_are_deterministic`（P1-1 新增）
- 循环 `("classify", "rerank")` 断言 `llm.temperature == 0.0`
- 反向循环 `("rewrite", "answer")` 断言 `llm.temperature > 0.0`

**RED** · `test_make_llm_rejects_unknown_node`（P1-5 新增）
- `make_llm("totally_made_up_node")` 抛 `ValueError` 且 message 含 `"unknown llm node"`

### Task 5：端到端 smoke 测试（P2-6 修订：4 节点 parametrize）

**RED** · `tests/integration/test_m3_smoke.py::test_embed_then_llm_pipeline`
- 起 docker-compose（M0 已配，在 `apps/rag_v1/infra/`）→ 拿到 TEI URL + LLM env
- `TEIEmbedder().embed(["smoke test"])` → 拿 vector
- `make_llm("answer").invoke([HumanMessage("reply ok")])` → 拿 string
- 断言 vector len=1024、reply 非空、Langfuse trace 出现在 `LANGFUSE_HOST/api/traces`（GET poll 一次）

**GREEN** · 修任何失败的 assert（通常在配置 / 端口）

**RED** · `test_make_llm_smoke_for_all_nodes`（P2-6 新增，parametrize 4 节点）
- `@pytest.mark.parametrize("node", ["classify", "rewrite", "rerank", "answer"])`
- 每节点：`make_llm(node)` 非空 → `llm.invoke([HumanMessage("ping")])` 非空 content

### Task 6：yaml 守门测试（P2-2 新增）

**RED** · `tests/unit/test_prompt_yaml_guard.py::test_all_prompt_yamls_meet_minimum`
- 循环 `("classify", "rewrite", "rerank", "answer")` 4 yaml
- 断言 1：`len(prompt.split()) >= 50`（DoD 第 7 条 token 数）
- 断言 2：`"1-shot" in prompt or "示例" in prompt or "Q:" in prompt`（1-shot 关键词守门）

---

## 测试策略

- **M3 单元**：`cd apps/rag_v1 && pytest tests/unit/test_tei_embedder.py tests/unit/test_llm_factory.py tests/unit/test_langfuse_callback.py tests/unit/test_prompt_yaml_guard.py` —— 全 mock，CI 内 0.5s
- **M3 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m3_smoke.py --require-docker` —— 需 `docker compose -f infra/docker-compose.yml up -d tei langfuse postgres`，含 4 节点 parametrize
- **覆盖率门禁**：`pytest --cov=app/llm --cov=app/embedding --cov=app/observability --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 [RED]）→ GREEN（commit 标 [GREEN]）→ REFACTOR（commit 标 [RF]）

---

## 验证（Definition of Done）

- [ ] `make_llm` 在 4 个节点下都能创建实例
- [ ] `TEIEmbedder.embed` 单条 / batch / 5xx 重试 / dim 断言 / context manager 五路径全测过
- [ ] Langfuse callback 在 env 缺 key 时返回 None（不抛）
- [ ] Langfuse callback 在 env 完整时注入 LLM invoke 并能在看板看到 trace（用 `with_config` 协议）
- [ ] `tests/integration/test_m3_smoke.py` 在 `infra/docker-compose.yml up` 后 30s 内通过（4 节点 parametrize 全过）
- [ ] 单元覆盖率 ≥ 85%
- [ ] 4 个 prompt yaml 文件（classify/rewrite/rerank/answer）各 ≥ 50 token，含 1-shot 示例（**由 `test_prompt_yaml_guard.py` 强制**，P2-2）
- [ ] `.env.example` 含全部新增 env vars
- [ ] `apps/rag_v1/` 仓库布局落地（infra/app/tests 三子目录）

---

## 与其他 M 的依赖

| 上游（必须 M3 前完成） | 下游（依赖 M3） |
|----------------------|----------------|
| M0 `infra/docker-compose.yml`（TEI + Langfuse + Postgres 容器） | M7 graph 节点（用 `make_llm`，含 `answer_chitchat`） |
| M1 alembic 基础（settings 加载有依赖） | M4–M6 ingest（用 `TEIEmbedder`） |
| | M10 obs 集成（基于 M3 callback 工厂） |
| | M11 RAGAS（用 `make_llm("judge")` + `TEIEmbedder`） |

**下游联动表**（M3 范本影响，P1-5 修订后对齐）：
- **M7 graph**：M3 工厂已注册 `answer_chitchat` 节点（classify intent=chitchat 分支用），M7 节点代码直接 `make_llm("answer_chitchat")` 即可
- **M10 obs-langfuse**：M3 工厂 callback 注入已用 `with_config` 正确写法，P0-2 修订后 M10 节点层 trace 不必再补 callback
- **M11 eval-ragas**：`make_llm("judge")` 已注册，`app/prompts/judge.yaml` 占位文件已建，M11 直接实写 yaml 内容即可

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| `langchain-anthropic` 0.3+ 与 1.0.x 协议不兼容 | M0 已锁定 `==1.0.8`；CI 跑 4 节点 mock invoke 验过 | v0.3 提议"砍 langchain，LLM 直调 anthropic SDK" — 20260608_145040_7202e5 msg 193 §1.1，**已否决**（v0.3-pre msg 195 §1 收回） |
| Langfuse v2 callback path 变化 | P1-2 已加双备 import 路径（`langfuse.langchain` 主 + `langfuse.callback.langchain` 旧）；单测覆盖 | — |
| `model.callbacks` 注入 callback 不生效（langchain 1.0+ 弃用） | P0-2 已改用 `with_config({"callbacks": [handler]})` 协议 | — |
| TEI 容器冷启动 30s+ | smoke test 设 `httpx.Timeout(60.0)` | — |
| TEI 返回 dim 不匹配（768/1024 混）污染 OpenSearch kNN | P0-3 已加 `EmbeddingDimMismatch` 硬断言 + 4xx/5xx 分类 | — |
| minimax-cn API 不稳定 | P0-4 已加 `timeout=60` + `max_retries=3` + `rate_limit_rpm=60`；M3 不要求 SLA 100% | — |
| Langfuse prod 1.0 sample rate 成本爆炸 | P0-4 已加 `sample_rate=0.1` (prod) + `flush_at/flush_interval` 控制 IO | — |
| Langfuse 进程退出丢 trace | P0-4 风险表标记：M12 atexit 调 `langfuse.flush()`；M3 范围内 langfuse 自身 background flush 够用 | — |
| LLM 节点 temperature 漂移（classify/rerank 应 deterministic） | P1-1 工厂层强制 `classify/rerank/judge` temperature=0.0，忽略 yaml | — |
| 4 节点 prompt 漂移 | YAML 集中管理 + P2-1 mtime 热加载；PR review 必看 prompt diff | — |
| 4 yaml 改 1 个字丢 1-shot | P2-2 `test_prompt_yaml_guard.py` 守门 ≥ 50 token + 1-shot 关键词 | — |
| M11/M7 引用未注册节点 `make_llm("judge"/"answer_chitchat")` | P1-5 注册表化：`KNOWN_NODES` 显式列 7 节点，未知节点抛 ValueError | — |
| `LLMSettings.model` 全局 vs yaml 节点级冲突 | P1-4 修订：`model` 由 yaml 唯一来源，全局只保留 `temperature_default/max_tokens_default` 兜底 | — |
| `apps/rag_v1/` 仓库布局与 CI 路径假设冲突 | M0 plan 同步更新 README 启动步骤；CD 配 `apps/rag_v1` 为工作目录 | — |
| Task 4 估时不准（5 分钟实际 20 分钟） | P1-6 拆 4a/4b/4c 标注；下游 M 估时 +1d（M11 估时影响） | — |
| P0-1 已修：新增 §4 草稿段，4 yaml 各 ≥ 50 token + 1-shot 示例 | r1-2026-06-11 | — |
| P0-2 已修：`make_llm` 改用 `with_config({"callbacks":[handler]})` 协议 | r1-2026-06-11 | — |
| P0-3 已修：TEIEmbedder 加 `EmbeddingDimMismatch` 硬断言 + 4xx/5xx 分类 + `httpx.Timeout(60s)` + batch_size 协调 | r1-2026-06-11 | — |
| P0-4 已修：LLMSettings 补 `timeout/max_retries/rate_limit_rpm`；LangfuseSettings 补 `sample_rate/flush_at/flush_interval/blocked_keys` | r1-2026-06-11 | — |
| P1-1 已修：工厂层强制 `classify/rerank/judge` temperature=0.0，忽略 yaml 覆盖 | r1-2026-06-11 | — |
| P1-2 已修：langfuse import 加双备路径（`langfuse.langchain` + `langfuse.callback.langchain`） | r1-2026-06-11 | — |
| P1-3 已修：pyproject dev 依赖补 `pytest-httpx>=0.30,<1` + `pytest-cov>=5.0,<7` | r1-2026-06-11 | — |
| P1-4 已修：`LLMSettings.model` 改 `temperature_default/max_tokens_default` 兜底；yaml `model` 字段为唯一来源 | r1-2026-06-11 | — |
| P1-5 已修：工厂改注册表 `KNOWN_NODES = (classify, rewrite, rerank, answer, judge, summarize, answer_chitchat)`；Files 表加 judge/summarize/answer_chitchat.yaml 占位 | r1-2026-06-11 | — |
| P1-6 已修：Task 4 拆 4a/4b/4c（约 20 分钟），下游 M 估时 +1d 通知 | r1-2026-06-11 | — |
| P2-1 已修：`load_prompt_cfg` 加 mtime cache key 热加载 | r1-2026-06-11 | — |
| P2-2 已修：新增 `tests/unit/test_prompt_yaml_guard.py` 守门 ≥ 50 token + 1-shot | r1-2026-06-11 | — |
| P2-3 已修：pyproject 补 `pyyaml>=6.0,<7` 直接依赖 | r1-2026-06-11 | — |
| P2-4 已修：估时改"2 个工作日（Tasks ~6h + 调试 ~6h + 文档 ~4h）" | r1-2026-06-11 | — |
| P2-5 已修：`TEIEmbedder` 加 `__aenter__/__aexit__/aclose` 协议 | r1-2026-06-11 | — |
| P2-6 已修：集成测试加 `test_make_llm_smoke_for_all_nodes` 4 节点 parametrize | r1-2026-06-11 | — |

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M3-plan-r0 | 2026-06-10 | 初稿（基线 V1 Scope §8 决策 #8/#9/#10） |
| M3-plan-r1 | 2026-06-10 | 仓库布局调整为 `apps/rag_v1/{infra,app,tests}/` |
| r1-2026-06-11 | 2026-06-11 | P0-1 已修 · 新增 §4 草稿段（classify/rewrite/rerank/answer 4 yaml ≥ 50 token + 1-shot） |
| r1-2026-06-11 | 2026-06-11 | P0-2 已修 · `make_llm` 改用 `with_config({"callbacks":[handler]})` 协议，避开 langchain 1.0+ 弃用 `model.callbacks` 字段 |
| r1-2026-06-11 | 2026-06-11 | P0-3 已修 · TEIEmbedder 加 `EmbeddingDimMismatch` 硬断言 + 4xx/5xx 分类 + `httpx.Timeout(60s)` + `batch_size=32` 协调 + normalize/truncate 语义明确 |
| r1-2026-06-11 | 2026-06-11 | P0-4 已修 · LLMSettings 补 `timeout/max_retries/rate_limit_rpm`；LangfuseSettings 补 `sample_rate/flush_at/flush_interval/blocked_keys`；atexit flush 风险表标 M12 |
| r1-2026-06-11 | 2026-06-11 | P1-1 已修 · 工厂层强制 `classify/rerank/judge` temperature=0.0，忽略 yaml 覆盖 |
| r1-2026-06-11 | 2026-06-11 | P1-2 已修 · langfuse import 加双备路径（`langfuse.langchain` + `langfuse.callback.langchain`） |
| r1-2026-06-11 | 2026-06-11 | P1-3 已修 · pyproject dev 依赖补 `pytest-httpx>=0.30,<1` + `pytest-cov>=5.0,<7` |
| r1-2026-06-11 | 2026-06-11 | P1-4 已修 · `LLMSettings.model` 改 `temperature_default/max_tokens_default` 兜底；yaml `model` 字段为唯一来源 |
| r1-2026-06-11 | 2026-06-11 | P1-5 已修 · 工厂改注册表 `KNOWN_NODES = (classify, rewrite, rerank, answer, judge, summarize, answer_chitchat)`；Files 表加 `judge.yaml`/`summarize.yaml`/`answer_chitchat.yaml` 占位 |
| r1-2026-06-11 | 2026-06-11 | P1-6 已修 · Task 4 拆 4a/4b/4c（约 20 分钟），下游 M 估时 +1d 通知 |
| r1-2026-06-11 | 2026-06-11 | P2-1 已修 · `load_prompt_cfg` 加 mtime cache key 热加载 |
| r1-2026-06-11 | 2026-06-11 | P2-2 已修 · 新增 `tests/unit/test_prompt_yaml_guard.py` 守门 ≥ 50 token + 1-shot |
| r1-2026-06-11 | 2026-06-11 | P2-3 已修 · pyproject 补 `pyyaml>=6.0,<7` 直接依赖 |
| r1-2026-06-11 | 2026-06-11 | P2-4 已修 · 估时改"2 个工作日（Tasks ~6h + 调试 ~6h + 文档 ~4h）" |
| r1-2026-06-11 | 2026-06-11 | P2-5 已修 · `TEIEmbedder` 加 `__aenter__/__aexit__/aclose` 协议 |
| r1-2026-06-11 | 2026-06-11 | P2-6 已修 · 集成测试加 `test_make_llm_smoke_for_all_nodes` 4 节点 parametrize |
| r1-2026-06-11 | 2026-06-11 | 范本影响 · M7 已知 `make_llm("answer_chitchat")` 可用；M10 已知 callback 已 `with_config`；M11 已知 `make_llm("judge")` + `judge.yaml` 占位已就位 |
| r2-2026-06-11 | 2026-06-11 | **M3 r2 修复** · Tech Stack 加 `Embedding 端口 18080:80` 行（host→容器映射，避免 8080/8081 冲突） |
| r2-2026-06-11 | 2026-06-11 | **M3 r2 修复** · 头部加「r2-2026-06-11 范本影响通知」段（明示 M7/M10/M11 已收 make_llm 7 节点 + judge 节点 + callback 工厂） |
