# M3 Plan Review · LLM 工厂 + TEI Embedding 客户端 + Langfuse 范本

> 评审对象：M3 `2026-06-10-rag-m3-llm-embed.md`（318 行）
> 评审基线：V1 Scope v0.4 spec §0 决策 #8/#9/#10 / §2 模块树 llm+embedding+observability 段 / §6 测试策略 / §8.1 核心 LLM 编排栈 / §8.2 Embedding & 文档解析栈 / §8.6 观测依赖；M0/M1/M2 review；总 review `2026-06-11-rag-plans-review.md` P1-12~P1-18；M7 / M10 / M11 plan 契约引用
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M3 plan 是 RAG V1 路线**唯一被显式标注为"范本"**的里程碑（自警 L8："给 M0/M1/M2/M4–M12 提供'单里程碑'计划的结构样板"）。它把 11 段模板走齐（Goal / 不包含 / Architecture / Tech Stack / Files / Tasks / 测试 / DoD / 依赖 / 风险 / 修订记录），技术版本与 spec §8.1 / §8.2 / §8.6 **完全对齐**（与 M2 review 指出 M2 版本 2 处与 spec §8.3 漂移形成对照——M3 没踩这个坑），4 节点 prompt YAML 文件名与 M7 graph 节点一一对应、契约边界表覆盖 M4–M7/M10/M11 全部下游。

但作为"范本"，它**多处就绪度不足**：4 节点 prompt YAML 仅列文件名无内容（DoD 却要求"≥ 50 token 含 1-shot"）、`make_llm` 注入 callback 写 `model.callbacks` 与 langchain 1.0+ 弃用 API 冲突、TEIEmbedder 缺 dim/batch_size/timeout/normalize/truncate 实际行为定义、缺采样率/flush 策略/超时配置等 LLM 工程化关键决策、缺"judge/summarize/chitchat"等下游节点预留。**整体框架对、内容薄、范本可借鉴但不能照搬**——其他 M 起草时若 100% 复制 M3 结构，会复制这些缺陷。

| 维度 | 评分 | 说明 |
|---|---|---|
| 结构完整性 | ⭐⭐⭐⭐ | 11 段齐，"范本目的"段明确（是 5 份 M0–M3 plan 中**唯一**带"范本目的"的——M0 review P2-2 反复呼吁补这一段）|
| 范本示范性 | ⭐⭐⭐ | 11 段是骨架好示范；但 4 yaml 无内容、callback 注入写法有误、TEI 缺关键工程项 → 后续 M 复制结构时会复制缺陷 |
| 一致性 | ⭐⭐⭐⭐⭐ | 5 个直接依赖版本（langchain 1.0.8 / langchain-core / langchain-anthropic / langfuse 2.50+ / httpx / tenacity）逐一对齐 spec §8.1/§8.2/§8.6；4 节点名与 spec §3.3 + M7 graph 节点名 1:1 对齐 |
| 实施就绪度 | ⭐⭐ | 4 yaml 没草稿、callback 注入写法过时（已 review P1-14 标）、Tasks 4 写 5 分钟实际含 3 个 RED 测试、DoD 第 7 条 "≥ 50 token" 标准在 plan 内**无对应内容** |
| 错误处理 | ⭐⭐⭐ | TEI 5xx/4xx 重试有方案；LLM 错误/超时/限速处理**完全缺**；Langfuse env 缺 key 优雅降级 OK；minimax-cn 不稳定风险只说"retry 3 次"无具体参数 |
| 跨 M 契约 | ⭐⭐⭐ | 契约边界表清晰（5 个下游 M），但漏 `make_llm("judge")`（M11 强依赖）和 `make_llm("answer_chitchat")`（M7 闲聊分支用）；X-1 config 拆分/X-3 全局单例未在本 plan 落实 |

**一句话**：M3 plan **结构对、版本对、契约清**，是 4 份 plan 中最值得作为"骨架样板"的一份；**但作为范本的内容示范是失败的**——下游 M 复制时若不补 P0/P1，会复制其"4 yaml 空壳 + callback 过时写法 + 缺超时/采样/限速"三大缺陷。**修完 4 个 P0 + 6 个 P1 后是合格的"骨架范本"，可成为 M4–M12 的样板。**

---

## P0 · 阻塞级（动手前必改）

### P0-1 · 4 节点 prompt YAML 在 plan 中完全没草稿（已有 review P1-13 + 新发现）

**位置**：M3 Files 表 L155-158 + DoD L283 + Task 4 RED `test_factory_binds_system_prompt` L249

**问题**：
- DoD L283 明文："4 个 prompt yaml 文件（classify/rewrite/rerank/answer）各 ≥ 50 token，含 1-shot 示例"
- 但 plan **全篇没有任何 yaml 草稿**（既不在 Files 表后给内容样例，也不在 Task 4 GREEN 段给 system_prompt 字符串）
- Task 4 RED 测试 `test_factory_binds_system_prompt` 需要"mock yaml → 断言 llm.invoke([HumanMessage("test")]) 时 system message 已绑定"——**没有 yaml 草稿，RED 测试断言的 system_message 是空字符串**，通过即假绿
- M3 是范本 → M4–M12 plan 起草人复制 Files 表结构时，会复制"列文件名无内容"的反模式，导致所有 prompt 实际工作要回 plan review 才能定

**修改**（Files 表后补一个 §4 草稿段，给 4 个 yaml 各 5-10 行伪代码）：

```yaml
# app/prompts/classify.yaml
model: minimax-cn/MiniMax-M3
temperature: 0.0           # classify 要 deterministic
max_tokens: 64
system_prompt: |
  你是 query 意图分类器。把用户 query 分到两类之一：
    - "retrieve"：需要查知识库（事实 / 流程 / 代码 / 配置）
    - "chitchat"：闲聊 / 寒暄 / 不需要事实回答
  严格只输出 JSON：`{"intent": "retrieve" | "chitchat", "reason": "<1 句中文理由>"}`
  ---
  1-shot:
    Q: "你好"
    A: {"intent": "chitchat", "reason": "问候语无信息需求"}
  Q: "V1 决策 #8 选型理由？"
    A: {"intent": "retrieve", "reason": "需查决策表"}
```

```yaml
# app/prompts/rewrite.yaml
model: minimax-cn/MiniMax-M3
temperature: 0.2
max_tokens: 256
system_prompt: |
  你是 query 改写器。基于对话历史把当前 query 改写成 1-3 句、自包含的检索 query。
  - 消解代词（"它" → "V1 决策 #8 选型"）
  - 补全主语/对象
  - 保留原 query 的意图
  严格只输出改写后 query，不要解释。
```

```yaml
# app/prompts/rerank.yaml
model: minimax-cn/MiniMax-M3
temperature: 0.0
max_tokens: 1024
system_prompt: |
  你是相关性评分员。给每个 chunk 打 0-10 分（10=直接回答 query 核心问题）。
  输入格式：
    QUERY: <query>
    CHUNKS:
      [1] <chunk1>
      [2] <chunk2>
      ...
  严格只输出 JSON：`{"scores": [[1, 8], [2, 3], ...]}`，顺序与输入 chunks 对齐。
```

```yaml
# app/prompts/answer.yaml
model: minimax-cn/MiniMax-M3
temperature: 0.3
max_tokens: 1024
system_prompt: |
  你是 RAG 回答助手。基于 <context> 块回答 <query>。
  - 必须用 [1][2][3] 引用编号标注信息来自哪个 chunk
  - context 不足时直说"未找到足够信息"，不要编造
  - 中文回答
  严格按格式：`ANSWER: <markdown 回答>\nSOURCES: [1, 2, 3]`
```

并 Task 4 RED 段补："`assert "你是 query 意图分类器" in bound_messages[0].content`"——锚定 yaml 实际字符串，避免假绿。

**注**：P1-13 已指"yaml 无内容"，本 review **新发现**应同时给完整草稿 + 范本契约——M3 是范本，缺草稿会被下游 M 复制。

---

### P0-2 · `make_llm` 注入 callback 方式与 langchain 1.0+ 弃用 API 冲突（已有 review P1-14）

**位置**：M3 Task 4 GREEN 段 L246
```
- 如果 get_callback_handler() is not None → 注入到 model.callbacks（不破坏 langchain 1.0 内部 handler chain）
```

**问题**：
- langchain 1.0+ 弃用 `model.callbacks`（基础 BaseChatModel 字段保留但写入后**不会**走 callback manager 路由）
- 实际生效写法（langchain 1.0.8 官方）：`model.with_config({"callbacks": [handler]})` 或 invoke 时 `model.invoke(messages, config={"callbacks": [handler]})`
- M3 写法 → 注入后 Langfuse 看板**完全收不到** LLM trace → Task 5 集成测试 `LANGFUSE_HOST/api/traces` GET poll 失败，DoD 第 4 条"Langfuse callback 在 env 完整时注入 LLM invoke 并能在看板看到 trace"为假绿

**修改**（Task 4 GREEN 段改写）：

```python
# app/llm/factory.py
from functools import lru_cache
from langchain_anthropic import ChatAnthropic
from app.config import settings
from app.observability.langfuse import get_callback_handler
from app.llm.prompts import load_prompt_cfg

@lru_cache(maxsize=8)  # 4 节点复用同一 LLM 实例
def make_llm(node: str) -> ChatAnthropic:
    cfg = load_prompt_cfg(node)
    model = ChatAnthropic(
        model=cfg.model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        api_key=settings.llm.api_key.get_secret_value(),
        timeout=settings.llm.timeout,           # ← 新增 P1-2
        max_retries=settings.llm.max_retries,   # ← 新增 P1-2
    )
    # bind system_prompt（langchain 1.0 bind 协议）
    bound = model.bind(system_message=cfg.system_prompt)
    # callback 在 invoke 时注入（不写进 model.callbacks）
    handler = get_callback_handler()
    if handler is not None:
        # 返回 Runnable binding，节点 invoke 时传 config
        return bound.with_config({"callbacks": [handler]})
    return bound
```

并在 Task 4 RED 段补断言：
```python
# 验证 callback 注入路径正确（不写进 model.callbacks 字段）
def test_callback_uses_with_config_not_callbacks_field(monkeypatch):
    from app.llm import factory
    monkeypatch.setattr(factory, "get_callback_handler", lambda: FakeHandler())
    llm = factory.make_llm("answer")
    assert not hasattr(llm, "callbacks") or llm.callbacks == []
    # callback 应在 config 里
    assert llm.steps[0].kwargs.get("config", {}).get("callbacks") or \
           any("callback" in str(s) for s in llm.steps)
```

**注**：已有 review P1-14 已点名，本 review 强化——给出完整重写 + 实际 API 路径 + 假绿防护。

---

### P0-3 · TEIEmbedder 缺 dim 硬约束断言 + batch_size 协调 + normalize/truncate 明确语义

**位置**：M3 Task 2 GREEN 段 L207-209

**问题**：
- `async def embed(self, texts)` → `list[list[float]]` 返回值**没有 dim 断言**：TEI 偶发返 dim=768（模型加载到一半 / 配置错）→ DB 存 dim=1024 / dim=768 混 → OpenSearch kNN 索引报错
- `EmbeddingSettings.dim: int` 字段定义了但**没人用**——既不传给 TEI（TEI 由模型决定 dim），也不在返回时断言
- `batch_size=32` 是 client 端切分，TEI 服务端 `max_client_batch_size` 默认 32 协调但 plan 没写（TEI 1.5 默认是 32，但如果配置改了不一致会 413/400）
- "normalize=true, truncate=true" 是请求体参数，但**语义没说**——是 L2 normalize 吗？truncate 多长（bge-m3 上限 8192 token）？

**修改**（Task 2 GREEN 段补）：

```python
# app/embedding/client.py
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx
from app.config import settings

class EmbeddingError(Exception): ...
class EmbeddingDimMismatch(EmbeddingError): ...

class TEIEmbedder:
    def __init__(self, cfg: EmbeddingSettings | None = None):
        self.cfg = cfg or settings.embedding
        self._client = httpx.AsyncClient(
            base_url=self.cfg.base_url,
            timeout=httpx.Timeout(self.cfg.timeout_seconds),  # 默认 60
        )

    async def aclose(self):
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type(EmbeddingError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),  # 1/2/4s
        reraise=True,
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for batch in _chunked(texts, self.cfg.batch_size):
            try:
                resp = await self._client.post(
                    "/embed",
                    json={"inputs": batch, "normalize": True, "truncate": True},
                )
            except httpx.TimeoutException as e:
                raise EmbeddingError(f"TEI timeout: {e}") from e
            if 500 <= resp.status_code < 600:
                raise EmbeddingError(f"TEI {resp.status_code}: {resp.text}")  # 触发 retry
            if 400 <= resp.status_code < 500:
                raise EmbeddingError(f"TEI 4xx no-retry: {resp.status_code} {resp.text}")
            resp.raise_for_status()
            vecs = resp.json()["embeddings"]
            # 硬约束 dim 断言
            for v in vecs:
                if len(v) != self.cfg.dim:
                    raise EmbeddingDimMismatch(
                        f"TEI returned dim={len(v)}, expected {self.cfg.dim}"
                    )
            results.extend(vecs)
        return results

def _chunked(texts: list[str], n: int):
    for i in range(0, len(texts), n):
        yield texts[i:i + n]
```

并 Task 2 RED 段补：
```python
async def test_embed_raises_on_dim_mismatch(httpx_mock):
    httpx_mock.add_response(json={"embeddings": [[0.1] * 768]})  # 错的 dim
    embedder = TEIEmbedder()
    with pytest.raises(EmbeddingDimMismatch):
        await embedder.embed(["hello"])
```

---

### P0-4 · 缺 LLM 超时 + 重试 + 限速 + 采样率 + flush 配置（LLM 工程化 5 件套）

**位置**：M3 Task 1 GREEN 段（`LLMSettings` 字段定义）+ Task 4 GREEN（`make_llm` 构造）+ 风险表 L307

**问题**：
- `LLMSettings` 字段只有 `model / temperature / max_tokens / api_key`——**缺 timeout / max_retries**（M3 风险表说"minimax-cn 不稳定，retry 3 次"但代码里没实现）
- `LangfuseSettings` 只有 `public_key / secret_key / host`——**缺 sample_rate / flush_at / flush_interval / blocked_keys**
  - prod 1.0 sample rate = 100% trace → 成本爆炸（minimax-cn 不一定收费但 Langfuse OSS 仍写库 + 网络 IO）
  - 异步 trace 不显式 flush → 进程退出时丢 trace
- 没设 LLM `request_timeout` → `make_llm("answer").invoke(...)` 在网络 hang 时**拖垮**整个 ASGI 请求（FastAPI 默认 60s，minimax-cn 60s 不够）

**修改**（Task 1 GREEN 段 LLMSettings + LangfuseSettings 补）：

```python
class LLMSettings(BaseSettings):
    model: str = "minimax-cn/MiniMax-M3"
    temperature: float = 0.3
    max_tokens: int = 1024
    api_key: SecretStr
    timeout: int = 60                # 单次 invoke 超时（秒）
    max_retries: int = 3             # 内部 retry（ChatAnthropic built-in）
    rate_limit_rpm: int = 60        # 每分钟限速，触发走 token bucket

class LangfuseSettings(BaseSettings):
    public_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    host: HttpUrl = HttpUrl("http://localhost:3000")
    sample_rate: float = 1.0         # prod 改 0.1
    flush_at: int = 2                # 攒 N 条 flush
    flush_interval: float = 5.0      # 每 N 秒 flush
    blocked_keys: list[str] = []     # PII：password / token / secret 不入 trace
```

并在 `make_llm` GREEN 段补：
```python
# rate limit + retry
model = ChatAnthropic(
    ...,
    timeout=settings.llm.timeout,
    max_retries=settings.llm.max_retries,
)
```

并在 `observability/langfuse.py` GREEN 段补：
```python
def get_callback_handler() -> CallbackHandler | None:
    if not (settings.langfuse.public_key and settings.langfuse.secret_key):
        return None
    return CallbackHandler(
        public_key=settings.langfuse.public_key.get_secret_value(),
        secret_key=settings.langfuse.secret_key.get_secret_value(),
        host=str(settings.langfuse.host),
        sample_rate=settings.langfuse.sample_rate,
        blocked_keys=settings.langfuse.blocked_keys,
    )
```

并在 process 退出 hook（M3 可不管实现，但 plan 应记录"M12 加 atexit flush"）：
```
# 风险表 + 修订记录补：M12 atexit 调 langfuse.flush()，M3 范围内 langfuse 自身 background flush 够用
```

---

## P1 · 重要

### P1-1 · 4 节点 LLM 没显式 deterministic 控（已有 review 没列）

**位置**：M3 Task 4 GREEN 段 L242-246

**问题**：
- `classify` / `rerank` 必须是 deterministic（temperature=0.0）——否则同一 query 反复跑结果不一样，answer 引用编号也跟着变
- `rewrite` 应低温度（0.2）
- `answer` 可稍高（0.3）
- plan 只在 P0-1 yaml 草稿里建议过 temperature，**没在工厂层强制**——节点调用方写 `make_llm("classify")` 后改 temperature 就破

**修改**（`make_llm` 内强制 temperature，yaml 里只是声明）：
```python
# factory.py 强制不覆盖
if node in ("classify", "rerank"):
    # 忽略 yaml temperature，强制 0.0
    model = ChatAnthropic(model=cfg.model, temperature=0.0, ...)
```

并在 Task 4 RED 段补：
```python
def test_classify_and_rerank_are_deterministic():
    llm = make_llm("classify")
    assert llm.temperature == 0.0
    llm = make_llm("rerank")
    assert llm.temperature == 0.0
```

**注**：review 报告**新发现**——LLM 工程质量红线。

---

### P1-2 · `langfuse.langchain.CallbackHandler` import 路径无 fallback（已有 review P1-12）

**位置**：M3 Tech Stack L133

**问题**：
- langfuse v2 重构后路径有变更风险（v2.x → v3.x 可能会再改）
- plan 写 `from langfuse.langchain import CallbackHandler` 单路径
- 集成测试启动后若 import 抛 ImportError，DoD 第 4 条直接挂

**修改**（Task 3 GREEN 段加 fallback）：
```python
# app/observability/langfuse.py
try:
    from langfuse.langchain import CallbackHandler  # langfuse 2.50+ 主路径
except ImportError:
    try:
        from langfuse.callback.langchain import CallbackHandler  # 旧版兼容
    except ImportError:
        CallbackHandler = None
```

并在 Task 3 RED 段补：
```python
def test_callback_handler_import_paths_resolve():
    """至少一条路径能 import 到 CallbackHandler。"""
    from app.observability.langfuse import CallbackHandler
    assert CallbackHandler is not None
```

---

### P1-3 · `pytest-httpx` 缺 pyproject 声明（已有 review P1-18）

**位置**：M3 Tech Stack L123 + Files 表 L168

**问题**：
- `tests/unit/test_tei_embedder.py` 大量 mock httpx 调用，依赖 `pytest-httpx`
- plan 在 Tech Stack 文字里提了"pytest-httpx"，**pyproject 依赖表里没写**——新人 `pip install` 后跑测试 `fixture 'httpx_mock' not found`

**修改**（M3 Files 表 / pyproject 段补）：
```toml
[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.24,<1",
  "pytest-httpx>=0.30,<1",      # M3 新增
  "pytest-cov>=5.0,<7",          # M0/M1 通用
]
```

**注**：已有 review P1-18 已列，本 review 强化给出 pyproject 完整 dev 段。

---

### P1-4 · M3 plan 内部不一致：`api_key` 配置 vs yaml model 字段

**位置**：M3 Task 1 L192 (`LLMSettings.model: str`) + Task 4 L242 (`load_prompt_cfg` 返回 `cfg.model`)

**问题**：
- `LLMSettings.model` 是 **全局** LLM 模型（所有节点共用）
- yaml 里又声明 `model: minimax-cn/MiniMax-M3`（**每个** yaml 一份）
- 两份 model 字段谁优先？plan 没写
- 若 yaml 里写 `model: minimax-cn/MiniMax-M3-pro`（4 节点用不同模型）→ `load_prompt_cfg` 怎么校验不允许？
- 实际工程上 `LLMSettings.model` 应**废弃**（yaml 才是 source of truth），或反之

**修改**（二选一）：

- **方案 A**（推荐）：`LLMSettings` 不含 `model` 字段，yaml 是唯一来源
  ```python
  class LLMSettings(BaseSettings):
      temperature_default: float = 0.3  # 兜底
      max_tokens_default: int = 1024
      api_key: SecretStr
      timeout: int = 60
      max_retries: int = 3
  ```
- **方案 B**：`LLMSettings.model` 是兜底，yaml 缺省继承
  ```python
  def load_prompt_cfg(node: str) -> PromptCfg:
      yaml_cfg = _read_yaml(f"app/prompts/{node}.yaml")
      return PromptCfg(
          model=yaml_cfg.get("model", settings.llm.model),  # yaml > global
          temperature=yaml_cfg.get("temperature", settings.llm.temperature_default),
          ...
      )
  ```

**注**：review 报告**新发现**——plan 内部字段冲突。

---

### P1-5 · M3 缺下游契约：`make_llm("judge")` 是 M11 强依赖

**位置**：M3 plan 全篇（无）+ M11 plan L18, L43, L73（"RAGAS judge LLM **显式注入**... 复用 M3 `make_llm("judge")`"）

**问题**：
- M11 plan L18 明确写："复用 M3 `make_llm("judge")`"——M3 必须提供
- M11 plan L44 仓库布局：`app/llm/prompts/judge.yaml` 标注"M11 新增"——意味着 M11 plan 默认 M3 工厂**已支持** node 名动态注册
- M3 plan 4 节点 hard-code：`make_llm(node)` 的 `node` ∈ {"classify", "rewrite", "rerank", "answer"}
- 没 `make_llm("judge")` → M11 评估 CI 起不来
- M7 plan L19 7 节点 workflow 还可能加 `answer_chitchat`（classify 判 chitchat 后走闲聊分支），也是 M3 工厂没预留的节点

**修改**（Task 4 GREEN 段改写工厂为**注册表** + 显式列出 5 节点起步）：

```python
# app/llm/factory.py
KNOWN_NODES = ("classify", "rewrite", "rerank", "answer", "judge", "summarize", "answer_chitchat")

def make_llm(node: str) -> ChatAnthropic:
    if node not in KNOWN_NODES:
        raise ValueError(f"unknown llm node: {node}. known: {KNOWN_NODES}")
    cfg = load_prompt_cfg(node)
    ...
```

并在 Files 表 L155-158 旁补 `app/prompts/judge.yaml` 占位（"M11 阶段实写"）：
```
# app/prompts/judge.yaml  (M11 阶段实写，M3 阶段创建空文件占位)
model: minimax-cn/MiniMax-M3
temperature: 0.0
max_tokens: 512
system_prompt: ""  # TODO M11
```

**注**：review 报告**新发现**——M3 plan 缺"下游契约预留"段。M11 plan 已把 `judge` 节点当事实契约引用，M3 必须回应。

---

### P1-6 · Task 4 写"5 分钟"实际含 3 个 RED 测试（10-15 分钟）

**位置**：M3 Task 4 L237-252

**问题**：
- Task 4 RED 段含 2 个测试：`test_factory_creates_chat_anthropic` + `test_factory_binds_system_prompt`
- GREEN 段还要做 `load_prompt_cfg` + 工厂实现 + callback 注入（受 P0-2 影响还得重写）
- Task 4 标 2-5 分钟，实际 10-15 分钟（参考 M0 review P2-6 "Task 1 标 5 分钟实 25 分钟"的同类问题）

**修改**（拆 Task 4 → 4a/4b）：
- Task 4a：load_prompt_cfg 实现（5 分钟）
- Task 4b：make_llm 工厂 + 4 节点注册（10 分钟）
- Task 4c：callback 注入（5 分钟，受 P0-2 修正）

或在 DoD / 风险表坦白写："Task 4 是 4-4c 合并体，约 20 分钟"。

**注**：M0 review P2-6 已点同类问题，本 review **新发现** M3 同一坑。

---

## P2 · 优化

### P2-1 · 4 yaml 加载方式缺热加载设计（`load_prompt` 每次读文件 vs 缓存）

**位置**：M3 Task 4 L242 `load_prompt(node: str) -> PromptCfg`

**问题**：
- 每次 `make_llm(node)` 调 `load_prompt` 都读 yaml 文件 → 1000 QPS 跑 4 节点 graph = 4000 次/秒文件 IO
- 即使加 `@lru_cache` 也行，但 plan 没明说
- yaml 热加载（改 prompt 不重启）也是 V1 后期常见需求，plan 没规划

**修改**（`load_prompt` 加缓存 + mtime 失效）：
```python
import functools
import os
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"

@functools.lru_cache(maxsize=16)
def _load_prompt_cached(path: str, mtime: float) -> dict:
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)

def load_prompt_cfg(node: str) -> PromptCfg:
    path = _PROMPT_DIR / f"{node}.yaml"
    mtime = os.path.getmtime(path)
    raw = _load_prompt_cached(str(path), mtime)
    return PromptCfg(**raw)
```

`mtime` 作 cache key → 改 yaml 自动失效，无需重启。

**注**：review 报告**新发现**。

---

### P2-2 · DoD 第 7 条 "4 yaml ≥ 50 token" 标准在 plan 内无验证机制

**位置**：M3 DoD L283

**问题**：
- "≥ 50 token 含 1-shot" 是 DoD 但**没有测试**保证（plan 写 Task 4 测的是 system_prompt 已 bind，**不测** yaml 文件本身 token 数 / 是否含 1-shot）
- 实际工程 yaml 改 1 个字可能 1-shot 没了，CI 不卡

**修改**（新增 Task 6：yaml 守门测试）：
```python
# tests/unit/test_prompt_yaml_guard.py
import yaml
from pathlib import Path

def test_all_prompt_yamls_meet_minimum():
    for name in ("classify", "rewrite", "rerank", "answer"):
        with open(f"app/prompts/{name}.yaml") as f:
            data = yaml.safe_load(f)
        prompt = data.get("system_prompt", "")
        token_count = len(prompt.split())  # 简化：词数 ≈ token
        assert token_count >= 50, f"{name} yaml prompt {token_count} < 50 tokens"
        # 1-shot 关键词检查
        assert "1-shot" in prompt or "示例" in prompt or "Q:" in prompt, \
            f"{name} yaml missing 1-shot example"
```

并在 DoD 第 7 条旁标"由 `test_prompt_yaml_guard.py` 强制"。

**注**：review 报告**新发现**。

---

### P2-3 · 4 yaml 加载库 `PyYAML` 缺 pyproject 声明

**位置**：M3 Task 4 GREEN 段

**问题**：
- `load_prompt_cfg` 用 yaml.safe_load 隐式 import `yaml`（PyYAML）
- M3 pyproject 依赖表里**没** PyYAML
- 跑测试 `ModuleNotFoundError: No module named 'yaml'`

**修改**（pyproject 直接依赖加 `pyyaml>=6.0,<7`）。

---

### P2-4 · Tasks 估时汇总 vs 实际

**位置**：M3 plan 头部 "估时：2 个工作日"

**问题**：
- Task 1 配置块：10 分钟
- Task 2 TEIEmbedder：含 3 RED 测试 + 重试 + dim 断言 + batch = 30 分钟
- Task 3 Langfuse callback：10 分钟
- Task 4 LLM 工厂：含 3 RED + 注册表 + callback 注入（受 P0-2 重写影响）= 30 分钟
- Task 5 smoke：docker compose up + 端到端 + 等 Langfuse trace = 20 分钟
- Tasks 累计 ~100 分钟 = 1.7 小时
- 但受 P0-1（写 4 yaml 草稿）/ P0-3（补 dim 断言）/ P1-5（注册表化）/ P1-6（拆任务）等修补，实际 4-6 小时
- 2 个工作日（16h）充足但**估时颗粒度对下游 plan 误导**（M11 plan 估时 3d 是基于 M3 工厂 1-2h 估出来的 → 实际 M3 要 4-6h → M11 估时要相应 +1d）

**修改**：在 M3 plan 头部估时改为 "2 个工作日（Tasks ~6h + 调试 ~6h + 文档 ~4h）"。

**注**：M0 review P2-6 同类问题。

---

### P2-5 · TEIEmbedder 缺连接复用策略（`__aenter__` / context manager）

**位置**：M3 Task 2 GREEN 段 `class TEIEmbedder`

**问题**：
- 当前实现 `__init__` 里建 `httpx.AsyncClient`，无 `__aenter__` / `aclose`
- 调用方写法：`embedder = TEIEmbedder(); await embedder.embed(...)`——谁负责关连接？长跑进程会 leak
- 标准做法：实现 `__aenter__` / `__aexit__` / `aclose`，调用方 `async with TEIEmbedder() as e: ...`

**修改**：
```python
class TEIEmbedder:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): await self.aclose()
```

并在 Files 表注释里写"使用方式 `async with TEIEmbedder() as e: ...`"。

---

### P2-6 · 集成测试 smoke 缺"4 节点都跑过"覆盖

**位置**：M3 Task 5 RED 段 L256-261

**问题**：
- `test_embed_then_llm_pipeline` 只测 `make_llm("answer")` —— DoD 第 1 条"4 节点都创建实例"在集成层**不验证**
- 万一 classify/rewrite/rerank 工厂在 prompt 解析时崩（缺 yaml），集成测试发现不了

**修改**（Task 5 补 4 节点 parametrize）：
```python
import pytest
from app.llm.factory import make_llm

@pytest.mark.parametrize("node", ["classify", "rewrite", "rerank", "answer"])
def test_make_llm_smoke_for_all_nodes(node):
    llm = make_llm(node)
    assert llm is not None
    # 真实 invoke 一次（用真 env）
    resp = llm.invoke([HumanMessage("ping")])
    assert resp.content
```

**注**：review 报告**新发现**。

---

## 范本影响评估

M3 计划是 RAG V1 路线**唯一被显式标注为"范本"**的里程碑（自警 L8），其他 M4–M12 起草时都参考它的 11 段结构。

### 优点（M3 范本值得借鉴的 5 点）

1. **11 段骨架清晰**（Goal / 不包含 / Architecture / Tech Stack / Files / Tasks / 测试 / DoD / 依赖 / 风险 / 修订记录）——M0/M1/M2 起草时都参考了。M0 review P2-2 还呼吁 M0 补"范本目的"段——M3 是 5 份中**唯一**带"范本目的"的，示范性完整。
2. **仓库布局图清晰**（`apps/rag_v1/{infra,app,tests}/` 3 段）——M4/M5/M6/M7/M10/M11 Files 表都引用 M3 布局。
3. **跨 M 契约边界表**（M3 L101-106）——4 个下游 M 4-6/7/10/11 用什么接口、batch 多少、是否复用 callback 都列清楚。**M3 范本最大贡献**。
4. **版本精确 pin**（langchain==1.0.8 / langchain-anthropic>=0.3,<1.0 / langfuse>=2.50,<3）——与 spec §8.1/§8.2/§8.6 **逐字对齐**，无 M2 那样的"argon2-cffi<25 vs spec<24"漂移。
5. **RED-GREEN-REFACTOR 标注完整**——M3 Tasks 5 个里 4 个含 RED 测试描述。

### 不足（M3 范本若不修补会被复制的 4 个缺陷）

1. **"Files 列文件名无内容"反模式**——M3 4 yaml 列在 Files 表但**无草稿**，DoD 却要求"≥ 50 token" → M4–M12 plan 起草人复制 Files 表结构时，会复制"列文件名无内容"的反模式，导致 prompt 实际内容要 plan review 阶段定。**P0-1 必须修，否则范本污染 9 个下游 M**。
2. **`model.callbacks` 注入 callback 的过时写法**——P0-2 修了；如果不修 → M7/M10 节点代码会复制这个错误写法 → Langfuse 看板全空。
3. **缺 LLM 工程化 5 件套**（timeout / max_retries / sample_rate / flush / blocked_keys）——P0-4 修了；如果不修 → M7/M8/M10 各自再实现一遍，重复且不一致。
4. **缺下游契约预留**（judge / summarize / answer_chitchat 节点）——P1-5 修了；如果不修 → M11 / M7 plan 各自 hack M3 工厂（monkey patch / 重新注册），破坏 M3 范本权威性。

### 范本对其他 9 份 plan 的实际影响（采样 M7 / M10 / M11 验证）

| 后续 M | 是否引用 M3 11 段结构 | 是否引用 M3 契约表 | 是否有 M3 缺陷的复制 | 严重度 |
|---|---|---|---|---|
| M4 ingest-file | ✅ Files 表同构 | ✅ 用 `TEIEmbedder.embed` | ⚠️ 估计也"列 yaml 无内容" | 中 |
| M5 ingest-url | ✅ | ✅ | ⚠️ | 中 |
| M6 ingest-confluence | ✅ | ✅ | ⚠️ | 中 |
| M7 graph | ✅ | ✅ 引用 `make_llm(4 节点)` | ❌ **漏 `answer_chitchat` 节点**——M7 plan L19 提"intent ∈ {retrieve, chitchat}" 但 make_llm 没注册 chitchat | **高** |
| M8 api-chat | ✅ | ✅ 调 graph | ⚠️ | 中 |
| M9 ui-gradio | ✅ | ✅ 调 M8 | 无 | 低 |
| M10 obs-langfuse | ✅ | ✅ 基于 `get_callback_handler` | ❌ **M10 自己重写 CallbackHandler 注入**——M3 工厂 callback 注入错，M10 必须在节点层补救 | **高** |
| M11 eval-ragas | ✅ | ✅ 用 `make_llm("judge")` | ❌ **`judge` 节点 M3 plan 完全没提** | **高** |
| M12 hardening | ✅ | ✅ 调 M0/M3 全套 | 无 | 低 |

**结论**：M3 作为范本**结构性影响成功**（9 份 plan 全部按 11 段起草），**契约性影响部分失败**（3 份 plan 引用了 M3 工厂契约但 M3 工厂本身有缺陷，导致 M7/M10/M11 不得不"绕过"或"补强" M3）。**M3 plan 必须修 P0-1/P0-2/P0-4/P1-5 后才是合格的"范本"**。

---

## 与已有 review 交叉验证

| ID | 已有 review 项 | M3 现状 | 本报告 |
|---|---|---|---|
| P0-12 | langfuse import 路径风险 | ⚠️ 单路径，无 fallback | P1-2 |
| P0-13 | 4 节点 prompt yaml 实际内容未写 | ❌ **未改** | **P0-1**（升级到 P0 + 给完整草稿） |
| P0-14 | make_llm 注入 callback 方式过时 | ❌ **未改** | **P0-2**（升级到 P0 + 完整重写） |
| P0-18 | pytest-httpx 缺声明 | ❌ **未改** | P1-3 |
| P1-13 | 4 yaml ≥ 50 token 无验证 | ❌ | P2-2（补守门测试） |
| P1-14 | make_llm callback 注入 | 同 P0-14 | P0-2 |
| P1-12 | langfuse import 路径 | 同 P0-12 | P1-2 |
| X-1 | `app/config.py` 拆分（configs/ 子目录）| ❌ 未在本 plan 落实 | P1 跨 M 协调（备注：M0 review P2-3 已要求 M0 拆，但 M3 Task 1 仍用单文件 `app/config.py` 聚合，X-1 决议未落地）|
| X-3 | `from app.config import settings` 全局单例 | ⚠️ Task 1 GREEN 段写 `Settings()` 聚合但**未在文件末尾 `settings = Settings()`** | 跨 M 协调（与 M0 review P1-9 同问题）|
| X-4 | prod 分离 | N/A（M12） | — |
| 跨 M 依赖版本漂移 | M2 review P0-1 指 M2 argon2-cffi/cryptography 与 spec §8.3 不一致 | ✅ M3 5 个直接依赖（langchain / langchain-core / langchain-anthropic / langfuse / httpx / tenacity）**全部与 spec §8.1/§8.2/§8.6 对齐** | **M3 没踩这个坑**——可作为 M2 修复参考 |

**验证结论**：
- 已有 review 列出的 M3 范围 5 项：**全部 ❌ 未改**
- 升级到 P0 的 2 项：P1-13→P0-1 / P1-14→P0-2
- 跨 M 一致性 2 项（X-1 / X-3）：M3 没比 M0/M2 做得更好（X-3 仍未落实全局单例）

---

## 你发现的新问题（已有 review 未列）

合计 **10 个新问题**：

1. **P0-1** · 4 节点 prompt yaml 在 plan 中完全没草稿（升级自 P1-13 + 给完整草稿 + 范本污染警告）
2. **P0-3** · TEIEmbedder 缺 dim 硬约束断言 + batch_size 协调 + normalize/truncate 明确语义
3. **P0-4** · 缺 LLM 工程化 5 件套：timeout / max_retries / sample_rate / flush / blocked_keys
4. **P1-1** · 4 节点 LLM 没显式 deterministic 控（classify/rerank 强制 temperature=0.0）
5. **P1-4** · M3 plan 内部字段冲突：`LLMSettings.model` 全局 vs yaml `model` 节点级，谁优先没定
6. **P1-5** · M3 缺下游契约：`make_llm("judge")` 是 M11 强依赖 / `answer_chitchat` 是 M7 强依赖，工厂应注册表化
7. **P1-6** · Task 4 估时 5 分钟实际 10-15 分钟（M0 review P2-6 同类问题）
8. **P2-1** · 4 yaml 加载缺热加载设计（mtime cache key）
9. **P2-2** · DoD 第 7 条 yaml ≥ 50 token 缺测试守门
10. **P2-3** · PyYAML 缺 pyproject 声明
11. **P2-5** · TEIEmbedder 缺 context manager 协议
12. **P2-6** · 集成测试 smoke 缺 4 节点 parametrize 覆盖

---

## 落地建议

按 P0 → P1 → P2 优先级：

### 第一波（本轮必改，4 项 P0）

1. **P0-1** 在 Files 表后补 `§4 草稿段`，给 4 yaml 各 5-10 行伪代码（classify/rewrite/rerank/answer），并 Task 4 RED 段补"锚定 yaml 实际字符串"断言
2. **P0-2** Task 4 GREEN 段改 `make_llm` 写法：用 `model.with_config({"callbacks": [handler]})` 替代 `model.callbacks`，并 Task 4 RED 段补"不写进 model.callbacks 字段"断言
3. **P0-3** Task 2 GREEN 段补 `EmbeddingDimMismatch` 异常 + dim 硬断言 + 4xx/5xx 分类 + `httpx.Timeout(60.0)`
4. **P0-4** Task 1 GREEN 段 LLMSettings 补 `timeout/max_retries`、LangfuseSettings 补 `sample_rate/flush_at/flush_interval/blocked_keys`，`make_llm` 构造传 `timeout/max_retries`

### 第二波（重要，6 项 P1）

5. **P1-1** `make_llm` 内强制 `classify/rerank` temperature=0.0
6. **P1-2** langfuse import 加双备路径 + 测试
7. **P1-3** pyproject dev 依赖补 `pytest-httpx>=0.30,<1` + `pyyaml>=6.0,<7`
8. **P1-4** `LLMSettings.model` 字段二选一（推荐删除，yaml 唯一来源）
9. **P1-5** 工厂改注册表：`KNOWN_NODES = ("classify", "rewrite", "rerank", "answer", "judge", "summarize", "answer_chitchat")`，并 Files 表加 `app/prompts/judge.yaml` 占位
10. **P1-6** Task 4 拆 4a/4b/4c，或 DoD 标"Task 4 约 20 分钟"

### 第三波（优化，6 项 P2）

11. **P2-1** `load_prompt_cfg` 加 mtime cache key
12. **P2-2** 新增 `test_prompt_yaml_guard.py` 守门测试
13. **P2-3** pyproject 加 `pyyaml`
14. **P2-4** M3 估时改"2 个工作日（Tasks ~6h + 调试 ~6h + 文档 ~4h）"
15. **P2-5** `TEIEmbedder` 加 `__aenter__/__aexit__`
16. **P2-6** 集成测试 `test_make_llm_smoke_for_all_nodes` parametrize 4 节点

### 跨 M 协调（M3 改完后通知）

- 通知 **M7 graph**：`make_llm` 工厂已注册 `answer_chitchat` 节点（classify intent=chitchat 分支用）
- 通知 **M10 obs-langfuse**：M3 工厂 callback 注入已用 `with_config` 正确写法，M10 节点层 trace 不必再补 callback
- 通知 **M11 eval-ragas**：`make_llm("judge")` 已注册，`app/prompts/judge.yaml` 占位文件已建
- 通知 **M2/M0**：M3 已用 `app/config.py` 聚合配置；X-3 全局单例仍待跨 M 决议

### 范本修正（M3 改完后建议作为 M4-M12 起草标准）

M3 范本**结构**（11 段）保持不变，**内容** 强化以下 3 条（写入 `apps/rag_v1/AGENTS.md` 给后续 plan 起草参考）：
- 所有"列文件名无内容"的 Files 必须给至少 1 段伪代码草稿
- callback 注入统一用 `.with_config({"callbacks": [handler]})` 协议
- LLM 工厂必须用注册表 + 显式列 KNOWN_NODES（让下游 M 引用时能确认节点存在）

---

## 状态

- **不可动手**：P0-1 ~ P0-4 共 4 项必改
- **建议本轮改**：P1-1 ~ P1-6 共 6 项
- **可下轮改**：P2-1 ~ P2-6 共 6 项
- **新问题合计**：12 个（已有 review 未列），其中 3 个升级到 P0
- **已有 review 验证**：M3 范围 5 项 P1 + 跨 M 2 项，**全部 ❌ 未改**
- **范本定位**：M3 是 5 份 plan 中**唯一**值得作为"骨架样板"的，11 段 + 仓库布局 + 契约边界表 + 版本 pin 都对；但 P0-1/P0-2/P0-4/P1-5 这 4 项不修，会把缺陷传染给 M4-M12 全部 9 份下游 plan

M3 plan **结构对、版本对、契约清**；**作为范本的内容示范是失败的**——4 yaml 空壳 + callback 过时写法 + 缺 LLM 工程化 + 漏下游契约 = 范本会污染下游 9 份 plan。**修完 4 个 P0 后可作为"骨架范本"；P0+P1 修完后可作为"完整范本"给 M4–M12 复制。**
