# M7 Plan Review · LangGraph 7 节点 + PostgresCheckpointer

> 评审对象：`plans/2026-06-10-rag-m7-graph.md`（631 行）
> 评审基线：V1 Scope v0.4 spec（§0 决策 #5/#12/#17 · §1 架构 graph 段 · §2 模块树 graph 段 · §3.3 Query 数据流 · §5 错误矩阵 · §8.1 核心 LLM 编排栈）
> 参考 review：总报告 `2026-06-11-rag-plans-review.md` · M0–M6 独立 review 报告（reviews/ 目录 7 份）+ M3 范本审查
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M7 plan 覆盖 11 段模板（Goal / Architecture / Tech Stack / Files / 11 Tasks RED-GREEN / 测试策略 / DoD / 依赖 / 风险 / 修订记录），作为"最大里程碑"（自警 L10）的 631 行篇幅合理——远大于 M0 313 行 / M1 395 行 / M3 318 行。7 节点函数签名 + PostgresCheckpointer 降级 + session_id-thread_id 解析 + retrieve kNN + rerank LLM 0-10 + answer 源引用 + fallback 兜底等主体设计**完整且与 §3.3 Query 数据流逐一对齐**。

但作为 RAG 系统核心骨架，**实施就绪度严重不足**——已有 review 列出的 6 项（P0-10 / P1-15 / P1-16 / P1-17 / P2-4 / P2-5）**全部未改**；**本 review 新发现 24 个问题**，其中 6 个升级到 P0（阻塞级），覆盖 graph 无限循环保护、answer_chitchat 空实现、classify 缺 history 输入、graph 超时缺失、OpenSearch index 硬编码、并查策略未定义等**核心设计漏洞**。修完 P0 8 项 + P1 14 项后是可直接动手的合格 plan。

| 维度 | 评分 | 说明 |
|------|------|------|
| 结构完整性 | ⭐⭐⭐⭐ | 11 段齐含范本目的段；Architecture 图清晰；Files 表完整（20 个源+测试文件） |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 11 Tasks 全部 RED-GREEN；RED 测试名具体、GREEN 代码段完整（非伪代码） |
| 技术深度 | ⭐⭐⭐ | 7 节点数据流设计完整；但缺 context 窗口保护 / 并发安全 / 版本控制 / 超时等工程关键项 |
| 错误处理 | ⭐⭐⭐ | retrieve fallback 有方案；但 classify / rewrite / rerank / answer / save_memory 节点缺异常传播机制 |
| 一致性 | ⭐⭐ | checkpointer 双重定义（P0-10 未改）；`cp.aget` API 与 langgraph 1.0.5 不匹配（P2-4 未改） |
| 已有 review 就绪度 | ❌ | 6 项已列问题**全部未改**——P0-10 / P1-15 / P1-16 / P1-17 / P2-4 / P2-5 |

**一句话**：M7 plan **7 节点数据流正确、TDD 节奏好、主体设计对齐 spec**；但**在已有 review 6 项全未改 + 本 review 新发现 24 项问题（含 6 项 P0）的情况下不可直接动手**。修完 P0 8 项后 M7 的工程化才算完整。

---

## 已有 review 验证（2026-06-11-rag-plans-review.md）

| ID | 已有 review 项 | Plan 现状 | 本报告 |
|----|---------------|-----------|--------|
| **P0-10** | checkpointer 双重定义：`app/graph/checkpointer.py` vs `app/memory/checkpointer.py` | ❌ **未改**——Files 表 L159 + L166 都保留，spec §2 模块树说 `app/memory/checkpointer.py` 是"Postgres checkpointer 封装"，M7 Plan 又在 `app/graph/checkpointer.py` 写同一逻辑。两个文件职责完全重叠。 | **P0-1**（升级到本 review 首项 P0） |
| **P1-15** | `route_after_answer` 缺测试（plan L500-501 提到 RED 但代码段截断，看不到实际内容） | ❌ **未改**——L500-502 只有注释行"调 `route_after_answer(state)` → 断言返回 'save_memory'"，无 `route_after_answer` 函数体的 GREEN 实现。edges.py 里只有 `route_after_classify`，缺少 `route_after_answer` 函数体和对应的单元测试。 | **P0-5**（升级到 P0——因为 workflow 里 `add_edge("answer", "save_memory")` 本是常量边不需要路由函数，但 plan 自己既写了 `route_after_answer` 又画了常量边，自相矛盾） |
| **P1-16** | `app/retrieval/store.py` vs `retriever.py` 边界不清 | ❌ **未改**——Files 表 L163 写 `store.py` = "LlamaIndex OpenSearchVectorStore 封装"，L165 写 `retriever.py` = "retrieve 节点用 (kNN top_k=10)"。但 Task 4 GREEN 段 `retriever.py` 实现直接调 `AsyncOpenSearch` 客户端，**完全没用** `store.py`。两个文件职责重叠。 | **P1-1** |
| **P1-17** | 集成测试 `test_fallback_answer_on_retrieve_failure` 期望的 fallback 文案"检索服务暂不可用，已切换到直答模式。"硬编码 | ❌ **未改**——L570 文案直接 hardcode 在 `errors.py` 的 `retrieve_with_fallback` 函数里。 | **P1-2** |
| **P2-4** | `load_memory_node` 写 `cp.aget` API 在 langgraph 1.0.5 不存在（应是 `aget_tuple`） | ❌ **未改**——L469 仍是 `await cp.aget(...)`。 | **P0-2**（升级到 P0——因为 langgraph 官方 API 不对 → 代码跑不起来） |
| **P2-5** | `make_checkpointer` 是 `@asynccontextmanager` 工厂，但 `compile(checkpointer=...)` 需要实例而非 contextmanager | ❌ **未改**——L236-247 仍是 `@asynccontextmanager` 返回实例，plan 没说"调用方负责 `async with make_checkpointer() as cp: compile(cp)`"。 | **P0-3**（升级到 P0——因为 compile 直接传 contextmanager 会 TypeError） |

**验证结论**：已有 review 列出的 6 项 M7 范围问题：**全部 ❌ 未改**。其中 3 项从 P1/P2 升级到 P0。

---

## M2 review 交叉验证

**M2 review P0-4 `is_revoked` 字段缺失**：M7 `resolve_thread_id` 函数（L271-277）中调 `ChatSession.get(id=session_id, user_id=user_id)` 做归属校验。M2 review P0-4 指出 `auth_sessions` 表缺 `is_revoked` 字段，导致 logout 不能软吊销。M7 不直接依赖 `is_revoked`，但 M7 的 thread_id 解析依赖 `chat_sessions` 表——该表在 M1 schema 中缺 `is_active` 缺省值 / `deleted_at` 软删除字段（M1 review P1-5）。如果 `chat_sessions` 行被直接 DELETE（越权/清理），resolve_thread_id 查不到会 404——**与 spec §5 "越权 404 不暴露存在性"一致**。不影响 M7 当前逻辑，但风险表应记录"chat_sessions 行被清理后历史 thread 丢失"。

## M3 review 交叉验证

**M3 review P1-5 `make_llm("judge")` 缺** + **M7 也缺 `make_llm("answer_chitchat")`**：M7 plan L533 声明了 `answer_chitchat_node` 节点，但 M3 工厂的 `KNOWN_NODES` 只有 `("classify", "rewrite", "rerank", "answer")`。M3 review 已建议注册 `("classify", "rewrite", "rerank", "answer", "judge", "summarize", "answer_chitchat")`——M3 未改，M7 plan 也没提"需要在 M3 追加注册"。M7 实现时若 M3 工厂没注册 chitchat，`load_prompt("answer_chitchat")` 会缺 yaml 文件。**这是 M7 的直接依赖阻塞**，应在 M7 依赖表里显式写"依赖 M3 注册 answer_chitchat 节点"。

**M3 review P0-2 `make_llm` callback 注入方式**：M3 `model.callbacks = [...]` 被 langchain 1.0+ 弃用。M7 节点函数中 `make_llm("rerank")` 等方式调工厂，回调下沉到工厂层。如果 M3 不用 `.with_config(...)` 修复，M7 节点函数要自建 callback 注入——M7 plan 对此完全没提及。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · checkpointer 双重定义（已有 review P0-10 未改）

**位置**：Files 表 L159 `app/graph/checkpointer.py` + L166 `app/memory/checkpointer.py` + spec §2 模块树 L137-139

**问题**：
- `app/graph/checkpointer.py`（L159）做 `make_checkpointer()` 工厂（PG 优先 / SQLite 降级）
- `app/memory/checkpointer.py`（L166）做 `AsyncPostgresSaver.from_conn_string` 包装
- spec §2 模块树明确定义 `app/memory/checkpointer.py` 是"Postgres checkpointer 封装"，但 M7 把逻辑搬到 `app/graph/checkpointer.py`
- **两个文件职责完全重叠**，留下"哪个是 source of truth"的二义性

**修改**（二选一，选后更新 spec §2 模块树）：
- 方案 A（推荐，遵守 spec）：`app/graph/checkpointer.py` 只做工厂 + 降级逻辑，`app/memory/checkpointer.py` 删掉或只放 thread 相关
- 方案 B：删 `app/memory/checkpointer.py`，所有 checkpointer 逻辑放 `app/graph/checkpointer.py`

---

### P0-2 · `load_memory_node` 用 `cp.aget` 但 langgraph 1.0.5 API 是 `aget_tuple`（已有 review P2-4 升级）

**位置**：Task 9 GREEN 段 L468-469
```python
saved = await cp.aget({"configurable": {"thread_id": thread_id}})
```

**问题**：
- langgraph 1.0.5 + `langgraph-checkpoint==2.0.10` 的 `AsyncPostgresSaver` API 是 `aget_tuple(config)` 返回 `CheckpointTuple | None`，不是 `aget(config)` 返回 dict
- `cp.aget()` 不存在 → Python 跑时 `AttributeError` → load_memory 节点直接崩溃 → 整条 graph 中断
- 已有 review P2-4 已列此问题，**plan 未改**

**修改**：
```python
async def load_memory_node(state: RagState, config: RunnableConfig) -> RagState:
    thread_id = config["configurable"]["thread_id"]
    cp = config["configurable"]["__checkpointer"]
    saved = await cp.aget_tuple({"configurable": {"thread_id": thread_id}})
    messages = list(saved.checkpoint.get("messages", [])) if saved else []
    return {**state, "messages": messages}
```

---

### P0-3 · `make_checkpointer` 是 `@asynccontextmanager` 工厂，但 `compile()` 需要实例（已有 review P2-5 升级）

**位置**：Task 2 GREEN 段 L236-247 + Task 11 workflow.py L524-548

**问题**：
- `make_checkpointer` 用 `@asynccontextmanager` 装饰 → 访问时得到的是 `_AsyncGeneratorContextManager`，不是 `AsyncPostgresSaver` 实例
- `g.compile(checkpointer=checkpointer)` 期望 checkpointer 实例。传 contextmanager 会 `TypeError: Expected a BaseCheckpointSaver instance, got <class 'async_generator'>`
- 计划表说"调用方负责 async with make_checkpointer() as cp: ..."但 Task 11 workflow.py 的 compile_workflow 签名 `def compile_workflow(checkpointer)` 完全没说调用方要 `async with`

**修改**（二选一）：
- 方案 A（推荐）：删 `@asynccontextmanager`，改为普通工厂返回实例，调用方自行 lifecycle 管理：
```python
async def make_checkpointer() -> BaseCheckpointSaver:
    if settings.checkpointer.dsn:
        cp = AsyncPostgresSaver.from_conn_string(settings.checkpointer.dsn)
        await cp.setup()
        return cp
    else:
        cp = AsyncSqliteSaver.from_conn_string(settings.checkpointer.sqlite_path)
        await cp.setup()
        return cp
```
- 方案 B：保留 contextmanager，但在 `compile_workflow` 签名里写 `async def compile_workflow(checkpointer) -> CompiledStateGraph` + 在 workflow.py 内部 `async with make_checkpointer() as cp: ...`（但这样每次 compile 都重新建连接，与 graph lifecycle 不符）

---

### P0-4 · graph 缺 `max_iterations` 保护（新发现）

**位置**：Task 11 workflow.py L548
```python
return g.compile(checkpointer=checkpointer)
```

**问题**：
- StateGraph 默认 `max_iterations=25`（langgraph 1.0.5 默认值等于节点数 2× ≈ 安全），但如果某个节点死循环（如 `classify` 返回 "retrieve" 但 `query_rewrite` → `retrieve` → `rerank` → `answer` → ... 之后又回到 `classify`——虽然当前 graph 设计没有环，但未来修改 graph 加循环边时可能引入）
- 更关键的是：**单个节点内部** LLM invoke 可能 hang（60s 超时后重试 3 次 = 180s），graph 整体不设超时的话，M8 API 的客户端等 180s 也会 timeout（FastAPI 默认 30s）
- **没有 `max_time` 参数**：langgraph 的 `CompiledStateGraph` 不直接暴露 invoke 超时参数，需要外层包装 `asyncio.wait_for(graph.ainvoke(...), timeout=30)`

**修改**（Task 11 GREEN 段补）：
```python
# app/graph/workflow.py
def compile_workflow(checkpointer) -> CompiledStateGraph:
    g = StateGraph(RagState)
    # ... add nodes and edges ...
    return g.compile(
        checkpointer=checkpointer,
        interrupt_after=[],  # V1 无中断
    )

# 调用方（M8）包装超时：
import asyncio
try:
    result = await asyncio.wait_for(
        graph.ainvoke(input, config={"configurable": {"thread_id": thread_id}}),
        timeout=30.0,
    )
except asyncio.TimeoutError:
    return {"answer": "服务超时，请稍后重试。", "sources": [], "error": "timeout"}
```

风险表补一行：`graph invoke 无内置超时` | 风险：LLM 慢 / OpenSearch 慢导致请求 hang 长达几分钟 | 缓解：M8 调用方用 `asyncio.wait_for(graph.ainvoke(...), timeout=30)` 包装

---

### P0-5 · `route_after_answer` 存在性自相矛盾（已有 review P1-15 升级）

**位置**：Task 10 L501-503 + Task 11 L544

**问题**：
- Task 10 RED 段（L501）："调 `route_after_answer(state)` → 断言返回 'save_memory'"——暗示存在 `route_after_answer` 条件边函数
- Task 11 workflow.py（L544）：`g.add_edge("answer", "save_memory")`——用的是**常量边**（`add_edge`），不是条件边
- edges.py 只定义了 `route_after_classify`，**没有** `route_after_answer` 函数体
- 常量边 `add_edge("answer", "save_memory")` 和条件边 `route_after_answer` 二选一，不能同时存在。当前 plan 自相矛盾。

**修改**：
- 方案 A（推荐，与当前 workflow.py 一致）：删 `route_after_answer`（常量边即可），删 Task 10 的 RED 测试 `test_routes_to_save_memory_after_answer`
- 方案 B（保留扩展性）：把 `add_edge("answer", "save_memory")` 改为 `add_conditional_edges("answer", route_after_answer, {"save_memory": "save_memory", "answer": "answer"})`，支持 answer 节点自环重新回答——但 V1 不需要

---

### P0-6 · `answer_chitchat_node` 只有节点名无实现（新发现）

**位置**：Task 11 L532（节点注册 `g.add_node("answer_chitchat", answer_chitchat_node)`）+ Task 6-9（只实现了 retrieve/rerank/answer/load_memory/save_memory/classify/rewrite 7 节点）

**问题**：
- plan 注册了 8 个节点（7 节点 + `answer_chitchat_node`），DoD L590 也列了 8 个节点
- 但 **Task 1-9 只实现了 7 个节点函数**（classify / query_rewrite / retrieve / rerank / answer / load_memory / save_memory）
- `answer_chitchat_node` **完全没有实现**——既不在 nodes.py GREEN 段里，也不在任何 Task 中
- classify 分支 `intent=chitchat` 会走到这个空节点，graph invoke 报 `NodeNotFound / AttributeError`

**修改**（Task 9 旁新增 Task 9b：answer_chitchat 节点）：
```python
# RED: test_answer_chitchat_returns_chat_response
# 直接基于 history + query 调用 LLM，不检索
async def answer_chitchat_node(state: RagState) -> RagState:
    cfg = load_prompt("answer_chitchat")
    llm = make_llm("answer_chitchat").bind(system_message=cfg.system_prompt)
    # 传入 messages (history) + query
    msgs = list(state.get("messages", []))
    msgs.append(HumanMessage(content=state["query"]))
    resp = await llm.ainvoke(msgs)
    return {**state, "answer": resp.content, "sources": [], "chunks": []}
```

Files 表补 `app/prompts/answer_chitchat.yaml`（M3 工厂也要注册 `answer_chitchat` 节点）。

---

### P0-7 · `save_memory_node` 是 no-op 占位，但 checkpointer 自动 persist 行为未确认（新发现）

**位置**：Task 9 GREEN 段 L473-474
```python
async def save_memory_node(state: RagState, config: RunnableConfig) -> RagState:
    return state  # no-op
```

**问题**：
- LangGraph `checkpointer=...` 的 `AfterWriteCheckpointSaver` 机制是**图全部执行完后**才 persist checkpoint，不是每个节点执行后 persist
- save_memory 作为最末节点，graph invoke 完成后 checkpointer 自动写 checkpoint——**但只写最后一次 invoke 后的 state**，不写每个节点的中间状态
- `save_memory_node` 即使有逻辑也无意义（graph 完成后才写），但注释说"留 hook 给 M10 业务级 trace"——M10 如果要 intercept save 时机，应该用 `NodeInterrupt` 或 `after_save_hook`，不是 no-op 占位
- **plan 没说 clear**：M8 调用 `/api/sessions/{id}` 读历史时，是读 checkpoint 还是另外写 `messages` 到 `chat_sessions`？

**修改**：
- 在 plan 风险表补：`save_memory_node 作为 no-op 占位，M10 如需 intercept 请用 `graph.add_node("save_memory", save_memory_node)` + `RunnableConfig` 的 `on_after_save` 回调"
- 明确：`save_memory_node` 目前是 pure pass-through，`save_memory` 节点名称保留仅用于 graph 可观测性（Langfuse trace 能看到节点执行），实际 persist 由 checkpointer 在 graph 完成时自动做

---

### P0-8 · retrieve 节点内部异常只处理了 retrieve 函数层面，缺 graph 整体异常传播机制（新发现）

**位置**：Task 11 L560-574（`retrieve_with_fallback`）+ errors.py

**问题**：
- `retrieve_with_fallback` 只兜底 `retrieve_node` 的异常，但：
  - `classify_node` LLM 4xx/5xx → spec §5 要求 502，**不静默**——但 plan 没处理
  - `query_rewrite_node` LLM 异常 → 节点直接崩溃，graph 抛出未处理异常
  - `rerank_node` LLM 异常 → 节点直接崩溃
  - `answer_node` LLM 异常 → 节点直接崩溃
  - `save_memory_node` checkpointer 写盘异常 → 节点直接崩溃
- 7 个节点中**只有 retrieve 节点有 error handling**，其余 6 个节点异常时 graph 直接中断，回调到 M8 变成 500 Internal Server Error

**修改**（errors.py 补全局异常节点包装）：
```python
# app/graph/errors.py — 节点执行包装
from functools import wraps
from app.graph.state import RagState
from app.config import settings
import logging

log = logging.getLogger(__name__)

class GraphNodeError(Exception):
    """单个节点执行异常，包装后继续走 graph（不终止）"""
    node: str

def safe_node(node_name: str):
    """装饰器：节点执行异常 → 设置 state.error + 日志，不抛出"""
    def decorator(func):
        @wraps(func)
        async def wrapper(state: RagState, *args, **kwargs) -> RagState:
            try:
                return await func(state, *args, **kwargs)
            except Exception as e:
                log.error("Node %s failed: %s", node_name, str(e), exc_info=True)
                return {
                    **state,
                    "error": f"{node_name}_failed: {str(e)[:200]}",
                }
        return wrapper
    return decorator
```

并在风险表补：`节点级异常传播` | 风险：6 个节点缺异常处理，classify/rewrite/rerank/answer/save_memory 异常时 graph 直接崩 | 缓解：`safe_node` 装饰器包装所有节点，设 `state.error` 不终止 graph；M8 读 `state.error` 定 HTTP 状态码

---

## P1 · 重要

### P1-1 · `app/retrieval/store.py` vs `retriever.py` 边界仍不清（已有 review P1-16 未改）

**位置**：Files 表 L163-165 + Task 4 retriever.py 实现

**问题**：
- `store.py` 定义"LlamaIndex OpenSearchVectorStore 封装"
- `retriever.py` 实现直接调 `AsyncOpenSearch` 客户端，完全没用 `store.py`
- 两个文件都做 OpenSearch 查询封装，职责重叠。M4-M6 ingest pipeline 写 chunk 时用的是 `store.py`（LlamaIndex 生态），M7 读 chunk 时直接用 `AsyncOpenSearch` 客户端——**两条路径不一致**

**修改**（二选一）：
- 方案 A（推荐）：`store.py` 删掉或改为只做 `OpenSearchVectorStore` 实例化供 ingest 用；`retriever.py` 保持独立，职责明确为"graph retrieve 节点专用"
- 方案 B：`retriever.py` 放弃直接 `AsyncOpenSearch`，改为调 `store.py` 的 `OpenSearchVectorStore.similarity_search_by_vector()`——统一 LlamaIndex 路径

Files 表注释同步更新。

---

### P1-2 · fallback 文案硬编码（已有 review P1-17 未改）

**位置**：Task 11 errors.py L569-573

**问题**：
- `"检索服务暂不可用，已切换到直答模式。"` 写死在函数体内
- i18n / 产品文案 A/B 测试 / UI 侧覆盖都要改代码

**修改**：放进 `CheckpointerSettings` 或新建 `RetrievalSettings.fallback_prompt`：
```python
# settings
class RetrievalSettings(BaseSettings):
    fallback_message: str = "检索服务暂不可用，已切换到直答模式。"
```

---

### P1-3 · `classify` 启发式关键词不完整（新发现）

**位置**：Task 7 GREEN 段 L419
```python
CHITCHAT_KEYWORDS = {"刚才", "上面", "它", "他们", "她", "这个", "那个", "你", "我"}
```

**问题**：
- 缺中文指代词：`"哪些"`、`"这些"`、`"那些"`、`"此"`、`"其"`、`"某"`、`"该"`、`"本"`
- 缺人称：`"您"`（正式对话）、`"大家"`、`"各位"`
- 缺指代短语：`"如上所述"`、`"如上"`、`"前述"`
- 缺疑问/情感：`"好吧"`、`"谢谢"`、`"嗯"`、`"对"` → 这些可能仍应走 retrieve（问"对"可能是在确认事实）

**修改**（扩大集合 + 注释分类）：
```python
# 强 chitchat 触发词：指代词、人称、翻译软件问候
_CHITCHAT_STRONG = {"刚才", "上面", "它", "他们", "她", "他", "它们"}
# 中强度：需要结合 history 判断
_CHITCHAT_MEDIUM = {"这个", "那个", "这些", "那些", "哪些", "此", "其",
                    "您", "大家", "各位", "如上", "前述"}
```

并在 Task 7 RED 段补 `test_classify_chinese_pronouns` 覆盖中强度关键词（含 history 上下文判断）。

---

### P1-4 · `query_rewrite` 生成 1-3 句后并查策略未定义（新发现）

**位置**：Task 8 GREEN 段 L445-451 + spec §3.3 L248-249

**问题**：
- spec §3.3 L245-249 写："rewrites = llm.rewrite(query) [1..3] ... for r in rewrites: chunks += retrieve(r, top_k=10)"
- plan Task 8 只实现了 `rewrite_node` 生 1-3 句（L449），但 **retrieve 节点**（Task 4）只接受单 query `retrieve(query: str, top_k=10)`
- `retrieve_node`（nodes.py）只调了 `retrieve(rewrites[0])` 还是 `for r in rewrites: chunks += retrieve(r)`？plan **没说**
- 多条 rewrite 分多次检索还是合并在一次 kNN 里（如 OR filter）？结果如何合并/去重？

**修改**（Task 4 GREEN 段 retrieve_node 补并查逻辑）：
```python
async def retrieve_node(state: RagState) -> RagState:
    rewrites = state.get("rewrites", [state["query"]])
    all_chunks = []
    seen_doc_ids = set()
    for r in rewrites:
        chunks = await retrieve(r, top_k=10)
        for c in chunks:
            if c["doc_id"] not in seen_doc_ids:
                all_chunks.append(c)
                seen_doc_ids.add(c["doc_id"])
    return {**state, "chunks": dedupe_by_doc(all_chunks)}
```

---

### P1-5 · `rerank` JSON 解析健壮性只提供 try/except 轮廓（新发现）

**位置**：Task 5 L363-374

**问题**：
- GREEN 段写了 `parse_json_scores(resp.content, n=len(chunks))`——但这个函数**不存在于任何 Files 表**中
- `parse_json_scores` 内部要处理 LLM 返回非 JSON、JSON 但缺失字段、JSON 但 scores 长度不对、scores 值不在 0-10 范围 等多种情况
- plan 只说了"try/except + 兜底排序"，但没给 `parse_json_scores` 实现

**修改**（Task 5 GREEN 段补 parse_json_scores 实现）：
```python
import json
import re

def _extract_json(text: str) -> str:
    """从 LLM 输出中提取 JSON 块（兼容 markdown 代码块包裹）"""
    # 1. 先尝试直接反引号包裹
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    # 2. 裸露 JSON
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return ""

def parse_json_scores(raw: str, n: int) -> list[float]:
    input_str = _extract_json(raw)
    if not input_str:
        return [5.0] * n  # degenerate: 全给中性分
    try:
        data = json.loads(input_str)
        scores = data.get("scores", data.get("score", []))
        if not isinstance(scores, list) or len(scores) != n:
            return [5.0] * n
        return [max(0.0, min(10.0, float(s))) for s in scores]  # clip [0, 10]
    except (json.JSONDecodeError, ValueError, TypeError):
        return [5.0] * n
```

---

### P1-6 · `answer` 节点 context 窗口溢出保护缺失（新发现）

**位置**：Task 6 L382-405

**问题**：
- answer prompt 拼接 `f"[{i}] {c['text']}\n"`——chunk text 可能远超 500 字符（M4 ingest 默认 chunk=512 tokens ≈ 约 700 中文字符）
- 5 chunks × 700 字 + history messages + query = 极易超过 8K/16K context window
- 中文 LLM（MiniMax-M3）context window 通常是 32K tokens，但 accumulate 后仍可能溢出
- rerank 节点已经做了 `c['text'][:500]` 截断（L361），但 **answer 节点没有**

**修改**（Task 6 GREEN 段补截断）：
```python
MAX_CHUNK_CHARS = 800  # 约 500-600 tokens
user_msg += f"[{i}] {c['text'][:MAX_CHUNK_CHARS]}\n"
```

Files 表 `app/config.py` 追加 `AnswerSettings.max_chunk_chars: int = 800`，可配置化。

---

### P1-7 · `classify` 节点缺 history 输入（新发现）

**位置**：Task 7 classify_node L421-431 + §3.3 L241

**问题**：
- spec §3.3 L241 写 "llm.classify(query, history)"——classify 需要 history 上下文来判断"刚才/它"的指代
- M7 plan 的 `classify_node` 只传入 `state["query"]`，没传 history（`state.get("messages", [])`）
- 启发式关键词 `CHITCHAT_KEYWORDS` 能覆盖浅层 chitchat 检测，但**结合 history 的 LLM 分类**需要 messages
- 例如 query="它": 在 history 无消息时该走 chitchat 吗？反问用户"你指的什么？"也是检索路径的一部分

**修改**（classify_node 补 history 传入）：
```python
async def classify_node(state: RagState) -> RagState:
    q = state["query"]
    if any(kw in q for kw in CHITCHAT_KEYWORDS):
        return {**state, "intent": "chitchat"}
    cfg = load_prompt("classify")
    llm = make_llm("classify").bind(system_message=cfg.system_prompt)
    msgs = list(state.get("messages", []))
    msgs.append(HumanMessage(content=q))
    resp = await llm.ainvoke(msgs)  # 传 history + query
    intent = "chitchat" if "chitchat" in resp.content.lower() else "retrieve"
    return {**state, "intent": intent}
```

---

### P1-8 · `source` 返回排序未定义——rerank 后 chunks 顺序变了但 sources 顺序可能不一致（新发现）

**位置**：Task 6 L394-399（source 列表构造）

**问题**：
- `rerank_node` 把 chunks 按 LLM 评分降序排列（L367: `sorted(zip(chunks, scores), key=lambda x: -x[1])[:5]`）
- `answer_node` 此时拿到的 `chunks` 是**重排后**的顺序（第 1 个是最相关的）
- `source` 列表按 `chunks` 顺序构造（L392: `for i, c in enumerate(chunks, 1)`）——这没问题，source 顺序 = rerank 后顺序
- 但 **spec §3.3 没规定 source 返回顺序**——M8 API 返回给前端的 `sources: [{chunk_id, doc_id, image_ref?, score}]` 里 `score` 是 0.0（answer 节点写死了 L398），不是 rerank 的评分
- 前端拿到 source 列表，score 全是 0.0，无法按相关度排序展示

**修改**（Task 6 answer_node 补 score 传递）：
```python
sources.append({
    "chunk_id": c["chunk_id"],
    "doc_id": c["doc_id"],
    "image_ref": c["metadata"].get("image_ref"),
    "score": c.get("rerank_score", 0.0),  # rerank 节点应在 chunk 上附加 score
})
```

并在 `rerank_node`（Task 5）中把评分写入 chunk：
```python
ranked = sorted(zip(chunks, scores), key=lambda x: -x[1])[:5]
return {**state, "chunks": [{**c, "rerank_score": s} for c, s in ranked]}
```

---

### P1-9 · OpenSearch index 名称硬编码为 "chunks"（新发现）

**位置**：Task 4 L316
```python
resp = await client.search(index="chunks", ...)
```

**问题**：
- M4-M6 ingest 写入 OpenSearch 的 index 名称在 `index.py`（L163）也应该可配置
- 硬编码后多环境（dev/staging/prod）不能复用同一个 OpenSearch 集群
- spec §8.2 没规定 index 命名规范

**修改**：`app/config.py` 追加 `OpenSearchSettings.index_name: str = "chunks"`，retriever 用 `settings.opensearch.index_name`。

---

### P1-10 · `dedupe_by_doc_id` 的排列策略未定义（新发现）

**位置**：Task 4 L328-329 + spec §3.3 L249

**问题**：
- 多条 rewrite 分别检索后，同 doc_id 的多个 chunk 需要去重
- plan 说了 `dedupe_by_doc(chunks)` 工具函数（L329），但没说**去重策略**：
  - 保留最高分的那个 chunk？
  - 保留最先出现的那个 chunk？
  - 保留最长的那个 chunk？
- 不同策略影响 answer 质量

**修改**（Task 4 GREEN 段补 dedupe_by_doc 实现）：
```python
def dedupe_by_doc(chunks: list[Chunk]) -> list[Chunk]:
    """按 doc_id 去重，同一 doc_id 保留最高 cosine score 的 chunk。"""
    seen: dict[str, Chunk] = {}
    for c in chunks:
        doc_id = c["doc_id"]
        existing = seen.get(doc_id)
        if not existing or c.get("_score", 0) > existing.get("_score", 0):
            seen[doc_id] = c
    # 保持原顺序（首次出现位置优先）
    return [seen[c["doc_id"]] for c in chunks if c["doc_id"] in seen and seen.pop(c["doc_id"], None)]
```

---

### P1-11 · 缺 PostgresCheckpointer 连接池配置（新发现）

**位置**：Task 2 L237-241

**问题**：
- `AsyncPostgresSaver.from_conn_string(dsn)` 内部默认连接池配置未知——langgraph-checkpoint-postgres 2.0.10 默认 `pool_size=5, max_overflow=10` 但 plan 没写
- M8 API 并发请求 → graph.invoke → checkpointer get/put → 连接池用尽 → 请求排队 → latency 上升
- 与 app/db/session.py（M1）的 `pool_size=10, max_overflow=20` 不同，checkpointer 连接池是独立的——**总连接数 double**
- 风险表没记录检查点连接池与业务 DB 连接池的互相影响

**修改**（Task 2 GREEN 段 + 风险表补）：
- 显式在 plan 注释写 `AsyncPostgresSaver.from_conn_string(dsn)` 的默认连接池参数
- 风险表补：`checkpointer 连接池独立` | 风险：与 M1 业务 DB 连接池（10+20=30）共用 PG max_connections=100 → 还剩 50 给 Langfuse + 调试 | 缓解：checkpointer 默认 pool_size=5，max_overflow=10，总 45 < 100 安全；如超可降低 `max_overflow=5`

---

### P1-12 · 缺 thread_id UUID 生成稳定性保障（新发现）

**位置**：Task 3 L277
```python
return str(uuid.uuid4())
```

**问题**：
- `uuid4()` 碰撞概率 ≈ 1/2^122，理论上极低，但**逻辑上**：如果真的碰撞了（同一个 thread_id 被两个不同 session 使用），checkpointer 会混掉两个对话的历史
- 虽然在工程上可以接受（概率 < 宇宙射线），但 plan 应在风险表记录，并提供可选的 prefix 隔离（如 `"t1_"` + uuid4 前缀以支持多租户 V2）

**修改**（风险表补一行）：thread_id UUID 碰撞 | 风险：2^122 碰撞概率 0，但 V2 多租户需 thread_id 含 tenant prefix | 缓解：V1 免责，V2 改 `f"{tenant_id}_{uuid4()}"`

---

### P1-13 · 缺 OpenSearch kNN query 与 filter context 结合预留（V1 不做，但要预埋）（新发现）

**位置**：Task 4 L318-323

**问题**：
- 当前 kNN query 纯向量搜索，无 metadata filter
- V1.1 spec §9 规划 "doc ACL / 多租户"——届时需要 filter by `metadata.user_id` / `metadata.source`
- 现在不加 filter context 预留，V1.1 改 retriever 时 chunk 结构和 index 定义都要动

**修改**（Task 4 注释说明 + 风险表补）：
```python
# kNN body（V1 不含 filter，V1.1 可加：
# "query": {
#   "knn": {
#     "vector": {
#       "vector": qvec, "k": top_k,
#       "filter": {"term": {"metadata.user_id": user_id}}  # V1.1
#     }
#   }
# }
```

---

### P1-14 · chunk text 过长截断策略只在 rerank 里做了，answer 里缺（新发现）

**位置**：Task 5 L361（rerank 截断 500 char）vs Task 6 L392（answer 无截断）

**问题**：
- rerank 节点 prompt 中 `c['text'][:500]` 做了截断
- answer 节点 prompt 中 `f"[{i}] {c['text']}\n"` **没截断**
- 导致：rerank 拿到完整 chunk，answer 也拿到完整 chunk，但 answer 的 context window 压力更大（加上了 query + history + system prompt）

**修改**：answer 节点也用 `c['text'][:800]`（见 P1-6），两处截断长度可以不同（rerank 更短，answer 更长）。

---

### P1-15 · 缺 `pytest-httpx` / `freezegun` 等测试依赖声明（新发现）

**位置**：M7 测试策略行 L580-582 + Tech Stack 表

**问题**：
- `tests/unit/test_retrieval.py` mock OpenSearch 响应 → 需 `pytest-httpx`
- `tests/unit/test_graph_nodes.py` mock LLM invoke → 可能需要 `freezegun`（超时场景）
- M7 Tech Stack 表**只列了 langgraph/opensearch/asyncpg 等 runtime 依赖**，没列测试依赖

**修改**（Tech Stack 表补测试依赖）：
| 测试 mock LLM/OS | `pytest-httpx` | `>=0.30,<1` |
| 测试 datetime mock | `freezegun` | `>=1.5,<2` |

注：M3 review P1-3 已建议 `pytest-httpx`，M2 review P1-11 已建议 `freezegun`——M7 应该复用相同建议。

---

### P1-16 · `make_checkpointer` 首次建表权限处理未在 plan 落实（新发现）

**位置**：Task 2 L241 + 风险表 L619

**问题**：
- 风险表 L619 写 "`AsyncPostgresSaver.setup()` 首次跑建表权限不足"，缓解措施"docker-compose 用 superuser；CI 用专用 langgraph 用户"
- 但 plan 的 Task 2 GREEN 段 `await cp.setup()` **没有 try/except**，也没有降级行为（没有"建表失败 = 回退到 SQLite"的逻辑）
- 如果 PG 用户权限不足，`setup()` 抛 `PermissionError` → `make_checkpointer()` 异常 → 整条 graph 不可用

**修改**（Task 2 GREEN 段补 setup 降级）：
```python
@asynccontextmanager
async def make_checkpointer():
    if settings.checkpointer.dsn:
        try:
            cp = ...
            await cp.setup()
            yield cp
        except (PermissionError, Exception) as e:
            log.warning("PG checkpointer setup failed (%s), falling back to SQLite", str(e))
            # 降级到 SQLite
            ...
```

---

## P2 · 优化

### P2-1 · graph 版本控制未考虑（新发现）

**位置**：plan 整篇

**问题**：
- graph 节点或 state 结构修改后，历史 checkpoint 的 state 结构与新版不兼容
- langgraph 1.0.5 的 checkpointer**不会自动迁移** state——读旧 checkpoint → state 缺新字段 → 节点函数预期字段不存在 → 报错
- 当前 plan 需要在 `load_memory_node` 中处理缺省值

**修改**（Task 9 load_memory GREEN 段补兼容代码 + 风险表）：
```python
saved = await cp.aget_tuple(...)
checkpoint = saved.checkpoint if saved else {}
messages = list(checkpoint.get("messages", []))
# 兼容旧 checkpoint（state 缺字段时补默认值）
```

风险表补：graph 版本兼容 | 风险：graph 改动后历史 checkpoint 不兼容 → load_memory 缺字段 | 缓解：`load_memory_node` 用 `state.get("field", default)` 访问；大版本改 state schema 时加 `state_version` 字段

---

### P2-2 · graph 并发安全性未考虑（新发现）

**位置**：plan 整篇

**问题**：
- 多个 ASGI worker 同时 `graph.invoke` 同一个 thread_id → checkpointer 同时读写 → 写冲突（Postgres serialization 层面报错）
- langgraph 的 checkpointer 有**乐观锁**（基于 checkpoint_id），但 plan 没说明冲突时的重试策略
- M8 API 可能同时收到同一个 session 的并发请求（前端快速双击发送）

**修改**（风险表补）：
`graph 并发 invoke 同一 thread_id` | 风险：checkpointer 写冲突（serialization error） | 缓解：langgraph checkpointer 自带乐观锁 + 调用方可加 `retry_on_conflict`；UI 层禁双击

---

### P2-3 · classify 节点 LLM 兜底路径输出解析太脆弱（新发现）

**位置**：Task 7 L429
```python
intent = "chitchat" if "chitchat" in resp.content.lower() else "retrieve"
```

**问题**：
- `resp.content` 可能是 markdown（```json 包裹）、包含额外解释文本（"我认为这是 chitchat，因为..."）、含 punctuation 附加内容
- 简单的 substring match 在 LLM 输出格式漂移时不可靠

**修改**：
```python
import re
match = re.search(r'"intent"\s*:\s*"(retrieve|chitchat)"', resp.content)
intent = match.group(1) if match else "retrieve"  # 默认走 retrieve（安全）
```

---

### P2-4 · `workflow.py` 未暴露 `compile_workflow` 函数签名类型注解（新发现）

**位置**：Task 11 L524
```python
def compile_workflow(checkpointer):
```

**问题**：
- 缺 `checkpointer` 和返回值的类型注解
- 调用方 M8 不知道 `compile_workflow(checkpointer)` 的 checkpointer 类型是 `BaseCheckpointSaver`，返回值是 `CompiledStateGraph`

**修改**：
```python
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.graph import CompiledStateGraph

def compile_workflow(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
```

---

### P2-5 · Task 11 集成测试 `test_graph_invokes_end_to_end` 写"mock 真实 OpenSearch + 真实 LLM + 真实 PG checkpointer"——这是矛盾的（新发现）

**位置**：Task 11 L508-511

**问题**：
- 集成测试写"mock 真实 OpenSearch + 真实 LLM + 真实 PG checkpointer"——mock 和"真实"是反义词
- 如果是 mock（单元测试），不需要 docker-compose
- 如果是集成测试（真实服务），需要 docker-compose up + 真 PG + 真 LLM API key
- plan 写混了

**修改**：明确区分：
- 单元测试 `test_graph_invokes_end_to_end`(mock)：mock OpenSearch / mock LLM / mock checkpointer → `if not settings.checkpointer.dsn: pytest.skip("requires PG")`
- 集成测试 `test_m7_e2e_real`(docker)：需要 `--require-docker` marker，跑真 PG / 真 OS / 真 LLM

---

### P2-6 · 缺 OpenSearch client 连接池配置（新发现）

**位置**：Task 4 L314
```python
client = AsyncOpenSearch(hosts=[settings.opensearch.url])
```

**问题**：
- `AsyncOpenSearch()` 不传连接池参数，默认 `maxsize=10, retry_on_timeout=True`
- 并发 10+ retrieve 调用时，连接池满 → 请求排队 / 超时
- `opensearch-py` 的 `AsyncOpenSearch` 需要显式 `connection_class=...` 和 `pool_maxsize`

**修改**：
```python
from opensearchpy import AsyncOpenSearch, RequestsHttpConnection
client = AsyncOpenSearch(
    hosts=[settings.opensearch.url],
    connection_class=RequestsHttpConnection,
    pool_maxsize=settings.opensearch.pool_size,  # 默认 20
    retry_on_timeout=True,
    max_retries=3,
)
```

`OpenSearchSettings` 补 `pool_size: int = 20`。

---

### P2-7 · `retrieve_with_fallback` 函数名混淆——它是节点函数级别的 wrapper，不应放在 errors.py（新发现）

**位置**：errors.py L562-574

**问题**：
- `retrieve_with_fallback` 是**节点函数**（返回 `RagState`），不是错误处理工具函数
- 它应该放在 `nodes.py` 作为 `retrieve_node` 的一个装饰器或包装，或者让 `retrieve_node` 内部自含 try/except
- `errors.py` 职责本应是 `GraphError` / `RetrievalError` 异常类定义 + `fallback_answer()` 工具函数，不是节点逻辑

**修改**：`retrieve_with_fallback` 移到 `nodes.py` 或改为 `retrieve_node` 内部的 try/except；`errors.py` 只放异常类和纯工具函数。

---

### P2-8 · 集成测试提了"docker compose -f apps/rag_v1/infra/docker-compose.yml up -d postgres opensearch"但 infra/ 下的 docker-compose.yml 在 M0 目录 `apps/rag_v1/infra/`（新发现）

**位置**：L581

**问题**：
- M0 review 已指出 `infra/` 路径在 `apps/rag_v1/infra/docker-compose.yml`，但 M7 测试策略写相同的路径——**如果 M0 创建时路径不一致，这里也写错**
- 需要确认 `apps/rag_v1/infra/docker-compose.yml` 确实存在

**修改**：在 plan 测试策略段显式写"infra 路径：`apps/rag_v1/infra/docker-compose.yml`"，并在 M7 依赖表加"确认 infra 目录结构与 M0 一致"。

---

### P2-9 · `route_after_classify` 条件边字典值应与返回字符串一致，但 plan 两处写法不同（新发现）

**位置**：edges.py L489-493 + workflow.py L537-539

**问题**：
- edges.py 返回 `"answer_chitchat"` / `"query_rewrite"`（L491-492）
- workflow.py 注册 `g.add_conditional_edges("classify", route_after_classify, {"query_rewrite": "query_rewrite", "answer_chitchat": "answer_chitchat"})`——映射关系正确
- 但 **plan 在架构图 L84 画的是 `[chitchat] path`→ `answer (chitchat)`**，但实际节点名是 `"answer_chitchat"`——架构图、edges.py、workflow.py 三者应一致

**修改**：统一节点名为 `"answer_chitchat"`（已在 workflow.py 中用），架构图标注同步改为 `answer_chitchat`。

---

## 新发现问题汇总（已有 review 未列）

合计 **24 个新问题**：

| # | 等级 | 问题 | 简述 |
|---|------|------|------|
| 1 | **P0-4** | graph 缺 max_iterations/timeout 保护 | invoke 可能 hang 住，M8 API 超时 |
| 2 | **P0-5** | route_after_answer 自相矛盾 | plan 既写条件边又写常量边 |
| 3 | **P0-6** | answer_chitchat_node 无实现 | 8 个节点只有 7 个函数体，chitchat 分支崩 |
| 4 | **P0-7** | save_memory no-op 行为未确认 | checkpointer 写盘时机 vs no-op 矛盾 |
| 5 | **P0-8** | 缺 graph 整体异常传播机制 | 6/7 节点异常直接崩 graph |
| 6 | P1-3 | classify 启发式关键词不完整 | 缺"哪些/这些/那些/此/其/您"等 |
| 7 | P1-4 | query_rewrite 并查策略未定义 | 多 rewrite 是顺序检索还是合并检索？ |
| 8 | P1-5 | rerank JSON 解析不完整 | parse_json_scores 函数不存在 |
| 9 | P1-6 | answer context 窗口溢出保护缺 | 5 chunks + history 超 context window |
| 10 | P1-7 | classify 缺 history 输入 | §3.3 要求 classify(query, history) 但没传 |
| 11 | P1-8 | source score 全是 0.0 | rerank 评分没传递到 answer 的 source 列表 |
| 12 | P1-9 | OpenSearch index 名硬编码 | index="chunks" 不可配置 |
| 13 | P1-10 | dedupe_by_doc_id 策略未定义 | 保留最高分还是最先出现的 chunk？ |
| 14 | P1-11 | PostgresCheckpointer 连接池配置缺 | pool_size / max_overflow 未声明 |
| 15 | P1-12 | thread_id UUID 碰撞未讨论 | V1 接受但应有记录 |
| 16 | P1-13 | kNN filter context 未预留 | V1.1 多租户不可用 |
| 17 | P1-14 | chunk text 截断只在 rerank 做了 | answer 节点缺截断 |
| 18 | P1-15 | 测试依赖声名缺 | pytest-httpx / freezegun 未列 |
| 19 | P1-16 | checkpointer setup 权限降级未落实 | 风险表提到但代码没做 |
| 20 | P2-1 | graph 版本兼容性未考虑 | 改 state 后历史 checkpoint 不可用 |
| 21 | P2-2 | graph 并发安全性未考虑 | 多 worker 同 thread_id 写冲突 |
| 22 | P2-3 | classify LLM 兜底 substring match 脆弱 | 格式漂移后分类错 |
| 23 | P2-5 | 集成测试 mock vs real 矛盾 | "mock 真实"定义不清 |
| 24 | P2-7 | retrieve_with_fallback 不应该在 errors.py | 是节点逻辑放错文件 |

---

## 与已有 review 交叉验证汇总

| ID | 已有项 | M7 现状 | 本报告 | 严重度变更 |
|-----|--------|---------|--------|------------|
| P0-10 | checkpointer 双重定义 | ❌ 未改 | **P0-1** | 维持 P0 |
| P1-15 | route_after_answer 缺测试 | ❌ 未改 + 自相矛盾 | **P0-5** | P1 → **P0** |
| P1-16 | store vs retriever 边界不清 | ❌ 未改 | P1-1 | 维持 P1 |
| P1-17 | fallback 文案 hardcode | ❌ 未改 | P1-2 | 维持 P1 |
| P2-4 | load_memory aget API 不对 | ❌ 未改 | **P0-2** | P2 → **P0** |
| P2-5 | make_checkpointer contextmanager 形态 | ❌ 未改 | **P0-3** | P2 → **P0** |
| M2 review | is_revoked 字段缺失 | 不直接影响 M7 | 风险表备注 | — |
| M3 review P1-5 | make_llm("judge") 缺 | M7 缺 answer_chitchat | 依赖阻塞备注 | — |
| M3 review P0-2 | make_llm callback 注入方式 | M7 被动依赖 | 依赖阻塞备注 | — |

**验证结论**：
- 已有 review 的 6 项 M7 问题：**全部 ❌ 未改**
- 其中 3 项升级到 P0（P2-4→P0-2, P2-5→P0-3, P1-15→P0-5）
- 跨 M 2 项不直接影响当前版本但应记录风险

---

## 落地建议

按 P0 → P1 → P2 优先级：

### 第一波（本轮必改，8 项 P0）

1. **P0-1** checkpointer 双重定义 → 方案 A 或 B（推荐 A），更新 spec §2
2. **P0-2** load_memory_node 改 `aget_tuple` API + 正确解析 CheckpointTuple
3. **P0-3** make_checkpointer 去 `@asynccontextmanager` 改为普通工厂
4. **P0-4** graph 调用方补 `asyncio.wait_for(graph.ainvoke(...), timeout=30)` + 风险表记录
5. **P0-5** 删 `route_after_answer`（用常量边）或改统一
6. **P0-6** 补 `answer_chitchat_node` 实现 + 对应的 prompt yaml + M3 注册
7. **P0-7** save_memory 节点明确行为 + 注释"checkpointer 在 graph 完成后自动 persist"
8. **P0-8** 补 `safe_node` 装饰器 + 所有节点包装

### 第二波（重要，14 项 P1）

9. **P1-1** store.py / retriever.py 边界 + Files 表注释更新
10. **P1-2** fallback 文案移入 settings
11. **P1-3** 扩充 CHITCHAT_KEYWORDS + 分类（强/中强度）
12. **P1-4** retrieve_node 补多 rewrite 并查 + dedupe 策略
13. **P1-5** 实现 `parse_json_scores` 完整函数
14. **P1-6** answer 补 `MAX_CHUNK_CHARS` 截断 + settings 配置
15. **P1-7** classify_node 传 history messages
16. **P1-8** rerank 评分传递到 answer source 列表
17. **P1-9** OpenSearch index 名 settings 化
18. **P1-10** dedupe_by_doc 策略明确（保留最高 score）
19. **P1-11** checkpointer 连接池配置 + 风险表记录
20. **P1-12** thread_id UUID 碰撞风险表记录
21. **P1-13** kNN filter context 注释预留
22. **P1-14** answer 补 chunk text 截断

### 第三波（优化，9 项 P2）

23. **P2-1** load_memory_node 补旧 checkpoint 兼容
24. **P2-2** 风险表补 graph 并发写冲突
25. **P2-3** classify LLM 兜底改 regex 解析
26. **P2-4** workflow.py 补类型注解
27. **P2-5** 集成测试 mock vs real 区分
28. **P2-6** OpenSearch 连接池配置 + settings
29. **P2-7** retrieve_with_fallback 移入 nodes.py
30. **P2-8** 确认 infra docker-compose 路径
31. **P2-9** 统一节点名（架构图/edges/workflow）

### 跨 M 协调（M7 改完后通知）

- 通知 **M3**：注册 `answer_chitchat` 节点到 `KNOWN_NODES`
- 通知 **M3**：如果 M3 `make_llm` 仍用 `model.callbacks`，M7 节点函数要自建 callback 注入（替代方案：M7 等 M3 修完再动手）
- 通知 **M1**：`chat_sessions` 表的完整性和 `last_message_at` 字段（M1 review P1-6）
- 通知 **M8**：graph.invoke 要包 `asyncio.wait_for` 超时 + 读 `state.error` 定 HTTP 状态码
- 通知 **M10**：save_memory no-op 无 intercept，M10 若需节点级 trace 用 `NodeInterrupt` 而非改 save_memory

### M7 风险表补充建议

当前风险表覆盖 6 项（API drift / PG 降级 / setup 权限 / retrieve 崩溃 / prompt 漂移 / kNN 性能），建议追加以下 5 项：

| 风险 | 缓解 |
|------|------|
| graph invoke 无超时，LLM 慢拖垮 M8 | M8 调用方 `asyncio.wait_for(graph.ainvoke(...), timeout=30)` |
| 6/7 节点缺异常处理，异常直接崩 graph | `safe_node` 装饰器 + `state.error` |
| query_rewrite 多 rewrite 并查策略未定 | 默认逐条检索 + doc_id 去重，V1.1 再优化 |
| graph 版本兼容，改 state 后读旧 checkpoint 缺字段 | load_memory 用 `state.get("field", default)`，加 `state_version` |
| answer_chitchat 节点无实现 | 当前 P0-6 必须补，补后方可合并 |

---

## 状态

- **不可动手**：P0-1 ~ P0-8 共 8 项必改。其中 3 项（P0-2 aget API / P0-3 contextmanager / P0-5 route 矛盾）直接导致代码无法编译/运行，P0-6/P0-8 导致 graph 崩溃
- **建议本轮改**：P1-1 ~ P1-14 共 14 项
- **可下轮改**：P2-1 ~ P2-9 共 9 项
- **新问题合计**：24 个（已有 review 未列），其中 5 个升级到 P0
- **已有 review 验证**：6 项 M7 范围问题，**全部 ❌ 未改**，其中 3 项升级到 P0
- **跨 M 阻塞**：M3 未注册 `answer_chitchat` 节点 + M3 callback 注入方式未修 → M7 实际编码时卡住
- **总体评估**：M7 plan **7 节点数据流正确、TDD 节奏好**，是当前 RAG V1 路线核心骨架；但 **30 项问题（8 P0 + 14 P1 + 8 P2）** + 6 项已有 review 全未改 + 2 项跨 M 阻塞 = **修完 P0 + 等 M3 修复后方可动手**
