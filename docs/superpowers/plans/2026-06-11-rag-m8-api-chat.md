# M8 Plan · FastAPI 路由层（/api/chat + /api/sessions + 进度查询 + health）

> 所属：RAG V1 M0–M12 实施路线 · 第 8 步
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §3.3 Query 数据流](../specs/2026-06-10-rag-v1-scope.md#3-数据流) · [§4 API 列表](../specs/2026-06-10-rag-v1-scope.md#4-api-列表) · [§5 错误矩阵](../specs/2026-06-10-rag-v1-scope.md#5-错误矩阵) · [决策 #7](../specs/2026-06-10-rag-v1-scope.md#0-决策总表)
> 上游：[M2 auth 鉴权](./2026-06-10-rag-m2-auth.md) · [M7 LangGraph 7 节点 + checkpointer](./2026-06-10-rag-m7-graph.md)
> 下游：M9 Gradio UI（调 M8 全部端点）· M10 Langfuse 业务级 trace（挂在 graph 节点上，M8 路由透传 trace_id）· M11 RAGAS（直接调 `graph.invoke` 不走 M8）· M12 Hardening（限速中间件挂在 M8 app 实例上）
> 避雷基线：[P0/P1 review 报告](./2026-06-11-rag-plans-review.md)（P0-1 端口冲突 / P0-5 真 PG 集成测试 / P0-10 checkpointer 单一来源 / P1-4 updated_at 走 ORM / P1-6 chat_sessions 复合索引 / P1-11 protected endpoint 鉴权完整 / P1-16 M8 只 import M7 不动 retrieval / P2-6 `app/api/__init__.py` 聚合补完整 / X-3 全局 settings 单例）
> 估时：3 个工作日
> 范本目的：M8 是 RAG 系统的对外门面——把 M7 graph + M2 auth 包成可被 Gradio / 评测 / 第三方调用的 HTTP 端点

---

## Goal

把 v0.4 V1 Scope §3.3 Query 数据流 + §4 API 列表 + §5 错误矩阵落成 FastAPI 路由层：

1. **`POST /api/chat`**：鉴权 → session_id 解析（缺则建 / 有则越权 404） → 调 `graph.ainvoke()` 拿 answer+sources → 返回
2. **`GET /api/sessions` / `GET /api/sessions/{id}`**：列当前用户活跃会话 / 取单个会话详情（越权 404）
3. **`GET /api/ingest/{job_id}`**：查 ingest 进度（POST `/api/ingest` 由 M4-M6 实现，M8 写 stub + 委派约定）
4. **`GET /api/health`**：无鉴权，返 5 service（PG / OpenSearch / TEI / Langfuse / 业务）健康状态
5. **`app/main.py` FastAPI 入口** + **`app/api/__init__.py` 路由聚合** + **5 套 Pydantic schema** + **统一 exception handler（401/404/422/500/502/503）**
6. **`compile_workflow()` lifespan 单例**：启动时建 graph + checkpointer + async context，关闭时 cleanup（**修 P0-2**：lifespan 关闭时 `await engine.dispose()` 归还 asyncpg 连接池）

**不包含**（其他 M 负责）：
- M4-M6 ingest pipeline 写 chunk（POST `/api/ingest` 由它们实现，M8 写 stub 委派，**修 P1-7** 加 `# TODO(m8→m4)` 标记）
- M9 Gradio UI（M8 只产 JSON API）
- M10 Langfuse 业务级 trace（M8 路由透传 `X-Request-Id`，M10 节点上挂 trace）
- M11 RAGAS eval（直接 `graph.ainvoke()`，不走 M8 路由层）
- M12 限速 / 鉴权重启（挂在 M8 已有 app 实例上）

---

## Architecture

### 仓库布局（M8 增量）

```
apps/rag_v1/
├── app/
│   ├── api/                              # M8 主力
│   │   ├── __init__.py                   # APIRouter 聚合（修 P2-6）
│   │   ├── auth.py                       # M2 已建 · re-export
│   │   ├── chat.py                       # M8 新建 · POST /api/chat（修 P0-1 加 asyncio.wait_for 包装）
│   │   ├── sessions.py                   # M8 新建 · GET /api/sessions
│   │   ├── ingest.py                     # M8 新建 · GET /api/ingest/{job_id} + POST stub 委派 M4-M6（修 P1-7）
│   │   ├── health.py                     # M8 新建 · GET /api/health 路由
│   │   ├── health_checks.py              # M8 新建 · 5 service 探测函数（修 P2-2：直接放独立文件，不内联）
│   │   ├── deps.py                       # M8 新建 · 共享 Depends（get_db / get_orchestrator / get_request_id）（修 P1-5）
│   │   ├── errors.py                     # M8 新建 · 自定义异常 + handler 注册
│   │   ├── middleware.py                 # M8 新建 · RequestIdMiddleware（修 P2-5：拆出 main.py）
│   │   └── schemas/                      # M8 新建 · Pydantic 请求/响应（修 P2-1：字段定义完整）
│   │       ├── __init__.py
│   │       ├── chat.py                   # ChatRequest / ChatResponse / Source
│   │       ├── sessions.py               # SessionListItem / SessionListResponse / SessionDetailResponse
│   │       ├── ingest.py                 # IngestProgressResponse / IngestRequest / IngestAcceptedResponse
│   │       └── health.py                 # HealthResponse / ServiceHealth
│   ├── graph/                            # M7 已建 · M8 import
│   │   ├── workflow.py                   # compile_workflow(checkpointer) 同步
│   │   ├── checkpointer.py               # make_checkpointer() -> BaseCheckpointSaver（M7 r1 P0-3 已修：返回实例，非 contextmanager）
│   │   └── errors.py                     # GraphError / RetrievalError（503 转换用）
│   ├── auth/                             # M2 已建 · M8 直接 import
│   │   ├── deps.py                       # get_current_user
│   │   └── service.py
│   ├── db/                               # M1 已建 · 4 表 ORM
│   │   ├── models.py                     # User / ChatSession / AuthSession / IngestJob
│   │   └── session.py                    # async_session / get_session + engine（lifespan 用）
│   ├── memory/                           # M7 已建
│   │   └── thread.py                     # resolve_thread_id（404 越权）
│   ├── config.py                         # M0+M1+M2+M3+M7 累计 · 追加 APISettings（修 P1-1 / P2-4 / P2-8）
│   │                                    # · APISettings.chat_timeout_seconds=30
│   │                                    # · APISettings.default_session_page_size=50
│   │                                    # · APISettings.env=dev/staging/prod（修 P2-8）
│   │                                    # · APISettings.cors_origins / expose_docs
│   │                                    # · HealthSettings.opensearch_url / tei_url / langfuse_url / health_check_timeout
│   │                                    # · GraphSettings.fallback_message（与 M7 P1-2 共用）
│   └── main.py                           # M8 新建 · FastAPI 实例 + lifespan + middleware（修 P0-2 / P2-3 / P2-7 / P2-8）
│
└── tests/
    ├── unit/
    │   ├── test_api_health.py            # M8 · 5 service health 探测（修 P0-3 URL/timeout 具体）
    │   ├── test_api_sessions.py          # M8 · list + detail + 越权 404
    │   ├── test_api_chat.py              # M8 · session_id 缺/有/越权/401/异常 502/超时 502
    │   └── test_api_ingest_progress.py   # M8 · job_id 进度 + 委派 stub
    ├── integration/
    │   └── test_m8_e2e_api.py            # 端到端：login → chat 多轮 → sessions → logout
    └── conftest.py                       # M8 增补 · 真 PG fixture（修 P0-5）+ pg_dsn 注入
```

### 请求响应流程（`POST /api/chat`）

```
client POST /api/chat
  body: { query: "Q3 vs Q4 对比", session_id?: "uuid" }
  header: Authorization: Bearer ***
  │
  ▼
middleware: request_id 注入 X-Request-Id
  │
  ▼
api_router → /api/chat endpoint
  │
  ├─ 1) Depends(get_current_user)          # M2 · 401 if 无效
  │
  ├─ 2) Depends(get_db)                    # M8 · AsyncSession
  │
  ├─ 3) session_id 处理
  │     ├─ None  → INSERT chat_sessions(user_id, thread_id=uuid4())
  │     │         → commit → 用新 thread_id（title 走 safe_truncate 修 P2-6）
  │     └─ str   → 查 chat_sessions(id, user_id)  # 越权 404（不暴露存在性）
  │              → 用 row.thread_id
  │
  ├─ 4) graph_orchestrator.ainvoke(        # lifespan 单例
  │       {"query": ..., "user_id": ..., "thread_id": ...},
  │       config={"configurable": {"thread_id": thread_id},
  │                "callbacks": [<langfuse>],  # M3 工厂已注
  │                "metadata": {"trace_id": X-Request-Id, "request_id": X-Request-Id}}  # 双键：M8→M11 trace_id 关联 + M10 Langfuse request_id 透传（同值）
  │     )                                  # ── 修 P0-1 ──
  │     # ↑ 用 asyncio.wait_for(..., timeout=settings.api.chat_timeout_seconds) 包装
  │     # ↑ TimeoutError → HTTPException(502, "服务超时，请稍后重试。")
  │
  ├─ 5) 异常映射:
  │     - asyncio.TimeoutError → 502（修 P0-1）
  │     - GraphError(llm_4xx/5xx) → 502 Bad Gateway
  │     - RetrievalError(OS 不可达) → 503 + answer 兜底（修 P1-1：fallback_message 走 settings）
  │     - ValueError(schema) → 422 FastAPI 默认
  │     - HTTPException → 透传
  │
  └─ 6) return ChatResponse(answer, sources, session_id, trace_id, degraded)  # 修 r2-新-1：trace_id 字段 = X-Request-Id = Langfuse trace.id 三者同字符串
```

### lifespan 单例

```python
# app/main.py · 草图（修 P0-2 / P2-7 后）
import asyncio
from contextlib import asynccontextmanager
from app.db.session import engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 修 P2-7：启动时建 shutdown_event，health check 端点可感知
    app.state.shutdown_event = asyncio.Event()
    # 启动：建 checkpointer + 编译 graph
    # 注：M7 r1 P0-3 已修 make_checkpointer 为 async def 返回 BaseCheckpointSaver 实例（非 ctx mgr）
    #     M8 调用方负责 lifecycle 关闭（lifespan 末尾 dispose）
    checkpointer = await make_checkpointer()
    app.state.checkpointer = checkpointer
    app.state.graph = compile_workflow(checkpointer=checkpointer)
    try:
        yield
    finally:
        # 修 P2-7：通知 health check 开始返 503，给 in-flight 请求 500ms 缓冲
        app.state.shutdown_event.set()
        await asyncio.sleep(0.5)
        # 修 P0-2：归还 asyncpg 连接池
        await engine.dispose()
        # checkpointer 若有 close() 也调（M7 工厂保证幂等）
        close = getattr(checkpointer, "close", None)
        if close is not None:
            res = close()
            if asyncio.iscoroutine(res):
                await res
```

**M8 特有避雷**（M7 P0-10 修订后 + M7 r1 P0-3 修订后）：
- M7 修 P0-10 后，**唯一** checkpointer 工厂在 `app/graph/checkpointer.py`
- M7 r1 P0-3 修后，`make_checkpointer()` 是普通 `async def` 返回 `BaseCheckpointSaver` **实例**（**不是** `@asynccontextmanager`）
- M8 lifespan 改为 `await make_checkpointer()` + 手动 `dispose`，**不再**用 `async with`
- `app/memory/checkpointer.py` 删了或只放 thread
- M8 严格只 `from app.graph.checkpointer import make_checkpointer`

### Pydantic schema 边界

| 端点 | Request schema | Response schema | 错误码 |
|------|---------------|-----------------|--------|
| POST /api/auth/register | `RegisterRequest`（M2） | `RegisterResponse`（M2） | 409 / 422 |
| POST /api/auth/login | `LoginRequest`（M2） | `LoginResponse`（M2） | 401 |
| POST /api/auth/logout | — | — | 204 |
| GET /api/sessions | — | `SessionListResponse` | 401 |
| GET /api/sessions/{id} | — | `SessionDetailResponse` | 401 / 404 |
| POST /api/chat | `ChatRequest` | `ChatResponse` | 401 / 404 / 422 / 502 / 503 |
| POST /api/ingest | `IngestRequest`（M8 stub） | `IngestAcceptedResponse` | 501 → 委派 M4-M6（修 P1-7） |
| GET /api/ingest/{job_id} | — | `IngestProgressResponse` | 404 |
| GET /api/health | — | `HealthResponse` | 503 |

### M8 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M9 Gradio Chat tab | `POST /api/chat` / `GET /api/sessions` | 走 HTTP JSON |
| M9 Gradio Ingest tab | `POST /api/ingest`（M4-M6 真接）/ `GET /api/ingest/{id}` | M8 路由只透传 POST |
| M10 Langfuse 业务 trace | `X-Request-Id` header 透传 | 节点上挂 trace，M8 不直接注入 |
| M11 RAGAS eval | `graph.ainvoke()` 直接调 | **不走** M8 路由 |
| M12 Hardening | M8 `app/main.py` 加 `app.add_middleware(RateLimitMiddleware, ...)` | 改 main.py 不动 api/ |
| M12 监控 | `GET /api/health` 5 service 状态 | Prometheus scrape 友好 |

### 跨 M 关键依赖（M7 review 交叉验证）

| M7 review ID | 影响 M8 的点 | M8 plan 处理 |
|---|---|---|
| **M7 P0-3** | `make_checkpointer` 是 `@asynccontextmanager` vs 实例 | **M7 r1 已修**：改为 `async def make_checkpointer() -> BaseCheckpointSaver`；M8 lifespan 改为 `await make_checkpointer()` + 手动 dispose（见上 lifespan 段） |
| **M7 P0-4** | graph invoke 缺超时 | **M8 P0-1 已修**：`asyncio.wait_for(graph.ainvoke, timeout=30)` 在 Task 7 GREEN 段 |
| **M7 P0-6** | `answer_chitchat_node` 无实现 | **M7 r1 已修**：补节点实现 + prompt；M8 假设 chitchat 分支可用 |
| **M7 P0-8** | 节点级异常传播 | M8 假设 `GraphError` / `RetrievalError` 异常类已统一（`safe_node` 装饰器已加）；M8 路由 catch 这两类做 502/503 映射 |
| **M7 P1-2** | fallback_message 硬编码 | **M8 P1-1 已修**：M8 路由读 `settings.graph.fallback_message`（与 M7 共用） |
| **M7 r2 新-3 `RagState.trace_id`** | M7 graph 状态应含 `trace_id` 字段供 M8 提取 | **M8 r2 已对齐**：M8 chat 端点从 `result["trace_id"]`（若存在）取；`graph.ainvoke` 额外传 `metadata.trace_id` 兜底（双键）；M7 RagState 与 M8 ChatResponse 字段同名 |
| **M1 r2 4 表 `idempotency_key`** | M8 chat/ingest 端点应消费 Idempotency-Key Header | **M8 r2 已修新-4**：`POST /api/chat` + `POST /api/ingest` stub 都接收 `Idempotency-Key: str \| None = Header(None, alias="Idempotency-Key")`；chat 缺 session_id + 有 idempotency_key 时查重同 user_id + 同 idempotency_key 已有 session 复用 |
| **M9/M10/M11 `trace_id` 字段名统一** | M8 输出 schema 字段名应与跨 M 一致 | **M8 r2 已修新-1**：`ChatResponse` / `HealthResponse` / exception handler response 字段统一 `trace_id`；`RequestIdMiddleware` 内部 `request.state.request_id` 与 `X-Request-Id` Header 名协议级保留；graph.ainvoke metadata 双键（`trace_id` + `request_id`）同字符串不同语义 |
| **M12 r1 P0-1 LIFO middleware 顺序** | M8 add_middleware 注释需 LIFO 警示 | **M8 r2 已修新-5**：Task 13 `create_app` middleware 注释加 LIFO 警示（"后添加的先执行 / 最外层" + "调用顺序 CORS → RequestId → M12 RateLimit" + "执行顺序 M12 RateLimit → RequestId → CORS → endpoint"） |

---

## Tech Stack

| 层 | 选型 | 版本（精确） | 来源 |
|----|------|------------|------|
| Web 框架 | `fastapi` | `>=0.115,<1` | V1 Scope §8.4 |
| ASGI | `uvicorn[standard]` | `>=0.32,<1` | V1 Scope §8.4 |
| 表单 / 上传 | `python-multipart` | `>=0.0.9` | V1 Scope §8.4 |
| 配置 | `pydantic-settings` | `>=2.3,<3` | M0 沿用 |
| 状态 | `pydantic` | `>=2.7,<3` | M1 沿用 |
| 异步驱动 | `asyncpg` | `>=0.29,<1` | M1 沿用 |
| LangGraph | `langgraph` | `==1.0.5` | M7 |
| LLM | `langchain` | `==1.0.8` | M3 |
| HTTP 客户端（health 探测） | `httpx` | `>=0.27,<1` | M3 沿用 |
| 测试 | `pytest` / `pytest-asyncio` / `pytest-httpx` | 见 §测试 | 修 P1-18 |

**关键导入路径**：

```python
# FastAPI
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

# 中间件（修 P2-5：从 main.py 拆出）
from app.api.middleware import RequestIdMiddleware

# Pydantic
from pydantic import BaseModel, Field, ConfigDict

# Pydantic v2 配置
model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

# M8 全局单例
from app.config import settings

# M2 鉴权
from app.auth.deps import get_current_user

# M7 graph（修 M7 r1 P0-3：make_checkpointer 返回实例非 ctx mgr）
from app.graph.workflow import compile_workflow
from app.graph.checkpointer import make_checkpointer  # async def -> BaseCheckpointSaver
from app.graph.errors import GraphError, RetrievalError

# M1 ORM + 引擎（修 P0-2：lifespan 用 engine.dispose()）
from app.db.models import ChatSession
from app.db.session import async_session, get_session, engine

# M7 thread 解析
from app.memory.thread import resolve_thread_id, ThreadNotFound
```

**Python 导入规则**（从 `apps/rag_v1/` 内部）：
- `app.api.chat` —— `app` 是 `apps/rag_v1/app/`
- `tests.unit.test_api_chat` —— 跑测试时 `cd apps/rag_v1 && pytest`

---

## Files

**新增**（16 个源文件 + 5 个测试文件）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
| `app/api/__init__.py` | APIRouter 聚合（修 P2-6） |
| `app/api/chat.py` | `POST /api/chat` 路由 + lifespan orchestrator 包装（**修 P0-1**：`asyncio.wait_for` 包装 graph.ainvoke） |
| `app/api/sessions.py` | `GET /api/sessions` + `GET /api/sessions/{id}`（**修 P1-2**：含 `_count_messages` 实现） |
| `app/api/ingest.py` | `GET /api/ingest/{job_id}` + `POST /api/ingest` stub 委派 M4-M6（**修 P1-7**：`# TODO(m8→m4)` 标记 / **修 r2-新-4**：stub 也接受 Idempotency-Key Header 透传） |
| `app/api/health.py` | `GET /api/health` 路由 + 503 判断（调用 health_checks） |
| `app/api/health_checks.py` | 5 个 `_check_*` 探测函数（**修 P0-3** + **P2-2**：直接放独立文件，URL/timeout 具体） |
| `app/api/deps.py` | `get_db` / `get_orchestrator` / `get_request_id`（**修 P1-3 / P1-4 / P1-5**：get_db 类型注解 / get_orchestrator 删 fallback / 接受 lifespan override 测试） |
| `app/api/errors.py` | `APIError` 体系 + exception handler 注册 |
| `app/api/middleware.py` | `RequestIdMiddleware`（**修 P2-5**：从 main.py 拆出） |
| `app/api/schemas/__init__.py` | schema 暴露 |
| `app/api/schemas/chat.py` | `ChatRequest` / `ChatResponse` / `Source` |
| `app/api/schemas/sessions.py` | `SessionListItem` / `SessionListResponse` / `SessionDetailResponse`（**修 P2-1**：完整字段） |
| `app/api/schemas/ingest.py` | `IngestProgressResponse` / `IngestRequest`（stub） / `IngestAcceptedResponse`（**修 P2-1**：完整字段） |
| `app/api/schemas/health.py` | `HealthResponse` / `ServiceHealth` |
| `app/utils/text.py` | `safe_truncate` UTF-8 byte-aware 工具（**修 P2-6**：session 标题截取） |
| `app/main.py` | FastAPI 实例 + lifespan（**修 P0-2 / P2-3 / P2-7 / P2-8**）+ middleware + exception handler 注册 |
| `tests/unit/test_api_health.py` | 5 service health 探测单测（修 P0-3 URL mock） |
| `tests/unit/test_api_sessions.py` | sessions list/detail + 越权 404 |
| `tests/unit/test_api_chat.py` | chat 鉴权 + session 解析 + 异常 502/503 + **超时 502**（P0-1） |
| `tests/unit/test_api_ingest_progress.py` | 进度查询 + 委派 stub |
| `tests/integration/test_m8_e2e_api.py` | login → chat 多轮 → sessions → logout（真 PG，**修 P0-5**） |
| `tests/conftest.py` | 增补 `pg_session` fixture（真 PG，**修 P0-5**） |

**修改**：
- `pyproject.toml`：追加 `fastapi>=0.115,<1` / `uvicorn[standard]>=0.32,<1` / `python-multipart>=0.0.9` 3 个直接依赖（**修 P0-8**，M0 阶段不装）
- `app/config.py`（M0+M1+M2+M3+M7 累计）：
  - 追加 `APISettings`（**修 P0-1**：`chat_timeout_seconds: int = 30`）
  - 追加 `APISettings.default_session_page_size: int = 50`（**修 P2-4**）
  - 追加 `APISettings.env: Literal["dev","staging","prod"] = "dev"`（**修 P2-8**）
  - 追加 `APISettings.cors_origins: list[str]`（**修 P2-8**：dev=["*"]，prod 受限）
  - 追加 `APISettings.expose_docs: bool`（**修 P2-8**：dev=True，prod=False）
  - 追加 `HealthSettings.opensearch_url / tei_url / langfuse_url / health_check_timeout`（**修 P0-3**）
  - `GraphSettings.fallback_message: str = "检索服务暂不可用，已切换到直答模式。"`（**修 P1-1**：与 M7 P1-2 共用）
- `app/db/models.py`（M1）：确认 `ChatSession` 有 `is_active` / `thread_id` / `updated_at` 字段（M8 走 ORM 更新，**修 P1-4**）；复合索引 `(user_id, is_active, updated_at DESC)` 已在 M1 加（**修 P1-6**）
- `app/db/session.py`（M1）：暴露 `engine` 给 lifespan 用（**修 P0-2**：`engine.dispose()`）
- `app/auth/deps.py`（M2）：`get_current_user` 直接 import，不改 M2 代码

**不修改**：
- `app/graph/workflow.py`（M7）：M8 只 import `compile_workflow`
- `app/graph/checkpointer.py`（M7 修订后唯一来源，**修 P0-10** + **M7 r1 P0-3**：实例非 contextmanager）
- `app/retrieval/`（M7）：M8 不直接动 retrieval（**修 P1-16**）
- `infra/docker-compose.yml`（M0）：FastAPI 默认 8000 与 TEI 18080 不冲突（**修 P0-1**）

---

## Tasks（2-5 分钟/step 粒度）

### Day 1 · health + sessions 路由（无 graph 依赖，先把简单端点跑通）

#### Task 1：Pydantic schema 文件

**RED** · `tests/unit/test_api_health.py::test_service_health_schema_validates`
- 写测试：构造 `ServiceHealth(name="postgres", status="up", latency_ms=12.3, error=None)` → 断言 model_dump() 字段齐
- 跑测试 → 失败

**GREEN** · `app/api/schemas/health.py`（修 r2-新-2：ServiceHealth/HealthResponse 加 `starting` 字面量；修 r2-新-1：HealthResponse 字段统一 `trace_id`）：
```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

class ServiceHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    # 修 r2-新-2：加 starting 状态——lifespan 未启动时 business 服务的中间态
    status: Literal["up", "down", "degraded", "starting"]
    latency_ms: float | None = None
    error: str | None = None

class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 修 r2-新-2：加 starting 状态——lifespan 启动期 / 启动失败时 health 端点返 starting
    status: Literal["ok", "degraded", "down", "starting"]
    services: list[ServiceHealth]
    # 修 r2-新-1：与 M9/M10/M11 跨 M 统一用 trace_id（X-Request-Id = Langfuse trace.id = M11 trace_id 三者同字符串）
    trace_id: str
```

**RED** · `tests/unit/test_api_sessions.py::test_session_list_item_schema`
- 构造 `SessionListItem(id="uuid", title="Q3 收入对比", updated_at=datetime.now(timezone.utc), message_count=4)` → 断言序列化
- 跑测试 → 失败

**GREEN** · `app/api/schemas/sessions.py` + `app/api/schemas/chat.py` + `app/api/schemas/ingest.py` 全部 schema（**修 P2-1**：所有 Response schema 字段完整定义）

```python
# app/api/schemas/sessions.py（修 P2-1：完整字段）
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class SessionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    updated_at: datetime
    message_count: int

class SessionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessions: list[SessionListItem]
    total: int

class SessionDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    thread_id: str
    messages: list = []  # M10 后从 checkpoint 读 history 填充
    created_at: datetime
    updated_at: datetime

# app/api/schemas/ingest.py（修 P2-1：完整字段）
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class IngestProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: str
    progress: float | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

class IngestRequest(BaseModel):
    """M8 stub：实际 ingest 入参 schema 由 M4-M6 定义"""
    model_config = ConfigDict(extra="forbid")
    source: str  # file path / URL / confluence page id

class IngestAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: str = "accepted"
```

**REFACTOR** · 抽出 schema 共享 mixin（`TimestampMixin` / `RequestIdMixin`）

#### Task 2：`GET /api/health` 端点（无鉴权）+ 5 service 探测（**修 P0-3 + P2-2**）

**RED** · `tests/unit/test_api_health.py::test_health_returns_200_when_all_up`
- mock httpx（mock 5 个具体 URL：PG session / OS `/_cluster/health` / TEI `/health` / Langfuse `/api/public/health` / 业务检查）→ 全部 up → `GET /api/health` → 200 + `status="ok"`
- 跑测试 → 失败

**GREEN** · `app/api/health_checks.py`（**修 P2-2**：5 个 `_check_*` 函数直接放独立文件，URL/timeout 具体化）：

```python
# app/api/health_checks.py（修 P0-3 + P2-2：URL/timeout/auth 具体）
import asyncio
import time
import httpx
from sqlalchemy import text
from app.config import settings
from app.db.session import async_session
from app.api.schemas.health import ServiceHealth


async def _check_postgres() -> ServiceHealth:
    """PG 业务 DB：SELECT 1 探活"""
    t0 = time.perf_counter()
    try:
        async with async_session() as s:
            await s.execute(text("SELECT 1"))
        return ServiceHealth(
            name="postgres",
            status="up",
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as e:
        return ServiceHealth(name="postgres", status="down", error=str(e))


async def _check_opensearch() -> ServiceHealth:
    """OpenSearch cluster health：GET /_cluster/health?wait_for_status=yellow&timeout=2s"""
    t0 = time.perf_counter()
    url = settings.health.opensearch_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.health.health_check_timeout) as client:
            resp = await client.get(
                f"{url}/_cluster/health?wait_for_status=yellow&timeout=2s"
            )
            resp.raise_for_status()
            data = resp.json()
            # cluster_status: green/yellow/red → yellow 以上视为 up
            cluster_status = data.get("status", "red")
            if cluster_status in ("green", "yellow"):
                return ServiceHealth(
                    name="opensearch",
                    status="up",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            return ServiceHealth(
                name="opensearch",
                status="degraded",
                latency_ms=(time.perf_counter() - t0) * 1000,
                error=f"cluster_status={cluster_status}",
            )
    except Exception as e:
        return ServiceHealth(name="opensearch", status="down", error=str(e))


async def _check_tei() -> ServiceHealth:
    """TEI embedding service：GET /health（M0 端口 18080）"""
    t0 = time.perf_counter()
    url = settings.health.tei_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.health.health_check_timeout) as client:
            resp = await client.get(f"{url}/health")
            resp.raise_for_status()
        return ServiceHealth(
            name="tei",
            status="up",
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as e:
        return ServiceHealth(name="tei", status="down", error=str(e))


async def _check_langfuse() -> ServiceHealth:
    """Langfuse public health：GET /api/public/health（无需 auth）"""
    t0 = time.perf_counter()
    url = settings.health.langfuse_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.health.health_check_timeout) as client:
            resp = await client.get(f"{url}/api/public/health")
            resp.raise_for_status()
        return ServiceHealth(
            name="langfuse",
            status="up",
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as e:
        return ServiceHealth(name="langfuse", status="down", error=str(e))


async def _check_business(app) -> ServiceHealth:
    """业务健康：graph 编译过 + checkpointer 活着（M8 lifespan 已建）

    修 r2-新-2：直接读 app.state（startup 期间 / 启动失败时返 starting 而非 down）
    """
    t0 = time.perf_counter()
    try:
        graph = getattr(app.state, "graph", None)
        cp = getattr(app.state, "checkpointer", None)
        if graph is None or cp is None:
            # 修 r2-新-2：lifespan 未启动期 = starting（中间态，不算 down）
            return ServiceHealth(
                name="business",
                status="starting",
                latency_ms=0.0,
                error="lifespan initializing" if graph is None else "checkpointer initializing",
            )
        return ServiceHealth(
            name="business",
            status="up",
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as e:
        return ServiceHealth(name="business", status="down", error=str(e))


async def check_all(app) -> list[ServiceHealth]:
    """5 service 并行探测；business 检查依赖 app.state（lifespan 状态）

    修 r2-新-2：5 service 并行 gather + business 探针内部直接读 app.state，
    统一在 _check_business 内做 starting/up/down 判定；外层不再做脏数据二次判定。
    """
    pg, os_, tei, lf, business = await asyncio.gather(
        _check_postgres(),
        _check_opensearch(),
        _check_tei(),
        _check_langfuse(),
        _check_business(app),  # 修 r2-新-2：app 注入 business 探针
        return_exceptions=False,
    )
    return [pg, os_, tei, lf, business]
```

**GREEN** · `app/api/health.py` 路由（修 r2-新-2：starting 状态判定；修 r2-新-1：trace_id 字段统一）：
```python
from fastapi import APIRouter, Request
from app.api.schemas.health import HealthResponse, ServiceHealth
from app.api.health_checks import check_all

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    # 修 r2-新-1：response 字段 trace_id（与 M9/M10/M11 跨 M 统一）
    trace_id = getattr(request.state, "request_id", "")
    # 修 P2-7：lifespan 关闭中 → health 返 503
    shutdown_event = getattr(request.app.state, "shutdown_event", None)
    if shutdown_event is not None and shutdown_event.is_set():
        return _degraded_response(trace_id, error="shutting_down")
    services = await check_all(request.app)
    up_count = sum(1 for s in services if s.status == "up")
    starting_count = sum(1 for s in services if s.status == "starting")
    # 修 r2-新-2：starting 优先级最高（lifespan 未完成 → 503 starting）
    if starting_count > 0:
        overall = "starting"
    elif up_count == len(services):
        overall = "ok"
    elif up_count > 0:
        overall = "degraded"
    else:
        overall = "down"
    resp = HealthResponse(status=overall, services=services, trace_id=trace_id)  # 修 r2-新-1
    if overall != "ok":
        from fastapi.responses import JSONResponse
        # 修 r2-新-2：starting / down 都返 503（启动未完成 ≠ ok）
        return JSONResponse(status_code=503, content=resp.model_dump(mode="json"))
    return resp


def _degraded_response(trace_id: str, error: str):  # 修 r2-新-1：参数名 trace_id
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=503,
        content={
            "status": "down",
            "services": [
                ServiceHealth(name=s, status="down", error=error)
                for s in ["postgres", "opensearch", "tei", "langfuse", "business"]
            ],
            "trace_id": trace_id,  # 修 r2-新-1
        },
    )
```

**RED** · `test_health_returns_503_when_pg_down`（任一 down）
- mock DB 抛异常 → 调 → 断言 HTTP 503 + `status="degraded"`
- 跑测试 → 失败

**GREEN** · 上面 health.py 已用 `JSONResponse(status_code=503, ...)` 在 `overall != "ok"` 时返 503

#### Task 3：`RequestIdMiddleware` 拆到独立文件（**修 P2-5**）

**RED** · `tests/unit/test_api_health.py::test_request_id_generated_when_absent`
- `GET /api/health` 不带 header → 响应 header `X-Request-Id` 非空（uuid4）
- 跑测试 → 失败

**GREEN** · `app/api/middleware.py`（**修 P2-5**：从 main.py 拆出）：
```python
# app/api/middleware.py（修 P2-5 + r2-新-1 注释补充）
from starlette.middleware.base import BaseHTTPMiddleware
import uuid

class RequestIdMiddleware(BaseHTTPMiddleware):
    """注入 / 透传 X-Request-Id，用于 M10 Langfuse 业务 trace 关联

    修 r2-新-1 注释：request.state.request_id 内部名 = X-Request-Id Header = Langfuse trace.id
    = M8 ChatResponse.trace_id 字段 = M11 eval trace_id，五者同字符串，仅展示层命名差异。
    """
    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = rid  # 协议级内部名：保留 request_id（与 X-Request-Id Header 对称）
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response
```

`app/main.py` 改为 `from app.api.middleware import RequestIdMiddleware`（L809）。

**RED** · `test_request_id_echoed_when_present`
- client 送 `X-Request-Id: foo-123` → 响应 header 同值
- 跑测试 → 失败
**GREEN** · 读 header 优先级（已有）

#### Task 4：`GET /api/sessions` 列表（**修 P1-2 + P2-4**）

**RED** · `tests/unit/test_api_sessions.py::test_list_returns_only_current_user_sessions`
- mock DB：用户 A 2 条 + 用户 B 1 条 → 用 A 鉴权调 `GET /api/sessions` → 断言返 2 条
- 跑测试 → 失败

**GREEN** · `app/api/sessions.py`（**修 P1-2**：含 `_count_messages` 实现 / **修 P2-4**：`limit(settings.api.default_session_page_size)`）：
```python
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.db.models import User, ChatSession, Message
from app.db.session import get_session
from app.api.schemas.sessions import SessionListItem, SessionListResponse
from app.config import settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


async def _count_messages(db: AsyncSession, session_id: str) -> int:
    """单条 session 的消息数（修 P1-2：补实现）"""
    stmt = select(func.count()).select_from(Message).where(Message.session_id == session_id)
    result = await db.execute(stmt)
    return result.scalar() or 0


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> SessionListResponse:
    # 依赖 P1-6 复合索引 (user_id, is_active, updated_at DESC)
    # 修 P1-6：加 deleted_at IS NULL 软删除过滤（M1 schema 若有 deleted_at 列）
    stmt = (
        select(ChatSession)
        .where(
            ChatSession.user_id == current_user.id,
            ChatSession.is_active == True,
            ChatSession.deleted_at.is_(None),  # 修 P1-6 软删除过滤
        )
        .order_by(ChatSession.updated_at.desc())
        .limit(settings.api.default_session_page_size)  # 修 P2-4：可配置
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        SessionListItem(
            id=str(r.id),
            title=r.title or "新对话",
            updated_at=r.updated_at,
            message_count=await _count_messages(db, r.id),
        )
        for r in rows
    ]
    return SessionListResponse(sessions=items, total=len(items))
```

**RED** · `test_list_returns_401_when_unauthenticated`
- 无 token → 调 → 401
- 跑测试 → 失败

**GREEN** · M2 `get_current_user` 已处理 401

**RED** · `test_list_excludes_inactive_sessions`
- 1 active + 1 inactive → 调 → 断言返 1 条
- 跑测试 → 失败

**GREEN** · 加 `is_active == True` 过滤

**REFACTOR** · 把 N+1 的 `_count_messages` 改为单 SQL `select(ChatSession, func.count(Message.id))` + `outerjoin` + `group_by(ChatSession.id)` 一次出数

#### Task 5：`GET /api/sessions/{id}` 详情 + 越权 404

**RED** · `tests/unit/test_api_sessions.py::test_detail_returns_session_for_owner`
- session 属于 current_user → 调 → 200 + 详情
- 跑测试 → 失败

**GREEN** · `app/api/sessions.py` 加 `@router.get("/{session_id}")`：
```python
@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> SessionDetailResponse:
    # 关键：user_id 一起查，越权 404 不暴露存在性（V1 Scope §5）
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionDetailResponse(
        id=str(row.id),
        title=row.title or "新对话",
        thread_id=row.thread_id,
        messages=[],  # M10 后从 checkpoint 读
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
```

**RED** · `test_detail_returns_404_for_other_user_session`（P1-11 关键）
- session 属于用户 B → 用 A 鉴权调 → 404（**不是** 403，避免暴露存在性）
- 跑测试 → 失败

**GREEN** · 上面 SQL 已含 `user_id == current_user.id`，自然 404

**RED** · `test_detail_returns_404_for_nonexistent_session`
- 不存在 id → 404
- 跑测试 → 失败

**GREEN** · 已有 GREEN 路径

### Day 2 · chat 路由 + lifespan orchestrator（核心路径）

#### Task 6：`compile_workflow` 异步 lifespan 包装（**修 P1-3 / P1-4 / P1-5**）

**RED** · `tests/unit/test_api_chat.py::test_orchestrator_returns_lifespan_graph`
- 用 `app.state.graph` fixture → 断言 `isinstance(graph, CompiledStateGraph)`
- 跑测试 → 失败

**GREEN** · `app/api/deps.py`（**修 P1-3**：删 fallback 路径，未初始化时显式 503；**修 P1-5**：`get_db` 显式 `AsyncSession` 类型注解）：
```python
# app/api/deps.py（修 P1-3 / P1-5）
from fastapi import Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.graph import CompiledStateGraph
from app.db.session import get_session as _get_session


async def get_db() -> AsyncSession:
    """FastAPI Depends：每个请求一个 AsyncSession（修 P1-5 显式类型注解）"""
    async with _get_session() as session:
        yield session


async def get_orchestrator(request: Request) -> CompiledStateGraph:
    """lifespan 单例 graph；未初始化时显式 503（修 P1-3：删 fallback 避免连接泄漏）"""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务尚未就绪，请稍后重试。",
        )
    return graph


async def get_request_id(request: Request) -> str:
    """X-Request-Id 由 RequestIdMiddleware 注入"""
    return getattr(request.state, "request_id", "")


def get_app(request: Request):
    """测试 / 中间件用：取 app 实例（lifespan override 测试需要）"""
    return request.app
```

**RED** · `test_orchestrator_returns_503_when_app_state_missing`（**修 P1-4**：可测试 fallback）
- 用 `create_app(lifespan_override=noop_lifespan)` 启动 → 调 `get_orchestrator` → 断言 503
- 跑测试 → 失败

**GREEN** · 上面 `get_orchestrator` 已显式 raise 503

**REFACTOR** · 把 `get_orchestrator` 显式 raise 503 的逻辑抽到 `app/api/errors.py` 的 `ServiceNotReadyError`

#### Task 7：`POST /api/chat` 主体（**修 P0-1 / P1-1 / P1-6**）

**RED** · `tests/unit/test_api_chat.py::test_chat_returns_401_when_unauthenticated`（P1-11 关键）
- 无 token → 调 → 401
- 跑测试 → 失败

**GREEN** · M2 `get_current_user` 已处理；先建 `app/api/chat.py` 空 router + endpoint stub

**RED** · `test_chat_creates_new_session_when_session_id_absent`
- 不传 session_id + mock graph.ainvoke → 调 → 断言 `db` 新增 1 条 `ChatSession`（user_id=current_user, thread_id=uuid4）+ response.session_id 非空
- 跑测试 → 失败

**RED** · `test_chat_returns_502_on_timeout`（**修 P0-1 关键测试**）
- mock graph.ainvoke `await asyncio.sleep(60)` → 调 → 断言 502 + `detail="服务超时，请稍后重试。"`
- 跑测试 → 失败

**GREEN** · `app/api/chat.py`（**修 P0-1**：`asyncio.wait_for` 包装 graph.ainvoke / **修 P1-1**：`fallback_message` 走 settings / **修 P2-6**：`safe_truncate` UTF-8 byte-aware / **修 r2-新-1**：`ChatResponse.trace_id` 字段名 / **修 r2-新-4**：`Idempotency-Key` Header 透传 + 同 user_id + 同 idempotency_key 复用 session）：

```python
import asyncio
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Request  # 修 r2-新-4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.db.models import User, ChatSession
from app.db.session import get_session
from app.api.deps import get_orchestrator
from app.api.schemas.chat import ChatRequest, ChatResponse, Source
from app.utils.text import safe_truncate  # 修 P2-6
from app.config import settings
from app.graph.errors import GraphError, RetrievalError
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    # 修 r2-新-4：M8 端显式接受 Idempotency-Key Header 透传到业务层（M1 r2 4 表 idempotency_key 联动）
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    graph = Depends(get_orchestrator),
) -> ChatResponse:
    # 修 r2-新-1：内部变量名 trace_id（与 ChatResponse 字段名一致）
    trace_id = getattr(request.state, "request_id", "")
    thread_id: str | None = None
    session_id: str | None = None

    if req.session_id is None:
        # 修 r2-新-4：缺 session_id + 有 idempotency_key → 查重同 user_id + 同 idempotency_key 的已有 session
        if idempotency_key is not None:
            dup_stmt = select(ChatSession).where(
                ChatSession.user_id == current_user.id,
                ChatSession.idempotency_key == idempotency_key,  # M1 r2 已建 idempotency_key 列
            )
            existing = (await db.execute(dup_stmt)).scalar_one_or_none()
            if existing is not None:
                # 命中：复用已有 session（防止 M9 Gradio UI 双击产生重复 session）
                thread_id = existing.thread_id
                session_id = str(existing.id)
        if thread_id is None:
            # 新会话（修 P2-6：safe_truncate UTF-8 byte-aware）
            new_session = ChatSession(
                user_id=current_user.id,
                thread_id=str(uuid.uuid4()),
                title=safe_truncate(req.query.strip().replace("\n", " "), 50),
                # 修 r2-新-4：写 idempotency_key 到 DB（NULL = 无幂等保护）
                idempotency_key=idempotency_key,
            )
            db.add(new_session)
            await db.commit()
            await db.refresh(new_session)
            thread_id = new_session.thread_id
            session_id = str(new_session.id)
    else:
        # 已有会话 + 越权 404（不暴露存在性）
        stmt = select(ChatSession).where(
            ChatSession.id == req.session_id,
            ChatSession.user_id == current_user.id,
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="session not found")
        thread_id = row.thread_id
        session_id = str(row.id)

    # 调 graph ── 修 P0-1 ── asyncio.wait_for 包装 + settings.chat_timeout_seconds
    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
                {"query": req.query, "user_id": str(current_user.id), "thread_id": thread_id},
                config={
                    "configurable": {"thread_id": thread_id},
                    # 修 r2-新-1：双键 metadata（trace_id 供 M11 eval / request_id 供 M10 Langfuse）—— 同字符串不同语义
                    "metadata": {
                        "trace_id": trace_id,  # M8→M11 跨 M 关联
                        "request_id": trace_id,  # M8→M10 Langfuse 关联（与 X-Request-Id 同值）
                        "user_id": str(current_user.id),
                    },
                },
            ),
            timeout=settings.api.chat_timeout_seconds,  # 默认 30s
        )
    except asyncio.TimeoutError:
        # 修 P0-1：超时返 502
        log.warning("graph.ainvoke timeout", trace_id=trace_id, timeout=settings.api.chat_timeout_seconds)
        raise HTTPException(status_code=502, detail="服务超时，请稍后重试。")
    except GraphError as e:
        raise HTTPException(status_code=502, detail=f"upstream LLM error: {e}")
    except RetrievalError as e:
        # 503 + 兜底（V1 Scope §5 OS 不可达 → query 走纯 LLM）—— 修 P1-1：fallback_message 走 settings
        log.warning("retrieval degraded", error=str(e), trace_id=trace_id)
        return ChatResponse(
            answer=settings.graph.fallback_message,
            sources=[],
            session_id=session_id,
            # 修 r2-新-1：ChatResponse 字段 trace_id（与 M9/M10/M11 跨 M 统一）
            trace_id=trace_id,
            degraded=True,
        )

    return ChatResponse(
        answer=result["answer"],
        sources=[Source(**s) for s in result.get("sources", [])],
        session_id=session_id,
        # 修 r2-新-1 + r2 跨 M 联动：ChatResponse 字段 trace_id 优先从 M7 RagState.trace_id 取（result.get("trace_id")），fallback 到内部变量（与 X-Request-Id 同值）
        trace_id=result.get("trace_id") or trace_id,
        degraded=False,
    )
```

**GREEN** · `app/utils/text.py`（**修 P2-6**：UTF-8 byte-aware 截取）：
```python
# app/utils/text.py（修 P2-6）
def safe_truncate(text: str, max_bytes: int = 100) -> str:
    """按 UTF-8 byte length 截取，不截断在 multi-byte 中间（emoji / surrogate safe）"""
    encoded = text.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore")
```

**RED** · `test_chat_reuses_existing_thread_on_second_call`（多轮 thread 复用）
- 第 1 次 chat（无 session_id）→ 拿 session_id
- 第 2 次 chat 带 session_id + mock graph.ainvoke → 断言**同 thread_id** 传入 config
- 跑测试 → 失败

**GREEN** · 已有 GREEN 路径；mock graph 断言 `config["configurable"]["thread_id"] == row.thread_id`

**RED** · `test_chat_returns_404_for_other_user_session`（越权不暴露）
- 拿 B 的 session_id + A 鉴权 → 调 → 404
- 跑测试 → 失败

**GREEN** · 已有 GREEN 路径

**RED** · `test_chat_returns_502_on_graph_error`
- mock graph.ainvoke 抛 `GraphError("anthropic 503")` → 调 → 502 + body 含 "upstream"
- 跑测试 → 失败

**GREEN** · try/except GraphError → HTTPException 502

**RED** · `test_chat_returns_503_with_fallback_on_retrieval_error`
- mock graph.ainvoke 抛 `RetrievalError` → 调 → 200 + `degraded=True` + 兜底文案
- 跑测试 → 失败

**GREEN** · 已有 GREEN 路径

**RED** · `test_chat_validates_query_length`（422 边界）
- 传 `query=""` → 422（FastAPI 默认 schema 校验）
- 跑测试 → 失败

**GREEN** · `ChatRequest` schema 已有 `Field(min_length=1, max_length=2000)`

#### Task 8：ChatRequest / ChatResponse Pydantic schema

**RED** · `tests/unit/test_api_chat.py::test_chat_request_rejects_empty_query`
- 构造 `ChatRequest(query="")` → 抛 ValidationError
- 跑测试 → 失败

**GREEN** · `app/api/schemas/chat.py`：
```python
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, description="缺则新建会话")

class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    doc_id: str
    image_ref: str | None = None
    score: float

class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    sources: list[Source]
    session_id: str
    # 修 r2-新-1：trace_id 字段统一（与 M9/M10/M11 跨 M 一致；X-Request-Id = Langfuse trace.id = M11 trace_id 三者同字符串）
    trace_id: str
    degraded: bool = False
```

**RED** · `test_chat_request_rejects_extra_fields`
- 构造 `ChatRequest(query="hi", evil="x")` → ValidationError
- 跑测试 → 失败

**GREEN** · `extra="forbid"` 已有

#### Task 9：统一 exception handler

**RED** · `tests/unit/test_api_chat.py::test_validation_error_returns_422_with_field_detail`
- POST body `{"query": ""}` → 422 + body `{"detail": [{"loc": ["body", "query"], "msg": "..."}], "trace_id": "..."}`  # 修 r2-新-1
- 跑测试 → 失败

**GREEN** · `app/main.py` 注册（修 r2-新-1：response 字段统一 trace_id）：
```python
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "trace_id": getattr(request.state, "request_id", "")},  # 修 r2-新-1
    )
```

**RED** · `test_generic_exception_returns_500_without_stacktrace`
- endpoint 抛 `RuntimeError("boom")` → 调 → 500 + body `{"detail": "internal error", "trace_id": "..."}`（**不暴露** stacktrace）  # 修 r2-新-1
- 跑测试 → 失败

**GREEN** · `@app.exception_handler(Exception)` 兜底 + log.error

**REFACTOR** · 抽 `app/api/errors.py` 集中定义 `APIError` 类 + handler 注册函数 `register_exception_handlers(app)`

### Day 3 · ingest + 集成测试 + main.py 收尾

#### Task 10：`GET /api/ingest/{job_id}` 进度查询

**RED** · `tests/unit/test_api_ingest_progress.py::test_progress_returns_status_for_owner`
- mock `ingest_jobs` 表 → 调 `GET /api/ingest/{job_id}` → 200 + `status="processing"` + `progress=0.45`
- 跑测试 → 失败

**GREEN** · `app/api/ingest.py`：
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.db.models import User, IngestJob
from app.db.session import get_session
from app.api.schemas.ingest import IngestProgressResponse

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.get("/{job_id}", response_model=IngestProgressResponse)
async def get_ingest_progress(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> IngestProgressResponse:
    stmt = select(IngestJob).where(
        IngestJob.id == job_id,
        IngestJob.user_id == current_user.id,  # 越权 404
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return IngestProgressResponse(
        job_id=str(row.id),
        status=row.status,
        progress=row.progress,
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
```

**RED** · `test_progress_returns_404_for_other_user_job`
- 越权 → 404
- 跑测试 → 失败

**GREEN** · 已有 GREEN 路径

**RED** · `test_progress_returns_404_for_nonexistent_job`
- 不存在 → 404
- 跑测试 → 失败

**GREEN** · 已有 GREEN 路径

#### Task 11：`POST /api/ingest` stub 委派（**修 P1-7**）

**RED** · `tests/unit/test_api_ingest_progress.py::test_post_ingest_returns_501_with_deferred_message`
- POST `POST /api/ingest` body → 501 + `detail="POST /api/ingest 由 M4-M6 实现，当前里程碑 stub"`（用 501 Not Implemented 明确占位，**不静默 200**）
- 跑测试 → 失败

**GREEN** · `app/api/ingest.py` 加 stub（**修 P1-7**：加 `# TODO(m8→m4)` 标记 / **修 r2-新-4**：stub 也接受 Idempotency-Key Header 透传，未来 M4-M6 替换为真实 ingest 入口时保留 Header）：
```python
from app.api.schemas.ingest import IngestRequest, IngestAcceptedResponse
from fastapi import Header, HTTPException  # 修 r2-新-4

@router.post("", response_model=IngestAcceptedResponse, status_code=501)
async def post_ingest_stub(
    req: IngestRequest,
    # 修 r2-新-4：M8 stub 端先接受 Idempotency-Key Header（虽然 stub 不写 DB，但 API 契约已定）
    # M4-M6 替换为真实 ingest 时直接复用此 Header → IngestJob.idempotency_key 落库
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """M8 占位：M4-M6 落地后替换为真实 ingest 入口。

    TODO(m8→m4): 合并 M4-M6 时删除本 stub handler，将 IngestRequest 替换为真实 schema
    并接入 M4 file ingest / M5 URL ingest / M6 confluence ingest 三个子入口。
    Idempotency-Key Header 透传契约保留（修 r2-新-4 联动 M1 r2 4 表 idempotency_key）。
    grep 关键词：TODO(m8→m4)
    """
    raise HTTPException(
        status_code=501,
        detail="POST /api/ingest 由 M4-M6 ingest pipeline 实现，当前里程碑 stub。M8 路由仅透传 GET 进度。",
    )
```

#### Task 12：`app/api/__init__.py` 聚合（**修 P2-6**）

**RED** · `tests/unit/test_api_chat.py::test_router_exposes_all_endpoints`
- `from app.api import api_router` → 断言 `api_router.routes` 含 `/chat` / `/sessions` / `/health` / `/ingest` 4 个 prefix 路径
- 跑测试 → 失败

**GREEN** · `app/api/__init__.py`：
```python
from fastapi import APIRouter
from app.api import auth, chat, sessions, ingest, health

api_router = APIRouter()
api_router.include_router(auth.router)       # M2 /api/auth/*
api_router.include_router(chat.router)       # M8 /api/chat
api_router.include_router(sessions.router)   # M8 /api/sessions/*
api_router.include_router(ingest.router)     # M8 /api/ingest/*
api_router.include_router(health.router)     # M8 /api/health
```

**RED** · `test_router_health_path_is_unauthenticated`
- 不带 token 调 `GET /api/health` → 200（**不是** 401）
- 跑测试 → 失败

**GREEN** · health router 不用 `Depends(get_current_user)`

#### Task 13：`app/main.py` 入口（**修 P0-2 / P2-3 / P2-5 / P2-7 / P2-8**）

**RED** · `tests/integration/test_m8_e2e_api.py::test_app_starts_with_lifespan`
- `from app.main import app` → 用 `TestClient` 启动 → 调 `GET /api/health` → 200（验证 lifespan 跑过）
- 跑测试 → 失败

**GREEN** · `app/main.py`（**修 P0-2**：lifespan 关闭 `engine.dispose()` / **修 P2-3**：middleware 顺序注释 / **修 P2-5**：从 `app.api.middleware` import / **修 P2-7**：shutdown_event + 缓冲 / **修 P2-8**：`docs_url`/`cors_origins` 受 `env` 控制）：

```python
import asyncio
import logging  # 修 r2-新-3：graph close 失败时记 log
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
from app.api.middleware import RequestIdMiddleware  # 修 P2-5：从独立文件 import
from app.api.errors import register_exception_handlers
from app.config import settings
from app.db.session import engine  # 修 P0-2：lifespan 关闭用
from app.graph.checkpointer import make_checkpointer  # M7 r1：async def 返回实例
from app.graph.workflow import compile_workflow

log = logging.getLogger(__name__)  # 修 r2-新-3


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 修 P2-7：启动建 shutdown_event，health check 端点可感知
    app.state.shutdown_event = asyncio.Event()
    # 启动：建 checkpointer + 编译 graph
    # 注：M7 r1 P0-3 已修 make_checkpointer 为 async def 返回 BaseCheckpointSaver 实例
    #     lifecycle 由 M8 管理（lifespan 末尾 dispose）
    checkpointer = await make_checkpointer()
    app.state.checkpointer = checkpointer
    app.state.graph = compile_workflow(checkpointer=checkpointer)
    try:
        yield
    finally:
        # 修 P2-7：通知 health check 开始返 503 + 给 in-flight 请求 500ms 缓冲
        app.state.shutdown_event.set()
        await asyncio.sleep(0.5)
        # 修 r2-新-3：graph 自身幂等清理（langgraph 1.0.5 CompiledStateGraph 若有 aclose/close 调之；无则 fallback GC）
        try:
            graph = getattr(app.state, "graph", None)
            if graph is not None:
                aclose = getattr(graph, "aclose", None) or getattr(graph, "close", None)
                if aclose is not None:
                    res = aclose()
                    if asyncio.iscoroutine(res):
                        await res
        except Exception as e:  # 兜底：graph.close 失败不影响 engine.dispose
            log.warning("graph close on shutdown failed", error=str(e))
        # 修 P0-2：归还 asyncpg 连接池
        await engine.dispose()
        # checkpointer 幂等关闭（M7 工厂保证）
        close = getattr(checkpointer, "close", None)
        if close is not None:
            res = close()
            if asyncio.iscoroutine(res):
                await res


def create_app(lifespan_override=None) -> FastAPI:
    """FastAPI 工厂；lifespan_override 用于测试（修 P1-4）"""
    app = FastAPI(
        title="RAG V1",
        version="0.1.0",
        lifespan=lifespan_override or lifespan,  # 修 P1-4：可注入测试 lifespan
        # 修 P2-8：dev 暴露 /docs + redoc，prod/staging 关闭
        docs_url="/docs" if settings.api.expose_docs else None,
        redoc_url="/redoc" if settings.api.expose_docs else None,
        openapi_url="/openapi.json" if settings.api.expose_docs else None,
    )
    # 修 P2-3 + r2-新-5：middleware 挂载顺序（LIFO 警示）
    # FastAPI add_middleware 是 LIFO（后添加的先执行 / 最外层）
    # 调用顺序：CORS（最内层，先 add）→ RequestId（中间层）→ M12 RateLimit（最外层，最后 add）
    # 执行顺序：M12 RateLimit → RequestId → CORS → endpoint
    # 1. CORS 内层：处理 OPTIONS preflight（不依赖 tracing）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # 允许 M9 Gradio 前端 / M11 eval 脚本带 X-Request-Id 调用
        expose_headers=["X-Request-Id"],
    )
    # 2. RequestId 中间层：所有后续中间件 / 路由可读 request_id
    app.add_middleware(RequestIdMiddleware)
    # ↓ future: RateLimitMiddleware (M12)  # 3. M12 加在最外层：依赖 request_id for per-user limit
    app.include_router(api_router)
    register_exception_handlers(app)
    return app


app = create_app()
```

**RED** · `test_lifespan_cleanup_on_shutdown`
- 用 `TestClient` 上下文 → exit 后 → 断言 checkpointer 关闭 + engine dispose
- 跑测试 → 失败

**GREEN** · `finally: shutdown_event.set() + sleep(0.5) + engine.dispose()` + checkpointer.close()

**REFACTOR** · `create_app(lifespan_override=...)` 工厂模式已实现

#### Task 14：集成测试端到端（**修 P0-5 · 必须用真 PG**）

**RED** · `tests/integration/test_m8_e2e_api.py::test_login_chat_sessions_logout_flow`
- 真 PG fixture 起 alembic 4 表
- `POST /api/auth/register` → 拿 token
- `POST /api/chat`（无 session_id）→ 拿 session_id
- `POST /api/chat`（带 session_id + 含"刚才"）→ mock graph 走 chitchat
- `GET /api/sessions` → 列表含刚才 1 条
- `GET /api/sessions/{id}` → 详情
- `POST /api/auth/logout` → 204
- 跑测试 → 失败
- **不跑 sqlite**，必须 `pytest --require-docker` 起真 PG（**修 P0-5**）

**GREEN** · `tests/conftest.py` 增补：
```python
import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import make_url

@pytest.fixture(scope="session")
def pg_dsn():
    # CI 环境跑前 `docker compose -f infra/docker-compose.yml up -d postgres`
    return os.environ.get(
        "ASYNC_POSTGRES_DSN",
        "postgresql+asyncpg://rag_app:rag_app_password@localhost:5432/rag_test",
    )

@pytest.fixture
async def db_engine(pg_dsn):
    from app.db.session import engine
    engine.url = make_url(pg_dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
```

**RED** · `test_e2e_chat_thread_reuse_via_real_graph`（**M7 P0-10 修订后** + 真实 graph）
- 不 mock graph，用 `compile_workflow` + mock LLM/embed/OS（langgraph.ainvoke 真跑）
- 2 次 invoke 同 thread_id → 第二次拿得到第一次的 history
- 跑测试 → 失败

**GREEN** · 用 `pytest-httpx` mock 外部 HTTP（TEI / OS / Langfuse）

**RED** · `test_e2e_chat_returns_404_on_unauthorized_session`
- 注册 2 个用户 A / B → A chat 拿 session → B 用自己 token 调 A 的 session_id → 404
- 跑测试 → 失败

**GREEN** · 已有 GREEN 路径

**RED** · `test_e2e_health_returns_real_pg_status`
- 真 PG up → `GET /api/health` → 200 + postgres status="up" + latency_ms 数值
- 跑测试 → 失败

**GREEN** · 已有 GREEN 路径

**REFACTOR** · 把 e2e 拆 4 个小测试（register_flow / chat_flow / sessions_flow / auth_negative）

---

## 测试策略

- **M8 单元**：`cd apps/rag_v1 && pytest tests/unit/test_api_health.py tests/unit/test_api_sessions.py tests/unit/test_api_chat.py tests/unit/test_api_ingest_progress.py` —— 全 mock DB / graph / httpx，CI 内 3s
- **M8 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m8_e2e_api.py --require-docker` —— **必须**起真 PG（**修 P0-5**），用 `pytest-httpx` mock 外部 HTTP（TEI / OpenSearch / Langfuse）
- **覆盖率门禁**：`pytest --cov=app/api --cov=app/main --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 `[RED]`）→ GREEN（commit 标 `[GREEN]`）→ REFACTOR（commit 标 `[RF]`）

**关键测试矩阵**（spec §5 错误矩阵全覆盖）：

| 场景 | 端点 | 期望 | 关键单测 |
|------|------|------|----------|
| 未登录 | 任意 protected | 401 | `test_*_returns_401_when_unauthenticated` |
| 越权 session | GET /api/sessions/{id} | 404（不暴露存在性） | `test_detail_returns_404_for_other_user_session` |
| 越权 session | POST /api/chat 带他人 session_id | 404 | `test_chat_returns_404_for_other_user_session` |
| LLM 4xx/5xx | POST /api/chat | 502 + 不静默 | `test_chat_returns_502_on_graph_error` |
| **graph invoke 超时（修 P0-1）** | POST /api/chat | 502 + 中文 detail | `test_chat_returns_502_on_timeout` |
| OpenSearch 不可达 | POST /api/chat | 503 + 兜底 | `test_chat_returns_503_with_fallback_on_retrieval_error` |
| 422 schema 错 | POST /api/chat | 422 + 字段详情 | `test_validation_error_returns_422_with_field_detail` |
| 多轮 thread 复用 | POST /api/chat 2 次 | 同 thread_id 传 graph | `test_chat_reuses_existing_thread_on_second_call` |
| health 全部 up | GET /api/health | 200 + status="ok" | `test_health_returns_200_when_all_up` |
| health 任一 down | GET /api/health | 503 + status="degraded" | `test_health_returns_503_when_pg_down` |
| **health 5 service 探测（修 P0-3）** | GET /api/health | 5 service 字段齐 + URL 正确 | `test_health_*_url_and_timeout`（5 个） |
| lifespan 启动 | 任意 endpoint | graph 已编译 | `test_app_starts_with_lifespan` |
| **lifespan 关闭 engine dispose（修 P0-2）** | TestClient exit | engine 已关闭 | `test_lifespan_closes_db_engine` |
| **lifespan override 测试（修 P1-4）** | TestClient(no-op lifespan) | 503 from get_orchestrator | `test_orchestrator_returns_503_when_app_state_missing` |
| **lifespan shutdown event（修 P2-7）** | TestClient exit 中 | health 返 503 | `test_health_returns_503_during_shutdown` |
| **APP_ENV 感知（修 P2-8）** | dev vs prod | /docs 暴露 vs 关闭 | `test_docs_url_disabled_in_prod` |
| ingest POST 暂未实现 | POST /api/ingest | 501 + stub 说明 | `test_post_ingest_returns_501_with_deferred_message` |
| **stub 标记可 grep（修 P1-7）** | grep | `TODO(m8→m4)` 存在 | 手动 `rg "TODO\(m8→m4\)" apps/rag_v1/` |

---

## 验证（Definition of Done）

- [ ] 5 个路由全部跑通（chat / sessions×2 / ingest / health） + auth 3 件（M2 已建）共 8 端点
- [ ] `POST /api/chat` 鉴权 → session 解析（缺建/有查+越权 404）→ graph.ainvoke → 返回 4 路径全测过
- [ ] **多轮 chat thread 复用**：第 2 次 invoke 同 thread_id，graph 拿得到 history（PG checkpoint 落数据）
- [ ] 错误矩阵全覆盖：401 / 404 / 422 / 500 / 502 / 503
- [ ] lifespan 启动建 graph + checkpointer，关闭自动 cleanup
- [ ] **lifespan 关闭 `engine.dispose()` 归还 asyncpg 连接池**（**修 P0-2**）
- [ ] **chat 端点 `asyncio.wait_for` 包装 graph.ainvoke，超时 502**（**修 P0-1**）
- [ ] **health check 5 service URL/timeout/auth 具体化**（**修 P0-3**）
- [ ] `app/api/__init__.py` 聚合 5 个子路由（**修 P2-6**）
- [ ] `compile_workflow` 单一来源在 `app/graph/checkpointer.py`（**修 P0-10**），M8 import 路径正确
- [ ] **`make_checkpointer` 已是 `async def` 返回实例**（**M7 r1 P0-3**），M8 lifespan `await make_checkpointer()` + 手动 dispose
- [ ] `chat_sessions.updated_at` 更新走 ORM（**修 P1-4**）
- [ ] `GET /api/sessions` 性能依赖复合索引 `(user_id, is_active, updated_at DESC)`（**修 P1-6**）
- [ ] **`GET /api/sessions` 加 `deleted_at IS NULL` 软删除过滤**（**修 P1-6**）
- [ ] `POST /api/chat` 鉴权集成完整（**修 P1-11**）
- [ ] **503 兜底文案走 `settings.graph.fallback_message`**（**修 P1-1**）
- [ ] **`get_orchestrator` 删 fallback，未初始化时显式 503**（**修 P1-3**）
- [ ] **`create_app(lifespan_override=...)` 工厂支持测试 override**（**修 P1-4**）
- [ ] **`get_db` 显式 `AsyncSession` 类型注解**（**修 P1-5**）
- [ ] **`POST /api/ingest` stub 加 `# TODO(m8→m4)` 标记**（**修 P1-7**），grep 可定位替换点
- [ ] **所有 Response schema 字段完整定义**（**修 P2-1**）
- [ ] **`_check_*` 函数直接放 `app/api/health_checks.py` 独立文件**（**修 P2-2**）
- [ ] **middleware 挂载顺序带职责注释**（**修 P2-3**）
- [ ] **`sessions limit` 走 `settings.api.default_session_page_size`**（**修 P2-4**）
- [ ] **`RequestIdMiddleware` 拆到 `app/api/middleware.py`**（**修 P2-5**）
- [ ] **session title 用 `safe_truncate` UTF-8 byte-aware 截取**（**修 P2-6**）
- [ ] **lifespan 关闭设 `shutdown_event` + 500ms 缓冲 + engine dispose**（**修 P2-7**）
- [ ] **`APP_ENV` 感知：`/docs` 暴露与 CORS 受 dev/staging/prod 控制**（**修 P2-8**）
- [ ] 集成测试**必须**用真 PG（**修 P0-5**），不跑 sqlite
- [ ] `POST /api/ingest` 返 501 stub，文档说明 M4-M6 替换
- [ ] 单元 + 集成测试全过
- [ ] 单元覆盖率 ≥ 85%
- [ ] `pyproject.toml` 追加 3 个依赖（fastapi / uvicorn / python-multipart）（**修 P0-8**）
- [ ] `pytest-httpx` 已声明在 dev 依赖（**修 P1-18**）
- [ ] **`ChatResponse` / `HealthResponse` / exception handler response 字段统一 `trace_id`**（**修 r2-新-1**），与 M9/M10/M11 跨 M 一致
- [ ] **`ServiceHealth.status` / `HealthResponse.status` 含 `starting` 字面量**（**修 r2-新-2**），lifespan 启动期 health 端点返 503 + status="starting"
- [ ] **lifespan finally 块 `graph.aclose()` 幂等调用 + try/except 兜底**（**修 r2-新-3**）
- [ ] **`POST /api/chat` + `POST /api/ingest` 显式接受 `Idempotency-Key` Header 透传**（**修 r2-新-4**）；chat 缺 session_id + 有 idempotency_key 时复用同 user_id + 同 idempotency_key 已有 session
- [ ] **`create_app` middleware 挂载注释加 LIFO 警示**（**修 r2-新-5**），与 M12 r1 P0-1 LIFO 模式对齐

---

## 与其他 M 的依赖

| 上游（必须 M8 前完成） | 下游（依赖 M8） |
|----------------------|----------------|
| M0 docker-compose（PG + OpenSearch + TEI + Langfuse） | M9 Gradio UI（调 M8 全部端点） |
| M1 Alembic 4 表（users / chat_sessions / auth_sessions / ingest_jobs） | M10 Langfuse 业务级 trace（用 M8 透传的 X-Request-Id） |
| M2 auth 鉴权（`Depends(get_current_user)`） | M11 RAGAS（直接 `graph.ainvoke()` 不走 M8） |
| M3 LLM 工厂 + TEI Embedding | M12 Hardening（限速中间件挂在 M8 app 实例） |
| **M7 graph（`compile_workflow` + 7 节点 + checkpointer + `answer_chitchat_node` 实现 + `safe_node` 装饰器 + `make_checkpointer` 返回实例）**（M7 r1 已修） | M12 Prometheus（scrape M8 `GET /api/health`） |
| **M7 `GraphSettings.fallback_message` 已定义**（M7 r1 P1-2 已修） | — |

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| `compile_workflow` 同步 vs graph.ainvoke 异步不匹配（M7 写 `def compile_workflow` 同步返回，但 M8 端点是 async） | lifespan 用 `await make_checkpointer()` + `compile_workflow(checkpointer=cp)` 同步建图后 `await graph.ainvoke()` 异步调；测试 mock `ainvoke` | 改 M7 为 `async def compile_workflow` — 风险大，会改 7 节点签名 |
| PG 不可达时 lifespan 启动失败 → app 起不来 | 跟 M7 对齐：lifespan 走 `make_checkpointer()` 工厂，自动 PG → SQLite 降级；`GET /api/health` 返 503 + UI 告警 | 启动失败硬挂 — M12 monitoring 才能发现，UX 差 |
| FastAPI lifespan 与 pytest-asyncio loop 冲突 | 集成测试用 `TestClient`（同步），不走 asyncio loop；单元测试用 `httpx.AsyncClient(transport=ASGITransport(app=app))` 显式 loop | — |
| `chat_sessions` 缺复合索引 → sessions 列表慢（**P1-6**） | M1 已加 `(user_id, is_active, updated_at DESC)`；M8 集成测试 EXPLAIN 验证 | 单列 `user_id` 索引 — 用户量大时 N 回表 |
| `updated_at` 走原生 SQL 不更新（**P1-4**） | M8 session 创建走 ORM `db.add() + commit()`；不直接 `session.execute(update(...))` | — |
| OpenSearch 不可达时整 chat 失败而非走兜底 | `RetrievalError` 在 M7 节点已 try/except 返 fallback answer；M8 路由**再** catch 503 兜底（双层） | M8 路由层裸调 — 失去 spec §5 503 语义 |
| 越权 session 返 403 暴露存在性 | 强制走 `WHERE user_id = current_user.id`，自然 404；M2 鉴权 401 与 M8 业务 404 严格分层 | 返 403 — 安全审计会扣分 |
| `POST /api/ingest` 501 静默成 200 | 用 501 Not Implemented + 明确 detail 字符串；前端 catch `detail` 字段显式提示 | 返 200 + `pending` 假状态 — Gradio UI 会以为成功 |
| 集成测试用 sqlite 假绿（**P0-5**） | 强制 `--require-docker` 标记 + `pg_dsn` fixture；CI 起真 PG | sqlite 内存 — JSONB / UUID / 约束全失真 |
| M7 `make_checkpointer` 是 `async def`（M7 r1 P0-3） | M8 lifespan 用 `await make_checkpointer()` 拿实例 + 手动 `engine.dispose()` + `cp.close()`（幂等） | 改 M7 为 `@asynccontextmanager` — M7 r1 已否决，破坏 lifecycle 自管语义 |
| Langfuse callback 注入方式 | M3 工厂已注入到 `model.with_config({"callbacks": [handler]})`（**修 P1-14**）；M8 只在 graph.ainvoke config 里再传 `metadata.request_id` | M8 路由层注入 — 越权，破坏 M3 单一来源 |
| `python-multipart` 版本不匹配 V1 Scope | 锁 `>=0.0.9`（spec §8.4 精确版） | — |
| **r1-2026-06-11 P0-1 已修**：`POST /api/chat` 无超时保护 → `graph.ainvoke` 慢拖垮 worker | Task 7 GREEN 段加 `await asyncio.wait_for(graph.ainvoke(...), timeout=settings.api.chat_timeout_seconds)`，超时 raise 502 + 中文 detail；RED 测试 `test_chat_returns_502_on_timeout` | 改 langgraph 加 `max_iterations=10`：M7 r1 P0-4 已否决（langgraph 1.0.5 无 invoke timeout API） |
| **r1-2026-06-11 P0-2 已修**：lifespan 关闭未调 `engine.dispose()` → asyncpg 连接池残留 | Task 13 GREEN `lifespan` 函数 `finally` 块 `await engine.dispose()` + `cp.close()` 幂等；RED 测试 `test_lifespan_closes_db_engine`（启动后 engine 未关 → lifespan exit 后断言已关） | 改 uvicorn `--timeout-graceful-shutdown=30`：被 supervisor 杀掉时连接还是泄漏 |
| **r1-2026-06-11 P0-3 已修**：health check 4 service 探测实现模糊（缺 URL / timeout / auth） | Task 2 GREEN 段 5 个 `_check_*` 函数移到 `app/api/health_checks.py`，URL 全部从 `settings.health.{opensearch_url,tei_url,langfuse_url}` 读，timeout 用 `settings.health.health_check_timeout`；RED 测试 mock 具体 URL 前缀 | 全用 `httpx.AsyncClient()` 默认 URL：compose 端口变更时测试断不到 |
| **r1-2026-06-11 P1-1 已修**：503 降级兜底文案硬编码 | Task 7 GREEN 段改用 `settings.graph.fallback_message`（与 M7 r1 P1-2 共用同一配置源 `app/config.py` GraphSettings） | 写死在路由函数 — 改文案要改 M8 代码 |
| **r1-2026-06-11 P1-2 已修**：`GET /api/sessions` 缺 `_count_messages` 实现 | Task 4 GREEN 段补 `async def _count_messages(db, session_id) -> int` 用 `select(func.count()).select_from(Message).where(Message.session_id == ...)`；REFACTOR 改为 outerjoin 一次出数避免 N+1 | 删 `message_count` 字段 — 前端需要展示 |
| **r1-2026-06-11 P1-3 已修**：`get_orchestrator` fallback 路径每次重建 graph + CP 泄漏 | Task 6 GREEN 删 fallback 路径，未初始化时 `raise HTTPException(503, "服务尚未就绪，请稍后重试。")`；lifespan 启动失败直接 500 更诚实 | 保留 fallback 缓存到 module-level：测试/异常场景拿不到 graph 反而更隐蔽 |
| **r1-2026-06-11 P1-4 已修**：lifespan override 不可测，fallback 是死代码 | Task 13 GREEN `create_app(lifespan_override: Lifespan | None = None)` 接受测试 no-op lifespan；RED 测试用 `TestClient(create_app(lifespan_override=noop_lifespan))` 触发 503 | 改用 module-level graph 单例：lifespan 重入时连接双开 |
| **r1-2026-06-11 P1-5 已修**：`get_db` Depends 缺 `AsyncSession` 类型注解 | Task 6 GREEN 段 `async def get_db() -> AsyncSession: ...` 显式注解 | 不标类型 — IDE/类型检查器无法推断下游 |
| **r1-2026-06-11 P1-6 已修**：`GET /api/sessions` 缺软删除过滤 | Task 4 GREEN 段查询加 `ChatSession.deleted_at.is_(None)` 过滤（M1 schema 已有 `deleted_at` 列） | 仅 `is_active=False` 过滤 — 系统归档和用户删除不可分 |
| **r1-2026-06-11 P1-7 已修**：`POST /api/ingest` 501 stub 缺 M4 合并标记 | Task 11 GREEN 段 stub 函数加 `# TODO(m8→m4): 合并 M4-M6 时删除本 stub`；DoD 加 `grep "TODO\(m8→m4\)" apps/rag_v1/` 必须命中 | 单纯 501 — M4 合并时不知道要删哪些 |
| **r1-2026-06-11 P2-1 已修**：5 个 Response schema 字段未完整列出 | Files 表 schema 段补全：`SessionListResponse{sessions, total}` / `SessionDetailResponse{id, title, thread_id, messages, created_at, updated_at}` / `IngestProgressResponse{job_id, status, progress, error, created_at, updated_at}` / `IngestAcceptedResponse{job_id, status="accepted"}` | 只在 GREEN 段临时拼 — schema 文件与使用处不同步 |
| **r1-2026-06-11 P2-2 已修**：`_check_*` 拆到独立文件提法过晚 | 直接在 Task 2 GREEN 段写 `app/api/health_checks.py` 5 个函数 + `check_all(app)` 聚合；`health.py` 只留路由；删原 REFACTOR 步骤 | 保持内联 + 后续 PR 拆：增加 review diff 噪音 |
| **r1-2026-06-11 P2-3 已修**：middleware 挂载顺序无注释 | Task 13 GREEN 段在 `add_middleware` 上方加注释：`1. CORS（不依赖 tracing）` / `2. RequestId（后续中间件/路由有 request_id）` / `↓ M12 RateLimit（依赖 request_id）` | 不注释 — M12 接限速时不知道该挂哪 |
| **r1-2026-06-11 P2-4 已修**：`limit(50)` 硬编码 | Task 4 GREEN 段改用 `settings.api.default_session_page_size`（默认 50，`APISettings` 追加字段） | 加 `?page_size=` query param — V1 阶段前端分页不需要 |
| **r1-2026-06-11 P2-5 已修**：`RequestIdMiddleware` 内联在 main.py | 拆到 `app/api/middleware.py`；main.py 改 `from app.api.middleware import RequestIdMiddleware`；M12 改 request_id 行为不动 main.py | 保持内联 — main.py 100 行就难读 |
| **r1-2026-06-11 P2-6 已修**：session title 截断可能截断 multi-byte（emoji / surrogate） | Task 7 GREEN 段用 `safe_truncate(text, max_bytes=50)`（按 UTF-8 byte 截，surrogate 安全）；实现放 `app/utils/text.py` | `text[:50]` — emoji surrogate pair 被切成乱码 |
| **r1-2026-06-11 P2-7 已修**：lifespan 关闭时 in-flight health check 仍读 DB | Task 13 GREEN `finally` 块先 `app.state.shutdown_event.set()` + `await asyncio.sleep(0.5)` 给 in-flight 请求缓冲，再 `engine.dispose()`；health 端点检测 shutdown_event 返 503 | 直接 `dispose()` — in-flight 请求拿 `InterfaceError` 500 |
| **r1-2026-06-11 P2-8 已修**：缺 `APP_ENV` 环境感知（Swagger docs / CORS / debug） | `APISettings.env: Literal["dev","staging","prod"] = "dev"`；`cors_origins` 按 env 切换（dev=`["*"]`、prod 受限域名）；`expose_docs: bool = env == "dev"`；`create_app` 中 `docs_url/redoc_url/openapi_url` 受 `expose_docs` 控制 | 全用 `["*"]` + 默认开 docs — 生产环境暴露 Swagger UI 安全审计扣分 |
| **r2-2026-06-12 新-1 已修**：`ChatResponse` 字段 `request_id` 与 M9/M10/M11 命名不一致 | Task 7 chat 端点 + Task 8 schema 改 `trace_id` 字段；Task 2 `HealthResponse` 改 `trace_id`；Task 9 exception handler 改 `trace_id`；RequestIdMiddleware 内部 `request.state.request_id` 保留（协议级）；graph.ainvoke metadata 双键（trace_id + request_id）同字符串不同语义 | 仅改 M8 字段名 — M9/M10/M11 需各自同步更新字段名，跨 M 协调成本高 |
| **r2-2026-06-12 新-2 已修**：5 service health 并行 + business 在 gather 后判定，lifespan 未启动时 business 永远 down | Task 2 `_check_business(app)` 重写：直接读 `app.state.graph` / `app.state.checkpointer`，未就绪时返 `status="starting"` 而非 down；`ServiceHealth.status` 和 `HealthResponse.status` 加 `starting` 字面量；health 端点 starting 优先返 503 | 仅扩 enum 字面量 — 旧客户端可能只识别 ok/degraded/down 三态 |
| **r2-2026-06-12 新-3 已修**：Lifespan 关闭时 `graph` 自身未 await 清理（依赖 langgraph 1.0.5 是否有 aclose） | Task 13 lifespan finally 块在 `engine.dispose()` 之前加 `getattr(graph, "aclose", None) or getattr(graph, "close", None)` 幂等调用 + try/except 兜底 + `log.warning` | 改 M7 在 graph 编译时显式释放资源 — 编译态资源本来就应 GC，破坏 M7 抽象 |
| **r2-2026-06-12 新-4 已修**：`Idempotency-Key` Header 透传未在 M8 plan 显式支持（依赖 M1 r2 4 表 idempotency_key 联动） | Task 7 chat 端点显式接收 `idempotency_key: str | None = Header(None, alias="Idempotency-Key")`；缺 session_id + 有 idempotency_key 时查重同 user_id + 同 idempotency_key 已有 session 复用；新建 session 写 idempotency_key 到 DB（NULL = 无幂等保护）。Task 11 POST /api/ingest stub 也加 Header 透传（M4-M6 替换时直接复用） | 仅在 M9 UI 端做客户端 dedup — 第三方直接调 M8 API 仍会双击污染 |
| **r2-2026-06-12 新-5 已修**：middleware 顺序注释与 M12 r1 P0-1 LIFO add_middleware 顺序需复核 | Task 13 GREEN 段 `create_app` middleware 注释加 LIFO 警示（"后添加的先执行 / 最外层" + "调用顺序 CORS → RequestId → M12 RateLimit" + "执行顺序 M12 RateLimit → RequestId → CORS → endpoint"），与 M12 r1 P0-1 LIFO 模式对齐 | 不加 LIFO 警示 — M12 integration 时 reviewer 可能误判嵌套关系 |

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M8-plan-r0 | 2026-06-11 | 初稿（基线 V1 Scope §3.3 §4 §5 + 决策 #7） |
| M8-plan-r1 | 2026-06-11 | 仓库布局对齐 `apps/rag_v1/{app/api,tests}/`；补 P0-1/P0-5/P0-10/P1-4/P1-6/P1-11/P1-16/P2-6 避雷标注 |
| M8-plan-r2 | 2026-06-11 | lifespan 单例 + compile_workflow 同步/异步边界明确（async context 包装） |
| r1-2026-06-11 | 2026-06-11 | **P0-1 已修** · `POST /api/chat` 加 `asyncio.wait_for(graph.ainvoke, timeout=settings.api.chat_timeout_seconds)` 包装；超时 raise 502 + 中文 detail；RED 测试 `test_chat_returns_502_on_timeout`；`APISettings.chat_timeout_seconds=30` |
| r1-2026-06-11 | 2026-06-11 | **P0-2 已修** · lifespan `finally` 块 `await engine.dispose()` 归还 asyncpg 连接池 + `cp.close()` 幂等；RED 测试 `test_lifespan_closes_db_engine` |
| r1-2026-06-11 | 2026-06-11 | **P0-3 已修** · 5 个 `_check_*` 函数移到 `app/api/health_checks.py`；URL 全部从 `settings.health.{opensearch_url,tei_url,langfuse_url}` 读，timeout 走 `settings.health.health_check_timeout`；RED 测试 mock 具体 URL 前缀 |
| r1-2026-06-11 | 2026-06-11 | **P1-1 已修** · 503 兜底文案改用 `settings.graph.fallback_message`（与 M7 r1 P1-2 共用 `app/config.py` GraphSettings） |
| r1-2026-06-11 | 2026-06-11 | **P1-2 已修** · Task 4 GREEN 段补 `async def _count_messages(db, session_id) -> int`；REFACTOR 改 outerjoin 一次出数 |
| r1-2026-06-11 | 2026-06-11 | **P1-3 已修** · `get_orchestrator` 删 fallback 路径，未初始化时 `raise HTTPException(503)`；避免每次重建 graph + CP 泄漏 |
| r1-2026-06-11 | 2026-06-11 | **P1-4 已修** · `create_app(lifespan_override=None)` 接受测试 no-op lifespan；RED 测试用 `TestClient(create_app(lifespan_override=noop_lifespan))` 触发 503 |
| r1-2026-06-11 | 2026-06-11 | **P1-5 已修** · `get_db` 显式 `async def get_db() -> AsyncSession` 类型注解 |
| r1-2026-06-11 | 2026-06-11 | **P1-6 已修** · `GET /api/sessions` 加 `ChatSession.deleted_at.is_(None)` 软删除过滤；M1 schema 已有 `deleted_at` 列 |
| r1-2026-06-11 | 2026-06-11 | **P1-7 已修** · `POST /api/ingest` 501 stub 加 `# TODO(m8→m4): 合并 M4-M6 时删除本 stub` 标记；DoD 加 `grep "TODO\(m8→m4\)" apps/rag_v1/` 必须命中 |
| r1-2026-06-11 | 2026-06-11 | **P2-1 已修** · 5 个 Response schema 字段完整定义：`SessionListResponse` / `SessionDetailResponse` / `IngestProgressResponse` / `IngestAcceptedResponse` |
| r1-2026-06-11 | 2026-06-11 | **P2-2 已修** · `_check_*` 函数直接放 `app/api/health_checks.py` 独立文件；删原 Task 2 REFACTOR 步骤；`health.py` 只留路由 |
| r1-2026-06-11 | 2026-06-11 | **P2-3 已修** · `create_app` middleware 挂载顺序加职责注释（CORS → RequestId → ↓ M12 RateLimit） |
| r1-2026-06-11 | 2026-06-11 | **P2-4 已修** · `sessions limit` 改用 `settings.api.default_session_page_size`（`APISettings` 追加字段，默认 50） |
| r1-2026-06-11 | 2026-06-11 | **P2-5 已修** · `RequestIdMiddleware` 拆到 `app/api/middleware.py`；`main.py` 改为 import |
| r1-2026-06-11 | 2026-06-11 | **P2-6 已修** · session title 用 `safe_truncate(text, max_bytes=50)` UTF-8 byte-aware 截取（`app/utils/text.py`） |
| r1-2026-06-11 | 2026-06-11 | **P2-7 已修** · lifespan `finally` 块先 `app.state.shutdown_event.set()` + `await asyncio.sleep(0.5)` 给 in-flight 请求缓冲；health 端点检测 shutdown_event 返 503 |
| r1-2026-06-11 | 2026-06-11 | **P2-8 已修** · `APISettings.env / cors_origins / expose_docs` 区分 dev/staging/prod；`create_app` 中 `docs_url / redoc_url / openapi_url` 受 `expose_docs` 控制 |
| r1-2026-06-11 | 2026-06-11 | **M7 联动调整** · M7 r1 P0-3 已修 `make_checkpointer` 为 `async def` 返回实例；M8 lifespan 改 `await make_checkpointer()` + 手动 `engine.dispose()` + `cp.close()`；更新 Architecture 段 + Files 段说明 |
| r1-2026-06-11 | 2026-06-11 | **M7 联动调整** · M7 r1 P1-2 已修 `GraphSettings.fallback_message`；M8 P1-1 共用同一配置源 |
| r1-2026-06-11 | 2026-06-11 | **M7 联动调整** · M7 r1 P0-4 graph timeout 由调用方 M8 负责；M8 P0-1 `asyncio.wait_for` 包装已落 |
| r2-2026-06-12 | 2026-06-12 | **新-1 已修** · `ChatResponse` / `HealthResponse` / exception handler response 字段统一为 `trace_id`（与 M9/M10/M11 跨 M 一致）；`RequestIdMiddleware` 内部 `request.state.request_id` 与 `X-Request-Id` Header 名协议级保留；graph.ainvoke `metadata` 双键 `trace_id` + `request_id` 同字符串不同语义 |
| r2-2026-06-12 | 2026-06-12 | **新-2 已修** · `ServiceHealth.status` / `HealthResponse.status` 加 `starting` 字面量；`_check_business(app)` 直接读 `app.state.graph` / `app.state.checkpointer`，未就绪返 `starting` 而非 down；health 端点 starting 优先返 503 |
| r2-2026-06-12 | 2026-06-12 | **新-3 已修** · lifespan finally 块在 `engine.dispose()` 之前加 `getattr(graph, "aclose", None) or getattr(graph, "close", None)` 幂等调用 + try/except 兜底 + `log.warning`（与 cp.close 模式一致） |
| r2-2026-06-12 | 2026-06-12 | **新-4 已修** · `POST /api/chat` 显式接收 `Idempotency-Key: str | None = Header(None, alias="Idempotency-Key")`；缺 session_id + 有 idempotency_key 时查重同 user_id + 同 idempotency_key 已有 session 复用；新建 session 写 idempotency_key 到 DB。`POST /api/ingest` stub 也加 Header 透传（M4-M6 替换时直接复用） |
| r2-2026-06-12 | 2026-06-12 | **新-5 已修** · `create_app` middleware 挂载注释加 LIFO 警示（"后添加的先执行 / 最外层" + "调用顺序 CORS → RequestId → M12 RateLimit" + "执行顺序 M12 RateLimit → RequestId → CORS → endpoint"），与 M12 r1 P0-1 LIFO 模式对齐 |
