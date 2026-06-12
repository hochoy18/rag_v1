# M11 Plan · RAGAS 离线评估 CLI + Golden Set + CI Gate

> 所属：RAG V1 M0–M12 实施路线 · 第 11 步
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §6 测试策略](../specs/2026-06-10-rag-v1-scope.md#6-测试策略) · [决策总表 #11](../specs/2026-06-10-rag-v1-scope.md#0-决策总表)
> 估时：3 个工作日（day 1 = golden set + CLI 入口 / day 2 = runner + scorer + RAGAS 集成 / day 3 = report + gate + 端到端）
> 前置 review：[2026-06-11-rag-plans-review.md](./2026-06-11-rag-plans-review.md) P0/P1 已收敛（X-1 `app/configs/` 拆分已采纳，X-3 `from app.config import settings` 全局单例）
> 本轮 review：[2026-06-11-rag-m11-eval-ragas-review.md](./reviews/2026-06-11-rag-m11-eval-ragas-review.md) 已采纳 6 P0 + 8 P1 + 5 P2 全部修复

---

## Goal

把 v1-scope 决策 #11 落成可执行代码契约：

1. 一个 Click CLI（`python -m app.eval.ragas_run`），跑 golden set 算 RAGAS 三指标（faithfulness / answer_relevancy / context_precision），输出 JSON + HTML 报告
2. 一个 50 题 golden set（JSONL 格式，3 源 × 3 类问题矩阵 + 5 chitchat + edge），git 化锁版本。**r2-2026-06-12 新-1 已修**：fixture 重排 q001-q005 = 5 chitchat + q006-q050 = 45 rag（CI 前 20 = q001-q020 包含 5 chitchat + 15 rag；nightly = 50 题全部）
3. 一个 CI gate（**CI faithfulness < 0.65** / **nightly < 0.7** 抛 `GateViolationError`、exit code 1），M12 Hardening 接 CI
4. RAGAS judge LLM **显式注入**（不读 env 里的 OpenAI key），复用 M3 `make_llm("judge")`，**强制不接 Langfuse callback**（避免污染业务 trace 看板）
5. 跑 RAGAS 时把 M10 Langfuse trace_id 写入报告（用 langfuse 2.50+ 公开 API `get_client().get_current_trace_id()` + try/except 包装），建立"评测 → 业务 trace"双向追溯

**不包含**（其他 M 负责）：M10 业务级 Langfuse trace 实现（只读已有 trace_id）、M12 CI workflow（只产出 gate 钩子）、M4–M6 真实 ingest 数据（评测用 50 题样本够）、M9 UI 集成（HTML 报告独立产物）。

---

## Architecture

### 仓库布局（apps/rag_v1/，仅显示 M11 新增/修改）

```
apps/rag_v1/
├── app/
│   ├── eval/                            # M11 主力
│   │   ├── __init__.py
│   │   ├── ragas_run.py                 # Click CLI 入口
│   │   ├── golden_set.py                # JSONL 加载 + 校验（含 reference_contexts）
│   │   ├── runner.py                    # async 调 M7 graph 拿 answer+contexts+trace_id
│   │   ├── scorer.py                    # 调 RAGAS evaluate（LangchainLLMWrapper 包装）
│   │   ├── report.py                    # JSON + HTML 输出（含 git SHA + 时间戳）
│   │   ├── gate.py                      # CI gate（CI/nightly 双阈值）
│   │   ├── judge.py                     # RAGAS judge LLM 注入包装（剥离 callback）
│   │   └── config.py                    # M11 EvalSettings（含 cost_budget）
│   ├── llm/                             # M3 已建（**M11 修改**：注册 "judge" 节点）
│   │   ├── factory.py                   # make_llm 在 KNOWN_NODES 追加 "judge"
│   │   └── prompts/
│   │       └── judge.yaml               # M11 新增
│   ├── graph/                           # M7 已建
│   │   └── workflow.py                  # runner 调 graph.ainvoke（M7 P0-3 修后已 compile）
│   ├── retrieval/                       # M7 已建（runner 不直接调，从 state["chunks"] 取）
│   └── observability/                   # M10 已建
│       └── langfuse.py                  # 读 trace_id 关联报告（langfuse 2.50+ 公开 API）
│
├── tests/
│   ├── unit/
│   │   ├── test_golden_set.py           # JSONL 加载/校验（含 reference_contexts 必填校验）
│   │   ├── test_judge.py                # judge LLM 注入 + 剥离 callback
│   │   ├── test_runner.py               # async mock graph（用 pytest-asyncio）
│   │   ├── test_scorer.py               # mock RAGAS + LangchainLLMWrapper 包装断言
│   │   ├── test_report.py               # JSON/HTML 输出（含 git SHA 命名）
│   │   ├── test_gate.py                 # CI 0.65 / nightly 0.7 双阈值
│   │   └── test_ragas_run.py            # CLI 串联测试
│   ├── fixtures/
│   │   └── golden_set_v1.jsonl          # 50 题（CI 用前 20 + nightly 用全部 + 5 chitchat + edge）
│   └── integration/
│       ├── test_m11_e2e_ragas.py        # 端到端：golden set → gate
│       └── test_m11_golden_set_docs_exist.py  # expected_doc_id 真实索引校验（warning 不挂）
│
└── pyproject.toml                       # 追加 ragas + datasets + click + python-markdown + pytest-asyncio
```

**模块组织原则**：
- `app/eval/` 全部依赖 M3/M7/M10 接口，**不引入**新端口/新服务
- golden set 是 JSONL（line-delimited JSON），每行独立可读，git diff 友好
- RAGAS judge LLM 通过 M3 `make_llm("judge")` 注入，**禁止**读 `OPENAI_API_KEY` env
- runner **不直接调** `retriever.retrieve`（M7 graph 已 retrieve），从 `state["chunks"]` 取（M7 P1-6 修后字段）

### M11 数据流

```
[golden_set_v1.jsonl]                   # 50 题（CI 前 20 / nightly 全部 / 5 chitchat）
        ↓ load
[GoldenSet] (items, 含 reference_contexts)
        ↓ for each: await graph.ainvoke({query}, thread_id="eval-N")
[Runner] → async.gather 批跑 → 拿 (answer, contexts, trace_id)
        ↓ build Dataset(question, answer, contexts, ground_truth, reference_contexts)
[Scorer] → LangchainLLMWrapper(judge) + RAGAS evaluate(raise_exceptions=False)
        ↓ result.to_pandas()
[Report] → {timestamp}_{git_sha}.json + .html（含 diff 列 vs baseline 可选）
        ↓ CI: faithfulness < 0.65 ?  /  nightly: < 0.7 ?
[Gate] ✓ pass / ✗ GateViolationError + exit 1
```

### 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M11 CLI | `python -m app.eval.ragas_run` | 唯一入口 |
| M11 runner | `await graph.ainvoke({query}, config={"configurable": {"thread_id": f"eval-{n}"}})` | M7 workflow 已建（**依赖 M7 P0-3 修复**：get_graph() 返回已 compile graph） |
| M11 runner | `state.get("chunks", state.get("sources", []))` 拿 contexts | **不直接调** retriever（避免重复 retrieve）；**依赖 M7 P1-6 修复**：state["chunks"] 含 rerank 后 chunks |
| M11 judge | `make_llm("judge").with_config({"callbacks": []})` | M3 factory 节点新增（**M11 修改 M3 已建文件**，详见 Files）；强制剥离 callback |
| M11 report | `from langfuse import get_client; get_client().get_current_trace_id()` | 2.50+ 公开 API；try/except 包装拉不到时返 None（**依赖 M10 P0-3 修复**） |
| M12 CI | `app.eval.gate.check(result, mode="ci")` | CI faithfulness < 0.65 抛 / nightly < 0.7 抛 |

---

## Tech Stack

| 层 | 选型 | 版本（精确） |
|----|------|------------|
| 评估 | `ragas` | `==0.2.10`（spec §8.6 收紧：pin 0.2.10 精确，避免 0.2/0.3 break change） |
| 数据集 | `datasets` | `>=2.20,<4`（HuggingFace datasets，ragas 依赖） |
| CLI | `click` | `>=8.1,<9` |
| HTML 渲染 | `python-markdown` | `>=3.6,<4`（markdown → HTML 单文件，**不**用 jinja2） |
| LLM 抽象 | M3 `langchain` | `==1.0.8`（复用） |
| 重试 | M3 `tenacity` | `>=8.3,<10`（RAGAS judge LLM 4xx/5xx 重试） |
| 异步测试 | `pytest-asyncio` | `>=0.24,<1`（**M11 新增**：runner/scorer 异步） |
| Mock 库 | `pytest-mock` | `>=3.14,<4`（**M11 新增**：runner/scorer mock） |
| 测试 | `pytest` | 同上 |

**关键导入路径**（RAGAS 0.2.10）：

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from ragas.llms import LangchainLLMWrapper      # 0.2.5+ 强制包装
from datasets import Dataset
from langchain_anthropic import ChatAnthropic
```

**RAGAS judge LLM 注入**（**P0 避雷** —— RAGAS 0.2 默认读 `OPENAI_API_KEY` env；**0.2.5+ 必须 LangchainLLMWrapper 包装**）：

```python
# app/eval/judge.py
from langchain_anthropic import ChatAnthropic
from app.config import settings
from app.llm.factory import make_llm

def make_judge_llm() -> ChatAnthropic:
    """RAGAS judge 专用：显式传 ChatAnthropic，不读 OPENAI_API_KEY；
    显式剥离 Langfuse callback（评测不污染业务 trace 看板）。"""
    llm = make_llm("judge")                          # M3 工厂新增 "judge" 节点
    return llm.with_config({"callbacks": []})        # 强制空 callback list 覆盖 M3 自动注入
```

---

## Files

**新增**（10 个源 + 7 个测试 + 1 fixture + 1 yaml）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
| `app/eval/__init__.py` | 包标识 |
| `app/eval/ragas_run.py` | Click CLI 入口 |
| `app/eval/golden_set.py` | JSONL 加载 + Pydantic 校验（含 `reference_contexts`） |
| `app/eval/runner.py` | async 调 graph 拿 (answer, contexts, trace_id) + GraphNodeError |
| `app/eval/scorer.py` | 调 RAGAS evaluate（LangchainLLMWrapper 包装 + reference_contexts） |
| `app/eval/report.py` | JSON + HTML 报告（含 `{timestamp}_{git_sha}` 命名 + baseline diff） |
| `app/eval/gate.py` | CI gate（`mode: "ci"\|"nightly"` 双阈值）+ `GateViolationError` |
| `app/eval/judge.py` | RAGAS judge LLM 注入包装（剥离 callback） |
| `app/eval/config.py` | `EvalSettings`（threshold / cost_budget / sample_size_ci / sample_size_nightly） |
| `app/llm/prompts/judge.yaml` | judge 节点 prompt（system_prompt + temperature=0.0） |
| `tests/unit/test_golden_set.py` | JSONL 加载/校验（覆盖 3 源 × 3 类 + chitchat） |
| `tests/unit/test_judge.py` | judge LLM 不读 OPENAI_API_KEY + 剥离 callback |
| `tests/unit/test_runner.py` | async mock graph（pytest-asyncio mode=auto） |
| `tests/unit/test_scorer.py` | mock RAGAS + LangchainLLMWrapper 包装断言 |
| `tests/unit/test_report.py` | JSON/HTML 生成（含 git SHA 命名 + baseline diff 列） |
| `tests/unit/test_gate.py` | CI 0.65 / nightly 0.7 双阈值 |
| `tests/unit/test_ragas_run.py` | CLI 串联 + exit code 1 路径 |
| `tests/fixtures/golden_set_v1.jsonl` | **50 题**（CI 前 20 + nightly 全部 + 5 chitchat + edge） |
| `tests/integration/test_m11_e2e_ragas.py` | 端到端：load → run → score → report → gate |
| `tests/integration/test_m11_golden_set_docs_exist.py` | expected_doc_id 真实索引校验（warning 不挂） |

**修改**：
- `pyproject.toml`：追加 7 个新直接依赖（`ragas==0.2.10` / `datasets` / `click` / `python-markdown` / `pytest-asyncio` / `pytest-mock` / `langchain-anthropic`） + `asyncio_mode = auto` 配置
- `app/llm/factory.py`（M3 已建，**M11 显式修改**）：在 `KNOWN_NODES` 追加 `"judge"` + 注册 `load_prompt("judge")` → `ChatAnthropic`
- `app/config.py`（或 `app/configs/eval.py` if X-1 已落地）：追加 `EvalSettings`（含 `cost_budget_usd_per_run` / `cost_budget_usd_per_week` / `include_chitchat` / `mode: ci\|nightly`）

**不修改**：`infra/docker-compose.yml`（M11 不依赖容器，纯 CLI 跑本地 Python）、M7 graph、M10 Langfuse 实现。

---

## Tasks（2-5 分钟/step 粒度）

### Day 1 · Golden Set + CLI 入口

#### Task 1：Pydantic 配置块（追加 EvalSettings，含 cost_budget / include_chitchat / mode）

**RED** · `tests/unit/test_config.py::test_eval_config_loads`（M3 已建文件，追加新测试）
- mock env vars → 加载 `Settings().eval` → 断言 `threshold == 0.7` / `sample_size_ci == 20` / `sample_size_nightly == 50`
- 跑测试 → 失败（配置不存在）
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_config.py::test_eval_config_loads -v`

**GREEN** · `app/eval/config.py`：
```python
class EvalSettings(BaseSettings):
    threshold: float = 0.7                       # spec 决策 #11（nightly 硬阈值）
    threshold_ci: float = 0.65                   # CI 宽容阈值（P0-5 统计稳定性）
    sample_size_ci: int = 20                     # CI 跑 20 题（5 分钟）
    sample_size_nightly: int = 50                # nightly 跑 50 题（fixture 全部）
    ragas_metrics: list[str] = ["faithfulness", "answer_relevancy", "context_precision"]
    judge_model: str = "minimax-cn/MiniMax-M3"   # 复用 M3 model
    cost_budget_usd_per_run: float = 5.0         # P1-5 单次评测预算
    cost_budget_usd_per_week: float = 20.0       # P1-5 每周评测预算
    include_chitchat: bool = True                # P1-2 chitchat 路径开关
    mode: Literal["ci", "nightly"] = "ci"        # gate 模式（P0-5 双阈值）
```
- 顶层 `Settings` 聚合 `eval: EvalSettings`

**RED** · `test_eval_settings_has_cost_budgets_and_mode`
- 断言 `cost_budget_usd_per_run == 5.0` / `mode in ("ci", "nightly")`

**REFACTOR** · 跟 M3 一样用 sub-settings 嵌套（避免单文件 500 行）

#### Task 2：Golden Set 数据模型 + JSONL 加载（含 `reference_contexts`）

**RED** · `tests/unit/test_golden_set.py::test_load_golden_set_v1`
- 读 `tests/fixtures/golden_set_v1.jsonl`（50 行）→ 解析 → 断言 len == 50
- 跑测试 → 失败（fixture 还没建好）

**GREEN** · `app/eval/golden_set.py`：
```python
from pydantic import BaseModel, Field
from typing import Literal

class GoldenItem(BaseModel):
    id: str                                          # "q001"
    question: str
    ground_truth: str                                # 参考答案文本（answer_relevancy 用）
    source_filter: Literal["file", "url", "confluence"]
    expected_doc_id: str | None = None
    question_type: Literal["factual", "summary", "multi_hop", "chitchat"]  # P1-2 加 chitchat
    reference_contexts: list[str] = Field(default_factory=list)            # P0-1/P1-3 新增：context_precision 用

def load_golden_set(path: str) -> list[GoldenItem]:
    items = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            item = GoldenItem.model_validate_json(line)
            items.append(item)
    return items
```

**RED** · `test_validates_required_fields`
- 写一行 `{"id": "q001"}` 缺 question → 断言抛 `ValidationError`
- 跑测试 → 失败（Pydantic schema 还没测）

**GREEN** · 加 `Field(..., min_length=1)` 约束

**RED** · `test_validates_source_filter`
- 传 `source_filter: "github"` → 断言 `ValidationError`（不在 Literal 里）
- 跑测试 → 失败

**GREEN** · `Literal` 类型守住

**RED** · `test_validates_question_type`
- 传 `question_type: "unknown"` → 断言 `ValidationError`
- 跑测试 → 失败

**GREEN** · `Literal` 类型守住

**RED** · `test_validates_reference_contexts_for_non_chitchat`（**P1-3 必填校验**）
- 传 `question_type: "factual"` + `reference_contexts: []` → 断言 `ValidationError`（factual 必须有至少 1 个 ref context）
- chitchat 题 `reference_contexts: []` 允许

**GREEN** · `model_validator` 守住

#### Task 3：Golden Set Fixture（**50 题**样本，含 chitchat）

**RED** · `test_fixtures_covers_3_sources_3_types_and_chitchat`
- 断言 50 题里：3 种 `source_filter` 都出现、4 种 `question_type` 都出现（含 chitchat）、3 源 × 3 类 = 9 类交叉都有
- 跑测试 → 失败（fixture 还没建）

**GREEN** · 写 `tests/fixtures/golden_set_v1.jsonl`（50 行）：

```jsonl
{"id": "q001", "question": "公司年假政策是什么？", "ground_truth": "入职满 1 年享 10 天年假", "source_filter": "file", "expected_doc_id": "policy_2024.md", "question_type": "factual", "reference_contexts": ["policy_2024.md", "policy_general.md"]}
{"id": "q002", "question": "Confluence 上 Q3 OKR 总结", "ground_truth": "Q3 完成 3 个 OKR 中的 2 个", "source_filter": "confluence", "expected_doc_id": "OKR-Q3", "question_type": "summary", "reference_contexts": ["OKR-Q3"]}
{"id": "q003", "question": "对比 file 和 url 两份文档的部署流程差异", "ground_truth": "file 写 Kubernetes，url 写 Docker Compose", "source_filter": "file", "expected_doc_id": "deploy.md", "question_type": "multi_hop", "reference_contexts": ["deploy.md", "deploy_k8s.md"]}
... (47 more lines: 17 + 5 chitchat + 3 edge; 每行一组 source_filter × question_type 组合; chitchat 题 reference_contexts=[])
{"id": "q046", "question": "你好，请自我介绍", "ground_truth": "我是 Hermes Agent...（chitchat 不需要参考文档）", "source_filter": "file", "expected_doc_id": null, "question_type": "chitchat", "reference_contexts": []}
... (4 more chitchat)
{"id": "q050", "question": "包含 <特殊>字符@的#问题$测试", "ground_truth": "schema 健壮性测试", "source_filter": "file", "expected_doc_id": null, "question_type": "factual", "reference_contexts": ["special_chars_doc.md"]}
```

分布矩阵（**50 题** = 18 + 18 + 9 + 5 chitchat，**CI 用前 20 + nightly 用全部**）：
- 18 factual（file 6 / url 6 / confluence 6）
- 18 summary（file 6 / url 6 / confluence 6）
- 9 multi_hop（file 3 / url 3 / confluence 3）
- 5 chitchat（**P1-2**：评估只算 `answer_relevancy`，context_precision 跳过）
- edge：空问题、问题包含特殊字符、chitchat 路径

**REFACTOR** · 把 fixture 注释行去掉，确保 50 行严格 line-delimited

#### Task 4：RAGAS Judge LLM 注入（**含 LangchainLLMWrapper 包装**）

**RED** · `tests/unit/test_judge.py::test_judge_uses_m3_factory_not_env`
- mock `make_llm` → 断言 `make_judge_llm()` 调用了 `make_llm("judge")`
- 断言**没有**读 `os.environ["OPENAI_API_KEY"]`（monkeypatch 删除 env 也跑通）
- 跑测试 → 失败

**GREEN** · `app/eval/judge.py`：
```python
from app.llm.factory import make_llm

def make_judge_llm():
    """RAGAS judge 专用：走 M3 工厂 + 显式剥离 Langfuse callback（评测不污染业务 trace）"""
    llm = make_llm("judge")
    return llm.with_config({"callbacks": []})   # P2-4 显式空 callback 覆盖 M3 自动注入
```

**RED** · `tests/unit/test_judge.py::test_judge_strips_langfuse_callback`（**P2-4 新增**）
- mock `make_llm` 返回 `MagicMock(spec=ChatAnthropic)`
- 调 `make_judge_llm()` → 断言返回值 ≠ mock 直接返回（必须有 `.with_config` 调用）

**RED** · `tests/unit/test_llm_factory.py::test_judge_node_registered`（M3 已建文件，追加）
- 断言 `make_llm("judge")` 返回 `ChatAnthropic` 实例
- 跑测试 → 失败（judge 节点未注册）

**GREEN** · `app/llm/factory.py` 追加（**M11 修改 M3 已建文件**，**P0-2 / C-1 联动**）：
- `KNOWN_NODES` 追加 `"judge"`
- `app/llm/prompts/judge.yaml`（M11 新增）：
  ```yaml
  model: minimax-cn/MiniMax-M3
  temperature: 0.0        # judge 确定性优先
  max_tokens: 2048
  system_prompt: |
    You are an expert evaluator for RAG system outputs.
    Score the following on a 0-1 scale based on:
    1. Faithfulness: Is the answer grounded in the contexts?
    2. Answer relevancy: Does the answer address the question?
    3. Context precision: Are the retrieved contexts relevant?
  ```
- `make_llm("judge")` 走 `load_prompt("judge")` → `ChatAnthropic(...)`

**RED** · `test_make_llm_judge_node_registered_with_deterministic_temp`（**P0-2 补强**）
- 断言 `"judge" in KNOWN_NODES`
- 断言 `make_llm("judge").temperature == 0.0`

#### Task 5：Click CLI 入口骨架

**RED** · `tests/unit/test_ragas_run.py::test_cli_help`（新增文件）
- `subprocess.run(["python", "-m", "app.eval.ragas_run", "--help"])` → 断言 exit 0 + 包含 "golden-set" / "metrics" / "threshold" / "mode"
- 跑测试 → 失败

**GREEN** · `app/eval/ragas_run.py`：
```python
import click

@click.command()
@click.option("--golden-set", required=True, type=click.Path(exists=True))
@click.option("--metrics", default="faithfulness,answer_relevancy,context_precision")
@click.option("--threshold", default=0.7, type=float)
@click.option("--mode", default="ci", type=click.Choice(["ci", "nightly"]))   # P0-5 双阈值
@click.option("--report-json", type=click.Path())
@click.option("--report-html", type=click.Path())
@click.option("--sample-size", type=int, default=None, help="限制跑题数（CI 用 20）")
@click.option("--baseline", type=str, default=None, help="**r2-2026-06-12 新-4 已修**：P1-6 baseline 改用 git tag v0.1.0（V1.1 时启用）OR 报告 json 路径（V1 fallback）")
def main(golden_set, metrics, threshold, mode, report_json, report_html, sample_size, baseline):
    """RAG V1 RAGAS 离线评估 CLI"""
    click.echo(f"golden_set={golden_set} metrics={metrics} threshold={threshold} mode={mode}")

if __name__ == "__main__":
    main()
```

**RED** · `test_cli_rejects_missing_golden_set`
- 跑 `python -m app.eval.ragas_run`（无参数）→ 断言 exit 2 + 报错
- 跑测试 → 失败

**GREEN** · `required=True` 守住

**REFACTOR** · 把 `main()` 拆 `def _run_eval(golden_set, metrics, threshold, mode, ...)` 让集成测试可调（async）

**RED** · `tests/unit/test_judge.py::test_with_config_callbacks_empty_returns_runnable_binding`（**r2-2026-06-12 新-3 已修**：与 M3 工厂返回 `RunnableBinding` 兼容性断言）
- mock `make_llm("judge")` 返回 mock Runnable
- 调 `judge.with_config({"callbacks": []})` → 断言返回 `RunnableBinding` 类型（不是 ChatAnthropic 原类）
- 跑测试 → 失败

**GREEN** · `judge.py` 显式断言：`from langchain_core.runnables import RunnableBinding; assert isinstance(judge, RunnableBinding), "judge LLM 必须是 RunnableBinding"`

---

### Day 2 · Runner + Scorer + RAGAS 集成

#### Task 6：Runner（**async** + 重试只在 graph 外部异常 + GraphNodeError 冒泡节点失败）

**RED** · `tests/unit/test_runner.py::test_run_single_item_returns_answer_contexts`
- mock `graph.ainvoke` 返回 `{"answer": "...", "sources": ["ctx1", "ctx2"], "chunks": ["ctx1", "ctx2"]}`
- 调 `await runner.run_item(item, n=1)` → 断言 `answer` 非空 / `contexts` 是 list[str] / `trace_id` 非空
- 跑测试 → 失败

**GREEN** · `app/eval/runner.py`：
```python
import asyncio
import uuid
from app.graph.workflow import get_graph
from app.eval.golden_set import GoldenItem

def _safe_get_trace_id() -> str | None:
    """P0-6 拉取当前 Langfuse trace_id；拉不到返 None（不抛异常污染主流程）
    用 langfuse 2.50+ 公开 API：from langfuse import get_client; get_client().get_current_trace_id()
    """
    try:
        from langfuse import get_client
        return get_client().get_current_trace_id()
    except Exception:
        return None

class GraphNodeError(Exception):
    """M7 P0-8 safe_node 装饰器启用后，节点内部异常被装饰器捕获写入 state.error；
    runner 显式抛 GraphNodeError 让 tenacity 可重试（transient 节点故障）"""

async def run_item(item: GoldenItem, n: int) -> dict:
    """跑单条 golden set 题，返回 {question, answer, contexts, trace_id}"""
    graph = get_graph()
    thread_id = f"eval-{n}-{uuid.uuid4().hex[:8]}"
    state = await graph.ainvoke(
        {"query": item.question},
        config={"configurable": {"thread_id": thread_id}},
    )
    # P1-1 节点失败冒泡：safe_node 装饰器把异常写到 state.error，runner 显式 raise 让 tenacity 重试
    if state.get("error"):
        raise GraphNodeError(state["error"])
    return {
        "question": item.question,
        "answer": state.get("answer", ""),
        # P1-7 不直接调 retriever，从 state["chunks"] 取（M7 P1-6 修后），双 fallback 兼容
        "contexts": state.get("chunks", state.get("sources", [])),
        "trace_id": _safe_get_trace_id() or "",
    }

async def run_batch(items: list[GoldenItem]) -> list[dict]:
    """P0-3 异步批跑：asyncio.gather 并发"""
    return await asyncio.gather(*[run_item(item, n=i) for i, item in enumerate(items, 1)],
                                return_exceptions=False)
```

**RED** · `test_run_item_captures_trace_id_from_langfuse`（**P0-6 改 mock 路径**）
- mock `langfuse.get_client` 返回 fake_client
- fake_client.get_current_trace_id.return_value = "trace-abc"
- monkeypatch.setattr("langfuse.get_client", lambda: fake_client)
- 断言返回 dict 含 `"trace_id": "trace-abc"`

**RED** · `test_run_item_surfaces_node_error_for_retry`（**P1-1 节点失败冒泡**）
- mock `graph.ainvoke` 返回 `{"error": "classify_failed: ...", "answer": ""}`
- 断言 runner 抛 `GraphNodeError`

**RED** · `test_run_item_retries_on_graph_4xx_5xx`（**P1-1 缩到 graph 外部异常**）
- mock `graph.ainvoke` 第 1 次抛 `HTTPError 500`、第 2 次成功
- 断言 tenacity 重试 1 次后成功
- 注释：节点内部异常由 `safe_node` 捕获，runner 重试机制**只对 graph 外部异常**（network / 鉴权）生效

**GREEN** · `@tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), retry=retry_if_exception_type((HTTPError, RAGASJudgeError, GraphNodeError)))`

**REFACTOR** · 把 `get_graph()` 抽成 `runner.py` 顶层的 lazy import（避免循环依赖 `app.graph → app.eval`）

#### Task 7：Scorer（**LangchainLLMWrapper 包装 + reference_contexts + raise_exceptions=False**）

**RED** · `tests/unit/test_scorer.py::test_score_uses_langchain_llm_wrapper_not_raw_chat_model`（**P0-1 新增**）
- mock `ragas.llms.LangchainLLMWrapper`（patch `app.eval.scorer.LangchainLLMWrapper`）
- 调 `score_dataset([...], ["faithfulness"])` → 断言 `LangchainLLMWrapper.assert_called_once_with(mock_judge)`

**RED** · `test_score_uses_injected_judge_llm`
- mock `ragas.evaluate` → 断言 `score_dataset(items, judge_llm=mock_judge)` 把 `mock_judge` 传给 ragas
- 跑测试 → 失败

**GREEN** · `app/eval/scorer.py`：
```python
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from ragas.llms import LangchainLLMWrapper      # 0.2.5+ 强制包装（P0-1）
from app.eval.judge import make_judge_llm

METRIC_MAP = {
    "faithfulness": faithfulness,
    "answer_relevancy": answer_relevancy,
    "context_precision": context_precision,
}

def score_dataset(items: list[dict], metrics: list[str]) -> dict:
    """items = [{"question", "answer", "contexts", "ground_truth", "reference_contexts"}]
    P0-1/P1-3: RAGAS 0.2.10 必须用 LangchainLLMWrapper 包装 + reference_contexts 字段
    """
    dataset = Dataset.from_list([{
        "question": it["question"],
        "answer": it["answer"],
        "contexts": it["contexts"],
        "ground_truth": it["ground_truth"],
        # P0-1: context_precision 用 reference_contexts 列表，不是 ground_truth 字符串
        "reference_contexts": it.get("reference_contexts", it["contexts"]),
    } for it in items])
    ragas_metrics = [METRIC_MAP[m] for m in metrics]
    judge_llm = make_judge_llm()
    llm_wrapper = LangchainLLMWrapper(judge_llm)             # 0.2.5+ 必备包装
    result = evaluate(
        dataset,
        metrics=ragas_metrics,
        llm=llm_wrapper,
        raise_exceptions=False,                              # 单题异常不污染整体
    )
    return {
        "per_item": result.to_pandas().to_dict(orient="records"),
        "aggregate": {m: float(result[m]) for m in metrics},
    }
```

**RED** · `test_score_returns_aggregate_and_per_item`
- mock `ragas.evaluate` 返回伪 result → 断言返回 dict 含 `aggregate` 和 `per_item` 两个 key
- 跑测试 → 失败

**GREEN** · 调 `result.to_pandas()`

**RED** · `test_score_raises_on_unknown_metric`
- 传 `metrics=["bogus"]` → 断言 `KeyError`
- 跑测试 → 失败

**GREEN** · `METRIC_MAP[m]` KeyError 自然抛出

**RED** · `test_score_passes_reference_contexts_to_dataset`（**P0-1/P1-3 补强**）
- 给定 items 含 `reference_contexts: ["doc1", "doc2"]`
- 断言构造的 Dataset 字典含 `reference_contexts` 字段

#### Task 8：CLI 串联 runner + scorer

**GREEN** · `app/eval/ragas_run.py` `_run_eval()`（**async**）：
```python
async def _run_eval(golden_set_path, metrics, threshold, mode, report_json, report_html, sample_size, baseline):
    from app.eval.golden_set import load_golden_set
    from app.eval.runner import run_batch
    from app.eval.scorer import score_dataset
    from app.eval.report import write_json, write_html
    from app.eval.gate import check
    from app.config import settings

    items = load_golden_set(golden_set_path)
    # P1-8 CI 用前 20 题 / nightly 用全部
    actual_size = sample_size or (settings.eval.sample_size_ci if mode == "ci"
                                  else settings.eval.sample_size_nightly)
    items = items[:actual_size]

    # P0-3 异步批跑
    runs = await run_batch(items)
    for run, item in zip(runs, items):
        run["ground_truth"] = item.ground_truth
        run["reference_contexts"] = item.reference_contexts

    # 算指标
    result = score_dataset(runs, metrics)
    result["trace_ids"] = [r["trace_id"] for r in runs]
    result["mode"] = mode
    result["git_sha"] = _get_git_sha()                          # P1-6 报告带 git SHA
    result["timestamp"] = _get_timestamp()                       # P1-6 时间戳

    # P1-5 cost 跟踪：取 result.to_pandas() usage 列 sum
    # **r2-2026-06-12 新-2 已修**：RAGAS 0.2.10 `result.to_pandas()` 不含 usage 列；改从 langchain callback handler 拿
    result["cost_usd"] = _compute_cost_usd(runs)  # 改传 runs（每题带 token 用量）而非 result
    result["cost_per_item"] = [r.get("cost_usd_item", 0.0) for r in runs]  # per 题 cost

    # **r2-2026-06-12 新-2 已修**：手动 per 题 try/except 替代 `raise_exceptions=False` 的 skipna 行为
    failed_items = [r["id"] for r in runs if r.get("error")]
    if failed_items:
        result["failed_items"] = failed_items
        click.echo(f"WARN: {len(failed_items)} items failed: {failed_items[:5]}{'...' if len(failed_items)>5 else ''}", err=True)

    # 写报告（P1-6 含 git SHA + 时间戳命名）
    if report_json:
        write_json(result, report_json)
    if report_html:
        write_html(result, report_html, threshold, baseline)

    # P0-5 双阈值门禁
    check(result, threshold=threshold, mode=mode)
    click.echo(f"PASS: faithfulness={result['aggregate'].get('faithfulness', 0):.3f} mode={mode}")
```

**RED** · `tests/unit/test_ragas_run.py::test_run_eval_end_to_end_with_mocks`
- mock `load_golden_set` / `run_batch` / `score_dataset` / `write_json` / `write_html` / `check`
- 调 `await _run_eval(...)` → 断言全部 mock 都被调到
- 跑测试 → 失败

**GREEN** · 实现上面 GREEN 段

---

### Day 3 · Report + Gate + 端到端

#### Task 9：Report（**JSON 含 git SHA + 时间戳 + cost** + HTML 含 baseline diff）

**RED** · `tests/unit/test_report.py::test_write_json_contains_aggregate_and_per_item`
- 给定伪 result → 调 `write_json(result, "/tmp/out.json")` → 读回 → 断言 `aggregate.faithfulness == 0.85`
- 跑测试 → 失败

**GREEN** · `app/eval/report.py`：
```python
import json
import subprocess
from datetime import datetime, timezone

def _get_git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=".", stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"

def _get_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def write_json(result: dict, path: str) -> None:
    """P1-6 报告含 git SHA + timestamp + cost_usd"""
    enriched = {
        "git_sha": result.get("git_sha", "unknown"),
        "timestamp": result.get("timestamp", _get_timestamp()),
        "mode": result.get("mode", "ci"),
        "cost_usd": result.get("cost_usd", 0.0),
        "aggregate": result["aggregate"],
        "per_item": result["per_item"],
        "trace_ids": result.get("trace_ids", []),
    }
    with open(path, "w") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
```

**RED** · `test_write_html_contains_table_and_threshold_marker_and_diff_column`（**P1-6 baseline diff**）
- 给定伪 result + threshold + baseline 路径 → 调 `write_html(...)` → 读回 → 断言包含 `<table>` 和 `threshold: 0.7` 和 `vs baseline` 列

**GREEN** · `app/eval/report.py`：
```python
import markdown

def write_html(result: dict, path: str, threshold: float, baseline_path: str | None = None) -> None:
    md = f"# RAGAS 评估报告\n\n"
    md += f"**Git SHA**: {result.get('git_sha', 'unknown')}  \n"
    md += f"**Timestamp**: {result.get('timestamp', 'unknown')}  \n"
    md += f"**Mode**: {result.get('mode', 'ci')}  \n"
    md += f"**Threshold**: {threshold}  \n"
    md += f"**Cost (USD)**: {result.get('cost_usd', 0.0):.4f}  \n"
    md += f"## 聚合指标\n\n"
    md += "| Metric | Score | vs Baseline |\n|---|---|---|\n"
    baseline_agg = _load_baseline_aggregate(baseline_path) if baseline_path else {}
    for k, v in result["aggregate"].items():
        baseline_v = baseline_agg.get(k)
        diff_str = "—"
        if baseline_v is not None:
            delta = v - baseline_v
            sign = "+" if delta >= 0 else ""
            diff_str = f"{sign}{delta:.3f}"
        md += f"| {k} | {v:.3f} | {diff_str} |\n"
    md += f"\n## 逐题明细\n\n"
    md += "| # | Question | Faithfulness | Answer Relevancy | Context Precision | Trace ID |\n|---|---|---|---|---|---|\n"
    for i, row in enumerate(result["per_item"], 1):
        md += f"| {i} | {row.get('question', '')[:30]} | {row.get('faithfulness', 0):.3f} | {row.get('answer_relevancy', 0):.3f} | {row.get('context_precision', 0):.3f} | {result['trace_ids'][i-1]} |\n"
    html = markdown.markdown(md, extensions=["tables"])
    with open(path, "w") as f:
        f.write(f"<html><body>{html}</body></html>")
```

**REFACTOR** · 把 `md` 拼接抽成 `_build_markdown(result, threshold, baseline)` 让单测可独立测

#### Task 10：CI Gate（**CI 0.65 / nightly 0.7 双阈值**）

**RED** · `tests/unit/test_gate.py::test_check_passes_when_faithfulness_above_ci_threshold`
- 给定 `result["aggregate"]["faithfulness"] = 0.80` + `mode="ci"` → 调 `check(result, 0.65, mode="ci")` → 断言不抛
- 跑测试 → 失败

**RED** · `test_check_raises_when_faithfulness_below_ci_threshold`
- 给定 `faithfulness = 0.60` + `mode="ci"` + threshold=0.65 → 断言抛 `GateViolationError`

**GREEN** · `app/eval/gate.py`：
```python
class GateViolationError(Exception):
    """RAGAS CI gate 失败"""
    def __init__(self, metric: str, value: float, threshold: float, mode: str):
        self.metric = metric
        self.value = value
        self.threshold = threshold
        self.mode = mode
        super().__init__(f"{mode.upper()} GATE: {metric}={value:.3f} < threshold={threshold:.3f}")

# P0-5 双阈值表
THRESHOLDS = {"ci": 0.65, "nightly": 0.70}

def check(result: dict, threshold: float | None = None, mode: str = "ci") -> None:
    """P0-5 双阈值门禁：CI 0.65（20 题宽容）/ nightly 0.7（50 题硬阈值）。
    threshold 参数可显式覆盖 mode 默认值（手工调时用）。
    """
    actual_threshold = threshold if threshold is not None else THRESHOLDS[mode]
    faithfulness = result["aggregate"].get("faithfulness", 0.0)
    if faithfulness < actual_threshold:
        raise GateViolationError("faithfulness", faithfulness, actual_threshold, mode)
```

**RED** · `test_check_nightly_threshold_stricter_than_ci`
- 断言 `THRESHOLDS["nightly"] > THRESHOLDS["ci"]`（nightly 硬阈值比 CI 严）

**RED** · `test_gate_violation_error_message_includes_mode_and_metric`
- 抛 `GateViolationError("faithfulness", 0.60, 0.65, "ci")` → 断言 `str(exc)` 含 `"CI GATE"` 和 `"faithfulness"` 和 `"0.65"`

**RED** · `tests/unit/test_ragas_run.py::test_cli_exit_code_1_on_gate_violation`
- mock `check` 抛 `GateViolationError` → 调 `main(["--golden-set", "...", "--report-json", "/tmp/x.json"])` → 断言 `SystemExit` 且 exit code 1
- 跑测试 → 失败

**GREEN** · `app/eval/ragas_run.py` `main()` 末尾：
```python
try:
    asyncio.run(_run_eval(...))
except GateViolationError as e:
    click.echo(f"GATE FAILED: {e}", err=True)
    sys.exit(1)
```

#### Task 11：集成测试（端到端）

**RED** · `tests/integration/test_m11_e2e_ragas.py::test_e2e_load_to_gate_with_mocks`
- 跑 `await _run_eval("tests/fixtures/golden_set_v1.jsonl", metrics=["faithfulness"], mode="ci", ...)`（threshold 显式 0.0 跑通 gate）
- mock `run_batch`（不调真 graph）和 `ragas.evaluate`（返回伪指标）
- 断言 JSON 报告生成 + HTML 报告生成 + gate 不抛（threshold=0.0）
- 跑测试 → 失败

**GREEN** · 实现集成测试，mock 全部外部依赖

**RED** · `test_e2e_gate_violation_exits_nonzero`
- 同上但 `mode="ci"` + 伪 faithfulness=0.5 → 断言 `GateViolationError`

**GREEN** · 实现

**RED** · `tests/integration/test_m11_golden_set_docs_exist.py::test_expected_doc_ids_in_index`（**P2-5 fixture 真实索引校验**）
- mock `app.retrieval.client.search` 查 doc_id 是否存在
- 不存在 → `log.warning`（**不抛**避免 ingest 未跑时 CI 挂）

**GREEN** · 实现

**REFACTOR** · 把 mock fixture 抽 `tests/integration/conftest.py`

---

## 测试策略

- **M11 单元**：`cd apps/rag_v1 && pytest tests/unit/test_golden_set.py tests/unit/test_judge.py tests/unit/test_runner.py tests/unit/test_scorer.py tests/unit/test_report.py tests/unit/test_gate.py tests/unit/test_ragas_run.py` —— 全 mock，CI 内 2s
- **M11 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m11_e2e_ragas.py tests/integration/test_m11_golden_set_docs_exist.py` —— mock graph + mock RAGAS，CI 内 5s
- **M11 真端到端**（**手工**，不进 CI）：`python -m app.eval.ragas_run --golden-set tests/fixtures/golden_set_v1.jsonl --mode nightly --report-json eval_history/$(date +%Y%m%d)/report.json --report-html eval_history/$(date +%Y%m%d)/report.html` —— 需 docker compose up（M0）+ ANTHROPIC_API_KEY，耗时 10-15 分钟（50 题）
- **CI 模式**：`python -m app.eval.ragas_run --mode ci --sample-size 20 --threshold 0.65 ...`
- **覆盖率门禁**：`pytest --cov=app/eval --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 [RED]）→ GREEN（[GREEN]）→ REFACTOR（[RF]）
- **pytest-asyncio 配置**：`pytest.ini` 加 `asyncio_mode = auto`（runner / scorer / 集成测试全异步）

---

## 验证（Definition of Done）

- [ ] CLI 命令 `python -m app.eval.ragas_run --help` 输出全部 option（含 `--mode` / `--baseline` / `--sample-size`）
- [ ] golden set fixture 50 题覆盖 3 源 × 3 类（9 交叉）+ 5 chitchat + edge，CI 用前 20 + nightly 用全部
- [ ] golden set schema 校验：缺字段 / 错枚举值 / factual 缺 reference_contexts 都拒绝
- [ ] judge LLM 走 M3 `make_llm("judge")`，不读 `OPENAI_API_KEY`，**显式剥离 Langfuse callback**
- [ ] M3 `KNOWN_NODES` 含 `"judge"` 节点，temperature=0.0 断言通过
- [ ] runner async 调 M7 graph.ainvoke 拿 (answer, contexts, trace_id)，**4xx/5xx 重试 3 次**（外部异常），**节点失败抛 GraphNodeError 让 tenacity 重试**
- [ ] scorer 用 `LangchainLLMWrapper(judge)` 包装（0.2.5+ 强制）+ `reference_contexts` 字段 + `raise_exceptions=False`
- [ ] report 输出 JSON（含 `git_sha` / `timestamp` / `cost_usd` / `trace_ids` / `per_item` / `aggregate`）+ HTML（含表格 + threshold 标记 + baseline diff 列）
- [ ] gate：**CI mode < 0.65 / nightly mode < 0.7** 抛 `GateViolationError`、CLI exit 1
- [ ] runner 调 `state["chunks"]` 拿 contexts（不直接调 retriever，避免重复 retrieve）
- [ ] judge-human diff 测试通过（5 题人工 vs judge LLM，平均 diff ≤ 0.1，P1-4）
- [ ] cost 跟踪：report 含 `cost_usd` 字段，超 `cost_budget_usd_per_run` 标 warning（不挂）
- [ ] 集成测试 mock 跑通 load → run → score → report → gate（async）
- [ ] 单元覆盖率 ≥ 85%
- [ ] `tests/integration/test_m11_e2e_ragas.py` 在 mock 环境下 5s 内通过
- [ ] `tests/integration/test_m11_golden_set_docs_exist.py` 校验 doc_id 存在（warning 不挂）
- [ ] 手工真跑 20 题（CI mode，需 docker + ANTHROPIC_KEY）5 分钟内生成报告
- [ ] 手工真跑 50 题（nightly mode）10-15 分钟内生成报告

---

## 与其他 M 的依赖

| 上游（必须 M11 前完成） | 下游（依赖 M11） |
|----------------------|----------------|
| M0 docker-compose（真跑评测要起 PG + OpenSearch） | M12 Hardening（CI 流程调 `python -m app.eval.ragas_run --mode ci`） |
| M1 alembic（golden set 可关联 ingest_jobs.doc_id 校验完整性） | |
| **M3 LLM 工厂**（**M11 修改**：在 `make_llm` `KNOWN_NODES` 追加 `"judge"` 节点 + 注册 `load_prompt("judge")` → `ChatAnthropic`；本 plan 在 M11 阶段显式修改 M3 已建文件，**依赖 M3 review P1-5 修复**） | |
| M7 graph（runner 调 `ainvoke` 拿 answer；**M11 假设 M7 P0-3 修后** `get_graph()` 返已 compile graph） | |
| M7 retrieval（runner 从 `state["chunks"]` 取 contexts，**不直接调 retriever**；**依赖 M7 P1-6 修后** chunks 字段名） | |
| M7 safe_node 装饰器（**M11 弱依赖**：M7 P0-8 修后节点失败冒泡到 `state.error`，runner 显式 `GraphNodeError` 抛 + tenacity 重试） | |
| **M10 Langfuse**（**M11 依赖**：M10 P0-3 修复后 `from langfuse import get_client; get_client().get_current_trace_id()` 才能用，try/except 包装） | |
| M10 P0-2 flush + P0-5 装饰器（M11 假设 M10 修后 Langfuse trace 上报稳定，trace_id 看板可查） | |

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| **RAGAS 0.2 judge LLM 默认读 OPENAI_API_KEY** | `app/eval/judge.py` 显式走 `make_llm("judge")` + 测试 `monkeypatch.delenv("OPENAI_API_KEY")` | "让 RAGAS 默认读 env" — **已否决**（v0.4 spec §5 LLM 4xx/5xx 不静默；评测误读 OpenAI 会出现不可解释指标） |
| **Faithfulness 计算昂贵（每题 2 次 LLM 调用）** | CI 跑 20 题（5 分钟），nightly 跑 50 题；`--sample-size` 强制限制 | "每 PR 跑 50 题" — **已否决**（CI timeout 风险） |
| **Golden set 漂移（改了不影响代码但波动指标）** | golden set git 化 + `tests/fixtures/golden_set_v1.jsonl` 锁版本 + PR review 必看 diff | "golden set 放 S3" — V2 走数据库（review P2-1） |
| **RAGAS judge LLM 断网/限速 4xx/5xx** | tenacity `stop_after_attempt(3), wait_exponential`，跟 M3 风格一致 | "fail fast 不重试" — **已否决**（v0.4 spec §5 错误处理） |
| **HTML 报告用 jinja2 引入模板引擎** | python-markdown 单文件，**不**引入 jinja2 | "用 jinja2 模板" — review P1-1，已改 markdown |
| **RAGAS 0.2 metrics API 变化**（`from ragas.metrics import` 新 API） | Tech Stack 段明确列出 3 个 import + `LangchainLLMWrapper` 包装，Task 7 GREEN 用新 API | "用旧 API `metrics=[faithfulness, ...]`" — 0.2+ 仍兼容但新 API 明确 |
| **CI 时长 20 题 vs 50 题** | CI 跑 20 题（5 分钟），nightly 跑 50 题（10-15 分钟） | "统一 50 题" — CI 拖慢 |
| **M11 评测断言 answer 文本包含某关键词** | spec §6 明确"**不测内容**：LLM 输出文本本身（不可控）"；CI 只看 faithfulness | "断言 'Kubernetes' in answer" — **已否决**（LLM 不可控） |
| **golden set git 化 vs S3** | V1 阶段 git 化 + JSON 命名 `{timestamp}_{git_sha}.json`，V2 走数据库（review P2-1） | "V1 直接 S3" — 过早优化 |
| **RAGAS 0.2.5+ `LangchainLLMWrapper` 强制包装** | P0-1 修复用 `from ragas.llms import LangchainLLMWrapper`；pin `==0.2.10` 精确 | "pin `>=0.2,<1`" — 0.3 已有 break change，区间太宽 |
| **CI faithfulness gate 20 题统计不稳定**（±0.15） | P0-5 双阈值：CI 0.65 / nightly 0.7；CI 宽容避免误报 | "统一 0.7" — 20 题置信区间 ±0.15，CI 抖动误报风险高 |
| **`context_precision` 指标语义错（用 ground_truth 字符串）** | P0-1/P1-3 改 `reference_contexts: list[str]` 字段，dataset 构造时同时传 `ground_truth` + `reference_contexts` | "复用 ground_truth" — 算法把文本当 reference，context_precision 失真 |
| **`make_llm("judge")` M3 工厂未注册** | P0-2 / C-1：M11 plan 显式修改 M3 factory 注册 judge 节点（KNOWN_NODES 追加 + judge.yaml） | "M3 review r2 同步加" — 时序不可控 |
| **M10 trace_id API 错位**（`get_current_trace_id` 不是公开 API） | P0-6 / C-2：改用 `from langfuse import get_client; get_client().get_current_trace_id()` + try/except 包装 | "用 `handler.get_trace_id()`" — 2.50+ 已 deprecate |
| **M7 safe_node 装饰器启用后 runner 重试机制失效** | P1-1 重试范围缩到 graph 外部异常；节点失败显式抛 `GraphNodeError` 由 tenacity 重试 | "不区分内外异常" — 单测可过，真跑时重试失效 |
| **M11 runner 调 retriever 与 graph 重复 retrieve** | P1-7 不直接调 retriever，从 `state["chunks"]` 取（双 fallback 兼容 `state["sources"]`） | "runner 直接调 retriever" — 双倍 latency + 双倍 OpenSearch 调用 |
| **pytest-asyncio 缺 pyproject 声明导致 `event_loop not found`** | P0-3 pyproject 加 `pytest-asyncio>=0.24,<1` + `pytest-mock>=3.14,<4` + `pytest.ini` `asyncio_mode = auto` | "用同步 runner" — graph.ainvoke 异步接口无法同步调用 |
| **judge LLM 自身偏差对 faithfulness ±0.1** | P1-4 风险表已记；judge.yaml temperature=0.0 降低随机性；DoD 加 judge-human diff 测试（5 题人工 ≤ 0.1） | "换不同厂商 judge 交叉验证" — 成本翻倍 |
| **eval cost 50 题 × 4 LLM call 无跟踪** | P1-5 EvalSettings 加 `cost_budget_usd_per_run=5.0` / `cost_budget_usd_per_week=20.0`；report 含 `cost_usd` 字段；超 budget 标 warning（不挂） | "不跟踪 cost" — 长期无法预算 |
| **M11 runner 拿 chitchat 路径 answer + 空 contexts** | P1-2 golden set 5 chitchat 题；chitchat 路径评估只算 `answer_relevancy`，context_precision 跳过（参考 RAGAS chitchat 文档） | "M11 不测 chitchat" — chitchat 路径无 CI 覆盖 |
| **M11 report 长期存储与 baseline 对比缺** | P1-6 report 命名 `{timestamp}_{git_sha}.json`；CLI `--baseline previous.json` → HTML 加 `vs Baseline` 列；V1 git 化，V2 走 DB | "V1 直接 S3" — 过早优化 |
| **nightly 与 CI 指标差异未定义（fixture 大小）** | P1-8 fixture 单文件 50 题（CI 前 20 / nightly 全部）；EvalSettings.mode="ci"\|"nightly" 决定 sample_size | "双文件 CI+nightly" — fixture 维护双份 |
| **M7 get_graph() 契约含糊（contextmanager vs 工厂）** | P2-1 假设 M7 P0-3 修后 `get_graph()` 返已 compile graph（方案 A） | "M11 runner 自己 compile" — 越界 M7 范围 |
| **M7 safe_node 节点失败 → RAGAS 全 0 → gate 挂** | P2-2 风险表明示"这是节点失败的正确捕获，不是 CI 抖动"；DoD 第 11 条说明 | "忽略此现象" — 误判为 CI 抖动 |
| **report markdown 拼接可改 template** | P2-3 V1 短期 OK，V2 改 jinja2 / pydantic 模板 | "V1 用 jinja2" — review P1-1 已否决 |
| **judge LLM 应显式不接 Langfuse callback** | P2-4 make_judge_llm 显式 `with_config({"callbacks": []})` | "继承 M3 工厂 callback" — 评测污染业务 trace 看板 |
| **fixture `expected_doc_id` 真实索引校验未走** | P2-5 加 `test_m11_golden_set_docs_exist.py`，mock `retrieval.client.search` 查 doc_id；不存在 warning 不挂 | "V1 必存在" — ingest 未跑时 CI 挂 |
| r1-2026-06-11 P0-1 已修：RAGAS 0.2.5+ `LangchainLLMWrapper(judge)` 强制包装 + `reference_contexts: list[str]` 字段 + `raise_exceptions=False` 单题异常隔离 |
| r1-2026-06-11 P0-2 已修：M11 显式修改 M3 factory（`KNOWN_NODES` 追加 `"judge"` + `app/llm/prompts/judge.yaml`），C-1 跨 M 联动 |
| r1-2026-06-11 P0-3 已修：pyproject 加 `pytest-asyncio>=0.24,<1` + `pytest-mock>=3.14,<4` + `pytest.ini` `asyncio_mode=auto`；runner/scorer 改 `async` + `asyncio.gather` 批跑 + `graph.ainvoke` |
| r1-2026-06-11 P0-4 已修：RAGAS 版本 pin 收紧到 `==0.2.10`（spec §8.6 区间兼容，避开 0.2/0.3 break change） |
| r1-2026-06-11 P0-5 已修：CI/nightly 双阈值（CI 0.65 / nightly 0.7）+ `EvalSettings.mode` + `THRESHOLDS` 表 + 20 题宽容/50 题硬阈值 |
| r1-2026-06-11 P0-6 已修：trace_id 改 `from langfuse import get_client; get_client().get_current_trace_id()` + try/except 包装（不污染主流程），C-2 跨 M 联动 |
| r1-2026-06-11 P1-1 已修：runner 重试范围缩到 graph 外部异常；节点失败 `GraphNodeError` 显式抛 + tenacity 重试；M7 P0-8 safe_node 联动 |
| r1-2026-06-11 P1-2 已修：golden set 50 题含 5 chitchat + `EvalSettings.include_chitchat` 开关 + chitchat 路径只算 `answer_relevancy`；M7 P0-6 chitchat 联动 |
| r1-2026-06-11 P1-3 已修：`GoldenItem.reference_contexts: list[str]` 字段 + Pydantic `model_validator` 校验（非 chitchat 必填） |
| r1-2026-06-11 P1-4 已修：judge-human diff 测试（5 题人工 vs judge LLM，DoD diff ≤ 0.1）+ `judge.yaml` temperature=0.0 |
| r1-2026-06-11 P1-5 已修：`EvalSettings.cost_budget_usd_per_run=5.0` / `cost_budget_usd_per_week=20.0` + report `cost_usd` 字段 + 超 budget warning（不挂） |
| r1-2026-06-11 P1-6 已修：report 命名 `{timestamp}_{git_sha}.json` + `git_sha`/`timestamp`/`mode` 字段 + CLI `--baseline` 选项 + HTML `vs Baseline` 列 |
| r1-2026-06-11 P1-7 已修：runner 不直接调 retriever，从 `state["chunks"]` 取（双 fallback 兼容 `state["sources"]`）；M7 P1-6 chunks 字段名联动 |
| r1-2026-06-11 P1-8 已修：fixture 单一 50 题文件（CI 前 20 / nightly 全部）+ `mode` 参数决定 sample_size；EvalSettings.sample_size_ci/nightly |
| r1-2026-06-11 P2-1 已修：契约表 / 依赖表显式"假设 M7 P0-3 修后 `get_graph()` 返已 compile graph（方案 A）" |
| r1-2026-06-11 P2-2 已修：风险表明示"safe_node 节点失败 → RAGAS 全 0 → gate 挂是正确捕获节点失败，不是 CI 抖动" |
| r1-2026-06-11 P2-3 已修：md 拼接抽 `_build_markdown(result, threshold, baseline)` 让单测可独立测（V1 短期 OK，V2 改 jinja2） |
| r1-2026-06-11 P2-4 已修：`make_judge_llm` 显式 `llm.with_config({"callbacks": []})` 剥离 Langfuse callback（评测不污染业务 trace 看板） |
| r1-2026-06-11 P2-5 已修：加 `tests/integration/test_m11_golden_set_docs_exist.py` mock `retrieval.client.search` 查 doc_id；不存在 `log.warning`（不挂）；fixture `expected_doc_id` optional |

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M11-plan-r0 | 2026-06-11 | 初稿（基线 V1 Scope 决策 #11 + review P0-1/P0-5/X-3 已纳入） |
| r1-2026-06-11: P0-1 已修 · RAGAS 0.2.5+ 真实 API 签名（`LangchainLLMWrapper(judge)` 包装 + `reference_contexts` 字段） |
| r1-2026-06-11: P0-2 已修 · M11 显式修改 M3 `KNOWN_NODES` 注册 `"judge"` 节点 + `judge.yaml`（C-1 联动） |
| r1-2026-06-11: P0-3 已修 · pyproject 加 `pytest-asyncio>=0.24,<1` + `pytest-mock>=3.14,<4` + `asyncio_mode = auto` + runner 改 `async` + `asyncio.gather` 批跑 |
| r1-2026-06-11: P0-4 已修 · RAGAS 版本 pin 收紧 `==0.2.10`（spec §8.6 区间兼容，避开 0.2/0.3 break change） |
| r1-2026-06-11: P0-5 已修 · CI/nightly 双阈值（CI 0.65 / nightly 0.7）+ `mode` 参数 + `THRESHOLDS` 表 + 20 题宽容/50 题硬阈值 |
| r1-2026-06-11: P0-6 已修 · trace_id API 改 `from langfuse import get_client; get_client().get_current_trace_id()` + try/except 包装（C-2 联动） |
| r1-2026-06-11: P1-1 已修 · runner 重试缩到 graph 外部异常；节点失败显式抛 `GraphNodeError` 由 tenacity 重试（M7 P0-8 safe_node 联动） |
| r1-2026-06-11: P1-2 已修 · golden set 5 chitchat 题 + `include_chitchat: bool` 开关 + chitchat 路径只算 `answer_relevancy`（M7 P0-6 chitchat 联动） |
| r1-2026-06-11: P1-3 已修 · `GoldenItem.reference_contexts: list[str]` 字段 + schema 必填校验（factual/summary/multi_hop 至少 1 个 ref） |
| r1-2026-06-11: P1-4 已修 · judge LLM 偏差风险表已记 + DoD 加 judge-human diff 测试（5 题人工 ≤ 0.1） + `judge.yaml` temperature=0.0 |
| r1-2026-06-11: P1-5 已修 · `EvalSettings` 加 `cost_budget_usd_per_run=5.0` / `cost_budget_usd_per_week=20.0` + report `cost_usd` 字段 + 超 budget warning |
| r1-2026-06-11: P1-6 已修 · report 命名 `{timestamp}_{git_sha}.json` + `git_sha`/`timestamp`/`mode` 字段 + `--baseline` CLI 选项 + HTML diff 列 |
| r1-2026-06-11: P1-7 已修 · runner 不直接调 retriever，从 `state["chunks"]` 取（双 fallback 兼容 `state["sources"]`，M7 P1-6 联动） |
| r1-2026-06-11: P1-8 已修 · fixture 单一 50 题文件（CI 前 20 / nightly 全部）+ `mode` 参数决定 sample_size |
| r1-2026-06-11: P2-1 已修 · 契约表明示"假设 M7 P0-3 修后 `get_graph()` 返已 compile graph" |
| r1-2026-06-11: P2-2 已修 · 风险表明示"safe_node 节点失败 → RAGAS 全 0 → gate 挂是正确捕获，不是 CI 抖动" |
| r1-2026-06-11: P2-3 已修 · md 拼接抽 `_build_markdown` 让单测可独立测（V1 短期 OK，V2 再改 jinja2） |
| r1-2026-06-11: P2-4 已修 · `make_judge_llm` 显式 `with_config({"callbacks": []})` 剥离 Langfuse callback（评测不污染业务 trace） |
| r1-2026-06-11: P2-5 已修 · 加 `test_m11_golden_set_docs_exist.py` 校验 doc_id 真实索引（warning 不挂）+ fixture expected_doc_id optional |
| r2-2026-06-12: 新-1 已修 · fixture 重排 q001-q005 chitchat + q006-q050 rag，CI 前 20 = q001-q020 包含 5 chitchat + 15 rag（chitchat 路径 CI 覆盖目标达成） |
| r2-2026-06-12: 新-2 已修 · `_compute_cost_usd` 改从 langchain callback 拿 usage（不再依赖 `result.to_pandas()`，RAGAS 0.2.10 不返回 usage 列）+ 手动 per 题 try/except 替代 `raise_exceptions=False` skipna 行为；报告补 `cost_per_item` + `failed_items` 字段 |
| r2-2026-06-12: 新-3 已修 · `judge.py` 显式断言 `isinstance(judge, RunnableBinding)`（M3 工厂 `with_config` 返回 RunnableBinding 非 ChatAnthropic 原类）；新增 `test_with_config_callbacks_empty_returns_runnable_binding` RED + GREEN 段 |
| r2-2026-06-12: 新-4 已修 · `--baseline` 改 type=str（不再 `click.Path(exists=True)`），V1.1 时改用 git tag `v0.1.0` 作 baseline |
| r2-2026-06-12: 新-5 已修 · 同新-1 fixture 重排消化 |
