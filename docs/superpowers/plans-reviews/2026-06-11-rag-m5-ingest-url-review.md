# M5 Plan Review · Ingest URL 源（4 种 Auth 模式）

> 评审对象：`2026-06-11-rag-m5-ingest-url.md`（681 行，v0 初稿 2026-06-11）
> 评审基线：V1 Scope v0.4 spec（§0 决策 #4/#15 · §3.1 Ingest 数据流 url 段 · §5 错误矩阵 11 条 · §8.2 Embedding & 文档解析栈 7 包）;
> 已有 review 总报告 `2026-06-11-rag-plans-review.md` P0-1/P0-5/P1-5;
> M0/M1/M2/M3/M4 独立 review 报告（reviews/ 目录 5 份）;
> M3 review P0-3 TEIEmbedder dim 硬断言
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M5 plan 是 V1 ingest URL source 的完整实现方案，**11 段模板走齐**（Goal / Architecture / Tech Stack / Files / Tasks RED-GREEN / 测试 / DoD / 依赖 / 风险 / 修订记录），**主动吸收了**跨 M review 的关键 P0/P1（P0-1 端口 18080 / P0-5 真 PG / P1-5 payload_hash UNIQUE），**SSRF 白名单设计远超常见标准**（9 个私有网段 + DNS 解析后校验 + scheme 限制 + IPv6 loopback / ULA / link-local），**4 种 auth 模式实现完整**（Bearer / Basic / Cookie / Header，含 Pydantic SecretStr 加密存储 + to_httpx_kwargs 适配器），**TrafilaturaWebReader 集成走临时文件避免重复抓取**，是已审查 5 份 M plan 中**技术深度最深的一份**。

但作为 V1 首个带外部 HTTP 调用的 source 实现，**安全与工程化仍有显著缺口**：

| 维度 | 评分 | 说明 |
|------|------|------|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐；Goal/不包含（含 M5 vs 其他 M 的契约边界表）/ Architecture（仓库布局 + 数据流 + 模块树 ）/ Tech Stack（版本精确到 <1 级）/ Files / Tasks 9 个 + DoD 20 条 + 风险 11 行——它是已审查 5 份 M plan 中**最完整的一份** |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 9 个 Task 全 RED-GREEN；RED 测试名具体、GREEN 代码段完整（非伪代码）；`RetryableHTTPError` 自定义异常解决了 tenacity 4xx/5xx 选择性重试难题 |
| 技术深度 | ⭐⭐⭐⭐⭐ | SSRF 白名单 9 网段 + DNS 解析 + scheme 限制；auth 模式 4 种含 SecretStr + 适配器；重试/退避/超时/重定向全部实现化 |
| 安全就绪度 | ⭐⭐⭐ | SSRF 白名单完整但**缺 redirect 后二次校验**（P0-1）；URL 长度无限制（P1-3）；auth 配置明文传输（P1-4） |
| 错误处理 | ⭐⭐⭐ | spec §5 错误矩阵 M5 范围 5 条覆盖 3 条（SSRF / HTTP 4xx / 5xx），**缺 Trafilatura 解析失败**（P1-1）、**缺 pipeline 失败后 ingest_jobs 状态残留 pending**（P0-2）、**缺 URL 格式校验**（P1-2） |
| 跨 M 契约 | ⭐⭐⭐⭐ | 边界表完整（M4 pipeline / M7 OpenSearch upsert / M8 / M6 auth.py 复用）；依赖表清晰注明 M7 强依赖+测试 mock 降级策略 |
| SSRF 深度（对比标准） | ⭐⭐⭐⭐ | 远超常见实现但缺 redirect 二次校验——这恰是真实攻击路径 |

**一句话**：M5 plan 是当前 RAG V1 路线**技术密度最高、SSRF 防护最认真的 plan**，但 SSRF redirect bypass（P0-1）是**真实安全漏洞**，pipeline 失败后状态残留 pending（P0-2）会阻塞重复提交，修完 2 个 P0 + 7 个 P1 后即可动手。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · SSRF redirect bypass：assert_safe_url 只校验初始请求 URL，不校验 redirect 目标

**位置**：Task 5 GREEN 段 `fetch_url` L386-398；Task 4 GREEN 段 `assert_safe_url` L320-338

**问题**：

攻击者构造如下攻击链：
1. 攻击者公网域名 `public-attacker.com` 正常 DNS 解析到公网 IP（`1.2.3.4`）
2. `assert_safe_url("https://public-attacker.com/")` 通过
3. 该域名 HTTP 返回 **302 重定向**到 `http://192.168.1.1/admin`
4. httpx `follow_redirects=True` + `max_redirects=3` 自动跟随 → **直接请求内网地址**
5. `assert_safe_url` **不会再次被调用**——SSRF 防护被绕过

这是**真实攻击路径**（CVE-2024-XXXX 类 SSRF bypass 通过 redirect），V1 上线即存在。

**修改**（方案 A 推荐）：用 httpx 的 `redirect_handler` 或自定义 transport 拦截 redirect：

```python
# app/ingest/sources/url.py（改写 fetch_url）
from app.ingest.ssrf import assert_safe_url

class SSRFRedirectHandler(httpx.BaseTransport):
    """在每个 redirect 目标 URL 上执行 SSRF 校验。"""
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert_safe_url(str(request.url))  # ← 每个 redirect 都校验
        return await self._inner.handle_async_request(request)

async def fetch_url(url: str, auth: AuthConfigUnion) -> httpx.Response:
    assert_safe_url(url)  # 初始校验
    ...
    async with httpx.AsyncClient(
        ...,
        follow_redirects=True,
        max_redirects=settings.ingest.max_redirects,
    ) as client:
        # 挂载 SSRF transport 拦截 redirect
        original_transport = client._transport
        client._transport = SSRFRedirectHandler(original_transport)  # type: ignore
        resp = await client.get(url, **kwargs)
    return resp
```

或方案 B（更轻量）——在 `fetch_url` 后手动检查 `resp.history` 中每个 URL：

```python
async def fetch_url(url: str, auth: AuthConfigUnion) -> httpx.Response:
    assert_safe_url(url)
    ...
    async with httpx.AsyncClient(... follow_redirects=True, ...) as client:
        resp = await client.get(url, **kwargs)
    # 校验所有 redirect 目标
    for r in resp.history:
        assert_safe_url(str(r.url))
    return resp
```

**影响**：Test `test_fetch_url_redirect_follows_max_3` 需追加 `test_fetch_url_redirect_ssrf_checked` （mock 链 302 → 127.0.0.1 → 断言 UnsafeURLError）。

---

### P0-2 · `ingest_url` 中 `run_pipeline` 失败后 ingest_jobs 状态残留 `pending`（不标记 failed）

**位置**：Task 7 GREEN 段 L531-533；L546-556 try/except 只包 `fetch_url`

**问题**：

```python
async def ingest_url(url: str, auth_payload: dict, user_id: UUID) -> UUID:
    ...
    # 实际抓取 + pipeline
    resp = await fetch_url(url, auth)
    docs = parse_url_to_documents(url, resp.text)
    await run_pipeline(docs, user_id=user_id, job_id=job_id)
    return job_id
```

- `fetch_url` 抛异常 → try/except 捕了 → 标记 `status=failed` ✓
- `parse_url_to_documents` 抛异常（Trafilatura 挂 / HTML 畸形）→ **无 catch** → 任务抛异常 → job 状态残留 `pending`
- `run_pipeline` 抛异常（TEI 挂 / OpenSearch 挂）→ **无 catch** → job 残留 `pending`
- 残留 `pending` 的 job：
  - P1-5 幂等逻辑（`ON CONFLICT DO NOTHING`）允许重复提交（因为 payload_hash 冲突会返旧 job_id）→ **旧 job_id 状态永 pending，用户永远看不到 indexed/failed**
  - 若 `payload_hash` + `user_id` 不变重试 → 返旧（pending）job_id → 前端以为任务在跑但实际已挂

**修改**（Task 7 GREEN 段补外层 try/except）：

```python
async def ingest_url(url: str, auth_payload: dict, user_id: UUID) -> UUID:
    auth = load_auth_config(auth_payload)
    payload_hash = hashlib.sha256(f"{url}{auth.auth_type}".encode()).hexdigest()
    job_id = uuid4()
    async with async_session() as session:
        job = IngestJob(
            id=job_id, user_id=user_id, source="url",
            status=JobStatus.pending, payload_hash=payload_hash,
            payload=auth_payload,
        )
        session.add(job)
        try:
            await session.commit()
        except IntegrityError:
            existing = await session.scalar(select(IngestJob).where(IngestJob.payload_hash == payload_hash))
            return existing.id

    try:  # ← 新增外层 try
        resp = await fetch_url(url, auth)
        docs = parse_url_to_documents(url, resp.text)
        await run_pipeline(docs, user_id=user_id, job_id=job_id)
    except Exception as e:  # ← 捕所有 pipeline 级异常
        async with async_session() as session:
            job = await session.get(IngestJob, job_id)
            job.status = JobStatus.failed
            job.error = str(e)[:1000]
            await session.commit()
        raise
    return job_id
```

**影响**：需补 RED 测试 `test_ingest_url_marks_failed_on_parse_error` + `test_ingest_url_marks_failed_on_pipeline_error`；现有 RED 测试 `test_ingest_url_records_failure_on_4xx` / `_on_ssrf` 可维持。

---

## P1 · 重要

### P1-1 · Trafilatura 解析失败没有错误处理路径

**位置**：Task 6 GREEN 段 `parse_url_to_documents` L476-490

**问题**：

- `TrafilaturaWebReader.load_data(urls=[f"file://{tmp_path}"])` 读 HTML 文件时可能失败（HTML 非 UTF-8 编码 / 空文件 / 二进制响应被当 HTML 传）
- 当前实现**没有 try/except**——抛 `UnicodeDecodeError` / `ValueError` 等直接冒泡到 `ingest_url` 的调用方
- 空 HTML（HTTP 200 返回空 body）→ trafilatura 可能返回空 list → pipeline 跑空 → `chunks_count=0` → 用户看到 indexed 但 0 chunk

**修改**（Task 6 GREEN 段补）：

```python
def parse_url_to_documents(url: str, html: str) -> list[Document]:
    if not html.strip():
        raise ValueError(f"Empty HTML content from {url}")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp_path = f.name
    try:
        reader = TrafilaturaWebReader()
        docs = reader.load_data(urls=[f"file://{tmp_path}"])
        if not docs:
            raise ValueError(f"Trafilatura failed to extract any content from {url}")
        for doc in docs:
            doc.metadata["source_url"] = url
        return docs
    except Exception as e:
        raise ValueError(f"Trafilatura parse failed for {url}: {e}") from e
    finally:
        os.unlink(tmp_path)
```

并在 Files 表补测试 `test_parse_empty_html_raises` + `test_parse_non_utf8_raises`。

---

### P1-2 · URL 格式校验只靠 urlparse（缺完整 URL 合法性校验）

**位置**：Task 4 GREEN 段 `assert_safe_url` L320-338；`ingest_url` 入参 `url: str`

**问题**：

- `urlparse("")` → `scheme=''`、`hostname=None` → assert_safe_url 抛 `UnsafeURLError("missing hostname")`——OK 但错误信息不该叫 Unsafe
- `urlparse("ftp://example.com/")` → assert_safe_url 抛 scheme 检查——OK
- `urlparse("http://")` → `hostname=None` → UnsafeURLError
- 但：
  - `urlparse("http://a" * 5000)` → 合法 URL（超长），`assert_safe_url` 不检查长度 → URL 过长可能被目标站拒绝（400 Bad Request）或者被中间件截断
  - `urlparse("http://256.256.256.256/")` → `socket.getaddrinfo("256.256.256.256")` 抛 `gaierror` → 被转成 `UnsafeURLError("DNS resolution failed")`——但这不是安全问题，是用户输错 IP
  - `urlparse("[::1]")`（无 scheme）→ scheme 检查先抛

**修改**：

1. 在 `ingest_url` 入口加独立 URL 格式校验（调用 `assert_safe_url` 前）：

```python
from urllib.parse import urlparse

def validate_url_format(url: str) -> None:
    """URL 格式校验（非安全相关）。"""
    if not url or len(url) > 2048:
        raise ValueError(f"URL must be 1-2048 chars, got {len(url)}")
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"Invalid URL: missing scheme or hostname")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Scheme must be http/https, got {parsed.scheme}")
```

2. `UnsafeURLError` 专用于安全相关拒绝，URL 格式错误用 `ValueError` 而非 Unsafe 误导。

---

### P1-3 · 缺 URL 长度限制（2048+ 字符 URL 可以绕过）

**位置**：`assert_safe_url` 全篇无长度检查

**问题**：

- 浏览器/HTTP 标准建议 URL ≤ 2048 字符（IE ≥ 2083，nginx 默认 `large_client_header_buffers` 4×8k）
- 不检查长度 → 攻击者可传 100KB URL → 触发目标站请求头超长拒绝 / 自身截断 → 抓取失败或隐式截断后指向错误资源
- `payload_hash = sha256(url + auth_type)` → 超长 URL 的 hash 仍然正确——但 URL 本身存在 DB（`ingest_jobs.payload`）爆存储

**修改**：`assert_safe_url` 或 `validate_url_format` 加：

```python
MAX_URL_LENGTH = 2048

if len(url) > MAX_URL_LENGTH:
    raise ValueError(f"URL exceeds max length {MAX_URL_LENGTH} (got {len(url)})")
```

---

### P1-4 · auth 配置明文传输 + .env 存储风险

**位置**：Task 2 GREEN 段 `load_auth_config` L242-248；`.env.example` 未列 auth env vars

**问题**：

- `load_auth_config(payload: dict)` 参数是**明文 dict**——从 API 请求体经过 REST → Pydantic → dict 到 load 函数，token / password 全程明文在内存
- `SecretStr` 只在 Python repr 和 log 时隐藏，但 `to_httpx_kwargs` 中用 `.get_secret_value()` 显式解封——当 trace / 异常栈 / debug log 泄露时 token 明文可见
- `.env.example` 追加了 `INGEST_URL_TIMEOUT` / `INGEST_MAX_REDIRECTS` / `INGEST_RETRY_MAX`，但**没有 auth 相关的 env**_——用户创建 bearer token 或 basic password 时只能写死在代码/环境变量中，无安全存储指导

**修改**：

1. `load_auth_config` 参数签名改 Pydantic model 而非 raw dict（M8 路由负责把 JSON 转 Pydantic schema）
2. `.env.example` 加注释指导：

```env
# Ingest URL auth secrets（生产环境请走 secret manager / vault）
# INGEST_AUTH_BEARER_TOKEN=<your-token>
# INGEST_AUTH_BASIC_USERNAME=<username>
# INGEST_AUTH_BASIC_PASSWORD=<password>
```

3. 风险表加一行：auth secrets 在 log / trace / 异常栈泄露风险 → M12 hardening 阶段加 `secrets.redact()` 过滤器

---

### P1-5 · `INGEST_URL_TIMEOUT=30` 对大型页面/慢速站点不足，建议默认 60s 或配置化

**位置**：Task 1 GREEN 段 `IngestSettings.url_timeout: int = 30`；`.env.example` 写 `INGEST_URL_TIMEOUT=30`

**问题**：

- 30s 超时对于：
  - 含 auth 的站点（auth handshake + page load = 慢速响应）
  - 大型文档页面（HTML 响应 > 10MB 读完整）
  - 通过防火墙/代理的站点（额外延迟 2-5s）
  - 5xx 重试 3 次后总超时 = 30s × 3 = 90s——**足够**，但初次请求 30s 可能就挂
- bge-m3 TEI embed timeout 默认 60s（M3 review P0-4），URL 抓取 30s 与之不对称

**修改**：

```python
# 默认 60s，可被 env override
url_timeout: int = 60
INGEST_URL_TIMEOUT=60
```

---

### P1-6 · `payload_hash` 不含 `user_id`，跨用户同 URL+auth 被识别为幂等

**位置**：Task 7 GREEN 段 L514 `sha256(f"{url}{auth.auth_type}")`；M5 风险表 L670

**问题**：

- plan 风险表已自警\"同 url 不同 auth_type 会建不同 job\"——但**同 url + 同 auth_type + 不同 user_id 不会建不同 job**
- 用户 A ingest `https://example.com`（bearer, token_A）→ job1
- 用户 B ingest `https://example.com`（bearer, token_B）→ payload_hash 相同（hash 只含 url + auth_type，不含 token 值）→ 幂等返 job1 → 用户 B 以为自己 ingest 了但实际是 A 的 job
- 用户 B 的 token_B **不会用于抓取**（幂等返旧 job）

**修改**：payload_hash 加入 `user_id`：

```python
payload_hash = hashlib.sha256(f"{url}{auth.auth_type}{user_id}".encode()).hexdigest()
```

并在 `ingest_jobs` 的 `UNIQUE(payload_hash)` 约束中保留——这确保了跨用户幂等不冲突。

---

### P1-7 · `ingest_url` 对内网 URL 返回 `UnsafeURLError` 但错误消息没标注\"SSRF\"，前端/运营无法区分

**位置**：Task 7 GREEN 段 L559 try/except 捕 `UnsafeURLError` → `job.error = "SSRF: " + str(e)`

**问题**：

当前 plan 错误处理代码写：

```python
except UnsafeURLError:
    async with async_session() as session:
        job = await session.get(IngestJob, job_id)
        job.status = JobStatus.failed
        job.error = f"SSRF: {e}"  # ← 已有
        await session.commit()
    raise
```

这已有 `SSRF:` 前缀——OK。但集成测试 `test_ingest_url_records_failure_on_ssrf` 应断言 `\"SSRF\" in job.error`。补到 DoD。

---

### P1-8 · `.env.example` 没有列出 `INGEST_USER_AGENT`（虽然 config 有 `user_agent`）

**位置**：Files 表 L175 `.env.example` 追加行只写了 3 个变量；`IngestSettings.user_agent: str = "rag-v1-ingest/0.1"` 已有

**问题**：

- `user_agent` 是可配置的（config 有默认值），但 `.env.example` 没显式列出
- 目标站可能白名单特定 UA，用户需要改但不知道有这个配置

**修改**：`.env.example` 加：

```env
INGEST_USER_AGENT=rag-v1-ingest/0.1
```

---

### P1-9 · `auth.py` `AuthConfigUnion` 类型用 `Union[...]` 而不是 discriminated union（Pydantic v2 支持）

**位置**：Task 2 GREEN 段 L239 `AuthConfigUnion = Union[BearerAuth, BasicAuth, CookieAuth, HeaderAuth]`

**问题**：

- Pydantic v2 支持 `typing.Annotated` 做 discriminated union（`tagged_union`），可以在反序列化时自动按 `auth_type` 字段 dispatch
- 当前实现手动在 `load_auth_config` 中用 dict.get + if/elif dispatch——不优雅但**功能正确**
- 不是 P0——功能正确，但应该注在 REFACTOR 段：\"如果用 Pydantic discriminated union 替换手动 dispatch，需 `from typing import Annotated` + `from pydantic import Field` + `Annotated[Union[...], Field(discriminator='auth_type')]`\"

---

### P1-10 · `auth.py`  枚举字符串用 `Literal` 但没集中定义，M6 Confluence 复用时会复制魔数

**位置**：Task 2 GREEN 段 L218 `auth_type: Literal["bearer", "basic", "cookie", "header"]`

**问题**：

- `Literal["bearer", "basic", "cookie", "header"]` 字符串散落在子类 `auth_type: Literal["bearer"] = "bearer"` 中
- M6 复用 `load_auth_config` 不需要这些字符串——但 M6 写 `AuthConfigUnion` 类型别名时也要写一遍
- REFACTOR 应抽 `AuthType` enum：

```python
from enum import StrEnum

class AuthType(StrEnum):
    BEARER = "bearer"
    BASIC = "basic"
    COOKIE = "cookie"
    HEADER = "header"
```

---

## P2 · 优化

### P2-1 · SSRF 白名单没覆盖 IPv4-mapped IPv6 地址（`::ffff:10.0.0.1`）

**位置**：Task 4 GREEN 段 `_PRIVATE_NETS` L308-318

**问题**：

- `::ffff:10.0.0.1` 是 IPv4-mapped IPv6 地址，实际指向 10.0.0.1
- `ipaddress.ip_address("::ffff:10.0.0.1")` 返回的是 IPv6Address 类型，**不属于** `ipaddress.ip_network("10.0.0.0/8")`（IPv4Network）
- `socket.getaddrinfo` 可能返回 `('::ffff:10.0.0.1', 0, 0, 0, ...)` 格式的 IPv6 地址
- 当前代码 `for ip in ... for net in _PRIVATE_NETS: if ip in net`——IPv6 地址 vs IPv4 网络：`in` 操作返回 `False`，**漏放**

**修改**（Task 4 GREEN 段补转换）：

```python
for info in infos:
    raw = info[4][0]
    ip = ipaddress.ip_address(raw)
    # 如果 IPv4-mapped IPv6，转回 IPv4 再对比
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    for net in _PRIVATE_NETS:
        if ip in net:
            raise UnsafeURLError(f"private/loopback IP rejected: {raw} in {net}")
```

---

### P2-2 · `tenacity` 重试策略中 `httpx.HTTPStatusError` 对所有 4xx/5xx 都触发重试，但 4xx 被自定义 `RetryableHTTPError` 区分——这层抽象在 GREEN 段不清晰

**位置**：Task 5 GREEN 段 L412-418 装饰器 + L427-434

**问题**：

```python
@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)),
    ...
)
async def fetch_url_with_retry(...): ...
```

- tenacity 的 `retry_if_exception_type` 参数含 `httpx.HTTPStatusError`——意味着**任何** HTTPStatusError（含 4xx）都会触发重试
- 但实际逻辑：4xx 通过 `retryable_http_status_error` 抛**不是** `RetryableHTTPError`？不对——代码里是 `_maybe_raise_retryable`，5xx 抛 `RetryableHTTPError`，4xx 走 `resp.raise_for_status()` 抛标准 `httpx.HTTPStatusError`
- 因为 `retry_if_exception_type` 包括 `httpx.HTTPStatusError`——4xx 的 `httpx.HTTPStatusError` 也会触发重试！**4xx 费 3 次重试才 reraise**

**修改**：

```python
@retry(
    retry=retry_if_exception_type((RetryableHTTPError, httpx.TimeoutException, httpx.ConnectError)),
    # 不包含 httpx.HTTPStatusError——4xx 不会触发重试
    ...
)
```

---

### P2-3 · 9 个 Task 标 2-5 分钟粒度，但 Task 5（fetch_url 含重试 + 重定向 + 超时 + 4xx/5xx 区分）实际 20-25 分钟

**位置**：Tasks 段 L190 标题\"（2-5 分钟/step 粒度）\"；Task 5 L373-447

**问题**：

- Task 5 含 5 个 RED 测试 + 2 个 GREEN 段 + 1 个自定义异常类——**实际 20-25 分钟**
- M4 review P1-2 已指出 M4 同类问题
- 3 个工作日估时也偏紧——M5 有 9 个 Task 含集成测试，SSRF 白名单 + auth 4 模式 + fetch 重试 + trafilatura 集成，**实际至少 4-5 个工作日**

**修改**：估时从 3d 改 4-5d；Tasks 段标题改\"（Task 1-3: 5-10min；Task 4-5: 20-30min；Task 6-9: 10-15min）\"。

---

### P2-4 · `pyproject.toml` 依赖追加没给完整 toml 片段

**位置**：Files \"修改\" 段 L178

**问题**：只写\"追加 `trafilatura>=1.12,<2` / `llama-index-readers-web>=0.3,<1`\"，没给完整 `[project.dependencies]` 片段。新人不知道是加在最前/最后/逗号分割方式。

**修改**：给完整片段：

```toml
dependencies = [
  # ... M3 已装 ...
  "trafilatura>=1.12,<2",
  "llama-index-readers-web>=0.3,<1",
]
```

---

### P2-5 · `llama-index-readers-web` 依赖版本区间 `<1` 但该包目前主版本是 0.x——`>=0.3,<1` 实际上等价于 `>=0.3,<0.4`（如果 0.x 只有 0.3.x）

**位置**：Tech Stack L124

**问题**：`llama-index-readers-web` 的版本策略：如果将来出 `0.4.0` 有 break change，`<1` 会允许自动升级。应改成 `<0.4` 或 `==0.3.x`。但这是优化，不是 P0。

---

### P2-6 · 集成测试 `test_m5_ingest_url.py` 缺 `@pytest.mark.asyncio` 标记和 pytest-asyncio mode 声明

**位置**：测试策略 L614-619

**问题**：

- plan 写 `pytest tests/integration/test_m5_ingest_url.py`——假设 pytest-asyncio 已配 `asyncio_mode = auto`
- 但 M0 review P2-1 已建议加 `pytest.ini` ——若没设 `asyncio_mode = auto`，async 测试函数不执行
- 应明确在 test file 头部写 `pytestmark = pytest.mark.asyncio` 或显式依赖 `pytest.ini`

---

## 交叉验证表

### 已有 review P0 验证（总报告 `2026-06-11-rag-plans-review.md` + M0/M1/M2/M3/M4 独立 review）

| 编号 | 议题 | M5 状态 | 验证 |
|------|------|---------|------|
| P0-1 | TEI 端口 18080 | ✅ **已吸收** | 依赖表 L649 写\"TEI 18080\"; 避雷行 L9 主动标\"P0-1（端口 18080）\" |
| P0-5 | 真 PG（不用 sqlite） | ✅ **已吸收** | 测试策略 L618 \"真 PG 强制（P0-5 避雷）\"; 集成测试用 testcontainers |
| P1-5 | payload_hash UNIQUE | ✅ **已吸收** | Task 7 代码段显式注 \"P1-5 幂等：UNIQUE(payload_hash) + ON CONFLICT DO NOTHING\" |
| M3 review P0-3 | TEIEmbedder dim 硬断言 | ⚠️ **间接依赖** | M5 通过 M4 pipeline 调 TEIEmbedder，M5 plan 自身不直接调 TEI；应注\"依赖 M3/M4 的 dim 硬断言\" |

### M4 review 交叉引用

| M4 问题 | M5 影响 | 检查 |
|---------|---------|------|
| P0-1 元素分类 | **M5 URL source 没有元素分类**——trafilatura 提取纯文本，没有 Table / Image 分类。这是 M5 自身的设计选择（spec §3.1 只要求 trafilatura extract，不要求元素分类），但 M5 应明确说明\"TrafilaturaWebReader 默认只返回 NarrativeText，暂不做 Table 分类\" | ⚠️ 已说明但不够显式 |
| P0-3 OpenSearch 写入层 | M5 调用 M7 `upsert_chunks`——如果 M7 没实现 mapping、refresh、bulk 策略，M5 集成测试 mock 后等到 M7 才爆雷。M5 风险表 L655 已自警\"M7 强依赖\" | ✅ 已列出 |
| P1-5 状态机 | M5 `ingest_url` 返回后 job 状态：fetch_url 失败→failed；pipeline 成功→indexed（M4 负责）；pipeline 失败→**P0-2 残留 pending** | ❌ P0-2 |

---

## 新问题汇总

| # | 类别 | 问题 | 严重度 |
|---|------|------|--------|
| 1 | 安全 | **SSRF redirect bypass**（P0-1）——assert_safe_url 不校验 redirect 目标 | P0 |
| 2 | 错误处理 | **pipeline 失败后 job 状态残留 pending**（P0-2）——parse / pipeline 抛异常无 catch | P0 |
| 3 | 错误处理 | **Trafilatura 解析失败无 catch**（P1-1）——空 HTML / 编码错 / 返回空 list | P1 |
| 4 | 格式校验 | **缺 URL 长度限制 + 格式校验**（P1-2/P1-3） | P1 |
| 5 | 安全 | **auth 配置明文传输 + 无存储指导**（P1-4） | P1 |
| 6 | 配置 | **timeout 默认 30s 对大页面不足**（P1-5） | P1 |
| 7 | 幂等 | **payload_hash 不含 user_id，跨用户同 URL 幂等（P1-6）** | P1 |
| 8 | 安全 | **IPv4-mapped IPv6 绕过 SSRF 白名单**（P2-1） | P2 |
| 9 | 重试 | **tenacity 重试条件错：4xx 也触发 retry**（P2-2） | P2 |
| 10 | 估时 | **9 个 Task 估时偏紧，实际 4-5d**（P2-3） | P2 |
| 11 | 依赖 | **`llama-index-readers-web` 版本区间过宽**（P2-5） | P2 |
| 12 | 测试 | **集成测试缺 `pytest.mark.asyncio`**（P2-6） | P2 |

---

## 落地建议

1. **动手先修 2 个 P0**：
   - P0-1（SSRF redirect bypass）是**安全修复，必须动手前改**——只需要在 `fetch_url` 后加 `resp.history` 校验或 transport hook 即可，改动量约 10 行
   - P0-2（pipeline 失败状态残留）是**数据完整性修复**——`ingest_url` 外层 try/except 包裹 parse + pipeline，～15 行

2. **P1 中优先修 P1-2/P1-3（URL 长度+格式校验）+ P1-6（payload_hash 含 user_id）**——两者改动极小（共 10 行），但对生产可用性影响大

3. **P1-4（auth 配置安全）留到 M8 路由实现时一起解决**——M5 代码层面用 `SecretStr` 已做到最小暴露，REST 传输安全由 M8 HTTPS + 请求体序列化负责

4. **集成测试中 SSRF redirect bypass 测试必须加**——mock 一个域名返回 302 → 127.0.0.1，验证 `UnsafeURLError` 被抛出

5. **与 M4/M7 的契约**：M5 集成测试 mock OpenSearch（M5 风险表 L655 已说明），但**M7 合入后必须跑全部 M5 集成测试**验证 `upsert_chunks` 真实接口

6. **与 M6 的复用契约**：M6 应直接 import `app/ingest/auth.py` 的 `load_auth_config` + `to_httpx_kwargs` + `AuthConfigUnion`，M5 Files 表的文件结构已经预留（`app/ingest/auth.py` 在 M5 增量中列在 `confluence.py` 注释前）

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M5-review-r0 | 2026-06-11 | 初稿（独立审查 M5 ingest-url plan，附 2×P0 + 7×P1 + 6×P2 + 交叉验证表） |
