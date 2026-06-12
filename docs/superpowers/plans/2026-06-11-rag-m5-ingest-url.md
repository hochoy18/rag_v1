# M5 Plan · Ingest URL 源（4 种 Auth 模式）

> 所属：RAG V1 M0–M12 实施路线 · 第 5 步
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §3.1 ingest 数据流](../specs/2026-06-10-rag-v1-scope.md#31-ingest-数据流) · [决策总表 #4/#15](../specs/2026-06-10-rag-v1-scope.md#0-决策总表) · [§5 错误矩阵](../specs/2026-06-10-rag-v1-scope.md#5-错误矩阵)
> 范本：M3 plan L1-319（11 段结构）
> 脑暴基线：v0.4 spec 决策 #4 数据源 / 决策 #15 URL auth 四模式
> 估时：4-5 个工作日（P2-3 修正：原估时 3d 偏紧）
> Review 避雷：P0-1（端口 18080） / P0-5（真 PG） / P1-5（payload_hash UNIQUE） / **P-新增**（SSRF 白名单） / **M5 r1**：P0-1 SSRF redirect bypass / P0-2 pipeline 失败残留 pending / P1-6 payload_hash 含 user_id

---

## Goal

把 v1-scope 决策 #4（数据源含 url）和 #15（url auth 4 模式）落成可执行代码契约：

1. 一个 `app/ingest/auth.py`：4 种 auth 配置数据类 + 加载函数（bearer / basic / cookie / header）
2. 一个 `app/ingest/sources/url.py`：用 `httpx` + `TrafilaturaWebReader` 抓取 URL，串联 M4 pipeline
3. URL 白名单防 SSRF：拒绝 127.0.0.1、localhost、私有 IP 段、IPv4-mapped IPv6（`::ffff:10.0.0.1`）、redirect 目标二次校验
4. 错误处理矩阵：httpx 超时 60s / 5xx 指数退避 3 次 / 4xx 立即失败 / 301-302 跟随最多 3 次 / Trafilatura 解析失败 / pipeline 失败
5. 幂等键：`payload_hash = sha256(url + auth_type + user_id)`，沿用 M1 ingest_jobs UNIQUE 约束
6. 集成端到点：mock `/api/ingest` 路由（真路由 M8 写）→ `ingest_url(url, auth_config, user_id)` → upsert chunks
7. URL 格式校验：长度 ≤ 2048 / scheme=http(s) / hostname 非空（与 SSRF 校验分离）

**不包含**（其他 M 负责）：
- M4 ingest pipeline 主体（parse → split → embed → upsert）—— M5 **复用** M4 的 `pipeline.run(docs, user_id, job_id)` 接口
- M6 confluence 源 —— M6 复用本 M5 的 `app/ingest/auth.py` 加载机制
- M8 `/api/ingest` 真实路由 —— M5 集成测试只 mock 路由
- OAuth 流程 / 浏览器渲染 / JS 抓取 —— V1 不做（V1.1 才加 Playwright 后端）

---

## Architecture

### 仓库布局（M5 增量）

```
apps/rag_v1/
├── app/
│   └── ingest/
│       ├── __init__.py
│       ├── sources/
│       │   ├── file.py            # M4（已存在）
│       │   ├── url.py             # M5 新增
│       │   └── confluence.py      # M6 复用 M5 的 auth.py
│       ├── auth.py                # M5 新增（4 种 auth 加载 + AuthType enum）
│       ├── pipeline.py            # M4（复用，不改）
│       ├── splitter.py            # M4（复用，不改）
│       └── ssrf.py                # M5 新增（URL 白名单 + IPv4-mapped 转换 + redirect 二次校验）
├── tests/
│   ├── unit/
│   │   ├── test_ingest_auth.py            # M5 新增
│   │   ├── test_ingest_ssrf.py            # M5 新增
│   │   └── test_ingest_url.py             # M5 新增
│   └── integration/
│       └── test_m5_ingest_url.py          # M5 新增（真 PG + mock 路由 + pytestmark asyncio）
├── pyproject.toml                # 追加 trafilatura / llama-index-readers-web
└── .env.example                  # 追加 INGEST_URL_TIMEOUT=60 / MAX_REDIRECTS=3 / RETRY_MAX=3 / USER_AGENT
```

### M5 模块树

```
apps/rag_v1/
├── app/ingest/
│   ├── sources/url.py        fetch_url(url, auth_config) -> list[Document]
│   │                          ingest_url(url, auth_config, user_id) -> job_id
│   │                          parse_url_to_documents(url, html) -> list[Document]
│   ├── auth.py               AuthType (StrEnum: bearer/basic/cookie/header)
│   │                          AuthConfig (Union[BearerAuth|BasicAuth|CookieAuth|HeaderAuth])
│   │                          load_auth_config(payload: dict) -> AuthConfigUnion
│   │                          to_httpx_kwargs(auth) -> dict
│   └── ssrf.py               assert_safe_url(url) -> None  # 抛 UnsafeURLError
│                              validate_url_format(url) -> None  # 抛 ValueError（P1-2）
└── tests/
    ├── unit/
    │   ├── test_ingest_auth.py        4 种 auth 模式独立 RED/GREEN
    │   ├── test_ingest_ssrf.py        黑名单 / 私有 IP / IPv6 loopback / IPv4-mapped / DNS rebinding
    │   └── test_ingest_url.py         fetch / 重试(4xx 不重试) / 重定向 / pipeline 串联 / parse 失败
    └── integration/
        └── test_m5_ingest_url.py      真 PG + mock /api/ingest + mock httpbin
                                       (pytestmark = pytest.mark.asyncio)
```

### M5 数据流

```
POST /api/ingest   (M8 写；M5 集成测试 mock 这个路由)
  body: { source: "url", payload: {url, auth_type, ...auth_value}, user_id }
  ↓
ingest_url(url, auth_config, user_id)        [app/ingest/sources/url.py]
  ├── validate_url_format(url)              [app/ingest/ssrf.py · P1-2 格式校验]
  ├── assert_safe_url(url)                  [app/ingest/ssrf.py · SSRF]
  ├── payload_hash = sha256(url + auth_type + user_id)   [P1-6 含 user_id]
  ├── INSERT ingest_jobs (status=pending)   [复用 M4 model]
  ├── 外层 try/except 包裹 fetch + parse + pipeline（P0-2）
  │   ├── 失败 → ingest_jobs.status=failed, error 字段记录原因
  │   │   ├── SSRF: UnsafeURLError → "SSRF: ..."
  │   │   ├── 4xx: httpx.HTTPStatusError → "HTTP 401"
  │   │   ├── 5xx 重试耗尽: RetryableHTTPError → "HTTP 500 after N retries"
  │   │   ├── Trafilatura 解析失败: ValueError → "Trafilatura parse failed: ..."
  │   │   └── pipeline 失败: 任意 Exception → str(e)[:1000]
  │   └── 成功 → ingest_jobs.status=indexed
  └── return job_id
```

### M5 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M8 `/api/ingest` 路由 | `ingest_url(url: str, auth_payload: dict, user_id: UUID) -> UUID` | M5 暴露函数；M8 转 payload dict → AuthConfig |
| M6 confluence | `load_auth_config(payload)` + `to_httpx_kwargs(auth)` + `AuthType` enum 复用 | 4 种 auth 模式直接照搬；M6 plan 修订记录已标"复用 M5 SSRF 防护" |
| M4 pipeline | `pipeline.run(docs, user_id, job_id)` | 复用 M4 已有接口，不改 |
| M7 retrieval | `OpenSearchClient.upsert_chunks(chunks)` | M5 调用；M7 实现 |
| M1 ingest_jobs | model + UNIQUE(payload_hash) | 幂等靠 DB 约束 + `ON CONFLICT DO NOTHING`；payload_hash 含 user_id（P1-6） |

---

## Tech Stack

| 层 | 选型 | 版本（精确） | 备注 |
|----|------|------------|------|
| HTTP 客户端 | `httpx` | `>=0.27,<1` | M3 已装；M5 复用 |
| HTML 解析 | `trafilatura` | `>=1.12,<2` | M5 新增；M4 用 `unstructured` 处理 file，M5 URL 用 trafilatura |
| 重试 | `tenacity` | `>=8.3,<10` | M3 已装；M5 复用；4xx 不触发重试（仅 RetryableHTTPError/Timeout/ConnectError） |
| SSRF 检测 | `ipaddress` (stdlib) | — | 不引外部库，stdlib `ipaddress.ip_address` 够用；含 IPv4-mapped IPv6 转换 |
| URL 解析 | `urllib.parse` (stdlib) | — | 不引 `tldextract` / `validators` |
| URL 格式校验 | `urllib.parse` (stdlib) | — | P1-2 新增：长度 ≤ 2048 / scheme 限制 / hostname 非空 |
| LlamaIndex Reader | `llama-index-readers-web` | `>=0.3,<0.4` | M5 新增；带 `TrafilaturaWebReader`；版本区间收紧（P2-5 修正） |
| AuthType 枚举 | `enum.StrEnum` (stdlib) | — | P1-10 抽出集中定义，避免 M6 复用时复制魔数 |
| 测试 | `pytest` / `pytest-asyncio` / `pytest-httpx` | 见 §测试 | 复用 M3；集成测试显式 `pytestmark = pytest.mark.asyncio`（P2-6 修正） |

**关键导入路径**：

```python
# 抓取
import httpx
from llama_index.readers.web import TrafilaturaWebReader

# 重试
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# SSRF
import ipaddress
from urllib.parse import urlparse

# Pydantic 配置
from pydantic import BaseModel, Field, SecretStr, HttpUrl

# AuthType 枚举（P1-10）
from enum import StrEnum
```

**依赖追加**（`pyproject.toml` 完整片段，P2-4 修正）：
```toml
dependencies = [
  # ... M3 已装（httpx>=0.27,<1 / tenacity>=8.3,<10 / pydantic>=2,<3 / sqlalchemy[asyncio]>=2,<3 等）...
  "trafilatura>=1.12,<2",
  "llama-index-readers-web>=0.3,<0.4",  # P2-5 收紧版本区间
]

[project.optional-dependencies]
dev = [
  # ... M3 已装（pytest>=8 / pytest-asyncio>=0.23 / pytest-httpx>=0.30 / pytest-cov>=5）...
  "testcontainers[postgresql]>=4.8",  # P0-5 真 PG 强制
]
```

**Python 导入规则**：
- `app.ingest.sources.url` —— `app` 是 `apps/rag_v1/app/`
- `tests.unit.test_ingest_url` —— 跑测试时 `cd apps/rag_v1 && pytest`

---

## Files

**新增**（5 个源文件 + 3 个测试文件）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
| `app/ingest/exceptions.py` | **r2 NP-5 新增** · M5 异常类收口：`UnsafeURLError` / `URLFormatError` / `RetryableHTTPError`（M4 r1 review P1-6 已建此文件，M5 **复用不新建**——本行 M5 显式声明） |
| `app/ingest/sources/__init__.py` | 暴露 `ingest_url` |
| `app/ingest/sources/url.py` | `fetch_url` + `parse_url_to_documents` + `ingest_url` 主入口（含 P0-2 外层 try/except + P0-1 redirect 二次校验）；**r2 NP-5 修正**：`RetryableHTTPError` 改为 `from app.ingest.exceptions import RetryableHTTPError` |
| `app/ingest/auth.py` | 4 种 AuthConfig Pydantic 模型 + `AuthType` StrEnum（P1-10）+ 加载 + `to_httpx_kwargs`；**r2 NP-2 修正**：4 子类统一加 `model_config = ConfigDict(extra="forbid")` 强制互斥字段 |
| `app/ingest/ssrf.py` | `assert_safe_url` + `validate_url_format`（P1-2）+ IPv4-mapped 转换（P2-1）；**r2 NP-5 修正**：`UnsafeURLError` / `URLFormatError` 类定义从本文件**移到** `app/ingest/exceptions.py`，本文件只 `from app.ingest.exceptions import UnsafeURLError, URLFormatError` |
| `app/ingest/__init__.py` | 暴露 `ingest_url` / `load_auth_config` / `to_httpx_kwargs` / `URLFormatError` / `UnsafeURLError` / `RetryableHTTPError`（**r2 NP-5**：M6 复用统一从 `app.ingest` 入口 import） |
| `tests/unit/test_ingest_auth.py` | 4 种 auth 模式独立测试 + AuthType 枚举测试 |
| `tests/unit/test_ingest_ssrf.py` | SSRF 黑名单 / 私有 IP / IPv6 / IPv4-mapped（P2-1）/ DNS rebinding / URL 格式校验（P1-2/P1-3）/ redirect 二次校验（P0-1） |
| `tests/unit/test_ingest_url.py` | fetch / 重试(4xx 不重试,P2-2) / 重定向(SSRF 二次校验) / pipeline 串联 / parse 失败（P1-1）|
| `tests/integration/test_m5_ingest_url.py` | 真 PG + mock 路由 + mock httpbin；`pytestmark = pytest.mark.asyncio`（P2-6）|
| `.env.example` | 追加 `INGEST_URL_TIMEOUT=60`（P1-5 默认 60s）/ `INGEST_MAX_REDIRECTS=3` / `INGEST_RETRY_MAX=3` / `INGEST_USER_AGENT=rag-v1-ingest/0.1`（P1-8）/ auth secrets 注释指导（P1-4）|

**修改**：
- `pyproject.toml`：追加 `trafilatura>=1.12,<2` / `llama-index-readers-web>=0.3,<0.4`（P2-5 收紧）到 `[project.dependencies]`；给完整 toml 片段（P2-4）
- `app/config.py`（M0-M3 已有）：追加 `IngestSettings`（`url_timeout: int = 60` / `max_redirects: int = 3` / `retry_max_attempts: int = 3` / `user_agent: str = "rag-v1-ingest/0.1"`）；P1-5 默认 60s
- `pytest.ini`（如未存在）：设 `asyncio_mode = auto`（P2-6 兜底）

**不修改**：
- `app/ingest/pipeline.py`（M4 共用）—— M5 只调用，不改
- `app/ingest/splitter.py`（M4 共用）
- `app/embedding/client.py`（M3）—— M5 通过 M4 pipeline 间接调用
- `app/db/models.py`（M1）—— M1 已有 `ingest_jobs` model，M5 直接 import

---

## Tasks（Task 1-3: 5-10min · Task 4-5: 20-30min · Task 6-9: 10-15min · P2-3 修正）

### Task 1：Pydantic 配置块（IngestSettings）

**RED** · `tests/unit/test_config.py::test_ingest_settings_loads`（M0 已有 test_config.py，M5 追加）
- mock env vars → 加载 `Settings().ingest` → 断言 `url_timeout == 60`（P1-5 默认 60s）/ `max_redirects == 3` / `retry_max_attempts == 3` / `user_agent == "rag-v1-ingest/0.1"`
- 跑测试 → 失败（配置不存在）
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_config.py::test_ingest_settings_loads`

**GREEN** · 改 `app/config.py`：
- 新增 `IngestSettings`：`url_timeout: int = 60`（P1-5 默认 60s）/ `max_redirects: int = 3` / `retry_max_attempts: int = 3` / `user_agent: str = "rag-v1-ingest/0.1"`（P1-8 显式列 .env）
- 顶层 `Settings` 聚合（X-1 拆分 configs/ 是后续轮次，本 M 先在 `app/config.py` 追加）

**REFACTOR** · 无（M5 只加一个配置块，不触其他子配置）

---

### Task 2：AuthConfig 数据类（4 模式 + AuthType 枚举）

**RED** · `tests/unit/test_ingest_auth.py::test_load_bearer_auth`
- 传 `{"auth_type": "bearer", "token": "abc123"}` → 断言 `load_auth_config(payload)` 返回 `BearerAuth(token=SecretStr("abc123"))`
- 跑测试 → 失败（模块不存在）

**GREEN** · `app/ingest/auth.py`：
```python
from enum import StrEnum
from typing import Literal, Union
from pydantic import BaseModel, ConfigDict, SecretStr, Field  # r2 NP-2：追加 ConfigDict

class AuthType(StrEnum):
    """P1-10 集中定义 auth 类型字符串，避免散落魔数（M6 复用时也引用此枚举）。"""
    BEARER = "bearer"
    BASIC = "basic"
    COOKIE = "cookie"
    HEADER = "header"

class AuthConfig(BaseModel):
    # r2 NP-2 修正：父类即开 extra="forbid"，子类继承——避免"bearer + 偷塞 username/password"被静默接受
    model_config = ConfigDict(extra="forbid")
    auth_type: AuthType

class BearerAuth(AuthConfig):
    auth_type: Literal[AuthType.BEARER] = AuthType.BEARER
    token: SecretStr

class BasicAuth(AuthConfig):
    auth_type: Literal[AuthType.BASIC] = AuthType.BASIC
    username: str
    password: SecretStr

class CookieAuth(AuthConfig):
    auth_type: Literal[AuthType.COOKIE] = AuthType.COOKIE
    name: str
    value: SecretStr

class HeaderAuth(AuthConfig):
    auth_type: Literal[AuthType.HEADER] = AuthType.HEADER
    name: str
    value: SecretStr

AuthConfigUnion = Union[BearerAuth, BasicAuth, CookieAuth, HeaderAuth]

def load_auth_config(payload: dict) -> AuthConfigUnion:
    """根据 auth_type 字段 dispatch 到对应子类。

    r2 NP-2：依赖 Pydantic `extra="forbid"`，多余字段（如 bearer 同时带 username/password）抛 ValidationError。
    """
    auth_type = payload.get("auth_type")
    cls = {
        AuthType.BEARER: BearerAuth,
        AuthType.BASIC: BasicAuth,
        AuthType.COOKIE: CookieAuth,
        AuthType.HEADER: HeaderAuth,
    }.get(AuthType(auth_type)) if auth_type else None
    if cls is None:
        raise ValueError(f"Unknown auth_type: {auth_type}")
    return cls.model_validate(payload)  # r2 NP-2：extra="forbid" 在此处触发
```

**RED** · `test_load_basic_auth` / `test_load_cookie_auth` / `test_load_header_auth`（3 个独立测试）
- 各自传 dict → 断言返回对应子类，`SecretStr` 不在 repr 泄露

**GREEN** · 上面 `load_auth_config` 4 路径全 GREEN

**RED** · `test_load_auth_config_rejects_unknown_type`
- 传 `{"auth_type": "oauth"}` → 断言 `ValueError`
- 跑测试 → 失败（无 raise）

**GREEN** · 加 raise

**RED** · `test_load_auth_config_rejects_missing_required_field`
- bearer 缺 `token` → 断言 `ValidationError`

**GREEN** · Pydantic 自动校验，0 额外代码

**RED** · `test_authtype_enum_values`（P1-10 验证枚举）
- 断言 `AuthType.BEARER.value == "bearer"` 等 4 个值；`AuthType("bearer") is AuthType.BEARER` 解析正确

**RED** · `test_auth_modes_mutually_exclusive`（r2 NP-2 新增）
- 4 个独立断言：传 `BearerAuth + username/password` / `BasicAuth + token` / `CookieAuth + token` / `HeaderAuth + username/password`，各断言 `ValidationError`（Pydantic `extra="forbid"` 触发）
- 跑测试 → 失败（默认 Pydantic 接受多余字段，r0 未开 forbid）

**GREEN** · 父类 `AuthConfig.model_config = ConfigDict(extra="forbid")` 已加，子类继承——4 个 RED 全 GREEN，0 额外代码

---

### Task 3：AuthConfig → httpx 参数适配

**RED** · `tests/unit/test_ingest_auth.py::test_bearer_to_httpx_headers`
- 构造 `BearerAuth(token="abc")` → 断言 `to_httpx_kwargs(BearerAuth(...)) == {"headers": {"Authorization": "Bearer abc"}}`

**GREEN** · `app/ingest/auth.py` 追加：
```python
def to_httpx_kwargs(auth: AuthConfigUnion) -> dict:
    """把 AuthConfig 转成 httpx.AsyncClient 接受的 kwargs。

    P1-4 安全注意：调用方应避免在 trace/log/异常栈中打印整个 kwargs dict；
    M12 hardening 阶段会加 secrets.redact() 过滤器。
    """
    if isinstance(auth, BearerAuth):
        return {"headers": {"Authorization": f"Bearer {auth.token.get_secret_value()}"}}
    if isinstance(auth, BasicAuth):
        return {"auth": (auth.username, auth.password.get_secret_value())}
    if isinstance(auth, CookieAuth):
        return {"cookies": {auth.name: auth.value.get_secret_value()}}
    if isinstance(auth, HeaderAuth):
        return {"headers": {auth.name: auth.value.get_secret_value()}}
```

**RED** · `test_basic_to_httpx_auth_tuple` / `test_cookie_to_httpx_cookies_dict` / `test_header_to_httpx_headers_dict`（3 个独立测试）
- 各自验证 key/value 类型正确

**GREEN** · 上面 `to_httpx_kwargs` 4 路径全 GREEN

---

### Task 4：SSRF 白名单（含 IPv4-mapped 转换 + URL 格式校验 + 长度限制）

**RED** · `tests/unit/test_ingest_ssrf.py::test_rejects_localhost`
- `assert_safe_url("http://localhost/admin")` → 断言 `UnsafeURLError`

**GREEN** · `app/ingest/ssrf.py`（**r2 NP-5 修正**：`UnsafeURLError` / `URLFormatError` 类定义移到 `app/ingest/exceptions.py`，本文件只 import）：
```python
import ipaddress
from urllib.parse import urlparse
import socket
from app.ingest.exceptions import UnsafeURLError, URLFormatError  # r2 NP-5 异常类收口

MAX_URL_LENGTH = 2048  # P1-3 长度上限

# r2 NP-5：以下类定义从本文件移到 app/ingest/exceptions.py（M4 r1 review P1-6 已建），本文件不再定义
# class UnsafeURLError(ValueError): ...        # 已移到 exceptions.py
# class URLFormatError(ValueError): ...        # 已移到 exceptions.py

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local（含云元数据 169.254.169.254）
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

def validate_url_format(url: str) -> None:
    """P1-2 / P1-3：URL 格式校验（非安全相关）。

    - 长度 1-2048
    - scheme 必须 http/https
    - hostname 非空
    - 格式错误抛 URLFormatError（ValueError 子类），不与 SSRF 混用
    """
    if not url or len(url) > MAX_URL_LENGTH:
        raise URLFormatError(f"URL length must be 1-{MAX_URL_LENGTH}, got {len(url) if url else 0}")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise URLFormatError(f"URL scheme must be http/https, got {parsed.scheme!r}")
    if not parsed.hostname:
        raise URLFormatError(f"URL missing hostname: {url!r}")


def assert_safe_url(url: str) -> None:
    """SSRF 黑名单校验。

    流程：
    1. scheme 限制 http/https
    2. hostname 黑名单（localhost / ip6-localhost / ip6-loopback）
    3. DNS 解析后立即校验 IP（防 DNS rebinding 第一道）
    4. P2-1：IPv4-mapped IPv6（::ffff:10.0.0.1）转 IPv4 再对比私有网段
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme must be http/https: {parsed.scheme!r}")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("missing hostname")
    if hostname.lower() in ("localhost", "ip6-localhost", "ip6-loopback"):
        raise UnsafeURLError(f"localhost rejected: {hostname}")
    # 解析 hostname → IP（防 DNS rebinding 第一道：解析后立即校验）
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"DNS resolution failed: {hostname}") from e
    for info in infos:
        raw = info[4][0]
        ip = ipaddress.ip_address(raw)
        # P2-1：IPv4-mapped IPv6 转 IPv4 再对比（::ffff:10.0.0.1 → 10.0.0.1）
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        for net in _PRIVATE_NETS:
            if ip in net:
                raise UnsafeURLError(f"private/loopback IP rejected: {raw} in {net}")
```

**RED** · `test_rejects_private_ip_literal`（10.0.0.1 / 192.168.1.1 / 172.16.0.1 各一个 case）
- 传 `http://10.0.0.1/` → 断言 `UnsafeURLError`

**GREEN** · 上面 `_PRIVATE_NETS` 已覆盖

**RED** · `test_rejects_ipv6_loopback`
- `http://[::1]/` → 断言 `UnsafeURLError`

**GREEN** · `::1/128` 已加

**RED** · `test_rejects_link_local_169.254`
- `http://169.254.169.254/latest/meta-data/`（AWS 元数据）→ 断言 `UnsafeURLError`

**GREEN** · `169.254.0.0/16` 已加

**RED** · `test_rejects_ftp_scheme`
- `ftp://example.com/` → 断言 `UnsafeURLError`

**GREEN** · scheme 检查已加

**RED** · `test_rejects_dns_rebinding_to_private`（mock socket.getaddrinfo 返 127.0.0.1）
- 传 `http://attacker.com/` 但 `getaddrinfo` mock 返 127.0.0.1 → 断言 `UnsafeURLError`

**GREEN** · 上面循环 `for info in infos` 已覆盖

**RED** · `test_rejects_ipv4_mapped_ipv6`（P2-1）
- mock `getaddrinfo` 返 `('::ffff:10.0.0.1', ...)` → 断言 `UnsafeURLError`（"10.0.0.1" 出现在错误信息）

**GREEN** · 上面 `ip.ipv4_mapped` 转换已加

**RED** · `test_accepts_public_ip`
- `http://8.8.8.8/`（Google DNS 公网）→ 断言不抛

**GREEN** · 公网不在 `_PRIVATE_NETS` 内

**RED** · `test_validate_url_format_too_long`（P1-3）
- 传 `len > 2048` 字符串 → 断言 `URLFormatError`（非 `UnsafeURLError`）

**RED** · `test_validate_url_format_empty`（P1-2）
- 传 `""` → 断言 `URLFormatError("URL length must be 1-2048...")`

**RED** · `test_validate_url_format_ftp_scheme`（P1-2）
- 传 `"ftp://example.com/"` → 断言 `URLFormatError`（不是 UnsafeURLError，便于运营区分）

**RED** · `test_validate_url_format_missing_hostname`（P1-2）
- 传 `"http://"` → 断言 `URLFormatError`

---

### Task 5：fetch_url 抓取层（含 P0-1 redirect 二次校验 + P2-2 4xx 不重试）

**RED** · `tests/unit/test_ingest_url.py::test_fetch_url_returns_html`
- 用 `pytest-httpx` mock `https://example.com/` → 响应 `<html>...</html>`
- 调 `fetch_url("https://example.com/", BearerAuth(token="x"))` → 断言返回 `httpx.Response` 且 `status_code == 200`

**GREEN** · `app/ingest/sources/url.py`（**r2 NP-5 修正**：`RetryableHTTPError` 从 `app.ingest.exceptions` 导入，不再在 url.py 内部定义）：
```python
import httpx
from app.ingest.auth import AuthConfigUnion, to_httpx_kwargs
from app.ingest.ssrf import assert_safe_url, validate_url_format
from app.ingest.exceptions import RetryableHTTPError  # r2 NP-5 异常类收口
from app.config import settings

class SSRFRedirectTransport(httpx.AsyncBaseTransport):
    """P0-1：拦截 redirect 目标 URL，在每次重定向前执行 SSRF 校验。

    httpx 自身不会在 follow_redirects=True 时回调用户代码；
    自定义 transport 包裹真实 transport，在 handle_async_request 阶段对 request.url 校验。
    """
    def __init__(self, inner: httpx.AsyncBaseTransport):
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # 每个请求（包括 redirect 后的）都校验
        assert_safe_url(str(request.url))
        return await self._inner.handle_async_request(request)

async def fetch_url(url: str, auth: AuthConfigUnion) -> httpx.Response:
    validate_url_format(url)          # P1-2 格式校验先
    assert_safe_url(url)              # 初始 URL SSRF 校验
    timeout = httpx.Timeout(settings.ingest.url_timeout)  # P1-5 默认 60s
    kwargs = to_httpx_kwargs(auth)
    transport = SSRFRedirectTransport(httpx.AsyncHTTPTransport())
    async with httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=True,
        max_redirects=settings.ingest.max_redirects,
        headers={"User-Agent": settings.ingest.user_agent},
    ) as client:
        resp = await client.get(url, **kwargs)
    # 方案 B 兜底：手动检查 resp.history 中每个 URL（即使 transport 漏判，history 也会被校验）
    for r in resp.history:
        assert_safe_url(str(r.url))
    return resp
```

**RED** · `test_fetch_url_4xx_fails_immediately`
- mock 401 响应 → 断言 `fetch_url` 抛 `httpx.HTTPStatusError` 且**不重试**（用 `pytest-httpx` 的 `assert_called_once`）

**GREEN** · `resp.raise_for_status()` 在 client 上下文退出前调

**RED** · `test_fetch_url_5xx_retries_3_times`
- mock 前 2 次 500、第 3 次 200 → 断言成功 + httpx 调用 3 次

**GREEN** · 加 tenacity 装饰器（P2-2 修正：retry 条件不含 `httpx.HTTPStatusError`，仅含 `RetryableHTTPError`）：
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(settings.ingest.retry_max_attempts),
    wait=wait_exponential(multiplier=1, min=1, max=4),  # 1s/2s/4s
    # P2-2 修正：不包含 httpx.HTTPStatusError（4xx 不重试）；仅 RetryableHTTPError/Timeout/ConnectError
    retry=retry_if_exception_type((RetryableHTTPError, httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
async def fetch_url_with_retry(...): ...
```

注意：tenacity 重试只对 5xx 触发（4xx 不重试），`RetryableHTTPError` 自定义异常专用于 5xx 区分：

**RED** · `test_fetch_url_5xx_raises_for_retry`
- mock 500 → 断言抛 `RetryableHTTPError`（让 tenacity 接住）且 `response.status_code == 500`

**GREEN** · 自定义 `RetryableHTTPError`（**r2 NP-5 修正**：类定义在 `app/ingest/exceptions.py`，不在 url.py）：
```python
# app/ingest/exceptions.py（r2 NP-5 新增片段）
class RetryableHTTPError(httpx.HTTPStatusError):
    """5xx 专用，触发 tenacity 重试。
    P2-2：4xx 不抛此异常，而是抛 httpx.HTTPStatusError 且不被 tenacity 接住（retry 条件排除）。
    r2 NP-5：从 app/ingest/sources/url.py 收口到本文件，M6 复用时 import 路径统一。
    """

# app/ingest/sources/url.py（_maybe_raise_retryable 仍在 url.py）
def _maybe_raise_retryable(resp: httpx.Response) -> None:
    if 500 <= resp.status_code < 600:
        raise RetryableHTTPError("5xx", request=resp.request, response=resp)
    resp.raise_for_status()  # 4xx 立即失败（不重试）
```

**RED** · `test_fetch_url_redirect_follows_max_3`
- 链 4 次 302 → 断言抛 `httpx.TooManyRedirects`

**GREEN** · `max_redirects=3` 在 `AsyncClient` 已配

**RED** · `test_fetch_url_redirect_ssrf_checked`（P0-1 新增）
- mock 域名 `attacker.com` → 302 → `http://127.0.0.1/admin` → 断言抛 `UnsafeURLError`（不是 `TooManyRedirects`）

**GREEN** · `SSRFRedirectTransport` + `resp.history` 双重校验已加

**RED** · `test_fetch_url_timeout_30s`（注：实际为 60s，见 P1-5）
- mock `httpx.TimeoutException` → 断言 tenacity 重试 3 次后 reraise

**GREEN** · `tenacity` 装饰器覆盖 `TimeoutException`

---

### Task 6：TrafilaturaWebReader 解析层（含 P1-1 解析失败处理）

**RED** · `tests/unit/test_ingest_url.py::test_parse_html_to_documents`
- mock `TrafilaturaWebReader.load_data` 返回 `[Document(text="Hello world", metadata={"url": "..."})]`
- 调 `parse_url_to_documents("https://example.com/", auth)` → 断言返回 1 个 `Document`

**GREEN** · `app/ingest/sources/url.py`：
```python
from llama_index.core import Document
from llama_index.readers.web import TrafilaturaWebReader

def parse_url_to_documents(url: str, html: str) -> list[Document]:
    reader = TrafilaturaWebReader()
    docs = reader.load_data(urls=[url])  # trafilatura 内部重抓一次；为避免双重抓取，V1 接受这个开销
    return docs
```

注：`TrafilaturaWebReader` 内部会自己用 httpx 抓取。M5 决策：**抓取走我们自己的 `fetch_url`（带 auth + 重试 + SSRF 防护）→ 把 HTML 写入临时文件 → `TrafilaturaWebReader` 从文件读**。这避免重复抓取并保留我们的 auth/重试语义。

**RED** · `test_parse_uses_local_html_not_refetch`（mock httpx + 临时文件）
- mock httpx 响应 + 用 `tmp_path` 写 HTML → 断言 `TrafilaturaWebReader` 调 `load_data(urls=...)` 时传入的是 file:// URI，**不再发 httpx 请求**

**GREEN** · 改 `parse_url_to_documents`（P1-1 增加空 HTML / 解析失败 / 空 list 处理）：
```python
import tempfile, os
from pathlib import Path

def parse_url_to_documents(url: str, html: str) -> list[Document]:
    # P1-1：空 HTML / 编码错 / 二进制响应都抛 ValueError，让 ingest_url 外层 try 捕到并 mark failed
    if not html or not html.strip():
        raise ValueError(f"Empty HTML content from {url}")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp_path = f.name
    try:
        reader = TrafilaturaWebReader()
        try:
            docs = reader.load_data(urls=[f"file://{tmp_path}"])
        except (UnicodeDecodeError, ValueError, OSError) as e:
            # P1-1：trafilatura 解析失败（含编码错）转 ValueError 让外层 catch
            raise ValueError(f"Trafilatura parse failed for {url}: {e}") from e
        if not docs:
            # P1-1：HTTP 200 但 trafilatura 没提取到任何内容（HTML 太烂 / JS-only 页）
            raise ValueError(f"Trafilatura failed to extract any content from {url}")
        for doc in docs:
            doc.metadata["source_url"] = url
        return docs
    finally:
        os.unlink(tmp_path)
```

**RED** · `test_parse_empty_html_raises`（P1-1）
- 传 `html=""` → 断言 `ValueError("Empty HTML content...")`

**RED** · `test_parse_non_utf8_raises`（P1-1）
- 传 `html="\xff\xfe garbage"`（非 UTF-8 字节）→ 断言 `ValueError("Trafilatura parse failed...")`

**RED** · `test_parse_trafilatura_returns_empty_raises`（P1-1）
- mock `TrafilaturaWebReader.load_data` 返 `[]` → 断言 `ValueError("Trafilatura failed to extract...")`

---

### Task 7：ingest_url 主入口（串联 pipeline + 写 ingest_jobs + P0-2 外层 try + P1-6 含 user_id）

**RED** · `tests/integration/test_m5_ingest_url.py::test_ingest_url_creates_job_and_indexes_chunks`
- 启动真 PG（testcontainers 拉 pg:16）→ 建表（M1 alembic 跑过）→ mock httpx 响应 + mock TrafilaturaWebReader
- 调 `ingest_url("https://example.com/", {"auth_type": "bearer", "token": "x"}, user_id=uuid4())` → 断言：
  1. `ingest_jobs` 表新增 1 行，status=indexed，chunks_count>0
  2. payload_hash 符合 `sha256("https://example.com/" + "bearer" + str(user_id)).hexdigest()`（P1-6 含 user_id）

**GREEN** · `app/ingest/sources/url.py`（P0-2 / P1-6 修正 + **r2 NP-1 显式分 catch** + **r2 NP-5 import 改源**）：
```python
import hashlib
from uuid import UUID, uuid4
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from app.db.models import IngestJob, JobStatus
from app.db import async_session
from app.ingest.sources.url import fetch_url, parse_url_to_documents
from app.ingest.auth import load_auth_config
from app.ingest.ssrf import assert_safe_url, validate_url_format
from app.ingest.exceptions import (  # r2 NP-5 异常类收口
    UnsafeURLError, URLFormatError, RetryableHTTPError,
)
from app.ingest.pipeline import run_pipeline  # M4 提供

async def ingest_url(url: str, auth_payload: dict, user_id: UUID) -> UUID:
    auth = load_auth_config(auth_payload)
    # r2 NP-1：先显式分 catch URLFormatError（区别于 UnsafeURLError 便于运营分类）
    try:
        validate_url_format(url)  # P1-2 格式校验
    except URLFormatError as e:
        # 格式错不打 job（M5 决策：格式错是客户端错误，不浪费 job_id）；运营通过 HTTP 4xx 即可定位
        raise
    # r2 NP-1：再显式 catch UnsafeURLError（与 URLFormatError 顺序不可反）
    try:
        assert_safe_url(url)
    except UnsafeURLError as e:
        raise
    # P1-6：payload_hash 含 user_id，避免跨用户同 URL+auth_type 幂等误判
    payload_hash = hashlib.sha256(
        f"{url}{auth.auth_type}{user_id}".encode()
    ).hexdigest()
    job_id = uuid4()
    async with async_session() as session:
        # P1-5 幂等：UNIQUE(payload_hash) + ON CONFLICT DO NOTHING
        job = IngestJob(
            id=job_id, user_id=user_id, source="url",
            status=JobStatus.pending, payload_hash=payload_hash,
            payload=auth_payload,
        )
        session.add(job)
        try:
            await session.commit()
        except IntegrityError:
            # 重复 payload → 复用旧 job_id 返回
            existing = await session.scalar(select(IngestJob).where(IngestJob.payload_hash == payload_hash))
            return existing.id
    # P0-2：外层 try/except 包裹 fetch + parse + pipeline，任一失败都 mark failed
    try:
        resp = await fetch_url(url, auth)
        docs = parse_url_to_documents(url, resp.text)
        await run_pipeline(docs, user_id=user_id, job_id=job_id)
    except UnsafeURLError as e:
        # P1-7：SSRF 错误消息明确标注 "SSRF: " 前缀
        async with async_session() as session:
            job = await session.get(IngestJob, job_id)
            job.status = JobStatus.failed
            job.error = f"SSRF: {e}"
            await session.commit()
        raise
    except httpx.HTTPStatusError as e:
        # 4xx 立即失败（不应进 retry，但兜底捕）
        async with async_session() as session:
            job = await session.get(IngestJob, job_id)
            job.status = JobStatus.failed
            job.error = f"HTTP {e.response.status_code}"
            await session.commit()
        raise
    except ValueError as e:
        # P1-1：Trafilatura 解析失败 / 空 HTML / 格式错误
        async with async_session() as session:
            job = await session.get(IngestJob, job_id)
            job.status = JobStatus.failed
            job.error = f"Parse: {e}"
            await session.commit()
        raise
    except Exception as e:
        # P0-2：pipeline 失败 / 其他任意异常
        async with async_session() as session:
            job = await session.get(IngestJob, job_id)
            job.status = JobStatus.failed
            job.error = str(e)[:1000]
            await session.commit()
        raise
    return job_id
```

**RED** · `test_ingest_url_idempotent_on_repeat`
- 同一 url+auth_type+user_id 调 2 次 → 断言只 1 个 `ingest_jobs` 行，第二次返回旧 job_id
- 同一 url+auth_type + **不同 user_id** → 断言生成 2 个 job（P1-6 跨用户不幂等）

**GREEN** · 上面 `IntegrityError` catch 路径 + P1-6 user_id 加入 hash

**RED** · `test_ingest_url_records_failure_on_4xx`
- mock 401 → 断言 `ingest_jobs.status=failed`，`error` 字段含 "HTTP 401"

**GREEN** · `except httpx.HTTPStatusError` 已加

**RED** · `test_ingest_url_records_failure_on_ssrf`
- 传 `http://127.0.0.1/` → 断言 `UnsafeURLError` + `ingest_jobs.status=failed`，error 含 "SSRF"（P1-7 验证 SSRF 前缀）

**GREEN** · `except UnsafeURLError` 已加

**RED** · `test_ingest_url_marks_failed_on_parse_error`（P0-2 + P1-1）
- mock fetch 成功但 trafilatura 解析失败 → 断言 `ingest_jobs.status=failed`，error 含 "Parse"

**RED** · `test_ingest_url_marks_failed_on_pipeline_error`（P0-2）
- mock fetch + parse 成功但 `run_pipeline` 抛异常 → 断言 `ingest_jobs.status=failed`

**RED** · `test_ingest_url_payload_hash_format`（P1-6）
- 断言 `payload_hash == sha256(b"https://example.com/bearer" + str(user_id).encode()).hexdigest()`

**GREEN** · 上面 hash 计算已对

**RED** · `test_ingest_url_rejects_url_too_long`（P1-3）
- 传 `len > 2048` URL → 断言 `URLFormatError`（非 UnsafeURLError）

**RED** · `test_ingest_url_urlformat_vs_ssrf_distinguished`（r2 NP-1 新增）
- 传 `len > 2048` URL → 断言 `URLFormatError`（**不**进 `ingest_jobs` 表；M5 决策：格式错是客户端错，不浪费 job_id）
- 传 `http://127.0.0.1/` → 断言 `UnsafeURLError`（**进** `ingest_jobs` 表 status=failed，error 含 `"SSRF:"`）
- 跑测试 → 失败（r0 不区分，统一 raise）

---

### Task 8：4 种 auth 端到端集成测试

**RED** · `tests/integration/test_m5_ingest_url.py::test_ingest_url_with_bearer_auth`
- 启真 PG + mock httpx 期望 `Authorization: Bearer ***` header → 调 `ingest_url` 成功

**GREEN** · 上面的 `to_httpx_kwargs` 已注入

**RED** · `test_ingest_url_with_basic_auth`（断言 httpx 收到 `auth=("user", "pass")` tuple）

**RED** · `test_ingest_url_with_cookie_auth`（断言 httpx 收到 `cookies={"session": "..."}`）

**RED** · `test_ingest_url_with_header_auth`（断言 httpx 收到 `headers={"X-API-Key": "..."}`）

**GREEN** · 4 个测试都走同一个 `to_httpx_kwargs` 路径，RED 后 GREEN 取决于 Task 3 正确性

---

### Task 9：mock /api/ingest 路由（集成测试用）

注：M8 写真路由。M5 集成测试用 `fastapi.APIRouter` 临时挂载：

**RED** · `tests/integration/test_m5_ingest_url.py::test_api_ingest_url_endpoint`
- 构造 `app = FastAPI()`，临时挂 `app.include_router(make_test_router())`（内部调 `ingest_url`）
- `TestClient.post("/api/ingest", json={"source": "url", "payload": {...}, "user_id": str(uuid4())})` → 断言 202 + `{"job_id": "..."}`

**GREEN** · `tests/integration/_helpers.py` 写 `make_test_router()`：
```python
def make_test_router() -> APIRouter:
    router = APIRouter()
    @router.post("/api/ingest")
    async def ingest(req: IngestRequest, background: BackgroundTasks):
        if req.source != "url":
            raise HTTPException(400, "M5 only supports url")
        job_id = await ingest_url(req.payload["url"], req.payload, req.user_id)
        return {"job_id": str(job_id)}
    return router
```

注：M5 集成测试**不**挂鉴权（M2 范围），M8 真实路由会加。

---

## 测试策略

- **M5 单元（auth/ssrf/url）**：`cd apps/rag_v1 && pytest tests/unit/test_ingest_auth.py tests/unit/test_ingest_ssrf.py tests/unit/test_ingest_url.py` —— 全 mock（pytest-httpx / 临时文件 / monkeypatch socket.getaddrinfo），CI 内 1s
- **M5 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m5_ingest_url.py --require-docker` —— 需 testcontainers 真 PG（M1 schema 已 migrate）+ pytest-httpx mock httpbin 风格
- **集成测试显式 `pytestmark = pytest.mark.asyncio`**（P2-6 修正：每个集成测试 file 头部声明，避免依赖 pytest.ini 的 `asyncio_mode = auto`）
- **pytest.ini 兜底**（P2-6）：如未配 `asyncio_mode = auto`，M5 PR 顺手在 `pytest.ini` 加 `[pytest]\nasyncio_mode = auto`
- **覆盖率门禁**：`pytest --cov=app/ingest --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 [RED]）→ GREEN（commit 标 [GREEN]）→ REFACTOR（commit 标 [RF]）
- **真 PG 强制**（P0-5 避雷）：M5 集成测试**不用 sqlite**（ingest_jobs.payload 是 JSONB + payload_hash 是 UNIQUE 约束，sqlite 测不出真实语义）
- **URL 白名单独立测试**（P-新增 避雷）：test_ingest_ssrf.py 11+ case 覆盖 localhost / 私有 IPv4 / IPv6 loopback / IPv4-mapped（P2-1） / link-local 169.254 / FTP scheme / DNS rebinding / 公网放行 / 长度超限（P1-3） / 格式错（P1-2）
- **SSRF redirect 二次校验测试**（P0-1）：test_ingest_url.py::test_fetch_url_redirect_ssrf_checked

---

## 验证（Definition of Done）

- [ ] 4 种 auth 模式（bearer / basic / cookie / header）各有独立 RED/GREEN 单元测试
- [ ] `to_httpx_kwargs` 把 4 种 AuthConfig 正确转 httpx 接受的 kwargs
- [ ] `load_auth_config` 拒绝 `auth_type=oauth` 等未知类型
- [ ] `load_auth_config` 拒绝必填字段缺失（bearer 缺 token 等）
- [ ] **r2 NP-2** 4 auth 模式互斥：`BearerAuth + username/password` 等多余字段被 Pydantic `extra="forbid"` 拒绝（`test_auth_modes_mutually_exclusive` 4 个断言）
- [ ] `AuthType` StrEnum 集中定义（P1-10），M6 复用同一枚举
- [ ] SSRF 白名单拒绝 localhost / 127.0.0.1 / 10.x / 172.16.x / 192.168.x / ::1 / 169.254.x / 私有 IPv6 / IPv4-mapped IPv6（`::ffff:10.0.0.1` P2-1）/ ftp://
- [ ] SSRF 白名单放行公网 IP（8.8.8.8 等）
- [ ] **SSRF redirect 二次校验**（P0-1）：redirect 到 127.0.0.1 抛 `UnsafeURLError`
  - **r2 NP-3 边界标注 1**：`SSRFRedirectTransport` 仅适用于 httpx 客户端；M6 若用 aiohttp 需自实现等价 transport
  - **r2 NP-3 边界标注 2**：SSRF redirect 校验在 transport.handle_async_request 阶段（**不**重新做 DNS 解析——如果 URL 字符串是 IP literal 立即黑名单命中；如果是域名，依赖初始 `assert_safe_url` 已做的 DNS 校验）
- [ ] **URL 格式校验**（P1-2/P1-3）：长度 ≤ 2048 / scheme=http(s) / hostname 非空，错误抛 `URLFormatError`（非 UnsafeURLError）
- [ ] **r2 NP-1** `ingest_url` 入口显式分 catch `URLFormatError`（格式错**不**写 `ingest_jobs` 表，HTTP 4xx 直接返回；客户端错）与 `UnsafeURLError`（SSRF 错**写** `ingest_jobs` 表 status=failed，error 含 `"SSRF:"`）
- [ ] `fetch_url` 4xx 立即失败（**不重试**，P2-2 修正）+ 5xx 重试 3 次（1s/2s/4s 指数退避）+ 超时重试 3 次
- [ ] `fetch_url` 301-302 跟随最多 3 次，第 4 次抛 `TooManyRedirects`
- [ ] `parse_url_to_documents` 走"fetch → 临时文件 → TrafilaturaWebReader 读文件"，**不再二次抓取**
- [ ] `parse_url_to_documents` 解析失败 / 空 HTML / 非 UTF-8 / trafilatura 返空 → 抛 `ValueError`（P1-1）
- [ ] `ingest_url` 调一次 → ingest_jobs 表新增 1 行，status=indexed，chunks_count>0
- [ ] `ingest_url` 重复调（同一 url+auth_type+user_id）→ 幂等返回旧 job_id，DB 不新增（P1-6）
- [ ] `ingest_url` 同一 url+auth_type + **不同 user_id** → 生成不同 job（P1-6）
- [ ] `ingest_url` 4xx / 5xx / SSRF / Parse / pipeline 失败 → ingest_jobs.status=failed，error 字段填具体原因（P0-2）
- [ ] SSRF 错误消息含 "SSRF: " 前缀（P1-7），便于前端/运营区分
- [ ] `payload_hash = sha256(url + auth_type + user_id)`（P1-6）与 M1 ingest_jobs UNIQUE 约束配合
- [ ] 集成测试在真 PG + pytest-httpx 下 30s 内通过；测试 file 头部 `pytestmark = pytest.mark.asyncio`（P2-6）
- [ ] 单元覆盖率 ≥ 85%
- [ ] `.env.example` 追加 `INGEST_URL_TIMEOUT=60`（P1-5 默认 60s）/ `INGEST_MAX_REDIRECTS=3` / `INGEST_RETRY_MAX=3` / `INGEST_USER_AGENT=rag-v1-ingest/0.1`（P1-8）/ auth secrets 注释指导（P1-4）
- [ ] `pyproject.toml` 追加 `trafilatura>=1.12,<2` / `llama-index-readers-web>=0.3,<0.4`（P2-5 收紧）；dev 依赖加 `testcontainers[postgresql]>=4.8`
- [ ] P1-9 REFACTOR 备注：用 Pydantic discriminated union 替换手动 dispatch（`Annotated[Union[...], Field(discriminator='auth_type')]`），可选优化
- [ ] **r2 NP-5** M5 异常类（`UnsafeURLError` / `URLFormatError` / `RetryableHTTPError`）收口到 `app/ingest/exceptions.py`（M4 r1 review P1-6 已建）；`ssrf.py` / `url.py` 仅 import，不重新定义；M6 复用时 import 路径统一

---

## 与其他 M 的依赖

| 上游（必须 M5 前完成） | 下游（依赖 M5） |
|----------------------|----------------|
| M0 `docker-compose.yml`（TEI 18080 + OpenSearch 9200 + PG 5432） | M6 confluence 复用 `app/ingest/auth.py`（`load_auth_config` / `to_httpx_kwargs` / `AuthType`）+ **复用 M5 SSRF 防护**（`assert_safe_url` / `validate_url_format`，M6 修订记录 r1 已标） |
| M1 alembic（`ingest_jobs` 表 + UNIQUE(payload_hash)） | M8 `/api/ingest` 调 `ingest_url(url, auth_payload, user_id)` |
| M3 TEI 客户端（embed 调用链） | M9 端到端 ingest 测试（M9 集成 M4+M5+M6） |
| M4 pipeline（`pipeline.run` 复用） | |
| M7 OpenSearch `upsert_chunks`（M5 调用） | |

**M5 强依赖 M7**：写 `ingest_url` 时如果 M7 还没合，测试要 mock `upsert_chunks`。M7 plan 已起草（2026-06-10-rag-m7-graph.md），但具体 `upsert_chunks` 接口定义在 M7 plan 里要确认存在；如果 M7 还未实现该接口，M5 集成测试 mock 整个 OpenSearch 调用即可。

**跨 M 联动**（M6 复用 M5）：
- M6 confluence source 复用 `app/ingest/auth.py` 的 4 种 auth 加载（`AuthType` enum 共享）
- M6 复用 M5 的 `assert_safe_url` / `validate_url_format` / `SSRFRedirectTransport`（Confluence 站点对外，也可能受 SSRF 风险）
- M6 集成测试应覆盖 SSRF（mock confluence response 含 redirect）
- **r2 NP-5 跨 M 联动**：M6 复用 M5 异常类时统一从 `app.ingest.exceptions` 入口 import（`UnsafeURLError` / `URLFormatError` / `RetryableHTTPError`），不再从 `app.ingest.ssrf` 或 `app.ingest.sources.url` 零散 import——避免 M6 r2 NP-A 揭示的「异常类未对齐」源头
  - M6 plan 修订记录需补 1 行：`M6 r2 NP-A 已修 · 异常类统一从 app.ingest.exceptions import（源头是 M5 r2 NP-5）`
  - M6 集成测试 imports 段需替换 `from app.ingest.ssrf import UnsafeURLError` → `from app.ingest.exceptions import UnsafeURLError`（如已写需一并改）

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| **SSRF：攻击者传 `http://10.0.0.1/admin` 抓内网** | **M5 主动加白名单**（P-新增）：`assert_safe_url` 在 `fetch_url` 第一行；DNS 解析后立即校验 IP，不依赖客户端传值；测 9+ case 覆盖 | v0.4 spec §5 错误矩阵没显式提 SSRF——M5 主动加 |
| **SSRF redirect bypass**（P0-1） | `SSRFRedirectTransport` 拦截每次 redirect 目标 + `resp.history` 兜底双重校验；新增 `test_fetch_url_redirect_ssrf_checked` | 仅初始 URL 校验（被绕过） |
| **Pipeline 失败后 job 残留 pending**（P0-2） | `ingest_url` 外层 try/except 包裹 fetch + parse + pipeline；任意阶段异常都 mark `status=failed` 并填 `error` 字段 | 只裹 `fetch_url`（parse/pipeline 失败残留 pending） |
| **Trafilatura 解析失败**（P1-1） | `parse_url_to_documents` 加空 HTML / 编码错 / 空 list 检测，统一抛 `ValueError` 让外层 catch 标 failed | 让异常直接冒泡（残留 pending） |
| **URL 格式错误误导 SSRF**（P1-2） | `validate_url_format` 独立函数，抛 `URLFormatError`（非 `UnsafeURLError`）便于前端/运营区分 | 全部混用 `UnsafeURLError`（运营无法分类） |
| **URL 过长存储爆 / 隐式截断**（P1-3） | 长度限制 2048 字符；`validate_url_format` 检查 | 不检查（DB payload 字段可能爆） |
| **auth secrets 在 log/trace 泄露**（P1-4） | `SecretStr` 加密存储 + `.env.example` 注释指导走 secret manager；M12 hardening 加 `secrets.redact()` 过滤器 | 不处理（生产事故） |
| **timeout 30s 对大页面不足**（P1-5） | 默认改 60s（与 TEI 60s 对称）；env 可 override | 保持 30s（大页面失败率高） |
| **payload_hash 跨用户幂等误判**（P1-6） | hash 拼接 `user_id`；DB UNIQUE 约束仍生效 | hash 只含 url + auth_type（用户 B 拿用户 A 的 job） |
| **SSRF 错误消息未标注**（P1-7） | `error = f"SSRF: {e}"`；DoD 验证 `"SSRF" in job.error` | 通用错误（运营无法分类） |
| **INGEST_USER_AGENT 未列 .env**（P1-8） | `.env.example` 追加 `INGEST_USER_AGENT=rag-v1-ingest/0.1` | 不显式列（用户不知可改） |
| **Union[...] 而非 discriminated union**（P1-9） | 手动 dispatch 已功能正确；REFACTOR 段注 Pydantic discriminated union 替代方案 | 不动（功能 OK 但不优雅） |
| **Literal 字符串散落**（P1-10） | 抽 `AuthType` StrEnum 集中定义；M6 复用同一枚举 | 散落 Literal（M6 复制魔数） |
| **TrafilaturaWebReader 内部重抓** | 改成"我们 fetch → 写临时文件 → reader 读 file://" | 让 reader 自己抓（会丢 auth / 重试 / SSRF 控制） |
| **DNS rebinding**：首次解析返公网 IP，httpx 实际连接时返 127.0.0.1 | V1 接受这个窗口（解析时校验一次）；V1.1 加"连接后再次 getpeername 校验" | 引入 `dnspython` 做 pin——过度工程 |
| **5xx 退避时长**：1s/2s/4s 单 job 最高 7s 等 | `retry_max_attempts=3` 配 exponential；ingest_jobs 表 `started_at` 反映真实耗时 | 改 5 次重试（10s+ 阻塞 worker） |
| **抓取被防火墙拦截 / IP 黑名单** | ingest_jobs.status=failed + error 字段填 `httpx.ConnectError`；运营侧看 failed job 列表；不自动重试（避免雪崩） | 加代理池（V1.1） |
| **目标站 JS 渲染**（V1 不支持） | 任务说明 + spec §多模态 V1：图片元数据保留，不做 JS 渲染；如需 Playwright 后端 → V1.1 单独 M 评估 | V1 加 Playwright（增加镜像 ~500MB + 资源开销） |
| **OAuth 流程 URL**（V1 不支持） | spec 决策 #15 明确 4 种模式，OAuth 不在内；如需 → M6 之后单独 M | V1 加 OAuth 流程（state 管理 + 回调 + refresh token，超 V1 scope） |
| **重复 chunk 索引**（同一页面多次 ingest） | 沿用 payload_hash 幂等：同 url+auth_type+user_id 不重复建 job；同 url 不同 user_id 建不同 job（P1-6） | 改用 chunk 内容 hash（成本高、不解决"auth 改了重抓"语义） |
| **fetch_url 返回 HTML 含恶意 `<script>`** | trafilatura 默认剥离脚本（main content extraction 行为）；M5 不做额外 XSS 防护（输入是 trusted internal URL） | v0.4 spec §3.1 没要求；M5 加 BeautifulSoup sanitize 是过度工程 |
| **X-1 config.py 拆分**（review X-1 警告） | M5 暂只在 `app/config.py` 追加 `IngestSettings`（1 个新块 4 字段，不破坏现有 8 块）；M5 REFACTOR 不动；下轮 M0/M1 实际改代码时统一拆 | M5 顺便拆 configs/——超出 3 天估时 |
| **P0-5 集成测试用 sqlite**（review 警告） | M5 集成测试**强制 testcontainers 真 PG**；pyproject `dev` 依赖加 `testcontainers[postgresql]>=4.8` | 用 sqlite 测（假绿） |
| **IPv4-mapped IPv6 绕过 SSRF**（P2-1） | `assert_safe_url` 检测前先转 `ip.ipv4_mapped`；新增 `test_rejects_ipv4_mapped_ipv6` | 不转（`::ffff:10.0.0.1` 漏放） |
| **tenacity 4xx 也重试**（P2-2） | `retry_if_exception_type` 只含 `RetryableHTTPError` / `TimeoutException` / `ConnectError`，不含 `httpx.HTTPStatusError` | 含 `HTTPStatusError`（4xx 费 3 次重试） |
| **估时偏紧**（P2-3） | 估时改 4-5d；Tasks 段分粒度标 | 3d（实际不够） |
| **pyproject 依赖片段不完整**（P2-4） | 给完整 toml 片段含 dev 依赖 | 只写追加行（新人不知格式） |
| **llama-index-readers-web 版本过宽**（P2-5） | `>=0.3,<0.4` 收紧 | `>=0.3,<1`（意外 0.4 break 升级） |
| **集成测试缺 asyncio mark**（P2-6） | 测试 file 头部 `pytestmark = pytest.mark.asyncio`；pytest.ini 兜底 `asyncio_mode = auto` | 依赖默认（async 测试不执行） |
| P0-1 已修：SSRFRedirectTransport + resp.history | r1 双重校验已加 | 「仅初始 URL 校验」——r0 漏洞：302→127.0.0.1 绕过 |
| P0-2 已修：ingest_url try/except 包裹三阶段 | r1 全阶段 catch 已加 | 「只 catch fetch_url」——r0 漏洞：parse/pipeline 失败残留 pending |
| P1-1~10 已修：parse 失败/URL 格式/长度/auth 安全/timeout60s/payload_hash含user_id/SSRF前缀/UA/Pydantic discriminated/AuthType enum | r1 逐项落地（详见修订记录 L929-944） | r0 漏洞：trafilatura 异常残留 / 格式错混用 SSRF 错 / URL 无长度限制 / SecretStr 散落 / timeout 30s 不足 / payload_hash 不含 user_id 跨用户误判 / SSRF 错无前缀 / UA 未显式列 / 手动 dispatch 不优雅 / 字符串魔数散落 |
| P2-1~6 已修：IPv4-mapped转换/4xx不重试/估时4-5d/toml完整/版本<0.4/pytestmark asyncio | r1 逐项落地（详见修订记录 L929-944） | r0 漏洞：`::ffff:10.0.0.1` 漏放 / 4xx 费 3 次重试 / 3d 估时偏紧 / toml 片段不完整 / 版本过宽意外 break / async 测试不执行 |
| **r2 NP-1 已修（r2-2026-06-12）：`URLFormatError` 与 `UnsafeURLError` 入口显式分 catch** | ingest_url 入口先 except URLFormatError（格式错不写 job，HTTP 4xx 直接返）再 except UnsafeURLError（SSRF 错写 job+`SSRF:` 前缀） | 「统一 except ValueError」——r1 漏洞：两个异常都是 ValueError 子类，调用方仍需 isinstance 区分 |
| **r2 NP-2 已修（r2-2026-06-12）：4 auth 模式 Pydantic `extra="forbid"` 互斥** | AuthConfig 父类 `model_config = ConfigDict(extra="forbid")`，4 子类继承；新增 `test_auth_modes_mutually_exclusive` 4 断言 | 「Pydantic 默认 extra="ignore"」——r1 漏洞：bearer + 偷塞 username/password 被静默接受，运维审计无法定位 |
| **r2 NP-3 已修（r2-2026-06-12）：`SSRFRedirectTransport` 语义 DoD 显式标注** | DoD 追加 2 条边界：仅适用 httpx 客户端（M6 aiohttp 需自实现）+ 不重新做 DNS 解析 | 「DoD 只写外层行为」——r1 漏洞：M6 复用时易踩 aiohttp transport 不适用坑 |
| **r2 NP-4 已修（r2-2026-06-12）：本表 r1 行「曾被否决的替代方案」列填实际 r0 漏洞描述** | 4 行 r1 cosmetic 全部填实际方案 + r0 漏洞对比 | 「写 r1-2026-06-11 字符串」——r1 cosmetic bug：列内容无意义（与 M4 r2 报告同模式） |
| **r2 NP-5 已修（r2-2026-06-12）：M5 异常类 3 个收口到 `app/ingest/exceptions.py`** | `UnsafeURLError` / `URLFormatError` / `RetryableHTTPError` 从 ssrf.py / url.py 移到 exceptions.py（M4 r1 P1-6 已建）；ssrf.py / url.py 仅 import；Files 表 + DoD 同步 | 「异常类分散在 2 个文件」——r1 漏洞：M6 复用时需从 2 个不同模块 import（M6 r2 NP-A 揭示的源头） |

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M5-plan-r0 | 2026-06-11 | 初稿（基线 V1 Scope §3.1 / 决策 #4 / #15） |
| r1-2026-06-11 | 2026-06-11 | P0-1 已修：SSRFRedirectTransport + resp.history 双重校验 |
| r1-2026-06-11 | 2026-06-11 | P0-2 已修：ingest_url try/except 包裹 fetch+parse+pipeline |
| r1-2026-06-11 | 2026-06-11 | P1-1 已修：parse_url_to_documents 三类失败检测 |
| r1-2026-06-11 | 2026-06-11 | P1-2 已修：validate_url_format + URLFormatError |
| r1-2026-06-11 | 2026-06-11 | P1-3 已修：MAX_URL_LENGTH=2048 |
| r1-2026-06-11 | 2026-06-11 | P1-4 已修：to_httpx_kwargs docstring + .env.example auth 注释 |
| r1-2026-06-11 | 2026-06-11 | P1-5 已修：url_timeout 默认 30→60 |
| r1-2026-06-11 | 2026-06-11 | P1-6 已修：payload_hash 含 user_id |
| r1-2026-06-11 | 2026-06-11 | P1-7 已修：DoD 追加 "SSRF:" 前缀验证 |
| r1-2026-06-11 | 2026-06-11 | P1-8 已修：.env.example 加 INGEST_USER_AGENT |
| r1-2026-06-11 | 2026-06-11 | P1-9 已修：REFACTOR 段注 discriminated union 替代方案 |
| r1-2026-06-11 | 2026-06-11 | P1-10 已修：抽 AuthType StrEnum |
| r1-2026-06-11 | 2026-06-11 | P2-1 已修：IPv4-mapped IPv6 转 IPv4 |
| r1-2026-06-11 | 2026-06-11 | P2-2 已修：tenacity retry 排除 HTTPStatusError |
| r1-2026-06-11 | 2026-06-11 | P2-3 已修：估时 3d→4-5d + Tasks 粒度 |
| r1-2026-06-11 | 2026-06-11 | P2-4 已修：pyproject.toml 完整 toml 片段 |
| r1-2026-06-11 | 2026-06-11 | P2-5 已修：llama-index-readers-web 版本收紧 <0.4 |
| r1-2026-06-11 | 2026-06-11 | P2-6 已修：pytestmark = pytest.mark.asyncio |
| r2-2026-06-12 | 2026-06-12 | NP-1 已修 · `ingest_url` 入口显式分 catch `URLFormatError`（格式错不写 job，HTTP 4xx 直返）与 `UnsafeURLError`（SSRF 错写 job+`SSRF:` 前缀）；新增 `test_ingest_url_urlformat_vs_ssrf_distinguished`；DoD 追加 r2 NP-1 行 |
| r2-2026-06-12 | 2026-06-12 | NP-2 已修 · 4 auth 模式 Pydantic `extra="forbid"` 互斥：`AuthConfig` 父类加 `model_config = ConfigDict(extra="forbid")`，4 子类继承；新增 `test_auth_modes_mutually_exclusive` 4 断言（BearerAuth+username/password / BasicAuth+token / CookieAuth+token / HeaderAuth+username/password）；DoD 追加 r2 NP-2 行 |
| r2-2026-06-12 | 2026-06-12 | NP-3 已修 · `SSRFRedirectTransport` 语义 DoD 显式标注 2 条边界：(1) 仅适用 httpx 客户端，M6 若用 aiohttp 需自实现等价 transport；(2) transport.handle_async_request 阶段不重新做 DNS 解析——IP literal 立即黑名单命中，域名依赖初始 assert_safe_url 已做 DNS 校验 |
| r2-2026-06-12 | 2026-06-12 | NP-4 已修 · 风险表 4 行 r1 cosmetic 全部填实际 r0 漏洞描述（「仅初始 URL 校验」/「只 catch fetch_url」/r0 漏洞列项 + r1 逐项落地指向修订记录 L929-944 等），不再写 `r1-2026-06-11` 无意义字符串；与 M4 r2 报告 cosmetic bug 同模式 |
| r2-2026-06-12 | 2026-06-12 | NP-5 已修 · M5 异常类 3 个收口到 `app/ingest/exceptions.py`（M4 r1 P1-6 已建，M5 复用不新建）：`UnsafeURLError` / `URLFormatError` 从 `ssrf.py` 移出，`RetryableHTTPError` 从 `url.py` 移出；ssrf.py / url.py 仅 import；Files 表新增 `exceptions.py` 行 + DoD 追加 r2 NP-5 行；M6 复用统一从 `app.ingest.exceptions` 入口 import，消化 M6 r2 NP-A 揭示的「异常类未对齐」源头 |
