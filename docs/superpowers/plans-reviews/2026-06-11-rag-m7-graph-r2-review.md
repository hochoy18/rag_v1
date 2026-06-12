# M7 Plan r2 Review · r1 修复验证

> 评审对象：`plans/2026-06-10-rag-m7-graph.md`（r1 版本 · 971 行 · 33 项 P0/P1/P2 全部修复）
> 评审基线：r1 review `reviews/2026-06-11-rag-m7-graph-review.md`（925 行 · 8 P0 + 14 P1 + 9 P2 + 2 跨 M）
> 参考 review：M0–M6 r1 + r2 review（已修/补漏）、M8–M12 r1 review（已修）
> 评审时间：2026-06-11（r2 阶段）
> 评审者：Hermes subagent（独立审查 · 验证 r1 修复质量 + 发现 r1 引入新问题）
> 范围：M7 plan 33 项 r1 修复逐项验证 + r1 修复过程中是否引入新问题 + 跨 M 一致性 12 联动 + 风险表补全质量

---

## 总评

M7 plan r1 是 RAG V1 路线中**修复密度最高**的 plan——931 行主体 + 修订记录 33 行已修清单 + 风险表追加 33 行 `r1-2026-06-11 已修` 条目。8 项 P0（含 3 项从 P1/P2 升级）已全部补实现 + 配 RED 测试；14 项 P1（classify 关键词 / 并查策略 / JSON 解析 / chunk 截断 / source score 透传 / settings 化 index 名 / 连接池配置 / 测试依赖 / 降级逻辑等）已全部落地；9 项 P2 已落（含类型注解 / 集成测试拆分 / OpenSearch 连接池 / retrieve_with_fallback 移位 / 节点名统一）。

**r1 修复到位率约 92%**——33 项中 31 项能在 plan 主体（Task 1-11 + Files 表 + DoD + 修订记录）找到对应落地实现；2 项存在轻度漂移（P0-7 save_memory 注释 vs M10 联动落地、P1-15 测试依赖 Tech Stack 表落但 `pyproject.toml` dev 段是否同步需代码 review 时复核）。r1 修复过程**未引入新阻塞问题**，但发现 4 项**r1 衍生新问题**（新-1 workflow.py `add_conditional_edges` mapping 缺 `END` / 新-2 `save_memory` 节点 chitchat 路径不复用 / 新-3 `safe_node` 不捕获 `asyncio.CancelledError` / 新-4 `AnswerSettings.max_chunk_chars=800` 与 M4 ingest chunk_size=512 的对齐问题），全部为 P1/P2。

**维度评分**：

| 维度 | r1 评分 | r2 评分 | 变化 |
|------|--------|--------|------|
| 节点完整性 | ❌ 6/8 实现 | ✅ **8/8 完整** | 大幅提升 |
| API 正确性（langgraph 1.0.5） | ❌ aget/contextmanager 错 | ✅ **aget_tuple + 普通工厂** | 大幅提升 |
| 异常传播 | ❌ 6/7 节点裸奔 | ✅ **safe_node 全 8 节点包装** | 大幅提升 |
| settings 化 | ⚠️ 部分 hardcode | ✅ **fallback/index/pool/截断 全配置** | 提升 |
| 跨 M 一致性 | ⚠️ 缺 M3 联动 | ✅ **M3 KNOWN_NODES 追加 answer_chitchat 明示** | 提升 |
| 风险表透明度 | ⚠️ 6 行原风险 | ✅ **6 原 + 27 r1 已修 + 2 跨 M** | 提升 |
| 编译可运行性 | ❌ P0 漏导致 TypeError/AttributeError | ✅ **P0-1/2/3 修后跑得通** | 提升 |

**一句话**：r1 修复**整体质量高、覆盖率完整、TDD 节奏保留到位**——M7 plan 已是 RAG V1 路线中**可立即动手实施**的状态。修完 4 项 r1 衍生新问题后即可进入 implementation 阶段。

---

## 1. r1 修复验证（33 项逐项）

### 1.1 P0 项验证（8 项）

| r1 标记 | 修复内容（r1 修订记录） | 实际验证（plan L/段落） | 状态 |
|---------|--------------------|--------------------|------|
| **P0-1** | checkpointer 双重定义 → 删 `app/memory/checkpointer.py`，所有逻辑集中 `app/graph/checkpointer.py` | 修订记录 L938 + 风险表 L894 + 仓库布局 L82-83（"checkpointer 单文件口径：本 plan 实施 P0-1 方案 A（推荐），删除 `app/memory/checkpointer.py` 文件，所有 checkpointer 逻辑集中在 `app/graph/checkpointer.py`"）+ spec §2 模块树 L205 同步 | ✅ **到位** |
| **P0-2** | `load_memory_node` 改用 `cp.aget_tuple(config)` 解析 `saved.checkpoint.get("messages", [])` | Task 9 GREEN 段 L642-650：代码明确 `saved = await cp.aget_tuple({"configurable": {"thread_id": thread_id}})` + `checkpoint = saved.checkpoint if saved else {}` + `messages = list(checkpoint.get("messages", []))` | ✅ **到位** |
| **P0-3** | `make_checkpointer` 删 `@asynccontextmanager` 改为普通 `async def make_checkpointer() -> BaseCheckpointSaver` | Task 2 GREEN 段 L261-283：函数签名 `async def make_checkpointer() -> BaseCheckpointSaver`（无 contextmanager 装饰）；try/except `(PermissionError, Exception)` 降级 SQLite；`await cp.setup()` 不再 yield | ✅ **到位** |
| **P0-4** | graph 8 节点 < langgraph 默认 `max_iterations=25`；M8 必须 `asyncio.wait_for(graph.ainvoke(...), timeout=30)` 包装；Task 11 RED 加 `test_invoke_timeout_via_wait_for` | Task 11 GREEN L799-800 注释："P0-4: 节点数 8 < langgraph 1.0.5 默认 max_iterations=25, 安全 / 单节点超时由 M8 调用方 asyncio.wait_for 包装" + 跨 M 联动 L882"M8 graph.invoke 必须用 asyncio.wait_for(...)" + Task 11 RED 段 L831-833 RED 测试 `test_invoke_timeout_via_wait_for` 演示调用方模式 | ✅ **到位**（但仅文档化 + 演示测试，真实超时包装在 M8 落地——这是 M7/M8 边界划分的合理选择） |
| **P0-5** | 删 `route_after_answer` + `test_routes_to_save_memory_after_answer`；`workflow.py` 用 `add_edge("answer", "save_memory")` 常量边 | Task 10 L706 注释 "**已删除** route_after_answer 及对应测试 test_routes_to_save_memory_after_answer" + workflow.py L792-793 `g.add_edge("answer", "save_memory")` + `g.add_edge("answer_chitchat", "save_memory")` 两条常量边 | ✅ **到位**（无二义性） |
| **P0-6** | 新增 Task 9b `answer_chitchat_node` 实现 + `app/prompts/answer_chitchat.yaml` + 通知 M3 工厂 `KNOWN_NODES` 追加 `"answer_chitchat"` | Task 9b L662-681 完整 GREEN 实现（`make_llm("answer_chitchat")` + history + query + `sources=[]` + `chunks=[]`）+ Files 表 L189 已加 `app/prompts/answer_chitchat.yaml` + 跨 M 联动 L881 明示"必须注册 answer_chitchat 节点到 KNOWN_NODES" + DoD L852 "8 节点函数全部就位" + workflow.py L779 `g.add_node("answer_chitchat", answer_chitchat_node)` | ✅ **到位** |
| **P0-7** | `save_memory_node` 注释明确 checkpointer 自动 persist 行为 + M10 用 `NodeInterrupt` 而非改本函数 | Task 9 GREEN L652-657 注释 + 修订记录 L900 + 跨 M 联动 L883 "M10 save_memory no-op 无 intercept，M10 若需节点级 trace 用 NodeInterrupt 而非改 save_memory" | ✅ **到位** |
| **P0-8** | `app/graph/errors.py` 新增 `safe_node(name)` 装饰器 + `GraphNodeError` / `GraphNodeFallback` 异常类；所有 8 节点函数 `@safe_node(name)` 包装 | Task 11 GREEN L724-755：`safe_node` 装饰器完整代码（try/except + `state.error = f"{node_name}_failed: {str(e)[:200]}"` + `log.error` + 不抛出）+ 所有 8 节点 GREEN 段均显式 `@safe_node("...")`：load_memory L641 / classify L582 / query_rewrite L612 / retrieve L815 / rerank L478 / answer L522 / answer_chitchat L672 / save_memory L652 | ✅ **到位** |

**P0 验证小结**：8 项全部到位，P0 阻塞全部解除。其中：
- P0-1/P0-2/P0-3 是代码跑不起来的**编译/运行**级修复 → 已全修
- P0-5/P0-6/P0-7/P0-8 是 graph 设计完整性修复 → 已全修
- P0-4 是跨 M 调用方约束（已落 M7 plan + 跨 M 联动通知 M8）

### 1.2 P1 项验证（14 项）

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|---------|---------|---------|------|
| **P1-1** | `store.py` vs `retriever.py` 边界：Files 表注释明确 `store.py` 仅 M4-M6 ingest 用，`retriever.py` graph 节点专用 | 仓库布局 L51-56（store.py L54 "**仅供 M4-M6 ingest 用**" + retriever.py L55 "retrieve 节点用"）+ 修订记录 L902 | ✅ **到位** |
| **P1-2** | fallback 文案移入 `RetrievalSettings.fallback_message` | Files 表 修改段 L202 "RetrievalSettings{fallback_message=...}" + Task 11 GREEN L825 `answer = settings.retrieval.fallback_message` | ✅ **到位** |
| **P1-3** | `CHITCHAT_KEYWORDS` 拆 `_CHITCHAT_STRONG` + `_CHITCHAT_MEDIUM` + 中强度 RED 测试 | Task 7 GREEN L573-578：强集合（指代词/人称/翻译软件问候）+ 中集合（哪些/这些/那些/此/其/您/如上/前述）+ RED 测试 `test_classify_heuristic_chinese_pronouns_medium` L559-560 | ✅ **到位** |
| **P1-4** | `retrieve_node` 多 rewrite 并查策略 + `dedupe_by_doc` 合并去重 | Task 4 GREEN L412-423：`rewrites = state.get("rewrites") or [state["query"]]` + `for r in rewrites: chunks = await retrieve(r, top_k=10); all_chunks.extend(chunks)` + `deduped = dedupe_by_doc(all_chunks)` + RED 测试 `test_retrieve_node_invoke_in_graph_handles_multiple_rewrites` L408-409 | ✅ **到位** |
| **P1-5** | `parse_json_scores` + `_extract_json` 完整实现（markdown block / 裸 JSON / scores 字段 / 长度校验 / 0-10 clip）+ 5 个 RED 测试 | Task 5 GREEN L447-473 完整实现 + 5 个 RED 测试 L435-446（`test_parse_json_scores_handles_markdown_block` / `handles_invalid_json_returns_neutral` / `clips_to_0_10_range` / `handles_wrong_length_returns_neutral` / `test_rerank_fallback_on_invalid_json` L503-504） | ✅ **到位**（实现完整 + 测试覆盖 4 种边界 + 1 个上层降级） |
| **P1-6** | `AnswerSettings.max_chunk_chars=800` 默认；answer prompt 中截断；RED 测试 | Files 表 修改段 L202 "AnswerSettings{max_chunk_chars=800}" + Task 6 GREEN L531 `max_chars = settings.answer.max_chunk_chars` + L535 `text_excerpt = c["text"][:max_chars]` + RED 测试 L517-518 `test_answer_truncates_chunks_to_max_chars` | ✅ **到位** |
| **P1-7** | `classify_node` 传 history + query；RED 测试 | Task 7 GREEN L590-593：`msgs = list(state.get("messages") or [])` + `msgs.append(HumanMessage(content=q))` + `resp = await llm.ainvoke(msgs)` + RED 测试 L562-563 `test_classify_passes_history_to_llm` | ✅ **到位** |
| **P1-8** | rerank 评分写入 `chunk["rerank_score"]`；answer source 构造读 `c.get("rerank_score", 0.0)`；RED 测试 | Task 5 GREEN L496-499 `chunks=[{**c, "rerank_score": s} for c, s in ranked]` + Task 6 GREEN L541 `"score": c.get("rerank_score", 0.0)` + RED 测试 L514-515 `test_answer_passes_rerank_score_to_source` | ✅ **到位** |
| **P1-9** | `OpenSearchSettings.index_name="chunks"`；retriever 读 settings | Files 表 修改段 L202 "OpenSearchSettings{url, index_name=\"chunks\", pool_size=20}" + Task 4 GREEN L374 `index=settings.opensearch.index_name` | ✅ **到位** |
| **P1-10** | `dedupe_by_doc` 策略：同 doc_id 保留最高 `_score`，首次出现位置优先 | Task 4 GREEN L387-406 完整实现（`seen: dict[str, Chunk]` + 分数比较 + 顺序保持）+ RED 测试 L383-384 `test_dedupes_by_doc_id_keeps_highest_score` | ✅ **到位** |
| **P1-11** | `CheckpointerSettings{pool_size=5, max_overflow=10}` 显式配置 + 总连接数注释 | Files 表 修改段 L202 "CheckpointerSettings{dsn, sqlite_path, pool_size=5, max_overflow=10}" + Task 2 GREEN L266-272 注释 "P1-11: 显式连接池 / 默认 pool_size=5, max_overflow=10 / 总连接数 5+10+10+20=45 < PG max_connections=100" | ✅ **到位** |
| **P1-12** | thread_id UUID 碰撞：V1 接受 + 风险表记录 + 注释 V2 改 `f"{tenant_id}_{uuid4()}"` | 风险表 L913 + 修订记录 L957 | ✅ **到位** |
| **P1-13** | kNN filter context 预留：注释 V1.1 可加 `query.knn.vector.filter.term.metadata.user_id` | 风险表 L914 + 修订记录 L958 | ✅ **到位**（仅注释 + 风险记录，无代码变更——符合 P1-13 V1 不做但预埋的定位） |
| **P1-14** | chunk text 截断两处独立：rerank 500 / answer 800 | Task 5 L489 `f"[{i}] {c['text'][:500]}\n"` + Task 6 L535 `text_excerpt = c["text"][:max_chars]`（max_chars=800 默认） | ✅ **到位** |
| **P1-15** | `pytest-httpx` / `freezegun` 测试依赖：Tech Stack 表追加 + pyproject dev 段加 | Tech Stack 表 L145-146：`pytest-httpx>=0.30,<1` + `freezegun>=1.5,<2` + Files 表 修改段 L201 "dev 段追加 `pytest-httpx>=0.30,<1` / `freezegun>=1.5,<2`" | ⚠️ **Tech Stack 落到位** · `pyproject.toml` dev 段具体新增位置需 implementation 时复核（plan 文字承诺"dev 段追加"但未给 pyproject.toml 段位置） |
| **P1-16** | `make_checkpointer` `try/except (PermissionError, Exception)` + 自动降级 SQLite + `log.warning` | Task 2 GREEN L276-283 完整实现 + RED 测试 L292-293 `test_falls_back_to_sqlite_on_setup_permission_error` | ✅ **到位** |

**P1 验证小结**：14 项全部到位。P1-15 唯一轻度漂移——Tech Stack 表声明 + Files 表修改段承诺"dev 段追加"一致，但 plan 未给出 pyproject.toml 实际 diff（这是 plan 风格问题，非功能问题，implementation 时按字面补即可）。P1-13 全部以注释 + 风险记录形式落地，符合"V1 不做但预埋"的定位。

### 1.3 P2 项验证（9 项）

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|---------|---------|---------|------|
| **P2-1** | `RagState.state_version: int` 字段；`load_memory_node` 用 `state.get("field", default)` 兼容 | Task 1 GREEN L243 `state_version: int` + Task 9 GREEN L649 `messages = list(checkpoint.get("messages", []))` + RED 测试 L631-632 `test_load_memory_handles_missing_old_checkpoint_fields` | ✅ **到位** |
| **P2-2** | graph 并发安全：风险表记录 langgraph checkpointer 乐观锁 + M8 串行化 + UI 禁双击 | 风险表 L919 + 修订记录 L963 | ✅ **到位**（仅风险表，无代码） |
| **P2-3** | classify LLM 兜底改 `re.search(r'"intent"\s*:\s*"(retrieve|chitchat)"', resp.content)`；不命中默认 "retrieve" | Task 7 GREEN L594-597 完整 regex + RED 测试 L565-569（`test_classify_llm_regex_parse_intent` + `test_classify_llm_invalid_format_defaults_to_retrieve`） | ✅ **到位** |
| **P2-4** | workflow.py 显式类型注解 `def compile_workflow(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph` | Task 11 GREEN L770-771 完整注解 | ✅ **到位** |
| **P2-5** | 集成测试 mock vs real 拆分：`test_graph_invokes_end_to_end_mock` + `test_m7_e2e_real_docker`（`@pytest.mark.require_docker`） | Task 11 RED L713-714 + L718-722（两条独立测试 + `require_docker` marker） | ✅ **到位** |
| **P2-6** | `OpenSearchSettings.pool_size=20` + AsyncOpenSearch 显式 `connection_class=RequestsHttpConnection` + `pool_maxsize` + `retry_on_timeout` + `max_retries=3` | Files 表 修改段 L202 "OpenSearchSettings{url, index_name=\"chunks\", pool_size=20}" + Task 4 GREEN L366-372 完整配置 | ✅ **到位** |
| **P2-7** | `retrieve_with_fallback` 移到 `app/graph/nodes.py`；`errors.py` 只留异常类 + 装饰器 | Task 11 GREEN L766 import 含 `retrieve_with_fallback`（从 nodes.py）+ Task 11 GREEN L813-829 完整实现 + 修订记录 L968 | ✅ **到位** |
| **P2-8** | 集成测试 docker-compose 路径 `apps/rag_v1/infra/docker-compose.yml` 显式标注 | Task 11 RED L720 + 测试策略 L843 完整路径 | ✅ **到位** |
| **P2-9** | 统一节点名 `"answer_chitchat"`：架构图 / edges.py / workflow.py 三者一致 | 修订记录 L970 + 架构图 L96-114（已用 `answer_chitchat`）+ Task 10 L697 注释 "P2-9: 统一节点名 answer_chitchat" + workflow.py L786 mapping `{"answer_chitchat": "answer_chitchat"}` | ✅ **到位** |

**P2 验证小结**：9 项全部到位。P2-1 / P2-3 / P2-4 / P2-5 / P2-6 / P2-7 / P2-9 都有代码 / 测试 / 注释落地；P2-2 / P2-8 仅文档 / 风险记录（符合 P2 优先级定位）。

### 1.4 33 项修复到位率统计

| 级别 | 项数 | 完全到位 | Tech Stack / 文档到位 需 implementation 复核 | 未到位 |
|------|------|---------|---------------------------------------------|--------|
| P0 | 8 | 8 | 0 | 0 |
| P1 | 16 | 15 | 1（P1-15 pyproject.toml diff） | 0 |
| P2 | 9 | 9 | 0 | 0 |
| **合计** | **33** | **32** | **1** | **0** |

**r1 修复到位率 = 32/33 = 97%**（严格）/ **100%**（宽口径，计 P1-15 已在 Files 表修改段承诺"dev 段追加"）

---

## 2. r1 修复引入的新问题

### 新-1（**P1**）· workflow.py `add_conditional_edges` mapping 缺 `END` 选项

**位置**：Task 11 GREEN 段 L784-787
```python
g.add_conditional_edges("classify", route_after_classify, {
    "query_rewrite": "query_rewrite",
    "answer_chitchat": "answer_chitchat",
})
```

**问题**：
- `route_after_classify` 在 Task 10 GREEN 段 L694-698 只返回 `"answer_chitchat"` 或 `"query_rewrite"` 两值
- 但 `Literal["retrieve", "chitchat"]` 定义的 intent（Task 1 GREEN 段 L235）有 `"retrieve"` —— 这是 classify LLM 兜底返回时（`if "intent" in resp.content` 解析后）的 intent 字段名
- 如果 classify LLM 返回 `"intent": "retrieve"`（string 形式），state.intent="retrieve"，route_after_classify 走 `return "query_rewrite"` 分支——**这条路径 OK**
- 但如果 LLM 兜底 regex 不命中（P2-3），intent 默认 `"retrieve"`（Task 7 L596）——也 OK
- **真正风险点**：`route_after_classify` 函数体（Task 10 L694-698）只比较 `state.get("intent") == "chitchat"`，intent 字段值"retrieve"才走 query_rewrite。**但 Literal 定义有 "retrieve"**——不是 bug，但 plan 主体 L19 "条件边：classify 节点判 intent ∈ {retrieve, chitchat} 决定后续走哪条分支" 暗示 retrieve 走 retrieve 节点（不是 query_rewrite）——**与 Task 10 函数体矛盾**！

**架构图 L96-114 路径**：
```
classify → [retrieve] path → query_rewrite → retrieve → rerank → answer → save_memory
```

**Task 10 函数体实际**：
```python
if state.get("intent") == "chitchat":
    return "answer_chitchat"
return "query_rewrite"  # 不管 retrieve/chitchat 之外的任何值都走这里
```

**r1 修复引入的"看似一致实则自相矛盾"**：架构图说"chitchat 走 answer_chitchat，retrieve 走 query_rewrite"，函数体说"非 chitchat 走 query_rewrite"——两者**字面一致**（chitchat 走 answer_chitchat、其他走 query_rewrite）——但**type Literal 有 "retrieve" 值** 是个幽灵，**没人赋 intent="retrieve"**——classify_node 函数体只赋 `"chitchat"` 或 `"retrieve"`（P2-3 兜底 default `"retrieve"` 但 LLM 路径才用，启发式短路直接 `return "chitchat"`）。

**结论**：实际无 bug，但 plan 应补：
- 改 `route_after_classify` 为显式 `if/elif/else` 三分支（含 "retrieve" 显式 return "query_rewrite" + 兜底 default "query_rewrite"）
- 或 Literal 删除 `"retrieve"`（但 type 完整性受损）
- **建议**：在 `route_after_classify` 函数体加注释 "classify_node 已保证 intent ∈ {retrieve, chitchat}，本函数只需 chitchat 走 answer_chitchat，其他走 query_rewrite"——消除 review 误读

**影响等级**：P1（不阻塞实现，但 review/未来 reader 易误读）

---

### 新-2（**P1**）· `save_memory` 节点 chitchat 路径与 retrieve 路径复用——M10 业务级 trace 无法区分

**位置**：Task 11 GREEN 段 L792-794
```python
g.add_edge("answer", "save_memory")
g.add_edge("answer_chitchat", "save_memory")
g.add_edge("save_memory", END)
```

**问题**：
- r1 修复 P0-7 时明确：`save_memory_node` 是 no-op 占位；LangGraph checkpointer 在 graph invoke **完成后**自动 persist
- 但 M10 业务级 trace（langfuse）要看"这条 thread 走的是 retrieve 路径还是 chitchat 路径"——目前 answer 与 answer_chitchat **都连到同一个 save_memory 节点**（no-op），M10 在 save_memory 上加 trace 拿不到"哪条分支来"的信号
- **r1 修复前的设想**：P0-7 注释 L654-656 "M10 如需 intercept 保存时机，请用 NodeInterrupt 或 after_save_hook，**不**改本函数体"
- **M10 实际诉求**（参考 M10 r2 review 已修 `inspect.signature` + `get_client()` API）：M10 用 `node_trace` 装饰器挂在节点函数上，trace name 默认 = 函数名 `save_memory`——**两条路径的 trace 都是 "save_memory"，无法区分 intent**

**结论**：
- r1 修复 P0-7 时没考虑到 M10 业务级 trace 的"路径区分"诉求
- **建议**：在 `save_memory_node` 函数体内读 `state.get("intent")` 写到 `state["last_intent"]` 或 Langfuse metadata；或 plan 注明"M10 如需区分 retrieve vs chitchat 路径，请在 answer / answer_chitchat 节点分别加 trace，**不**在 save_memory 节点上区分"
- 这不是 bug，是 P0-7 修复的衍生——但 M10 已修（r2），M7 跨 M 联动段 L883 只说"M10 用 NodeInterrupt 而非改 save_memory"——**没说 trace name 区分问题**

**影响等级**：P1（不阻塞 M7 实施；M10 实施时再加 trace 即可）

---

### 新-3（**P2**）· `safe_node` 装饰器不捕获 `asyncio.CancelledError` 与 `KeyboardInterrupt`

**位置**：Task 11 GREEN 段 L740-755
```python
def safe_node(node_name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(state: RagState, *args, **kwargs) -> RagState:
            try:
                return await func(state, *args, **kwargs)
            except Exception as e:  # ← 范围过大
                log.error("Node %s failed: %s", node_name, str(e), exc_info=True)
                return {
                    **state,
                    "error": f"{node_name}_failed: {str(e)[:200]}",
                }
        return wrapper
    return decorator
```

**问题**：
- `except Exception` 范围包括 `asyncio.CancelledError`（Python 3.8+ `CancelledError` 继承自 `BaseException`——**这次 OK**）但 `KeyboardInterrupt` 也继承 `BaseException`——**这次也 OK**
- **真正问题**：`except Exception` 会吞掉 `langgraph` 自己的 `NodeInterrupt` / `GraphRecursionError` / `InvalidUpdateError`——这些是**控制流异常**，应该向上传播让 graph 决定（interrupt 让 graph 暂停、recursion 让 graph 报错、invalid update 让 graph 重试）
- M10 跨 M 联动 L883 明示 "M10 用 NodeInterrupt 而非改 save_memory"——M10 抛 NodeInterrupt 时**会被 safe_node 吞掉**变成 `state.error="save_memory_failed: NodeInterrupt(...)"`——M10 业务级 trace 中断机制失效

**结论**：
- r1 修复 P0-8 时**只关心"不让节点崩 graph"**，但未考虑"哪些异常是控制流应放行"
- **建议**：在 `safe_node` 装饰器加白名单：`except (NodeInterrupt, GraphRecursionError, InvalidUpdateError): raise`；其他 Exception 才吞
- 或更保守：把 `Exception` 改为 `except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, ...)` 显式列出
- Python 3.8+ `BaseException` → `Exception` → `CancelledError`（自 Python 3.8 起 CancelledError 改继承自 BaseException）——`Exception` 不捕获 CancelledError 是**正确**的——`KeyboardInterrupt` 也不在 `Exception` 内

**影响等级**：P2（M10 trace 中断机制不常用；当前 r1 实现已覆盖 99% 节点异常场景）

---

### 新-4（**P2**）· `AnswerSettings.max_chunk_chars=800` 与 M4 ingest chunk_size=512 tokens 的对齐问题

**位置**：
- Files 表 修改段 L202 "AnswerSettings{max_chunk_chars=800}"（M7 决定）
- M4 ingest 切块策略待定（r2 review 主体同步率 0%，22 项待续——**未明确 ingest chunk size**）

**问题**：
- M7 `AnswerSettings.max_chunk_chars=800` 字符截断（Chinese ≈ 800 char / 1.5 ≈ 530 tokens）
- M4 ingest 默认 chunk size 若是 512 tokens（≈ 1500-2000 char Chinese），answer 截断到 800 char 意味着**后 1/3 chunk 文本被丢**
- LLM 拿到 800 char 的 chunk 后看不到原 chunk 后 1/3 上下文——可能影响 answer 完整性
- **但**：M7 P1-6 的 800 char 是"防 context window 溢出"——是 trade-off（多 chunk 覆盖 vs 单 chunk 完整）

**结论**：
- r1 修复 P1-6 时未与 M4 联动确认 chunk size
- **建议**：在 Files 表 修改段加注释 "max_chunk_chars=800 是 M7 拍板的 LLM context 窗口保护值；M4 ingest chunk size 若 > 800 char，建议 M4 端切到 600-700 char 留 padding"
- **或**：M7 改 `max_chunk_chars=1500`（≈ 1 个 512 token chunk），由 M4 ingest 端保证 ≤ 1500 char
- 实施前 M7 ↔ M4 需对齐

**影响等级**：P2（不阻塞 M7 实施；M4 落地时同步确认）

---

### 新-5（**P2**）· 修订记录 L938-970 33 行与计划表 6 行原风险"曾被否决的替代方案"列语义不一致

**位置**：风险表 L888-927 + 修订记录 L933-970

**问题**：
- 原 6 行风险 L888-927（langgraph API drift / PG 降级 / OpenSearch checkpointer 否决）——是 plan 初稿风险
- 修订记录 33 行"r1 已修"——是 r1 修复条目
- **风险表与修订记录是两份独立列表**——r1 修复条目**没合并到风险表**（除了 L894-901 等少数 r1 已修条目写进了风险表 L888-927 之后）
- 实际阅读体验：风险表只有 6 行原风险 + 27 行 r1 已修（部分）——**和修订记录 33 行不同步**
- r1 修复条目散落在：风险表 L894-925（r1 已修标签） + 修订记录 L938-970（r1 已修标签）——**同一信息两处出现**

**结论**：
- 建议 r2 把 33 项 r1 已修条目**只保留一处**（推荐：风险表加列"曾被否决的替代方案"——作为单一信息源；修订记录 L937 只保留一行 "r1-2026-06-11 33 项 P0/P1/P2 全部修复（详见 review ...）"）
- 当前 plan **未做整合**——r1 reader 要看两处才能拼全图
- 不是 bug，是 r1 修复过程中**没统一格式**

**影响等级**：P2（不影响实施；review 体验略冗余）

---

## 3. 跨 M 一致性检查（M0/M1/M2/M3/M4/M5/M6/M8/M9/M10/M11/M12）

### M7 ↔ M0（infra · docker-compose）

| 检查项 | M7 现状 | M0 r2 现状 | 一致性 |
|--------|--------|-----------|--------|
| OpenSearch 容器 | M7 用 `settings.opensearch.url` 调 AsyncOpenSearch | M0 启 OpenSearch 9200 | ✅ 一致 |
| PG 容器 | M7 用 `settings.checkpointer.dsn` | M0 启 PG 5432 + 业务库 + LangGraph 库 | ✅ 一致 |
| docker-compose 路径 | M7 L720 + L843 `apps/rag_v1/infra/docker-compose.yml` | M0 路径同 | ✅ 一致（P2-8 已修） |
| `app.state.checkpointer` 注入 | M7 L262-264 显式返回实例，lifecycle 自管；M0 lifespan 负责 `await cp.setup()` | M0 lifespan 段已落 | ✅ 一致 |
| M3 TEI 18080 端口 | M7 retrieve_node L360 调 `TEIEmbedder` | M0 启 TEI 18080 | ✅ 一致 |

**结论**：M7 ↔ M0 **完全一致**。M0 r2 补完后 M7 可直接用 settings + lifespan 注入。

### M7 ↔ M1（schema · chat_sessions）

| 检查项 | M7 现状 | M1 r2 现状 | 一致性 |
|--------|--------|-----------|--------|
| `chat_sessions.thread_id` 字段 | M7 Task 3 L318-326 `ChatSession.get(id=session_id, user_id=user_id)` 查 thread_id | M1 r2 已确认 `chat_sessions.thread_id UNIQUE` | ✅ 一致 |
| `session_metadata` JSONB | 未在 M7 主体使用 | M1 r2 已确认字段 | ✅ 一致（M7 当前不读 session_metadata——可在 V1.1 加 use case） |
| `last_message_at` | 未在 M7 主体使用 | M1 r2 已确认字段 | ✅ 一致（M8 / M11 实施时用） |
| `is_active` / `deleted_at` 软删除 | M7 越权 404（V1 Scope §5）行为：`session not found or not owned` 抛 `ThreadNotFound` | M1 r2 已加 | ✅ 一致 |
| `updated_at=func.now()` | M7 L318 不依赖 | M1 r2 已修 | ✅ 一致 |

**结论**：M7 ↔ M1 **完全一致**。M1 r2 补完后 M7 可直接依赖。

### M7 ↔ M2（auth · Depends）

| 检查项 | M7 现状 | M2 r2 现状 | 一致性 |
|--------|--------|-----------|--------|
| `user_id` 来源 | M7 L318 `resolve_thread_id(session_id, user_id)` 由调用方注入 | M2 r2 `Depends(get_current_user)` 拿 user_id | ✅ 一致（M8 调用 M7 时把 user_id 传给 M7） |
| 越权 404 行为 | M7 L324 `raise ThreadNotFound` | M2 r2 NP-1~5 + 越权 404 一致 | ✅ 一致 |
| `auth_sessions.is_revoked` | M7 不直接依赖 | M2 r2 已加字段 | ✅ 不影响 M7 |

**结论**：M7 ↔ M2 **完全一致**。M2 越权行为与 M7 resolve_thread_id 404 行为对齐。

### M7 ↔ M3（LLM 工厂 + TEI Embedding） · **强依赖**

| 检查项 | M7 现状 | M3 r2 现状 | 一致性 |
|--------|--------|-----------|--------|
| `KNOWN_NODES` 7 节点 | M7 修订记录 L881 + 跨 M 联动 "**M3 工厂 KNOWN_NODES 追加 `answer_chitchat`**" | M3 r2 已加 `answer_chitchat`（共 7 节点） | ✅ **一致**（关键修复落地） |
| `make_llm(node)` 7 处调用 | M7 节点函数显式 `make_llm("rerank")` / `make_llm("answer_chitchat")` 等 | M3 工厂支持 7 节点名 | ✅ 一致 |
| `model.callbacks` vs `.with_config(...)` | M7 节点函数不直接处理 callback，依赖工厂层 | M3 r2 已切到 `.with_config(...)` | ✅ 一致（M7 透明受益） |
| `load_prompt(node)` 5 个 yaml | M7 Files 表 L60-65 5 个 yaml（classify / rewrite / rerank / answer / answer_chitchat） | M3 r2 已注册 5 个 prompt 名 | ✅ 一致 |
| TEI 18080 embedding | M7 L360 `from app.embedding.client import TEIEmbedder` | M3 r2 TEI 18080 已起 | ✅ 一致 |
| Prompt YAML 路径 | M7 L60-65 `app/prompts/*.yaml` | M3 r2 已建 5 个 yaml | ✅ 一致 |

**结论**：M7 ↔ M3 **完全一致**。**M7 强阻塞（answer_chitchat 节点）已解除**。

### M7 ↔ M4（ingest-file · OpenSearch 写）

| 检查项 | M7 现状 | M4 r2 现状 | 一致性 |
|--------|--------|-----------|--------|
| `OpenSearchClient.ensure_index` | M7 L375 读 `settings.opensearch.index_name` | M4 r2 P0-3 补 mapping | ✅ 一致 |
| `payload_hash` 字段 | M7 不直接读（仅 retrieve 时靠 OS 内部 hash） | M4 r2 P0-3 已加 | ⚠️ **轻度漂移**：M7 retriever 拿到 chunk 后不暴露 payload_hash——M11 RAGAS 评测若要"同一文档判定"需 M7 把 payload_hash 透传 |
| HNSW dim=1024 cosine | M7 L376-378 kNN query 用 dim=1024 | M4 r2 已建同维 index | ✅ 一致 |
| `metadata.image_ref` | M7 answer L540 `c["metadata"].get("image_ref")` 读 | M4 r2 ingest 写入 metadata | ✅ 一致 |
| `chunk_id` 唯一性 | M7 answer L537 `c["chunk_id"]` 读 | M4 r2 payload_hash 派生 | ✅ 一致 |

**结论**：M7 ↔ M4 **基本一致**，仅 `payload_hash` 透传是 P2 优化项（M11 RAGAS 评测时再加）。

### M7 ↔ M5（ingest-url） / M7 ↔ M6（ingest-confluence）

| 检查项 | M7 现状 | M5/M6 r2 现状 | 一致性 |
|--------|--------|--------------|--------|
| OpenSearch 写 chunk 路径 | M7 只读 | M5/M6 r2 已修 NP-1~5 / NP-A~F | ✅ 不影响 M7 |
| chunk 结构 | M7 读 `chunk_id / doc_id / text / vector / metadata / _score / rerank_score` | M5/M6 写入同结构 | ✅ 一致（`exceptions` 字段未对齐是 M5/M6 内部 cosmetic bug，不影响 M7） |

**结论**：M7 ↔ M5/M6 **完全一致**。M7 不依赖 M5/M6 的 exceptions 字段。

### M7 ↔ M8（api-chat） · **强依赖**

| 检查项 | M7 现状 | M8 r1 现状 | 一致性 |
|--------|--------|-----------|--------|
| `graph.ainvoke()` 异步 | M7 workflow.py 返回 CompiledStateGraph | M8 调 `await graph.ainvoke(...)` | ✅ 一致 |
| 30s `asyncio.wait_for` 超时 | M7 L832-833 RED 演示 + 跨 M 联动 L882 "M8 必须 asyncio.wait_for" | M8 r1 已修 | ✅ 一致 |
| 读 `state.error` 转 HTTP 状态码 | M7 L753 `state.error = f"{node_name}_failed: ..."` | M8 r1 读 state.error | ✅ 一致 |
| `user_id` / `thread_id` 注入 | M7 `resolve_thread_id(session_id, user_id)` | M8 调 M7 前先 `get_current_user` 拿 user_id | ✅ 一致 |
| 流式 `astream_events` | M7 L121 注释 "M8.1 / M3.4 已签协议" | M8 r1 已修 | ✅ 一致 |

**结论**：M7 ↔ M8 **完全一致**。30s 超时 + state.error HTTP 状态码契约已双向落地。

### M7 ↔ M9（ui-gradio）

| 检查项 | M7 现状 | M9 r1 现状 | 一致性 |
|--------|--------|-----------|--------|
| trace_id 流转 | M7 不生成 trace_id | M9 r1 调 M8 时传 trace_id（M8 透传到 M7） | ✅ 一致 |
| chitchat 走 answer_chitchat_node | M7 Task 9b 完整实现 | M9 r1 不区分（UI 层统一调 M8 `/api/chat`） | ✅ 一致 |
| 历史展示 | M7 save_memory 落 checkpoint → M8 `/api/sessions/{id}` 读 | M9 r1 调 M8 拿 history | ✅ 一致 |

**结论**：M7 ↔ M9 **完全一致**。M9 不直连 M7，走 M8 间接。

### M7 ↔ M10（obs-langfuse · 业务级 trace） · **强依赖**

| 检查项 | M7 现状 | M10 r2 现状 | 一致性 |
|--------|--------|-----------|--------|
| 节点函数加 `@trace` 装饰器 | M7 节点函数目前无 `@trace`（M7 自身不挂 trace） | M10 r2 已修 `inspect.signature` + `get_client()` API | ✅ 一致（M10 实施时 M7 节点函数加装饰器） |
| `NodeInterrupt` vs 改 save_memory | M7 L654-656 注释"M10 用 NodeInterrupt 而非改 save_memory" | M10 r2 已修 | ✅ 一致 |
| trace name 区分 retrieve vs chitchat 路径 | **未明示**（r1 衍生新-2） | M10 需读 state.intent 区分 | ⚠️ **轻度漂移**（新-2 已记录） |

**结论**：M7 ↔ M10 **基本一致**，trace name 区分是 P1 优化项（实施时在 M10 侧加分支即可）。

### M7 ↔ M11（eval-ragas）

| 检查项 | M7 现状 | M11 r1 现状 | 一致性 |
|--------|--------|-----------|--------|
| `graph.invoke(query, thread_id="eval-{n}")` 跑 golden set | M7 L124 "M11 跑 graph.invoke 拿 query/answer/chunks" | M11 r1 已修 | ✅ 一致 |
| chitchat 走 answer_chitchat_node | M7 Task 9b 完整实现 | M11 RAGAS 评测含 chitchat golden set | ✅ 一致 |
| runner 重试 | M7 不涉及 | M11 r1 runner 重试 | ✅ 不冲突 |

**结论**：M7 ↔ M11 **完全一致**。

### M7 ↔ M12（hardening · 中间件）

| 检查项 | M7 现状 | M12 r1 现状 | 一致性 |
|--------|--------|-----------|--------|
| safe_node 异常传播 → HTTP 状态码 | M7 P0-8 safe_node + state.error | M12 中间件读 state.error | ✅ 一致 |
| rate limit | M7 不涉及 | M12 中间件 | ✅ 不冲突 |
| 节点级 trace 与中间件顺序 | M7 节点函数 + M10 装饰器 | M12 中间件最外层 | ✅ 一致 |
| checkpointer 写盘异常 → save_memory | M7 save_memory no-op + checkpointer 自动 persist | M12 不影响 | ✅ 一致 |

**结论**：M7 ↔ M12 **完全一致**。

### 跨 M 一致性总结

| M 对 | 状态 | 备注 |
|------|------|------|
| M7 ↔ M0 | ✅ 完全一致 | lifespan + settings 单例对齐 |
| M7 ↔ M1 | ✅ 完全一致 | thread_id UNIQUE / session_metadata / last_message_at 已确认 |
| M7 ↔ M2 | ✅ 完全一致 | user_id 由 M2 Depends 注入 |
| M7 ↔ M3 | ✅ **完全一致**（关键修复） | KNOWN_NODES 7 节点含 answer_chitchat / 范本影响段已明示 |
| M7 ↔ M4 | ⚠️ 基本一致 | payload_hash 透传是 P2 优化项 |
| M7 ↔ M5 | ✅ 完全一致 | M7 不读 exceptions |
| M7 ↔ M6 | ✅ 完全一致 | M7 不读 exceptions |
| M7 ↔ M8 | ✅ **完全一致**（关键修复） | 30s 超时 + state.error HTTP 契约双向落地 |
| M7 ↔ M9 | ✅ 完全一致 | trace_id 由 M8 透传 |
| M7 ↔ M10 | ⚠️ 基本一致 | trace name 区分是 P1 优化项（新-2） |
| M7 ↔ M11 | ✅ 完全一致 | thread_id="eval-{n}" 复用 workflow |
| M7 ↔ M12 | ✅ 完全一致 | safe_node + state.error 透明传递 |

**跨 M 关键阻塞（M3 强依赖 / M8 强依赖）已全部解除**。4 项 M（r1 衍生新-1/2/3/4）已识别但都不阻塞实施。

---

## 4. 风险表补全质量

### 4.1 风险表结构

| 部分 | 行数 | 内容 |
|------|------|------|
| 原风险（plan 初稿） | 6 行（L888-927） | langgraph API drift / PG 降级 / setup 权限 / retrieve 崩溃 / prompt 漂移 / kNN 性能 |
| r1 已修（修订记录） | 33 行（L938-970） | 8 P0 + 14 P1 + 9 P2 + 2 跨 M |
| r1 已修（风险表） | 27 行（L894-925） | 同 33 项的部分子集（L894-925 + 原 6 行 + kNN 性能 1 行 = 27+7 行） |

**问题**：
- 风险表 L894-925 的"r1 已修"标签和修订记录 L938-970 是**两份独立列表**——同一信息两处出现
- r1 review 建议追加的 5 行风险（review L907-913）——**M7 风险表已包含**（L894-925）+ 又新加 4 行（L926 kNN 性能保留 + L891-892 两行 langgraph 锁版本 + L893 PG 降级保留 + L894 P0-1 r1 已修...）——**形式上完整**
- 曾被否决的替代方案列：原 6 行有 1 行（OpenSearch checkpointer 否决）——**r1 修复条目绝大多数 `曾被否决的替代方案` 列为空**（除 P0-1 / P0-2 / P0-3 / P0-4 / P0-5 有"否决方案 B"说明）——这与 r1 review 期望"对每个 P0/P1 都应列替代方案"不完全一致，但**作为修复条目的执行记录，替代方案列空是合理的**（r1 修复本身就是选定方案）

### 4.2 风险表质量评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 原风险保留 | ⭐⭐⭐⭐⭐ | 6 行原风险完整保留（含 OpenSearch checkpointer 否决方案） |
| r1 修复条目完整性 | ⭐⭐⭐⭐ | 33 项 r1 已修条目信息完整，但**与修订记录重复**（新-5） |
| 替代方案列 | ⭐⭐⭐ | r1 修复条目绝大多数为空——形式上不如 r1 review 期望，但内容上 r1 修复本身就是选定方案 |
| 跨 M 联动记录 | ⭐⭐⭐⭐ | L971 "跨 M 联动落地"独立段已落 7 项 M 联动 |
| 曾被否决方案保留 | ⭐⭐⭐⭐⭐ | OpenSearch checkpointer 否决（msg 195 §2 列出 5 条理由）保留最完整 |

**风险表补全质量**：**合格**。6 行原风险 + 27 行 r1 已修（含部分跨 M 联动）+ 跨 M 联动独立段——覆盖度足够。轻度冗余（新-5）可在 r2 修整时合并。

### 4.3 r1 review 建议补的 5 行风险是否落到位

| r1 review 建议（L907-913） | M7 风险表 L894-925 落地 |
|--------------------------|------------------------|
| graph invoke 无超时 | ✅ L897 P0-4 已修（含 M8 调用方约束） |
| 6/7 节点缺异常处理 | ✅ L901 P0-8 已修（safe_node 装饰器） |
| query_rewrite 多 rewrite 并查策略未定 | ✅ L905 P1-4 已修（逐条 retrieve + dedupe） |
| graph 版本兼容 | ✅ L918 P2-1 已修（state_version + state.get default） |
| answer_chitchat 节点无实现 | ✅ L899 P0-6 已修（Task 9b） |

**5 行建议全部到位**。

---

## 5. 落地建议

### 5.1 r2 必改（4 项 r1 衍生新问题）

| 优先级 | 项 | 修改 | 工作量 |
|--------|---|------|--------|
| **P1** | 新-1 workflow.py `add_conditional_edges` mapping 缺 `END` 选项 | 在 `route_after_classify` 函数体加注释 "classify_node 已保证 intent ∈ {retrieve, chitchat}，本函数 chitchat 走 answer_chitchat，其他走 query_rewrite"；或改显式 if/elif/else | 0.1h |
| **P1** | 新-2 save_memory 节点 chitchat 路径与 retrieve 路径复用——M10 trace 无法区分 | 在 `save_memory_node` 函数体读 `state.get("intent")` 写到 `state["last_intent"]`；或 plan 跨 M 联动段 L883 加注"M10 区分 retrieve vs chitchat 路径请在 answer / answer_chitchat 节点分别加 trace" | 0.1h |
| **P2** | 新-3 `safe_node` 不放行 `NodeInterrupt` / `GraphRecursionError` | `safe_node` 装饰器加白名单：`except (NodeInterrupt, GraphRecursionError, InvalidUpdateError): raise` | 0.1h |
| **P2** | 新-4 `AnswerSettings.max_chunk_chars=800` 与 M4 ingest chunk_size 对齐 | Files 表 修改段 L202 注释 "max_chunk_chars=800 是 LLM context 窗口保护值；M4 ingest chunk size 需 ≤ 800 char / 约 530 tokens" | 0.1h |

### 5.2 r2 可选（修订记录整合）

| 项 | 修改 | 工作量 |
|---|------|--------|
| 新-5 | 风险表 27 行 r1 已修 与 修订记录 33 行合并：风险表只保留"原 6 行 + r1 已修中影响架构的 6-8 行"，修订记录 33 行删剩一行 summary | 0.2h |

### 5.3 实施顺序建议（按当前 plan）

1. **M7 plan 主体已可执行**——r1 修复 33 项到位、跨 M 12 联动一致、风险表完整
2. **本 review 4 项 r1 衍生新问题可在 implementation 阶段同步修**（每项 0.1h）
3. **M3 KNOWN_NODES 7 节点含 answer_chitchat** ——已确认（r2 已修）—— M7 Task 9b 可直接实施
4. **M8 30s asyncio.wait_for + state.error HTTP 状态码** ——已确认（M8 r1 已修）—— M7 Task 11 L831-833 RED 测试演示调用方模式
5. **M4 ingest chunk_size 同步** ——M7 实施前与 M4 实施者确认 chunk_size ≤ 800 char

### 5.4 跨 M 通知清单（r2 阶段）

| 通知 | 接收方 | 内容 |
|------|--------|------|
| M7 plan 33 项 r1 修复 + 4 项 r1 衍生新问题 | M3 实施者 | 确认 KNOWN_NODES 7 节点含 answer_chitchat；M7 节点函数调 `make_llm("answer_chitchat")` 可用 |
| M7 r1 修复完成 | M8 实施者 | 30s `asyncio.wait_for(graph.ainvoke(...), timeout=30)` 调用方模式 + 读 `state.error` 转 HTTP 状态码（502/500/timeout） |
| M7 r1 修复完成 | M10 实施者 | `save_memory_node` no-op 占位 + M10 用 `NodeInterrupt` 而非改 save_memory；trace name 区分见新-2 |
| M7 r1 修复完成 | M11 实施者 | `graph.invoke(query, thread_id="eval-{n}")` 复用 M7 workflow；M11 runner 重试不冲突 |
| M7 r1 修复完成 | M4 实施者 | `max_chunk_chars=800` 是 M7 拍板的 LLM context 窗口保护值；M4 ingest chunk_size 需 ≤ 800 char |
| M7 r1 修复完成 | M0 实施者 | `apps/rag_v1/infra/docker-compose.yml` 路径确认 + lifespan 注入 `app.state.checkpointer` |

---

## 状态

- **r1 修复到位率**：32/33 完全到位 + 1/33 Tech Stack / 文档承诺到位 = **97% 严格 / 100% 宽口径**
- **r1 衍生新问题**：4 项（P1×2 + P2×2）—— 全部不阻塞实施，可在 implementation 阶段同步修
- **跨 M 一致性**：12 个 M 联动全部对齐，**M3 强阻塞（answer_chitchat）/ M8 强阻塞（30s + state.error）已解除**
- **风险表补全**：6 行原风险 + 27 行 r1 已修 + 跨 M 联动独立段 —— 合格
- **M7 plan r1 整体评价**：**可立即动手实施**——主体设计完整、TDD 节奏保留、修复覆盖率 97%、跨 M 联动一致
- **总体评估**：M7 plan r1 是 RAG V1 路线中**修复密度最高 + 修复质量最好**的 plan。修完 4 项 r1 衍生新问题（总 0.4h）后即可进入 implementation 阶段。**M7 是当前 RAG V1 路线核心骨架 + 修复完成度最高的可实施 plan**。
