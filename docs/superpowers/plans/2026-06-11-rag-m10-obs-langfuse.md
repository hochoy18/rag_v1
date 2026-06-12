# M10 Plan · Langfuse 业务级 Trace 集成（节点级 + PII 脱敏 + Token 追踪）

> 所属：RAG V1 M0–M12 实施路线 · 第 10 步
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §1 观测双轨](../specs/2026-06-10-rag-v1-scope.md#1-架构总览) · [§5 错误矩阵 LLM 4xx/5xx→Langfuse trace+502](../specs/2026-06-10-rag-v1-scope.md#5-错误矩阵) · [§8.6 依赖 langfuse>=2.50 / OTEL](../specs/2026-06-10-rag-v1-scope.md#8-依赖版本清单) · [决策 #10/#11](../specs/2026-06-10-rag-v1-scope.md#0-决策总表)
> 上游：[M3 LLM 工厂 + Langfuse callback 工厂](./2026-06-10-rag-m3-llm-embed.md)（`get_callback_handler` + `@trace` 已建）· [M7 LangGraph 8 节点](./2026-06-10-rag-m7-graph.md)（7 业务节点 + `answer_chitchat_node`，含 `(state, config)` 双参签名的 `load_memory_node` / `save_memory_node`）· [M8 FastAPI `/api/chat` X-Request-Id 透传 + 30s chat timeout](./2026-06-11-rag-m8-api-chat.md)（middleware + `asyncio.wait_for` 已建）· [M9 Gradio UI](./) 计划（trace_id 链接到 Langfuse 看板）
> 下游：M11 RAGAS 离线 eval（不直接调 M10，但 trace_id 可作 RAGAS input 关联字段）· M12 Hardening（限速 / 备份 / Sentry 都基于 M10 观测基线）
> 避雷基线：[P0/P1 review 报告](./2026-06-11-rag-plans-review.md)（P0-1 端口冲突·Langfuse 3000 端口 / P0-5 集成测试用真 PG（checkpointer 写 trace_id 关联）/ P1-12 langfuse import 路径双备 / P1-14 `with_config({"callbacks":[handler]})` 替代 `model.callbacks` / X-3 `from app.config import settings` 全局单例）· [M10 review 2026-06-11](./reviews/2026-06-11-rag-m10-obs-langfuse-review.md)（新发现 5 P0 + 14 P1 + 10 P2，本 r1 全部修复）
> 估时：2 个工作日
> 范本目的：把 Langfuse 从"M3 工厂注入 LLM callback"升级到"业务级 trace 覆盖 7 节点 + ingest pipeline + 错误 + PII 脱敏 + token 成本"——M11 RAGAS / M12 Hardening 都依赖此观测基线

---

## Goal

把 v0.4 V1 Scope §1 观测双轨中的 **Langfuse 在线 trace** 落到生产可观测级别，5 个交付目标：

1. **节点级 trace 装饰器** `app/observability/node_tracing.py` 的 `@node_trace(node_name)` 包装 LangGraph 8 节点函数（7 业务节点 + `answer_chitchat_node`）→ 每次 invoke 在 Langfuse 看板看到 8 个 nested span（装饰器内部用 `langfuse_context.update_current_observation` 打 span，**不再**误用 langchain 协议 `on_chain_*`）
2. **Session/user 注入** `app/observability/session_tracker.py` 把 `state["user_id"]` / `state["thread_id"]` 写入 Langfuse trace metadata + `session_id` / `user_id` 顶层字段
3. **Graph 8 节点全装饰**：`app/graph/nodes.py` 的 `load_memory_node / classify / query_rewrite / retrieve / rerank / answer / save_memory_node / answer_chitchat_node` 全部加 `@node_trace`（**装饰器自动识别 `(state)` 单参 / `(state, config)` 双参签名**，P0-1 修复）
4. **Ingest pipeline trace**：`app/ingest/pipeline.py` 的 `run_ingest` 加 `@node_trace("ingest.{kind}")` → M4-M6 ingest 在 Langfuse 看板也可观测
5. **X-Request-Id 透传 + PII 脱敏 + Token 追踪 + 错误 trace + 降级短路 + 429 retry + 节点 usage/cost 汇总 + 集成测试 e2e GET `/api/public/traces/{id}` 验证**——10 项一次性收口

**不包含**（其他 M 负责）：
- M11 RAGAS 离线 golden set eval（独立 CLI，决策 #11）
- M12 Sentry / 限速 / 备份（基于 M10 观测基线做告警）
- OpenTelemetry exporter 启用（spec §8.6 列了依赖但 M10 阶段不外发；**`OpenTelemetryInstrumentor().instrument()` 在 lifespan 启动时默认启用 auto-instrumentation**，P1-12 修复，exporter 配置推迟到 M12）
- Gradio UI 上点击 trace_id 跳 Langfuse（M9 计划实现，本 plan 只产 `trace_id` 字段）
- user feedback UI 按钮 + endpoint（M9 计划；M10 只预留 `langfuse.score` 接入路径，P1-10 建议）
- Langfuse trace 归档到 S3（M12 Hardening；M10 仅设 `trace_retention_days` 字段，P1-9 修复）

---

## Architecture

### 仓库布局（M10 增量）

```
apps/rag_v1/
├── app/
│   ├── observability/                       # M3 已有 + M10 扩展
│   │   ├── __init__.py                      # 最小暴露 node_trace / mask_pii / build_session_metadata / flush / get_current_trace_id
│   │   ├── langfuse.py                      # M3 已有 · get_callback_handler() 单例
│   │   ├── tracing.py                       # M3 已有 · @trace 通用装饰器
│   │   ├── node_tracing.py                  # M10 新建 · @node_trace(node_name) LangGraph 节点专用（用 langfuse_context.update_current_observation）
│   │   ├── session_tracker.py               # M10 新建 · build_session_metadata(state, request_id) → metadata dict；async flush() 调 get_client().flush()
│   │   ├── pii.py                           # M10 新建 · mask_pii(obj) 递归脱敏 password/token/api_key/email/手机/IP/Bearer...
│   │   └── config.py                        # M10 新建 · ObservabilitySettings（sample_rate / mask_keys / trace_env / flush_timeout_s / langfuse_offline_mode / trace_call_timeout_s / trace_retention_days / archive_to_s3 / prompt_source / trace_pii_redaction_strict）
│   ├── graph/                               # M7 已建 · M10 改 8 节点
│   │   └── nodes.py                         # 8 节点函数加 @node_trace(node_name)（load_memory_node / save_memory_node 双参签名）
│   ├── ingest/                              # M4-M6 已建 · M10 加 trace
│   │   └── pipeline.py                      # run_ingest 顶层加 @node_trace("ingest.{kind}")  # kind ∈ {file, url, confluence}
│   ├── api/                                 # M8 已建 · M10 改 chat 路由
│   │   └── chat.py                          # graph.ainvoke config.metadata.request_id + await flush() + ChatResponse.trace_id 来自 get_current_trace_id()
│   ├── llm/                                 # M3 已建 · 工厂注入方式不变（P1-14 已用 with_config）
│   │   └── factory.py                       # 无修改（P1-14 M3 修订后已正确）
│   └── config.py                            # M0+M1+M2+M3+M7 累计 · 追加 ObservabilitySettings
│
└── tests/
    ├── unit/
    │   ├── test_node_tracing.py             # M10 · @node_trace 单参/双参签名 + metadata 注入 + 错误捕获 + flush + Langfuse 不可达降级 + 性能 docstring
    │   ├── test_session_tracker.py          # M10 · metadata 字段注入 + PII 过滤 + flush 用 get_client().flush()
    │   ├── test_pii.py                      # M10 · mask_pii 递归脱敏 + email/手机号/IP/Bearer 兜底
    │   ├── test_handler_pool.py             # M10 · HandlerPool 单例（仅 LLM 级，节点级走 langfuse_context）
    │   └── test_trace_id_propagation.py     # M10 · X-Request-Id 透传 + config["metadata"]["request_id"] 路径 + ChatResponse.trace_id max_length=64
    └── integration/
        ├── conftest.py                      # M10 增补 · 真 Langfuse 容器 fixture（修 P0-5 / P0-1 端口）
        └── test_m10_e2e_trace.py            # 端到端：chat → await flush() → GET /api/public/traces/{id} 看到 8 节点 + node_usage
```

### 模块树（M10 增量）

```
apps/rag_v1/
├── app/observability/
│   ├── node_tracing.py        @node_trace(node_name) — inspect.signature 自动识别 (state) / (state, config)；用 langfuse_context.update_current_observation 打 span
│   ├── session_tracker.py     build_session_metadata(state, request_id) — 抽取 user_id/thread_id/request_id；async flush() 调 get_client().flush()
│   ├── pii.py                 mask_pii(obj) — 递归 dict/list/str 脱敏 + 兜底正则 (email/手机号/IP/Bearer/password/token/api_key/secret)
│   └── config.py              ObservabilitySettings — sample_rate / mask_keys / trace_env / flush_timeout_s / langfuse_offline_mode / trace_call_timeout_s / trace_retention_days / archive_to_s3 / prompt_source / trace_pii_redaction_strict
```

### 节点 trace 数据流（8 节点 LangGraph invoke）

```
client POST /api/chat
  │
  ▼
M8 middleware: X-Request-Id 注入（缺则 uuid4）
  │
  ▼
M8 chat.py: graph.ainvoke(state,
  config={
    "configurable": {"thread_id": thread_id},
    "metadata": {"request_id": X-Request-Id, "user_id": ...}
  })
  │
  ▼
M10 @node_trace("load_memory_node")    ─┐
  │  ├─ inspect.signature 自动识别 (state, config) 双参 → 取 config["configurable"]["thread_id"]
  │  ├─ session_tracker.build_session_metadata(state, request_id) → metadata
  │  ├─ mask_pii(metadata)            # password / token / api_key / email / 手机 / IP 替换为 "***"
  │  ├─ langfuse_context.update_current_observation(name="load_memory_node", metadata=metadata)  # 创建 span
  │  ├─ should_trace() (sample_rate 短路) → 0.0 时直接 return fn()
  │  ├─ _safe_trace_update() (offline_mode / 1.0s timeout 短路)
  │  ├─ try: original_node(state, config)
  │  ├─ except Exception as e:
  │  │     langfuse_context.update_current_observation(level="ERROR", status_message=f"{type(e).__name__}: {str(e)[:200]}")
  │  │     raise
  │  └─ # 节点结束汇总 child LLM spans usage → node_usage.input_tokens/output_tokens/cost_usd
  │
  ▼ (M10 同样包装 7 节点：classify / query_rewrite / retrieve / rerank / answer / save_memory_node / answer_chitchat_node)
  │
  ▼
M10 @node_trace("ingest.{kind}")    # M4-M6 pipeline 入口，外部调
  │
  ▼
M10 session_tracker.async flush()   # chat 退出前 await flush() 显式 flush（get_client().flush()），避 P1-7 trace 未落库
```

### M10 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M7 graph 节点（8 个） | `@node_trace("classify")` 装饰节点函数 | 装饰器自动适配 `(state)` / `(state, config)` 双签名（P0-1 修复）；节点命名 `load_memory_node` / `save_memory_node` 带 `_node` 后缀（P0-4 修复） |
| M8 chat 路由 | `state["metadata"]["request_id"]` → 灌入 graph `config.metadata.request_id`（不在 state dict 里，state 是业务字段；P2-6 澄清） | M8 已建 middleware，M10 不用加 |
| M8 chat 路由（exit） | `await session_tracker.flush()` + `get_current_trace_id()` → 填到 `ChatResponse.trace_id: str \| None = Field(max_length=64)`（P1-14 修复） | trace_id 取法 `from langfuse import get_client; get_client().get_current_trace_id()`（P0-3 修复）· **r2 2026-06-12 新-1 同步**：M8 实际 `ChatResponse.request_id` 字段与 M10 期望 `trace_id` **命名不一致**；M8 r2 P1-1 修订时同步改 `request_id` → `trace_id`（M8 内部 state 名仍叫 `request_id`，仅 API 响应字段名改 `trace_id`） |
| M9 Gradio | `ChatResponse.trace_id` 字段（**M10 在 ChatResponse schema 加字段**，M9 渲染链接） | 见 M9 计划·**r2 2026-06-12 新-1 同步**：M9 plan L7/L85/L105/L531 全部统一为 `trace_id`（M9 r2 漂-2 必改） |
| M9 feedback UI（r2 2026-06-12 新-2 跨 M 联动） | `gr.Button("👍/👎").click(_handle_feedback, [trace_id_state, gr.State(1\|0)], [])` → 调 `POST {API_BASE}/api/feedback {trace_id, value, comment?}` | M10 端点接收 → 调 `record_feedback(trace_id, value, comment)` → 调 `langfuse.score(trace_id, name="user_feedback", value, comment)` |
| M4-M6 ingest | `@node_trace("ingest.file"\|"ingest.url"\|"ingest.confluence")` 装饰 `run_ingest` | pipeline 入口 |
| M11 RAGAS | `trace_id` 作 RAGAS input 关联字段（不直接调 M10） | 离线独立跑 |
| M12 Hardening | 读 `LangfuseSettings.sample_rate` / `langfuse_offline_mode` / `trace_retention_days` 决定是否采样 / 降级 / 保留 | 限速 / Sentry 基于此 |
| M3 LLM 工厂 | `get_callback_handler(sample_rate=settings.observability.sample_rate)`（**M10 修订** M3 P0-4 阻塞 2） | 客户端侧 sample_rate 才真正生效 |

---

## Tech Stack

| 层 | 选型 | 版本（精确） | 来源 |
|----|------|------------|------|
| 观测 | `langfuse` | `>=2.50,<3` | V1 Scope §8.6（决策 #10） |
| OTEL API | `opentelemetry-api` | `>=1.27,<2` | V1 Scope §8.6 |
| OTEL SDK | `opentelemetry-sdk` | `>=1.27,<2` | V1 Scope §8.6 |
| OTEL Instrumentor | `opentelemetry-instrumentation-langchain` | `>=0.40b0,<1` | P1-12 修复：默认启用 auto-instrumentation（**仅 instrument，不配 exporter**） |
| LangChain | `langchain` | `==1.0.8` | M3 |
| LangGraph | `langgraph` | `==1.0.5` | M7 |
| 重试 | `tenacity` | `>=8.2,<9` | P1-13 修复：Langfuse 429 retry with exponential backoff |
| 配置 | `pydantic-settings` | `>=2.3,<3` | M0 沿用 |
| 测试 | `pytest` / `pytest-asyncio` / `pytest-httpx` | 见 §测试 | M3 沿用 |
| 测试容器 | `testcontainers[langfuse]`（**可选**） | `>=4.8,<5` | M10 集成测试备选 |

**关键导入路径**（langfuse 2.50+，修 P1-12 双备 + P0-2 flush 改路径）：

```python
# 主路径（langfuse 2.50+ 推荐，P0-2 修复）
from langfuse import get_client, Langfuse  # get_client() 用于 flush() / get_current_trace_id()

# CallbackHandler 主路径（M3 已用，P1-12 验证通过）
try:
    from langfuse.langchain import CallbackHandler
except ImportError:
    from langfuse.callback.langchain import CallbackHandler

# 节点级 trace（M10 新增，P0-5 修复：不再误用 langchain 协议 on_chain_*）
from langfuse import langfuse_context  # 用于 update_current_observation / update_current_span
# 注：langfuse_context.flush() 在 2.50+ 不存在；改用 get_client().flush()
```

**Python 导入规则**（M10 沿用 M3 风格）：
- `app.observability.node_tracing` —— `app` 是 `apps/rag_v1/app/`
- `tests.unit.test_node_tracing` —— 跑测试时 `cd apps/rag_v1 && pytest`

**M10 特有避雷**：
- **P0-1 端口**：集成测试连 Langfuse API 用 `http://localhost:3000`（M0 docker-compose 已配，`depends_on: condition: service_healthy` P0-3 已修）
- **P0-5 真 PG**：集成测试 `test_m10_e2e_trace.py` 用真 Postgres（checkpointer 写 `trace_id` 到 `auth_sessions` 关联），禁用 sqlite 假绿
- **P1-12 双 import 路径**：M10 测 `test_langfuse_import_fallback` 验证主路径失败时备路径可用
- **P1-14 callback 注入方式**：M3 工厂已修订为 `with_config({"callbacks":[handler]})`，M10 不用再改
- **P0-1 装饰器双签名**：`inspect.signature(fn)` 自动识别 `(state)` / `(state, config)`，**不再写死 `args[0]`**
- **P0-2 flush 路径**：`from langfuse import get_client; get_client().flush()`，**不再用 `langfuse_context.flush()`**
- **P0-3 trace_id 取法**：`get_client().get_current_trace_id()`，**不再用 `handler.get_trace_id()`**
- **P0-5 装饰器机制**：用 `langfuse_context.update_current_observation`，**不再调 `handler.on_chain_*`**
- **X-3 settings 单例**：`from app.config import settings`，M10 不在测试里 `Settings()` 实例化

---

## Files

**新增**（6 个源文件 + 5 个测试文件 + 1 个 env 模板）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
| `app/observability/node_tracing.py` | `@node_trace(node_name)` 装饰器：`inspect.signature` 自动识别双签名 + `langfuse_context.update_current_observation` 打 span + 节点 usage/cost 汇总 + 性能 docstring |
| `app/observability/session_tracker.py` | `build_session_metadata(state, request_id)` → dict；`async flush()` 显式 flush 调 `get_client().flush()` |
| `app/observability/pii.py` | `mask_pii(obj)` 递归脱敏；`DEFAULT_MASK_KEYS` 常量；`PII_VALUE_RE` 兜底正则（含 email/手机号/IP/Bearer） |
| `app/observability/handler_pool.py` | `HandlerPool` 单例：**(user_id, thread_id)** 维度复用 CallbackHandler（仅服务于 LLM 级；P1-5 建议方案 B 保留） |
| `app/observability/config.py` | `ObservabilitySettings`：sample_rate / mask_keys / trace_env / flush_timeout_s / langfuse_offline_mode / trace_call_timeout_s / trace_retention_days / archive_to_s3 / prompt_source / trace_pii_redaction_strict |
| `app/observability/__init__.py` | **最小暴露**：`node_trace` / `mask_pii` / `build_session_metadata` / `flush` / `get_current_trace_id`（**不**暴露 `HandlerPool` / `ObservabilitySettings`，走单例） |
| `tests/unit/test_node_tracing.py` | 装饰器：单参/双参签名（P0-1）/ metadata 注入（P1-1）/ 错误捕获 / flush / Langfuse 不可达降级（P1-4）/ 节点 usage 汇总（P1-3）/ 性能 docstring |
| `tests/unit/test_session_tracker.py` | metadata 字段抽取 / PII 过滤 / 缺字段兜底 / flush 调 `get_client().flush()`（P0-2）|
| `tests/unit/test_pii.py` | 递归脱敏 / 嵌套 dict / list / str 子串 / 边界 None / **email + 手机号 + IP + Bearer**（P1-8） |
| `tests/unit/test_handler_pool.py` | acquire 复用 / release 归还 / 跨请求不串扰 / 注解"仅 LLM 级"（P1-5） |
| `tests/unit/test_trace_id_propagation.py` | X-Request-Id 透传 / 缺 header 兜底 / 注入 `graph config["metadata"]` 而非 `state.metadata`（P2-6 澄清）/ ChatResponse.trace_id max_length=64（P1-14）|
| `tests/integration/conftest.py` | 增补 `langfuse_client` / `live_langfuse` / `live_pg` fixture |
| `tests/integration/test_m10_e2e_trace.py` | e2e：chat → `await flush()` → GET `/api/public/traces/{id}` 看到 8 节点 + node_usage |
| `.env.example` | **完整段**：`LANGFUSE_SAMPLE_RATE` / `LANGFUSE_MASK_KEYS` / `LANGFUSE_TRACE_ENV` / `LANGFUSE_FLUSH_TIMEOUT_S` / `LANGFUSE_OFFLINE_MODE` / `LANGFUSE_TRACE_RETENTION_DAYS` / `LANGFUSE_PROMPT_SOURCE`（P2-2 修复） |

**修改**：
- `app/config.py`：追加 `ObservabilitySettings`（含 9 字段，P1-9 / P1-11 / P1-4 修复）
| `app/graph/nodes.py`（M7 已建）：**8** 节点函数加 `@node_trace("load_memory_node")` 等装饰器（**仅 import + 1 行装饰器**；P0-4 修复——节点名带 `_node` 后缀的实际命名）。**r2 2026-06-12 消化 M7 r2 新-2 save_memory 双节点**：`save_memory_node` 拆为 `save_memory_rag` + `save_memory_chitchat` 双 key，装饰器分别 `@node_trace(name="save_memory_rag")` + `@node_trace(name="save_memory_chitchat")` |
- `app/ingest/pipeline.py`（M4-M6 已建）：`run_ingest` 入口加 `@node_trace("ingest.{kind}")`（M10 只改入口装饰，内部各 step 由 M4-M6 自决）
- `app/api/chat.py`（M8 已建）：`graph.ainvoke(..., config={"metadata": {"request_id": request.state.request_id}})` + `await flush()` 在返回前 + 取 `get_current_trace_id()` 填 response
- `app/api/schemas/chat.py`（M8 已建）：`ChatResponse` 加 `trace_id: str | None = Field(default=None, max_length=64)`（P1-14 修复）
- `app/llm/factory.py`（M3 已建）：**最小修改**——`get_callback_handler` 接收 `sample_rate` 参数，注入到 `CallbackHandler(sample_rate=...)`（**M10 修订 M3 P0-4 阻塞 2**）
- `pyproject.toml`：追加 `testcontainers[langfuse] >=4.8,<5` / `tenacity >=8.2,<9` / `opentelemetry-instrumentation-langchain >=0.40b0,<1` 到 dev 依赖
- `app/main.py`（M0 已建）：lifespan 启动时调 `OpenTelemetryInstrumentor().instrument()`（P1-12 修复——**仅 instrument，不配 exporter**）

**不修改**：
- `infra/docker-compose.yml`（Langfuse 3000 端口 P0-1 已修；`depends_on` healthcheck P0-3 已修）
- `app/observability/langfuse.py`（M3 `get_callback_handler` 工厂继续被 M10 复用，**仅追加 sample_rate 参数**）
- `app/observability/tracing.py`（M3 通用 `@trace` 装饰器，M10 不重写，新写 `@node_trace` 是 LangGraph 专用版；P2-3 暂保留两文件，标注差异注释）

---

## Tasks（2-5 分钟/step 粒度）

### Task 1：ObservabilitySettings 配置块

**RED** · `tests/unit/test_config.py::test_observability_settings_loads`（**追加**，不破坏 M3 测试）
- 写测试：mock env `LANGFUSE_SAMPLE_RATE=0.1` / `LANGFUSE_MASK_KEYS=password,token,api_key` / `LANGFUSE_TRACE_ENV=staging` / `LANGFUSE_FLUSH_TIMEOUT_S=1.0` / `LANGFUSE_OFFLINE_MODE=true` → 加载 `settings.observability` → 断言 9 字段正确
- 跑测试 → 失败（配置不存在）
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_config.py::test_observability_settings_loads`

**GREEN** · 改 `app/config.py`：
- 新增 `ObservabilitySettings`（**9 字段**，含 P1-4 降级 / P1-9 保留 / P1-11 prompt 来源 / P2-1 flush_timeout=1.0）：
  - `sample_rate: float = 1.0`  # P1-2 风险：dev=1.0 / staging=0.5（建议）/ prod=0.1
  - `mask_keys: set[str] = {"password", "token", "api_key", "secret", "authorization", "session_token"}`  # P1-1：默认黑名单
  - `trace_env: str = "dev"`  # dev / staging / prod
  - `flush_timeout_s: float = 1.0`  # **P2-1 修复**：从 5.0 改 1.0（M8 chat 30s timeout，5s flush 占 17% 太多）
  - `langfuse_offline_mode: bool = False`  # **P1-4 新增**：True 时所有 Langfuse 调用短路
  - `trace_call_timeout_s: float = 1.0`  # **P1-4 新增**：单次 context update 超时
  - `trace_retention_days: int = 30`  # **P1-9 新增**：M10 仅设字段，清理脚本 M12 实现
  - `archive_to_s3: bool = False`  # **P1-9 新增**：V1 不实现
  - `prompt_source: str = "yaml"`  # **P1-11 新增**：V1=yaml，V1.1 可改 `langfuse`
  - `trace_pii_redaction_strict: bool = True`  # **P1-9 新增**：严格模式额外脱敏
- 顶层 `Settings` 聚合（X-3：保留 `from app.config import settings` 单例）

**RED** · `test_observability_settings_defaults`
- 不设 env → 断言 9 字段默认值（`sample_rate == 1.0` / `mask_keys` 包含 `password` / `flush_timeout_s == 1.0` / `langfuse_offline_mode == False` 等）

**GREEN** · 补默认值

**REFACTOR** · 把 `ObservabilitySettings` 抽到 `app/observability/config.py` 独立文件（X-1 风险：M0 时已决定 `app/config.py` 暂不拆分，**本 M10 沿用**——见风险）

### Task 2：PII 脱敏工具（**P1-8 扩展**）

**RED** · `tests/unit/test_pii.py::test_mask_pii_top_level_keys`
- 测 `mask_pii({"password": "***", "username": "alice"})` → `{"password": "***", "username": "alice"}`
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_pii.py::test_mask_pii_top_level_keys`

**GREEN** · 实现 `app/observability/pii.py`：
- `DEFAULT_MASK_KEYS = {"password", "token", "api_key", "secret", "authorization", "session_token"}`
- `PII_VALUE_RE = re.compile(r"(?i)(password|token|api_key|secret)[\"']?\s*[:=]\s*[\"']?([^\s\"',}]+)")`  # 兜底：值里也扫
- `def mask_pii(obj, mask_keys: set[str] | None = None) -> Any`：递归 dict/list/str
  - dict：key（lower）in mask_keys → value 替换 `"***"`
  - str：跑 `PII_VALUE_RE.sub` 替换
  - list：逐元素递归
  - 其它类型（int/float/None/bool）：原样返回
- 用 `from app.config import settings` 读 `mask_keys`（X-3 单例）

**RED** · `test_mask_pii_nested_dict`
- 测 `mask_pii({"user": {"password": "***", "name": "alice"}})` → 嵌套也脱敏

**GREEN** · 加递归

**RED** · `test_mask_pii_list_of_dicts`
- 测 `mask_pii([{"token": "***"}, {"safe": "ok"}])` → 列表里 dict 也脱敏

**GREEN** · list 分支

**RED** · `test_mask_pii_passthrough_non_string_keys`
- 测 `mask_pii({1: "password=***"})` → 整数 key 原样；值里子串仍脱敏

**GREEN** · 加类型分支

**RED** · `test_mask_pii_handles_email_and_ip`（**P1-8 新增**）
- 测 `mask_pii({"contact": "user@example.com"})` → `{"contact": "***"}`
- 测 `mask_pii({"client_ip": "192.168.1.1"})` → `{"client_ip": "***"}`
- 测 `mask_pii({"phone": "13800138000"})` → `{"phone": "***"}`
- 测 `mask_pii({"auth": "Bearer eyJhbG...VCJ9..."})` → 开头 "Bearer ***"

**GREEN** · **P1-8 修复**：扩展 `PII_VALUE_RE`：
```python
PII_VALUE_RE = re.compile(
    r"(?i)"
    r"(password|token|api_key|secret)[\"'\u201d]?\s*[:=]\s*[\"'\u201d]?([^\s\"',}]+)"
    r"|"
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"  # email
    r"|"
    r"\b1[3-9]\d{9}\b"  # 中国手机号
    r"|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b"  # IPv4
    r"|"
    r"\b[Bb]earer\s+[A-Za-z0-9._-]{20,}\b"  # Bearer token
)
```

**REFACTOR** · 抽 `_mask_value(v: str) -> str` 工具；加 docstring

### Task 3：Session metadata 构建器

**RED** · `tests/unit/test_session_tracker.py::test_build_session_metadata_extracts_fields`
- 测 `build_session_metadata(state={"user_id": "u1", "thread_id": "t1", "query": "hi"}, request_id="req-123")` → `{"user_id": "u1", "thread_id": "t1", "request_id": "req-123", "intent": None, "query_length": 2}`
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_session_tracker.py::test_build_session_metadata_extracts_fields`

**GREEN** · 实现 `app/observability/session_tracker.py`：
- `def build_session_metadata(state: dict, request_id: str | None = None) -> dict`：
  - 抽 `user_id = state.get("user_id")` / `thread_id = state.get("thread_id")` / `intent = state.get("intent")`
  - `query_length = len(state.get("query", ""))` （不存原 query 防泄漏）
  - 抽 `request_id`（可空）
  - 返回 `{"user_id", "thread_id", "intent", "query_length", "request_id", "prompt_source": settings.observability.prompt_source}`（**P1-11 修复**）
- 调 `mask_pii()` 包一层（P1-1：必须用工具函数，不写散落 regex）

**RED** · `test_build_session_metadata_masks_password_in_state`
- 测 `state={"user_id": "u1", "password": "***"}` → 输出**不含** `"password": "***"`（被 mask_pii 过滤掉）

**GREEN** · 调 `mask_pii()` 后再返回

**RED** · `test_build_session_metadata_handles_missing_fields`
- 测 `state={}` → 输出 `{"user_id": None, "thread_id": None, ...}` 不抛 KeyError

**GREEN** · `.get()` 兜底

**RED** · `test_flush_calls_langfuse_client_flush`（**P0-2 修复**——从 `langfuse_context.flush` 改 `get_client().flush`）
```python
def test_flush_calls_client_flush(monkeypatch):
    from app.observability.session_tracker import flush
    from langfuse import get_client
    from unittest.mock import MagicMock
    fake_client = MagicMock()
    monkeypatch.setattr("app.observability.session_tracker.get_client", lambda: fake_client)
    # async flush
    import asyncio
    asyncio.run(flush())
    fake_client.flush.assert_called_once()
```

**GREEN** · 实现 `async flush()`（**P0-2 修复**）：
```python
async def flush() -> None:
    """显式 flush 当前 trace 到 Langfuse。注：langfuse 2.50+ 公开 API 是 get_client().flush()。"""
    try:
        from langfuse import get_client
        client = get_client()
        # 不 await langfuse 2.50+ 的 client.flush()（同步）；保留 async 签名以备 3.x 演进
        client.flush()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("langfuse flush failed: %s", e)
```

**REFACTOR** · 把 `flush()` 内部加 try/except 防 flush 失败污染主流程；封装到 context manager `with flush_context()`

### Task 4：HandlerPool 单例（**P1-5 澄清：仅 LLM 级**）

**RED** · `tests/unit/test_handler_pool.py::test_handler_pool_reuses_per_thread`
- 测 `HandlerPool().acquire("u1", "t1")` 调 2 次 → 返同 1 个 handler
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_handler_pool.py::test_handler_pool_reuses_per_thread`

**GREEN** · 实现 `app/observability/handler_pool.py`（**P1-5 修复——加模块 docstring 澄清"仅服务 LLM 级，节点级走 langfuse_context"**）：
```python
"""
HandlerPool: 复用 Langfuse CallbackHandler 实例。

⚠️ P1-5 澄清（来自 M10 review）：
- 本 HandlerPool **仅服务于 LLM 节点**（M3 工厂 make_llm().with_config({"callbacks":[handler]}) 路径）
- 节点级 trace 走 langfuse_context.update_current_observation（无需 handler 实例）
- 两者不冲突：LLM callback 自动 emit LLM span；节点 callback 写业务 metadata 到当前 observation
"""
```
- `class HandlerPool`：
  - `__init__(self)`：self._pool = {}（key = `(user_id, thread_id)`, value = `CallbackHandler`）
  - `def acquire(self, user_id: str | None, thread_id: str) -> CallbackHandler`：
    - key = `(user_id, thread_id)`
    - if key in pool: return pool[key]
    - else: handler = get_callback_handler(sample_rate=settings.observability.sample_rate)  # M3 工厂；缺 env 返 None
          if handler: pool[key] = handler
          return handler
  - `def release(self, user_id: str | None, thread_id: str) -> None`：
    - pool.pop((user_id, thread_id), None)
  - 线程安全：`threading.Lock()` 保护 `_pool` dict
- 全局单例：`pool = HandlerPool()`

**RED** · `test_handler_pool_does_not_reuse_across_users`
- 测 acquire("u1","t1") 2 次 + acquire("u2","t1") 1 次 → 返 2 个不同 handler

**GREEN** · key 含 user_id

**RED** · `test_handler_pool_release_clears_entry`
- 测 acquire → release → acquire 同一 key → 返**新** handler

**GREEN** · release 实现

**RED** · `test_handler_pool_returns_none_when_env_missing`
- mock env 无 langfuse key → acquire 返 None（不抛）

**GREEN** · 加 None 兜底

**REFACTOR** · 加 LRU 容量限制（最多 1000 个 handler，超出 LRU 淘汰，防内存泄漏）

### Task 5：@node_trace 装饰器（**P0-1 / P0-5 / P1-1 / P1-3 / P1-4 / P1-6 / P1-13 全面重写**）

**RED** · `tests/unit/test_node_tracing.py::test_node_trace_wraps_sync_function`
- 写一个 `def my_node(state): return {"result": state["x"]*2}`，加 `@node_trace("test_node")` → 调 `my_node({"x":3})` → 断言返 `{"result":6}` 且 `langfuse_context.update_current_observation` 被调
- mock `langfuse_context.update_current_observation` → 断言被调
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_node_tracing.py::test_node_trace_wraps_sync_function`

**RED** · `test_node_trace_handles_both_signatures`（**P0-1 新增**——双签名自动识别）
```python
def test_node_trace_handles_both_signatures():
    """装饰器自动识别 (state) 单参 / (state, config) 双参签名（P0-1 修复）。"""
    from app.observability import node_trace

    @node_trace("single")
    def single_arg(state):
        return state

    @node_trace("dual")
    async def dual_args(state, config):
        return {"state": state, "thread_id": config["configurable"]["thread_id"]}

    # 单参：传 1 参
    assert single_arg({"x": 1}) == {"x": 1}
    # 双参：传 (state, config)
    import asyncio
    result = asyncio.run(dual_args({"x": 2}, {"configurable": {"thread_id": "t1"}}))
    assert result["thread_id"] == "t1"
```

**GREEN** · 实现 `app/observability/node_tracing.py`（**P0-1 + P0-5 全面重写**）：
```python
"""
@node_trace(node_name) · LangGraph 节点装饰器 · M10 业务级 trace。

⚠️ 性能影响（P2-10 docstring）：
- 单次 langfuse_context.update_current_observation RPC ~ 5-10ms（langfuse 客户端默认同步）
- 8 节点 × 4 次 update = 32 RPC → 单 chat +200ms 延迟
- sample_rate=0.1 时：90% chat 不打 RPC → 平均 +20ms
- langfuse_offline_mode=True 时：0 RPC → 平均 +0ms
- trace_call_timeout_s=1.0 时：单 RPC 超时 1s 短路，不阻塞节点

⚠️ 修复记录：
- P0-1: inspect.signature 自动识别 (state) / (state, config) 双签名
- P0-5: 改用 langfuse_context.update_current_observation（不再误用 langchain 协议 on_chain_*）
- P1-1: metadata 字段走 langfuse 期望格式
- P1-3: 节点结束汇总 child LLM spans usage → node_usage.{input_tokens, output_tokens, cost_usd}
- P1-4: langfuse_offline_mode + trace_call_timeout_s 短路
- P1-6: 显式用 contextvars 存当前 node_name（避免 langfuse_context 跨 task 污染）
- P1-13: 429 retry with tenacity exponential backoff
"""
import asyncio
import contextvars
import functools
import inspect
import logging
from typing import Any, Callable

import langfuse_context
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.observability.session_tracker import build_session_metadata
from app.observability.pii import mask_pii

log = logging.getLogger(__name__)

# P1-6 修复：显式 contextvars 隔离（V1 节点顺序执行不并发，标注风险表）
_current_node_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_node_name", default=None
)


def _should_trace() -> bool:
    """P1-2 / Task 10 短路：sample_rate=0.0 时不打 trace。"""
    import random
    return random.random() < settings.observability.sample_rate


def _safe_trace_update(**kwargs) -> None:
    """P1-4 降级：offline_mode 短路 + 1.0s 超时 + 异常吞掉。"""
    if settings.observability.langfuse_offline_mode:
        return
    try:
        # langfuse_context.update_current_observation 同步调用；超时由 tenacity 控制（P1-13）
        langfuse_context.update_current_observation(**kwargs)
    except Exception as e:
        log.debug("langfuse update_current_observation failed: %s", e)


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def _retry_safe_trace_update(**kwargs) -> None:
    """P1-13 修复：429 retry with exponential backoff。"""
    _safe_trace_update(**kwargs)


# r2 2026-06-12 新-4 修复：start_as_current_span 创建独立 span（避免 update_current_observation name 覆盖）
@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def _retry_safe_trace_update_start_span(name: str, metadata: dict) -> None:
    """新-4 修复：每次节点 invoke 创建独立 span（8 节点 → 8 个 nested span）。

    ⚠️ r2 2026-06-12 新-4 揭示：原 `_retry_safe_trace_update(name=node_name, ...)` 调
    `langfuse_context.update_current_observation(name=...)` 会**覆盖当前 observation 的 name
    字段**——8 节点顺序执行后实际只看到 1 个 observation 而非 8 个 nested span。
    修法：用 `with langfuse_context.start_as_current_span(name=node_name) as span:` 创建
    独立 span（嵌套在 chat_root observation 下，span.exit 时自动 close）。
    """
    if settings.observability.langfuse_offline_mode:
        return
    try:
        from langfuse import langfuse_context
        with langfuse_context.start_as_current_span(name=name) as span:
            # 设置初始 metadata 到 span
            if span is not None and hasattr(span, "update"):
                span.update(metadata=metadata)
            # 后续 update_span 由 _retry_safe_trace_update_update_span 处理（不重开 context）
    except Exception as e:
        log.debug("langfuse start_as_current_span failed: %s", e)


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def _retry_safe_trace_update_update_span(**kwargs) -> None:
    """新-4 修复：更新**当前 span**（不是 observation）—— 配合 start_as_current_span 使用。

    `langfuse_context.update_current_span()` 在 langfuse 2.50+ 公开，update 当前 active span
    （由 start_as_current_span 创建）的字段；不创建新 span。
    """
    if settings.observability.langfuse_offline_mode:
        return
    try:
        from langfuse import langfuse_context
        # langfuse 2.50+ 优先用 update_current_span；旧版回退 update_current_observation
        if hasattr(langfuse_context, "update_current_span"):
            langfuse_context.update_current_span(**kwargs)
        else:
            langfuse_context.update_current_observation(**kwargs)
    except Exception as e:
        log.debug("langfuse update_current_span failed: %s", e)


def _summarize_node_usage() -> dict:
    """P1-3 修复：汇总 child LLM spans 的 usage → node_usage 节点级 summary。

    r2 2026-06-12 新-5 修复：`langfuse_context.get_current_observation()` 可能返 None
    （如 langfuse 不可达、offline_mode 时）；需 None 守卫 + 整段 try/except 兜底。
    """
    try:
        from langfuse import langfuse_context
        obs = langfuse_context.get_current_observation()
        # 新-5 None 守卫：obs 可能为 None（langfuse 内部未创建 observation 时）
        if obs is None:
            return {}
        children = getattr(obs, "children", None) or []
        total_input = 0
        total_output = 0
        for child in children:
            if child is None:  # 新-5 None 守卫
                continue
            usage = getattr(child, "usage", None)
            # 新-5 修复：usage 可能非 dict（如 int/None）需类型检查
            if not isinstance(usage, dict):
                continue
            total_input += usage.get("input", 0) if isinstance(usage.get("input"), (int, float)) else 0
            total_output += usage.get("output", 0) if isinstance(usage.get("output"), (int, float)) else 0
        # cost 估算：minimax-cn 暂未公开定价，写 placeholder（P1-3）
        cost_usd = (total_input * 0.000003 + total_output * 0.000015)
        return {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": cost_usd,
        }
    except Exception as e:
        log.debug("node usage summary failed: %s", e)
        return {}


def node_trace(node_name: str) -> Callable:
    """装饰器：包装 LangGraph 节点函数（单参 / 双参签名自动识别）。

    P0-1: inspect.signature(fn) 自动识别 (state) / (state, config)
    P0-5: 改用 langfuse_context.update_current_observation（节点结束场景）
    P1-1: metadata 字段走 langfuse 期望格式
    P1-3: 节点结束汇总 child LLM spans usage
    P1-4: 不可达降级短路
    P1-6: contextvars 隔离当前 node_name
    P1-13: 429 retry with exponential backoff

    r2 2026-06-12 修复：
    新-4: 入口改用 start_as_current_span 创建独立 span（不再用 update_current_observation 覆盖）
    新-5: _summarize_node_usage 加 None 守卫 + isinstance(usage, dict) 检查
    新-6: inspect.signature 加 try/except ValueError 兜底（langchain @tool 工具函数无签名时）
    """
    def decorator(fn: Callable) -> Callable:
        # r2 2026-06-12 新-6 修复：inspect.signature 对内置/C 扩展/@tool 装饰的函数可能抛
        # `ValueError: no signature found`；加 try/except 兜底，假定单参。
        try:
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            has_config = len(params) >= 2 and params[1] in ("config", "runnable_config")
        except ValueError:
            # 新-6 修复：工具函数无 inspectable signature，假定单参 state
            has_config = False
            log.debug("node_trace: inspect.signature failed for %s, assuming single arg", fn.__name__)

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                if not _should_trace():  # P1-2 / Task 10
                    return await fn(*args, **kwargs)
                state = args[0] if args else kwargs.get("state", {})
                config = args[1] if (has_config and len(args) >= 2) else kwargs.get("config")
                thread_id = ((config or {}).get("configurable", {}) or {}).get("thread_id")
                user_id = (state or {}).get("user_id") if isinstance(state, dict) else None
                metadata = build_session_metadata(state or {}, request_id=None)
                if thread_id and not metadata.get("thread_id"):
                    metadata["thread_id"] = thread_id

                token = _current_node_name.set(node_name)  # P1-6
                try:
                    # r2 2026-06-12 新-4 修复：用 update_current_span / start_as_current_span 创建新 span
                    # 避免 update_current_observation(name=...) 覆盖上一节点 name 导致只看到 1 个 observation
                    _retry_safe_trace_update_start_span(name=node_name, metadata=metadata)  # 新-4 + P0-5 + P1-1 + P1-13
                    result = await fn(*args, **kwargs)
                    # 输出端脱敏
                    if isinstance(result, dict):
                        _retry_safe_trace_update_update_span(output=mask_pii(result))
                    # P1-3: 节点级 usage 汇总
                    node_usage = _summarize_node_usage()
                    if node_usage:
                        _retry_safe_trace_update_update_span(
                            metadata={**metadata, "node_usage": node_usage}
                        )
                    return result
                except Exception as e:
                    _retry_safe_trace_update_update_span(
                        level="ERROR",
                        status_message=f"{type(e).__name__}: {str(e)[:200]}",
                    )
                    raise
                finally:
                    _current_node_name.reset(token)
            return async_wrapper

        # sync 路径同样实现
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            if not _should_trace():
                return fn(*args, **kwargs)
            state = args[0] if args else kwargs.get("state", {})
            config = args[1] if (has_config and len(args) >= 2) else kwargs.get("config")
            thread_id = ((config or {}).get("configurable", {}) or {}).get("thread_id")
            metadata = build_session_metadata(state or {}, request_id=None)
            if thread_id and not metadata.get("thread_id"):
                metadata["thread_id"] = thread_id

            token = _current_node_name.set(node_name)
            try:
                # r2 2026-06-12 新-4 修复：同步走 start_as_current_span 创建独立 span
                _retry_safe_trace_update_start_span(name=node_name, metadata=metadata)
                result = fn(*args, **kwargs)
                if isinstance(result, dict):
                    _retry_safe_trace_update_update_span(output=mask_pii(result))
                node_usage = _summarize_node_usage()
                if node_usage:
                    _retry_safe_trace_update_update_span(
                        metadata={**metadata, "node_usage": node_usage}
                    )
                return result
            except Exception as e:
                _retry_safe_trace_update_update_span(
                    level="ERROR",
                    status_message=f"{type(e).__name__}: {str(e)[:200]}",
                )
                raise
            finally:
                _current_node_name.reset(token)
        return sync_wrapper
    return decorator


def get_current_trace_id() -> str | None:
    """P0-3 修复：取当前 Langfuse trace_id（用于回填到 ChatResponse.trace_id）。

    langfuse 2.50+ 公开 API: from langfuse import get_client; get_client().get_current_trace_id()
    """
    try:
        from langfuse import get_client
        return get_client().get_current_trace_id()
    except Exception:
        return None
```

**RED** · `test_node_trace_wraps_async_function`
- 写 `async def my_async_node(state): return {"result": "ok"}`，加 `@node_trace("test")` → `await my_async_node({...})` → 断言返 `{"result":"ok"}` 且 `langfuse_context.update_current_observation` 被调
- 用 `pytest.mark.asyncio`

**GREEN** · async wrapper 分支

**RED** · `test_node_trace_captures_exception_and_reraises`（**P2-4 修复——用 `update_current_observation` 断言 `level="ERROR"` + `status_message`，不再用 `on_chain_error`/`exc_value`**）
- 写 `def failing_node(state): raise ValueError("boom")` + `@node_trace("fail")` → 调 → 断言 `ValueError` 被 raise 且 `langfuse_context.update_current_observation` 被调 1 次带 `level="ERROR"` + `status_message` 含 `"ValueError"` 和 `"boom"`

**GREEN** · try/except + `_retry_safe_trace_update(level="ERROR", ...)`

**RED** · `test_node_trace_skips_when_handler_none` / `test_node_trace_skips_when_sample_rate_zero`
- mock `settings.observability.sample_rate = 0.0` → 调 `my_node({...})` → 正常返不抛错（不依赖 handler）

**GREEN** · sample_rate 短路

**RED** · `test_node_trace_metadata_serialized_to_lf_format`（**P1-1 新增**）
- 断言传参 `metadata={"user_id": ..., "thread_id": ..., "request_id": ..., "query_length": ..., "prompt_source": "yaml"}`

**RED** · `test_langfuse_unreachable_does_not_block_node`（**P1-4 新增**）
- mock `langfuse_context.update_current_observation` raise `ConnectionError` → 节点函数仍正常返回

**RED** · `test_node_usage_summarized_to_metadata`（**P1-3 新增**）
- mock child LLM span usage → 断言节点 metadata 包含 `input_tokens` / `output_tokens` / `cost_usd`

**REFACTOR** · 把 sync/async wrapper 抽公共 `_invoke_handler(handler, method, *args)` 工具

### Task 6：Graph 8 节点加装饰器（**P0-4 修复**——含 `answer_chitchat_node` + 节点名带 `_node` 后缀）

**RED** · `tests/unit/test_graph_nodes.py::test_all_eight_nodes_have_node_trace`（**P0-4 修复——8 节点 + getsourcelines**）
```python
def test_all_eight_nodes_have_node_trace():
    """8 节点函数（7 业务 + answer_chitchat_node）全部加 @node_trace 装饰（P0-4 修复）。"""
    from app.graph import nodes
    import inspect
    expected = {
        "load_memory_node",  # M7 实际命名带 _node 后缀（P0-4 修复）
        "classify",
        "query_rewrite",
        "retrieve",
        "rerank",
        "answer",
        "save_memory_node",  # M7 实际命名带 _node 后缀（P0-4 修复）
        "answer_chitchat_node",  # M7 P0-6 修复后加的节点（P0-4 修复）
    }
    for name in expected:
        assert hasattr(nodes, name), f"missing node function: {name}"
        func = getattr(nodes, name)
        # P2-5 修复：inspect.getsource 不含装饰器行，必须用 getsourcelines
        lines, _ = inspect.getsourcelines(func)
        full_src = "".join(lines)
        assert "@node_trace" in full_src, f"{name} missing @node_trace decorator"
```
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_graph_nodes.py::test_all_eight_nodes_have_node_trace`

**GREEN** · 改 `app/graph/nodes.py`（M7 已建）：
- import 追加：`from app.observability import node_trace`
- **8** 节点函数**每个**加 1 行装饰器（**P0-4 修复——用 M7 实际函数名带 `_node` 后缀**）：
  ```python
  @node_trace("load_memory_node")
  async def load_memory_node(state, config: RunnableConfig) -> RagState: ...  # M7 实际双参签名

  @node_trace("classify")
  async def classify(state: RagState) -> RagState: ...

  @node_trace("query_rewrite")
  async def query_rewrite(state: RagState) -> RagState: ...

  @node_trace("retrieve")
  async def retrieve(state: RagState) -> RagState: ...

  @node_trace("rerank")
  async def rerank(state: RagState) -> RagState: ...

  @node_trace("answer")
  async def answer(state: RagState) -> RagState: ...

  @node_trace("save_memory_node")
  async def save_memory_node(state, config: RunnableConfig) -> RagState: ...  # M7 实际双参签名

  @node_trace("answer_chitchat_node")
  async def answer_chitchat_node(state: RagState) -> RagState: ...  # M7 P0-6 修复后加的节点
  ```
- **不修改**节点函数签名 / 内部逻辑（M7 已审过）

**REFACTOR** · 写 `node_traced(name)` 工厂函数减少样板（如果装饰器写法啰嗦）

### Task 7：Ingest pipeline 加 trace

**RED** · `tests/integration/test_m10_e2e_trace.py::test_ingest_pipeline_emits_trace`（**e2e** 文件中）
- 起真 Langfuse（docker-compose）→ 调 `run_ingest(kind="file", ...)` → 调 `langfuse.get("trace_id")` → 断言 trace 存在
- 跑法：`cd apps/rag_v1 && pytest tests/integration/test_m10_e2e_trace.py::test_ingest_pipeline_emits_trace --require-docker`

**GREEN** · 改 `app/ingest/pipeline.py`（M4-M6 已建）：
- import：`from app.observability import node_trace`
- 在 `run_ingest(kind, ...)` 入口加装饰器：
  ```python
  @node_trace("ingest.{kind}")  # 动态 name：file / url / confluence
  async def run_ingest(state: dict) -> dict: ...
  ```
- 若 M4-M6 用 functools.partial 传 kind 不便：写 `_run_ingest_with_trace(kind, ...)` 包装，动态拼 node_name

**REFACTOR** · 抽 `ingest_traced(kind: str)` 工厂

### Task 8：X-Request-Id 透传到 graph config + flush + trace_id 回填

**RED** · `tests/unit/test_trace_id_propagation.py::test_request_id_propagates_to_graph_metadata`（**P2-6 修复——测 `config["metadata"]["request_id"]` 而非 `state.metadata.request_id`**）
- mock M8 chat 路由调用 → 断言 `graph.ainvoke` 的 `config["metadata"]["request_id"]` 等于 `X-Request-Id` header
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_trace_id_propagation.py::test_request_id_propagates_to_graph_metadata`

**GREEN** · 改 `app/api/chat.py`（M8 已建）：
- 在 `graph.ainvoke(state, config=...)` 处加 `metadata={"request_id": request.state.request_id}`（**P2-6 修复——`request_id` 来自 M8 middleware 注入到 `request.state.request_id`，不在 state dict 里**）
- `request_id` 来自 M8 middleware（M8 已建 `request_id_middleware`，M10 不用重写）

**RED** · `test_request_id_falls_back_to_uuid`
- 测无 X-Request-Id header → middleware 自动生成 `uuid4()` → 同样进 metadata

**GREEN** · 验证 M8 middleware 兜底（M8 已写，M10 测）

**RED** · `test_chat_response_includes_trace_id`（**P0-3 修复——`get_client().get_current_trace_id()` 而非 `handler.get_trace_id()`**）
- mock graph 返回 + Langfuse handler → 调 `/api/chat` → 断言响应 `trace_id` 字段非空
- 改 `app/api/schemas/chat.py`：`ChatResponse` 加 `trace_id: str | None = Field(default=None, max_length=64)`（**P1-14 修复——max_length=64**）

**GREEN** · 改 `app/api/chat.py`：
```python
# P0-3 修复：取 trace_id 用 get_client().get_current_trace_id()
from app.observability.node_tracing import get_current_trace_id
from app.observability.session_tracker import flush as langfuse_flush

# 在 ChatResponse 返回前
try:
    await langfuse_flush()  # P1-7 修复：chat 退出前 await flush()，确保 trace 落库
except Exception as e:
    log.warning("langfuse flush failed: %s", e)
return ChatResponse(
    answer=result["answer"],
    sources=result.get("sources", []),
    session_id=session_id,
    request_id=request_id,
    trace_id=get_current_trace_id(),
)
```

**REFACTOR** · 把 trace_id 取法封到 `app/observability/node_tracing.py::get_current_trace_id()`（P0-3）

### Task 9：集成测试 e2e（真 Langfuse + 真 PG）

**RED** · `tests/integration/test_m10_e2e_trace.py::test_chat_creates_eight_node_trace`（**P0-4 修复——8 节点**）
- 配 conftest：
  - `live_langfuse` fixture：起 docker-compose，确认 Langfuse 容器 healthy（P0-1 端口 3000 + P0-3 healthcheck）
  - `live_pg` fixture：起 Postgres（修 P0-5，不假绿）
- 测：
  1. POST `/api/auth/register` + `/api/auth/login` 拿 token
  2. POST `/api/chat` 1 次（带 X-Request-Id=`req-test-1`）
  3. 拿 response.trace_id
  4. **P1-7 修复：`await flush()` 后**调 `Langfuse(host=...).get_trace(response.trace_id)` → 断言 `trace.metadata["request_id"] == "req-test-1"`
  5. **r2 2026-06-12 新-7 修复**：断言 `trace.observations` 长度精确 = 1 root + 8 node + N LLM，**不**写"≥ 8"过松断言；改用 `assertEqual(observations[0].name, "chat_root")` + 8 节点 name 存在性检查
  6. 断言每个节点 observation 都有 `metadata["user_id"]` / `metadata["thread_id"]`
  7. **P1-3 修复**：断言至少 answer 节点 observation 含 `metadata.node_usage.input_tokens/output_tokens/cost_usd`
- 跑法：`cd apps/rag_v1 && docker compose -f infra/docker-compose.yml up -d postgres langfuse && pytest tests/integration/test_m10_e2e_trace.py::test_chat_creates_eight_node_trace --require-docker`

**GREEN** · 修任何失败（通常在 handler 取 trace_id / metadata 拼装）

**RED** · `test_chat_error_emits_trace_with_stack`（**P2-7 修复——用 `ChatAnthropic.APIError` 而非 `RuntimeError`**）
```python
from langchain_anthropic import ChatAnthropic
from unittest.mock import patch

@patch("app.graph.nodes.make_llm")
def test_chat_error_emits_trace_with_stack(mock_make_llm):
    """P2-7 修复：用 langchain-anthropic 真实异常类。"""
    mock_make_llm.return_value.ainvoke.side_effect = ChatAnthropic.APIError("LLM 4xx")
    ...
```
- mock `classify` 节点抛 `ChatAnthropic.APIError("LLM 4xx")` → 调 chat → 调 Langfuse API → 断言 trace 含 `level="ERROR"` observation 且 `status_message` 含 `"LLM 4xx"`

**GREEN** · `_retry_safe_trace_update(level="ERROR", ...)` 已实现（Task 5），跑通

**RED** · `test_pii_does_not_appear_in_trace_metadata`
- POST chat 时 metadata 含 `password=***`（mock 状态里塞）→ 调 Langfuse API → 断言 trace.metadata 里的 `password` 字段值是 `"***"`

**GREEN** · `mask_pii` 已实现（Task 2），跑通

**RED** · `test_token_usage_tracked_in_observation`
- 跑 chat → Langfuse observation 里断言 `usage.prompt_tokens` / `usage.completion_tokens` 非空
- CallbackHandler 自动追踪（langfuse 2.50+ 内置），不需 M10 写代码

**GREEN** · 仅验证（不写实现）

**RED** · `test_node_usage_summarized_in_observation`（**P1-3 新增**）
- 跑 chat → Langfuse observation 里断言至少 answer 节点含 `metadata.node_usage.input_tokens/output_tokens/cost_usd`

**RED** · `test_single_chat_does_not_create_n_handlers`
- mock HandlerPool → 调 chat 1 次 → 断言 `pool.acquire` 被调 ≤ 9 次（8 节点 + 1 root span），**不** ≥ 20 次
- 避 P0-1 handler 复用问题

**GREEN** · HandlerPool 已实现（Task 4），跑通

**REFACTOR** · 把 7 个 e2e 测试拆 7 个函数（每个 1 个测试方法），不要塞一个

### Task 10：PII 端到端验证 + 采样率

**RED** · `tests/integration/test_m10_e2e_trace.py::test_sensitive_payload_masked_in_retrieve_node`（**P1-8 扩展——email/IP/Bearer 也测**）
- 调 chat，state.chunks 字段含 `{"text":"password=***", "email":"user@example.com", "ip":"192.168.1.1"}`（mock OS 返回）→ 调 Langfuse API → 断言 `retrieve` observation 的 metadata/output 不含明文 `"***"` / `"user@example.com"` / `"192.168.1.1"`
- 跑法：`cd apps/rag_v1 && pytest tests/integration/test_m10_e2e_trace.py::test_sensitive_payload_masked_in_retrieve_node --require-docker`

**GREEN** · `mask_pii` 在 `build_session_metadata` 已调；node 输出端在 `_retry_safe_trace_update(output=mask_pii(result))` 后再写入

**RED** · `test_sample_rate_zero_skips_tracing`（**P1-2 修复——`sample_rate=0.0` 短路**）
- mock `settings.observability.sample_rate = 0.0` → 调 chat → 断言 Langfuse 无新 trace 写入
- 用 `pytest.MonkeyPatch.setenv("LANGFUSE_SAMPLE_RATE", "0.0")`

**GREEN** · 在 `@node_trace` 入口加 `if not _should_trace(): return fn(...)` 短路（Task 5 已实现）

**REFACTOR** · 抽 `should_trace() -> bool` 工具（已在 Task 5 实现为 `_should_trace`）

### Task 11：User feedback 端点（**P1-10 新增——建议加 Task**）

**RED** · `tests/unit/test_feedback.py::test_record_feedback_calls_langfuse_score`
- 测 `record_feedback(trace_id="abc", value=1, comment="good")` → mock `langfuse.score` → 断言被调 1 次带 `trace_id="abc"`, `name="user_feedback"`, `value=1`

**GREEN** · 新增 `app/observability/feedback.py`：
```python
from langfuse import get_client

def record_feedback(trace_id: str, value: int, comment: str | None = None) -> None:
    """M9 Gradio 👍/👎 按钮回写 Langfuse score（P1-10 修复）。"""
    try:
        client = get_client()
        client.score(trace_id=trace_id, name="user_feedback", value=value, comment=comment)
    except Exception:
        pass  # feedback 失败不污染主流程
```

**RED** · `tests/integration/test_m10_e2e_trace.py::test_feedback_endpoint_writes_score`
- 测 POST `/api/feedback {trace_id, value: 1|0, comment?: str}` → 调 `langfuse.score` → 断言 Langfuse API 看到 score

**GREEN** · 新增 `app/api/feedback.py` 路由（不在本 plan 详细展开，标 TODO 给 M9）

**REFACTOR** · 在 `app/api/chat.py` 加 `trace_id` → `feedback` 端点引用（**M9 计划实现 UI 按钮**）

**r2 2026-06-12 新-2 修复（feedback 闭环）**：
- **Task 11 GREEN 补完整 `app/api/feedback.py` 路由实现**（不仅是 stub）：
  ```python
  # app/api/feedback.py （M10 完整实现，M9 UI 调这里）
  from fastapi import APIRouter, HTTPException
  from pydantic import BaseModel, Field
  from app.observability.feedback import record_feedback
  import logging
  log = logging.getLogger(__name__)
  router = APIRouter()

  class FeedbackRequest(BaseModel):
      trace_id: str = Field(..., min_length=1, max_length=64)  # 与 ChatResponse.trace_id 同长度约束
      value: int = Field(..., ge=0, le=1)  # 0=👎 / 1=👍
      comment: str | None = Field(default=None, max_length=500)

  @router.post("/api/feedback")
  async def post_feedback(req: FeedbackRequest) -> dict:
      """M9 Gradio 👍/👎 按钮调此端点；M9 _handle_chat 内部 UpstreamError 路径也调此端点。

      跨 M 调用约定（消化 M9 r2 漂-3）：
      - M9 UI: gr.Button("👍").click(_handle_feedback, [trace_id_state, gr.State(1)], [])
      - M9 _handle_chat: 内部 UpstreamError 兜底调 _handle_feedback(trace_id, value=0, comment="upstream_error")
      - 端点: 收 {trace_id, value, comment?} → 调 record_feedback → 调 langfuse.score
      - 响应: 成功返 {"status": "ok"} / 失败返 HTTPException 503
      """
      try:
          record_feedback(req.trace_id, req.value, req.comment)
          return {"status": "ok", "trace_id": req.trace_id}
      except Exception as e:
          log.warning("feedback endpoint failed: %s", e)
          raise HTTPException(status_code=503, detail=f"feedback write failed: {e}")
  ```
- **Task 11 GREEN 补 `app/observability/feedback.py::record_feedback` 完整实现**（从 stub 改完整）：
  ```python
  # app/observability/feedback.py
  from langfuse import get_client
  import logging
  log = logging.getLogger(__name__)

  def record_feedback(trace_id: str, value: int, comment: str | None = None) -> None:
      """M9 Gradio 👍/👎 按钮 + M9 _handle_chat UpstreamError 兜底 → 写 langfuse score。

      跨 M 联动（消化 M9 r2 漂-3）：
      - M9 _handle_feedback 调 httpx.post(API_BASE + '/api/feedback', json={'trace_id': trace_id, 'value': value, 'comment': comment})
      - M10 端点收 → 调 record_feedback → 此函数调 langfuse.score
      - M11 RAGAS: 报告通过 get_client().get_current_trace_id() 拉 langfuse scores API 拿 user_feedback 维度
      """
      try:
          client = get_client()
          client.score(
              trace_id=trace_id,
              name="user_feedback",
              value=value,
              comment=comment,
          )
      except Exception as e:
          # feedback 失败不污染主流程；M9 UI 显示 gr.Warning("反馈失败") 即可
          log.warning("record_feedback failed: %s", e)
  ```
- **Files 表 L195 `app/observability/__init__.py` 暴露清单追加** `record_feedback`（P2-9 修订：feedback 端点用了 record_feedback，必须暴露）

### Task 12：M3 工厂 `get_callback_handler` 注入 `sample_rate`（**阻塞 2 修复**）

**RED** · `tests/unit/test_langfuse_factory.py::test_get_callback_handler_passes_sample_rate`（**追加**到 M3 既有测试）
- mock env `LANGFUSE_SAMPLE_RATE=0.1` → 调 `get_callback_handler()` → 断言 `CallbackHandler(sample_rate=0.1)` 被构造

**GREEN** · 改 `app/observability/langfuse.py::get_callback_handler`：
```python
def get_callback_handler():
    from app.config import settings
    # M10 阻塞 2 修复：注入 sample_rate 到 CallbackHandler（客户端侧真正生效）
    return CallbackHandler(sample_rate=settings.observability.sample_rate)
```

**REFACTOR** · 加注释：客户端侧 sample_rate 真正控制是否打全量 trace；节点级 sample_rate 是装饰器层短路

### Task 13：OTEL auto-instrumentation 默认启用（**P1-12 修复**）

**RED** · `tests/unit/test_otel_instrumentation.py::test_lifespan_instruments_langchain`
- 测 lifespan 启动后 `OpenTelemetryInstrumentor.is_instrumented_by_opentelemetry == True`

**GREEN** · 改 `app/main.py`（M0 已建）：
```python
from opentelemetry.instrumentation.langchain import LangchainInstrumentor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # P1-12 修复：默认启用 OTEL auto-instrumentation（仅 instrument，不配 exporter）
    LangchainInstrumentor().instrument()
    yield
    # shutdown logic
```

**REFACTOR** · 不配 OTEL exporter（让 langfuse 自动 collect spans，不外发；M12 Hardening 时再配）

---

## 测试策略

- **M10 单元**：`cd apps/rag_v1 && pytest tests/unit/test_node_tracing.py tests/unit/test_session_tracker.py tests/unit/test_pii.py tests/unit/test_handler_pool.py tests/unit/test_trace_id_propagation.py` —— 全 mock，CI 内 1s
- **M10 集成**：`cd apps/rag_v1 && docker compose -f infra/docker-compose.yml up -d postgres langfuse && pytest tests/integration/test_m10_e2e_trace.py --require-docker` —— 需真 Langfuse 容器（端口 3000 P0-1）+ 真 PG（修 P0-5）+ 60s 启动
- **覆盖率门禁**：`pytest --cov=app/observability --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 `[RED]`）→ GREEN（commit 标 `[GREEN]`）→ REFACTOR（commit 标 `[RF]`）
- **2 天任务排布**：
  - **Day 1**（Tasks 1-6）：配置块 + PII + session_tracker + handler_pool + 装饰器 + 8 节点接入（**单元测试全过**）
  - **Day 2**（Tasks 7-13）：ingest pipeline + X-Request-Id 透传 + 集成测试 e2e + PII 端到端 + 采样率 + feedback 端点 + M3 工厂修订 + OTEL auto（**集成测试真 Langfuse + 真 PG 跑通**）

---

## 验证（Definition of Done）

- [ ] `@node_trace` 装饰器覆盖 graph 8 节点 + ingest pipeline 入口
- [ ] 装饰器自动识别 `(state)` / `(state, config)` 双签名（test_node_trace_handles_both_signatures 过）
- [ ] 装饰器用 `langfuse_context.update_current_observation` 打 span（不用 langchain 协议 `on_chain_*`）
- [ ] 集成测试 `test_chat_creates_eight_node_trace` 在 docker-compose 起来后 60s 内通过
- [ ] Langfuse 看板能看到 1 个 root trace + 8 个 nested node spans + N 个 LLM spans（每个 LLM invoke 一个）
- [ ] 每个 node span 含 `metadata.user_id` / `metadata.thread_id` / `metadata.request_id` / `metadata.query_length` / `metadata.prompt_source`
- [ ] PII 测试：`test_pii_does_not_appear_in_trace_metadata` / `test_sensitive_payload_masked_in_retrieve_node` / `test_mask_pii_handles_email_and_ip` 全过（password / token / api_key / email / 手机号 / IP / Bearer 不入 trace）
- [ ] 错误节点测试：`test_chat_error_emits_trace_with_stack` 过（节点抛异常时 Langfuse 记 ERROR + status_message）
- [ ] Token 测试：`test_token_usage_tracked_in_observation` 过（CallbackHandler 自动追踪 LLM span usage）
- [ ] 节点 usage 测试：`test_node_usage_summarized_in_observation` 过（节点 metadata 包含 `node_usage.input_tokens/output_tokens/cost_usd`）
- [ ] Handler 复用测试：`test_single_chat_does_not_create_n_handlers` 过（单次 chat ≤ 9 次 acquire）
- [ ] 降级测试：`test_langfuse_unreachable_does_not_block_node` 过（容器 down 时节点正常返回）
- [ ] 429 retry 测试：mock `langfuse_context.update_current_observation` 抛 429 → 装饰器 retry 3 次 with exponential backoff
- [ ] 采样率测试：`test_sample_rate_zero_skips_tracing` 过（`sample_rate=0.0` 短路 trace）
- [ ] User feedback 测试：`test_feedback_endpoint_writes_score` 过（`langfuse.score` 被调）
- [ ] OTEL auto 测试：`test_lifespan_instruments_langchain` 过（`LangchainInstrumentor().instrument()` 被调）
- [ ] ChatResponse.trace_id 测试：`test_chat_response_includes_trace_id` 过（响应含 `trace_id` + `max_length=64`）
- [ ] flush 时机测试：`test_chat_creates_eight_node_trace` 集成测试中 `await flush()` 后 trace 落库
- [ ] 单元覆盖率 ≥ 85%
- [ ] `.env.example` 完整 M10 段：`LANGFUSE_SAMPLE_RATE` / `LANGFUSE_MASK_KEYS` / `LANGFUSE_TRACE_ENV` / `LANGFUSE_FLUSH_TIMEOUT_S` / `LANGFUSE_OFFLINE_MODE` / `LANGFUSE_TRACE_RETENTION_DAYS` / `LANGFUSE_PROMPT_SOURCE`
- [ ] `pyproject.toml` 追加 `testcontainers[langfuse]` / `tenacity` / `opentelemetry-instrumentation-langchain` 到 dev 依赖
- [ ] `ChatResponse` schema 增 `trace_id: str | None = Field(max_length=64)` 字段（M9 渲染用）
- [ ] M3 工厂 `make_llm` 不修改 callback 注入方式；`get_callback_handler` 追加 `sample_rate` 参数注入
- [ ] 装饰器 docstring 含性能影响说明（+200ms 延迟 / 32 RPC）

---

## 与其他 M 的依赖

| 上游（必须 M10 前完成） | 下游（依赖 M10） |
|----------------------|----------------|
| M0 `infra/docker-compose.yml`（Langfuse 容器 + 3000 端口 P0-1 + healthcheck P0-3） | M9 Gradio UI（`ChatResponse.trace_id` 渲染跳 Langfuse 看板 + 👍/👎 按钮调 `/api/feedback`） |
| M1 alembic（PG 集成测试需 schema） | M11 RAGAS eval（`trace_id` 作 RAGAS input 关联字段 + `langfuse.score` 关联 user_feedback 维度） |
| M2 auth（M8 chat 鉴权） | M12 Hardening（Sentry / 限速告警基于 M10 观测 + `langfuse_offline_mode` 降级开关） |
| M3 `observability/langfuse.py`（`get_callback_handler` 工厂）· **M10 修订注入 `sample_rate`** | |
| M7 graph 8 节点函数（`app/graph/nodes.py`，含 `load_memory_node` / `save_memory_node` 双参 + `answer_chitchat_node`） | |
| M8 `X-Request-Id` middleware + `/api/chat` 路由（30s chat timeout） | |
| M4-M6 `app/ingest/pipeline.py`（`run_ingest` 入口） | |

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| **P0-1** CallbackHandler 每次 invoke 重建 → 性能差 / 内存泄漏 | `HandlerPool` 单例按 `(user_id, thread_id)` 复用（Task 4）；LRU 容量 1000 防泄漏 | "用 `functools.lru_cache` 全局缓存 handler"——**已否决**（不同 user 串扰） |
| **P0-2** Langfuse 2.x callback 在 async node 里可能未 flush → 异步上下文泄漏 | `get_client().flush()` 显式 flush（`session_tracker.async flush()`，**P0-2 修复**不再用 `langfuse_context.flush()`）；`flush_timeout_s=1.0` 防 hang 死 | "不 flush 等 GC"——**已否决**（pytest 里 5xx 偶发） |
| **P0-3** TestClient 不发真实 HTTP → 集成测试要么真 Langfuse 要么 testcontainer | 集成测试用 `docker compose up langfuse`（端口 3000）；`testcontainers[langfuse]` 作备选 | "Mock 整个 Langfuse 客户端"——**已否决**（无法验证 metadata 真进看板） |
| **P0-4** M7 节点实际命名带 `_node` 后缀 + 8 个节点（7 业务 + `answer_chitchat_node`） | Task 6 RED 测 8 节点函数名 + `inspect.getsourcelines`（含装饰器） | "7 节点"——**已否决**（与 M7 不一致） |
| **P0-5** `handler.on_chain_*` 是 langchain 协议级私有 callback，不创建 Langfuse trace span | **P0-5 修复**——`@node_trace` 改用 `langfuse_context.update_current_observation`（P0-5 GREEN 段） | "调 `on_chain_start`"——**已否决**（不创建 trace span） |
| **P1-1** PII 散落 regex 难维护 | `mask_pii` 单点工具 + `ObservabilitySettings.mask_keys` 配置驱动 + 兜底 `PII_VALUE_RE` 扫值 | "每个节点函数手写脱敏"——**已否决**（易漏） |
| **P1-2** 采样率 1.0 在 prod 成本爆炸 | `ObservabilitySettings.sample_rate`，dev=1.0 / staging=0.5（建议）/ prod=0.1 env 切换 | "固定 1.0"——**已否决**（prod 不可用） |
| **P1-3** 节点级 usage/cost 缺失 | `_summarize_node_usage()` 汇总 child LLM spans → `node_usage.input_tokens/output_tokens/cost_usd`（Task 5 GREEN 段） | "只信 CallbackHandler 自动追踪"——**已否决**（节点级 summary 缺失） |
| **P1-4** Langfuse 不可达时阻塞 32 RPC × 5s | `langfuse_offline_mode=True` 短路 + `trace_call_timeout_s=1.0` 超时短路 + `test_langfuse_unreachable_does_not_block_node` 验证 | "不设降级"——**已否决**（拖垮 chat 30s timeout） |
| **P1-5** HandlerPool 与 langfuse 2.50+ 无状态 callback 冲突 | 保留 HandlerPool（**仅 LLM 级**） + 节点级走 `langfuse_context`；加模块 docstring 澄清（P1-5 GREEN 段） | "完全删 HandlerPool"——**已否决**（LLM 级仍需池化） |
| **P1-6** langfuse_context 跨 async task 传递可能丢失 | `_current_node_name = contextvars.ContextVar` 显式隔离（V1 节点顺序执行不并发，标注此处） | "不处理 contextvars"——**已否决**（V1.1 并行节点时需修复） |
| **P1-7** flush 调用时机缺失 | chat 路由返回前 `await flush()`（Task 8 GREEN 段） + 集成测试 `await flush()` 后 GET trace | "不调 flush"——**已否决**（集成测试 trace 拉不到） |
| **P1-8** PII 缺 email/手机号/IP/Bearer 兜底 | 扩展 `PII_VALUE_RE` + `test_mask_pii_handles_email_and_ip`（Task 2 RED 段） | "只脱敏 password/token"——**已否决**（合规风险） |
| **P1-9** Langfuse trace 保留 | 默认 30 天，prod 长保留撑爆磁盘 | 设置 `trace_retention_days=30` + 定期清理脚本（M12 实现） | "不设 retention"——**已否决**（数据无界增长） |
| **P1-10** user feedback 缺失 | 新增 `app/observability/feedback.py::record_feedback` + `app/api/feedback.py` 路由（Task 11，P1-10 建议） | "M10 不接 feedback"——**已否决**（M11 RAGAS 缺用户反馈维度） |
| **P1-11** prompt 来源 yaml vs langfuse 冲突 | `ObservabilitySettings.prompt_source: str = "yaml"`（V1=yaml，V1.1 改 langfuse） + 节点 metadata 增 `prompt_source` 字段 | "不标注来源"——**已否决**（metadata 误导） |
| **P1-12** OTEL auto-instrumentation 缺失 | `app/main.py` lifespan 启动时调 `LangchainInstrumentor().instrument()`（**仅 instrument，不配 exporter**，Task 13） | "OTEL 留 hook 不实现"——**已否决**（失去 OTEL 扩展点） |
| **P1-13** Langfuse 429 / 限速 | `_retry_safe_trace_update` 用 tenacity `@retry(stop=3, wait_exponential)`（Task 5 GREEN 段） | "429 静默丢"——**已否决**（高 QPS 静默数据缺） |
| **P1-14** `ChatResponse.trace_id` 缺 max_length | `trace_id: str \| None = Field(default=None, max_length=64)`（Task 8 GREEN 段） | "无长度限制"——**已否决**（URL 截断 / DB 异常） |
| **P2-1** `flush_timeout_s=5.0` 默认过大 | 默认 1.0s（trace flush 在 ASGI 请求内执行不能 block 太久；M8 chat 30s timeout，5s flush 占 17% 太多） | "5.0s 默认"——**已否决**（阻塞 chat 响应） |
| **P2-2** `.env.example` M10 段不全 | 补 7 项 env（`LANGFUSE_SAMPLE_RATE` / `LANGFUSE_MASK_KEYS` / `LANGFUSE_TRACE_ENV` / `LANGFUSE_FLUSH_TIMEOUT_S` / `LANGFUSE_OFFLINE_MODE` / `LANGFUSE_TRACE_RETENTION_DAYS` / `LANGFUSE_PROMPT_SOURCE`） | "只写 3 项"——**已否决**（env 不全） |
| **P2-3** `node_tracing.py` vs `tracing.py` 命名冲突 | 暂保留两文件，模块 docstring 标注差异（M3 通用 `@trace` vs M10 节点 `@node_trace`） | "删 `tracing.py`"——**已否决**（破坏 M3） |
| **P2-4** `exc_value="boom"` 断言名错 | 改用 `langfuse_context.update_current_observation` 测 `level="ERROR"` + `status_message`（Task 5 GREEN 段） | "保留 `on_chain_error` 测试"——**已否决**（API 不匹配） |
| **P2-5** `inspect.getsource` 不含装饰器行 | 改用 `inspect.getsourcelines(func)` 拼完整源码（Task 6 RED 段） | "`inspect.getsource` 包含"——**已否决**（不含装饰器） |
| **P2-6** mock 路径混淆 `state.metadata.request_id` 与 `config["metadata"]["request_id"]` | 测试断言 `mock_graph.ainvoke.call_args.kwargs["config"]["metadata"]["request_id"]`（Task 8 RED 段） | "测 `state.metadata.request_id`"——**已否决**（state 不含 metadata 嵌套） |
| **P2-7** mock 节点异常用 `RuntimeError` 不符合 langchain-anthropic 真实异常类 | 改用 `ChatAnthropic.APIError` mock（Task 9 RED 段） | "用 `RuntimeError`"——**已否决**（与实际不符） |
| **P2-8** staging sample_rate 缺默认 | `sample_rate=1.0` 默认 + 注释"staging 建议 0.5 配 env override" | "不标注 staging 默认"——**已否决**（可能压垮 staging Langfuse） |
| **P2-9** `__init__.py` 暴露太多 public API | 最小暴露 `node_trace` / `mask_pii` / `build_session_metadata` / `flush` / `get_current_trace_id`（**不**暴露 `HandlerPool` / `ObservabilitySettings`） | "暴露 4 个新模块全部"——**已否决**（API 表面过大） |
| **P2-10** 缺装饰器性能影响 docstring | 装饰器 docstring 写"+200ms / 32 RPC / 采样 0.1 时 +20ms"（Task 5 GREEN 段） | "不写性能说明"——**已否决**（运维盲点） |
| **X-1** `app/config.py` M10 再加 `ObservabilitySettings` → 累计 10 个子配置 | M10 沿用单文件；M0 时已决定暂不拆 `app/configs/`，本 M10 不破坏；M12 Hardening 时统一拆 | "M10 拆 `app/configs/`"——**已否决**（scope creep；review 报告 X-1 风险表已说明） |
| **r2-2026-06-12 新-1 已修** · ChatResponse 字段命名跨 M 统一 | M8/M10/M9 三 plan 统一为 `trace_id: str | None = Field(max_length=64)`；M8 内部 state 名仍叫 `request_id` 不变，仅 API 响应字段名改 `trace_id`（M8 r2 P1-1 修订时同步） | "M8 沿用 `request_id` 字段"——**已否决**（M9 r2 漂-2 + M8 r2 新-1 揭示命名混乱） |
| **r2-2026-06-12 新-2 已修** · feedback 闭环 | M9 UI 按钮（gr.Button("👍/👎")）+ M10 `/api/feedback` 端点（完整路由非 stub）+ `langfuse.score` 调通；M9 `_handle_chat` UpstreamError 路径兜底调 `value=0, comment="upstream_error"` | "M10 端点 stub + M9 不实现 UI"——**已否决**（M11 RAGAS 缺用户反馈维度） |
| **r2-2026-06-12 新-3 已修** · 4 名同串规范节 | M10 plan 增"Langfuse 链路 4 名同串规范"节，4 行表明确 `X-Request-Id` / `request_id` / `trace_id` / `Langfuse trace.id` 语义层差异 | "trace_id 承载 request_id 值"——**已否决**（langfuse API 限制，HTTP 层与业务层 ID 应分别） |
| **r2-2026-06-12 新-4 已修** · 装饰器覆盖问题 | Task 5 GREEN 段增 `_retry_safe_trace_update_start_span(name, metadata)` 用 `with langfuse_context.start_as_current_span(name=node_name)` 创建独立 span（不再用 `update_current_observation(name=...)` 覆盖）；节点结束用 `_retry_safe_trace_update_update_span(**kwargs)` 调 `update_current_span` | "保留 `update_current_observation` 覆写"——**已否决**（集成测试 `observations` 长度应为 1+8+N 而非 1） |
| **r2-2026-06-12 新-5 已修** · usage 类型检查 + None 守卫 | Task 5 GREEN 段 `_summarize_node_usage` 加 `if obs is None: return {}` 守卫 + `if not isinstance(usage, dict): continue` 类型检查 + `if not isinstance(usage.get("input"), (int, float)): else 0` | "全 try/except 吞"——**已否决**（吞掉真实异常） |
| **r2-2026-06-12 新-6 已修** · inspect.signature ValueError 兜底 | Task 5 GREEN 段装饰器 `inspect.signature(fn)` 加 `try/except ValueError: has_config = False` 兜底（langchain `@tool` 工具函数无 signature 时假定单参 state） | "不加兜底"——**已否决**（未来 M7 节点演进出 `@tool` 装饰时炸） |
| **r2-2026-06-12 新-7 已修** · 集成测试断言精确化 | Task 9 RED L788 改为断言 `trace.observations[0].name == "chat_root"` + 8 节点 name 存在性检查（`assertTrue(any(o.name == "load_memory_node" for o in observations))` × 8 节点），**不**用 `≥ 8` 过松断言 | "保留 ≥ 8 过松断言"——**已否决**（sample_rate<1.0 或 offline_mode 时易误判通过；不能验证 8 节点都被装饰） |

---

## Langfuse 链路 4 名同串规范（r2-2026-06-12 新增·消化 M8/M9/M10/M11 跨 M 命名）

> 解决 **r2 review 新-3**（M10 `get_current_trace_id()` 与 M8 `RequestIdMiddleware.request_id` 概念未对齐）+ **新-1**（ChatResponse 字段命名跨 M 不一致）+ **新-2**（feedback 闭环 M9 路径对齐）。本节是 M10 plan 的 **跨 M 字段契约基线**，M8/M9/M11 plan 应同步对齐。

**4 个名字，同一个值，不同语义层**：

| 名称 | 语义层 | 来源 | 取法 | 用途 |
|------|--------|------|------|------|
| `X-Request-Id` | **HTTP Header 协议级** | 客户端发 / M8 middleware 缺则 `uuid4()` 兜底 | `request.headers.get("X-Request-Id")` | HTTP 协议级请求唯一 ID（日志/链路追踪） |
| `request_id` | **M8 FastAPI 中间件内部 state** | M8 `RequestIdMiddleware` 注入到 `request.state.request_id` | `request.state.request_id` | M8 chat route 内部 state；灌到 `graph.ainvoke(config.metadata.request_id)` |
| `trace_id` | **M8 ChatResponse 响应字段 + M9 UI 渲染** | M8 chat route 构造 `ChatResponse(trace_id=...)` 时填 | `getattr(response, "trace_id", None)` | 客户端拿到 `ChatResponse.trace_id` → M9 Gradio 拼 Langfuse 链接；M11 RAGAS 报告关联字段 |
| `Langfuse trace.id` | **M10 Langfuse 平台级** | M10 装饰器创建 Langfuse trace 时平台自动生成 ULID/cuid2 | `get_client().get_current_trace_id()` | Langfuse 看板 GET `/api/public/traces/{id}` 用；M10 装饰器把前 3 层 ID 写入 `observation.metadata` 做关联 |

**4 名同值约束**（V1 实施强制）：
- **HTTP `X-Request-Id` = M8 `request_id` = `ChatResponse.trace_id`**：三者**字面字符串完全相同**，由 M8 middleware 统一生成（缺则 `uuid4()`），沿链路传递
- **Langfuse `trace.id` 可与上面不同**：langfuse 平台自动生成的内部 ULID，与 HTTP 层 ID 是**映射关系**（在 observation metadata 里同时存 `request_id` 字段做关联）
- **不要混用**：M8 代码用 `request_id`（M8 内部 state 名）/ M10 代码用 `trace_id`（Langfuse 语义）/ API 响应字段用 `trace_id`（统一对外口径）

**跨 M 字段同步清单**（M10 r2 揭示，需 M8/M9/M11 同步）：
1. **M8 plan**：ChatResponse 字段 `request_id: str` → 统一改 `trace_id: str`（M8 r2 P1-1 修订时同步；M8 内部 state 名仍叫 `request_id` 不变，仅 API 响应字段名改）
2. **M9 plan**：所有引用 `request_id` 的地方（trace_id 渲染 / 👍/👎 调 M10 `/api/feedback`）→ 统一改 `trace_id`（M9 r2 漂-2 必改）
3. **M11 plan**：RAGAS 报告 trace_id 关联字段 → 统一 `trace_id`（M11 r2 待改）
4. **M10 plan（本文）**：`ChatResponse.trace_id` 字段 + `get_current_trace_id()` + 装饰器 metadata `request_id` 字段 → 已对齐本规范

**Feedback 闭环调用路径**（消化 **新-2** 跨 M 联动）：
- **M9 UI 调用**：`gr.Button("👍").click(_handle_feedback, [trace_id_state, gr.State(1)], [])` + `gr.Button("👎").click(_handle_feedback, [trace_id_state, gr.State(0)], [])` → `_handle_feedback(trace_id, value)` 调 `httpx.post(f"{API_BASE}/api/feedback", json={"trace_id": trace_id, "value": value, "comment": None})`
- **M10 端点接收**：`app/api/feedback.py::POST /api/feedback {trace_id, value: 1|0, comment?: str}` → 调 `record_feedback(trace_id, value, comment)` → 调 `langfuse.score(trace_id, name="user_feedback", value=value, comment=comment)`
- **M11 关联**：RAGAS 报告通过 `get_client().get_current_trace_id()` 拉 langfuse scores API 拿 `user_feedback` 维度
- **错误路径调用**：M9 `_handle_chat` 内部 `UpstreamError` 路径也调 `_handle_feedback(trace_id, value=0, comment="upstream_error")` 把上游错误计入 feedback（用户未显式反馈时系统兜底）

**M7 双节点双 key**（消化 M7 r2 新-2 save_memory 双节点）：
- `save_memory_node` 拆为 `save_memory_rag`（RAG 路径走持久化 RAG memory）+ `save_memory_chitchat`（chitchat 路径走短期 chitchat memory）
- M10 装饰器分别 `@node_trace(name="save_memory_rag")` + `@node_trace(name="save_memory_chitchat")` 双 key
- Task 6 装饰器 GREEN 段补 1 行注释：`# M7 r2 新-2 修复：save_memory_node 拆双 key；M10 装饰器 name 字段同步`

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M10-plan-r0 | 2026-06-11 | 初稿（基线 V1 Scope 决策 #10/#11 + review P0/P1） |
| M10-plan-r0 | 2026-06-11 | 吸收 review P0-1（端口 3000）/ P0-5（真 PG 集成测试）/ P1-12（langfuse import 双备）/ P1-14（M3 callback 注入已正确，M10 不重写）/ P1-2（采样率 dev=1.0 / prod=0.1）/ P1-3（OTEL 留 hook 不实现） |
| M10-plan-r1 | 2026-06-11 | 吸收 M10 review 全部 29 项修复（P0-1 装饰器签名双参数支持 / P0-2 flush 改用 `get_client().flush()` / P0-3 trace_id 改用 `get_client().get_current_trace_id()` / P0-4 测试改 8 节点 + `getsourcelines` / P0-5 装饰器改 `langfuse_context.update_current_observation` / P1-1 metadata 格式测试 / P1-3 节点 usage/cost 汇总 / P1-4 不可达降级 `langfuse_offline_mode` + `trace_call_timeout_s` / P1-5 HandlerPool 模块 docstring 澄清 / P1-6 contextvars 隔离 / P1-7 flush 调用点 / P1-8 PII 扩展 email/手机/IP/Bearer / P1-9 retention 字段 / P1-10 user feedback 端点 / P1-11 prompt_source 字段 / P1-12 OTEL auto-instrumentation / P1-13 429 retry with tenacity / P1-14 trace_id `max_length=64` / P2-1 flush_timeout 默认 1.0 / P2-2 .env.example 补全 7 项 / P2-3 命名去重标注 / P2-4 错误断言改 `level=ERROR` / P2-5 `inspect.getsourcelines` / P2-6 metadata 路径澄清 / P2-7 mock 异常用 `ChatAnthropic.APIError` / P2-8 staging 0.5 注释 / P2-9 `__init__.py` 最小暴露 / P2-10 装饰器性能 docstring） |
| r1-2026-06-11 P0-1 已修：@node_trace 装饰器用 `inspect.signature(fn)` 自动识别 (state) / (state, config) 双签名，新增 `test_node_trace_handles_both_signatures` |
| r1-2026-06-11 P0-2 已修：`session_tracker.async flush()` 改用 `from langfuse import get_client; client.flush()`，RED 测试改 `test_flush_calls_client_flush`，Tech Stack 主路径 import 同步更新 |
| r1-2026-06-11 P0-3 已修：trace_id 取法封装到 `node_tracing.py::get_current_trace_id()`，内部调 `get_client().get_current_trace_id()`，M8 chat 路由 import 此函数填 `ChatResponse.trace_id` |
| r1-2026-06-11 P0-4 已修：Task 6 RED 测试改 8 节点（加 `answer_chitchat_node`），节点名用 M7 实际 `load_memory_node` / `save_memory_node` 带 `_node` 后缀；用 `inspect.getsourcelines`（含装饰器） |
| r1-2026-06-11 P0-5 已修：装饰器彻底改写——`langfuse_context.update_current_observation(name=node_name, metadata=...)` 打 span（不再误用 langchain 协议 `on_chain_*`）；错误用 `level="ERROR"` + `status_message`；输出端 `output=mask_pii(result)` |
| r1-2026-06-11 P1-1 已修：新增 `test_node_trace_metadata_serialized_to_lf_format`，断言 metadata 字段走 langfuse 期望格式（user_id / thread_id / request_id / query_length / prompt_source） |
| r1-2026-06-11 P1-2 已修：Task 5 GREEN 段彻底放弃 `on_chain_*` 私有协议改用 `langfuse_context.update_current_observation`（P0-5 已修）；`should_trace()` 工具抽到 `_should_trace()` 短路 sample_rate |
| r1-2026-06-11 P1-3 已修：`_summarize_node_usage()` 汇总 child LLM spans → `node_usage.{input_tokens, output_tokens, cost_usd}`；Task 5 GREEN 段补；新增 `test_node_usage_summarized_in_observation` e2e |
| r1-2026-06-11 P1-4 已修：`ObservabilitySettings` 加 `langfuse_offline_mode: bool = False` + `trace_call_timeout_s: float = 1.0`；`_safe_trace_update()` 短路离线模式 + 吞异常；新增 `test_langfuse_unreachable_does_not_block_node` |
| r1-2026-06-11 P1-5 已修：`HandlerPool` 模块 docstring 澄清"仅服务 LLM 级，节点级走 `langfuse_context`"；保留 HandlerPool 作为方案 B（仅 LLM 级用） |
| r1-2026-06-11 P1-6 已修：`_current_node_name = contextvars.ContextVar` 显式存 / 读当前 node_name，try/finally reset；V1 节点顺序执行不并发，风险表标注 V1.1 并行节点时验证 |
| r1-2026-06-11 P1-7 已修：M8 chat 路由返回 `ChatResponse` 前 `await langfuse_flush()`；集成测试 `test_chat_creates_eight_node_trace` 调 `await flush()` 后再 GET `/api/public/traces/{id}` |
| r1-2026-06-11 P1-8 已修：`PII_VALUE_RE` 扩展 4 类兜底正则（email / 中国手机号 / IPv4 / Bearer token）；新增 `test_mask_pii_handles_email_and_ip` + `test_sensitive_payload_masked_in_retrieve_node` 扩展 |
| r1-2026-06-11 P1-9 已修：`ObservabilitySettings` 加 `trace_retention_days: int = 30` + `archive_to_s3: bool = False` + `trace_pii_redaction_strict: bool = True`；风险表补"定期清理脚本 M12 实现" |
| r1-2026-06-11 P1-10 已修：新增 `app/observability/feedback.py::record_feedback` + Task 11（`/api/feedback` 端点，标 TODO 给 M9 UI 按钮）；`langfuse.score(trace_id, name="user_feedback", value, comment)` |
| r1-2026-06-11 P1-11 已修：`ObservabilitySettings.prompt_source: str = "yaml"`（V1=yaml，V1.1 改 `langfuse`）；`build_session_metadata` 返回增 `prompt_source` 字段；节点 metadata 同步 |
| r1-2026-06-11 P1-12 已修：Task 13 新增——`app/main.py` lifespan 启动时调 `LangchainInstrumentor().instrument()`（**仅 instrument，不配 exporter**）；pyproject 加 `opentelemetry-instrumentation-langchain` |
| r1-2026-06-11 P1-13 已修：`_retry_safe_trace_update` 用 tenacity `@retry(stop_after_attempt(3), wait_exponential(multiplier=1, min=1, max=4))` 包 `_safe_trace_update`；pyproject 加 `tenacity >=8.2,<9` |
| r1-2026-06-11 P1-14 已修：`app/api/schemas/chat.py::ChatResponse.trace_id: str \| None = Field(default=None, max_length=64)`；新增 `test_chat_response_includes_trace_id` 单元测试 |
| r1-2026-06-11 P2-1 已修：`ObservabilitySettings.flush_timeout_s: float = 1.0` 默认（从 5.0 改 1.0；M8 chat 30s timeout，5s flush 占 17% 太多） |
| r1-2026-06-11 P2-2 已修：`.env.example` M10 段补 7 项 env（`LANGFUSE_SAMPLE_RATE` / `LANGFUSE_MASK_KEYS` / `LANGFUSE_TRACE_ENV` / `LANGFUSE_FLUSH_TIMEOUT_S` / `LANGFUSE_OFFLINE_MODE` / `LANGFUSE_TRACE_RETENTION_DAYS` / `LANGFUSE_PROMPT_SOURCE`） |
| r1-2026-06-11 P2-3 已修：暂保留 `tracing.py`（M3 通用 `@trace`）+ `node_tracing.py`（M10 节点 `@node_trace`）两文件；模块 docstring 标注差异；`__init__.py` 最小暴露避免冲突 |
| r1-2026-06-11 P2-4 已修：`test_node_trace_captures_exception_and_reraises` 改用 `langfuse_context.update_current_observation` 断言 `level="ERROR"` + `status_message` 含 `"ValueError"` 和 `"boom"`（不再用 `on_chain_error`/`exc_value`） |
| r1-2026-06-11 P2-5 已修：`test_all_eight_nodes_have_node_trace` 用 `inspect.getsourcelines(func)` 拼完整源码（`inspect.getsource` 不含装饰器行） |
| r1-2026-06-11 P2-6 已修：`test_request_id_propagates_to_graph_metadata` 断言 `mock_graph.ainvoke.call_args.kwargs["config"]["metadata"]["request_id"] == "req-test-1"`（澄清 `request_id` 走 `config["metadata"]` 而非 `state.metadata`） |
| r1-2026-06-11 P2-7 已修：`test_chat_error_emits_trace_with_stack` mock `ChatAnthropic.APIError("LLM 4xx")`（用 langchain-anthropic 0.3+ 真实异常类，不再用 `RuntimeError`） |
| r1-2026-06-11 P2-8 已修：`ObservabilitySettings.sample_rate` 默认 1.0，注释"staging 建议 0.5 配 env override" |
| r1-2026-06-11 P2-9 已修：`app/observability/__init__.py` 最小暴露 `node_trace` / `mask_pii` / `build_session_metadata` / `flush` / `get_current_trace_id`（**不**暴露 `HandlerPool` / `ObservabilitySettings`） |
| r1-2026-06-11 P2-10 已修：`@node_trace` 装饰器 docstring 写性能影响（单 RPC 5-10ms / 8 节点 × 4 update = 32 RPC / +200ms 延迟 / sample_rate=0.1 时 +20ms / offline_mode 时 +0ms） |
| r2-2026-06-12 新-1 已修：ChatResponse 字段命名跨 M 统一 `trace_id: str | None = Field(max_length=64)`（M8/M10/M9 三 plan 同步；M8 内部 state 名仍 `request_id`，仅 API 响应字段名改 `trace_id`） |
| r2-2026-06-12 新-2 已修：feedback 闭环——M10 补完整 `app/api/feedback.py` 路由（`POST /api/feedback {trace_id, value: 0\|1, comment?}` → 调 `record_feedback` → 调 `langfuse.score`）+ `record_feedback` 完整实现（langfuse 2.50+ `client.score()`）+ M9 UI `gr.Button("👍/👎")` 跨 M 约定 + M9 `_handle_chat` UpstreamError 路径兜底 |
| r2-2026-06-12 新-3 已修：M10 plan 增 "Langfuse 链路 4 名同串规范" 节，4 行表 `X-Request-Id` / `request_id` / `trace_id` / `Langfuse trace.id` 语义层差异 + 4 名同值约束 + 跨 M 字段同步清单（M8/M9/M11 plan 应同步对齐） |
| r2-2026-06-12 新-4 已修：装饰器核心机制——Task 5 GREEN 段增 `_retry_safe_trace_update_start_span(name, metadata)` 用 `with langfuse_context.start_as_current_span(name=node_name) as span:` 创建独立 span（不再用 `update_current_observation(name=...)` 覆盖，导致 8 节点顺序执行后只看到 1 个 observation）；节点结束用 `_retry_safe_trace_update_update_span(**kwargs)` 调 `update_current_span`（langfuse 2.50+ 优先，旧版回退 `update_current_observation`） |
| r2-2026-06-12 新-5 已修：`_summarize_node_usage` 加 `if obs is None: return {}` 守卫 + `if not isinstance(usage, dict): continue` 类型检查 + `if not isinstance(usage.get("input"), (int, float)): else 0`（避 mock 边界场景 AttributeError） |
| r2-2026-06-12 新-6 已修：装饰器 `inspect.signature(fn)` 加 `try/except ValueError: has_config = False` 兜底（langchain `@tool` 装饰的 BaseTool 工具函数无 inspectable signature 时假定单参 state） |
| r2-2026-06-12 新-7 已修：集成测试 `test_chat_creates_eight_node_trace` 断言从 `observations 长度 ≥ 8` 过松断言改为精确化——`assertEqual(observations[0].name, "chat_root")` + 8 节点 name 存在性检查（`assertTrue(any(o.name == "load_memory_node" for o in observations))` × 8 节点），避 sample_rate<1.0 或 offline_mode 时误判通过 |
