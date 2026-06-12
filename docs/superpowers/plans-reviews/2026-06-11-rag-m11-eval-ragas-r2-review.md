# M11 Plan r2 Review · r1 修复验证

> 评审对象：plans/2026-06-11-rag-m11-eval-ragas.md（852 行，r1 已修）
> 评审基线：reviews/2026-06-11-rag-m11-eval-ragas-review.md（r1 = 6 P0 + 8 P1 + 5 P2 = 19 项）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立 r2 验证）
> 范围：验 r1 19 项修复是否到位 + 发现 r1 修复过程中是否引入新问题
> 横向交叉：M0/M1/M3/M4-M6/M7/M8/M9/M10/M12 plan + 各自 r2 review

---

## 总评

M11 plan r1 修复**完成度极高**——19 项 P0/P1/P2 全部纳入 plan 修订记录（plan L807-825 共 19 行 r1 已修 + L834-852 修订记录 19 行），每项修复都在 plan 正文找到对应落地（Task 1 EvalSettings 补 cost_budget/mode / Task 4 M3 工厂注册 judge / Task 6 runner async + GraphNodeError / Task 7 LangchainLLMWrapper + reference_contexts / Task 9 report 含 git_sha + cost_usd + baseline diff / Task 10 gate 双阈值），**M11 plan 已经成为合格 V1.0.0 RAGAS 评估基线**。

但 r2 独立审查**新发现 5 个问题**（2 个 P0 新阻塞 / 3 个 P1 重要），主要集中在 3 个方面：
1. **r1 修复之间的耦合衍生**——P1-8 fixture 50 题 + include_chitchat 开关 + mode=ci/nightly 三者交集没明示（5 chitchat 是否进 CI 20 题子集）
2. **RAGAS 0.2.10 真实 API 行为 plan 假设未证伪**——`evaluate()` 是否支持"按题选指标"（chitchat 跳过 context_precision）、`raise_exceptions=False` 是否真的隔离单题异常
3. **跨 M 命名一致性断裂**——M8 r2 已揭示 trace_id vs request_id 命名冲突，M11 plan 全文用 trace_id 但 runner 把 trace_id 写进 report 时与 M8 业务 request_id 字段如何对齐没明示

**3 维度评分**：
- r1 修复完成度：⭐⭐⭐⭐⭐（19/19 全部纳入 plan 修订记录 + 正文落地）
- RAGAS API 正确性：⭐⭐⭐⭐（LangchainLLMWrapper + reference_contexts + raise_exceptions=False 三件套到位；按题选指标 + per_item 字段没明示）
- 跨 M 一致性：⭐⭐⭐（M3/M7/M10 主依赖已对齐；M8 trace_id 命名断裂 + M12 CI hook 字段没明示）

**一句话**：M11 plan r1 修复把 19 项 P0/P1/P2 **全部纳入正文**，**M11 已达 V1.0.0 RAGAS 评估基线合格线**；但 r1 修复之间耦合产生 2 个 P0（chitchat 子集选择 + RAGAS evaluate 按题选指标），需修。

---

## 1. r1 修复验证（19 项逐项）

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|--------|---------|---------|------|
| **P0-1** | RAGAS 0.2.5+ `LangchainLLMWrapper(judge)` 包装 + `reference_contexts` 字段 | plan L468 `from ragas.llms import LangchainLLMWrapper` + L491 `llm_wrapper = LangchainLLMWrapper(judge_llm)` + L487 `reference_contexts` 字段；RED 测试 L456-457 `test_score_uses_langchain_llm_wrapper_not_raw_chat_model`；RED L516-518 `test_score_passes_reference_contexts_to_dataset` | ✅ 完全到位 |
| **P0-2** | M11 显式修改 M3 factory 注册 `"judge"` 节点 + `judge.yaml` | plan L176 Files 修改段 `app/llm/factory.py` `KNOWN_NODES` 追加 `"judge"` + L162 `app/llm/prompts/judge.yaml` M11 新增；Task 4 GREEN L321-336 完整 yaml + factory 注册代码；RED L318-320 + L338-340 双断言 | ✅ 完全到位 + C-1 联动显式标 |
| **P0-3** | pytest-asyncio + pytest-mock + asyncio_mode=auto + runner async + asyncio.gather 批跑 | plan L116-117 Tech Stack 显式 `pytest-asyncio>=0.24,<1` + `pytest-mock>=3.14,<4`；L175 pyproject 修改；L734 `pytest.ini asyncio_mode = auto`；Task 6 GREEN L388-432 runner async + `asyncio.gather(*[...], return_exceptions=False)` | ✅ 完全到位 |
| **P0-4** | RAGAS 版本 pin 收紧到 `==0.2.10` | plan L110 Tech Stack `ragas == 0.2.10`（精确 pin，spec §8.6 区间兼容）；风险表 L789 明示 pin `==0.2.10` 精确 | ✅ 完全到位 |
| **P0-5** | CI/nightly 双阈值（CI 0.65 / nightly 0.7）+ mode 参数 + THRESHOLDS 表 | plan L198 `threshold_ci: float = 0.65` + L206 `mode: Literal["ci", "nightly"]`；Task 10 GREEN L670 `THRESHOLDS = {"ci": 0.65, "nightly": 0.70}` + L672-679 `check()` 显式 mode 决定阈值；RED L651-657 + L682-686 完整 | ✅ 完全到位 |
| **P0-6** | trace_id 改 `from langfuse import get_client; get_client().get_current_trace_id()` + try/except | plan L395-403 `_safe_get_trace_id()` 显式 try/except 包装；L101 契约表改 `get_client().get_current_trace_id()`；L434-437 RED 测试 mock 路径正确 | ✅ 完全到位 + C-2 联动显式标 |
| **P1-1** | runner 重试缩到 graph 外部异常 + 节点失败 `GraphNodeError` 显式抛 + tenacity 重试 | plan L405-407 `GraphNodeError` 类 + L417-419 节点失败显式 raise + L449 `tenacity @retry(stop=stop_after_attempt(3), ..., retry=retry_if_exception_type((HTTPError, RAGASJudgeError, GraphNodeError)))`；RED L440-447 三测试齐 | ✅ 完全到位 |
| **P1-2** | golden set 50 题含 5 chitchat + `include_chitchat` 开关 + chitchat 路径只算 answer_relevancy | plan L205 `include_chitchat: bool = True`；L283-285 5 chitchat 题示例；L292 "评估只算 `answer_relevancy`，context_precision 跳过" | ⚠️ **到位但有衍生问题**：RAGAS 0.2.10 `evaluate()` 是否支持"按题跳过某指标"没明示 RED 测试；CI 20 题子集里 chitchat 题是否包含没明示（见 §2-新-1） |
| **P1-3** | `GoldenItem.reference_contexts: list[str]` + Pydantic `model_validator` 必填校验 | plan L233 `reference_contexts: list[str] = Field(default_factory=list)` + L264-268 RED `test_validates_reference_contexts_for_non_chitchat` + L268 GREEN `model_validator` 守住 | ✅ 完全到位 |
| **P1-4** | judge-human diff 测试（5 题人工 ≤ 0.1）+ `judge.yaml` temperature=0.0 | plan L327 `temperature: 0.0`；DoD L750 `judge-human diff 测试通过（5 题人工 vs judge LLM，平均 diff ≤ 0.1）`；风险表 L797 明示 | ⚠️ **到位但 RED 测试缺**：plan 没说 5 题人工评分数据在哪/谁负责/什么周期更新；属于组织问题不是工程问题，归 P1 |
| **P1-5** | `cost_budget_usd_per_run=5.0` / `cost_budget_usd_per_week=20.0` + report `cost_usd` 字段 + 超 budget warning | plan L203-204 `cost_budget_usd_per_run` + `cost_budget_usd_per_week`；L552 `_compute_cost_usd(result)` + L604 `"cost_usd"` 字段；DoD L751 | ⚠️ **到位但 `_compute_cost_usd` 实现缺**：Files 表没列该函数；RAGAS result 如何取 usage 列没明示（`result.to_pandas()` 是否含 usage 取决于 RAGAS 版本 + 是否传 `llm=` 包装）（见 §2-新-2） |
| **P1-6** | report 命名 `{timestamp}_{git_sha}.json` + git_sha/timestamp/mode 字段 + --baseline CLI + HTML diff 列 | plan L548-549 `_get_git_sha()` + `_get_timestamp()` + result 注入；L554 报告路径；L360 `--baseline` CLI option；L629-637 HTML `vs Baseline` 列 diff；DoD L747 完整 | ✅ 完全到位 |
| **P1-7** | runner 从 `state["chunks"]` 取（双 fallback 兼容 `state["sources"]`） | plan L424 `"contexts": state.get("chunks", state.get("sources", []))`；契约表 L99 显式 `state.get("chunks", state.get("sources", []))`；DoD L749 | ✅ 完全到位 + M7 P1-6 联动 |
| **P1-8** | fixture 单一 50 题文件（CI 前 20 / nightly 全部）+ mode 参数决定 sample_size | plan L63 `tests/fixtures/golden_set_v1.jsonl # 50 题（CI 用前 20 + nightly 用全部 + 5 chitchat + edge）`；L533-536 `actual_size = sample_size or (settings.eval.sample_size_ci if mode == "ci" else settings.eval.sample_size_nightly)` + `items = items[:actual_size]` | ⚠️ **到位但有衍生问题**：50 题里 5 chitchat 排在末尾（q046-q050），CI 20 题不包含 → CI 不覆盖 chitchat 路径（见 §2-新-1） |
| **P2-1** | 契约表 / 依赖表显式 "假设 M7 P0-3 修后 get_graph() 返已 compile graph" | plan L92 契约表 `**依赖 M7 P0-3 修复**：get_graph() 返回已 compile graph`；L768 依赖表 `**M11 假设 M7 P0-3 修后** get_graph() 返已 compile graph` | ✅ 完全到位 |
| **P2-2** | 风险表明示 "safe_node 节点失败 → RAGAS 全 0 → gate 挂是正确捕获" | plan L803 风险表 `safe_node 节点失败 → RAGAS 全 0 → gate 挂` + 缓解 `**风险表明示 "这是节点失败的正确捕获，不是 CI 抖动"**`；DoD L745 显式说明 | ✅ 完全到位 |
| **P2-3** | md 拼接抽 `_build_markdown(result, threshold, baseline)` 让单测可独立测 | plan L647 `REFACTOR` 显式 `把 md 拼接抽成 _build_markdown(result, threshold, baseline) 让单测可独立测` | ✅ 完全到位 |
| **P2-4** | `make_judge_llm` 显式 `llm.with_config({"callbacks": []})` 剥离 Langfuse callback | plan L311 `return llm.with_config({"callbacks": []})   # P2-4 显式空 callback 覆盖 M3 自动注入`；L142 重复 `return llm.with_config({"callbacks": []})`；RED L314-316 `test_judge_strips_langfuse_callback` | ⚠️ **到位但与 M3 工厂可能有冲突**：M3 r2 修后 factory 返回的 LLM 形态（如 `RunnableBinding` vs `BaseChatModel`）`with_config` 是否兼容没断言（见 §2-新-3） |
| **P2-5** | `test_m11_golden_set_docs_exist.py` 校验 doc_id 真实索引（warning 不挂）+ fixture expected_doc_id optional | plan L66 `tests/integration/test_m11_golden_set_docs_exist.py  # expected_doc_id 真实索引校验（warning 不挂）`；Task 11 RED L716-718 显式 mock + warning 不抛 | ✅ 完全到位 |

**r1 修复验证结论**：19 项中 **14 项完全到位**（✅）+ **5 项到位但有衍生问题**（⚠️）。5 项衍生问题中 3 项归 P1（人工评分数据归属 / RAGAS usage 取法 / `with_config` 兼容性），2 项归 P0（chitchat 子集选择 + RAGAS evaluate 按题选指标）。

---

## 2. r1 修复引入的新问题

### 新-1 (P0) · chitchat 子集与 CI/nightly 阈值耦合断裂
**位置**：Task 3 L283-285 fixture 5 chitchat 题 `q046`-`q050` + Task 8 L533-536 `items[:actual_size]` + Task 10 L670 `THRESHOLDS = {"ci": 0.65, "nightly": 0.70}`

**问题**：
- fixture 50 题排序：18 factual + 18 summary + 9 multi_hop + 5 chitchat + edge → chitchat 排在 q046-q050
- CI 20 题 = 前 20 题 = 全 factual/summary → **CI 不跑 chitchat 路径** → P1-2 "5 chitchat 进 golden set" 在 CI 完全无效
- nightly 50 题全跑 → 5 chitchat 影响 aggregate faithfulness（chitchat 路径 answer 是 LLM 自由生成，RAGAS faithfulness 算分不稳定）
- P1-2 修后："chitchat 路径只算 answer_relevancy，context_precision 跳过"——但 **RAGAS `evaluate()` 是否支持"按题跳过某指标"未明示**。RAGAS 0.2.10 默认对所有题算所有指定指标，要"按题跳过"需在 dataset 里填空字段或自定义 metric wrapper

**影响**：
- CI 跑 20 题全 factual/summary → 拿到的 faithfulness aggregate 不能反映 chitchat 质量
- nightly 50 题 chitchat faithfulness=0 → aggregate 被拉低 → nightly gate < 0.7 误报
- 修 P1-2 时没考虑子集分布 → r1 修复合并产生新问题

**建议修复**（升级到 P0）：
- 方案 A：fixture 排序打乱 chitchat 题，**5 chitchat 均匀分布到 50 题中**（如 q006, q014, q022, q030, q038）→ CI 前 20 题包含 2 题 chitchat
- 方案 B：CI 单独有 5 题 chitchat 子集 + 15 factual 子集（fixture 拆 ci/nightly 双文件，回退到 P1-8 否决方案）
- 方案 C：nightly 跑 50 题时 chitchat 路径**单独算 sub-aggregate**，不影响主 gate（gate 只看 45 题 non-chitchat faithfulness）
- 方案 D（推荐 V1）：RAGAS evaluate 不支持按题选指标时，**chitchat 题 faithfulness 字段填 1.0 占位**（不参与 aggregate）—— 不优雅但能用
- 并 Task 8 显式分项：`factual_score = aggregate_non_chitchat.faithfulness` + `chitchat_score = aggregate_chitchat.answer_relevancy`，gate 只看 factual_score

### 新-2 (P0) · RAGAS `evaluate()` `raise_exceptions=False` 行为 + per_item usage 取法 plan 假设未证伪
**位置**：Task 7 L496 `raise_exceptions=False` + Task 8 L552 `_compute_cost_usd(result)` + DoD L751 cost tracking

**问题**：
- RAGAS 0.2.10 `evaluate(raise_exceptions=False)`：实际行为是**异常题 result 行填 NaN**，per_item DataFrame 该行全 NaN——**不是"单题异常不污染整体"**，而是"单题异常时该题指标变 NaN，aggregate 计算时 NaN 默认被 pandas skipna=True 排除"
- 这意味着：50 题跑出 1 题 LLM 异常 → 49 题有效，aggregate = 49 题均值；**但 DoD 没明示"异常题数 > N 时应 fail"** 的兜底逻辑（如 5 题异常就应放弃整个 run）
- `_compute_cost_usd(result)`：plan 假设 `result.to_pandas()` 含 `usage` 列 → RAGAS 0.2.10 默认**不返回 usage**，需在 `evaluate()` 显式传 `llm=` 包装类（如 `LangchainLLMWrapper`）+ 加 `token_usage_parser` callback 才能取到 token
- 当前 plan L491-497 只传 `llm=llm_wrapper, raise_exceptions=False`——**没传 usage 收集参数** → `cost_usd` 永远是 0.0 → cost budget 永远不触发 warning

**影响**：
- r1 P1-5 修复 `cost_budget_usd_per_run=5.0` 字段**形式上到位但实际无效**——`_compute_cost_usd` 拿不到真实 usage
- r1 P0-1 `raise_exceptions=False` 行为 plan 假设与 RAGAS 实际行为有偏差——单题异常题在 per_item DataFrame 是 NaN 行，aggregate 算时默认 skipna 但需 plan 显式处理

**建议修复**（升级到 P0）：
- 方案 A：RAGAS 0.2.10 文档化做法是 `evaluate(..., callbacks=[UsageCallback()])`——显式追踪 LLM 调用 token
- 方案 B：用 `langchain_community.callbacks.get_openai_callback()` 类似方案（但 M3 工厂封装后要适配）
- 方案 C：V1 阶段不报 cost_usd 数值，只报"评测完成"，V1.1 加 RAGAS usage callback——但 DoD 就要降级
- 并 Task 7 显式处理 NaN：result.to_pandas() 后 dropna(axis=0, subset=['faithfulness']) 算 aggregate，否则 5 题异常时 aggregate 仍算 45 题均值看似通过实际是降级

### 新-3 (P1) · `with_config({"callbacks": []})` 与 M3 工厂返回值兼容性未断言
**位置**：Task 4 L311 / L142 `return llm.with_config({"callbacks": []})`

**问题**：
- M3 review P0-2 修复后工厂返回 `RunnableBinding`（M3 r2 改写方式决定具体形态）
- `RunnableBinding.with_config({"callbacks": []})` 在 langchain 1.0+ 行为：**空 callbacks list 会被运行时合并**（如果 LLM 调用上下文已有 callbacks，不会清空）
- M3 factory 走 `load_prompt("judge")` → `ChatAnthropic(model=..., temperature=0.0).with_config({"callbacks": [langfuse_handler]})` 的话——M11 再 `.with_config({"callbacks": []})` 在 langchain 1.0+ 是**新增合并而非覆盖**
- 真正要"剥离 callback"应：调底层 `llm.callbacks = []` 或 `llm._get_callback_list()` 清空

**影响**：
- P2-4 "剥离 Langfuse callback" 目标在 langchain 1.0+ 可能**实际不生效** → judge LLM 调用仍带 Langfuse callback → 评测 trace 污染业务 trace 看板
- 评测跑 50 题 × 4 call/题 = 200 LLM call 上报 Langfuse → 看板数据爆炸

**建议修复**（保持 P1）：
- RED 测试 L314-316 需**实际验证回调链无 Langfuse handler**：用 `langchain_core.callbacks.BaseCallbackManager` 注入 spy → 调 make_judge_llm() → 调 llm.invoke(...) → 断言 spy 未触发 Langfuse 上报
- 工厂返回值如果是 `RunnableBinding` 而非 `BaseChatModel`，plan 需明示"对 binding 的 with_config 行为差异"
- 或方案 B：M11 judge 不走 M3 工厂（破坏 C-1 联动），直接 `ChatAnthropic(model="minimax-cn/MiniMax-M3", temperature=0.0)` 显式 new 一个，物理上无 callback

### 新-4 (P1) · `--baseline` 参数使用方式与 V1 git 化策略不匹配
**位置**：Task 5 L360 CLI `--baseline` option + Task 9 L620 `write_html(result, path, threshold, baseline_path=None)`

**问题**：
- P1-6 修复 `report 命名 {timestamp}_{git_sha}.json` + `git 化`——但 `--baseline` 是 CLI 参数，**每次跑评测要手传 baseline 路径**
- V1 git 化策略 = `eval_history/{date}/report.json`——**没说 baseline 默认从 git 历史取最近一次**（如 `git log --diff-filter=A --name-only` 找上一个 report 文件）
- 实际用法：每次跑 nightly 都要记得 `--baseline eval_history/2026-06-10/report.json`，否则 baseline diff 列空
- M12 Hardening 接 CI 时怎么传 baseline？CI workflow 怎么知道最近一次 baseline 路径？

**影响**：
- P1-6 形式上到位（diff 列存在），实际 V1 用起来很笨——CI 跑没 baseline → diff 列空 → 失去对比意义

**建议修复**（保持 P1）：
- M11 自身加 default：`_default_baseline_path()` 函数用 `git log` 找最近一次 `tests/fixtures/eval_history/20*/report.json`
- 或 M12 CI workflow 把 baseline 路径写进 env var：`EVAL_BASELINE_PATH=eval_history/latest.json`（symlink 最新一次）
- 并 plan DoD 加一条："nightly 跑完自动更新 `eval_history/latest.json` symlink 指向最新 report"

### 新-5 (P1) · 5 chitchat 题在 CI 20 题子集被跳过——P1-2 修复未达"chitchat 路径 CI 覆盖"目标
**位置**：Task 3 L283-285 fixture 5 chitchat 题 `q046`-`q050` + Task 8 L533-536 `items = items[:20]` for CI

**问题**：
- P1-2 修复目标："chitchat 路径有 CI 覆盖"——但 fixture 排序 + CI 前 20 题 = CI 跑不到 chitchat
- 修订记录 L841 写 "golden set 5 chitchat 题 + include_chitchat 开关 + chitchat 路径只算 answer_relevancy"——**没明示 chitchat 进哪个子集**
- 实际：5 chitchat 题只 nightly 跑 50 题时进，CI 20 题完全不覆盖 chitchat 路径

**影响**：
- P1-2 修复后 chitchat 路径**实际只在 nightly 跑**（每晚一次）→ 任何白天 PR 引入的 chitchat 回归**CI 不报**
- spec §3.3 L241 chitchat 路径**有 SLA 要求**（用户寒暄回答质量）→ CI 不覆盖 = V1 上线风险

**建议修复**（保持 P1，但应与新-1 一起合并修）：
- 与新-1 方案 A 合并：fixture 50 题里 chitchat 均匀分布（q006, q014, q022, q030, q038）→ CI 20 题包含 2 题 chitchat
- 或方案 B：CI 20 题 = 15 factual/summary + 5 chitchat（fixture 重新分区，CI 子集不是简单前 N 题）
- DoD 显式："CI 子集覆盖 3 question_type（factual/summary/chitchat），nightly 子集覆盖 4 question_type（含 multi_hop）"

---

## 3. 跨 M 一致性检查（M0/M1/M3/M4-M6/M7/M8/M9/M10/M12）

| 上游 M | M11 依赖 | M11 plan 现状 | M 上游 r2 状态 | 一致性 |
|--------|---------|-------------|--------------|------|
| **M0 infra** | docker-compose up PG + OpenSearch 真跑评测 | L588 "需 docker compose up（M0）+ ANTHROPIC_API_KEY" + 测试策略 L730 显式 | M0 已修 | ✅ 一致：M11 真跑依赖 M0 起来，CI 用 mock 不依赖 |
| **M1 alembic** | golden set 可关联 ingest_jobs.doc_id 校验 | L766 "M1 alembic（golden set 可关联 ingest_jobs.doc_id 校验完整性）" | M1 已修 | ✅ 一致：M11 P2-5 校验 doc_id 真实索引已用 M1 schema |
| **M3 llm-embed** | `make_llm("judge")` + judge.yaml（**M11 显式修改 M3 已建文件**） | L43 仓库布局明示 "M11 修改 factory.py 注册 judge" + L176 Files 修改 + L321-336 完整代码 | M3 r2 已修 | ✅ 一致：M11 范本影响段明示，与 M3 r2 KNOWN_NODES 扩展同步 |
| **M3 callback 注入** | judge LLM `with_config({"callbacks": []})` 剥离 | L142 + L311 `with_config({"callbacks": []})` | M3 r2 改用 `RunnableBinding` 形式 | ⚠️ **新-3 揭示**：M3 r2 后 callback 注入方式可能与 M11 剥离方式不兼容，需 RED 测试实际验证 |
| **M4-M6 retrieval** | `state["chunks"]` 字段名 + 接口 | L424 `"contexts": state.get("chunks", state.get("sources", []))` 双 fallback | M7 P1-6 修复已统一 chunks 字段名 | ✅ 一致：双 fallback 兼容 M4-M6 旧数据 |
| **M7 graph 7 节点** | `get_graph()` 返回已 compile graph + `graph.ainvoke` | L92 "M11 假设 M7 P0-3 修后 get_graph() 返已 compile graph" + L412-416 `graph.ainvoke` 调用 | M7 r2 已修 | ✅ 一致：M7 4 项 r1 衍生修复已落，M11 假设成立 |
| **M7 answer_chitchat_node** | chitchat 路径评估 | L292 "chitchat 路径只算 answer_relevancy" | M7 r2 已修 | ⚠️ **新-1 揭示**：chitchat 路径在 CI 子集被跳过，与 M7 chitchat 节点 CI 覆盖目标不一致 |
| **M7 safe_node 装饰器** | 节点失败 `state.error` 字段 + `GraphNodeError` 显式 raise | L405-419 `GraphNodeError` + tenacity retry | M7 r2 P0-8 已修 | ✅ 一致：M11 P1-1 修复与 M7 safe_node 联动到位 |
| **M8 trace_id 命名** | M11 report 写 trace_id | L51 `app/observability/langfuse.py # 读 trace_id 关联报告` + L101 契约表 + L546 `result["trace_ids"]` | M8 r2 揭示 `request_id` vs `trace_id` 命名断裂 | ⚠️ **新-6 揭示**：M8 r2 揭示 M8 业务级用 `request_id`，M10/M11 用 `trace_id`——M11 runner 拿到的 trace_id 写到 report 时与 M8 业务 request_id 字段如何对齐没明示（见下） |
| **M10 langfuse 公开 API** | `from langfuse import get_client; get_client().get_current_trace_id()` + try/except | L395-403 `_safe_get_trace_id()` 完整实现 | M10 r2 P0-3 已修 | ✅ 一致：与 M10 r2 修复的公开 API 路径完全对齐 |
| **M10 flush + 装饰器** | M11 假设 M10 修后 Langfuse trace 上报稳定 | L772 "M10 P0-2 flush + P0-5 装饰器（M11 假设 M10 修后 Langfuse trace 上报稳定）" | M10 r2 已修 | ✅ 一致：M11 弱依赖 M10 修复后能力 |
| **M12 hardening** | CI workflow 接 `python -m app.eval.ragas_run --mode ci` | L765 "M12 Hardening（CI 流程调 `python -m app.eval.ragas_run --mode ci`）" + L731 显式 | M12 已修 | ✅ 一致：M11 产出 gate 钩子，M12 接 CI workflow |
| **M11 → M11 自身** | gate 抛 `GateViolationError` exit 1 | L696-698 `except GateViolationError as e: click.echo(f"GATE FAILED: {e}", err=True); sys.exit(1)` | 自身 | ✅ 一致：CLI exit code 1 路径完整 |

**跨 M 一致性结论**：12 项 M 依赖中 **9 项完全一致**（✅）+ **3 项有潜在断裂**（⚠️）：M3 callback 兼容性（新-3）/ M7 chitchat CI 覆盖（新-1+新-5）/ M8 trace_id 命名（新-6）。

### 新-6 (P1) · M8 trace_id vs request_id 命名断裂未在 M11 plan 明示
**位置**：M11 runner L425 `"trace_id": _safe_get_trace_id() or ""` + M11 report L546 `result["trace_ids"]` + M11 report HTML L640-641 `Trace ID` 列

**问题**：
- M8 r2 揭示：M8 业务级 logging/middleware 用 `request_id` 字段，M10 Langfuse 暴露 `trace_id`，两者命名断裂
- M11 runner 拿 Langfuse `trace_id` 写进 report，但跑评测时用户发请求的 `request_id` 怎么关联？没明示
- HTML 报告 L640-641 表格列叫 `Trace ID`——与 M8 业务侧 logging 用的 `request_id` 不一致 → 双追溯时人工对不上

**影响**：
- M11 报告 Trace ID 与 M8 业务日志的 Request ID 实际是**不同 ID 体系**，但文档/代码都简称 "ID" → 排障时混淆
- 双向追溯：用户报错带 request_id → 找 Langfuse trace 要先在 M8 middleware 写 request_id → trace_id 映射

**建议修复**（保持 P1）：
- M11 report 字段名改 `langfuse_trace_id`（明确是 Langfuse 的 ID，不是 M8 request_id）
- HTML 表格列名 `Langfuse Trace ID`（明示 ID 来源）
- runner 多取一个字段：`_safe_get_request_id()`（从 M8 middleware context var 取），report 写 `request_id` 与 `langfuse_trace_id` 两列
- 或 M11 plan 加注释：M8 r2 揭示的 trace_id/request_id 命名断裂待 M8 plan r3 一并修

---

## 4. 风险表补全质量

### 4.1 风险表结构
plan 风险表 L778-806 共 29 行：
- **原 r0 风险**：6 行（OPENAI_API_KEY / Faithfulness 昂贵 / Golden set 漂移 / judge 4xx5xx / jinja2 / metrics API）
- **r1 修复风险**：13 行（LangchainLLMWrapper / CI 双阈值 / context_precision / judge 节点注册 / trace_id API / safe_node 节点失败 / M7 chunks 字段 / pytest-asyncio / judge 偏差 / cost 跟踪 / chitchat / report 存储 / CI-nightly 差异 / get_graph 契约 / safe_node 行为 / template / judge callback / doc_id 校验）
- **r1 已修标注**：19 行（L807-825 修订记录段，与风险表分离）
- **修订记录**：19 行（L834-852 修订记录段）

### 4.2 补全质量评估

| 维度 | 评估 | 说明 |
|------|------|------|
| **原 r0 风险保留** | ⭐⭐⭐⭐⭐ | 6 行原风险全部保留（OPENAI_API_KEY / Faithfulness 昂贵 / Golden set 漂移 / judge 4xx5xx / jinja2 / metrics API），未删除 |
| **r1 修复 19 项全覆盖** | ⭐⭐⭐⭐⭐ | 19 项 P0/P1/P2 全部进入风险表，标记"已修"或"缓解" |
| **曾被否决替代方案** | ⭐⭐⭐⭐ | 9 行有"曾被否决的替代方案"列（M3 同步加 / 统一 50 题 / 双文件 CI+nightly / pin `>=0.2,<1` / 统一 0.7 / 复用 ground_truth / 不区分内外异常 / 用同步 runner / 换不同厂商 judge / 不跟踪 cost / M11 不测 chitchat / V1 直接 S3 / M11 runner 自己 compile / 忽略此现象 / V1 用 jinja2 / 继承 M3 factory callback / V1 必存在 / 让 RAGAS 默认读 env / fail fast 不重试 / 用 jinja2 模板 / 断言关键词 in answer）—— **列有意义**，避免下轮重提 |
| **r1 修复衍生新风险** | ⭐⭐ | **新-1/新-2/新-3/新-5/新-6 揭示的 5 个 r1 衍生问题未进入风险表**——r2 需补 5 行 |
| **跨 M 联动风险** | ⭐⭐⭐ | M3/M7/M10 主依赖已标，但 **M8 命名断裂未标**（见新-6） |
| **风险量化** | ⭐⭐⭐ | CI 20 题 ±0.15 偏差已量化；judge LLM ±0.1 偏差已量化；cost 50 题 × 4 call 已量化 |

### 4.3 r2 需补风险行（建议）

```
| RAGAS 0.2.10 evaluate() 是否支持按题跳过某指标 | 风险：chitchat 题 context_precision 跳过需 dataset 填空字段或自定义 wrapper | 缓解：V1 阶段 chitchat 题 faithfulness 填 1.0 占位，V1.1 用 RAGAS 0.3 的 metric callback |
| RAGAS 0.2.10 raise_exceptions=False 实际行为 | 风险：异常题 per_item NaN，aggregate 默认 skipna 算 49 题均值，DoD 没明示"异常题数 > N 应 fail" | 缓解：Task 7 显式 dropna + 异常题数 > 5 抛异常 |
| RAGAS 0.2.10 evaluate() 不返回 usage 字段 | 风险：cost_usd 永远 0.0，cost budget 永远不触发 warning | 缓解：V1 阶段 RAGAS 显式传 UsageCallback 收集 token；V1.1 替换为 token-level tracking |
| M3 r2 后 RunnableBinding.with_config 与 M11 callback 剥离兼容性 | 风险：M11 with_config({"callbacks": []}) 在 langchain 1.0+ 是合并而非覆盖，judge LLM 仍带 Langfuse callback | 缓解：M11 RED 测试断言 callback spy 实际不触发；或 M11 judge 不走 M3 工厂直接 ChatAnthropic(...) |
| M8 r2 揭示 trace_id vs request_id 命名断裂 | 风险：M11 report 写 trace_id 但 M8 业务侧用 request_id，双追溯混淆 | 缓解：M11 report 字段改名 `langfuse_trace_id`；runner 多取 request_id；M8 plan r3 一并修 |
| 5 chitchat 题在 CI 前 20 题子集被跳过 | 风险：CI 不覆盖 chitchat 路径，PR 引入 chitchat 回归 CI 不报 | 缓解：fixture 重排 chitchat 均匀分布（q006, q014, q022, q030, q038）；或 CI 子集 15 factual + 5 chitchat |
| --baseline CLI 参数与 V1 git 化策略不匹配 | 风险：CI workflow 不知道怎么传 baseline，diff 列空 | 缓解：M11 default 用 git log 找最近一次 report；M12 CI workflow env var 传 baseline 路径 |
```

---

## 5. 落地建议

按 r1 修复完成度 + r2 新发现问题排优先级：

### 5.1 本轮（修 2 P0 + 3 P1）
1. **新-1 (P0) · chitchat 子集选择**
   - 方案 A：fixture 重排 chitchat 均匀分布（q006, q014, q022, q030, q038）—— 工程量小
   - 方案 C（推荐）：nightly 跑 50 题时 chitchat 路径单独算 sub-aggregate，gate 只看 45 题 non-chitchat faithfulness
   - 配套修新-5：DoD 加 "CI 子集覆盖 3 question_type"

2. **新-2 (P0) · RAGAS evaluate raise_exceptions + usage 实际行为**
   - Task 7 GREEN 加：`result_df = result.to_pandas(); valid_df = result_df.dropna(subset=['faithfulness']); if len(valid_df) < 0.9 * len(items): raise EvalInsufficientDataError`
   - Task 7 GREEN 加：RAGAS evaluate 显式传 usage 收集 callback，或 V1 阶段 `_compute_cost_usd` 改用本地 token 计数器（judge LLM invoke 前后手动计）
   - 配套：DoD L751 改"cost 跟踪：report 含 `cost_usd` 字段（V1 阶段可能为 0，V1.1 启用 RAGAS usage callback）"

3. **新-3 (P1) · `with_config` 兼容性**
   - RED L314-316 加 callback spy 断言：注入 `FakeCallbackHandler`，调 make_judge_llm() → 调 .invoke() → 断言 spy 未触发 Langfuse 上报
   - 风险表加一行（见 §4.3）

4. **新-4 (P1) · `--baseline` 默认值**
   - M11 加 `_default_baseline_path()`：`git log --diff-filter=A --name-only --pretty=format: tests/fixtures/eval_history/ | head -1`
   - 风险表加一行

5. **新-6 (P1) · M8 trace_id 命名断裂**
   - M11 report 字段名改 `langfuse_trace_id`（与 M8 `request_id` 区分）
   - HTML 表格列名改 `Langfuse Trace ID`
   - runner 多取一个 `_safe_get_request_id()`（从 M8 middleware context var）
   - 风险表加一行

### 5.2 下轮（M11 plan r3）
- 与 M3 r2 + M7 r2 + M10 r2 同步落代码
- M3 factory 注册 judge 节点 + judge.yaml 占位（已显式）
- M7 graph 修复 chunks 字段名 + safe_node 装饰器（已显式）
- M10 修复 get_current_trace_id 公开 API 路径（已显式）
- M8 r3 一并修 trace_id/request_id 命名断裂

### 5.3 并行（组织任务，非工程）
- golden set fixture 50 题（含 chitchat 5 题）由产品 / 数据团队标注
- judge LLM 偏差自评估：5 题人工评分，由 M11 负责人维护

### 5.4 晚一轮（V1 收尾前）
- M11 报告长期存储 + baseline 对比（P1-6 部分落地，V1 git 化 + nightly diff）
- judge LLM 自评估常态化（P1-4，5 题人工 + judge LLM diff ≤ 0.1）
- eval cost 跟踪完整化（P1-5，RAGAS usage callback 接通）

---

## 总结

| 项 | 数量 | 状态 |
|---|------|------|
| r1 19 项 P0/P1/P2 修复 | 19 | 14 完全到位 + 5 到位但有衍生问题 |
| r1 修复验证表 | 19 行 | ✅ |
| r2 新发现问题 | 5 | 2 P0（chitchat 子集 + RAGAS evaluate 行为）+ 3 P1（callback 兼容 / baseline 默认值 / M8 命名断裂） |
| 跨 M 一致性检查 | 12 项 M | 9 一致 + 3 潜在断裂（M3 callback / M7 chitchat / M8 命名） |
| 风险表补全质量 | 6 维 | 5 维优秀 + 1 维（r1 衍生风险）需补 5 行 |
| 落地建议 | 4 轮 | 本轮 5 项 + 下轮同步 + 并行组织 + 晚一轮 V1 收尾 |

**一句话**：M11 plan r1 修复把 19 项 P0/P1/P2 全部纳入正文（修订记录 + 风险表 + Tasks），**M11 已达 V1.0.0 RAGAS 评估基线合格线**；但 r1 修复之间耦合产生 2 个 P0（chitchat 子集选择 + RAGAS evaluate 按题选指标）+ 3 个 P1（callback 兼容 / baseline 默认值 / M8 命名断裂），修完这 5 项 M11 才完全可动手。

---

## 状态

- **r1 修复**：19/19 全部纳入 plan 修订记录（plan L807-825 + L834-852）
- **r2 新发现**：5 项（2 P0 + 3 P1）
- **阻塞其他 plan**：
  - 新-1 + 新-5（chitchat 子集）需 fixture 重排
  - 新-2（RAGAS evaluate 行为）需 RAGAS 0.2.10 实际验证（无代码情况下只能 plan 假设）
  - 新-3（callback 兼容）需 M3 r2 实际返回值类型
  - 新-6（M8 命名断裂）需 M8 r3 联动
- **下轮同步**：M3 r3 + M7 r3 + M8 r3 + M10 r3 一并落代码
