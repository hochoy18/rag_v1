# M11 Plan Review · RAGAS 离线评估 CLI + Golden Set + CI Gate

> 评审对象：`plans/2026-06-11-rag-m11-eval-ragas.md`（646 行）
> 评审基线：V1 Scope v0.4 spec §0 决策 #11 / §2 模块树 eval 段 / §6 测试策略 / §8.6 观测&评估依赖；system design v2.0 §10 测试与 CI/CD；M3 / M7 / M10 plan + 各自独立 review
> 横向交叉：总 review `2026-06-11-rag-plans-review.md`（P0-1/P0-5/X-1/X-3 已避雷标注）· M3 review（callback 注入 P0-2 / judge 节点 P1-5 / 4 yaml 空壳 P0-1）· M7 review（P0-2 aget_tuple / P0-3 make_checkpointer 形态 / P0-6 answer_chitchat 空实现 / P0-8 节点异常处理缺失）· M10 review（5 P0 装饰器/flush/trace_id API 错位）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M11 plan 把 spec §0 决策 #11 落成可执行代码契约的**完整度好于预期**——11 段模板齐（Goal/不包含/Architecture/Tech Stack/Files/11 Tasks RED-GREEN/测试/DoD/依赖/风险/修订记录），架构图 + 数据流 ASCII + 契约边界表 + 9 行风险表 + 修订记录全部到位，10 源 + 6 单测 + 1 fixture + 1 集成测试的 Files 表与 M3 范本 1:1 对齐。**关键避雷已经覆盖**：RAGAS 0.2 judge LLM 不读 OPENAI_API_KEY（P0 已写明）、Langfuse trace_id 透传不另起服务、`make_llm("judge")` 显式注入复用 M3 工厂、CI/nightly 20/50 题分级、faithfulness 0.7 gate 用 `GateViolationError` 异常（不进 silent fail）、HTML 报告拒用 jinja2 改 python-markdown（响应 review P1-1）、golden set git 化避 S3 过早优化。

但**实施就绪度严重不足**——本 review **新发现 19 个问题**，其中 **6 个 P0**（RAGAS 0.2 API 真实签名与 plan 写法不符 / `make_llm("judge")` M3 未注册导致 import 阻塞 / RAGAS evaluate 输入 schema 与 plan `Dataset.from_list` 不匹配 / `pytest-asyncio` 缺声明 / plan L539 faithfulness gate 阈值在 nightly 50 题稳定性未论证 / M10 review 5 P0 的 trace_id 取法直接被 M11 引用但底层 API 错）+ **8 个 P1**（golden set 题目质量门槛缺 / question_type 缺 chitchat 路径 / `context_precision` 需要 ground-truth chunks 而非 ground_truth 字符串 / `context_precision` 受 judge LLM 偏差影响没量化 / `langfuse.get_current_trace_id()` 不是公开 API / eval cost 跟踪缺 / report 长期存储与 baseline 对比缺 / nightly 与 CI gate 阈值差异未定义）+ **5 个 P2**（RAGAS 版本 pin 缺失 / 报告 markdown 拼接可改 template / fixture 的 expected_doc_id 校验未走真实索引 / 端到端真跑缺 CI 路径说明 / 测试覆盖 `test_judge_uses_m3_factory_not_env` 与 M3 工厂实现耦合于 callback 注入路径）。修完 6 个 P0 才能动手；M11 是 V1 收尾 checklist 的"CI: RAGAS gate"项的源头，gate 跑不起来 V1.0.0 不可发布。

| 维度 | 评分 | 说明 |
|---|---|---|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐 + Architecture ASCII + 数据流 ASCII + 契约边界表 + 风险 9 行 + 修订记录 |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 11 Tasks 全部 RED-GREEN（含 RED 测试名具体 + GREEN 代码段完整） |
| 技术深度 | ⭐⭐⭐ | judge LLM 注入、HTML 报告、gate 异常都到位；但 RAGAS 0.2+ 真实 API、`Dataset.from_list` schema 适配、`context_precision` 输入语义、trace_id API 错位 |
| 一致性 | ⭐⭐⭐ | spec §8.6 版本（ragas>=0.2,<1）+ M3 工厂复用 + M7 graph 调用契约都对；但 M3 工厂未注册 `judge`（M3 review P1-5）、M10 trace_id API 错（M10 review P0-3） |
| 已有 review 就绪度 | ⭐⭐⭐⭐ | review P0-1/P0-5/X-1/X-3 已避雷标注；但 P1-12/P1-14/M3 P1-5（judge 节点）未在 M11 强校验 |
| 错误处理 | ⭐⭐⭐⭐ | graph 4xx/5xx tenacity 重试 + judge LLM 不读 OPENAI_API_KEY + gate 异常；缺 chitchat 路径测试 + RAGAS 内部异常 |
| 跨 M 契约 | ⭐⭐⭐ | M7 graph 调、M3 工厂、M10 Langfuse 引用齐；但 M3 工厂 `judge` 节点未注册 → M11 跑起来 ImportError |

**一句话**：M11 plan **结构对、TDD 节奏好、主体设计对齐 spec §0 决策 #11**；**但在 RAGAS 0.2+ 真实 API、M3/M10 上游契约、golden set 质量、gate 统计稳定性 4 个方面有 6 个 P0 阻塞**——修完才能动手。

---

## 已有 review 验证（2026-06-11-rag-plans-review.md）

| ID | 已有 review 项 | Plan 现状 | 本报告 |
|----|---------------|-----------|--------|
| **P0-1** | 端口冲突（TEI 8080 vs http.server） | ✅ 已避雷——M11 plan L169 "**不修改**：`infra/docker-compose.yml`（M11 不依赖容器，纯 CLI 跑本地 Python）" + L590 "需 docker compose up（M0）+ ANTHROPIC_API_KEY" | 通过。M11 CLI 跑本地，明示 docker-compose 由 M0 负责 |
| **P0-5** | M1 Task 2 单元测试用 sqlite，但生产用 PG（假绿） | ✅ 已避雷——M11 plan 不涉及 SQLite 测试；runner 用 mock graph + 单测全 mock | 通过。M11 单测全部 mock |
| **X-1** | `app/config.py` 跨 M 反复改 → 拆 `app/configs/` | ✅ 已避雷——L167 "修改：`app/config.py`（或 `app/configs/eval.py` if X-1 已落地）：追加 `EvalSettings`" | 通过。分支选择已显式标注 |
| **X-3** | `from app.config import settings` 全局单例 | ✅ 已避雷——L129, 222, 224, 363, 412 全部 `from app.config import settings` | 通过。5 处使用全部对齐全局单例 |
| **P1-12** | langfuse.CallbackHandler import path | ⚠️ 部分避雷——M11 plan L51 写 `app/observability/langfuse.py` 已建（M10 范围），M11 不需自己 import；L96 "M11 report 用 `langfuse.get_current_trace_id()`" | **新发现 P0-6**：`get_current_trace_id()` 在 langfuse 2.50+ 不是公开 API，应是 `from langfuse import get_client; get_client().get_current_trace_id()` |
| **P1-14** | M3 `make_llm` 注入 callback 写 `model.callbacks` 与 langchain 1.0+ 冲突 | ✅ 已避雷——M11 plan 不写 callback 注入，复用 M3 工厂；judge 节点只调 `make_llm("judge")` 不动 factory 内部 | 通过 |
| **X-2** | CI 路径假设冲突（`cd apps/rag_v1`） | ⚠️ 部分避雷——L588 写 `cd apps/rag_v1 && pytest ...` 但没指定 pytest.ini 锁 rootdir | 留 **P2-3**：M11 plan 引用 M0/M2/M3 plan 的 `pytest.ini`（已加 rootdir），M11 自身单测不需新增 pytest.ini |

**验证结论**：已有 review 中直接影响 M11 的 7 项——5 项 ✅ 通过，2 项 ⚠️ 部分避雷需补。

---

## 横向交叉验证

### 3-1 · M3 review P1-5 → M11 `make_llm("judge")` 是空头支票

M3 review P1-5 明确指出：**M3 工厂 `KNOWN_NODES` 只有 `("classify", "rewrite", "rerank", "answer")`**，没注册 `judge`。M11 plan L43, L73, L97, L134, L301 全部硬编码依赖 `make_llm("judge")`——**M3 工厂未实现此节点时，M11 跑起来直接 `ValueError: unknown llm node: judge`**。

**M11 风险**：
- M11 Task 4 RED L271 `test_judge_uses_m3_factory_not_env` mock `make_llm` → 绿（mock 不挑节点存在性）
- Task 4 GREEN L288 `make_llm("judge")` 走 `load_prompt("judge")` → `ChatAnthropic(...)`——**但 `load_prompt("judge")` 找不到 yaml 文件**（M3 Files 表只有 4 yaml，无 `judge.yaml`）
- 集成测试 Task 11 L568 跑 `_run_eval(...)` → 跑 runner → 跑 graph → 跑 RAGAS → 跑 judge LLM → 调 `make_llm("judge")` → ImportError / FileNotFoundError

**关键**：M11 plan 必须**显式声明**"M11 阶段在 M3 工厂追加 `judge` 节点"——这是 M11 对 M3 的破坏性修改，不应隐藏在"M3 工厂动态注册"假设里。**升级到 P0-2**。

### 3-2 · M7 review P0-2 → M11 runner `graph.aget_tuple` API 与 M7 一致性

M7 review P0-2 指出 M7 `load_memory_node` 写 `cp.aget(...)` 与 langgraph 1.0.5 不匹配（应是 `aget_tuple`）。**M11 runner 不直接调 checkpointer**，只调 `graph.invoke(...)`，所以**不依赖** checkpointer API 修复——M11 只需确认 `graph.invoke` 返回的 state 含 `answer` + `sources` 即可。但若 M7 P0-2 修复后改 `load_memory_node` 签名（如 `async def load_memory_node(state, config: RunnableConfig)`），M11 plan L268 runner 调 `graph.invoke({"query": item.question})` 仍能跑（invoke 接口未变）。

**M11 风险**：低；M11 不直接调 checkpointer，graph.invoke 是稳定接口。但 M11 Task 6 RED `test_run_item_retries_on_graph_4xx_5xx` mock `graph.invoke` 第 1 次抛 `HTTPError 500`——**如果 M7 加了 `safe_node` 装饰器**（M7 review P0-8 推荐）**，graph 节点内部异常不会冒泡到 invoke 层** → runner 重试机制失效。需在 M11 plan 加一句"`safe_node` 装饰器若启用，runner 重试只对 graph 外部异常（如 network）生效，节点内部异常由 `safe_node` 捕获 → runner 直接拿到 `state.error` 字段 → RAGAS faithfulness 算 0 → CI 报错**"。

**关键**：M11 与 M7 在错误传播路径上耦合度高，需在依赖表显式记录"依赖 M7 P0-8 修复（safe_node 装饰器）"。**升级到 P1-1**。

### 3-3 · M7 review P0-3 → M11 runner `graph.invoke` 调用前需先建立 checkpointer

M7 review P0-3 指出 `make_checkpointer` 是 `@asynccontextmanager` 工厂，但 `compile(checkpointer=...)` 需要实例。M11 runner L268 调 `get_graph()`（M7 工厂函数）——**如果 `get_graph()` 内部已建好 checkpointer + compile，M11 runner 无感**；如果 `get_graph()` 只返回未 compile 的 graph，M11 runner 要先 `async with make_checkpointer() as cp: graph.compile(cp)`。

**M11 风险**：取决于 M7 P0-3 修复方案 A（普通工厂返回实例）还是 B（保留 contextmanager + 调用方负责 async with）。M11 plan 应在"与其他 M 的契约边界"表 L92-99 补一行"**M11 runner 假设 `get_graph()` 返回已 compile 的 graph（M7 P0-3 修复后）**"，避免依赖假设含糊。**P2-1**。

### 3-4 · M7 review P0-6 → M11 golden set 缺 chitchat 路径

M7 review P0-6 指出 M7 实际有 8 个节点（7 业务 + `answer_chitchat_node`），但 M11 golden set L213 `question_type: Literal["factual", "summary", "multi_hop"]` **完全没 chitchat**——L260-264 分布矩阵 6 factual + 6 summary + 6 multi_hop + 2 edge，**没有 chitchat 题**。

**M11 风险**：
- spec §3.3 L241 classify 节点 `intent ∈ {retrieve, chitchat}` —— V1 graph **两路并行**（spec §1 架构 L60-62）
- M11 只测 retrieve 路径 → chitchat 路径完全无 CI 覆盖 → M7 answer_chitchat 节点永远不会有 faithfulness 数据
- chitchat 路径调 LLM 不检索 → faithfulness 不适用（没 contexts），但 answer_relevancy 仍可测

**关键**：M11 必须补 chitchat 题（或明确"chitchat 路径仅做冒烟，不进 golden set"）。**升级到 P1-2**。

### 3-5 · M7 review P0-8 → M11 runner 在 M7 safe_node 装饰器下行为变化

M7 review P0-8 推荐 M7 用 `safe_node` 装饰器包装所有节点，节点异常被捕获 → state.error 被设置 → graph 不中断。M11 runner L268 `graph.invoke(...)` 仍正常返回（state 含 error 字段），但 answer/contexts 可能为空或部分缺失。

**M11 风险**：
- runner L275 `state.get("answer", "")` → answer 为空 → RAGAS faithfulness = 0（合理，因为 answer 不 grounded）
- runner L276 `state.get("sources", [])` → sources 为空 → context_precision = 0
- 这本身**不是 bug**，但 M11 plan 没断言 "graph 跑通 ≠ RAGAS 通过"，CI 容易出假绿

**M11 风险**：低；现有断言机制能 catch 节点失败。但 M11 plan 风险表应补"M7 safe_node 装饰器启用后，runner 拿到的 answer/contexts 可能为空 → RAGAS 三指标全 0 → gate 触发 → 这不是 bug 是正确捕获节点失败"。**P2-2**。

### 3-6 · M10 review P0-2 / P0-3 → M11 report 透传 trace_id 的 API 错位

M10 review P0-3 指出 `handler.get_trace_id()` 不是公开 API，正确是 `from langfuse import get_client; get_client().get_current_trace_id()`。M11 plan L51, L98, L366 全部写 `get_current_trace_id()`（假定从 `app.observability.langfuse` 导入），但 M10 修复后该函数**应是** `get_client().get_current_trace_id()` 而**不是** `app.observability.langfuse.get_current_trace_id`。

**M11 风险**：
- M11 plan L367 `trace_id = get_current_trace_id() or ""` —— 假设 `get_current_trace_id()` 函数存在于 `app.observability.langfuse`
- M10 修复后，该函数要么不存在要么签名不同 → runner 测试 `test_run_item_captures_trace_id_from_langfuse` L370-375 mock 不到目标路径
- 单测可 mock 通过，但真跑（手测）时 trace_id 永远为空 → HTML 报告 L510 `Trace ID` 列全空 → 失去双向追溯价值

**关键**：M11 runner 必须等待 M10 P0-3 修复完成才能正确取 trace_id。**升级到 P0-6**。

### 3-7 · M10 review 整体 → M11 假设 Langfuse trace 上报稳定

M10 review 5 P0 + 9 P1 都影响 M11 关联字段：
- M10 P0-2 `langfuse_context.flush()` 在 2.50+ 不存在 → M11 跑完不 flush → trace 不到 Langfuse 看板 → runner 拿到的 trace_id 是**生成时 ID**，看板里查不到对应 trace
- M10 P0-5 装饰器机制错（用 `on_chain_*` 不会创建 Langfuse span）→ Langfuse 看板**根本看不到** trace → 即使 M11 拿到 trace_id 也无用
- M10 P1-4 缺 Langfuse 不可达降级 → 容器 down 时 trace 完全丢失 → M11 report trace_ids 字段全空

**M11 风险**：高。M11 把 M10 当"已完成"假设，但 M10 实际**未完成**。**升级到 P0-2 联动**：M11 plan 应在依赖表 L617-622 显式标"**M10 修复 5 P0 后** M11 才能跑真端到端"。

### 3-8 · M3 review P0-2 callback 注入 → M11 judge LLM 不依赖 callback

M3 review P0-2 指出 `make_llm` 注入 callback 写 `model.callbacks` 弃用，应改 `with_config({"callbacks":[handler]})`。M11 plan 不修改 M3 工厂（仅调 `make_llm("judge")`），所以**不受 M3 P0-2 影响**——judge LLM 不需要 Langfuse callback（评测是离线，不需要业务级 trace）。

**M11 风险**：无。M11 plan 隐含"judge LLM 不接 Langfuse callback"——但**没显式说**。建议 plan 在 Task 4 GREEN 段补注释：`make_llm("judge")` 返回的 LLM **不传 Langfuse handler**（评测不污染业务 trace 看板）。**P2-4**。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · RAGAS 0.2+ `ragas.evaluate()` 真实签名与 plan 写法不符（数据集 schema 字段名错）

**位置**：Task 7 GREEN 段 L392-416
```python
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
...
dataset = Dataset.from_list(items)
result = evaluate(dataset, metrics=ragas_metrics, llm=judge)
```

**问题**：
1. RAGAS 0.2+ 的 `evaluate()` 函数签名是 `evaluate(dataset, metrics=None, llm=None, embeddings=None, raise_exceptions=False, ...)`——`llm` 参数名对，但 **RAGAS 0.2+ 主推** `from ragas.llms import LangchainLLMWrapper; llm_wrapper = LangchainLLMWrapper(judge); evaluate(dataset, metrics=..., llm=llm_wrapper)`，**直接传 `BaseChatModel` 在 0.2+ 已被 deprecate**，0.3 会完全删除
2. RAGAS 0.2+ 期望的 dataset 字段是 `("question", "answer", "contexts", "ground_truth")`——plan L405-408 `items = [{"question", "answer", "contexts", "ground_truth"}]` 字段名对 ✓
3. 但 `context_precision` 指标的 ground_truth 字段**期望**是 `ground_truth` 字符串（如"是 / 否"）还是 `reference_contexts` 列表？RAGAS 0.2+ 文档明确：**`context_precision` 用 `reference_contexts`（参考答案相关文档 ID 列表）计算**，而 `answer_relevancy` 用 `ground_truth`（参考答案文本）——plan L413 把所有指标的 ground_truth 都用同一个字符串会**导致 context_precision 算错**：
   - 若 `ground_truth` = "Q3 完成 3 个 OKR 中的 2 个"（参考答案文本），`context_precision` 把这段文本当 reference → 算法把 contexts 与这段文本做相似度 → 永远接近 1（文本被 contexts 引）→ 指标失真
   - 正确做法：`GoldenItem.reference_contexts: list[str]` = 参考相关文档 ID 列表（如 `["doc-okr-q3"]`），构造 dataset 时把 `ground_truth=item.ground_truth` + `reference_contexts=item.reference_contexts` 同时传入

**修改**（Task 7 GREEN 段改写）：
```python
# app/eval/scorer.py
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from ragas.llms import LangchainLLMWrapper
from app.eval.judge import make_judge_llm

METRIC_MAP = {
    "faithfulness": faithfulness,
    "answer_relevancy": answer_relevancy,
    "context_precision": context_precision,
}

def score_dataset(items: list[dict], metrics: list[str]) -> dict:
    """items = [{"question", "answer", "contexts", "ground_truth", "reference_contexts"}]"""
    dataset = Dataset.from_list([{
        "question": it["question"],
        "answer": it["answer"],
        "contexts": it["contexts"],
        "ground_truth": it["ground_truth"],
        "reference_contexts": it.get("reference_contexts", it["contexts"]),  # 默认 fallback
    } for it in items])
    ragas_metrics = [METRIC_MAP[m] for m in metrics]
    judge_llm = make_judge_llm()
    llm_wrapper = LangchainLLMWrapper(judge_llm)  # 0.2+ 必备包装
    result = evaluate(
        dataset,
        metrics=ragas_metrics,
        llm=llm_wrapper,
        raise_exceptions=False,  # 单题异常不污染整体
    )
    return {
        "per_item": result.to_pandas().to_dict(orient="records"),
        "aggregate": {m: float(result[m]) for m in metrics},
    }
```

并 `GoldenItem` 加 `reference_contexts: list[str] = Field(default_factory=list)` + fixture 20 题每题补 3-5 个参考相关文档 ID。

并在 Task 7 RED 段补：
```python
def test_score_uses_langchain_llm_wrapper_not_raw_chat_model():
    mock_judge = MagicMock(spec=ChatAnthropic)
    with patch("app.eval.scorer.LangchainLLMWrapper") as wrapper_cls:
        score_dataset([...], ["faithfulness"])
        wrapper_cls.assert_called_once_with(mock_judge)
```

### P0-2 · `make_llm("judge")` 在 M3 工厂未注册（M3 review P1-5 联动阻塞）

**位置**：L43 仓库布局 `app/llm/factory.py # make_llm 新增 "judge" 节点` + L167 Files 修改 `app/llm/factory.py` `make_llm 注册 "judge" 节点` + L301 GREEN 段 `make_llm("judge")` + L289 yaml 文件

**问题**：
- M3 review P1-5 已指出 M3 工厂 `KNOWN_NODES = ("classify", "rewrite", "rerank", "answer")` 无 `judge`
- M11 plan L43, L167 写"在 `app/llm/factory.py` 注册 judge 节点"——**这是修改 M3 已建文件**，但 plan 没说明"在 M11 阶段修改 M3 已建文件"的合理性
- `app/llm/prompts/judge.yaml` 在 Files 表 L154 标注"M11 新增"——但 M3 review P1-5 已建议**M3 阶段建空文件占位**（避免下游 M 复制"4 yaml 空壳"反模式）
- 集成测试 Task 11 L568 跑 `_run_eval(...)` → `score_dataset(...)` → `make_judge_llm()` → `make_llm("judge")` → **`ValueError: unknown llm node: judge`**（M3 工厂白名单） OR **`FileNotFoundError: app/llm/prompts/judge.yaml`**（M3 没建空文件）

**修改**（Files 表 L154 + L167 改写 + 与 M3 契约明示）：
- 仓库布局 L43 改：`app/llm/                          # M3 已建，本 plan 修改 factory.py 注册 "judge" + 新增 prompts/judge.yaml`
- Files 修改 L167 改写：
  ```
  - app/llm/factory.py（M3 已建，本 plan 修改）：在 KNOWN_NODES 追加 "judge" 节点 + 注册 load_prompt("judge") → ChatAnthropic
  - app/llm/prompts/judge.yaml：M11 新增（含完整 system_prompt 草稿 + temperature=0.0）
  ```
- 并 Task 4 GREEN 段补断言：
  ```python
  def test_make_llm_judge_node_registered():
      from app.llm.factory import KNOWN_NODES, make_llm
      assert "judge" in KNOWN_NODES
      llm = make_llm("judge")
      assert isinstance(llm, ChatAnthropic)
      assert llm.temperature == 0.0  # judge 强制 deterministic
  ```

### P0-3 · `pytest-asyncio` 缺 pyproject 声明（review P1-18 联动）

**位置**：Tech Stack L113 "测试：`pytest` / `pytest-asyncio` 见 §测试策略" + Files 表 L166 `pyproject.toml` 追加 3 个新直接依赖（`ragas` / `datasets` / `click` / `python-markdown`）——**缺 pytest-asyncio**

**问题**：
- Task 6 runner GREEN 段 L348-368 全部是 `async def run_item(item, n)` + `await graph.invoke(...)` —— 异步函数
- Task 11 集成测试 L568 `_run_eval(...)` 内部 `runs = [run_item(item, n=i) for i, item in enumerate(items, 1)]` —— 异步 list comprehension 错（应是 `await asyncio.gather(*[run_item(...) for ...])`）
- plan 全篇**没有** `pytest-asyncio` 的 pyproject 声明 —— 新人 `pip install` 后跑测试 `fixture 'event_loop' not found` / `async function ... not awaited` 报错

**修改**（Files 修改 L166 补 + Task 6 GREEN 段改写）：
- pyproject.toml 追加：
  ```toml
  [project.optional-dependencies]
  dev = [
    ...  # 已有
    "pytest-asyncio>=0.24,<1",   # M11 异步测试必需
    "pytest-mock>=3.14,<4",      # M11 runner / scorer mock
  ]
  ```
- Task 6 GREEN runner 改写：
  ```python
  import asyncio
  from app.graph.workflow import get_graph
  from app.observability.langfuse import get_current_trace_id
  from app.eval.golden_set import GoldenItem

  async def run_item(item: GoldenItem, n: int) -> dict:
      graph = get_graph()
      thread_id = f"eval-{n}-{uuid.uuid4().hex[:8]}"
      state = await graph.ainvoke(  # ainvoke 不是 invoke
          {"query": item.question},
          config={"configurable": {"thread_id": thread_id}},
      )
      return {...}

  async def run_batch(items: list[GoldenItem]) -> list[dict]:
      return await asyncio.gather(*[run_item(item, n=i) for i, item in enumerate(items, 1)])
  ```
- 并在 Task 11 集成测试改用 `await _run_eval(...)`（不能是同步调用）
- 并 `pytest.ini` 显式开 `asyncio_mode = auto`（沿用总 review P2-1）

### P0-4 · RAGAS 版本 `>=0.2,<1` pin 区间太宽，0.2 / 0.3 API 已 break change

**位置**：Tech Stack L108 "`ragas` `>=0.2,<1`（spec §8.6）"

**问题**：
- RAGAS 0.2 → 0.3 API 已有 breaking change（如 `LangchainLLMWrapper` 是 0.2.5+ 引入，0.2.0 没）
- spec §8.6 L434 写 `ragas>=0.2,<1` 是允许漂移，但 M11 plan 依赖 P0-1 提到的 `LangchainLLMWrapper` API——此 API 在 0.2.0 不存在
- M11 plan L636 风险表 L635-636 写"`RAGAS 0.2 metrics API 变化`（`from ragas.metrics import` 新 API）"——但只提 metrics 路径，**没提 `LangchainLLMWrapper` 包装层**的 break change

**修改**（Tech Stack 改 + 风险表补）：
- Tech Stack L108 改：`ragas>=0.2.5,<0.3` —— pin 0.2.5+ 确保 `LangchainLLMWrapper` 可用，pin 0.3 以下避开 0.3 break change
- 风险表补：
  ```
  | RAGAS 0.2.5+ LangchainLLMWrapper 强制包装 | 风险：0.3+ 改 ragas.llms.LLM 协议 | 缓解：pin <0.3，0.3 升级时单独 milestone |
  ```
- 或方案 B（推荐 V1 收尾用）：`ragas==0.2.10`（最新 0.2.x）精确 pin，与 spec §8.6 区间保持兼容但不漂移

### P0-5 · CI gate `faithfulness < 0.7` 在 20 题样本下统计不稳定性未论证

**位置**：Task 10 GREEN 段 L524-539 + DoD L605 + 风险表 L631

**问题**：
- 20 题 golden set 跑 faithfulness，每题 2 次 LLM judge 调用（一次判 statement 数，一次判 statement 是否 grounded）→ 40 次 LLM 调用 → 单次 judge 偏差 ±0.05 → 20 题 aggregate 偏差 ±0.10 是**下限**（实际 ±0.15）
- spec §6 L319 "**CI 门禁：faithfulness ≥ 0.7**" —— 0.7 阈值在 20 题下置信区间 ±0.15 → 真值 0.85 的测试**可能** 70% 概率测出 0.70 而 gate 挂
- RAGAS 官方文档与社区实践建议 faithfulness 评估至少 50-100 题才有统计意义，20 题是 smoke
- 风险表 L631 写"CI 跑 20 题（5 分钟），nightly 跑 50 题"——但**两套都用 0.7 gate**没区分，nightly 50 题更稳定应做**硬 gate**，CI 20 题不稳定应做**警告不挂**

**修改**（Task 10 + 风险表 + DoD 改）：
- 方案 A（推荐）：拆 CI gate 与 nightly gate 两套阈值
  - CI 20 题：`faithfulness < 0.65` 抛异常（宽容阈值，避免统计抖动误报）
  - nightly 50 题：`faithfulness < 0.7` 抛异常（spec 阈值，统计稳定）
- 方案 B：CI 也用 0.7 但允许 1 次重试（避免偶发 judge 偏差）
- 方案 C：CI 跑 20 题 + 单题 pairwise comparison（每题与 baseline 比 diff 而非绝对值）—— 工程量大
- 风险表补：`faithfulness gate 统计稳定性` | 风险：20 题 aggregate 偏差 ±0.15 | 缓解：CI 阈值宽容到 0.65 / nightly 用 0.7
- DoD L605 改：`gate：CI faithfulness < 0.65 抛异常（20 题宽容）/ nightly < 0.7 抛异常（50 题硬阈值）`

### P0-6 · `app.observability.langfuse.get_current_trace_id()` API 与 langfuse 2.50+ 不匹配（M10 review P0-3 联动）

**位置**：L51 `app/observability/langfuse.py # 读 trace_id 关联报告` + L98 "M11 report | `langfuse.get_current_trace_id()` | M10 已建" + L366 `trace_id = get_current_trace_id() or ""` + L370-375 RED `test_run_item_captures_trace_id_from_langfuse` mock `get_current_trace_id`

**问题**：
- M10 review P0-3 明确：`handler.get_trace_id()` 不是公开 API
- 但**更深问题**：M11 plan 假设 `app.observability.langfuse.get_current_trace_id()` 是函数（从该模块导入）—— M10 plan 在 M10 范围可能**根本不提供这个函数**（M10 用 `langfuse_context.update_current_observation` 在装饰器内部写 metadata，不主动导出 `get_current_trace_id`）
- L98 契约表"调用方 | 用的接口 | 备注"写 `langfuse.get_current_trace_id()` —— 但 M10 plan L98-107 / L200-300 都没显式定义这个导出函数
- 真跑（手测）时 trace_id 永远拿不到，HTML 报告 L510 `Trace ID` 列全空 → **report 价值大打折扣**

**修改**（L98 + L366 + L370-375 改写）：
- L98 改：`M11 report | `from langfuse import get_client; get_client().get_current_trace_id()` | 2.50+ 公开 API；用 `try/except` 包装避免拉不到时影响主流程`
- L366 改：
  ```python
  def _safe_get_trace_id() -> str | None:
      """拉取当前 Langfuse trace_id；拉不到返 None（不抛异常污染主流程）"""
      try:
          from langfuse import get_client
          return get_client().get_current_trace_id()
      except Exception:
          return None
  ```
- L370-375 RED 改：
  ```python
  def test_run_item_captures_trace_id_from_langfuse(monkeypatch):
      # mock langfuse.get_client
      fake_client = MagicMock()
      fake_client.get_current_trace_id.return_value = "trace-abc"
      monkeypatch.setattr("langfuse.get_client", lambda: fake_client)
      item = GoldenItem(id="q1", question="...", ground_truth="...", source_filter="file", question_type="factual")
      result = asyncio.run(run_item(item, n=1))
      assert result["trace_id"] == "trace-abc"
  ```

---

## P1 · 重要

### P1-1 · runner 重试机制在 M7 safe_node 装饰器下失效（M7 review P0-8 联动）

**位置**：Task 6 GREEN 段 L380-382 `tenacity @retry(... retry=retry_if_exception_type((HTTPError, RAGASJudgeError)))` + RED `test_run_item_retries_on_graph_4xx_5xx` L377-382

**问题**：
- M7 review P0-8 推荐 M7 用 `safe_node` 装饰器——**节点内部异常被装饰器捕获**，不冒泡到 `graph.invoke` 层
- M11 runner 重试机制 `retry_if_exception_type(HTTPError)` 期望 `graph.invoke` 抛 HTTPError——但 safe_node 后 `graph.invoke` 正常返回 `state.error` 字段，**HTTPError 不再冒泡**
- 单测 mock `graph.invoke` 第 1 次抛 HTTPError（绕过 safe_node 模拟）→ 测试绿，但真跑时重试机制失效

**修改**（Task 6 GREEN 段改）：
- 重试范围缩到 graph **外部**异常（network / 鉴权），不要 retry 节点内部异常
- 加 runner 内部断言：`if state.get("error"): raise GraphNodeError(state["error"])` —— 节点失败冒泡后由 tenacity 重试 1 次（可能 transient）
- RED 段补：`test_run_item_surfaces_node_error_for_retry`（mock graph.invoke 返回 `{"error": "classify_failed: ..."}` → 断言 runner 抛 `GraphNodeError`）

### P1-2 · golden set 缺 chitchat 路径（M7 review P0-6 联动）

**位置**：Task 3 RED `test_fixtures_covers_3_sources_3_types` L246-248 + GREEN 段 L260-264 分布矩阵

**问题**：
- spec §3.3 L241 graph classify `intent ∈ {retrieve, chitchat}` 两路并行
- M7 review P0-6 指出 M7 实际有 `answer_chitchat_node` 节点
- M11 golden set 完全没 chitchat 题 → chitchat 路径无 CI 覆盖
- chitchat 路径不检索 → RAGAS `context_precision` 不适用，但 `answer_relevancy` 仍可测

**修改**（Task 3 GREEN 段补）：
- 分布矩阵扩 7×3=21 + edge → 30 题（25 + 5 chitchat）
- chitchat 题 5 条：`question_type: "chitchat"`，ground_truth 简短（"我是 Hermes Agent..."），contexts = `[]`，reference_contexts = `[]`，评估只算 `answer_relevancy`
- 或 M11 在 config 里加 `include_chitchat: bool = False` 默认开关，让 chitchat 题在 v1.1 加

### P1-3 · `context_precision` 指标需 `reference_contexts`，plan 当 `ground_truth` 字符串传（P0-1 部分）

**位置**：Task 2 GREEN 段 L207-213 `GoldenItem` 定义 + Task 7 L405-408 `score_dataset` 入参

**问题**：
- 见 P0-1.2 详述
- RAGAS `context_precision` 需要 ground-truth 相关文档 ID 列表（`reference_contexts`），不是参考答案文本
- 当前 plan `GoldenItem.ground_truth: str` 单字段，没 `reference_contexts` 字段 → context_precision 计算失真

**修改**（Task 2 GREEN 段改 + fixture 改）：
```python
class GoldenItem(BaseModel):
    id: str
    question: str
    ground_truth: str                              # 参考答案文本（给 answer_relevancy 用）
    source_filter: Literal["file", "url", "confluence"]
    expected_doc_id: str | None = None
    question_type: Literal["factual", "summary", "multi_hop", "chitchat"]
    reference_contexts: list[str] = Field(default_factory=list)  # 新增：参考相关文档 ID（给 context_precision 用）
```

fixture 20 题每题补 3-5 个参考相关 doc_id（如 `["policy_2024.md", "policy_general.md"]`）。

### P1-4 · judge LLM 自身偏差对 faithfulness 指标影响未量化

**位置**：风险表 L631 + DoD L605

**问题**：
- faithfulness 是 RAGAS 指标中**对 judge LLM 最敏感**的（每次 judge 内部调 LLM 判 statement 是否 grounded）
- minimax-cn MiniMax-M3 作为 judge LLM 的**位置偏差**（position bias，对 prompt 第一个/最后一个 statement 倾向高分）+ **冗长度偏差**（verbosity bias，对长 answer 倾向高分）未量化
- 当前 plan 假设 judge 是公正裁判——实际 mini-judge 偏差可达 ±0.1 faithfulness

**修改**（风险表 + DoD 补）：
- 风险表补：`judge LLM 偏差` | 风险：MiniMax-M3 judge 对长 answer / 特定位置 statement 倾向高分，faithfulness ±0.1 | 缓解：judge.yaml temperature=0.0 已降低；加 judge LLM **自评估**：从 20 题里抽 5 题人工评分，与 judge LLM 评分对照，diff > 0.1 标 warning
- DoD 补：`judge-human diff 测试通过（5 题人工 vs judge LLM，平均 diff ≤ 0.1）`
- 或方案 B：judge LLM 换成不同模型（如另一厂商）做交叉验证——成本翻倍

### P1-5 · eval cost 跟踪缺（50 题 × 4 LLM call × judge 价格）

**位置**：风险表 L631 + DoD 全篇

**问题**：
- 50 题 nightly：每题 2 次 faithfulness judge + 1-2 次 answer_relevancy judge + 0-1 次 context_precision = 3-5 次 LLM 调用 → 50 题 × 4 = 200 次 LLM call
- 单次 LLM call 平均 1K input + 500 output tokens（MiniMax-M3）→ 50 题 = 100K input + 25K output = $X（minimax-cn 定价未知）
- 长期看：每周 7 次 nightly + 每天 50 PR CI × 20 题 = 150 题/天 + 350 题/周 = 500 题/周 → 2000 LLM call/周 → $X/周（无跟踪无法预算）

**修改**（Task 1 GREEN 段 + 风险表改）：
- `EvalSettings` 加 `cost_budget_usd_per_run: float = 5.0` + `cost_budget_usd_per_week: float = 20.0`
- Task 1 RED 加 `test_eval_settings_has_cost_budgets`
- runner 跑完后从 RAGAS result 取 usage（`result.to_pandas()` 含 `usage` 列） → sum → 写进 report JSON `cost_usd` 字段
- 超 budget → gate warning（不挂，留手动决策）

### P1-6 · report 长期存储与 baseline 对比缺（"v1.0.0 vs v1.1.0 diff"）

**位置**：Task 9 GREEN 段 L488-514 + DoD 全篇

**问题**：
- 当前 plan 只生成单次 report → 评估历史不可追溯
- V1.0.0 → V1.1.0 升级时没法对比"指标是涨是跌"
- HTML 报告适合人工看，**不适合机器对比**

**修改**（Task 9 + Files 改）：
- report 命名加时间戳 + git commit SHA：`ragas_report_{timestamp}_{git_sha}.json`
- 评估结果写 Postgres `eval_runs` 表（M1 schema 已规划，但当前 spec §2 模块树 eval 段没说建表）—— 或 V1 阶段 git 化 + S3 V2
- 加 baseline 对比：CLI `--baseline previous_report.json` → report HTML 加 diff 列（vs baseline 涨/跌）
- 短期方案：report JSON 输出固定路径 `eval_history/{date}/report.json`，git 化 + 用 `git log` 查历史

### P1-7 · M11 runner 调 `retriever.retrieve(query)` 拿 contexts 但 graph 已做 retrieve（设计冗余）

**位置**：Architecture 数据流 L77-87 + 契约表 L96-97

**问题**：
- L83 "graph.invoke(...) → 拿 (answer, contexts, trace_id)"
- L96 契约表"runner | `retriever.retrieve(query)` 取 sources | 拿 contexts 给 RAGAS"——**但 graph 已经 retrieve 过**
- 两处 retrieve 重复执行（graph 跑一次 + runner 直接再跑一次）→ 双倍 latency + 双倍 OpenSearch 调用
- 应从 `graph.invoke` 返回的 `state` 里取 `chunks`（M7 review P1-6 修后，`state["chunks"]` 应已含 rerank 后的 chunks），不直接调 retriever

**修改**（L96 改 + Task 6 GREEN 段改）：
- 契约表 L96 删：`retriever.retrieve(query)` 取 sources → 改 `graph.invoke 返回 state["chunks"]`（M7 review P1-6 修后已有）
- Task 6 GREEN runner L362 `contexts = state.get("sources", [])` 改 `contexts = state.get("chunks", state.get("sources", []))` —— 双 fallback
- L96 契约表"备注"列补：`依赖 M7 P1-6 修复（chunks 字段名统一）`

### P1-8 · nightly 与 CI 指标差异未定义（是否分开跑不同子集？）

**位置**：L190-191 `EvalSettings.sample_size_ci: int = 20` + `sample_size_nightly: int = 50` + Task 5 RED L308 `subprocess.run(["python", "-m", "app.eval.ragas_run", "--help"])` 含 `--sample-size`

**问题**：
- CI 跑 20 题 / nightly 跑 50 题——但 plan **没说 50 题是否包含 20 题 CI 子集**
- 若 50 题是**独立 50 题**，golden set 至少要 50 题 + 边角 → 实际要 60 题 → fixture 维护成本高
- 若 50 题**包含 20 题 CI 子集**（前 20 题固定 + 后 30 题随机/扩展）→ 需 schema 表达"扩展集"
- 当前 plan L161 写 `tests/fixtures/golden_set_v1.jsonl # 20 题`——**没说 50 题 fixture 在哪**

**修改**（Task 3 + 风险表 改）：
- 方案 A（推荐）：fixture **单一 50 题**文件 `golden_set_v1.jsonl`，CI 用 `--sample-size 20` 取前 20 题，nightly 默认跑全部 50 题
- 方案 B：拆 `golden_set_ci.jsonl` (20) + `golden_set_nightly.jsonl` (50 独立)，nightly 不含 CI 题 → fixture 维护双份
- fixture 文件名 L161 改：`tests/fixtures/golden_set_v1.jsonl # 50 题（CI 用前 20 + nightly 用全部）`

---

## P2 · 优化

### P2-1 · runner `get_graph()` 契约含糊（M7 P0-3 修复方案依赖）

**位置**：Task 6 GREEN L356 `graph = get_graph()` + 契约表 L95

**问题**：依赖 M7 修复方案 A（普通工厂返回已 compile graph）还是 B（contextmanager），M11 plan 没说。**P2**：与 M7 review P0-3 同步即可。

### P2-2 · runner 在 M7 safe_node 装饰器下"节点失败 → RAGAS 算 0 → gate 挂"是正确捕获但没明示

**位置**：DoD L605 + 风险表 L636

**问题**：M7 safe_node 启用后，runner 拿到 `state.error` → RAGAS 用空 answer + 空 contexts → 三指标全 0 → gate 触发。**这不是 bug**，plan 风险表应明示这是"节点失败的正确捕获"，避免被误读为"CI 抖动"。

### P2-3 · report markdown 拼接可改 template

**位置**：Task 9 GREEN L500-513 `f"..."` 拼接 markdown 字符串

**问题**：10 行 `md += ...` 拼接难以维护 + 不易扩展（加新指标要改拼接代码）。短期 OK，长期可改 jinja2 或 pydantic → markdown 模板。**V1 拒 jinja2**（review P1-1），V2 再考虑。

### P2-4 · judge LLM 应**显式不接** Langfuse callback（避免污染业务 trace）

**位置**：Task 4 GREEN L277-282 `def make_judge_llm(): return make_llm("judge")`

**问题**：`make_llm("judge")` 走 M3 工厂，M3 工厂会**自动注入 Langfuse callback**（M3 review P0-2 修复后 `with_config({"callbacks":[handler]})`）。但评测是离线、用户无关，不需要业务 trace 上报。

**修改**（Task 4 GREEN 段补）：
```python
def make_judge_llm():
    """RAGAS judge 专用：走 M3 工厂但显式剥离 Langfuse callback（评测不污染业务 trace 看板）"""
    llm = make_llm("judge")
    # 强制无 callback：M3 工厂返回 RunnableBinding，剥离 callbacks
    return llm.with_config({"callbacks": []})  # 显式空 list 覆盖
```

### P2-5 · fixture `expected_doc_id` 校验未走真实索引

**位置**：Task 3 fixture L253-258 `expected_doc_id` 字段

**问题**：fixture 写 `expected_doc_id: "policy_2024.md"`，但 plan **没有** task 校验这个 doc_id 在真实索引中存在（依赖 M4 ingest 数据）。手测跑时可能 doc_id 不存在 → RAGAS 算 context_precision 时 contexts 是别的 doc → 指标失真。

**修改**（Files 表 + DoD 改）：
- 加 Task 12（Day 3 末尾）：`tests/integration/test_m11_golden_set_docs_exist.py`，mock `app.retrieval.client.search` 查 doc_id 是否存在 → 不存在标 warning（不挂，避免 ingest 未跑时 CI 挂）
- 或 fixture 改：expected_doc_id 改 optional `None`，只校验 schema 不校验存在性

---

## 跨 M 契约补强（与现有 review 联动）

### C-1 · M11 → M3 强依赖：`judge` 节点必须在 M11 前注册

M11 plan L43, L167 修改 M3 已建文件 `app/llm/factory.py`，但**没在依赖表 L617-622 标"修改 M3 已建文件"**。建议依赖表补：
```
| M3 LLM 工厂（**M11 修改**：在 make_llm 注册 "judge" 节点） |
```

### C-2 · M11 → M10 强依赖：`get_current_trace_id` API 修复后 M11 才能跑真端到端

M11 假设 `get_current_trace_id()` 函数存在，但 M10 review P0-3 指出底层 API 错。**必须等 M10 修复**。建议依赖表 L617-622 补：
```
| M10 Langfuse（**M11 依赖**：M10 P0-3 修复后 `from langfuse import get_client; get_client().get_current_trace_id()` 才能用） |
```

### C-3 · M11 → M7 强依赖：graph compile 形态 + chunks 字段名

M11 runner 依赖 `get_graph()` 返回已 compile 的 graph（M7 P0-3 修复方案 A）+ `state["chunks"]` 含 rerank 后 chunks（M7 review P1-6 修复）。建议依赖表 L617-622 补：
```
| M7 graph（**M11 依赖**：M7 P0-3 修复后 `get_graph()` 返已 compile graph / M7 P1-6 修复后 state["chunks"] 含 rerank 后 chunks） |
```

### C-4 · M11 → M7 弱依赖：safe_node 装饰器影响 runner 错误捕获路径

M7 review P0-8 推荐 safe_node，M11 runner 重试机制 P1-1 需相应调整。

---

## 落地建议

按 P0 → P1 → P2 → 实施的顺序：

1. **本轮**：先修 6 P0
   - **P0-1** RAGAS evaluate 输入 schema + LangchainLLMWrapper 包装（最复杂，需精读 RAGAS 0.2.5+ 文档）
   - **P0-2** 与 M3 review P1-5 同步——M11 plan 修改 M3 factory 必须显式声明，写 KNOWN_NODES 扩展
   - **P0-3** pyproject 加 pytest-asyncio + pytest-mock + runner 改 async + asyncio.gather 批跑
   - **P0-4** RAGAS 版本 pin 收紧到 `>=0.2.5,<0.3` 或 `==0.2.10`
   - **P0-5** CI/nightly 拆双阈值（CI 0.65 / nightly 0.7）
   - **P0-6** trace_id 取法改 `from langfuse import get_client; get_client().get_current_trace_id()` + try/except 包装

2. **本轮**：写 M11 plan r2，把 P0/P1 修复全部纳入（参考 M3 review r2 节奏）

3. **下轮**：与 M3 review r2 + M7 review r2 + M10 review r2 同步落代码
   - M3 factory 注册 judge 节点 + judge.yaml 占位
   - M7 graph 修复 chunks 字段名 + safe_node 装饰器
   - M10 修复 get_current_trace_id 公开 API 路径

4. **并行**：golden set fixture 50 题（含 chitchat 5 题）由产品 / 数据团队标注，**不是工程任务**

5. **晚一轮（V1 收尾前）**：M11 报告长期存储 + baseline 对比（P1-6）+ judge LLM 自评估（P1-4）+ eval cost 跟踪（P1-5）

---

## 总结

| 项 | 数量 | 阻塞级别 |
|---|---|---|
| 已有 review 验证 | 7 项 | 5 通过 / 2 部分避雷（→ P0-6 / P2-3） |
| 横向交叉验证 | 8 项 | 3 升级 P0（3-1 / 3-6 / 3-7）/ 3 升级 P1 / 2 升级 P2 |
| P0 阻塞 | 6 项 | RAGAS API / judge 节点 / pytest-asyncio / 版本 pin / gate 阈值 / trace_id API |
| P1 重要 | 8 项 | runner 重试 / chitchat 题 / context_precision 字段 / judge 偏差 / cost 跟踪 / report 存储 / 设计冗余 / CI-nightly 差异 |
| P2 优化 | 5 项 | get_graph 契约 / safe_node 行为 / template / judge callback / doc_id 校验 |
| 跨 M 契约补强 | 4 项 | M3 / M10 / M7 双依赖 + safe_node 弱依赖 |

**一句话**：M11 plan **11 段模板 + TDD 节奏 + RAGAS judge LLM 不读 OPENAI_API_KEY + Langfuse trace_id 透传 + CI/nightly 分级 + faithfulness gate 异常**这 6 项是 V1 收尾的**关键避雷已落地**；**但在 RAGAS 0.2+ 真实 API（M11 自己用之前要深读 0.2.5+ 文档）、M3/M10 上游契约未对齐（M3 factory judge 节点未注册 + M10 trace_id API 错）、golden set 质量门槛（chitchat 路径）、gate 统计稳定性（20 题置信区间）4 个方面有 6 P0 阻塞**。修完 6 P0 后 M11 才可动手；修完 P0 + P1（共 14 项）后是合格的 V1.0.0 RAGAS 评估基线。

---

## 状态

- 等待决策：
  - **P0-1**：是否在 M11 阶段修改 M3 factory 注册 judge 节点（vs 让 M3 review r2 同步加）
  - **P0-3**：是否使用 `tenacity` 改 runner 重试（vs 接受 graph invoke 失败）
  - **P0-5**：CI/nightly 拆双阈值 vs 统一 0.7 + 偶发重试
  - **P1-2**：golden set 加 5 题 chitchat（30 题总）vs v1.1 加
  - **P1-8**：fixture 单文件 50 题 vs 双文件 CI+nightly
- 阻塞其他 plan：
  - **P0-2** 强依赖 M3 review P1-5 修复
  - **P0-6** 强依赖 M10 review P0-3 修复
  - **P1-7** 强依赖 M7 review P1-6 修复（chunks 字段名）
  - **P1-1** 弱依赖 M7 review P0-8 修复（safe_node）

修完 P0 即可开 M11 plan r2 起草 + 代码实现。