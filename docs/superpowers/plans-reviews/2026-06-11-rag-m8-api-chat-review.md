# M8 Plan Review · FastAPI 路由层（/api/chat + /api/sessions + 进度查询 + health）

> 评审对象：`plans/2026-06-11-rag-m8-api-chat.md`（964 行）
> 评审基线：V1 Scope v0.4 spec（§0 决策 #7 · §1 架构 API 段 · §2 模块树 api 段 · §3.2 Auth / §3.3 Query · §4 API & UI 表 · §5 错误矩阵 · §8.4 依赖）
> 参考 review：总报告 `2026-06-11-rag-plans-review.md` · M7 review `2026-06-11-rag-m7-graph-review.md` · M2 review `2026-06-11-rag-m2-auth-review.md` · M3 review `2026-06-11-rag-m3-llm-embed-review.md` · M0 review `2026-06-11-rag-m0-infra-review.md`
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M8 plan 覆盖 11 段模板（Goal / Architecture / Tech Stack / Files / 14 Tasks RED-GREEN / 测试策略 / DoD / 依赖 / 风险 / 修订记录），自带范本目的段（L10）和完整的数据流图（L84-119）。5 个路由端点（auth/sessions×2/chat/ingest/health）+ 5 套 Pydantic schema + 统一 exception handler + lifespan 单例——主体设计**与 spec §3.3 Query 数据流 + §4 API 表 + §5 错误矩阵逐一对齐**。任务是 RAG V1 中除 M7 外最复杂的里程碑（14 Tasks/3 天），行数 964 与复杂度匹配。

**但实施就绪度中等**——已有 review 中的 P0-5 / P0-10 / P1-4 / P1-6 / P1-11 / P2-6 已标注避雷并给出方案（加分），但 M7 review 的 P0（graph timeout / answer_chitchat / cp API）**未在本 plan 中建立依赖阻断机制**；外加本 review 新发现 17 个问题，其中 3 个 P0（chat 端点无超时保护、lifespan 关闭缺 engine.dispose()、health check 5 service 探测实现模糊）、6 个 P1、8 个 P2。修完 P0 后是可直接动手的合格 plan。

| 维度 | 评分 | 说明 |
|------|------|------|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐 + 范本目的段 + 数据流图 + 契约边界表 + 测试矩阵表，结构和可读性在 M0-M8 中最完整 |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 14 Tasks 全部 RED-GREEN-REFACTOR；RED 测试名具体、GREEN 代码段完整（非伪代码）、REFACTOR 提法恰当 |
| 技术深度 | ⭐⭐⭐⭐ | 5 路由数据流 + session 缺/有/越权 + lifespan 单例 + exception handler 统一注册，设计详细；但缺超时/优雅关闭/engine dispose 等生产化项 |
| 错误处理 | ⭐⭐⭐⭐⭐ | 401/404/422/500/502/503 + spec §5 全部 12 个场景映射到测试矩阵，错误码选择（401 vs 404 越权不暴露、503 降级兜底、501 stub）正确 |
| 一致性 | ⭐⭐⭐⭐ | 与 spec §3.3/§4/§5 对齐；P0-1/P0-5/P0-10/P1-4/P1-6/P1-11/P2-6 均已标注避雷方案；但 M7 review P0 依赖链未在依赖表或风险表显式阻断 |
| 已有 review 就绪度 | ⭐⭐⭐⭐ | 7 项避雷已标注（P0-1/P0-5/P0-10/P1-4/P1-6/P1-11/P2-6）；P0-8（pyproject 依赖追加）在 DoD 中覆盖；P1-18（pytest-httpx）在 DoD 中覆盖 |

**一句话**：M8 plan **结构最完整、TDD 节奏最佳、与 spec 对齐度高、已有避雷标注充分**，是 M0-M8 中最成熟的 plan；但**缺 chat 端点超时保护、lifespan 缺 asyncpg engine.dispose()、health check 5 service 探测实现模糊**三项 P0 阻塞 + 12 项 P1/P2，修完可直接动手。

---

## 已有 review 验证（2026-06-11-rag-plans-review.md）

| ID | 已有 review 项 | Plan 现状 | 本报告 |
|----|---------------|-----------|--------|
| **P0-1** | 端口冲突（TEI 8080 vs http.server） | ✅ 已避雷——L260 `infra/docker-compose.yml: FastAPI 默认 8000 与 TEI 18080 不冲突` | 通过。TEI 已改 18080，M8 FastAPI 8000 无冲突 |
| **P0-5** | 真 PG 集成测试（不跑 sqlite） | ✅ 已避雷——Task 14 强制 `--require-docker` + pg_dsn fixture；L891 `必须`起真 PG | 通过。Task 14 GREEN 段给完整 conftest 代码 |
| **P0-8** | pyproject.toml 过度装包 | ✅ 已避雷——Files 表 L252 `修改：pyproject.toml 追加 fastapi/uvicorn/python-multipart`，仅追加 M8 需要的 3 个 | 通过。M0 只装 base 3 包，M8 追加自己需要的，符合分阶段加依赖原则 |
| **P0-10** | checkpointer 双重定义 | ✅ 已避雷——L138-141 `M8 严格只 from app.graph.checkpointer import make_checkpointer`；L914 `compile_workflow 单一来源` | 通过。M8 不创建自己的 checkpointer import 路径 |
| **P1-4** | updated_at 走 ORM 而非原生 SQL | ✅ 已避雷——L253 `chat_sessions.updated_at 更新走 ORM（修 P1-4）`；风险表 L947 `M8 session 创建走 ORM db.add()+commit()` | 通过。新 session 创建用 ORM，不走原生 update |
| **P1-6** | chat_sessions 复合索引 | ✅ 已避雷——L253 `复合索引 (user_id, is_active, updated_at DESC) 已在 M1 加（修 P1-6）`；Task 4 GREEN 代码依赖该索引 | 通过。索引由 M1 创建，M8 sessions 查询使用 |
| **P1-11** | protected endpoint 鉴权完整 | ✅ 已避雷——Task 7 RED `test_chat_returns_401_when_unauthenticated`（P1-11 关键标注）；L917 `POST /api/chat 鉴权集成完整（修 P1-11）` | 通过。M2 get_current_user 在 chat/sessions/ingest 全部端点使用 |
| **P1-18** | pytest-httpx 缺声明 | ✅ 已避雷——DoD L923 `pytest-httpx 已声明在 dev 依赖（修 P1-18）` | 通过。plan 没有给具体片段但 DoD 覆盖了 |
| **P2-6** | app/api/__init__.py 聚合 | ✅ 已避雷——Task 12 明确修 P2-6；给完整 GREEN 代码段（L762-772） | 通过。APIRouter 聚合 5 个子路由，代码完整可用 |
| **P2-5** | make_checkpointer 是 @asynccontextmanager | ✅ 已避雷——风险表 L952 `M8 lifespan 用 async with make_checkpointer() as cp: compile_workflow(cp)` | 通过。M8 调用方正确处理 contextmanager |

**验证结论**：已有 review 中影响 M8 的 10 项——**全部 ✅ 已避雷**。plan 作者主动标注了 7 项并在对应位置给出了实现方案。

---

## M7 review 交叉验证（影响 M8 的关键项）

### 7-1 · M7 P0-4 graph 超时 / max_iterations → M8 应加 `asyncio.wait_for()`（**P0-1**）

**位置**：M7 review P0-4 · M8 plan Task 7 GREEN 段 L562-568

**问题**：
- M7 plan 的 `graph.ainvoke()` 没有超时保护，M8 review P0-4 已建议用 `asyncio.wait_for(graph.ainvoke(...), timeout=30)` 包装
- M8 plan **没有做这个包装**：L562 直接 `result = await graph.ainvoke(...)`——如果 LLM 慢（网络重试 3 次 × 60s = 180s）或 OpenSearch 慢（指数退避），请求可能 hang 长达几分钟
- FastAPI 默认 uvicorn `timeout_keep_alive=5` 但 `timeout_notify=30` supervisord 级别——被 uvicorn 杀后 client 拿不到 error，连接池资源泄漏
- **这是 M7 review 唯一未在 M8 plan 中修补的跨 M 阻塞**

**修改**（Task 7 GREEN 段 L561 包装超时）：

```python
import asyncio

# L561 改为：
try:
    result = await asyncio.wait_for(
        graph.ainvoke(
            {"query": req.query, "user_id": str(current_user.id), "thread_id": thread_id},
            config={
                "configurable": {"thread_id": thread_id},
                "metadata": {"request_id": request_id, "user_id": str(current_user.id)},
            },
        ),
        timeout=30.0,
    )
except asyncio.TimeoutError:
    log.warning("graph.ainvoke timeout", request_id=request_id)
    raise HTTPException(status_code=502, detail="服务超时，请稍后重试")
```

风险表补：`chat 端点 graph invoke 超时` | 无 `asyncio.wait_for` 保护，LLM/OS 慢导致请求 hang 到 uvicorn kill | 加 30s 超时 → 502

### 7-2 · M7 P0-6 answer_chitchat_node 缺实现 → M8 依赖阻断缺失

**位置**：M7 review P0-6 · M8 plan 依赖表 L929-936

**问题**：
- M7 plan 注册了 `answer_chitchat_node` 但 **没有实现**（M7 review P0-6）。如果 classify 返回 chitchat 意图，graph 调用会崩溃
- M8 plan 依赖表只列了 `M7 graph（compile_workflow + 7 节点 + checkpointer）`——没有说 M8 依赖 M7 的 chitchat 节点完整实现
- M8 的 `test_chat_reuses_existing_thread_on_second_call` 测试假设完整 graph（含 chitchat 分支），但 M7 若没实现 chitchat 节点，这个测试跑不通

**修改**（依赖表补一行）：

```
| M7 graph chitchat 分支（answer_chitchat_node 实现 / M7 P0-6） | 若 M7 未实现，graph invoke 崩溃（不兼容） |
```

### 7-3 · M7 P0-2 / P0-3 checkpointer API → M8 lifespan 依赖 M7 修复

**位置**：M7 review P0-2（`cp.aget` vs `aget_tuple`）· P0-3（contextmanager vs instance）

**问题**：
- M8 lifespan 使用 `async with make_checkpointer() as cp:` 模式——这个模式**假定 M7 已修复 P0-3**（checkpointer 作为 async contextmanager 返回实例）
- 如果 M7 没修 P0-3（compile 直接传 contextmanager），M8 整个 lifespan 启动失败，app 起不来
- M8 依赖表只列了 M7 `compile_workflow` 和 `checkpointer`，没有说依赖 M7 的 P0-3 修复

**修改**（依赖表补）：`M7 checkpointer async contextmanager 修复（M7 P0-3）` | M8 lifespan 依赖 `async with make_checkpointer()` 正确工作

### 7-4 · M7 P0-8 节点级异常传播 → M8 502/503 映射依赖 M7 error class

**位置**：M7 review P0-8 · M8 plan Task 7 L569-580

**问题**：
- M8 的 try/except 捕获 `GraphError` 和 `RetrievalError`——这假定 M7 的 7 个节点都统一使用这两个异常类
- M7 review P0-8 指出：6 个节点（classify/rewrite/rerank/answer/save_memory）**没有异常处理**，异常直接透传成 500
- M8 的 `test_chat_returns_502_on_graph_error` 测试反序列 `GraphError`——如果 M7 节点没抛此异常而是 `RuntimeError`，测试不过

**结论**：M8 的异常捕获设计正确（502/503 映射），但前提是 M7 已实现全局异常节点包装。**不做额外修改**，但风险表应补一行注明此依赖。

---

## M2 / M3 review 交叉验证

### 2-1 · M2 auth 端点 path prefix 一致性

M2 review P1-5 指出 M2 的 `api_router(prefix="/api")` 和 `auth.router(prefix="/api/auth")` 双 prefix 冲突。M8 Task 12 GREEN 代码（L763-772）使用 **无 prefix 的 api_router + 子路由自带 prefix** 模式——正确。但需确认 M2 的 `auth.router` 合并到 M8 的 `api_router` 后路径正确（即 `/api/auth/register` 而非 `/api/api/auth/register`）。

**结论**：M8 的 `app/api/__init__.py` 设计正确，不重复 prefix。但 M8 实现时需确认 M2 auth.router 的 prefix 设置与 M8 的策略一致。

### 2-2 · M3 `make_llm` callback 注入方式

M3 review P0-2（M3 review）/ P1-14（总 review）指出 `model.callbacks = [...]` 已被 langchain 1.0+ 弃用。M8 风险表 L953 已注明 `M3 工厂已注入到 model.with_config(...)（修 P1-14）；M8 只在 graph.ainvoke config 里再传 metadata.request_id`。

**结论**：M8 正确地将 callback 注入责任留在 M3 工厂层，自己只传 metadata——符合单一职责。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · `POST /api/chat` 端点缺 `asyncio.wait_for()` 超时保护

**位置**：Task 7 GREEN 段 L562-568（`await graph.ainvoke(...)` 裸调无超时）

**问题**：
- 单次 `graph.ainvoke()` 涉及 7 节点执行：classify（LLM）× 1 + rewrite（LLM）× 1 + retrieve（OS kNN）× 1-3 + rerank（LLM）× 1 + answer（LLM）× 1 = 4 次 LLM invoke + 1-3 次 OS query
- 每次 LLM invoke 可能 5-10s（MiniMax-M3 响应慢）+ 3 次重试 = 30s；OS 不可达时指数退避 3 次 = 15s
- 无超时 → 请求可能 hang 60s+ → FastAPI uvicorn worker 满 → 拒绝新请求
- 中文字段 `service not found` / `upstream LLM error` 返回前端的 502 body 未中文化

**修改**（Task 7 GREEN 段 L562 附近加）：

```python
import asyncio

TIMEOUT = settings.api.chat_timeout_seconds  # 默认 30

try:
    result = await asyncio.wait_for(
        graph.ainvoke(
            {"query": req.query, "user_id": str(current_user.id), "thread_id": thread_id},
            config={"configurable": {"thread_id": thread_id},
                    "metadata": {"request_id": request_id, "user_id": str(current_user.id)}},
        ),
        timeout=TIMEOUT,
    )
except asyncio.TimeoutError:
    log.warning("graph.ainvoke timeout", request_id=request_id)
    raise HTTPException(status_code=502, detail="服务超时，请稍后重试。")
```

Files 表 `app/config.py` 追加 `APISettings.chat_timeout_seconds: int = 30`。

RED 新增：`test_chat_returns_502_on_timeout`（mock graph.ainvoke sleep 60s → 断言 502）。

---

### P0-2 · lifespan 关闭时缺 `asyncpg engine.dispose()` + DB session 清理

**位置**：Task 13 GREEN 段 L797-801（lifespan 函数体）

**问题**：
- lifespan 启动时 `async with make_checkpointer() as cp:` 只管理 checkpointer 生命周期
- `app/db/session.py` 中的 `async_session = async_sessionmaker(engine)` — engine 是全局的，lifespan 关闭时没关
- `asyncpg` 连接池在 `engine.dispose()` 前不会关闭 → FastAPI 重启后旧连接残留（PG 侧 `idle in transaction`）
- Task 13 的 RED `test_lifespan_cleanup_on_shutdown` 断言"checkpointer 文件不存在或 PG 连接归还"——但只检查了 checkpointer，没覆盖 engine dispose

**修改**（lifespan 函数体补 close）：

```python
from app.db.session import engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with make_checkpointer() as cp:
        app.state.graph = compile_workflow(checkpointer=cp)
        app.state.checkpointer = cp
        yield
    # 关闭
    await engine.dispose()  # 归还 asyncpg 连接池
```

RED 补：`test_lifespan_closes_db_engine`（启动后断言 engine 未关闭 → lifespan exit → 断言 engine 已关闭/抛 `InterfaceError`）。

---

### P0-3 · health check 5 service 探测实现模糊——缺 URL / timeout / auth 具体值

**位置**：Task 2 GREEN 段 L307-340

**问题**：
- L329-331 只实现了 `_check_postgres`（DB 连通性），其余 3 个 service（OpenSearch / TEI / Langfuse）的 `_check_*` 函数用 `httpx.AsyncClient()`——但 **没给具体 URL / timeout / auth**：
  - OpenSearch：`GET http://localhost:9200/_cluster/health` 还是 `/_cat/health`？暴露端口是 9200 吗？
  - TEI：`GET http://localhost:18080/health` —— M0 compose 端口改 18080 后的正确 URL？TEI 的 health endpoint 路径是什么？
  - Langfuse：`GET http://localhost:3000/api/public/health` —— 需要 API key？plan 没说
- 没有 timeout：`httpx.AsyncClient` 默认 5s timeout，但 OS 重启 / TEI 模型加载中时 5s 可能不够
- **没有 mock 测试**：Task 2 RED `test_health_returns_200_when_all_up` 说"mock httpx + DB session"——但 httpx mock 的 URL 取决于实际探测路径，不定义路径 mock 测不了

**修改**（Task 2 GREEN 段给出完整 _check 函数）：

```python
import os
from app.config import settings

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
TEI_URL = os.getenv("TEI_URL", "http://localhost:18080")
LANGFUSE_URL = os.getenv("LANGFUSE_URL", "http://localhost:3000")

async def _check_opensearch() -> ServiceHealth:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OPENSEARCH_URL}/_cluster/health?wait_for_status=yellow&timeout=2s")
            resp.raise_for_status()
        return ServiceHealth(name="opensearch", status="up", latency_ms=(time.perf_counter()-t0)*1000)
    except Exception as e:
        return ServiceHealth(name="opensearch", status="down", error=str(e))

async def _check_tei() -> ServiceHealth:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{TEI_URL}/health")
            resp.raise_for_status()
        return ServiceHealth(name="tei", status="up", latency_ms=(time.perf_counter()-t0)*1000)
    except Exception as e:
        return ServiceHealth(name="tei", status="down", error=str(e))

async def _check_langfuse() -> ServiceHealth:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{LANGFUSE_URL}/api/public/health")
            resp.raise_for_status()
        return ServiceHealth(name="langfuse", status="up", latency_ms=(time.perf_counter()-t0)*1000)
    except Exception as e:
        return ServiceHealth(name="langfuse", status="down", error=str(e))
```

Files 表 `app/config.py` 追加 `HealthSettings.opensearch_url / tei_url / langfuse_url / health_check_timeout`。

同时 Task 2 RED 测试要 mock 具体的 URL 前缀（不要 `pytest_httpx` 全局 mock），确保 URL 变更时测试最先断。

---

## P1 · 重要

### P1-1 · `POST /api/chat` 503 降级返回的兜底文案硬编码

**位置**：Task 7 GREEN 段 L573-580

**问题**：
- 降级文案 `"检索服务暂不可用，已切换到直答模式。"` 写死在函数体内（同 M7 review P1-17/M1-2）
- 前端需要根据 `degraded` 字段自己显示 UI——如果文案要 A/B 测试或修改，得改 M8 代码

**修改**（引用 settings fallback_message）：

```python
from app.config import settings

return ChatResponse(
    answer=settings.graph.fallback_message,
    sources=[],
    session_id=session_id,
    request_id=request_id,
    degraded=True,
)
```

`app/config.py` 补 `GraphSettings.fallback_message: str = "检索服务暂不可用，已切换到直答模式。"`（与 M7 review P1-2 共用同一配置源）。

---

### P1-2 · `GET /api/sessions` 列表缺 `_count_messages` 实现

**位置**：Task 4 GREEN 段 L407-408

**问题**：
- 列表构建用 `await _count_messages(db, r.id)`——但这个函数 **不存在于任何 Files 表中**
- REFACTOR L428 说"改为单 SQL `select count(*)`"——但 GREEN 段**没给 `count_messages` 实现**
- 按当前实现每行一个 `_count_messages` 调用 = N+1 查询（50 条 session → 51 次 SQL）

**修改**（Task 4 GREEN 段 L414 前补实现）：

```python
from sqlalchemy import func, select as sa_select
from app.db.models import Message  # 假设 M1 存在该表

async def _count_messages(db: AsyncSession, session_id: str) -> int:
    """单条 session 的消息数（留作后续迁移到批量子查询）"""
    stmt = sa_select(func.count()).select_from(Message).where(Message.session_id == session_id)
    result = await db.execute(stmt)
    return result.scalar() or 0
```

**或**（推荐，避免 N+1）在 L407 改用子查询 `select(ChatSession, func.count(Message.id))` 一次出数。

---

### P1-3 · `get_orchestrator` fallback 路径可能重复创建 checkpointer

**位置**：Task 6 GREEN 段 L481-489

**问题**：
- `get_orchestrator` 的 fallback 路径（lifespan 外调用时）每次调 `async with make_checkpointer() as cp: compile_workflow(cp)`——但没缓存
- 单个请求 1 次 `get_orchestrator` 没事，但如果 `app.state.graph` 是 None（测试/异常），每次调端点都新建 checkpointer + 编译 graph（~5s，且连接泄漏）
- fallback 路径 `async with` 退出后 CP 连接关闭——但 graph 引用还留着，第二次 invoke 时 CP 已死

**修改**（二选一）：
- 方案 A：删 fallback，把 `app.state.graph = None` 情况改为 500 `ServiceNotReadyError`（更诚实，不会静默地每次编译新 graph）
- 方案 B：保留 fallback 但缓存编译结果到 module-level 变量，避免重复建 CP

---

### P1-4 · lifespan 外 `get_orchestrator` 测试路径不可达

**位置**：Task 6 RED L493 `test_orchestrator_falls_back_when_app_state_missing`

**问题**：
- RED 测试说"模拟 lifespan 未起"——但 `TestClient` 启动时自带 lifespan，`app.state.graph` 一定会被设
- 要模拟 "lifespan 未起" 需要 override lifespan（`create_app(lifespan=lambda a: yield None)`）——但 plan 没有给 `create_app()` 函数这个参数
- 如果 fallback 路径存在但不可测，就是死代码

**修改**（Task 13 GREEN `create_app` 函数签名改为可 receivelifespan）：

```python
def create_app(lifespan_override=None) -> FastAPI:
    app = FastAPI(
        title="RAG V1",
        version="0.1.0",
        lifespan=lifespan_override or lifespan,
    )
    ...
```

Task 6 RED 测试通过 `TestClient(create_app(lifespan_override=noop_lifespan))` 创建。

---

### P1-5 · `app/api/deps.py` 的 `get_db` Depends 返回类型缺 AsyncSession 标注

**位置**：Task 6 GREEN 段 L481-488 + Files 表 L235 (`deps.py`)

**问题**：
- `get_orchestrator` 的返回类型是 `CompiledStateGraph`——有标注
- `get_db` / `get_session` 只有草图轮廓，没有明确返回类型

**修改**（deps.py 补）：

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session as _get_session

# 给 FastAPI Depends 用，明确类型
async def get_db() -> AsyncSession:
    async with _get_session() as session:
        yield session
```

---

### P1-6 · `GET /api/sessions` 缺软删除过滤（`deleted_at IS NULL`）

**位置**：Task 4 GREEN 段 L397-402

**问题**：
- 查询条件只有 `ChatSession.user_id == current_user.id, ChatSession.is_active == True`
- M1 schema 定义了 `is_active` 但没有 `deleted_at`——如果后续 M9/M12 添加"删除 session"功能，`is_active` 不够区分"用户手动删除"vs"系统归档"

**修改**（Task 4 GREEN 段查询加 `deleted_at.is_(None)` filter + 性能影响：
- 如果 M1 schema 有 `deleted_at` 列：加 `ChatSession.deleted_at.is_(None)`
- 如果 M1 schema 没有：在风险表注明"V1 session 软删除用 is_active=False；deleted_at 字段留 V1.1"

---

### P1-7 · `POST /api/ingest` 用 501 Not Implemented 但 spec 期望 202 Accepted

**位置**：Task 11 GREEN 段 L744-751

**问题**：
- spec §4 表 `POST /api/ingest` 行写的是 `鉴权: 有`，没有期望状态码
- M8 用 501 没问题（M4-M6 才实现），但 TEST matrix L902 写的是"501 + stub 说明"——而 plan Goal L29（不包含段）说"POST /api/ingest 由 M4-M6 实现，M8 写 stub + 委派约定"——没有说 501 vs 202 的切换时序
- M8 DoD 也没有说"在 M4-M6 合并 pr 时，需删除 stub 代码"

**修改**（Task 11 REFACTOR 补）：

```python
# TODO(m8→m4): 合并 M4 时删除本 stub，替换为真实 IngestRequest handler
```

并确保 DoD 补一项：`删除 stub 的 grep 点——TODO(m8→m4) 标记已就位`。

---

## P2 · 优化

### P2-1 · plan 中 5 个路由的 response_model 未全部列出在 schema 定义中

**位置**：Files 表 schema 定义 L238-247 + 各 Task GREEN 段

**问题**：
- `app/api/schemas/__init__.py` 只列在 Files 表没说暴露内容
- `SessionListResponse` 和 `SessionDetailResponse` 在 GREEN 段被引用但 Files 表 schema 文件只说了 `SessionListItem`
- `IngestProgressResponse` GREEN 段用的字段（progress / error / created_at / updated_at）在 Files 表 schema 定义中未完整列出

**修改**（Files 表 schema 段补全所有 Response schema 字段）：

```python
# app/api/schemas/sessions.py
class SessionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessions: list[SessionListItem]
    total: int

class SessionDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    thread_id: str
    messages: list = []  # M10 后从 checkpoint 读完填充
    created_at: datetime
    updated_at: datetime

# app/api/schemas/ingest.py
class IngestProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: str
    progress: float | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

class IngestAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: str = "accepted"
```

---

### P2-2 · `_check_*` 函数拆到独立文件提法过晚（REFACTOR 在 Task 2 末）——应直接做

**位置**：Task 2 REFACTOR L347

**问题**：
- REFACTOR 说"把 `_check_*` 拆到 `app/api/health_checks.py`"——但 Task 2 写的是上午 Task，REFACTOR 在下午做
- health.py 当前 GREEN 段内联 4 个私有函数，一旦 `health.py` 超过 100 行再拆已经有技术债

**修改**：直接将 4 个 `_check_*` 函数写在 `app/api/health_checks.py`，`health.py` 只留 router 函数+Lifespan 调用。删 REFACTOR 步骤。

---

### P2-3 · 缺 middleware 挂载顺序文档 / 注释

**位置**：Task 13 GREEN 段 L809-810

**问题**：
- `create_app()` 中 middleware 顺序：RequestIdMiddleware → CORSMiddleware
- 最佳实践：CORS 应最先处理 OPTIONS preflight，再 RequestId（用于 tracing），再潜在 Auth
- 当前 order 不会出错（CORS 只拦截 preflight，不影响 tracing），但没注释说明

**修改**（加注释）：

```python
app.add_middleware(CORSMiddleware, ...)   # 1. CORS preflight（不依赖 tracing）
app.add_middleware(RequestIdMiddleware)   # 2. Request tracing（所有后续中间件/路由有 request_id）
# ↓ future: RateLimitMiddleware (M12)  # 3. 限速（依赖 request_id for per-user limit）
```

---

### P2-4 · `GET /api/sessions` 硬编码 `limit(50)`——应可配置

**位置**：Task 4 GREEN 段 L402

**问题**：
- hardcode `limit(50)` 不够灵活；大户用户可能有 200+ 活跃 session
- 没有 `offset`/`cursor` 参数，前端分页在 V1 阶段不可用

**修改**：用 settings 控制默认：

```python
stmt = (select(ChatSession).where(...).order_by(...).limit(settings.api.default_session_page_size))
```

`APISettings.default_session_page_size: int = 50`。

---

### P2-5 · `RequestIdMiddleware` 写在 `app/main.py` 内联类而非独立文件

**位置**：Task 3 GREEN 段 L359-367 + Task 13 main.py L809

**问题**：
- `RequestIdMiddleware` 作为类定义在 `app/main.py` 内——如果 M12 要读取/修改 request_id 行为，得改 main.py
- 内联类不能被其他文件单独 import

**修改**：拆到 `app/api/middleware.py`：

```python
# app/api/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
import uuid

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response
```

`app/main.py` 改为 `from app.api.middleware import RequestIdMiddleware`。

---

### P2-6 · `POST /api/chat` 新 session 标题截取 `req.query[:50]` 缺少安全剪裁

**位置**：Task 7 GREEN 段 L541

**问题**：
- `title=req.query[:50]`——50 字符截断，但如果 query 是 HTML/emoji/surrogate 对，Python 字符串切片会截断在中间出乱码
- 标准做法是截取 `grapheme` 或 UTF-8 byte aware

**修改**：

```python
import unicodedata

def safe_truncate(text: str, max_bytes: int = 100) -> str:
    """按 UTF-8 byte length 截取，不截断在 multi-byte 中间"""
    encoded = text.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore")

title = safe_truncate(req.query.strip().replace("\n", " "), 50)
```

---

### P2-7 · `app/main.py` `create_app()` 工厂模式 lifespan 缺 shutdown 前的 health check 关闭

**位置**：Task 13 GREEN 段 L797-801

**问题**：
- lifespan yield 后马上 `engine.dispose()`（如果 P0-2 已修）——但可能此时还有 health check 请求在读 DB
- 应采用 `app.state.shutdown_event = asyncio.Event()` + health check 端点检查该 event

**修改**（非强制，P2 优化）：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.shutdown_event = asyncio.Event()
    async with make_checkpointer() as cp:
        app.state.graph = compile_workflow(checkpointer=cp)
        app.state.checkpointer = cp
        yield
    app.state.shutdown_event.set()   # 通知 health check 开始返回 503
    await asyncio.sleep(0.5)          # 给 in-flight 请求 500ms 缓冲
    await engine.dispose()
```

health check 端点检测 `request.app.state.shutdown_event.is_set()` → 如果 True 返回 503。

---

### P2-8 · 缺 `APP_ENV` 环境感知（Swagger docs / debug / CORS）

**位置**：Task 13 GREEN 段 L803-813

**问题**：
- `create_app()` 没有根据 `APP_ENV`（dev/staging/prod）调整行为
- 生产环境不应暴露 `/docs`（Swagger UI）——FastAPI 默认开
- CORS origins 在 prod 应严格限制，dev 可用 `["*"]`

**修改**（`app/config.py` 补）：

```python
class APISettings(BaseSettings):
    env: str = "dev"  # dev / staging / prod
    cors_origins: list[str] = ["*"] if env == "dev" else ["https://gradio.mydomain.com"]
    expose_docs: bool = env == "dev"
```

`create_app`：

```python
app = FastAPI(..., docs_url="/docs" if settings.api.expose_docs else None, redoc_url=None)
```

---

## 新发现问题汇总

| # | 问题 | 档次 | 简要说明 |
|---|------|------|----------|
| 1 | `POST /api/chat` 无 `asyncio.wait_for()` 超时保护 | **P0** | graph.ainvoke 可能 hang 60s+，导致 uvicorn worker 满 |
| 2 | lifespan 关闭缺 `engine.dispose()` | **P0** | asyncpg 连接池不关闭，restart 后旧连接残留 |
| 3 | health check 5 service 探测缺具体 URL/timeout/auth | **P0** | OpenSearch/TEI/Langfuse 的 _check 函数无具体实现细节 |
| 4 | 503 降级文案硬编码 | P1 | fallback_message 应在 settings 中可配置 |
| 5 | `_count_messages` 未实现 | P1 | Task 4 引用了不存在的函数，当前产生 N+1 |
| 6 | get_orchestrator fallback 路径重复建 graph | P1 | 每次 fallback 编译新 graph，连接泄漏 |
| 7 | lifespan fallback 测试路径不可达 | P1 | `create_app` 不允许 override lifespan |
| 8 | deps.py get_db 缺 AsyncSession 类型标注 | P1 | FastAPI Depends 返回类型明确更好 |
| 9 | sessions 列表缺软删除过滤 | P1 | 只 filter is_active，未处理 deleted_at |
| 10 | POST /api/ingest 501 缺 M4 合并 TODO | P1 | 501 stub 在 M4-M6 接入后需删除 |
| 11 | Response schema 文件字段不全 | P2 | SessionListResponse / SessionDetailResponse / IngestProgressResponse 各字段未完整定义 |
| 12 | _check* 拆分提法过晚 | P2 | 应直接在 health_checks.py 写，不内联 |
| 13 | middleware 挂载顺序无注释 | P2 | 应标注各 middleware 的职责和挂载理由 |
| 14 | sessions limit(50) 硬编码 | P2 | 应改为 settings.api.default_session_page_size |
| 15 | RequestIdMiddleware 内联在 main.py | P2 | 应拆到 app/api/middleware.py |
| 16 | session title 截取可能截断 multi-byte | P2 | Python 切片在 surrogate/emoji 上出乱码 |
| 17 | 缺 APP_ENV 环境感知 | P2 | Swagger docs / CORS / debug 行为不区分环境 |

---

## 落地建议

1. **必须先修 3 个 P0** 再动手写任何代码：
   - P0-1：`asyncio.wait_for()` 包装 graph.ainvoke（在 Task 7 和主流程中）
   - P0-2：lifespan 关闭时 `engine.dispose()`（在 Task 13 和 lifespan 函数中）
   - P0-3：health check 探测具体 URL 和 timeout（在 Task 2 和 health_checks.py 中）

2. **M7 review 依赖请在 M7 修订后验证**再启动 M8 集成测试：
   - M7 P0-3（checkpointer contextmanager）：M8 lifespan 依赖它正确工作
   - M7 P0-6（answer_chitchat_node）：M8 chat 端点依赖 graph 不走入死分支
   - M7 P0-8（节点异常传播）：M8 的 502/503 映射依赖正确的异常类

3. **TDD 顺序建议**：
   - Day 1 (Tasks 1-5)：完全独立，不依赖 M7 graph——可先写
   - Day 2 (Tasks 6-9)：依赖 M7 的 compile_workflow 和 checkpointer——确认 M7 修完 P0-2/P0-3/P0-6 后再做
   - Day 3 (Tasks 10-14)：集成测试依赖所有前面的——最后做

4. **跨 M 契约验收点**：
   - M2 auth router prefix 策略与 M8 `api_router` 一致（双 prefix 检查）
   - M7 `make_checkpointer` 工厂签名与 M8 lifespan 用法匹配
   - M3 `make_llm` 回调注入方式（M8 不注入回调，只在 metadata 传 request_id）

5. **值得抄 M3 范本的结构闪光点**：
   - 数据流图（L84-119）：用 ASCII 图把鉴权→session→graph→异常的请求路径画清，其他 M 都应复制
   - 测试矩阵表（L888-903）：12 个场景全覆盖 spec §5 错误矩阵，格式可被 M9-M12 复用
   - 避雷基线（L8）：显式标注已有 review 中影响本 M 的项，方便 reviewer 快速验证

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M8-review-r0 | 2026-06-11 | 初稿（11 段结构审查 + 已有 review 10 项验证 + M7 交叉 4 项 + M2/M3 交叉 2 项 + 3 P0 + 6 P1 + 8 P2 + 落地建议 5 条） |
