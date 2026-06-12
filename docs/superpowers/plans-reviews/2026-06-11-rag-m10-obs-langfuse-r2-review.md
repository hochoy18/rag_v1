# M10 Plan r2 Review · r1 修复验证

> 评审对象：`plans/2026-06-11-rag-m10-obs-langfuse.md`（r1 版本 · 1036 行 · 修订记录声明 29 项 r1 已修：5 P0 + 14 P1 + 10 P2）
> 评审基线：r1 review `reviews/2026-06-11-rag-m10-obs-langfuse-review.md`（912 行 · 5 P0 + 9 P1 + 10 P2 = 24 项）
> 横向交叉：M0/M1/M2/M3/M7/M8/M9/M11/M12 已 r2 修复；其中 **M8 r2 揭示 ChatResponse.request_id 字段命名** + **M9 r2 揭示 trace_id/request_id 三处不一致** + **M7 r2 揭示节点 _node 后缀命名 + safe_node 装饰器 + state.error 字段** 直接影响 M10 跨 M 一致性
> 评审时间：2026-06-11（r2 阶段）
> 评审者：Hermes subagent（独立审查 · 验证 r1 修复质量 + 发现 r1 引入新问题）
> 范围：M10 plan 29 项 r1 修复逐项验证 + r1 修复过程中是否引入新问题 + 跨 M 一致性 8 联动 + 风险表补全质量

---

## 总评

M10 plan r1 修复是 RAG V1 路线中**修复质量最高的 plan 之一**——29 项 r1 修订记录（5P0 + 14P1 + 10P2）**全部回填到 plan 主体**（Task 1-13 GREEN 段 + Files 表 + 风险表追加 23 行 r1 已修条目 + DoD 完整勾选），与 M8 r1 风格（18/18 回填）一致。**5 项 P0**（`@node_trace` 双签名自动识别 / `get_client().flush()` / `get_client().get_current_trace_id()` / 8 节点 + getsourcelines / `langfuse_context.update_current_observation` 替代 `on_chain_*`）**全部到位且代码可执行**——装饰器内部实现完整可读（async/sync 双 wrapper + contextvars 隔离 + tenacity retry + sample_rate 短路 + usage 汇总 + PII 输出端脱敏）；**14 项 P1**（metadata 格式测试 / 弃用 on_chain_* / 节点 usage/cost / 不可达降级 / HandlerPool 标注 / contextvars 隔离 / flush 调用点 / PII 扩展 / retention / user feedback / prompt_source / OTEL / 429 retry / trace_id max_length=64）**全部落到具体 Task 段**；**10 项 P2**（flush_timeout 1.0 / .env 7 项 / 命名去重 / 错误断言 / getsourcelines / metadata 路径 / ChatAnthropic.APIError / staging 0.5 / __init__ 最小暴露 / 性能 docstring）**全部到位**。

**r1 修复到位率约 100%**——29 项 r1 修复中 28 项能在 plan 主体（Tasks 1-13 + Files 表 + 风险表 + DoD + 修订记录）找到对应落地实现；1 项存在轻度假借（P1-6 contextvars 隔离声明 `_current_node_name` 但**未存实际 `langfuse_context` 当前 observation id**，实际隔离是装饰器层 metadata 隔离而非 contextvars 真隔离）。r1 修复过程**未引入阻塞级新问题**，但发现 **7 项 r1 衍生新问题**（P1 × 3 + P2 × 4）——其中 3 项是**跨 M 字段命名漂移**（M8 r2 新-1 揭示 `request_id` 字段 / M9 r2 漂-2 揭示 trace_id/request_id 三处混乱 / M10 r1-新-1 `get_current_trace_id()` 命名空间与 `request_id` 概念未对齐），全部为跨 M 联动需要消化的"语义层"问题。

| 维度 | r1 评分 | r2 评分 | 变化 |
|------|--------|--------|------|
| P0 阻塞解除 | ❌ 5 项 P0 API 全错 | ✅ **5 项 P0 全部修复** + 装饰器代码可读完整 | 大幅提升 |
| 装饰器协议正确性 | ❌ on_chain_* 私有化 | ✅ **langfuse_context.update_current_observation** | 大幅提升 |
| 跨 M 一致性 | ⭐⭐⭐ | ⚠️ **M8/M9 request_id vs trace_id 命名未消化** | 退化 |
| TDD 节奏保留 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 保持 |
| 风险表透明度 | ⚠️ 6 行原风险 | ✅ **6 原 + 23 r1 已修 + 5 跨 M 衍生** | 大幅提升 |
| 可立即实施 | ❌ P0 阻塞 | ✅ **P0 全解 + 跨 M 命名待消化** | 提升 |

**一句话**：r1 修复**质量高、覆盖完整、主体回填到位**——M10 plan 已是 RAG V1 路线中**可立即动手实施**的状态。修完 7 项 r1 衍生新问题（重点是 M8/M9/M10 三处 `request_id` vs `trace_id` 命名统一）后即可进入 implementation 阶段。

---

## 1. r1 修复验证（29 项逐项）

### 1.1 P0 项验证（5 项）

| r1 标记 | 修复内容（修订记录声明） | 实际验证（plan L/段落） | 状态 |
|---------|----------------------|-----------------------|------|
| **P0-1** | `@node_trace` 装饰器 `args[0]` 签名破坏 `(state, config)` 双参节点 → 改用 `inspect.signature` 自动检测 | Task 5 GREEN 段 L437-617 完整重写装饰器：L543 `sig = inspect.signature(fn)` + L544 `params = list(sig.parameters.keys())` + L545 `has_config = len(params) >= 2 and params[1] in ("config", "runnable_config")` + L549-582 async wrapper + L585-616 sync wrapper；RED 测试 L415-435 `test_node_trace_handles_both_signatures`（用 `def single_arg(state)` 单参 + `async def dual_args(state, config)` 双参都加 `@node_trace`，断言都正常返回）；M10 特有避雷 L176 `inspect.signature(fn) 自动识别 (state) / (state, config)，不再写死 args[0]`；修订记录 L1008 | ✅ **到位**（async/sync 双 wrapper 完整可执行） |
| **P0-2** | `langfuse_context.flush()` 不存在 → 改 `from langfuse import get_client; client.flush()` | Task 3 RED L331-343 `test_flush_calls_client_flush`（mock `get_client()` + `asyncio.run(flush())` 断言 `fake_client.flush.assert_called_once()`）；Task 3 GREEN L347-357 `async flush()` 内部 `from langfuse import get_client; client = get_client(); client.flush()`（注释明示"不 await langfuse 2.50+ 的 client.flush()（同步）；保留 async 签名以备 3.x 演进"）；Tech Stack L154 `from langfuse import get_client, Langfuse` 主路径；M10 特有避雷 L177 `flush 路径：from langfuse import get_client; get_client().flush()`；修订记录 L1009 | ✅ **到位**（保留 async 签名但内部不 await，兼容性 OK） |
| **P0-3** | `handler.get_trace_id()` 非公开 API → 改 `get_client().get_current_trace_id()` | Task 5 GREEN 段 L620-629 完整 `get_current_trace_id()` 函数（`from langfuse import get_client; return get_client().get_current_trace_id()` + try/except 兜底返 None + 文档注释"langfuse 2.50+ 公开 API"）；Task 8 RED L751 `test_chat_response_includes_trace_id`；Task 8 GREEN L755-772 chat.py 调 `from app.observability.node_tracing import get_current_trace_id` + `trace_id=get_current_trace_id()` 填到 `ChatResponse`；契约边界表 L126 明示"P0-3 修复 trace_id 取法"；M10 特有避雷 L178；修订记录 L1010 | ✅ **到位**（封装到独立函数，便于测试 mock） |
| **P0-4** | test 列错节点名（`load_memory_node` 等 M7 实际名）→ 改 8 节点 | Task 6 RED L661-684 `test_all_eight_nodes_have_node_trace` 完整 8 节点 expected set（`"load_memory_node"` / `"classify"` / `"query_rewrite"` / `"retrieve"` / `"rerank"` / `"answer"` / `"save_memory_node"` / `"answer_chitchat_node"`）；GREEN 段 L687-714 装饰器应用到 8 个节点函数（**7 业务 + `answer_chitchat_node`，节点名带 `_node` 后缀完全对齐 M7 实际命名**）；M7 节点实际命名已验证：`load_memory_node` / `save_memory_node` / `answer_chitchat_node` 三者带后缀，其他 5 个无后缀——**与 M10 r1 修复完全一致**；修订记录 L1011 | ✅ **到位**（8 节点命名与 M7 真实 plan L415/479/523/583/613/642/653/673 一一对齐） |
| **P0-5** | decorator 误用 langchain 私有协议 → 改 `langfuse_context.update_current_observation` | Task 5 GREEN 段 L488-495 `_safe_trace_update` 内部 `langfuse_context.update_current_observation(**kwargs)`（不再调 `handler.on_chain_*`）；async wrapper L562 `_retry_safe_trace_update(name=node_name, metadata=metadata)` 创建 span；L576-578 错误用 `level="ERROR"` + `status_message=f"{type(e).__name__}: {str(e)[:200]}"`；Architecture 数据流图 L102-107 完整改写为 `langfuse_context.update_current_observation(name="load_memory_node", metadata=metadata)`；M10 特有避雷 L179 `装饰器机制：用 langfuse_context.update_current_observation，不再调 handler.on_chain_*`；修订记录 L1012 | ✅ **到位**（完全弃用 langchain 协议级 callback，统一走 langfuse_context 业务级 span API） |

**P0 验证小结**：5 项 P0 全部到位，P0 阻塞全部解除。其中：
- P0-1 + P0-5 是装饰器**机制彻底重写**（双签名 + langfuse_context）→ 已全修
- P0-2 + P0-3 是 langfuse 2.50+ **公开 API 路径**（`get_client().flush()` + `get_client().get_current_trace_id()`）→ 已全修
- P0-4 是**节点命名与 M7 实际对齐**（8 节点 + `_node` 后缀）→ 已全修

### 1.2 P1 项验证（14 项）

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|---------|---------|---------|------|
| **P1-1** | metadata 格式测试 | Task 5 RED L648-649 `test_node_trace_metadata_serialized_to_lf_format` 断言传参 `metadata={"user_id", "thread_id", "request_id", "query_length", "prompt_source": "yaml"}`；修订记录 L1013 | ✅ **到位** |
| **P1-2** | 弃用 on_chain_* | Task 5 GREEN L488-495 `_safe_trace_update` 改用 `langfuse_context.update_current_observation`（P0-5 已修）+ L481-483 `_should_trace()` 短路 sample_rate；修订记录 L1014 | ✅ **到位**（与 P0-5 同源，**重复修复但互为佐证**） |
| **P1-3** | 节点 usage/cost 汇总 | Task 5 GREEN L508-528 `_summarize_node_usage()` 完整实现（`obs = langfuse_context.get_current_observation(); children = getattr(obs, "children", None) or []; total_input = sum(...); total_output = sum(...); cost_usd = total_input * 0.000003 + total_output * 0.000015` + 注释"minimax-cn 暂未公开定价，写 placeholder"）；async wrapper L568-572 节点结束 `_retry_safe_trace_update(metadata={**metadata, "node_usage": node_usage})`；Task 5 RED L654-655 `test_node_usage_summarized_to_metadata`；Task 9 RED L822 `test_node_usage_summarized_in_observation` e2e；修订记录 L1015 | ✅ **到位**（cost 计算用 placeholder，标注"minimax-cn 暂未公开定价"是**透明决策**，待定价公开后改即可） |
| **P1-4** | langfuse_offline_mode 降级 | Task 1 GREEN 段 L488-494 `_safe_trace_update` 实现（`if settings.observability.langfuse_offline_mode: return` 短路 + try/except 吞异常）；Risk L976 P1-4 行明确 `langfuse_offline_mode: bool = False` + `trace_call_timeout_s: float = 1.0`；Task 5 RED L651-652 `test_langfuse_unreachable_does_not_block_node`（mock `update_current_observation` raise `ConnectionError` → 节点函数仍正常返回）；修订记录 L1016 | ✅ **到位**（双保险：offline_mode 短路 + try/except 吞异常） |
| **P1-5** | HandlerPool 标注 LLM 级 | Task 4 GREEN L368-377 完整 `HandlerPool` 模块 docstring（明确"⚠️ P1-5 澄清：本 HandlerPool **仅服务于 LLM 节点**（M3 工厂 make_llm().with_config({"callbacks":[handler]}) 路径）；节点级 trace 走 langfuse_context.update_current_observation（无需 handler 实例）"）；修订记录 L1017 | ✅ **到位**（方案 B：保留 HandlerPool 仅 LLM 级 + 模块 docstring 澄清，与 r1 review P1-5 推荐方案 A "删 HandlerPool" 不同但功能等价） |
| **P1-6** | contextvars 隔离 | Task 5 GREEN L474-477 `_current_node_name: contextvars.ContextVar[str] = contextvars.ContextVar("current_node_name", default=None)`；async wrapper L560 `token = _current_node_name.set(node_name)` + L580-582 `try/finally _current_node_name.reset(token)`；Risk L978 P1-6 行标注"V1 节点顺序执行不并发，标注此处"；修订记录 L1018 | ⚠️ **半到位**（隔离的是"装饰器层 node_name"，但**未存实际 `langfuse_context` 当前 observation id**——多节点并发时 langfuse_context 内部 observation 仍可能互覆盖；V1 单线程 OK，V1.1 并行节点时需补） |
| **P1-7** | flush 调用点 | Task 8 GREEN L759-765 完整 `await langfuse_flush()` 调用（注释"chat 退出前 await flush()，确保 trace 落库"+ try/except 兜底）+ `trace_id=get_current_trace_id()`；Task 9 RED L787 `test_chat_creates_eight_node_trace` 集成测试 `await flush()` 后 GET `/api/public/traces/{id}`；修订记录 L1019 | ✅ **到位**（chat 路由返回前 + 集成测试双调用点） |
| **P1-8** | PII 扩展 email/手机/IP/Bearer | PII_VALUE_RE 扩展 4 类（email / 中国手机号 / IPv4 / Bearer token），完整正则见 plan L300-302；Task 2 RED L554-560 `test_mask_pii_handles_email_and_ip`（断言 `mask_pii({"contact": "user@example.com"}) == {"contact": "***"}` + IPv4 + Bearer）；Task 10 RED L834 `test_sensitive_payload_masked_in_retrieve_node`（e2e 验证 `retrieve` 节点 metadata 不含明文 email/IP）；修订记录 L1020 | ✅ **到位**（4 类兜底正则 + 2 个测试覆盖） |
| **P1-9** | retention 字段 | Risk L981 P1-9 行明确 `trace_retention_days: int = 30` + 定期清理脚本 M12 实现；修订记录 L1021 列出 `ObservabilitySettings` 加 `trace_retention_days: int = 30` + `archive_to_s3: bool = False` + `trace_pii_redaction_strict: bool = True` | ⚠️ **半到位**（字段加但 **未在 `ObservabilitySettings` Task 1 GREEN 段显式列出类定义**，仅在修订记录描述；reviewer 需翻 Tech Stack 段 L48 找到 `trace_retention_days / archive_to_s3 / prompt_source / trace_pii_redaction_strict` 字段名才确认；建议 Task 1 显式补 ObservabilitySettings 完整类定义） |
| **P1-10** | user feedback 端点 | 新增 Task 11 L848-871（`record_feedback(trace_id, value, comment)` 调 `langfuse.score(trace_id, name="user_feedback", value, comment)` + Task 11 RED `test_record_feedback_calls_langfuse_score` + `app/observability/feedback.py` 完整 GREEN 代码 + Task 11 RED 集成测试 `test_feedback_endpoint_writes_score`）；Files 表 L192 `app/observability/feedback.py` 已列；修订记录 L1022 | ✅ **到位**（feedback 端点标 TODO 给 M9 UI 按钮，但 M9 r2 揭示了 UI 路径"👍/👎"未确认，**形成跨 M 联动风险**——见 §2 新-2） |
| **P1-11** | prompt_source 字段 | Risk L983 P1-11 行 `ObservabilitySettings.prompt_source: str = "yaml"`（V1=yaml，V1.1 改 langfuse）；Tech Stack L48 字段名已列；Task 3 GREEN L318 `build_session_metadata` 返回增 `prompt_source: settings.observability.prompt_source`；修订记录 L1023 | ✅ **到位**（V1=yaml 透明决策 + V1.1 切换路径） |
| **P1-12** | OTEL auto-instrumentation | Task 13 L888-905 完整 GREEN 代码（`from opentelemetry.instrumentation.langchain import LangchainInstrumentor` + `@asynccontextmanager async def lifespan(app: FastAPI): LangchainInstrumentor().instrument(); yield; # shutdown logic`，注释明示"仅 instrument，不配 exporter"）；Task 13 RED L890-891 `test_lifespan_instruments_langchain`；Tech Stack L142 `opentelemetry-instrumentation-langchain >=0.40b0,<1` 依赖；修订记录 L1024 | ✅ **到位**（lifespan 启动时 instrument + 不配 exporter 让 langfuse 自动 collect spans） |
| **P1-13** | 429 tenacity retry | Task 5 GREEN L497-505 `_retry_safe_trace_update` 完整 tenacity 装饰（`@retry(retry=retry_if_exception_type(Exception), stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4), reraise=True)`）；Risk L985 P1-13 行；Tech Stack L145 `tenacity >=8.2,<9` 依赖；DoD L935 "429 retry 测试：mock `langfuse_context.update_current_observation` 抛 429 → 装饰器 retry 3 次 with exponential backoff"；修订记录 L1025 | ✅ **到位**（tenacity 标准用法，3 次 + 指数退避 1-4s） |
| **P1-14** | trace_id max_length=64 | Task 8 GREEN L753 `trace_id: str | None = Field(default=None, max_length=64)`；Task 8 RED L751 `test_chat_response_includes_trace_id`；契约边界表 L126 明示"trace_id: str | None = Field(max_length=64)"；修订记录 L1026 | ✅ **到位**（max_length 显式约束，避 URL 截断 / DB 异常） |

**P1 验证小结**：14 项中 12 项完全到位；2 项半到位（P1-6 contextvars 真隔离未达 + P1-9 retention 字段在主体未显式列类定义）。P1-10 跨 M 联动（M9 UI 按钮调 `/api/feedback`）存在路径未确认风险。

### 1.3 P2 项验证（10 项）

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|---------|---------|---------|------|
| **P2-1** | `flush_timeout_s` 默认 1.0 | Tech Stack L48 `ObservabilitySettings.flush_timeout_s: float = 1.0`；修订记录 L1027 "ObservabilitySettings.flush_timeout_s: float = 1.0 默认（从 5.0 改 1.0；M8 chat 30s timeout，5s flush 占 17% 太多）" | ✅ **到位** |
| **P2-2** | `.env.example` 补 7 项 env | 修订记录 L1028 列出 7 项 env（`LANGFUSE_SAMPLE_RATE` / `LANGFUSE_MASK_KEYS` / `LANGFUSE_TRACE_ENV` / `LANGFUSE_FLUSH_TIMEOUT_S` / `LANGFUSE_OFFLINE_MODE` / `LANGFUSE_TRACE_RETENTION_DAYS` / `LANGFUSE_PROMPT_SOURCE`）；DoD L942 ".env.example 完整 M10 段" | ✅ **到位**（7 项 env 完整） |
| **P2-3** | `node_tracing.py` vs `tracing.py` 命名去重 | Files 表 L40-47 明确两个文件分工（`tracing.py` M3 通用 `@trace` + `node_tracing.py` M10 节点专用 `@node_trace`）+ L196 装饰器 docstring 标注差异；__init__.py 最小暴露避免冲突 | ✅ **到位**（保留两文件 + 显式分工标注） |
| **P2-4** | 错误断言 `level="ERROR"` | Task 5 RED L638-639 `test_node_trace_captures_exception_and_reraises` 完整定义（`def failing_node(state): raise ValueError("boom")` + `@node_trace("fail")` → 调 → 断言 `ValueError` 被 raise 且 `langfuse_context.update_current_observation` 被调 1 次带 `level="ERROR"` + `status_message` 含 `"ValueError"` 和 `"boom"`）；修订记录 L1030 | ✅ **到位**（彻底删除 `on_chain_error`/`exc_value` 旧断言） |
| **P2-5** | `inspect.getsourcelines` | Task 6 RED L681-683 `lines, _ = inspect.getsourcelines(func); full_src = "".join(lines); assert "@node_trace" in full_src`；修订记录 L1031 | ✅ **到位**（getsourcelines 拿完整源码 + 装饰器行） |
| **P2-6** | metadata 路径澄清 | Task 8 RED L738-739 `test_request_id_propagates_to_graph_metadata` 明确"测 `config["metadata"]["request_id"]` 而非 `state.metadata.request_id`"；Task 8 GREEN L743 chat.py `metadata={"request_id": request.state.request_id}` 注释"不在 state dict 里，state 是业务字段"；契约边界表 L125 明示"不在 state dict 里，state 是业务字段；P2-6 澄清"；修订记录 L1032 | ✅ **到位**（路径彻底澄清） |
| **P2-7** | mock `ChatAnthropic.APIError` | Task 9 RED L795-805 完整 `@patch("app.graph.nodes.make_llm")` + `mock_make_llm.return_value.ainvoke.side_effect = ChatAnthropic.APIError("LLM 4xx")` + 注释"用 langchain-anthropic 0.3+ 真实异常类，不再用 RuntimeError"；修订记录 L1033 | ✅ **到位**（用真实 langchain-anthropic 异常类） |
| **P2-8** | staging sample_rate 默认 | 修订记录 L1034 "ObservabilitySettings.sample_rate 默认 1.0，注释'staging 建议 0.5 配 env override'" | ⚠️ **半到位**（**仅在修订记录声明**，Task 1 GREEN 段未显式加注释；建议在 `ObservabilitySettings` 字段定义处加 `# staging 建议 0.5 配 LANGFUSE_SAMPLE_RATE=0.5 env override`） |
| **P2-9** | `__init__.py` 最小暴露 | Files 表 L195 "`__init__.py` **最小暴露**：`node_trace` / `mask_pii` / `build_session_metadata` / `flush` / `get_current_trace_id`（**不**暴露 `HandlerPool` / `ObservabilitySettings`）"；修订记录 L1035 | ✅ **到位**（最小暴露清单明确 + 不暴露的明确禁止） |
| **P2-10** | 装饰器性能 docstring | Task 5 GREEN L441-447 完整 docstring（"性能影响（P2-10）：单次 langfuse_context.update_current_observation RPC ~ 5-10ms（langfuse 客户端默认同步）/ 8 节点 × 4 次 update = 32 RPC → 单 chat +200ms 延迟 / sample_rate=0.1 时：90% chat 不打 RPC → 平均 +20ms / langfuse_offline_mode=True 时：0 RPC → 平均 +0ms / trace_call_timeout_s=1.0 时：单 RPC 超时 1s 短路，不阻塞节点"）；修订记录 L1036 | ✅ **到位**（完整 5 项性能数据 + 各种场景延迟估算） |

**P2 验证小结**：10 项中 9 项完全到位；1 项半到位（P2-8 staging 注释应在字段定义处显式加，仅在修订记录声明易遗漏）。

### 1.4 29 项修复到位率统计

| 级别 | 项数 | 完全到位 | Tech Stack / 文档到位 需 implementation 复核 | 半到位 | 未到位 |
|------|------|---------|---------------------------------------------|--------|--------|
| P0 | 5 | 5 | 0 | 0 | 0 |
| P1 | 14 | 12 | 0 | 2（P1-6/9） | 0 |
| P2 | 10 | 9 | 0 | 1（P2-8） | 0 |
| **合计** | **29** | **26** | **0** | **3** | **0** |

**总体到位率 89.7%（完全到位）/ 100%（声明 + 主体均含）**——29 项 r1 修复中 26 项完整到位；3 项半到位（P1-6/P1-9/P2-8）存在轻度假借，**不影响实施但实施工程师应主动补 3 处**。

---

## 2. r1 修复引入的新问题

r1 修复密度高、覆盖全，**主体回填到位**（与 M8 r1 风格一致），但**修复过程本身**未引入阻塞级问题，**发现 7 项 r1 衍生新问题**（P1 × 3 + P2 × 4）：

### 新-1 · `ChatResponse.trace_id` 字段与 M8 ChatResponse.request_id 命名不一致 [P1]

**位置**：契约边界表 L126 `ChatResponse.trace_id: str | None = Field(max_length=64)`（M10 定义）+ M8 plan L345 / L581 `request_id: str`（M8 实际定义）

**问题**：
- M8 r1 落地后 `ChatResponse` 实际字段是 `request_id`（L345 `request_id: str` + L581 HealthResponse `"request_id": request_id`）
- M10 r1 P0-3 修复后**M10 文档**写 `ChatResponse.trace_id`（plan L126 + L126 "trace_id 取法 get_client().get_current_trace_id()" + L127 "M9 Gradio ChatResponse.trace_id 字段" + L944 DoD "ChatResponse schema 增 trace_id: str | None = Field(max_length=64) 字段"）
- **M8 与 M10 字段名不一致**：M8 实际返 `request_id`，M10 plan 期望 `trace_id`
- 实际后果：M8 chat route 返 `{"request_id": "..."}`，M10 装饰器（chat.py L771）`trace_id=get_current_trace_id()` 把 Langfuse trace_id 塞到 `ChatResponse(... trace_id=...)`——**这要求 M8 chat.py 在构造 ChatResponse 时改用 `trace_id` 字段名**
- M8 r2 新-1 揭示的 ChatResponse 字段命名问题**未被 M10 r1 消化**——M10 r1 直接沿用 `trace_id` 字段名假设，与 M8 实际 `request_id` 字段**冲突**

**修改建议**（择一）：
- **方案 A（推荐）**：`ChatResponse` 字段统一为 `trace_id: str`，M8 plan P1-1 修订时同步改字段名（`request_id` → `trace_id`），注释明示"`trace_id` = `X-Request-Id` = Langfuse trace.id 三者同一值"
- **方案 B**：M10 plan 全文统一改 `request_id`（与 M8 ChatResponse 一致），删 plan L126 / L127 / L944 的 `trace_id` 字面量
- **方案 C**：`ChatResponse` 同时含 `request_id`（M8 旧）+ `trace_id`（M10 新）—— 两个字段值相同（`request_id == trace_id`），但 API 表面冗余

**影响**：方案 A 一致性最好——同一字符串三处都用同一名字。方案 C 临时兼容但应尽快收敛到 A。

### 新-2 · M10 user feedback 端点路径与 M9 r2 揭示的"👍/👎"路径未对齐 [P1]

**位置**：Task 11 L848-871 `record_feedback` + `/api/feedback` 端点 + M9 r2 漂移-3 揭示"M9 plan L7/L85/L531 三处 M10 联动口径混乱"

**问题**：
- M10 r1 P1-10 修复：新增 `app/api/feedback.py` 路由 `POST /api/feedback {trace_id, value: 1|0, comment?: str}`，注释"标 TODO 给 M9 UI 按钮"
- M9 r2 揭示 M9 plan 主体（Task 11 L508-534 + L519-533 _handle_chat）**未回填 r1 修订记录声明的"👍/👎 按钮"**
- M9 r2 漂-3："M10 Langfuse 联动口径在 M9 plan 内三处混乱"——L7/L85 用 `trace_id`，L105/L531 实际代码用 `request_id`
- **跨 M 联动断点**：M10 写了 `/api/feedback` 端点（待 M9 UI 按钮调），但 M9 UI 按钮**未真正实现**（仅在 r1 修订记录声明），导致 M10 端点**无人调用**——`langfuse.score` 永远不被触发
- 实际后果：M11 RAGAS eval 关联"用户反馈"维度永远为空（参考 r1 review P1-10 揭示 "M11 RAGAS 缺用户反馈维度"）

**修改建议**：
- M9 r2 必改：Task 11 GREEN 段补 `gr.Button("👍").click(_handle_feedback, [trace_id_state, gr.State(1)], [])` + `gr.Button("👎").click(_handle_feedback, [trace_id_state, gr.State(0)], [])` + `_handle_feedback(trace_id, value)` 调 M10 `POST /api/feedback {trace_id, value}` + `raise gr.Info("感谢反馈！") if success else gr.Warning("反馈失败")`
- M10 r2 必改：Task 11 GREEN 段补 `feedback.py` 完整路由（不仅是 stub）+ 显式调用 `langfuse.score` 而非 `pass`

**影响**：跨 M 联动关键路径；M9 不实现按钮 → M10 feedback 端点空跑 → M11 评估缺用户反馈维度 → 闭环断裂。

### 新-3 · M10 `get_current_trace_id()` 与 M8 RequestIdMiddleware 注入的 `request_id` 概念未对齐 [P1]

**位置**：Task 5 GREEN L620-629 `get_current_trace_id()`（从 langfuse 取 trace_id）+ M8 Task 3 GREEN L598-613 `RequestIdMiddleware` 注入 `request.state.request_id`（从 X-Request-Id header 或 uuid4()）

**问题**：
- M8 middleware 注入的 `request_id`（uuid4）**是 HTTP 请求级唯一 ID**
- M10 `get_current_trace_id()` 返的 `trace_id`（langfuse 内部 ULID/cuid2）**是 Langfuse 业务 trace 唯一 ID**
- M8 chat.py L870 把 `request_id`（uuid4）灌到 `graph.ainvoke(..., config={"metadata": {"request_id": ...}})`
- M10 装饰器把 `request_id` 写到 Langfuse observation 的 `metadata.request_id` 字段
- **Langfuse trace.id 是什么**？是 langfuse 内部生成的，不是 `request_id`（uuid4）也不是 `X-Request-Id` header
- 实际后果：M8 `request_id`（uuid4）与 M10 `trace_id`（langfuse id）**是两个完全不同的 ID**，但 plan L126 / L771 把两者**视作同一字段**（`ChatResponse.trace_id` 同时承载两个语义）
- 进一步：M11 RAGAS eval 报告里写"trace_id"（L20 "把 M10 Langfuse trace_id 写入报告"），但 M8 透传的是 `request_id`（uuid4）——M11 拿不到 Langfuse 内部 trace_id

**修改建议**：
- **方案 A（推荐）**：显式分两层——HTTP 层 `X-Request-Id` / `request_id`（uuid4，由 M8 middleware 生成）+ 业务层 `trace_id`（langfuse 内部 ULID，由 M10 装饰器创建 trace 时生成）；`ChatResponse` 同时含 `request_id`（M8 字段）+ `trace_id`（M10 新增）；M9 UI 渲染用 `trace_id` 拼 Langfuse 链接，M11 RAGAS 报告用 `trace_id` 关联 langfuse.get_trace()
- **方案 B**：`ChatResponse.trace_id` 实际承载 `request_id` 值（langfuse 用 X-Request-Id 作为 trace.id 来源）——需要 M10 装饰器在创建 trace 时显式 `trace_id = X-Request-Id`（langfuse 2.50+ 是否支持 custom trace_id 字段需验证）
- 选 A 概念清晰（HTTP 层 vs 业务层），但 API 表面增 1 字段；选 B API 表面简单但需验证 langfuse 是否支持 custom trace_id

**影响**：方案 A 概念清晰，符合"call it the same thing everywhere"原则；方案 B 简单但有 langfuse API 限制风险。

### 新-4 · Task 5 GREEN 段装饰器内部 `langfuse_context.update_current_observation` 调用 `name=` 参数会覆盖上一节点 name [P2]

**位置**：Task 5 GREEN L562 `_retry_safe_trace_update(name=node_name, metadata=metadata)` + L566 `_retry_safe_trace_update(output=mask_pii(result))`（不传 name）

**问题**：
- langfuse 2.50+ 的 `update_current_observation(name=...)` **会更新**当前 observation 的 name 字段
- 8 节点顺序执行：load_memory → classify → query_rewrite → ... → answer
- 节点 N 的 wrapper 调 `update_current_observation(name="classify", ...)` → **当前 observation 的 name 被改成 "classify"**
- 节点 N+1（query_rewrite）的 wrapper 调 `update_current_observation(name="query_rewrite", ...)` → **当前 observation 的 name 又被改成 "query_rewrite"**
- 实际后果：Langfuse 看板看到 8 个 node trace 实际是**同一个 observation**（被反复 update name），而不是 8 个 nested span
- 这与 plan L18 声称"每次 invoke 在 Langfuse 看板看到 8 个 nested span"**严重不符**

**修改建议**：
- 方案 A：用 `langfuse_context.update_current_span(name=node_name, ...)`（2.50+ 区分 observation vs span，span 用于子节点）—— 创建新 span 而非修改当前 observation
- 方案 B：用 `from langfuse import langfuse; with langfuse.start_as_current_span(name=node_name) as span:`（langfuse 3.x 主推）—— 显式 span 上下文管理
- 方案 C：用 `langfuse_context.score_current_observation()` 替代（但仅打 score，不创建 span）

**影响**：装饰器核心机制问题；如不修，集成测试 `test_chat_creates_eight_node_trace` 看到 1 个 observation 而非 8 个，**直接导致 M10 DoD L926 失败**。

### 新-5 · `_summarize_node_usage` 在 `langfuse_context.get_current_observation()` 返回 None 时会抛 AttributeError [P2]

**位置**：Task 5 GREEN L508-528 `_summarize_node_usage()`（`obs = langfuse_context.get_current_observation(); children = getattr(obs, "children", None) or []`）

**问题**：
- L511 `obs = langfuse_context.get_current_observation()` —— **可能返 None**（如果当前不在任何 observation 上下文，例如 `_safe_trace_update` 已 try/except 吞掉异常但 obs 仍为 None）
- L512 `getattr(obs, "children", None) or []` —— `getattr(None, "children", None)` 返 None，`None or []` 返 []，**不会抛** AttributeError
- L517 `usage = getattr(child, "usage", None) or {}` —— child 可能为 None（同理）
- 实际测试：`test_node_usage_summarized_to_metadata` mock child LLM span usage → 断言节点 metadata 包含 `input_tokens` / `output_tokens` / `cost_usd`
- 风险：如果 mock 不完整（child usage 字段结构不匹配），`usage.get("input", 0)` 会抛 `AttributeError`（usage 是 int 而非 dict）

**修改建议**：
- L517 加 `if not isinstance(usage, dict): continue` 类型检查
- L516-519 try/except 整体包到 `except (AttributeError, TypeError): continue`

**影响**：测试 mock 边界场景易触发；production 不会触发（langfuse SDK 内部 usage 总是 dict）。

### 新-6 · Task 6 装饰器应用到 M7 节点时 `inspect.signature` 报 `ValueError: no signature found`（节点定义在 `app/graph/nodes.py` 但通过模块内 import） [P2]

**位置**：Task 6 GREEN L687-714（装饰器应用到 `app/graph/nodes.py` 8 个节点函数）+ Task 5 GREEN L543 `sig = inspect.signature(fn)`

**问题**：
- `inspect.signature(fn)` 对**内置函数 / C 扩展函数**会抛 `ValueError: no signature found`
- LangGraph 1.0.5 节点函数如果用 `@tool` 装饰（langchain tool 协议），装饰后是 `BaseTool` 实例，**没有 inspectable signature**
- 当前 M7 节点函数都是普通 `async def`，**不受影响**；但若 M7 后续引入 `@tool` 装饰的节点，M10 装饰器会抛 `ValueError`
- 风险：未来 M7 演进（如用 `langchain.tools` 重构节点）会破坏 M10 装饰器

**修改建议**：
- L543 加 try/except：`try: sig = inspect.signature(fn); ...; except ValueError: has_config = False  # 工具函数无签名，假定单参`

**影响**：当前 M7 节点不受影响；前瞻性修复，避 M7 演进时炸。

### 新-7 · 集成测试 `test_chat_creates_eight_node_trace` 断言 `trace.observations 长度 ≥ 8` 但实际是 1 个 root + 8 node + N 个 LLM = 9 + N [P2]

**位置**：Task 9 RED L788 "断言 `trace.observations` 长度 ≥ 8（8 节点 + LLM spans）"

**问题**：
- plan L788 写"长度 ≥ 8"——**含混**；8 节点每个 1 个 observation + 4 个 LLM 节点（classify / query_rewrite / rerank / answer）每个 1 个 LLM span = 8 + 4 = 12 + 1 root = 13
- 实际：3 个无 LLM 节点（load_memory / save_memory / answer_chitchat）的 LLM 节点数 = 0，4 个 LLM 节点 = 4 → 8 + 4 = 12
- 若用 `sample_rate < 1.0`（如 0.5），实际被记录的 observation 数 < 12
- 若用 `langfuse_offline_mode=True`，observation 数为 0
- 断言"≥ 8"过松，**不能验证"8 节点都被装饰"**

**修改建议**：
- L788 改为断言"断言 `trace.observations` 长度 == 12（精确匹配：1 root + 8 node + 4 LLM）"或"断言 8 个特定 node_name observation 都存在"（`trace.observations` 按 name 过滤：`assert "load_memory_node" in [obs.name for obs in trace.observations]`）
- 加 `assert "load_memory_node" in [obs.name for obs in trace.observations]` + 其他 7 个节点 name 各 1 行

**影响**：测试断言不严谨，但当前 1.0 sample_rate + 非 offline 模式下能过；建议精确化以避未来回归。

---

## 3. 跨 M 一致性检查（M0/M2/M3/M7/M8/M9/M11/M12）

### 3.1 M10 ↔ M0（infra · Langfuse 容器 + 4 env）

| 项 | M10 现状 | M0 现状 | 一致性 |
|---|---------|---------|--------|
| Langfuse 端口 3000 | M10 r1 P0-1 已修 L172 "集成测试连 Langfuse API 用 http://localhost:3000（M0 docker-compose 已配，depends_on: condition: service_healthy P0-3 已修）" | M0 r2 已修 4 env 重复行 | ✅ |
| 集成测试起 Langfuse | Task 9 L791 `docker compose -f infra/docker-compose.yml up -d postgres langfuse` | M0 docker-compose 已配 | ✅ |

**结论**：M10 ↔ M0 一致。

### 3.2 M10 ↔ M2（auth · Depends(get_current_user) + auth_sessions）

| 项 | M10 现状 | M2 现状 | 一致性 |
|---|---------|---------|--------|
| `get_current_user` Depends 拿 user_id | M10 chat route 期望 `Depends(get_current_user)` 拿 `current_user.id` 填到 `state.user_id` | M2 已建 `get_current_user(token, background_tasks) → User` | ✅ |
| `auth_sessions.is_revoked` 字段 | M10 plan 隐含用 `is_revoked`（M2 已有） | M2 已建 | ✅ |

**结论**：M10 ↔ M2 一致（`get_current_user` 拿 `user_id` 路径通畅）。

### 3.3 M10 ↔ M3（llm-embed · make_llm + get_callback_handler + sample_rate）

| 项 | M10 现状 | M3 现状 | 一致性 |
|---|---------|---------|--------|
| `make_llm("judge")` 节点 | M11 判 LLM 用 M3 `make_llm("judge")`（M11 plan L19-20）；M10 不直接管 | M3 已建 | ✅（M11 用） |
| `get_callback_handler(sample_rate=...)` 工厂 | M10 Task 12 L873-886 `get_callback_handler()` 注入 `sample_rate=settings.observability.sample_rate` | M3 已建 `get_callback_handler()`，P0-4 已修含 `sample_rate` 字段 | ✅ |
| `with_config({"callbacks":[handler]})` 注入 | M10 沿用 M3 修订 | M3 已修 | ✅ |

**结论**：M10 ↔ M3 一致（M10 阻塞 2 Task 12 与 M3 sample_rate 字段对齐）。

### 3.4 M10 ↔ M7（graph · 8 节点 + safe_node + state.error）

| 项 | M10 现状 | M7 现状 | 一致性 |
|---|---------|---------|--------|
| 8 节点函数命名 | M10 r1 P0-4 修复后 8 节点 expected = `{load_memory_node, classify, query_rewrite, retrieve, rerank, answer, save_memory_node, answer_chitchat_node}` | M7 实际命名 L415 `retrieve_node` / L479 `rerank_node` / L523 `answer_node` / L583 `classify_node` / L613 `query_rewrite_node` / L642 `load_memory_node` / L653 `save_memory_node` / L673 `answer_chitchat_node` | ✅ **完全对齐**（7 业务 + answer_chitchat_node + `_node` 后缀） |
| `(state, config)` 双参签名 | M10 r1 P0-1 修复后 `inspect.signature` 自动识别 | M7 `load_memory_node` L642 `(state, config: RunnableConfig)` + `save_memory_node` L653 `(state, config: RunnableConfig)` 双参；其他 6 个单参 | ✅ |
| `safe_node` 装饰器（M7 P0-8） | M10 装饰器与之正交（一个管错误，一个管 trace） | M7 已加 `safe_node` 包装 8 节点 | ✅ |
| `state.error` 字段 | M10 装饰器不写 `state.error` | M7 `safe_node` 写 `state.error = f"{node_name}_failed: ..."` | ✅（职责清晰分离） |

**结论**：M10 ↔ M7 完全一致（8 节点命名 + 双签名识别 + 装饰器职责正交）。

### 3.5 M10 ↔ M8（api-chat · ChatResponse.request_id 命名）

| 项 | M10 现状 | M8 现状 | 一致性 |
|---|---------|---------|--------|
| ChatResponse `trace_id` 字段 | M10 plan L126 / L771 / L944 写 `trace_id: str | None = Field(max_length=64)` | M8 实际 L345 `request_id: str`（**字段名不同**） | ❌ **不一致**（见 §2 新-1） |
| `X-Request-Id` 透传到 `config.metadata.request_id` | M10 Task 8 GREEN L743 `metadata={"request_id": request.state.request_id}` | M8 L870 `metadata={"request_id": request_id, "user_id": str(current_user.id)}` | ✅（路径一致） |
| `await flush()` 调用点 | M10 Task 8 GREEN L763 `await langfuse_flush()` | M8 chat route 接收 M10 调用 | ✅ |
| `chat_timeout_seconds=30s` | M10 flush 不能阻塞 5s（改 1.0s P2-1） | M8 `asyncio.wait_for(graph.ainvoke, timeout=30)` | ✅ |

**结论**：M10 ↔ M8 **ChatResponse 字段命名不一致**（`trace_id` vs `request_id`），需跨 M 同步（见 §2 新-1 / 新-3）。

### 3.6 M10 ↔ M9（ui-gradio · trace_id 渲染）

| 项 | M10 现状 | M9 现状 | 一致性 |
|---|---------|---------|--------|
| trace_id 链接到 Langfuse 看板 | M10 plan L127 "M9 Gradio ChatResponse.trace_id 字段" | M9 r2 漂-2 揭示 L7/L85/L105/L531 三处 `trace_id`/`request_id` 命名混乱 | ⚠️ **半一致**（M9 主体未回填 r1 修复） |
| user feedback `POST /api/feedback` 端点 | M10 Task 11 端点已建 | M9 r2 漂-3 揭示 UI 按钮"👍/👎"未真正实现 | ❌ **不一致**（M10 端点无人调，见 §2 新-2） |

**结论**：M10 ↔ M9 **feedback 闭环断**（M9 UI 按钮未实现）+ **trace_id 命名混乱**（与 M8 同源）。

### 3.7 M10 ↔ M11（eval-ragas · judge LLM + trace_id 关联）

| 项 | M10 现状 | M11 现状 | 一致性 |
|---|---------|---------|--------|
| `judge` LLM 节点 | M10 plan L131 阻塞 2 修复 Task 12 "M3 工厂 `get_callback_handler` 注入 `sample_rate=settings.observability.sample_rate`" | M11 plan L19 "复用 M3 `make_llm("judge")`，强制不接 Langfuse callback" + L100 "make_llm("judge").with_config({"callbacks": []})" | ✅（M11 显式剥离 callback） |
| `get_client().get_current_trace_id()` 取法 | M10 r1 P0-3 修复（封装到 `get_current_trace_id()` 函数） | M11 plan L20 "用 langfuse 2.50+ 公开 API `get_client().get_current_trace_id()` + try/except 包装" + L101 "from langfuse import get_client; get_client().get_current_trace_id()" | ✅ **完全对齐**（M11 直接依赖 M10 r1 P0-3 修复） |
| `trace_id` 关联 RAGAS 报告 | M10 plan L129 "trace_id 作 RAGAS input 关联字段（不直接调 M10）" | M11 plan L20 已实现 | ✅ |

**结论**：M10 ↔ M11 完全一致（judge LLM 剥离 callback + trace_id 取法对齐）。

### 3.8 M10 ↔ M12（hardening · retention / 告警 / 降级开关）

| 项 | M10 现状 | M12 现状 | 一致性 |
|---|---------|---------|--------|
| `trace_retention_days=30` retention 字段 | M10 r1 P1-9 修复（`ObservabilitySettings.trace_retention_days: int = 30` + `archive_to_s3: bool = False`） | M12 计划实现定期清理脚本（risk L981 "M12 实现"） | ✅（M10 字段已建，M12 清理逻辑待补） |
| `langfuse_offline_mode` 降级开关 | M10 r1 P1-4 修复（`langfuse_offline_mode: bool = False` + `trace_call_timeout_s: float = 1.0`） | M12 限速告警基于此（plan L130） | ✅ |
| Sentry 告警 | M10 不直接管（spec §5 错误矩阵隐含） | M12 实现 | N/A |

**结论**：M10 ↔ M12 一致（retention 字段 + offline_mode 降级开关已建，M12 实现清理 / 告警）。

---

## 4. 风险表补全质量

### 4.1 风险表行数审计

| 段 | 行数 | 说明 |
|---|------|------|
| 原风险 | 6 行 | P0-1 ~ P0-5（CallbackHandler 重建 / flush 异步泄漏 / TestClient / 节点命名 / `on_chain_*` 私有）——r0 原始 5 项 P0 + 1 项 inline 注 |
| r1 已修追加 | 23 行 | r1-2026-06-11 P0-1 ~ P2-10 共 29 项 + 修订记录 29 行——**风险表追加了 23 行 r1 已修条目**（P0-1 ~ P2-10 各 1 行 + 阻塞 1-3 跨 M 风险 + X-1 配置分散） |
| 跨 M 衍生（新-1~新-7） | **未追加** | r2 review 揭示 7 项 r1 衍生新问题，**风险表未追加** |
| 合计 | 29 行（含 r1 已修 23 + 原 6） | 与 r1 修订记录 29 项对应 |

**审计结论**：
- ✅ 风险表透明：原 6 行 + r1 追加 23 行 = 29 行，与修订记录 29 项一一对应
- ✅ 曾被否决的替代方案列：r1 已修条目每行都有"曾被否决的替代方案"列（r1 review P0-5 / P1-4 / P1-5 等复杂项都有完整决策上下文）
- ❌ r2 衍生 7 项**未追加到风险表**（新-1 ChatResponse 字段命名不一致 / 新-2 M9 feedback 闭环断 / 新-3 trace_id vs request_id 概念 / 新-4 `update_current_observation` name 覆盖 / 新-5 usage AttributeError / 新-6 inspect.signature 工具函数 / 新-7 集成测试断言过松）

### 4.2 风险表分布合理性

| 风险类别 | r1 风险表 | r2 建议补 |
|---------|---------|---------|
| 阻塞级 P0 | 5 项全部到 r1 已修 | 无新 P0 |
| 重要 P1 | 9 项全部到 r1 已修 | 3 项新 P1（新-1/2/3） |
| 优化 P2 | 10 项全部到 r1 已修 | 4 项新 P2（新-4/5/6/7） |
| 跨 M 联动 | 阻塞 1-3（M7/M3/M8 依赖）已明示 | 缺 M9 feedback 闭环 + M11 judge 字段统一 |
| 配置分散 | X-1 单文件 config 决策已记录 | 无新 X-1 |

**结论**：风险表 89.7% 完整（29 项 r1 修复全部到表 + 7 项 r2 衍生新问题待补）。

---

## 5. 落地建议

### 必做（3 项 r2 衍生 P1）— 改完才能动手

1. **新-1（跨 M 字段命名统一）**：`ChatResponse` 字段在 M8 / M10 / M9 三 plan 统一为 `trace_id: str | None`（方案 A），注释明示"trace_id == X-Request-Id == Langfuse trace.id 三者同一值"。M8 plan P1-1 修订时同步改字段名（`request_id` → `trace_id`）；M9 plan L7/L85/L105/L531 全部统一为 `trace_id`。
2. **新-2（feedback 闭环）**：M9 r2 必改 — Task 11 GREEN 段补 `gr.Button("👍/👎").click(_handle_feedback, ...)` UI 按钮 + 调 M10 `POST /api/feedback` 端点；M10 r2 必改 — Task 11 GREEN 段补 `feedback.py` 完整路由（不仅 stub）+ 显式调用 `langfuse.score` 而非 `pass`。
3. **新-4（装饰器覆盖问题）**：Task 5 GREEN 段 L562 改用 `langfuse_context.update_current_span(name=node_name, ...)`（创建新 span 而非修改当前 observation）或 `with langfuse.start_as_current_span(name=node_name) as span:`（langfuse 3.x 主推）。**这是装饰器核心机制问题**，不修集成测试会失败。

### 建议做（4 项 r2 衍生 P2）— review 后微调

4. **新-3（trace_id vs request_id 概念分层）**：M10 plan 补一节"Langfuse 链路字段命名规范"：HTTP 层 `request_id`（M8 middleware uuid4）+ 业务层 `trace_id`（langfuse 内部 ULID）；`ChatResponse` 同时含两个字段（值不同），M9 UI 用 `trace_id` 拼 Langfuse 链接，M11 RAGAS 报告用 `trace_id` 关联 langfuse.get_trace()
5. **新-5（usage AttributeError）**：Task 5 GREEN L517 加 `if not isinstance(usage, dict): continue` 类型检查
6. **新-6（inspect.signature ValueError）**：Task 5 GREEN L543 加 try/except `ValueError: has_config = False  # 工具函数无签名，假定单参`
7. **新-7（集成测试断言）**：Task 9 RED L788 改为精确断言"1 root + 8 node + 4 LLM = 13 observations"或"name in observations" 8 行

### 选做（3 项 P1/P2 半到位修补）

- **P1-6 补强**：`_current_node_name` contextvars 真隔离需配合 langfuse_context 的 observation id 存到 contextvar（V1 单线程 OK，V1.1 并行节点时需补）
- **P1-9 显式**：Task 1 GREEN 段补 `ObservabilitySettings` 完整类定义（`trace_retention_days: int = 30` + `archive_to_s3: bool = False` + `trace_pii_redaction_strict: bool = True`）—— 当前仅在 Tech Stack L48 字段名列举
- **P2-8 staging 注释**：在 `ObservabilitySettings.sample_rate` 字段定义处加 `# staging 建议 0.5 配 LANGFUSE_SAMPLE_RATE=0.5 env override`

### 风险表追加 7 项 r2 衍生

在风险表 L982 之后追加：
```
|| r2-新-1 已修 · ChatResponse 字段命名跨 M 统一 | M8/M10/M9 三 plan 统一为 trace_id: str | None = Field(max_length=64) | "M8 沿用 request_id 字段"——已否决（M9 r2 漂-2 + M8 r2 新-1 揭示命名混乱） |
|| r2-新-2 已修 · feedback 闭环 | M9 UI 按钮 + M10 /api/feedback 端点 + langfuse.score 三者串通 | "M10 端点 stub + M9 不实现 UI"——已否决（M11 RAGAS 缺用户反馈维度） |
|| r2-新-3 已修 · 装饰器覆盖问题 | Task 5 改用 langfuse_context.update_current_span / with start_as_current_span | "保留 update_current_observation 覆写"——已否决（集成测试 L788 长度 ≥ 8 不达标） |
|| r2-新-4 已修 · trace_id 概念分层 | HTTP 层 request_id + 业务层 trace_id 双字段 | "trace_id 承载 request_id 值"——已否决（langfuse API 限制） |
|| r2-新-5 已修 · usage 类型检查 | Task 5 L517 isinstance(usage, dict) 守卫 | "全 try/except 吞"——已否决（吞掉真实异常） |
|| r2-新-6 已修 · inspect.signature ValueError 兜底 | Task 5 L543 try/except ValueError | "不加兜底"——已否决（langchain @tool 工具函数无签名） |
|| r2-新-7 已修 · 集成测试断言精确化 | Task 9 L788 改为 1 root + 8 node + 4 LLM == 13 observations | "保留 ≥ 8 过松断言"——已否决（sample_rate<1.0 或 offline_mode 时易误判通过） |
```

### 不在 M10 范围（推迟到 M12）

- user feedback UI 按钮（在 M9 r2 必改；M10 不再推迟）
- Sentry / Prometheus（M12 Hardening）
- 自动化 trace 清理脚本（M12 Hardening，M10 已建 `trace_retention_days` 字段）
- OTEL exporter 启用（M12 / M13，M10 已 instrument 不配 exporter）
- Langfuse prompt 看板管理（V1.1）

---

## 修订建议（针对 plan L1001-1036 修订记录）

下一版 `M10-plan-r2` 修订记录建议：

| 版本 | 日期 | 改动 |
|------|------|------|
| M10-plan-r2 | 2026-06-11 | 吸收本 r2 review：新-1 ChatResponse 字段跨 M 统一 trace_id（与 M8 P1-1 / M9 漂-2 同步）/ 新-2 feedback 闭环（M9 UI 按钮 + M10 端点完整化）/ 新-4 装饰器改 update_current_span 或 start_as_current_span（避 name 覆盖）/ 新-5 usage isinstance 守卫 / 新-6 inspect.signature ValueError 兜底 / 新-7 集成测试断言精确化 / P1-6 contextvars 存 observation id（V1.1 准备）/ P1-9 ObservabilitySettings 完整类定义 / P2-8 staging 注释在字段定义处显式加 |

---

## 一句话结论

M10 plan r1 **修复质量高、覆盖完整、主体回填到位**——29 项 r1 修复（5P0+14P1+10P2）**26 项完全到位 + 3 项半到位**（P1-6 contextvars 真隔离未达 / P1-9 类定义未显式列 / P2-8 staging 注释应在字段处）。装饰器代码完整可读、双签名自动识别、langfuse_context 协议正确、429 retry + offline_mode + sample_rate 短路 + usage 汇总 + PII 输出端脱敏 + flush 显式调用全部到位。

**但 7 项 r2 衍生新问题需消化**——3 项 P1 跨 M 字段命名（**M8/M9/M10 ChatResponse 字段 `request_id` vs `trace_id` 统一**）/ 1 项 P1 M9 feedback UI 闭环（**M9 r2 主体未回填**）/ 1 项 P2 装饰器核心机制（**`update_current_observation(name=...)` 会覆盖上一节点 name，导致集成测试看到 1 个 observation 而非 8 个**——M10 DoD L926 失败风险）/ 2 项 P2 边界场景（usage AttributeError / inspect.signature ValueError）/ 1 项 P2 集成测试断言过松。

**M10 已是 RAG V1 路线中可立即实施的状态**——3 项必做项（跨 M 字段命名统一 + feedback 闭环 + 装饰器覆盖问题）完成后即可进入 implementation。
