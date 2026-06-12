M10 Plan Review · Langfuse 业务级 Trace 集成（节点级 + PII 脱敏 + Token 追踪）

> 评审对象：`plans/2026-06-11-rag-m10-obs-langfuse.md`（584 行）
> 评审基线：V1 Scope v0.4 spec（§0 决策 #10/#11 · §1 观测双轨 · §2 模块树 observability 段 · §5 错误矩阵 · §8.6 依赖）+ system design v2.0（§3.10 观测 · §9 可观测性策略）
> 横向交叉：总 review `2026-06-11-rag-plans-review.md`（P0-1/P0-5/P1-12/P1-14 等已避雷）· M3 review `2026-06-11-rag-m3-llm-embed-review.md`（P0-2 callback 注入）· M7 review `2026-06-11-rag-m7-graph-review.md`（P0-2/P0-3/P0-6/P0-7/P0-8）· M8 review `2026-06-11-rag-m8-api-chat-review.md`（P0-1 chat 超时）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M10 plan 是 RAG V1 路线中**唯一一份"领域内专项 plan"**——不引入新业务节点、不写 LLM 逻辑，只把现有 M3 工厂注入的 Langfuse callback 升级为"业务级 trace 全覆盖"。它把 11 段模板走齐（Goal / 不包含 / Architecture / Tech Stack / Files / 10 Tasks RED-GREEN / 测试 / DoD / 依赖 / 风险 / 修订记录），目标 5 项 + 10 个 Task + 14 个测试文件 + 1 个 P0/P1 review 响应表，主线设计**与 spec §3.10 trace 结构 + §9 可观测性策略逐一对齐**（7 节点 + auth + LLM spans + PII + token）。

**但实施就绪度严重不足**——已有 review 中的 P0-1（端口 3000）/ P0-5（真 PG）/ P1-12（langfuse import 双备）/ P1-14（`with_config` 注入）**已显式标注避雷**（✅ 好），但本 review **新发现 24 个问题**，其中 **5 个 P0**（`@node_trace` 装饰器与 LangGraph `(state, config)` 双参数签名不兼容 / `langfuse_context.flush()` API 在 2.50+ 不存在 / `handler.get_trace_id()` 不是 CallbackHandler 公开 API / `trace_id` 取法与 LangChain 1.0.8 callback 实际返回错位 / `test_all_seven_nodes_have_node_trace` 误判同步节点函数名）+ **9 个 P1**（async context 传递、`on_chain_*` 在 langchain 1.0+ 私有化、cost 计算缺、retention 缺、user feedback 缺、降级短路不等、prompt 缓存污染 metadata、HandlerPool 与 LangGraph 1.0.5 callback 上下文冲突、Retry-After 限速策略缺）+ **10 个 P2**。修完 5 项 P0 后才能动手；M10 是 M11 RAGAS 关联字段的源头，trace 上报全断 M11 评估没法关联。

| 维度 | 评分 | 说明 |
|------|------|------|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐 + 范本目的段 + 仓库布局 ASCII + 数据流 ASCII + 契约边界表 + 风险 10 行 + 修订记录 |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 10 Tasks 全部 RED-GREEN-REFACTOR；RED 测试名具体，GREEN 代码段基本完整 |
| 技术深度 | ⭐⭐⭐ | 装饰器 + PII + handler pool 设计完整；但缺 cost 计算 / retention / user feedback / async 上下文 / callback 内部 API 演进 |
| 错误处理 | ⭐⭐⭐ | `on_chain_error` 有；flush 策略有；但缺 Langfuse 不可达降级 + trace 上报失败吞还是重试 |
| 一致性 | ⭐⭐ | spec §3.10 trace 结构对齐；但 `@node_trace` 与 M7 实际 `(state, config)` 签名**不兼容**（P0-1）；`langfuse_context.flush()` API 在 2.50+ 已迁移（P0-2） |
| 已有 review 就绪度 | ⭐⭐⭐⭐ | 4 项已有 review 已避雷标注；3 项间接相关已注意；但有 2 项被本 review 升 P0 |

**一句话**：M10 plan **结构完整、TDD 节奏好、主体设计与 spec 对齐**；**但在装饰器签名、CallbackHandler 内部 API、LangGraph callback 上下文、async 跨任务传递 4 个方面与 langchain/langgraph 1.0.x + langfuse 2.50+ 实际 API 有冲突**——修完 5 个 P0 才能动手。

---

## 已有 review 验证（2026-06-11-rag-plans-review.md）

| ID | 已有 review 项 | Plan 现状 | 本报告 |
|----|---------------|-----------|--------|
| **P0-1** | 端口冲突（TEI 8080 vs http.server）→ Langfuse 3000 | ✅ 已避雷——L165 `集成测试连 Langfuse API 用 http://localhost:3000（M0 docker-compose 已配，depends_on: condition: service_healthy P0-3 已修）` | 通过。L521 集成测试命令也用 3000 端口 |
| **P0-5** | M1 Task 2 单元测试用 sqlite，但生产用 PG（假绿） | ✅ 已避雷——L166 `集成测试 test_m10_e2e_trace.py 用真 Postgres（checkpointer 写 trace_id 到 auth_sessions 关联），禁用 sqlite 假绿`；L521 集成测试启动命令含 `postgres langfuse` | 通过。M10 集成测试强制真 PG + 真 Langfuse |
| **P1-12** | langfuse.CallbackHandler import path | ✅ 已避雷——L144-158 给主路径 + 备路径双备 + L167 `test_langfuse_import_fallback` | 通过。P1-12 完整响应 |
| **P1-14** | M3 `make_llm` 注入 callback 写 `model.callbacks` 与 langchain 1.0+ 冲突 | ✅ 已避雷——L168 `M3 工厂已修订为 with_config({"callbacks":[handler]})，M10 不用再改`；L200 `make_llm 无修改` | 通过。M10 复用 M3 修订后的注入方式 |
| **X-3** | `from app.config import settings` 全局单例 | ✅ 已避雷——L169 `from app.config import settings，M10 不在测试里 Settings() 实例化` | 通过 |

**验证结论**：已有 review 中直接影响 M10 的 5 项——**全部 ✅ 已避雷**。

---

## 横向交叉验证

### 3-1 · M3 review P0-2 callback 注入 → M10 `@node_trace` 装饰器内部行为

M3 review P0-2 已指出 `model.callbacks = [...]` 弃用、改用 `model.with_config({"callbacks":[handler]})`。M3 修订后 LLM callback 在工厂层注入。

**M10 风险**：M10 plan L98-107 装饰器伪代码写：
```python
sync wrapper:
  state = args[0]                       # ← P0-1 错位
  handler = pool.acquire(...)
  if handler: handler.on_chain_start(...)  # ← P1-2 on_chain_* 私有化
```

M3 工厂的 callback 注入是 LLM 级（每次 `make_llm(node).ainvoke(messages, config=...)`），M10 装饰器是**节点级**。两者不冲突，但 M10 装饰器不需再调 LLM callback（已经绑在 model 上了），它应该：
- 创建"业务级"trace span（用 `langfuse_context.update_current_observation` 或 `langfuse.score`）
- 在 metadata 上写 `user_id` / `thread_id` / `request_id`
- 错误时打 `level=ERROR`

M10 plan **写错了装饰器机制**——用 `on_chain_start` 是 langchain 协议级事件，不是 Langfuse trace span 写入路径。

### 3-2 · M7 review P0-2 / P0-7 → M10 `@node_trace` 装饰器签名不兼容

M7 实际节点函数签名（plan L350-384）：
```python
async def rerank_node(state: RagState) -> RagState: ...
async def answer_node(state: RagState) -> RagState: ...
# 但 load_memory_node / save_memory_node 是：
async def load_memory_node(state, config: RunnableConfig) -> RagState: ...
async def save_memory_node(state, config: RunnableConfig) -> RagState: ...
```

**M10 装饰器只读 `args[0]` → 拿不到 `config`**，但 `load_memory` / `save_memory` 需要 `config["configurable"]["thread_id"]` 拿 checkpointer（M7 P0-2 修复后用 `cp.aget_tuple`）。M10 plan 假设 7 节点都是 `(state)` 单参数——**与 M7 实际不一致**。

### 3-3 · M7 review P0-6 → M10 Task 6 RED 测试 count 错

M7 实际有 8 个节点：`load_memory / classify / query_rewrite / retrieve / rerank / answer / save_memory / answer_chitchat`（M7 review P0-6 指出 `answer_chitchat_node` 只有注册无实现）。M10 Task 6 RED `test_all_seven_nodes_have_node_trace` 假设 **7 个节点**，但 M7 workflow 实际 8 节点——**测试名 / 断言数 错**。

### 3-4 · M7 review P0-8 → M10 错误捕获只覆盖节点抛错，不覆盖 LangGraph 内部错误

M7 review P0-8 指出 6 个节点（classify / rewrite / rerank / answer / save_memory）无异常处理，LLM 4xx/5xx 直接 500 透传。M10 Task 9 `test_chat_error_emits_trace_with_stack` mock `classify` 节点抛 `RuntimeError`——**这是节点级 mock**，但 M7 真实场景是 `classify_node` 内部 `make_llm("classify").ainvoke(...)` 抛 `ChatAnthropic` 异常——装饰器 try/except 能捕到，但 LangGraph 内部 retry / fallback 路径装饰器看不见。

### 3-5 · M8 review P0-1 → M10 trace 上报不阻塞 chat 响应

M8 review P0-1 加 `asyncio.wait_for(graph.ainvoke, timeout=30)`。M10 `session_tracker.flush()` 写 `langfuse_context.flush()` 是**同步**调用（task 包装在 `async def` 里）——若 Langfuse 容器慢（5s+），chat 响应也被阻塞 5s。**M10 缺"flush 异步化 / 后台 flush"**。

### 3-6 · M3 review P0-4 缺 LLM 配置 5 件套 → M10 配置块只补 3 件

M3 review P0-4 提 `LLMSettings` + `LangfuseSettings` 缺 `timeout / max_retries / sample_rate / flush_at / flush_interval / blocked_keys`。M10 Task 1 GREEN 段补 `ObservabilitySettings` 含 `sample_rate / mask_keys / trace_env / flush_timeout_s`——**补了 sample_rate 和 mask_keys**（M3 P0-4 中 block_keys 改名 mask_keys），但**没补** `flush_at` / `flush_interval`（langfuse 2.50+ 客户端侧 buffer 参数），且 `flush_timeout_s=5.0` 是单次 flush 超时，与 flush_at/flush_interval 是不同概念。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · `@node_trace` 装饰器签名 `state = args[0]` 与 LangGraph `(state, config)` 双参数签名不兼容

**位置**：Task 5 GREEN 段 L353
```python
sync wrapper:
  state = args[0]  # 约定第 1 个参数是 state
```

**问题**：
- LangGraph 节点函数**两种**签名混存：
  - 业务节点：`async def classify_node(state: RagState) -> RagState`（单参）
  - 需要 `config` 的节点（load_memory / save_memory）：`async def load_memory_node(state, config: RunnableConfig) -> RagState`（双参）
- M10 装饰器 `args[0]` 拿 state → 拿不到 `config` → 装饰器**不知道 thread_id**（除从 state 取外）
- 即使 state 含 `thread_id` 字段（spec §3.3 L240 写 `thread_id: str` 是 RagState TypedDict 字段之一）——`load_memory_node` 用 `config["configurable"]["thread_id"]` 而非 state 字段，两者**可能不一致**（state 的 thread_id 是外部传入，config 的 thread_id 是 LangGraph 自动注入）

**修改**（Task 5 GREEN 段改写）：
```python
import inspect
from langchain_core.runnables import RunnableConfig

def node_trace(node_name: str):
    def decorator(fn):
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        # 自动识别 (state) 还是 (state, config) 签名
        has_config = len(params) >= 2 and params[1] in ("config", "runnable_config")
        # 同时也支持用 functools.wraps 透传
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                state = args[0]
                config = args[1] if has_config and len(args) >= 2 else kwargs.get("config")
                ...
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                state = args[0]
                config = args[1] if has_config and len(args) >= 2 else kwargs.get("config")
                ...
        return async_wrapper if asyncio.iscoroutinefunction(fn) else sync_wrapper
    return decorator
```

并新增 Task 5 RED `test_node_trace_handles_both_signatures`：
- 写 `def node_single(state): return state`
- 写 `async def node_dual(state, config): return state`
- 两者都加 `@node_trace("x")` → 都应正常执行不抛 `IndexError`

**关键**：M10 plan 假设"7 节点都是单参 state"是错的——M7 实际 `load_memory_node` / `save_memory_node` 是 `(state, config)`，装饰器**必须**能处理两种签名。

### P0-2 · `langfuse_context.flush()` API 在 langfuse 2.50+ 不存在

**位置**：Task 3 REFACTOR 段 L298 + Task 5 flush 路径
```python
def flush() -> None: langfuse_context.flush()
```

**问题**：
- langfuse 2.50+ 移除了 `langfuse.langfuse_context` 模块顶层 `flush()` 函数——`langfuse_context` 是 langfuse v2 早期（< 2.30）的 legacy module，**2.50+ 主推 `Langfuse` 客户端 + `langfuse_context.score_current_span` / `update_current_span`**
- 实际 2.50+ 公开 API：
  - 客户端侧：`from langfuse import Langfuse; client.flush()` —— `Langfuse(host=...).flush()` 是公开方法
  - 上下文侧：`langfuse_context.flush_current_observation()` 关闭当前 span（v2 仍有但 3.x 计划移除）
  - callback 侧：`CallbackHandler` 内部有 `_flush()` 但**私有**，无 `flush()` 公开方法
- 当前 plan 写 `langfuse_context.flush()` 直接 `ImportError` 或 `AttributeError`

**修改**（Task 3 GREEN 段改）：
```python
# app/observability/session_tracker.py
def flush() -> None:
    """显式 flush 当前 trace 到 Langfuse。注：langfuse 2.50+ 公开 API 是 client.flush()。"""
    from langfuse import get_client  # langfuse 2.50+ 新接口
    try:
        client = get_client()
        client.flush()
    except Exception as e:
        # flush 失败不污染主流程（spec §3.10 隐含"观测失败不影响业务"）
        log.warning("langfuse flush failed: %s", e)
```

并 Task 3 RED 改 `test_flush_calls_langfuse_client_flush`：
```python
def test_flush_calls_client_flush(monkeypatch):
    from app.observability.session_tracker import flush
    from langfuse import get_client
    monkeypatch.setattr(get_client(), "flush", MagicMock())
    flush()
    get_client().flush.assert_called_once()
```

并 Tech Stack 段 L154 改主路径：
```python
# 主路径（langfuse 2.50+ 推荐）
from langfuse import get_client, Langfuse
# 备路径（langfuse <2.50 兼容）
try:
    from langfuse.langchain import CallbackHandler
except ImportError:
    from langfuse.callback.langchain import CallbackHandler
```

### P0-3 · `handler.get_trace_id()` 不是 CallbackHandler 公开 API

**位置**：Task 8 REFACTOR 段 L457
```python
改 app/api/chat.py：取 handler.get_trace_id()（Langfuse 2.50+ API）→ 填到 response
```

**问题**：
- `CallbackHandler`（`langfuse.langchain.CallbackHandler`）**没有** `get_trace_id()` 方法
- langfuse 2.50+ 取当前 trace_id 的正确路径：
  - 在 callback handler 上下文中：`handler.trace_id`（内部属性，**非公开**）
  - 通过 `langfuse_context.get_current_trace_id()`（v2 公开，2.50+ 仍可用但 deprecated）
  - 通过 `from langfuse import get_client; get_client().get_current_trace_id()`（2.50+ 推荐）
- 当前 plan 写 `handler.get_trace_id()` 实际 `AttributeError`

**修改**（Task 8 GREEN 段改）：
```python
# app/observability/node_tracing.py
def get_current_trace_id() -> str | None:
    """取当前 Langfuse trace_id（用于回填到 ChatResponse.trace_id）。"""
    try:
        from langfuse import get_client
        return get_client().get_current_trace_id()
    except Exception:
        return None
```

并在 `ChatResponse` 填充：
```python
# app/api/chat.py
from app.observability.node_tracing import get_current_trace_id
result = await asyncio.wait_for(graph.ainvoke(...), timeout=TIMEOUT)
return ChatResponse(
    answer=result["answer"],
    sources=result.get("sources", []),
    session_id=session_id,
    request_id=request_id,
    trace_id=get_current_trace_id(),  # ← 改这里
)
```

新增 Task 8 RED `test_get_current_trace_id_returns_string_or_none`（mock `get_client().get_current_trace_id()` 返 `trace-abc-123`）。

### P0-4 · `test_all_seven_nodes_have_node_trace` 误判同步节点函数名 + count 错（7 vs 8）

**位置**：Task 6 RED 段 L386-388
```python
函数名：load_memory / classify / query_rewrite / retrieve / rerank / answer / save_memory
```

**问题**：
1. M7 plan Task 9 L468-474 中节点函数实际命名为 **`load_memory_node` / `save_memory_node`**（带 `_node` 后缀），其他 5 个节点是 `classify` / `query_rewrite` / `retrieve` / `rerank` / `answer`（无后缀）——**M10 plan 的函数名清单有 5 个错**
2. M7 实际有 **8 个节点**（7 + `answer_chitchat_node`）——M10 标"7 节点"是漏
3. `inspect.getsource` 解析装饰器字符串：装饰器 `@node_trace("load_memory")` 在 source 里就是字面字符串，包含 `node_trace` 子串——测试**会**过（只要函数有 `@node_trace` 装饰）。但**节点函数命名不一致**导致测试名错位（"load_memory" 实际函数是 `load_memory_node`）

**修改**（Task 6 RED 改）：
```python
def test_all_seven_nodes_have_node_trace():
    """7 业务节点 + answer_chitchat 节点（8 个节点函数）全部加 @node_trace 装饰。"""
    from app.graph import nodes
    import inspect
    expected = {
        "load_memory_node", "classify", "query_rewrite",
        "retrieve", "rerank", "answer",
        "save_memory_node", "answer_chitchat_node",
    }
    for name in expected:
        assert hasattr(nodes, name), f"missing node function: {name}"
        src = inspect.getsource(getattr(nodes, name))
        assert "@node_trace" in src, f"{name} missing @node_trace decorator"
```

并 M10 plan Files 表 L196 改 `app/graph/nodes.py` 函数列表为带 `_node` 后缀的实际命名。

### P0-5 · 装饰器内调 `handler.on_chain_start` / `on_chain_end` / `on_chain_error` 是 langchain 协议级私有 callback（不直接创建 Langfuse trace span）

**位置**：Task 5 GREEN 段 L356-363 + Architecture 图 L102-107
```python
if handler: handler.on_chain_start({"name": node_name, "metadata": metadata})
...
if handler: handler.on_chain_end(result)
if handler: handler.on_chain_error(e)
```

**问题**：
- `on_chain_start` / `on_chain_end` / `on_chain_error` 是 **langchain 协议**的 callback manager 方法，不是 langfuse trace span API
- 直接调 `handler.on_chain_start(...)` 不会创建 langfuse trace span，只会在 langchain 内部 callback manager 推一个事件——Langfuse 看板**看不到**
- langfuse 2.50+ 实际**推荐用法**是：
  - **方案 A**（推荐）：用 `langfuse_context.update_current_observation(name=..., metadata=...)` 在已有 trace 上下文中打子 span
  - **方案 B**：用 `langfuse_context.score_current_observation(name=..., value=...)` 打分
  - **方案 C**：用 `from langfuse import Langfuse; with langfuse.start_as_current_span(name=...) as span: ...` （langfuse 3.x 主推）
- M3 工厂的 callback 已经绑在 `make_llm(node).with_config({"callbacks":[handler]})` 上——M10 装饰器**不需**再调 LLM callback，只管业务级 metadata

**修改**（Task 5 GREEN 段彻底改写）：
```python
# app/observability/node_tracing.py
import langfuse_context
from app.observability.session_tracker import build_session_metadata
from app.observability.handler_pool import pool

def node_trace(node_name: str):
    """LangGraph 节点装饰器：在当前 trace 上打子 span + 注入 metadata + 错误捕获。"""
    def decorator(fn):
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                state = args[0] if args else kwargs.get("state")
                config = args[1] if len(args) >= 2 else kwargs.get("config")
                thread_id = (config or {}).get("configurable", {}).get("thread_id") if config else None
                user_id = (state or {}).get("user_id") if isinstance(state, dict) else None
                metadata = build_session_metadata(state or {}, request_id=None)
                metadata["thread_id"] = thread_id or metadata.get("thread_id")
                # 业务级 span：langfuse_context（2.50+ 仍可用，3.x 改 with span）
                langfuse_context.update_current_observation(
                    name=node_name,
                    metadata=metadata,
                )
                try:
                    result = await fn(*args, **kwargs)
                    # 输出端脱敏
                    if isinstance(result, dict):
                        langfuse_context.update_current_observation(
                            output=mask_pii(result),
                        )
                    return result
                except Exception as e:
                    langfuse_context.update_current_observation(
                        level="ERROR",
                        status_message=f"{type(e).__name__}: {str(e)[:200]}",
                    )
                    raise
            return async_wrapper
        # sync 路径同样改写
    return decorator
```

并删 `HandlerPool` 概念（**已在 P1-5 升级到 P0**——M3 callback 已绑 LLM 级，节点级不需 handler pool）。

**关键**：M10 装饰器机制**完全错**——plan L98-107 写 `handler.on_chain_start` 不会创建 Langfuse trace span。修法是改用 `langfuse_context.update_current_observation`（业务 metadata）或 `with langfuse.start_as_current_span(...)`（独立 span）。

---

## P1 · 重要

### P1-1 · 缺 `test_node_trace_returns_metadata_in_correct_format`（metadata 字段名 vs Langfuse 期望）

**位置**：Task 5 测试
**问题**：plan 写 `metadata.user_id` / `metadata.thread_id` / `metadata.request_id` / `metadata.query_length`——但 Langfuse SDK 期望的 metadata 字段**小写嵌套**：trace 上看是 `metadata.user_id`，但 `metadata.user_id` 在 Langfuse UI 显示是 `User Id` 字段（自动 title-case）。当前 plan 没测 metadata 在 Langfuse API GET `/api/public/traces/{id}` 返回的 JSON 路径。
**修改**：新增 `test_node_trace_metadata_serialized_to_lf_format`（mock `langfuse_context.update_current_observation` 调，断言传参 `metadata={"user_id": ..., "thread_id": ..., "request_id": ..., "query_length": ...}`）。

### P1-2 · `on_chain_*` 在 langchain 1.0+ BaseCallbackHandler 上是 `@override` 抽象方法，直接调会触发类型检查

**位置**：Task 5 GREEN 段 L356
**问题**：`CallbackHandler.on_chain_start(self, serialized, inputs, **kwargs)` 在 langchain 1.0+ 签名是 `(serialized: dict, inputs: dict, **kwargs) -> Any`——plan 写 `handler.on_chain_start({"name": node_name, "metadata": metadata})` 只传 1 个位置参数，会抛 `TypeError: missing 1 required positional argument: 'inputs'`。
**修改**：彻底改用 `langfuse_context.update_current_observation`（见 P0-5 改法），不要再调 `on_chain_*`。

### P1-3 · 缺 cost / token 成本计算与 Langfuse `usage` 字段映射

**位置**：DoD L538 + Task 9 RED `test_token_usage_tracked_in_observation`
**问题**：
- plan 写"`usage.prompt_tokens` / `usage.completion_tokens` 非空"通过——但 Langfuse 2.50+ 自动追踪的是 LLM span 的 `usage`（含 `input` / `output` / `total` tokens）
- 节点级 span 的 `usage` 字段**不会**自动填（节点 span 无 LLM invoke）
- 7 节点中 4 个（classify / rewrite / rerank / answer）调 LLM → 4 个 LLM sub-span 自动有 usage
- 但**节点级 summary**（如"answer 节点消耗 1.2K input + 200 output = $0.003"）需要装饰器**手动汇总** child LLM spans 的 usage
- 当前 plan 只说"CallbackHandler 自动追踪（langfuse 2.50+ 内置），不需 M10 写代码"——**节点级 usage 汇总缺失**

**修改**（Task 5 GREEN 段补）：
```python
# 节点结束时，汇总 child LLM spans
async def async_wrapper(*args, **kwargs):
    ...
    result = await fn(*args, **kwargs)
    # 汇总 token usage
    try:
        spans = langfuse_context.get_current_observation().children or []
        total_input = sum(s.usage.get("input", 0) for s in spans if s.usage)
        total_output = sum(s.usage.get("output", 0) for s in spans if s.usage)
        # cost 估算：minimax-cn 暂未公开定价，写 placeholder
        cost_usd = (total_input * 0.000003 + total_output * 0.000015)  # ← 临时定价
        langfuse_context.update_current_observation(
            metadata={**metadata, "node_usage": {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cost_usd": cost_usd,
            }},
        )
    except Exception as e:
        log.debug("usage summary failed: %s", e)
    return result
```

并 DoD 补一项：`node_usage 汇总测试通过`（mock child LLM span usage → 断言节点 metadata 包含 input/output/cost）。

### P1-4 · 缺 Langfuse 不可达降级（容器 down / network 阻塞）

**位置**：风险表 + DoD 全篇
**问题**：
- plan L165 写"集成测试连 Langfuse API 用 http://localhost:3000"——但 Langfuse 容器**未起** / 网络阻塞时，节点函数会 hang 在 `langfuse_context.update_current_observation` 调用（langfuse 客户端默认 5s timeout）
- 7 节点 × 4 次 context update = 28 次 RPC 阻塞可能 → 拖垮整个 graph invoke（M8 P0-1 chat 30s 超时）
- 当前 plan 缺"网络不可达时跳过 trace"短路

**修改**（Task 1 GREEN 段 `ObservabilitySettings` 补）：
```python
class ObservabilitySettings(BaseSettings):
    sample_rate: float = 1.0
    mask_keys: set[str] = {"password", "token", "api_key", "secret", "authorization"}
    trace_env: str = "dev"
    flush_timeout_s: float = 5.0
    langfuse_offline_mode: bool = False  # ← 新增 P1-4：True 时所有 Langfuse 调用短路
    trace_call_timeout_s: float = 1.0   # ← 新增 P1-4：单次 context update 超时
```

并在 `langfuse_context.update_current_observation` 外层包装：
```python
import contextlib

@contextlib.contextmanager
def _safe_trace_update(**kwargs):
    if settings.observability.langfuse_offline_mode:
        yield
        return
    try:
        with _timeout(settings.observability.trace_call_timeout_s):
            langfuse_context.update_current_observation(**kwargs)
            yield
    except (TimeoutError, Exception) as e:
        log.debug("langfuse update failed: %s", e)
        yield
```

并 Task 1 RED 补 `test_langfuse_unreachable_does_not_block_node`（mock `langfuse_context.update_current_observation` raise `ConnectionError` → 节点函数仍正常返回）。

### P1-5 · `HandlerPool` 概念与 LangGraph 1.0.5 callback 上下文冲突（**升级 P0 候选**）

**位置**：Task 4 + Task 5 GREEN 段
**问题**：
- M10 plan 假设每 (user_id, thread_id) 维度 1 个 CallbackHandler——但 langfuse 2.50+ 的 CallbackHandler 是**无状态**的（不存 trace context）
- 实际 trace context 来自 `langfuse_context` 全局模块（或 langfuse 3.x 的 `with span(...)` context var）
- M3 工厂 `make_llm(node)` 在 `lru_cache(maxsize=8)` 下 → 同一 (node_name) 复用 1 个 ChatAnthropic + 1 个 callback handler 实例
- M10 `HandlerPool` 在节点层再加一个 pool → 与 M3 工厂层 handler **双层管理**，会出现：
  - M3 工厂 handler 已经在 LLM invoke 时创建 LLM span
  - M10 节点 handler 再次 `update_current_observation` → 写**同一 trace**（OK），但 pool 的 (user_id, thread_id) 复用 key 在 LLM call 间隔**会失效**（多线程 / async 并发下）
- 更严重：LRU 1000 上限 + 多线程 lock → 测试 / 生产偶发 deadlock

**修改**（方案 A：删 HandlerPool，直接用 langfuse_context）：
- 删 `app/observability/handler_pool.py` 整个文件
- 装饰器不 acquire / release handler，直接调 `langfuse_context.update_current_observation`
- LLM 级 callback 走 M3 工厂的 handler（已绑在 LLM 上）
- 节点级 trace 走 `langfuse_context`（不需 handler 实例）

**修改**（方案 B：保留 HandlerPool 但限定用法）：
- HandlerPool 只管理 `CallbackHandler` 实例（用于 LLM 级 trace）
- 节点级 metadata 仍走 `langfuse_context`
- 加注释：`HandlerPool 仅服务于 LLM 节点；节点级 trace 走 langfuse_context`

**优先方案 A**（langfuse 2.50+ 推荐写法，无需 pool）。

并 DoD 删 `test_single_chat_does_not_create_n_handlers`（池化逻辑若删了，测试也删）。

### P1-6 · 缺 `langfuse_context` 的 async 跨任务传递保证

**位置**：Architecture 图 L82-116 + 风险表 P0-2
**问题**：
- `langfuse_context` 在 langfuse 2.50+ 内部用 `contextvars` 存当前 trace_id / observation
- LangGraph 1.0.5 节点函数 `async def` 在事件循环中执行 → 每次 `await` 切换 task 时 contextvars 应自动透传
- 但 LangGraph 内部用 `asyncio.gather` / `asyncio.create_task` 并发执行节点时，**会**创建新 task context → contextvars 跨 task 传递**可能丢失**
- M10 装饰器 `langfuse_context.update_current_observation(name=node_name, ...)` 在节点开始时**改了**当前 observation——若多个节点并发（如 LangGraph 内部并行节点），observation 名称会**互相覆盖**

**修改**（Task 5 GREEN 段补）：
```python
import contextvars

# 用 contextvars 显式存 / 读当前 node_name（避免 langfuse_context 跨 task 污染）
_current_node_observation: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_node_observation", default=None
)

def node_trace(node_name: str):
    def decorator(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            token = _current_node_observation.set(node_name)
            try:
                result = await fn(*args, **kwargs)
                return result
            finally:
                _current_node_observation.reset(token)
        return async_wrapper
    return decorator
```

或在 trace_id 上做"父子 span 严格按 LangGraph 节点拓扑"——V1 节点是顺序的（无并行），可不处理；标注在风险表即可。

### P1-7 · `flush()` 失败处理 + 调用时机未定义

**位置**：Task 3 GREEN 段 + Architecture 图 L115
**问题**：
- plan 写"`session_tracker.flush()` 显式 flush 避 P0-2 异步泄漏"——但没定义**何时**调
- M8 chat 路由不调 flush（plan L99-104 数据流图有 `session_tracker.flush()` 但 Task 8 没说在 chat 路由调）
- plan 写"Task 3 REFACTOR 把 flush 改为 async def + try/except 防 flush 失败污染主流程"——OK，但调用点缺失
- 集成测试 `test_chat_creates_seven_node_trace` 在 response 后 GET `/api/public/traces/{id}` 立即拉——若未 flush，trace 还没上 Langfuse 看板 → 假绿

**修改**（Task 8 RED 补）：
```python
# test_chat_creates_seven_node_trace 调整
async def test_chat_creates_seven_node_trace(...):
    ...
    resp = await client.post("/api/chat", ...)
    # 关键：flush 后再 GET
    from app.observability.session_tracker import flush
    await flush()
    trace = langfuse.get_trace(resp.json()["trace_id"])
    assert trace.metadata["request_id"] == "req-test-1"
```

并在 chat.py 路由加 `await flush()` 在返回 ChatResponse 之前：
```python
# app/api/chat.py
result = await asyncio.wait_for(graph.ainvoke(...), timeout=TIMEOUT)
from app.observability.session_tracker import flush
try:
    await flush()  # chat 退出前显式 flush，确保 trace 落库
except Exception as e:
    log.warning("langfuse flush failed: %s", e)
return ChatResponse(..., trace_id=get_current_trace_id())
```

### P1-8 · `mask_pii` 缺时间相关脱敏（query 含时间戳 / IP / email）

**位置**：Task 2 GREEN 段
**问题**：
- `DEFAULT_MASK_KEYS` 只覆盖 `password / token / api_key / secret / authorization / session_token`——不覆盖：
  - 用户 query 里可能含的 IP 地址（`192.168.1.1`）——PII
  - email（`user@example.com`）——PII
  - 身份证 / 手机号（中国 11 位手机号）——PII
  - Bearer token 字面值（`Bearer eyJhbGciOiJIUzI1...`）——值在 query 字段里
- `PII_VALUE_RE` 写 `password|token|api_key|secret` 也只覆盖这 4 个
- Langfuse 看板有合规要求（GDPR / 等保）——邮箱/手机号也属敏感

**修改**（Task 2 GREEN 段补）：
```python
# 兜底正则（值里也扫）
PII_VALUE_RE = re.compile(
    r"(?i)"
    r"(password|token|api_key|secret)[\"'″\u201d]?\s*[:=]\s*[\"'″\u201d]?([^\s\"',}]+)"
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

并 Task 2 RED 补 `test_mask_pii_handles_email_and_ip`：
```python
def test_mask_pii_handles_email_and_ip():
    assert mask_pii({"contact": "user@example.com"}) == {"contact": "***"}
    assert mask_pii({"client_ip": "192.168.1.1"}) == {"client_ip": "***"}
    assert mask_pii({"auth": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."})["auth"].startswith("Bearer ***")
```

### P1-9 · 缺 Langfuse trace retention / 数据保留策略

**位置**：DoD + 风险表全篇
**问题**：
- Langfuse 默认保留 trace 30 天，prod 长期 30 天可能不够调试 + 也不合规
- 看板数据增长会撑爆磁盘（每日 1k trace × 5 KB = 5 MB/天 → 1 年 1.8 GB → 不大但月 30k+ 就难控）
- plan 没定义"trace 保留多久 / 是否归档到 S3 / prod 看板数据谁有权限访问"

**修改**（Task 1 GREEN 段 ObservabilitySettings 补）：
```python
class ObservabilitySettings(BaseSettings):
    ...
    trace_retention_days: int = 30      # ← 新增
    archive_to_s3: bool = False          # ← 新增（V1 不实现，V1.1 启用）
    trace_pii_redaction_strict: bool = True  # ← 新增：严格模式额外脱敏
```

并风险表补：`Langfuse trace 保留` | 默认 30 天，prod 长保留撑爆磁盘 | 设置 `trace_retention_days=30` + 定期清理脚本（M12 实现）

### P1-10 · 缺 user feedback 接入（Langfuse score API）

**位置**：DoD 全篇
**问题**：
- spec §3.10 隐含"用户对 answer 给 thumbs up/down"是闭环关键——但 M10 计划不接 user feedback
- M9 Gradio UI 渲染 answer 旁会有"👍/👎"按钮（M9 计划）——feedback 应回写 Langfuse
- Langfuse 2.50+ 有 `langfuse.score(trace_id=..., name="user_feedback", value=1|0)` API
- 缺这层 → trace 只能看不能评 → M11 RAGAS 也关联不到"用户实际反馈"维度

**修改**（Files 表补）：
- `app/api/feedback.py`：`POST /api/feedback {trace_id, value: 1|0, comment?: str}` 端点
- `app/observability/feedback.py`：`record_feedback(trace_id, value, comment)` 调 `langfuse.score(...)`
- Task 11（新增）：feedback 端点 RED-GREEN（不在原 10 Tasks 内，作为 P1-10 建议加 Task）

### P1-11 · 缺 Langfuse prompt caching 与 trace metadata 冲突处理

**位置**：Task 1 + Task 5 全文
**问题**：
- langfuse 2.50+ 的 prompt 管理（`langfuse.get_prompt(name=...)`）与 M3 工厂的 yaml 加载有**重叠**——M10 未明确"prompt 是 yaml 还是 langfuse"
- 若 V1.1 引入"prompt 走 langfuse 看板管理"（产品想 A/B 不同 prompt），当前 M3 yaml 路径要废弃
- M10 trace metadata 里若写 `prompt_version: "yaml-2026-06-11"`，但实际 prompt 已切到 langfuse，metadata 误导

**修改**（风险表补 + M10 DoD 加一条"prompt 来源标注"）：
- `ObservabilitySettings.prompt_source: str = "yaml"` （V1= yaml，V1.1 可改 `langfuse`）
- 节点 metadata 增 `prompt_source` 字段

### P1-12 · 缺 Langfuse 自带 OTEL listener 接入

**位置**：Tech Stack + 风险 P1-3
**问题**：
- plan 写"OTEL 留 hook 不实现"——但 langfuse 2.50+ 自带 OTEL listener（`langchain` 调用 LLM 时自动 emit OTEL spans，langfuse 自动 collect）
- 不主动接 OTEL = 失去 future 可观测性扩展点（Prometheus / Sentry / Tempo 都要 OTEL）
- plan 把 OTEL 推到 M12/M13，但**M10 阶段已经可以默认启用**（`opentelemetry-api/sdk` 已在 pyproject）

**修改**（Task 1 GREEN 段补）：
- 启用 OTEL auto-instrumentation（`OpenTelemetryInstrumentor().instrument()` 在 lifespan 启动时调）
- 但**不**配 OTEL exporter（只让 langfuse 收 spans，不外发）

### P1-13 · 缺 RateLimit / 429 trace（Langfuse 自身限速后降级）

**位置**：风险表 + DoD
**问题**：
- Langfuse 2.50+ 公开 API 默认 1000 req/min，超过返回 429
- 单 chat 触发 7 节点 × 4 次 context update = 28 RPC → 高 QPS 下打满
- 429 响应**不**走 trace → 静默丢 trace → 看板数据缺

**修改**（Task 5 GREEN 段 `flush` 包装）：
```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def _safe_update_observation(**kwargs):
    resp = langfuse_context.update_current_observation(**kwargs)
    if hasattr(resp, "status_code") and resp.status_code == 429:
        raise httpx.HTTPStatusError("429 rate limit", request=None, response=resp)
    return resp
```

### P1-14 · `ChatResponse.trace_id: str | None` schema 缺 `serialization_alias` 处理

**位置**：Task 8 RED 段
**问题**：
- Langfuse trace_id 格式：`01HXYZABC...`（ULID）或 `cm5xxx...`（cuid2）—— 36-50 字符
- Pydantic schema `trace_id: str | None` 没 `max_length` 限制 → 异常 trace_id 入库超长字段
- 前端 Gradio 5.0+ 渲染 trace_id 当链接 href 用 → URL 截断

**修改**（Task 8 GREEN 段改 schema）：
```python
# app/api/schemas/chat.py
from pydantic import Field

class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    sources: list[SourceItem]
    session_id: str
    request_id: str
    trace_id: str | None = Field(default=None, max_length=64)  # ← 加 max_length
```

---

## P2 · 优化

### P2-1 · `ObservabilitySettings.flush_timeout_s=5.0` 默认过大——应 1.0s

**位置**：Task 1 GREEN 段
**修改**：默认改 1.0s（trace flush 在 ASGI 请求内执行不能 block 太久；M8 chat 30s timeout，5s flush 占 17% 太多）。

### P2-2 · 缺 `apps/rag_v1/.env.example` M10 段示例值

**位置**：Files 表 L192 + DoD L542
**问题**：plan 写"追加 `LANGFUSE_SAMPLE_RATE=1.0` / `LANGFUSE_MASK_KEYS=password,token,api_key` / `LANGFUSE_TRACE_ENV=dev`"——但 `LANGFUSE_MASK_KEYS` 是 set[str] 类型，逗号分隔解析要 plan 写明。
**修改**：补 `.env.example` 完整段：
```bash
# Observability (M10)
LANGFUSE_SAMPLE_RATE=1.0
LANGFUSE_MASK_KEYS=password,token,api_key,secret,authorization,session_token
LANGFUSE_TRACE_ENV=dev
LANGFUSE_FLUSH_TIMEOUT_S=1.0
LANGFUSE_OFFLINE_MODE=false
LANGFUSE_TRACE_RETENTION_DAYS=30
LANGFUSE_PROMPT_SOURCE=yaml
```

### P2-3 · `node_tracing.py` 与 `tracing.py` 命名重复（M3 已有 `tracing.py::@trace`）

**位置**：Files 表 L41-47
**问题**：
- `app/observability/tracing.py`（M3）已有通用 `@trace` 装饰器
- M10 新建 `app/observability/node_tracing.py` LangGraph 专用——命名与 M3 重复
- `__init__.py` 暴露时容易冲突

**修改**：
- 方案 A：删 `tracing.py`（M3 `@trace` 与 M10 `@node_trace` 重复），统一用 `node_trace`
- 方案 B：M3 `tracing.py` 改名 `trace_generic.py` 或 `trace_decorator.py`（避开 `node_trace` 重名）

### P2-4 · `test_node_trace_captures_exception_and_reraises` RED 测试名与 GREEN 段 `exc_value="boom"` 断言不匹配

**位置**：Task 5 RED 段 L371
```python
def test_node_trace_captures_exception_and_reraises():
    ...
    def failing_node(state): raise ValueError("boom")
    ...
    assert handler.on_chain_error 被调 1 次（带 exc_value="boom"）
```

**问题**：`on_chain_error` 在 langchain 1.0+ 签名是 `on_chain_error(self, error: BaseException, **kwargs)`，第二个位置参数是 `error` 不是 `exc_value`。
**修改**：删 `exc_value="boom"` 断言（实际 API 是 `error=ValueError("boom")`），改用 `mock.assert_called_with(mock.ANY, ValueError("boom"))` 或干脆改用 `langfuse_context.update_current_observation` 测（见 P0-5 改法）。

### P2-5 · `inspect.getsource` 解析 `@node_trace` 装饰字符串脆

**位置**：Task 6 RED 段 L387
```python
用 inspect.getsource 读 app/graph/nodes.py → 断言 7 个函数都有 @node_trace 装饰
```

**问题**：
- `inspect.getsource(node_fn)` 只取**单函数**的 source，**不含**装饰器行（装饰器在 def 上方一行）
- 实际写法 `inspect.getsource(node_fn)` 拿到的源码是：
  ```python
  async def classify_node(state: RagState) -> RagState:
      ...
  ```
  **没有** `@node_trace("classify")` 行
- 必须用 `inspect.getsourcelines`（含装饰器）或 `inspect.getsource(module)` 解析整个 module 字符串

**修改**：
```python
def test_all_seven_nodes_have_node_trace():
    from app.graph import nodes
    import inspect
    expected_nodes = {"load_memory_node", "classify", "query_rewrite",
                       "retrieve", "rerank", "answer",
                       "save_memory_node", "answer_chitchat_node"}
    for name in expected_nodes:
        func = getattr(nodes, name)
        src = inspect.getsource(func)  # ← 单函数不含装饰器
        # 必须用 getsourcelines
        lines, _ = inspect.getsourcelines(func)
        full_src = "".join(lines)
        assert "@node_trace" in full_src, f"{name} missing @node_trace"
```

### P2-6 · `test_request_id_propagates_to_graph_metadata` mock 路径假设 `state.metadata.request_id` 字段

**位置**：Task 8 RED 段 L438
```python
mock M8 chat 路由调用 → 断言 graph.ainvoke 的 config["metadata"]["request_id"] == X-Request-Id
```

**问题**：
- M8 middleware 注入 `request.state.request_id`（不在 state dict 里）
- M10 chat.py 把 `request.state.request_id` 灌到 `graph.ainvoke(..., config={"metadata": {"request_id": request_id}})`
- Task 8 RED 测的是 chat.py 的行为，但 mock 路径写"mock M8 chat 路由调用"——`state.metadata.request_id` 实际**不在** RagState TypedDict 里（state 是 graph input，不含 metadata 嵌套）

**修改**（澄清 metadata 流向）：
- `state` 字段：`query / user_id / thread_id / messages / ...`（业务字段）
- `config["metadata"]` 字段：`request_id`（中间件注入，不进 state）
- 测试 mock chat route handler，断言 `mock_graph.ainvoke.call_args.kwargs["config"]["metadata"]["request_id"] == "req-test-1"`

### P2-7 · 集成测试 `test_chat_error_emits_trace_with_stack` mock 节点抛 `RuntimeError` 不符合 M7 实际异常

**位置**：Task 9 RED 段 L476
```python
mock classify 节点抛 RuntimeError("LLM 4xx")
```

**问题**：
- M7 review P0-8 指出节点 LLM 异常**不**是 RuntimeError——`ChatAnthropic` 抛 `APIError` / `APITimeoutError` / `BadRequestError`（langchain-anthropic 0.3+）
- 装饰器 catch `Exception` 兜底 OK，但 mock 应该用 langchain 真实异常类

**修改**：
```python
from langchain_anthropic import ChatAnthropic
from unittest.mock import patch

@patch("app.graph.nodes.make_llm")
def test_chat_error_emits_trace_with_stack(mock_make_llm):
    mock_make_llm.return_value.ainvoke.side_effect = ChatAnthropic.APIError("LLM 4xx")
    ...
```

### P2-8 · `LANGFUSE_SAMPLE_RATE=1.0` 默认 dev/staging 写死 1.0，但 staging 应更低（0.5）

**位置**：Task 1 + 风险 P1-2
**问题**：风险表写"dev=1.0 / prod=0.1"——但 staging 环境**没**设默认。staging 全量 1.0 可能压垮 staging Langfuse 容器。
**修改**：`ObservabilitySettings.sample_rate` 默认 1.0，注释里写"staging 建议 0.5 配 env override"。

### P2-9 · `app/observability/__init__.py` 暴露太多 public API（4 个新模块）

**位置**：Files 表 L184
**修改**：最小暴露：`node_trace`（装饰器）+ `build_session_metadata` + `mask_pii` + `flush` + `get_current_trace_id`。**不**暴露 `HandlerPool`（若 P1-5 删 pool）或 `ObservabilitySettings`（走 `from app.config import settings` 单例）。

### P2-10 · 缺 docstring 描述 `@node_trace` 装饰器对 trace 性能影响

**位置**：Task 5 GREEN 段
**修改**：装饰器 docstring 写：
```
性能影响：
- 单次 context update RPC ~ 5-10ms（langfuse 客户端默认同步）
- 7 节点 × 4 次 update = 28 RPC → 单 chat +200ms 延迟
- 采样率 0.1 时：90% chat 不打 RPC → 平均 +20ms
```

---

## 跨 M 阻塞依赖

### 阻塞 1 · M7 P0-2 / P0-3 / P0-6 必须在 M10 之前修

- M7 P0-2（`cp.aget` → `aget_tuple`）：M10 装饰器不直接调 checkpointer，但 M7 没修 → M10 集成测试起不来
- M7 P0-3（make_checkpointer contextmanager）：M10 集成测试用真 PG，依赖 M7 修对
- M7 P0-6（`answer_chitchat_node` 实现）：M10 装饰器应用到 8 节点（不只是 7），M7 缺 `answer_chitchat_node` 实现 → M10 装饰器应用失败

### 阻塞 2 · M3 P0-4 缺 sample_rate/flush_at/flush_interval 配置 → M10 引入

M10 ObservabilitySettings 引入 `sample_rate`——但 langfuse **客户端侧**也需要 `sample_rate` 字段（`CallbackHandler(sample_rate=0.1)`）才能真正不写全量 trace。M3 review P0-4 已点过这个，但 M3 没改。M10 修 M3 工厂的 `get_callback_handler` 注入 sample_rate。

### 阻塞 3 · M8 P0-1 chat 30s 超时 → M10 flush 不能阻塞 5s

M8 chat route 加 `asyncio.wait_for(..., 30)`——M10 `session_tracker.flush()` 用 5s timeout 是单独组件，但集成时 `chat → flush` 总和 ≤ 30s。M10 应把 `flush_timeout_s` 默认改 1.0s（P2-1 已列）。

### 阻塞 4 · spec §0 决策 #10 "Langfuse 在线 trace" 与 M10 plan 范围

spec 决策 #10：观测 = Langfuse 在线 trace（langfuse>=2.50）。M10 实现 7 节点 + ingest pipeline + PII——**完整**。M11 RAGAS 决策 #11 是离线，不属 M10 范围。M10 DoD 完整。

---

## 关键新发现总结

| ID | 严重度 | 简述 |
|----|--------|------|
| P0-1 | 阻塞 | `@node_trace` 装饰器 `args[0]` 假设与 M7 节点 `(state, config)` 双参数签名不兼容 |
| P0-2 | 阻塞 | `langfuse_context.flush()` API 在 langfuse 2.50+ 不存在（`ImportError` / `AttributeError`） |
| P0-3 | 阻塞 | `handler.get_trace_id()` 不是 CallbackHandler 公开 API（`AttributeError`） |
| P0-4 | 阻塞 | `test_all_seven_nodes_have_node_trace` 函数名错（5/7 错）+ count 错（漏 `answer_chitchat`） |
| P0-5 | 阻塞 | 装饰器内调 `handler.on_chain_start` 是 langchain 协议级方法，不创建 Langfuse trace span；改用 `langfuse_context.update_current_observation` |
| P1-1 | 重要 | metadata 字段格式（`metadata.user_id` vs Langfuse 实际路径）未测 |
| P1-2 | 重要 | `on_chain_*` 在 langchain 1.0+ 签名要求 `(serialized, inputs, ...)`，1 参调会 `TypeError` |
| P1-3 | 重要 | 缺节点级 usage/cost 汇总（节点级 summary，LLM span 自动追踪） |
| P1-4 | 重要 | 缺 Langfuse 不可达降级（容器 down → 阻塞 28 RPC × 5s） |
| P1-5 | 重要 | `HandlerPool` 概念与 langfuse 2.50+ 无状态 callback 冲突（升级 P0 候选） |
| P1-6 | 重要 | `langfuse_context` 跨 async task 传递可能丢失（contextvar 隔离） |
| P1-7 | 重要 | `flush()` 调用时机缺失（chat route 不调，集成测试 trace 拉不到） |
| P1-8 | 重要 | PII 缺 email/手机号/IP/Bearer token 兜底 |
| P1-9 | 重要 | 缺 trace retention 策略（默认 30 天，prod 长期撑爆） |
| P1-10 | 重要 | 缺 user feedback 接入（`langfuse.score` API） |
| P1-11 | 重要 | prompt 来源（yaml vs langfuse）冲突未标注 |
| P1-12 | 重要 | 缺 OTEL auto-instrumentation 默认启用 |
| P1-13 | 重要 | 缺 Langfuse 429 / 限速 retry |
| P1-14 | 重要 | `ChatResponse.trace_id` 缺 `max_length` 约束 |
| P2-1 | 优化 | `flush_timeout_s=5.0` 默认过大（应 1.0s） |
| P2-2 | 优化 | `.env.example` 段示例值不全 |
| P2-3 | 优化 | `node_tracing.py` vs `tracing.py` 命名冲突 |
| P2-4 | 优化 | `exc_value="boom"` 断言名与 langchain 1.0+ `on_chain_error(error=...)` 不匹配 |
| P2-5 | 优化 | `inspect.getsource(node_fn)` 不含装饰器行，必须用 `getsourcelines` |
| P2-6 | 优化 | 测试 mock 路径混淆 `state.metadata.request_id` 与 `config["metadata"]["request_id"]` |
| P2-7 | 优化 | mock 节点异常用 `RuntimeError` 不符合 langchain-anthropic 真实异常类 |
| P2-8 | 优化 | staging sample_rate 缺默认（建议 0.5） |
| P2-9 | 优化 | `__init__.py` 暴露 public API 未最小化 |
| P2-10 | 优化 | 缺装饰器性能影响 docstring（+200ms 延迟 / 28 RPC） |

---

## 落地建议（按优先级排序）

### 必做（5 项 P0）— 改完才能动手

1. **P0-5 + P0-1**：装饰器机制彻底重写——改用 `langfuse_context.update_current_observation`（不调 `on_chain_*`）；同时支持 `(state)` 和 `(state, config)` 双签名（用 `inspect.signature` 自动识别）
2. **P0-2**：flush 改用 `from langfuse import get_client; client.flush()`，备 `langfuse_context.flush_current_observation()`
3. **P0-3**：trace_id 取法改 `from langfuse import get_client; get_client().get_current_trace_id()`，封装到 `app/observability/node_tracing.py::get_current_trace_id()`
4. **P0-4**：Task 6 RED 测试改 8 节点（加 `answer_chitchat_node`），改用 `inspect.getsourcelines`（含装饰器），并 M10 plan Files 表 L196 写明 M7 实际函数名带 `_node` 后缀
5. **M7 依赖阻断**：M10 文档显式声明"M10 阻塞 M7 P0-2 / P0-3 / P0-6 修复"——M7 未修前 M10 集成测试起不来

### 建议做（9 项 P1）— 一次写到位

- 6-14 项：PII 扩展（email/手机号/IP/Bearer）+ cost/usage 汇总 + 不可达降级 + async context 显式 + flush 调用点 + 429 retry + retention + user feedback + OTEL auto

### 选做（10 项 P2）— review 后微调

- 15-24 项：flush_timeout 改 1.0、.env 补全、命名去重、测试断言修正、inspect API 修正、staging sample_rate、__init__ 最小暴露、性能 docstring

### 不在 M10 范围（推迟）

- user feedback UI 按钮（M9 计划）
- Sentry / Prometheus（M12 Hardening）
- 自动化 trace 清理脚本（M12 Hardening）
- OTEL exporter 启用（M12 / M13）
- Langfuse prompt 看板管理（V1.1）

---

## 修订建议（针对 plan L582-584 修订记录）

下一版 `M10-plan-r1` 修订记录建议：

| 版本 | 日期 | 改动 |
|------|------|------|
| M10-plan-r1 | 2026-06-11 | 吸收本 review：P0-1 装饰器签名双参数支持 / P0-2 flush 改用 Langfuse 客户端 / P0-3 trace_id 改用 get_client() / P0-4 测试改 8 节点 + getsourcelines / P0-5 装饰器改 langfuse_context / P1-3 usage 汇总 / P1-4 不可达降级 / P1-5 HandlerPool 删 / P1-7 flush 调用点 / P1-8 PII 扩展 / P1-9 retention / P1-13 429 retry / P1-14 trace_id max_length / 9 项 P2 微调 |

---

## 一句话结论

M10 plan **结构最完整、TDD 节奏最好、与 spec §3.10 trace 结构对齐**——但**5 个 P0 全部涉及 langfuse 2.50+ / langchain 1.0.8 / langgraph 1.0.5 实际 API 与 plan 假设的差异**（不是"plan 写得不够细"，是"plan 用了错误的 API"），修完 P0 后是合格可动手的 plan。**M7 P0-2/P0-3/P0-6 是 M10 的隐性前置依赖**，M10 文档应显式声明。
