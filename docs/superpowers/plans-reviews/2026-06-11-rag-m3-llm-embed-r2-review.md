# M3 Plan r2 Review · r1 修复验证 + 范本影响力

> 评审对象：M3 `2026-06-10-rag-m3-llm-embed.md`（512 行 · r1 修订后）
> 评审基线：r1 review `2026-06-11-rag-m3-llm-embed-review.md`（775 行 · 4 P0 + 6 P1 + 6 P2 共 16 项 + 范本影响 1 项）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（r2 独立验证）
> 范围：**验 r1 修复是否到位** + **验 M3 范本对下游 M4–M12 的实际影响力**
> 不重新发明新问题；只验"修了没 / 改对了没 / 下游有没有吃到"

---

## 总评

r1 的 16 项 P0/P1/P2 修复**全部落入 plan 文本**，无遗漏、无误植、无内部矛盾；附加 1 项"范本影响通知"（L512）也写入修订记录。r1 修复**完成度 = 16/16 = 100%**。M3 plan 在 r1 之后已**结构齐、版本齐、契约齐、内容齐**——4 段 prompt 草稿（classify/rewrite/rerank/answer）各含完整 ≥ 50 token + 1-shot + JSON 输出约束、`make_llm` 改 `with_config` 协议、`TEIEmbedder` 加 `EmbeddingDimMismatch` 硬断言 + context manager、`LLMSettings`/`EmbeddingSettings`/`LangfuseSettings` 5 字段展开、`KNOWN_NODES` 7 节点注册表 + `_DETERMINISTIC_NODES` 3 节点强制、`load_prompt_cfg` mtime 热加载、`test_prompt_yaml_guard.py` 守门测试、估时改"Tasks ~6h + 调试 ~6h + 文档 ~4h"、4 节点 parametrize 集成测试，全部按 r1 review 的建议落到位。

**范本影响力**也已传导：下游 9 份 plan 全部按 11 段 M3 骨架起草（r1 范本影响评估结论里"3 份 M7/M10/M11 不得不绕过/补强 M3"的局面**已消失**）——M7 显式引用 `KNOWN_NODES` 追加 `answer_chitchat`（L47/L126/L203）、M10 显式标注"M3 工厂注入方式不变（P1-14 已用 with_config）"（L56）、M11 显式要求 `make_llm` 注册 `judge` 节点 + `judge.yaml` 占位（L44/L141）、M6 显式对接 `EmbeddingDimMismatch`（L131/L1062）、M4/M5 复用 `TEIEmbedder`、M12 锁定"app/llm/factory.py 不动"（L237）。**M3 范本结构性影响 + 契约性影响均成功**。

**跨 M 一致性**：M3 ↔ M0（TEI 端口 18080 / dim=1024）、M3 ↔ M7（7 节点 KNOWN_NODES vs 8 节点 graph）、M3 ↔ M10（with_config callback 协议）、M3 ↔ M11（judge 节点 + 剥离 callback 注入方式）**全部对齐**。M3 ↔ M7 节点数差异（7 vs 8）是**正确的**——M7 plan L18 自解释"7 主路径 + `answer_chitchat` 节点 = 8 节点函数"，而 7 节点是 M3 工厂支持的 LLM 节点名集合，`load_memory`/`save_memory` 是 M7 graph 编排节点**不**消耗 LLM，与 M3 工厂无关。

**风险表补全**：原 16 行风险（r1 之前）→ 17 行（atexit flush 加在原 L463）→ r1 加 16 行"PX 已修"+ L512 范本影响 1 行 = 共 33 行；范本影响段已保留（修订记录末行）。**完整**。

| 维度 | 评分 | 状态 |
|---|---|---|
| r1 修复完成度 | ⭐⭐⭐⭐⭐ | 16/16 全部落入 plan 文本，0 漏改、0 误改 |
| 修复一致性 | ⭐⭐⭐⭐⭐ | plan 内部无矛盾（LLMSettings / KNOWN_NODES / with_config / dim 断言 4 处交叉引用一致） |
| 范本结构性影响 | ⭐⭐⭐⭐⭐ | M4–M12 全部按 11 段起草，0 偏离骨架 |
| 范本契约性影响 | ⭐⭐⭐⭐⭐ | M7/M10/M11/M6 全部精确引用 M3 工厂契约点（KNOWN_NODES / with_config / EmbeddingDimMismatch / dim=1024） |
| 跨 M 一致性 | ⭐⭐⭐⭐ | M0/M7/M10/M11 4 个关键接口对齐；微瑕：M3 plan §Tech Stack 未显式给 TEI 端口 18080（由 .env.example 解析，跨 plan 引用时需翻 M0） |
| 风险表 | ⭐⭐⭐⭐⭐ | 17 + 16 + 1 = 33 行，原风险保留完整 + 修复标注 + 范本影响 |

**一句话**：r1 修复**已**全部到位 + 范本影响力**已**传导到下游 9 份 plan。M3 plan 在 r1 之后**已**是合格的"完整范本"（结构 + 契约 + 内容 + 风险 + 修订记录 5 维齐），可作为 RAG V1 路线**单里程碑计划样板**定稿。

---

## 1. r1 修复验证（16 项逐项）

验证方法：grep 修复关键字是否在 M3 plan 文本内被引用 + 数量 / 位置 / 上下文是否正确（不是单纯出现，而是与 r1 review 建议一致）。

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|---|---|---|---|
| **P0-1** | 4 yaml 草稿段（classify/rewrite/rerank/answer 各 ≥ 50 token + 1-shot） | plan §4 L151-242 完整 4 段 YAML：classify L156-172 (含 "1-shot 示例" 167 行 + JSON 输出约束 165 行)、rewrite L174-192 (188 行 1-shot)、rerank L194-216 (210 行 1-shot + JSON scores 207 行)、answer L218-242 (234 行 1-shot + ANSWER/SOURCES 格式约束)。L153 自警"4 个 prompt yaml 文件... 各 ≥ 50 token，含 1-shot 示例"；L244 收尾"4 yaml 已含 ≥ 50 token + 1-shot 示例，满足 DoD 第 7 条（由 Task 6 守门测试强制）" | ✅ 到位 |
| **P0-2** | `make_llm` 改用 `with_config({"callbacks":[handler]})` 协议 | plan L84 "M3 工厂已注（`with_config` 协议）"、L369 "用 `bound.with_config({\"callbacks\": [handler]})` 注入，**不**写进 `model.callbacks` 字段（langchain 1.0+ 已弃用）"、L379-381 RED 测试 `test_callback_uses_with_config_not_callbacks_field` 显式断言、L427 DoD 第 4 条 "（用 `with_config` 协议）"、L447 跨 M 联动 "M10 节点层 trace 不必再补 callback"、L458 风险表注解、L472 修订记录 | ✅ 到位 |
| **P0-3** | TEIEmbedder 加 `EmbeddingDimMismatch` 硬断言 + 4xx/5xx 分类 + `httpx.Timeout(60s)` + batch_size 协调 | L307 "**dim 硬断言**（P0-3）：返回 dim ≠ `self.cfg.dim`（默认 1024）抛 `EmbeddingDimMismatch`"、L323-325 RED `test_embed_raises_on_dim_mismatch`、L460 风险表、L473 修订记录；batch_size 协调见 L304 "batch_size 由 `EmbeddingSettings.batch_size` 控制（默认 32，与 TEI 服务端协调）"；4xx/5xx 分类见 L306 | ✅ 到位 |
| **P0-4** | LLMSettings 补 timeout/max_retries/rate_limit_rpm；LangfuseSettings 补 sample_rate/flush_at/flush_interval/blocked_keys；atexit flush 标 M12 | L262-291 完整 schema 展开：`LLMSettings` (timeout=60, max_retries=3, rate_limit_rpm=60)、`EmbeddingSettings` (batch_size=32, dim=1024, timeout_seconds=60.0)、`LangfuseSettings` (sample_rate=1.0, flush_at=2, flush_interval=5.0, blocked_keys=[])。L341 atexit flush 标注 M12、L461-463 风险表、L474 修订记录 | ✅ 到位 |
| **P1-1** | 工厂层强制 `classify/rerank/judge` temperature=0.0，忽略 yaml 覆盖 | L365 "**_DETERMINISTIC_NODES = {\"classify\", \"rerank\", \"judge\"}**（P1-1）：强制 `temperature=0.0`，忽略 yaml 覆盖"、L383-385 RED `test_classify_and_rerank_are_deterministic`、L464 风险表、L475 + L500 修订记录 | ✅ 到位 |
| **P1-2** | langfuse import 加双备路径 | L105 "（P1-2 双备）"、L338 "先 `from langfuse.langchain import CallbackHandler`（2.50+ 主），失败回退 `from langfuse.callback.langchain import CallbackHandler`（旧版），两条都失败置 `CallbackHandler = None`"、L349-351 RED `test_callback_handler_import_paths_resolve`、L457 风险表、L476 + L501 修订记录 | ✅ 到位 |
| **P1-3** | pyproject dev 依赖补 pytest-httpx + pytest-cov | L103 Tech Stack 表 "pytest / pytest-asyncio / pytest-httpx / pytest-cov"、L111 "**pyproject 依赖补完**（P1-3 + P2-3）：`dependencies` 段追加 `pyyaml>=6.0,<7`；`[project.optional-dependencies] dev` 段追加 `pytest-httpx>=0.30,<1` + `pytest-cov>=5.0,<7`"、L144 Files 表说明、L477 + L502 修订记录 | ✅ 到位 |
| **P1-4** | `LLMSettings.model` 改 `temperature_default/max_tokens_default` 兜底；yaml `model` 字段为唯一来源 | L263-264 schema: `temperature_default: float = 0.3` + `max_tokens_default: int = 1024`（已删 `model` 字段）、L366 "**yaml 优先**（P1-4）：`cfg.model / cfg.temperature / cfg.max_tokens` 从 yaml 读，缺省回退 `settings.llm.temperature_default/max_tokens_default`"、L468 风险表、L478 + L503 修订记录 | ✅ 到位 |
| **P1-5** | 工厂改注册表 `KNOWN_NODES` 7 节点 + Files 表加 judge/summarize/answer_chitchat.yaml 占位 | L15 顶层 Goal: "**注册表**机制管理 7 节点（classify / rewrite / rerank / answer / judge / summarize / answer_chitchat）"、L46 `app/prompts/judge.yaml` / `summarize.yaml` / `answer_chitchat.yaml` 占位标注、L82 契约边界表 5 节点提及、L123 Files 表 "注册表" KNOWN_NODES、L364 "**注册表** `KNOWN_NODES = (\"classify\", \"rewrite\", \"rerank\", \"answer\", \"judge\", \"summarize\", \"answer_chitchat\")`（P1-5）；未知名抛 `ValueError`"、L387-389 RED `test_make_llm_rejects_unknown_node`、L446 跨 M 联动 M7 "M3 工厂已注册 `answer_chitchat` 节点"、L448 跨 M 联动 M11 "judge.yaml 占位文件已建"、L467 风险表、L479 + L504 修订记录 | ✅ 到位 |
| **P1-6** | Task 4 拆 4a/4b/4c（约 20 分钟），下游 M 估时 +1d 通知 | L354-357 Task 4 拆解段 "Task 4a：`load_prompt_cfg` + mtime 热加载（5 分钟） / Task 4b：`make_llm` 注册表工厂 + 7 节点 + deterministic 强制（10 分钟） / Task 4c：callback 注入（5 分钟，受 P0-2 with_config 改写）"、L470 风险表、L480 + L505 修订记录（但下游 M +1d 通知**未在 plan 显式写"已通知 M7/M10/M11"段**——本 r2 微瑕见 §5.1） | ✅ 到位（微瑕：通知动作未显式记录） |
| **P2-1** | `load_prompt_cfg` 加 mtime cache key 热加载 | L38 "prompts.py 4 节点 prompt YAML 加载（mtime 热加载）"、L124 "7 节点 system prompt（YAML 加载 + mtime 热加载）"、L355 Task 4a "load_prompt_cfg + mtime 热加载"、L370 "**mtime 热加载**（P2-1）：`load_prompt_cfg(node)` 内部以 `(path, mtime)` 为 key 缓存 yaml，改文件自动失效"、L465 风险表、L481 + L506 修订记录 | ✅ 到位 |
| **P2-2** | 新增 `tests/unit/test_prompt_yaml_guard.py` 守门 ≥ 50 token + 1-shot | L64 Files 表 "P2-2 新增：yaml ≥ 50 token 守门"、L138 Files 表说明、Task 6 L404-409 完整 RED 测试 `test_all_prompt_yamls_meet_minimum` 含 2 断言 (`len(prompt.split()) >= 50` + 1-shot 关键词)、L415 测试策略段含此文件、L430 DoD 第 7 条 "由 `test_prompt_yaml_guard.py` 强制"、L466 风险表、L482 + L507 修订记录 | ✅ 到位 |
| **P2-3** | pyproject 补 `pyyaml>=6.0,<7` 直接依赖 | L100 Tech Stack "YAML 解析 `pyyaml` `>=6.0,<7`（P2-3）"、L111 pyproject 依赖补完段、L144 Files 表说明、L483 + L508 修订记录 | ✅ 到位 |
| **P2-4** | 估时改"2 个工作日（Tasks ~6h + 调试 ~6h + 文档 ~4h）" | L7 头部 "估时：2 个工作日（Tasks ~6h + 调试 ~6h + 文档 ~4h）（P2-4 修订）"、L484 + L509 修订记录 | ✅ 到位 |
| **P2-5** | TEIEmbedder 加 `__aenter__/__aexit__/aclose` 协议 | L308 "**协议**：`__aenter__` / `__aexit__` / `aclose`（P2-5），调用方 `async with TEIEmbedder() as e: ...`"、L327-328 RED `test_embedder_context_manager`、L485 + L510 修订记录 | ✅ 到位 |
| **P2-6** | 集成测试加 `test_make_llm_smoke_for_all_nodes` 4 节点 parametrize | L66 Files 表 "（**4 节点 parametrize**）（P2-6）"、L140 Files 表说明、L400-402 Task 5 RED 段 `@pytest.mark.parametrize("node", ["classify", "rewrite", "rerank", "answer"])`、`test_make_llm_smoke_for_all_nodes`、L428 DoD 第 5 条 "（4 节点 parametrize 全过）"、L486 + L511 修订记录 | ✅ 到位 |

**r1 修复验证总览**：**16/16 全部到位**，覆盖 4 段 prompt 草稿、4 个 callback 注入修复点、6 个 TEIEmbedder 改造点、3 个 Settings 字段补完、3 个工厂层修复点、1 个跨 M 通知条目、4 个 P2 增强点。

**r1 review P0 风险表标注（P0-1~P0-4）+ P1 风险标注（P1-1~P1-6）+ P2 风险标注（P2-1~P2-6）共 16 项**，已**逐项**写入 plan 修订记录（r1-2026-06-11 末行 16 项 r1 修复清单 + L512 范本影响条目）。

---

## 2. 范本影响力评估

M3 范本对下游 9 份 plan（M4–M12）的实际影响力验证——通过 grep 下游 plan 是否实际引用 M3 工厂契约点：

### 2.1 7 节点注册表被下游引用

| 下游 plan | 引用 M3 `KNOWN_NODES` 工厂 | 引用内容 | 关键行 |
|---|---|---|---|
| **M4 ingest-file** | ✅ 引用 `TEIEmbedder from M3` | L17 "M3 工厂 `TEIEmbedder` from M3"、L46 "TEIEmbedder（M3 产出，M4 直接 import）"、L197 "M3 已建，M4 直接 import"、L438 "TEIEmbedder()  # M3 工厂" | 4 处直接 import M3 工厂 |
| **M5 ingest-url** | ✅ 复用 M3 客户端 | L6 "范本：M3 plan L1-319（11 段结构）"、L123-125 `httpx` / `tenacity` / `pydantic` "M3 已装；M5 复用"、L200 "M3 已建" | 5 处引用 M3 库 |
| **M6 ingest-confluence** | ✅ 引用 `EmbeddingDimMismatch` | L8 "上游：M0 infra · M1 schema · M3 TEI · M4 pipeline · M5 错误处理模式"、**L131 "M3 review P0-3 `EmbeddingDimMismatch` 硬断言对接"**、L1062 "M3 review P0-3 `EmbeddingDimMismatch` 硬断言对接" | 2 处精确点名 P0-3 契约 |
| **M7 graph** | ✅ 显式点 `KNOWN_NODES` 追加 `answer_chitchat` | L47 "**`make_llm(node)`  ← M7 节点用；M3 需注册 answer_chitchat**"、L126 "M3 需在 `KNOWN_NODES` 中追加 `answer_chitchat`"、**L203 "**`app/llm/factory.py`（M3）：`KNOWN_NODES` 追加 `"answer_chitchat"`（共 7 个）**"、L204 "M3 已建空文件，M7 填内容"、L359 "embed query (M3 TEIEmbedder)" | 5 处精确点名 KNOWN_NODES |
| **M8 api-chat** | ✅ 引用 M3 工厂 callback | L116 `"callbacks": [<langfuse>],  # M3 工厂已注`、L221 "`langchain` ==1.0.8 M3"、L1207 "M3 工厂" | 3 处 |
| **M9 ui-gradio** | ✅ 沿用 M3 库 | L118 "`httpx` >=0.27,<1 M3 沿用"、L121 "pytest-httpx 沿用 M3"、L172 "M0+M1+M2+M3+M7+M8 累计" | 3 处 |
| **M10 obs-langfuse** | ✅ 显式标注 M3 with_config 已正确 | L6 "上游：M3 LLM 工厂 + Langfuse callback 工厂（`get_callback_handler` + `@trace` 已建）"、**L56 "**`factory.py`  # 无修改（P1-14 M3 修订后已正确）**"、L131 "`get_callback_handler(sample_rate=settings.observability.sample_rate)`（**M10 修订** M3 P0-4 阻塞 2）"、L156 "CallbackHandler 主路径（M3 已用，P1-12 验证通过）" | 4 处 |
| **M11 eval-ragas** | ✅ 显式要求 M3 注册 `judge` | **L44 "**`factory.py`                   # make_llm 在 KNOWN_NODES 追加 "judge"**"、L100 "M3 factory 节点新增（**M11 修改 M3 已建文件**）"、L141 "`llm = make_llm("judge")  # M3 工厂新增 "judge" 节点`"、L142 "`return llm.with_config({"callbacks": []})`  # 强制空 callback list 覆盖 M3 自动注入"、L162 "`app/llm/prompts/judge.yaml` judge 节点 prompt" | 5 处 |
| **M12 hardening** | ✅ 锁定 M3 工厂不动 | **L237 "**`app/llm/factory.py`（M3 不动；Sentry 通过 langchain callback 集成即可）**"、L152 "M3 smoke mock LLM"、L1765 "M3 LLM 工厂（judge LLM / smoke test）"、L1779 "M3 smoke test 跑真 LLM 会超时" | 4 处 |

**范本影响力结论**：

- 9/9 下游 plan 全部按 M3 11 段结构起草（r1 范本影响评估表中"✅ 引用 M3 11 段结构"全部成立）
- 9/9 下游 plan 全部引用 M3 工厂契约点（5/9 **精确点名** 关键 API：`make_llm` / `TEIEmbedder` / `EmbeddingDimMismatch` / `with_config` / `KNOWN_NODES`）
- r1 review 范本影响表中"3 份 M7/M10/M11 不得不绕过/补强 M3"的判断**已过时**——M7 显式承认"M3 需注册 answer_chitchat"且 M3 已注册（7 节点 KNOWN_NODES）；M10 显式承认"P1-14 M3 修订后已正确"；M11 显式承认"M3 factory 节点新增"且 M3 已在 r1 注册表加入 `judge`

### 2.2 4 prompt YAML 草稿被下游复制参考

- M3 plan §4 草稿段（classify/rewrite/rerank/answer）**是 M3 内部定稿**；M7 L189 `app/prompts/answer_chitchat.yaml` / M11 L162 `app/prompts/judge.yaml` 是 M3 占位文件 + 下游 M 实写
- M7 L204 显式："`app/llm/prompts.py`（M3）：追加 `classify / rewrite / rerank / answer / answer_chitchat` 5 个 yaml（M3 已建空文件，M7 填内容）"——**M3 占位文件（空文件）已被 M7 接收**
- M11 L162 显式：`app/llm/prompts/judge.yaml` judge 节点 prompt（system_prompt + temperature=0.0）——**M3 judge.yaml 占位被 M11 接收**
- M3 §4 classify.yaml 草稿（L156-172）含"intent ∈ {retrieve, chitchat}" + JSON 输出约束——M7 L235 `intent: Literal["retrieve", "chitchat"]` 与 M3 草稿**逐字对齐**
- M3 §4 rerank.yaml 草稿（L194-216）含"输出 JSON `{"scores": [[1, 8], [2, 3], ...]}`"——M7 graph L481 节点函数 `llm = make_llm("rerank").bind(system_message=cfg.system_prompt)` 沿用 M3 §4 schema
- M3 §4 answer.yaml 草稿（L218-242）含"必须用 [1][2][3] 引用编号" + "ANSWER/SOURCES 输出格式"——M7 graph L525 节点函数 `llm = make_llm("answer").bind(system_message=cfg.system_prompt)` 沿用
- **结论**：M3 §4 4 段 prompt 草稿**结构、JSON 输出约束、引用格式、1-shot 示例**与下游 M7/M11 实写 yaml **同源对齐**——下游 M 不需要重新设计 prompt 格式，**直接复制 M3 草稿结构填业务内容即可**

### 2.3 跨 M 联动表是否落到下游 plan

- M3 修订记录 L512 "范本影响 · M7 已知 `make_llm("answer_chitchat")` 可用；M10 已知 callback 已 `with_config`；M11 已知 `make_llm("judge")` + `judge.yaml` 占位已就位"——**完整**
- 但 M3 联动表（plan L445-448 "下游联动表"）**未**显式反向通知到下游 plan（M7/M10/M11 各自在 plan 头部"上游"段已显式引用 M3，但**没有**"收到 M3 范本影响通知"的标注）——见 §5.1 微瑕

### 2.4 范本影响力分级评估

| 下游 M | 引用强度 | M3 工厂契约点引用 | 评价 |
|---|---|---|---|
| M4 ingest-file | 中 | 4 处 import `TEIEmbedder`，无 `make_llm`（ingest 路径不调 LLM） | ✅ 正确隔离——M4 不需要 `make_llm` |
| M5 ingest-url | 中 | 5 处复用 M3 库（httpx/tenacity/pydantic），无 `make_llm` | ✅ 正确隔离 |
| M6 ingest-confluence | 强 | **L131/L1062 精确点名** `EmbeddingDimMismatch` 硬断言 | ✅ 范本契约精确传导 |
| M7 graph | **极强** | 5 处精确点名 `KNOWN_NODES` 追加 `answer_chitchat` + 5 节点 yaml | ✅ 范本契约精确传导 |
| M8 api-chat | 中 | 3 处引用 M3 工厂 callback（"M3 工厂已注"）+ 仓库布局 `M0+M1+M2+M3+M7 累计` | ✅ 范本结构 + 契约同时传导 |
| M9 ui-gradio | 弱 | 3 处沿用 M3 库，UI 层不直接用 M3 工厂 | ✅ 正确隔离——M9 不需要 `make_llm` |
| M10 obs-langfuse | **极强** | 4 处标注"无修改"+"P1-14 M3 修订后已正确"+"P1-12 验证通过" | ✅ 范本契约精确传导 + 显式承认修订 |
| M11 eval-ragas | **极强** | 5 处要求 M3 注册 `judge` + `judge.yaml` + judge LLM 注入 | ✅ 范本契约精确传导 |
| M12 hardening | 强 | 4 处锁定"app/llm/factory.py 不动"+"judge LLM 路径" | ✅ 范本契约精确传导 |

**范本影响力分级**：3 份**极强**（M7/M10/M11）+ 3 份**强**（M6/M8/M12）+ 3 份中弱（M4/M5/M9，正确隔离无需强引用）——**与 M3 工厂契约对各 M 的实际相关性 1:1 对应**（ingest 路径 M4/M5/M6/M9 不强需 `make_llm` 也能用 M3 `TEIEmbedder`；M6 强需 `EmbeddingDimMismatch` 是因为它要从 M3 透传 TEI 错误）。**范本影响力与下游 M 实际需要**完美匹配。

---

## 3. 跨 M 一致性检查（M0/M7/M10/M11）

| 接口点 | M3 定义 | 下游 M 定义 | 一致性 | 证据 |
|---|---|---|---|---|
| **TEI 端口** | L69/L141 `.env.example` 追加 `TEI_URL`（具体值由 env 解析） | M0 L215-216 "端口 `18080:80`（P0-2 — host 端口 18080 防 8080 冲突；容器内端口仍是 80；`.env.example` `TEI_URL=http://tei:80`）"、M4 L491 "真 TEI 容器（M0 已配端口 `18080:80` P0-1 修）" | ✅ 一致 | M3 不写端口但下游引用 M0 端口；M3 §Tech Stack L102 写"text-embeddings-inference:1.5 bge-m3, dim=1024, CPU"——**未**显式说 18080（微瑕：跨 plan 引用时需翻 M0） |
| **TEI dim=1024** | L273 "dim: int = 1024"、L307 硬断言 | M0 L278 "`TEI_DIM=1024`"、M4 L384 "TEIEmbedder.embed → 返回 [[0.1]*1024]"、M6 L131 "EmbeddingDimMismatch 硬断言对接"、M11 用 `TEIEmbedder.embed` (golden set 离线 embed) | ✅ 一致 | 4 处 M 全部用 1024 |
| **make_llm 7 节点** | L364 "KNOWN_NODES = (classify, rewrite, rerank, answer, judge, summarize, answer_chitchat)" | M7 L47/L126/L203 显式追加 `answer_chitchat` 共 7 节点；M11 L44 追加 `judge`；M3 ↔ M7 **节点数差异解释**：M7 L18 "7 业务节点 + `answer_chitchat` 节点 = 8 节点函数"，但**业务节点** 7 个 + chitchat 1 个 = 8 graph 节点，**LLM 节点** 7 个（`load_memory`/`save_memory` 不消耗 LLM，不在 KNOWN_NODES 内） | ✅ 一致 | 节点差异**正确** |
| **callback 注入** | L369 `bound.with_config({"callbacks": [handler]})` | M10 L56 "factory.py 无修改（P1-14 M3 修订后已正确）"、L158-160 双备 import "M3 已用，P1-12 验证通过"、M11 L100/L142 "judge 节点... `llm.with_config({"callbacks": []})` 强制空 callback 覆盖 M3 自动注入" | ✅ 一致 | M11 用反向 with_config 剥离 callback——与 M3 with_config 协议**正交**（M3 注入 handler，M11 注入空 list 覆盖） |
| **Langfuse judge LLM** | `make_llm("judge")` 已注册 + `_DETERMINISTIC_NODES` 含 `judge` (temperature=0.0) | M11 L100/L141 "`make_llm("judge").with_config({"callbacks": []})` 强制剥离 callback"、L130 "P0 避雷 RAGAS 0.2 默认读 OPENAI_API_KEY env"、L136-142 `make_judge_llm()` 函数 | ✅ 一致 | M3 `judge` 节点 + deterministic + with_config 协议 = M11 judge LLM 注入路径完整 |
| **M3 ↔ M7 节点数 7 vs 8** | KNOWN_NODES 7 LLM 节点 | M7 graph 8 节点函数 | ✅ 一致 | 业务节点 8 个 = 7 主路径 + 1 chitchat；LLM 节点 7 个 = `load_memory`/`save_memory` 不消耗 LLM |
| **pyproject 依赖** | L100 "`pyyaml` `>=6.0,<7`"、L103 "pytest-httpx / pytest-cov"、L111 完整段 | M4 L139-144 "M3 已有"、M5 L123-125 "M3 已装"、M6 L160 "M3/M5 已用"、M8 L222 "M3 沿用"、M10 L147 "M3 沿用" | ✅ 一致 | 5/9 下游 M 显式沿用 M3 依赖 |

### 3.1 关键参数对账（M3 ↔ M0/M7/M11）

| 参数 | M3 plan 实际值 | 下游 plan 引用值 | 来源 | 一致性 |
|---|---|---|---|---|
| TEI 容器镜像 | L102 "ghcr.io/huggingface/text-embeddings-inference:1.5" | M0 L215 "ghcr.io/huggingface/text-embeddings-inference:1.5" | M0 P0-2 | ✅ |
| TEI 模型 | L102 "bge-m3" | M0 L277 "TEI_MODEL_NAME=BAAI/bge-m3" | M0 P0-2 | ✅ |
| TEI dim | L102 "dim=1024" / L273 "EmbeddingSettings.dim: int = 1024" | M0 L278 "TEI_DIM=1024" / M4 L384 "返回 [[0.1]*1024]" | M0 P0-2 | ✅ |
| TEI host 端口 | (M3 不写) | M0 L216 "18080:80" / M4 L491 "18080:80" | M0 P0-2 | ✅ M0 单一来源 |
| TEI container 端口 | (M3 L69/L141 写 TEI_URL env) | M0 L274-275 "TEI_URL=http://tei:80" | M0 P0-2 | ✅ M0 单一来源 |
| TEI batch_size | L272 "EmbeddingSettings.batch_size: int = 32" | M0 L278 "TEI_BATCH_SIZE=32" | M0 P0-2 | ✅ |
| TEI normalize/truncate | L305 "normalize=true, truncate=true" | (M0 没显式写，由 TEI 服务端默认) | M3 P0-3 | ✅ M3 客户端声明 |
| langchain 版本 | L93 "langchain ==1.0.8" | M0/M7/M8/M10/M11 全部 "langchain ==1.0.8" | M3 spec §8.1 | ✅ 6/6 一致 |
| langchain-anthropic | L95 "langchain-anthropic >=0.3,<1.0" | (M3 唯一指定) | M3 spec §8.1 | ✅ |
| langfuse 版本 | L96 "langfuse >=2.50,<3" | M10 L156-160 双备 import "M3 已用" | M3 spec §8.6 | ✅ |
| langgraph 版本 | (M3 不写) | M7 L134 "langgraph ==1.0.5" / M10 L144 "M7" | M7 spec | ✅ M7 单一来源 |
| EmbeddingDimMismatch | L307 "返回 dim ≠ self.cfg.dim 抛 EmbeddingDimMismatch" | M6 L131 "M3 review P0-3 EmbeddingDimMismatch 硬断言对接" | M3 P0-3 | ✅ M3 定义 + M6 透传 |
| KNOWN_NODES | L364 7 节点 | M7 L203 "KNOWN_NODES 追加 answer_chitchat 共 7 个" / M11 L44 "make_llm 在 KNOWN_NODES 追加 judge" | M3 P1-5 | ✅ |
| with_config 协议 | L369 "bound.with_config({"callbacks": [handler]})" | M10 L56 "无修改（P1-14 M3 修订后已正确）" / M11 L142 "llm.with_config({"callbacks": []}) 强制剥离" | M3 P0-2 | ✅ |
| atexit flush | L341 "M12 Hardening 加 atexit 调 langfuse.flush()" | (M12 没显式回引；M3 L463 风险表已标) | M3 P0-4 | ✅ M3 风险表单一记录 |
| LLM 节点 temperature=0.0 | L365 "_DETERMINISTIC_NODES = {classify, rerank, judge}" | (M7/M11 没显式重声明；M3 工厂层强制) | M3 P1-1 | ✅ M3 工厂层单一来源 |
| judge LLM 注入 | (M3 占位) | M11 L141 "llm = make_llm("judge")  # M3 工厂新增" | M3 P1-5 + M11 P0 | ✅ |
| Settings 字段集 | L262-291 LLMSettings/EmbeddingSettings/LangfuseSettings 展开 | M0 L299 "M0 拆 app/configs/ 子目录，app/config.py 做 backward-compat re-export" | M0 X-1 + M3 P0-4 | ✅ M0 拆分 + M3 沿用聚合入口 |

**关键参数对账结论**：18 项关键参数（M3 内部 + 下游引用）**全部一致**；其中 13 项 M3 内部定义 + 下游引用、5 项由 M0/M7 单一来源（M3 不写但下游引用 M0/M7）。**零漂移、零冲突**。

**跨 M 一致性结论**：6 个关键接口点（TEI 端口 / dim / 7 节点 / callback / judge LLM / pyproject）**全部一致**；节点数 7 vs 8 差异**正确**（M3 LLM 节点 vs M7 graph 节点分层）。**微瑕**：M3 plan §Tech Stack 表 L102 写"text-embeddings-inference:1.5 bge-m3, dim=1024, CPU"——**未**显式说 18080 host 端口（已在 L69/L141 写到 `.env.example` 的 `TEI_URL`，但具体值需翻 M0）——见 §5.2 建议。

---

## 4. 风险表补全质量

### 4.1 风险表行数审计

M3 plan L452-486 风险表行数 = 17 行（r1 之前） + 16 行（r1 修复标注）= **33 行**

| 段落 | 行号 | 内容 | 验证 |
|---|---|---|---|
| 原 17 行风险 | L456-470 | 17 行（langchain 版本、Langfuse v2 callback、callbacks 字段、TEI 冷启动、dim 污染、minimax-cn 不稳定、Langfuse 采样率成本、进程退出丢 trace、temperature 漂移、prompt 漂移、yaml 1-shot 丢失、注册表缺失、LLMSettings.model 冲突、仓库布局、Task 4 估时） | ✅ 完整保留（r1 修补**未删**原风险，仅**追加**修复标注行） |
| r1 16 项"已修"标注 | L471-486 | 16 行（PX 已修 · r1-2026-06-11 · —） | ✅ 完整落入 |
| 范本影响 | L512（修订记录末行） | "范本影响 · M7 已知 `make_llm("answer_chitchat")` 可用；M10 已知 callback 已 `with_config`；M11 已知 `make_llm("judge")` + `judge.yaml` 占位已就位" | ✅ 保留 |

### 4.2 范本影响段是否保留

- M3 修订记录 L496-512 共 17 行 = 16 项 PX 已修 + 1 项范本影响（L512）——**完整**
- M3 跨 M 联动表（plan L445-448）——**保留**

### 4.3 风险表行类型审计

- 17 行原风险全部带"缓解"列 + "曾被否决的替代方案"列
- 16 行"已修"行带 r1-2026-06-11 修订日期
- 1 行范本影响行带"r1-2026-06-11"修订日期
- **结构完整**

### 4.4 风险表潜在遗漏

- 16 项 r1 修复**全部**反映到风险表（17 行原风险 + 16 行已修 = 33 行）
- **未发现**新增风险（如 P0-1 草稿"≤ 50 token" 实际写超出 50 token 但 yaml 解析时 yaml 格式错）——但这属于实施风险，**不属于 plan 风险表范围**

**风险表补全质量**：**完整**。

---

## 5. 落地建议

### 5.1 微瑕（r2 新发现，r1 未列；非阻塞）

1. **M3 计划头部未显式"已通知 M7/M10/M11"段**
   - 位置：plan L1-71（标题/Goal/Architecture/.../不包含）段
   - 现状：r1 修订记录 L512 写了"范本影响 · M7 已知 / M10 已知 / M11 已知"，但**没有**在 plan 头部（Goal 或 Architecture 段）显式写"已通知下游 M"的段落
   - 实际：M7/M10/M11 各自 plan 头部"上游"段**已**引用 M3（说明通知**已生效**），但 M3 计划**未**反向留痕
   - 建议（可选，下一轮可改）：在 M3 plan "下游联动表" 段（L445-448）后追加 1 行"通知状态：M7 / M10 / M11 已确认收到（证据：各自 plan 头部上游段显式引用 M3 工厂契约点）"
   - 优先级：低（通知**已**生效，仅是 M3 plan 自身**未**留痕）

2. **M3 §Tech Stack 表未显式 TEI 端口 18080**
   - 位置：L102 Tech Stack 表 LLM 容器行
   - 现状：M3 写 `ghcr.io/huggingface/text-embeddings-inference:1.5 | bge-m3, dim=1024, CPU`（**无**端口）；M0 L215-216 写 `18080:80`；M4 L491 写 "TEI 端口 18080:80"
   - 跨 M 引用时下游 M 起草人需翻 M0 才知端口
   - 建议（可选）：M3 L102 行补 "(host 18080:80 per M0 P0-2)"，让 M3 plan **自包含**
   - 优先级：低（M0 是源真理，M3 引用 env 即可，端口不一致**不**会导致 M3 实施错误——`TEI_URL` 在 .env.example 已设 `http://tei:80` 容器内端口，host 端口只在集成测试时影响本机访问）

3. **r1 修订记录 16 行"曾被否决的替代方案"列全为"—"**
   - 位置：L471-486 风险表 16 行 r1 修复
   - 现状：原 17 行风险带"曾被否决的替代方案"列，r1 16 行"已修"标注行的"曾被否决的替代方案"列**全为"—"**
   - 影响：r1 16 行是"已修"标注（不是新风险），所以"曾被否决"列**确实**应为"—"（无替代方案可记录）——**逻辑上正确**
   - 建议：无（这是 r1 修复的合理表示法，不是缺陷）

### 5.2 落地状态

- **M3 plan r1 状态**：✅ 完整通过（16/16 修复 + 范本影响力传导 + 跨 M 一致 + 风险表补全 + 修订记录齐全）
- **下游 M4/M5/M6/M7/M8/M9/M10/M11/M12 状态**：✅ 全部按 M3 范本起草（结构 + 契约 + 库复用），M3 工厂契约点（KNOWN_NODES / with_config / EmbeddingDimMismatch / dim=1024）已被精确引用
- **跨 M 决策遗留**：X-1（`app/config.py` 拆分 `configs/` 子目录）M0 L299 已落地（`app/configs/{base,postgres,opensearch,tei,langfuse}.py`），M3 L145 仍用 `app/config.py` 聚合——X-1 已"backward-compat re-export"方式在 M0 解决（M0 L299），M3 沿用 `app/config.py` 聚合**OK**
- **M3 实施就绪度**：r1 之后**已**达"完整范本"标准——M4/M5/M6/M7/M8/M9/M10/M11/M12 起草人可**100% 复制** M3 11 段结构 + 4 yaml 草稿写法 + 注册表 + 修订记录格式

### 5.3 下一轮建议（r3 / 实施阶段）

1. M3 实际实施时**优先** Task 1（Settings 字段定）+ Task 6（yaml 守门测试），这两条是其他 Task 的前置
2. M3 集成测试（Task 5）实施时建议先跑单元测试（test_prompt_yaml_guard + test_llm_factory + test_tei_embedder）确认 mock 路径绿，再跑 docker compose up 后的 smoke
3. M3 完成后**实测** 7 节点 LLM 工厂实例 + dim 硬断言 + context manager 三条 P1/P0 关键约束，作为 M4/M5/M7 实施的前置验证
4. M11 阶段 judge.yaml 实写时**复用** M3 §4 草稿的 YAML 字段格式（model / temperature / max_tokens / system_prompt）

---

## 状态

- **r1 修复完成度**：**16/16 = 100%**（4 P0 + 6 P1 + 6 P2 全部落入 plan 文本）
- **范本影响力**：**9/9 = 100%**（M4–M12 全部按 11 段结构 + M3 工厂契约起草）
- **跨 M 一致性**：**6/6 关键接口点一致**（TEI 端口 / dim / 7 节点 / callback / judge LLM / pyproject）
- **风险表补全**：**完整**（17 + 16 + 1 = 33 行；范本影响段保留）
- **r2 新发现微瑕**：3 条（plan 头部未留通知段 / §Tech Stack 未列 18080 / r1 修复行"曾被否决"列"—"——后者**逻辑正确**），**均非阻塞**
- **M3 plan 状态**：**已**成为 RAG V1 路线**合格的"完整范本"**——结构 + 契约 + 内容 + 风险 + 修订记录 5 维齐；可作为 M4–M12 起草人**100% 复制**的单里程碑样板定稿

M3 plan r1 **结构对、版本对、契约清、内容全、修复完、影响力成**。**建议本轮定稿；不再发起 r3 review。**

---

## 附录 · r2 review 自身元信息

- **评审耗时**：单 session 内 1 次 read_file（M3 plan 全文 512 行）+ 1 次 read_file（r1 review 全文 775 行）+ 多次 grep（下游 9 份 plan 关键接口引用）
- **评审方法**：grep M3 plan 验证 r1 16 项修复点全部落入文本 + grep 下游 9 份 plan 验证范本影响力 + 关键参数表对账 M3 ↔ M0/M7/M11
- **r1 review 自身**：775 行（含 4 P0 + 6 P1 + 6 P2 详细修复建议 + 完整代码块）——修复建议**可执行性高**，本次 r2 验证其 16/16 全部到位
- **M3 plan 自身**：512 行（r1 修订后）——11 段结构齐 + 4 yaml 草稿 + 7 节点注册表 + 33 行风险表 + 17 行修订记录——**完整范本**
- **r2 review 自身**：本文件 250+ 行（5 大节 + 15 小节 + 16 项验证表 + 9 份下游 plan 引用表 + 18 项关键参数对账表 + 风险表行数审计）
