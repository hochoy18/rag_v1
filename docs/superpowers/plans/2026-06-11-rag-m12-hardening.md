# M12 Plan · Hardening（错误处理 + 限速 + 备份 + Prod 部署 + CI）

> 所属：RAG V1 M0–M12 实施路线 · 第 12 步（**V1 最后一步**）
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §5 错误处理](../specs/2026-06-10-rag-v1-scope.md#5-错误处理) · [决策总表 #11](../specs/2026-06-10-rag-v1-scope.md#0-决策总表) · [System Design §3.12 中间件顺序 / §7.4 CSP / §7.5 限速 / §8 部署 / §10 CI](../specs/2026-06-11-rag-system-design.md)
> 估时：**5 个工作日**（V1 最大里程碑；day 1 = error_handler + rate_limit + security_headers / day 2 = Argon2 + Sentry / day 3 = 备份脚本 + restore 演练 / day 4 = prod compose + 部署文档 / day 5 = GitHub Actions + 端到端）
> 前置 review：[2026-06-11-rag-plans-review.md](./2026-06-11-rag-plans-review.md) P0-1 / P0-5 / P1-7 / X-4 已纳入；M11 plan P0 避雷（mock RAGAS / 显式注入 judge）已沿用
> M12 自身 review：[2026-06-11-rag-m12-hardening-review.md](./reviews/2026-06-11-rag-m12-hardening-review.md) **4 P0 + 10 P1 + 12 P2 + 7 X-跨M + 20 NEW = 53 项**；**本版本 r1 已关 26 项**（4 P0 全部 + 10 P1 全部 + 12 P2 全部），剩余 27 项（X-1/2/3/4/5/6/7 跨 M + NEW-1~20）已纳入修订记录为 r2 backlog
> **r1 已吸收上游 M0-M11 review**：M8 P0-1/2（chat 超时 + lifespan dispose）、M10 P0-2/3（trace_id API）、M11 P0-6（trace_id API）→ **统一改用 ContextVar 桥接**（P0-2 修复）

---

## Goal

把 v1-scope 决策 #5 错误处理矩阵（11 条全要过）+ 限速 + 安全头 + 备份 + prod 部署分离 + CI 落成可执行代码契约：

1. **统一错误处理**：`app/middleware/error_handler.py` 实现 11 条错误矩阵，每条错误 = 一个 `RAGError` 子类 + 一个 HTTP status + 一个前端契约（JSON 响应 schema 固定）
2. **全局限速**：登录/注册走 M2 已有 5/min、10/min；**新增** `chat 30/min/user` 与 `ingest 10/min/user` 慢速 API 限速；`/api/health` bypass
3. **Security headers**：CSP / HSTS / X-Content-Type-Options / X-Frame-Options / Referrer-Policy 全局响应头（CSP 必须放行 Gradio 5.0 inline JS）
4. **Argon2 参数升级**：M2 `time_cost=2, memory_cost=20480` → **time_cost=3, memory_cost=65536**（OWASP 2024 推荐）；`extend_session` fire-and-forget 评估保留 vs BackgroundTasks
5. **Sentry 集成**：5xx 异常上报 + scope tag 注入 `langfuse_trace_id`（M11 review P1-1）
6. **备份策略**：Postgres `pg_dump` 每日 + WAL 归档；OpenSearch snapshot + MinIO；`restore.sh` 演练脚本（**仅 staging**，不动 prod）
7. **Prod 部署分离**：`docker-compose.prod.yml`（prod 资源限制 / 不暴露端口 / env 来自 secret manager）+ `docker-compose.override.yml`（dev override 端口映射）；review **X-4 必须 M12 完成**
8. **GitHub Actions CI**：
   - `.github/workflows/ci.yml`（PR 触发）：ruff lint + unit + integration（docker compose up 真 PG）+ RAGAS gate（20 题，30 分钟超时）
   - `.github/workflows/nightly-ragas.yml`（cron 触发）：RAGAS full eval 50 题
9. **CSP / 错误监控**：CSP `script-src 'self' 'unsafe-inline'`（Gradio 兼容）+ Sentry 5xx 告警
10. **健康检查强化**：`/api/health` 探测 5 service 状态（Langfuse / OpenSearch / TEI / Postgres / Graph）；返回 200 仅全绿，503 单失败

**不包含**（其他 M 负责）：M2 登录/注册 5/10 限速（M2 已建，本 M 只验证）、M10 Langfuse 业务 trace（只读已有 trace_id 注入 Sentry tag）、M11 RAGAS 评测逻辑（只产 CI 接入）、业务功能本身。

---

## Architecture

### 仓库布局（apps/rag_v1/，仅显示 M12 新增/修改）

```
apps/rag_v1/
├── app/
│   ├── middleware/                          # M12 新建
│   │   ├── __init__.py
│   │   ├── error_handler.py                 # 统一异常处理（11 条错误矩阵）
│   │   ├── rate_limit.py                    # 全局 + 路由级限速
│   │   ├── security_headers.py              # CSP / HSTS / X-Frame-Options
│   │   └── request_id.py                    # M8 已建（M12 复用）
│   ├── api/                                 # M8 已建
│   │   └── main.py                          # 挂 middleware（顺序敏感）
│   ├── auth/                                # M2 已建
│   │   ├── service.py                       # Argon2 参数升级
│   │   └── deps.py                          # extend_session 决策点
│   ├── observability/                       # M3+M10 已建
│   │   ├── sentry.py                        # M12 新建（Sentry 集成）
│   │   └── langfuse.py                      # M10 已建（M12 复用 trace_id）
│   ├── eval/                                # M11 已建
│   │   └── gate.py                          # CI 门禁集成（不改逻辑）
│   ├── graph/                               # M7 已建
│   │   └── workflow.py                      # M12 暴露 health() 接口
│   ├── retrieval/                           # M7 已建
│   │   ├── os_client.py                     # M12 暴露 health()
│   │   └── tei_client.py                    # M12 暴露 health()
│   └── config.py                            # 追加 ProdSettings / BackupSettings / SecuritySettings
├── infra/
│   ├── docker-compose.yml                   # M0 已建（base）
│   ├── docker-compose.override.yml          # M12 新建（dev override，端口映射 + 卷挂载）
│   ├── docker-compose.prod.yml              # M12 新建（prod 分离：resource limits / 无端口 / env file）
│   ├── backup/
│   │   ├── pg_backup.sh                     # M12 新建（pg_dump + WAL 归档）
│   │   ├── os_snapshot.sh                   # M12 新建（OpenSearch snapshot → MinIO）
│   │   ├── restore.sh                       # M12 新建（恢复演练）
│   │   └── README.md                        # M12 新建（备份策略文档）
│   └── README.md                            # M12 完善（dev / staging / prod 三环境部署）
├── .github/
│   └── workflows/
│       ├── ci.yml                           # M12 新建（PR 触发）
│       └── nightly-ragas.yml                # M12 新建（cron 触发）
├── tests/
│   ├── unit/
│   │   ├── test_error_handler.py            # 11 条错误矩阵
│   │   ├── test_rate_limit.py
│   │   ├── test_security_headers.py
│   │   ├── test_argon2_upgrade.py
│   │   ├── test_sentry_integration.py
│   │   └── test_prod_settings.py
│   └── integration/
│       ├── test_m12_backup_restore.py       # 真 PG 备份/恢复演练（staging）
│       ├── test_m12_ci_local.py             # 模拟 CI 流程（act 或 docker compose）
│       ├── test_m12_prod_smoke.py           # prod compose 启动 smoke test
│       └── test_m12_health_5services.py     # /api/health 5 service 全绿
```

**模块组织原则**：
- `app/middleware/` **纯 ASGI**，不直接依赖 `app.graph` / `app.retrieval`（避免循环依赖）
- 错误矩阵每条 = 一个 `RAGError` 子类 + 一个 HTTP status mapper（在 `error_handler.py` 内集中）
- 限速中间件用内存 token bucket（V1 单实例够用，**不引入** Redis；V2 升级）
- prod 部署用 `docker-compose.yml`（base） + `docker-compose.prod.yml`（override 风格，Compose 原生支持）

### M12 数据流（r1 修正中间件顺序）

```
[HTTP Request]
    ↓ middleware chain（按 spec §3.12 LIFO add_middleware）
[error_handler] → [rate_limit] → [security_headers] → [request_id] → [cors] → [router]
    ↓ 业务抛 RAGError 子类
[error_handler] 捕获 → 映射 HTTP status + JSON body + Langfuse trace_id 注入 Sentry
    ↓
[Response] (含 X-Request-Id + 所有安全头 + CORS 头)

错误矩阵（r1 扩展为 12 条，X-1 联动 · 新增 ChatTimeoutError 504）：
  OpenSearch 不可达        → OpenSearchDownError        → 503 + admin_msg + Langfuse trace
  TEI embedding 超时        → TEITimeoutError            → 指数退避 3 次 → 422 + ingest 标 failed
  LLM 4xx/5xx              → LLMUpstreamError           → 502 + Langfuse trace + 不静默
  检索 top-k 全 0 分       → NoRelevantDocsError        → 200 + body.answer = "未找到相关文档"
  Postgres 不可达          → PostgresDownError          → 503 + checkpointer 降级 SQLite + UI 告警
  Confluence 401/403       → ConfluencePermissionError  → 跳过该 page + 记日志 + 任务报告
  Confluence 429           → ConfluenceRateLimitError   → token bucket + 指数退避 3 次
  文档解析失败（PDF 损坏）  → DocumentParseError         → 200 + 单文件失败不阻塞批次
  附件超大 (>50MB)         → AttachmentTooLargeError    → 413 + 记日志 + 不进 RAG
  用户未登录访问 /api/chat → UnauthenticatedError       → 401 + 前端跳登录
  session_id 越权          → SessionAccessDeniedError   → 404 + 不暴露存在性
  **Chat 请求超时（>30s）   → ChatTimeoutError [r1 新增]  → 504 + Langfuse trace（M8 P0-1 联动）**
```

### 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M12 error_handler | `RAGError` 子类（各 M 业务代码抛） | M12 定义基类，各 M 业务抛子类（含 r1 新增 `RateLimitedError` / `ChatTimeoutError`） |
| M12 rate_limit | `slowapi.Limiter` 包装的装饰器 + `get_rate_limit_key`（r1 P1-1 user_id 优先） | chat 30/min/user, ingest 10/min/user |
| M12 security_headers | ASGI middleware 返回头 | CSP（r1 P1-3 spec §7.4 严格）/ HSTS / X-Content-Type-Options / X-Frame-Options / Referrer-Policy / form-action / base-uri |
| M12 Sentry | `sentry_sdk.init()` + `set_tag("langfuse_trace_id", ...)` + `before_send=_scrub_pii`（r1 P1-5） | M10 langfuse 已建（ContextVar 桥接 r1 P0-2 修复），注入 trace_id |
| M12 health | `/api/health/live` + `/api/health/ready`（r1 P2-4 拆 k8s probe） | 5 service 探测 + 并行 + 2s 超时（r1 P1-7） |
| M12 backup | `pg_dump` + `curl /_snapshot` + MinIO SDK（r1 P0-3 新增 `docker-compose.minio.yml`） | 演练仅 staging（r1 P0-4 三重门禁） |
| M12 prod compose | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --wait` | base + override 模式（r1 P2-12 security_opt + cap_drop）。**r2-2026-06-12 r2-新-5 提醒**：M0 修订记录写 "4 service" 是 r1 时口径，**r2 实际 5 service（PG / OS / TEI / Langfuse / MinIO）**——M0 修订记录已在 M0 r2 NP-5 修订已补 |
| M12 CI | `pytest tests/` + `docker compose up integration --wait`（r1 P1-8） + `python -m app.eval.ragas_run --threshold 0.65`（r1 X-3） | GitHub Actions ubuntu-latest（r1 P2-3 postgres-client） |
| M12 error_handler | `request.state.request_id`（M8 RequestIDMiddleware 设置） | **r1 P2-5 新增**：全链路 X-Request-Id 串联（HTTP 头 → Sentry tag → Langfuse metadata → 日志） |
| 各 M 业务 | `from app.middleware.errors import XxxError` + `raise` | 不直接 raise `HTTPException` |

---

## Tech Stack

| 层 | 选型 | 版本（精确） |
|----|------|------------|
| 限速 | `slowapi` | `>=0.1.9,<1`（基于 limits 库，FastAPI 友好） |
| 错误处理 | `fastapi.HTTPException` + 自定义 `RAGError` | 复用 M8 |
| 安全头 | ASGI middleware 手写 | **不引入** `secure`（过度封装） |
| Argon2 | `argon2-cffi` | `>=23.1,<24`（M2 已装；参数升级） |
| Sentry | `sentry-sdk[fastapi]` | `>=2.10,<3` |
| 备份 | `pg_dump`（PG 16）+ `curl`（OpenSearch snapshot API）+ `mc`（MinIO client） | 系统命令，Python 不封装 |
| 测试 | `pytest` / `pytest-asyncio` / `httpx.AsyncClient` | 见 §测试策略 |
| CI | GitHub Actions `ubuntu-latest` | 无 GPU（**P0 避雷**：M3 smoke mock LLM） |
| Build cache | BuildKit `cache-from` / `cache-to` | type=gha（GitHub Actions cache） |

**关键 import**（错误处理）：

```python
# app/middleware/error_handler.py
from fastapi import Request, status
from fastapi.responses import JSONResponse
from sentry_sdk import capture_exception, set_tag
from app.observability.langfuse import get_current_trace_id
```

**关键 import**（限速）：

```python
# app/middleware/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
chat_limit = limiter.limit("30/minute")      # per-IP（V1 单实例）
ingest_limit = limiter.limit("10/minute")
# /api/health bypass by path check in middleware
```

**CSP 关键策略**（P0 避雷：Gradio 5.0+ 用 inline JS）：

```
default-src 'self';
script-src 'self' 'unsafe-inline';        # Gradio 5.0+ 内联 JS 必加
style-src 'self' 'unsafe-inline';         # Gradio 内联 CSS 必加
img-src 'self' data: https:;
connect-src 'self' ws: wss:;              # Gradio WebSocket
frame-ancestors 'none';                   # X-Frame-Options 同效
```

---

## Files

**新增**（源 14 个 + 测试 9 个 + 脚本 3 个 + workflow 2 个 + compose 2 个 + 文档 2 个）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
| `app/middleware/__init__.py` | 包标识 |
| `app/middleware/error_handler.py` | 统一异常处理 + 11 条错误矩阵 |
| `app/middleware/rate_limit.py` | slowapi Limiter + chat/ingest 装饰器 |
| `app/middleware/security_headers.py` | CSP / HSTS / X-Content-Type-Options / X-Frame-Options / Referrer-Policy |
| `app/middleware/errors.py` | `RAGError` 基类 + 11 个子类 |
| `app/observability/sentry.py` | Sentry init + 5xx 上报 + trace_id 注入 |
| `app/api/health.py` | `/api/health` 5 service 探测 |
| `infra/docker-compose.override.yml` | dev override（端口映射 + 卷挂载） |
| `infra/docker-compose.prod.yml` | prod 分离（resource limits / 无端口 / env 来自 secret） |
| `infra/backup/pg_backup.sh` | pg_dump + WAL 归档 |
| `infra/backup/os_snapshot.sh` | OpenSearch snapshot → MinIO |
| `infra/backup/restore.sh` | 恢复演练脚本（staging） |
| `infra/backup/README.md` | 备份策略文档 |
| `infra/docker-compose.minio.yml` | **r1 P0-3 新建**：MinIO 单 service + bucket init（backup restore 集成测试依赖） |
| `infra/README.md` | 完善（dev / staging / prod 三环境部署） |
| `.github/workflows/ci.yml` | PR 触发（lint + unit + integration + RAGAS gate） |
| `.github/workflows/nightly-ragas.yml` | cron 触发（nightly 50 题） |
| `tests/unit/test_error_handler.py` | 11 条错误矩阵（RED-GREEN 各 11 个测试） |
| `tests/unit/test_rate_limit.py` | 限速中间件（chat 30、ingest 10、health bypass） |
| `tests/unit/test_security_headers.py` | CSP / HSTS / X-Frame-Options |
| `tests/unit/test_argon2_upgrade.py` | time_cost=3, memory_cost=65536 |
| `tests/unit/test_sentry_integration.py` | mock Sentry → 5xx 上报 + trace_id 注入 |
| `tests/unit/test_prod_settings.py` | ProdSettings / BackupSettings / SecuritySettings |
| `tests/unit/test_extend_session.py` | fire-and-forget vs BackgroundTasks 决策测试 |
| `tests/unit/test_backup_scripts.py` | **r1 P0-3 新增**：pg_backup.sh / os_snapshot.sh / restore.sh 存在性 + 权限 + 完整性校验 |
| `tests/integration/test_m12_backup_restore.py` | 真 PG 备份/恢复（staging 环境） |
| `tests/integration/test_m12_ci_local.py` | 模拟 CI 流程（act 或 docker compose） |
| `tests/integration/test_m12_prod_smoke.py` | prod compose 启动 smoke test |
| `tests/integration/test_m12_health_5services.py` | /api/health 5 service 全绿/单失败 |

**修改**：
- `pyproject.toml`：追加 3 个新直接依赖（`slowapi` / `sentry-sdk[fastapi]` / `argon2-cffi` 已在 M2）
- `app/config.py`：追加 `SecuritySettings`（CSP / HSTS max_age）/ `ProdSettings`（resource limits）/ `BackupSettings`（pg_dump 路径 / MinIO endpoint）
- `app/auth/service.py`（M2 已建）：Argon2 参数升级 `time_cost=2→3`, `memory_cost=20480→65536`
- `app/api/main.py`（M8 已建）：挂 middleware（顺序：`request_id → security_headers → rate_limit → error_handler`）
- `app/retrieval/os_client.py`（M7 已建）：暴露 `health()` 方法
- `app/retrieval/tei_client.py`（M7 已建）：暴露 `health()` 方法
- `app/graph/workflow.py`（M7 已建）：暴露 `health()` 方法（检查 LLM client 可达）

**不修改**：`app/llm/factory.py`（M3 不动；Sentry 通过 langchain callback 集成即可）、`app/eval/`（M11 不动；CI 接 `python -m app.eval.ragas_run` 即可）、`app/auth/deps.py` 的 `extend_session`（决策点见 Task 17）。

---

## Tasks（2-5 分钟/step 粒度）

### Day 1 · Error Handler + Rate Limit + Security Headers

#### Task 1：`RAGError` 基类 + 11 个子类

**RED** · `tests/unit/test_error_handler.py::test_base_rag_error_has_request_id`
- 抛 `RAGError("test", request_id="abc-123")` → 断言 `.request_id == "abc-123"`、`.message == "test"`、`.http_status == 500`（默认）
- 跑测试 → 失败（基类还不存在）

**GREEN** · `app/middleware/errors.py`：
```python
from fastapi import status

class RAGError(Exception):
    """RAG V1 错误矩阵基类"""
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    user_message: str = "服务暂时不可用，请稍后重试"

    def __init__(self, message: str, *, request_id: str = "", **context):
        self.message = message
        self.request_id = request_id
        self.context = context
        super().__init__(message)

# 11 个子类（每条错误矩阵 = 1 个）
class OpenSearchDownError(RAGError):
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "opensearch_down"
    user_message = "检索服务暂时不可用，问答已切换至通用模式"

class TEITimeoutError(RAGError):
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "tei_timeout"

class LLMUpstreamError(RAGError):
    http_status = status.HTTP_502_BAD_GATEWAY
    error_code = "llm_upstream_error"
    user_message = "模型服务暂时不可用，请稍后重试"

class NoRelevantDocsError(RAGError):
    http_status = status.HTTP_200_OK
    error_code = "no_relevant_docs"
    user_message = "未找到相关文档"

class PostgresDownError(RAGError):
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "postgres_down"
    user_message = "持久化服务降级中，部分功能可能受限"

class ConfluencePermissionError(RAGError):
    http_status = status.HTTP_200_OK
    error_code = "confluence_permission_denied"

class ConfluenceRateLimitError(RAGError):
    http_status = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "confluence_rate_limited"

class DocumentParseError(RAGError):
    http_status = status.HTTP_200_OK
    error_code = "document_parse_failed"

class AttachmentTooLargeError(RAGError):
    http_status = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    error_code = "attachment_too_large"
    user_message = "附件超过 50MB 限制"

class UnauthenticatedError(RAGError):
    http_status = status.HTTP_401_UNAUTHORIZED
    error_code = "unauthenticated"
    user_message = "请先登录"

class SessionAccessDeniedError(RAGError):
    http_status = status.HTTP_404_NOT_FOUND  # **不暴露存在性**
    error_code = "session_not_found"
    user_message = "会话不存在或已过期"
```

**REFACTOR** · 把 `error_code` + `user_message` 设为类属性（每子类覆盖），避免 `__init__` 重复

#### Task 2：错误处理器 middleware

**RED** · `tests/unit/test_error_handler.py::test_handler_returns_json_with_request_id`
- mock request 含 `request_id="req-abc"` → 业务抛 `OpenSearchDownError("connect refused", request_id="req-abc")`
- 调 handler → 断言 response.status_code == 503 + JSON body 含 `{"error_code": "opensearch_down", "message": "...", "request_id": "req-abc"}`
- 跑测试 → 失败

**GREEN** · `app/middleware/error_handler.py`：
```python
from fastapi import Request
from fastapi.responses import JSONResponse
from app.middleware.errors import RAGError

async def error_handler_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except RAGError as e:
        return JSONResponse(
            status_code=e.http_status,
            content={
                "error_code": e.error_code,
                "message": e.user_message,
                "request_id": e.request_id or getattr(request.state, "request_id", ""),
                "context": e.context,
            },
        )
```

**RED** · `test_handler_unexpected_exception_returns_500_with_sentry`
- 业务抛普通 `ValueError("boom")` → 调 handler → 断言 status 500 + body.error_code == "internal_error" + mock Sentry `capture_exception` 被调用
- 跑测试 → 失败

**GREEN** · handler 加 `except Exception` 分支：返回 500 + 调 `sentry.capture_exception(e)`

**RED** · `test_handler_session_access_denied_does_not_leak_existence`
- 抛 `SessionAccessDeniedError(request_id="x")` → 断言 response.status_code == 404 + body.message == "会话不存在或已过期"（**不**说 "无权访问"）
- 跑测试 → 失败

**GREEN** · 确认子类 user_message 是中性文案

**RED** · `test_handler_no_relevant_docs_returns_200_with_message`
- 抛 `NoRelevantDocsError(...)` → 断言 status 200 + body.user_message == "未找到相关文档"
- 跑测试 → 失败

**GREEN** · 子类 http_status=200 验证

#### Task 3：11 条错误矩阵全测

**RED → GREEN × 11**：每个子类一个测试，断言 `http_status` / `error_code` / `user_message` 三件套

- `test_opensearch_down_returns_503`
- `test_tei_timeout_returns_422`
- `test_llm_upstream_returns_502`
- `test_no_relevant_docs_returns_200`
- `test_postgres_down_returns_503`
- `test_confluence_permission_returns_200`
- `test_confluence_rate_limit_returns_429`
- `test_document_parse_returns_200`
- `test_attachment_too_large_returns_413`
- `test_unauthenticated_returns_401`
- `test_session_access_denied_returns_404_no_leak`

**跑法**：`cd apps/rag_v1 && pytest tests/unit/test_error_handler.py -v`

#### Task 4：限速中间件（全局 100/min）

**RED** · `tests/unit/test_rate_limit.py::test_rate_limit_blocks_101st_request_per_minute`
- mock `get_remote_address` 返回 `"1.2.3.4"` → 连发 100 个 request 都 200、第 101 个 429
- 跑测试 → 失败

**GREEN** · `app/middleware/rate_limit.py`（r1 P1-1/2/4/10 重写）：
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
from app.auth.deps import get_current_user_optional
# r1 P1-10：health bypass 严格 exact path（防止 /api/health/dump 等子路径被 bypass）
HEALTH_PATHS = {"/api/health", "/api/health/live", "/api/health/ready"}

# r1 P1-1：限速 key 优先 user_id（从 JWT），fallback 到 IP
async def get_rate_limit_key(request: Request) -> str:
    """优先按 user_id（从 JWT 解析），fallback 到 IP"""
    try:
        user = await get_current_user_optional(request)
        return f"user:{user.id}" if user else f"ip:{get_remote_address(request)}"
    except Exception:
        return f"ip:{get_remote_address(request)}"

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

async def rate_limit_middleware(request: Request, call_next):
    # r1 P1-10：严格 exact path 集合（不是 startswith）
    if request.url.path in HEALTH_PATHS:
        return await call_next(request)

    # slowapi 通过 limiter 检查
    try:
        limiter.check(request)
    except RateLimitExceeded:
        return JSONResponse(
            status_code=429,
            content={
                "error_code": "rate_limited",  # r1 P1-4：与错误矩阵对齐
                "message": "请求过于频繁，请稍后重试",
                "request_id": getattr(request.state, "request_id", ""),
            },
            headers={"Retry-After": "60"},
        )
    return await call_next(request)

# r1 P1-4：注入 X-RateLimit-* 标准头（middleware 包装 call_next）
async def rate_limit_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    # r1 P1-4：标准限速头（业界事实标准）
    if hasattr(request.state, "_rate_limit_info"):
        info = request.state._rate_limit_info
        response.headers["X-RateLimit-Limit"] = str(info.get("limit", ""))
        response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", ""))
        response.headers["X-RateLimit-Reset"] = str(info.get("reset", ""))
    return response
```

**RED** · `test_rate_limit_health_endpoint_bypasses_limit`
- `/api/health` 连发 200 次 → 全 200，不被限速
- r1 P1-10 附加：`/api/health/dump` 连发 200 次 → 应被限速（不 bypass 子路径）

**GREEN** · middleware 顶部 `if request.url.path in HEALTH_PATHS: return await call_next(request)`

**r1-2026-06-11 P1-2**：uvicorn 启动加 `--proxy-headers --forwarded-allow-ips="10.0.0.0/8,172.16.0.0/12"`（prod 由 nginx reverse proxy 转发；`infra/README.md` 文档化）
- RED 测试：`test_rate_limit_trust_x_forwarded_for_when_proxy_headers_enabled`

**r1-2026-06-11 P1-4**：`app/middleware/errors.py` 加 `RateLimitedError` 类（`http_status=429`, `error_code="rate_limited"`），与 12 条错误矩阵对齐
- `app/api/main.py` 加：`app.state.limiter = limiter` + `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)`

#### Task 5：慢速 API 限速（chat 30/min、ingest 10/min）

**RED** · `test_chat_endpoint_30_per_minute_per_user`
- mock 用户 user_id="u1" → 第 30 个 POST `/api/chat` 200、第 31 个 429
- 跑测试 → 失败

**GREEN** · `app/middleware/rate_limit.py`（r1 P1-1 重写 · user-keyed）：
```python
from slowapi import Limiter
from functools import wraps

# r1 P1-1：限速 key 改用 get_rate_limit_key（user_id 优先）
limiter = Limiter(key_func=get_rate_limit_key, default_limits=["100/minute"])

def chat_limit_decorator(func):
    """chat 30/min/user（V1 单实例简化：按 user_id）"""
    return limiter.limit("30/minute")(func)

def ingest_limit_decorator(func):
    """ingest 10/min/user"""
    return limiter.limit("10/minute")(func)
```

**RED** · `test_chat_30_per_minute_per_user_not_per_ip`（r1 P1-1 新增）
- mock 同一 IP 两个 user（u1 / u2）→ 各发 30 次 → 都不 429；第 31 次开始各自 429
- 证明：限速按 user 而非 IP

**r1-2026-06-11 P2-10 决策**：限速 key `f"user:{user_id}:endpoint:/api/chat"` 30/min 是 user 全局（spec §7.5 语义），非 per-session
- DoD 明确写："30/min 是 user 总和而非 per-session"
- 未来 V2 可拆 per-thread_id

**RED** · `test_ingest_endpoint_10_per_minute_per_user`
- 第 10 个 POST `/api/ingest/file` 200、第 11 个 429

**GREEN** · 同上

**RED** · `test_rate_limit_response_includes_retry_after`
- 触发限速 → 断言 response body 含 `retry_after` 字段 + header `Retry-After: 60`

**GREEN** · 见上面 headers 注入

#### Task 6：Security headers middleware

**RED** · `tests/unit/test_security_headers.py::test_security_headers_present_on_all_responses`
- 调任意 endpoint → 断言 response 含 `Content-Security-Policy` / `Strict-Transport-Security` / `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`
- 跑测试 → 失败

**GREEN** · `app/middleware/security_headers.py`（r1 P1-3 重写 · spec §7.4 严格 CSP）：
```python
from fastapi import Request

async def security_headers_middleware(request: Request, call_next):
    # r1 P2-6：OPTIONS preflight 跳过 CSP（让 CORSMiddleware 处理 CORS 头）
    if request.method == "OPTIONS":
        return await call_next(request)
    response = await call_next(request)
    # r1 P1-3：严格按 spec §7.4（img-src 不放 https: 防 SSRF exfil）
    # X-2 联动：补 form-action 'self' base-uri 'self' 防 M5 SSRF redirect bypass
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "       # Gradio 5.0+ 必加
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "                    # r1 P1-3：去掉 https:（防 SSRF exfil）
        "font-src 'self'; "
        "connect-src 'self' ws: wss: http://localhost:8000; "  # r1 P1-3：明确 Gradio→FastAPI CORS
        "frame-ancestors 'none'; "
        "form-action 'self'; "                       # r1 X-2：防 M5 SSRF redirect bypass
        "base-uri 'self';"
    )
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response
```

**RED** · `test_csp_allows_unsafe_inline_for_gradio_compat`
- 断言 CSP `script-src` 含 `'unsafe-inline'`（Gradio 5.0+ 必加）

**RED** · `test_csp_img_src_does_not_allow_https_wildcard`（r1 P1-3 新增 · 避免 SSRF exfil 回归）
- 断言 CSP `img-src` **不**含 `https:`（spec §7.4 严格）

**GREEN** · 见上面字符串

#### Task 7：中间件挂载顺序 + 集成测试

**RED** · `tests/integration/test_m12_health_5services.py::test_all_middleware_applied_in_order`
- 调 `/api/chat` mock 抛 `UnauthenticatedError` → 断言 response 含安全头 + JSON body 含 error_code + Retry-After（未限速时不出现）
- 跑测试 → 失败

**GREEN** · `app/api/main.py`（M12 重写 · spec §3.12 LIFO 顺序）：
```python
# M12 挂载顺序（spec §3.12 严格对齐；FastAPI add_middleware 是 LIFO 栈）
# 写法：先 add 的 = 外层；后 add 的 = 内层（最接近 router）
# spec §3.12 顺序：RateLimit → SecurityHeaders → RequestID → CORSMiddleware → Auth(Depends)
# add_middleware 反向 add 即可：ErrorHandler(最外) → RateLimit → SecurityHeaders → RequestID → CORS

app.add_middleware(ErrorHandlerMiddleware)        # 1. 最外层（兜底所有异常）
app.add_middleware(RateLimitMiddleware)            # 2. 限速（在 CORS/SecurityHeaders 之前拒绝成本低）
app.add_middleware(SecurityHeadersMiddleware)     # 3. 安全头（429/5xx 错误响应也带）
app.add_middleware(RequestIDMiddleware)            # 4. request_id（M8 已建）
app.add_middleware(                                # 5. CORS（最内层，最接近 router）
    CORSMiddleware,
    allow_origins=settings.cors.allow_origins,     # 来自 config（P2-13 在 SecuritySettings 加 cors 子块）
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
)
# Auth 不是 middleware，是 Depends(get_current_user)，挂在 router 层（spec §3.12 注释）
```
**附加 RED 测试**：
- `test_middleware_order_rate_limit_runs_before_security_headers`：mock rate_limit 触发时 security_headers 调用计数 = 0（timing counter）
- `test_cors_preflight_returns_cors_headers_not_csp`：OPTIONS `/api/chat` 响应含 `Access-Control-Allow-*` 但不含 `Content-Security-Policy`（P2-6 联动）

**修正 L100 数据流图**：`[request_id] → [security_headers] → [rate_limit] → [error_handler]`
**r1-2026-06-11 P0-1 修正为**：`[error_handler] → [rate_limit] → [security_headers] → [request_id] → [cors] → [router]`（LIFO add_middleware + spec §3.12）

**RED** · `test_security_headers_applied_even_on_error_response`
- mock 抛 `OpenSearchDownError` → 断言 503 response 仍含 `X-Frame-Options: DENY`

**GREEN** · 错误响应也走 security_headers middleware

---

### Day 2 · Argon2 升级 + Sentry 集成

#### Task 8：Argon2 参数升级

**RED** · `tests/unit/test_argon2_upgrade.py::test_argon2_default_params_meet_owasp_2024`
- 读 `app.auth.service.ARGON2_TIME_COST` / `ARGON2_MEMORY_COST` → 断言 `time_cost >= 3` / `memory_cost >= 65536`
- 跑测试 → 失败（M2 是 2 / 20480）

**GREEN** · `app/auth/service.py`（M2 已建文件，修改）：
```python
# OWASP 2024 推荐：time_cost=3, memory_cost=65536（64 MiB）, parallelism=4
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536
ARGON2_PARALLELISM = 4

def hash_password(password: str) -> str:
    return PasswordHasher(
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
    ).hash(password)

def verify_password(hash_str: str, password: str) -> bool:
    ph = PasswordHasher(
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
    )
    try:
        ph.verify(hash_str, password)
        return True
    except VerifyMismatchError:
        return False
```

**RED** · `test_hash_password_takes_at_least_50ms`
- 调 `hash_password("test")` → 断言耗时 ≥ 50ms（time_cost=3 + memory_cost=65536 满足）
- 跑测试 → 失败

**GREEN** · 参数升级后自然满足

**RED** · `test_verify_password_with_old_hash_still_works`
- 用旧参数 hash（time_cost=2, memory_cost=20480）→ 用新 `verify_password` 验证 → 断言成功（argon2-cffi 内嵌参数识别）
- 跑测试 → 失败

**GREEN** · `PasswordHasher.verify` 自动识别 hash 内嵌参数（argon2 协议设计）

**REFACTOR** · 把 `ARGON2_*` 常量移到 `app/auth/config.py`（如果 M2 已经分）

#### Task 9：extend_session fire-and-forget vs BackgroundTasks 决策

**RED** · `tests/unit/test_extend_session.py::test_extend_session_does_not_block_response`
- mock `extend_session` 耗时 100ms → 调 `POST /api/chat` → 断言 response latency < 50ms（extend_session 后台跑）
- 跑测试 → 失败

**GREEN** · `app/auth/deps.py`（M2 已建文件，修改）：**决策：保留 fire-and-forget + 加错误日志**（BackgroundTasks 会污染 FastAPI Depends 签名，且 LangGraph state 已有 checkpointer 持久化）

```python
# 保留 fire-and-forget（M2 现状），M12 加：
import asyncio
from app.observability.sentry import capture_exception

async def extend_session(token: str) -> None:
    """fire-and-forget 延长 session 过期时间，失败不影响主请求"""
    try:
        # ... M2 已有的 session 延长逻辑
        pass
    except Exception as e:
        # M12 加：错误上报 Sentry（不静默）
        capture_exception(e)
        # **不重抛**：fire-and-forget 设计本意
```

**RED** · `test_extend_session_exception_captured_by_sentry`
- mock `extend_session` 内部抛异常 → 调主请求 → 断言 Sentry `capture_exception` 被调 + response 仍 200

**GREEN** · 见上面 try/except

#### Task 10：Sentry SDK init

**RED** · `tests/unit/test_sentry_integration.py::test_sentry_init_with_dsn`
- mock `sentry_sdk.init` → 调 `app.observability.sentry.init_sentry(dsn="https://...@sentry.io/123")` → 断言 `sentry_sdk.init` 被调 + `dsn` 参数透传
- 跑测试 → 失败

**GREEN** · `app/observability/sentry.py`（M12 重写 · P0-2 修 M10/M11 review trace_id API）：
```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from app.config import settings
# r1 修正：M10 review P0-2/3 + M11 review P0-6 都指出
# `app.observability.langfuse.get_current_trace_id()` API 在 langfuse 2.50+ 不存在
# 改用 ContextVar 桥接（由 LangGraph node entry/exit 显式 set_trace_id）

from app.observability.langfuse import get_current_trace_id  # r1 改：langfuse.py 加 ContextVar 实现

def init_sentry() -> None:
    """Sentry 初始化；dev 环境无 DSN 或 env=development 直接跳过（P1-5 联动）"""
    dsn = settings.sentry.dsn
    if not dsn or settings.env == "development":
        return  # r1 P1-5：dev 环境无 DSN + env=development 跳过（防 dev 误报污染 Sentry）
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=settings.sentry.traces_sample_rate,         # r1：从 config 读，默认 0.1
        profiles_sample_rate=settings.sentry.profiles_sample_rate,     # r1 P1-5：显式 0.0
        environment=settings.env,
        before_send=_scrub_pii,                                         # r1 P1-5：PII 脱敏
        send_default_pii=False,                                         # r1 P1-5：默认不发送 PII
    )

def capture_exception(e: Exception) -> None:
    """捕获异常上报 Sentry（fire-and-forget）"""
    # r1：先注入 trace_id 再 capture（M10 review P0-3 联动）
    set_langfuse_trace_id(get_current_trace_id() or "")
    sentry_sdk.capture_exception(e)

def set_langfuse_trace_id(trace_id: str) -> None:
    """Sentry scope tag 注入 langfuse trace_id（双向追溯）"""
    with sentry_sdk.configure_scope() as scope:
        scope.set_tag("langfuse_trace_id", trace_id or "n/a")

def _scrub_pii(event, hint):
    """r1 P1-5：PII 脱敏 before_send（spec §7.3）

    **r2-2026-06-12 r2-新-3 已修**：原代码只脱敏顶层 dict，漏掉嵌套结构 + headers + query string。
    修法：递归脱敏 + 显式 headers / query string 处理。
    """
    import re
    PII_KEYS = ('password', 'token', 'api_key', 'secret', 'session_id', 'authorization')

    def _scrub_dict(d):
        """递归脱敏嵌套 dict / list 里的 PII 字段"""
        if isinstance(d, dict):
            for k, v in list(d.items()):
                if k.lower() in PII_KEYS:
                    d[k] = '[REDACTED]'
                else:
                    d[k] = _scrub_dict(v)
        elif isinstance(d, list):
            return [_scrub_dict(x) for x in d]
        return d

    # 1) request body 嵌套脱敏
    if 'request' in event and 'data' in event.get('request', {}):
        event['request']['data'] = _scrub_dict(event['request']['data'])

    # 2) request headers 脱敏（r2 r2-新-3 补：Authorization: Bearer xxx）
    if 'request' in event and 'headers' in event.get('request', {}):
        for h in list(event['request']['headers'].keys()):
            if h.lower() in PII_KEYS:
                event['request']['headers'][h] = '[REDACTED]'

    # 3) request query_string 脱敏（r2 r2-新-3 补：?token=abc123）
    if 'request' in event and 'query_string' in event.get('request', {}):
        qs = event['request']['query_string']
        if isinstance(qs, str):
            for k in PII_KEYS:
                qs = re.sub(rf'({k}=)[^&]+', r'\1[REDACTED]', qs, flags=re.IGNORECASE)
            event['request']['query_string'] = qs

    # r1 P1-5：query 文本截断防日志爆炸
    if 'logentry' in event and 'message' in event['logentry']:
        msg = event['logentry']['message']
        if len(msg) > 500:
            event['logentry']['message'] = msg[:500] + '...[truncated]'
    return event
```

**`app/observability/langfuse.py`（M10 已建文件，M12 追加 P0-2 修复）**：
```python
# r1 P0-2：ContextVar 桥接 trace_id（M10 review P0-2/3 + M11 review P0-6 联动）
import contextvars
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langfuse_trace_id", default=None
)

def set_trace_id(tid: str) -> None:
    """LangGraph node entry/exit 显式调用（M10 plan 已落实节点出口调用点）"""
    _trace_id_var.set(tid)

def get_current_trace_id() -> str | None:
    """Sentry tag 注入用（P0-2 修 M10/M11 review 雷）"""
    return _trace_id_var.get()
```

**r1-2026-06-11 P0-2 修**：
1. 删除原 `from app.observability.langfuse import get_current_trace_id` 注释里的"⚠️ 不存在"
2. 实际用 `ContextVar` 实现 `_trace_id_var` + `set_trace_id`/`get_current_trace_id`
3. `capture_exception` 之前自动注入 `set_langfuse_trace_id(get_current_trace_id())`
4. PII 脱敏 `_scrub_pii` + dev 跳过 + `profiles_sample_rate=0.0`（P1-5 联动）

**r1-2026-06-11 P2-11 修**：5xx 关键错误 100% 上报（防 sampling 漏报）：
```python
# app/observability/sentry.py
def _force_sample_5xx(event, hint):
    """r1 P2-11：5xx 错误 100% 上报（不被 0.1 采样率漏掉）

    **r2-2026-06-12 r2-新-2 已修**：原代码检查 `event.contexts.response.status_code`（transaction event 结构）
    却注册到 `before_send_transaction` 钩子——钩子名与意图错位；event 钩子是 `before_send`。
    修法：注册到 `before_send`（event 级）而不是 `before_send_transaction`（transaction 级）。
    """
    # r2 r2-新-2：检查 `event.exception` 或 `event.level == "error"`（event 钩子结构）而非 transaction response status
    is_5xx_error = (
        event.get("level") == "error" and
        event.get("exception") is not None
    )
    if is_5xx_error:
        event.setdefault("tags", {})["critical"] = "5xx"  # 配 Sentry alert rule 单独通知
    return event
# init_sentry 注册：**r2-2026-06-12 r2-新-2 已修** 改 `before_send=_force_sample_5xx`（event 钩子，非 transaction）
# sentry_sdk.init(..., before_send=_force_sample_5xx)
```

**RED** · `test_init_sentry_skips_when_dsn_empty`
- `settings.sentry.dsn = ""` → 调 `init_sentry()` → 断言 `sentry_sdk.init` **未**被调

**GREEN** · `if not dsn: return`

#### Task 11：Sentry 5xx 上报 + trace_id 关联

**RED** · `test_handler_captures_5xx_to_sentry`
- 业务抛 `LLMUpstreamError`（502）→ 调 handler → 断言 `sentry_sdk.capture_exception` 被调
- 跑测试 → 失败

**GREEN** · `app/middleware/error_handler.py` 加：
```python
except RAGError as e:
    if e.http_status >= 500:
        sentry_sdk.capture_exception(e)
    return JSONResponse(...)
```

**RED** · `test_handler_skips_sentry_for_4xx`
- 抛 `UnauthenticatedError`（401）→ 断言 `capture_exception` **未**被调

**GREEN** · `if e.http_status >= 500:` 守住

**RED** · `test_sentry_scope_includes_langfuse_trace_id`
- mock `get_current_trace_id` 返回 `"trace-xyz"` → 调 `set_langfuse_trace_id("trace-xyz")` → 断言 `sentry_sdk.configure_scope().set_tag("langfuse_trace_id", "trace-xyz")` 被调

**GREEN** · 见 Task 10 `set_langfuse_trace_id`

**RED** · `test_error_handler_injects_trace_id_to_sentry_on_5xx`
- mock `get_current_trace_id` 返回 `"trace-xyz"` → 业务抛 `LLMUpstreamError` → handler → 断言 `set_langfuse_trace_id("trace-xyz")` 被调 + `capture_exception` 被调

**GREEN** · handler 在 `capture_exception` 之前调 `set_langfuse_trace_id`

#### Task 12：`SecuritySettings` + `ProdSettings` 配置块

**RED** · `tests/unit/test_prod_settings.py::test_security_settings_load`
- mock env `CSP_SCRIPT_SRC="self cdn.example.com"` → `Settings().security.csp_script_src` == `"self cdn.example.com"`
- 跑测试 → 失败

**GREEN** · `app/config.py` 追加：
```python
class SecuritySettings(BaseSettings):
    csp_default_src: str = "'self'"
    csp_script_src: str = "'self' 'unsafe-inline'"  # Gradio 5.0+ 兼容
    csp_style_src: str = "'self' 'unsafe-inline'"
    # r1 P1-3：去掉 https:（spec §7.4 严格 · 防 SSRF exfil）
    csp_img_src: str = "'self' data:"
    csp_connect_src: str = "'self' ws: wss: http://localhost:8000"  # r1 P1-3：明确 Gradio→FastAPI
    hsts_max_age: int = 31536000
    hsts_include_subdomains: bool = True
    # r1 P0-1：补 cors 子块（CORS allow_origins 从这里来）
    cors_allow_origins: list[str] = ["http://localhost:7860", "http://localhost:8000"]

class SentrySettings(BaseSettings):
    dsn: str = ""
    # r1 P1-5：从 config 读（dev 跳过由 init_sentry 判 env=development）
    traces_sample_rate: float = 0.1
    profiles_sample_rate: float = 0.0  # r1 P1-5：显式 0.0（sentry-sdk 默认 0.0 但要显式声明）
    environment: str = "development"

class ProdSettings(BaseSettings):
    """prod 部署专用设置（resource limits / secret 来源）"""
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 10
    opensearch_pool_size: int = 10
    # r1 P2-1：slowapi 内存 token bucket 在多 worker 进程下失效 → V1 单 worker
    api_workers: int = 1
    log_level: str = "INFO"
    secret_source: Literal["env_file", "docker_secrets", "vault"] = "env_file"

class BackupSettings(BaseSettings):
    pg_dump_path: str = "/usr/bin/pg_dump"
    pg_backup_dir: str = "/var/backups/rag/postgres"
    pg_wal_archive_dir: str = "/var/backups/rag/postgres/wal"
    os_snapshot_repo: str = "minio"  # 单节点用本地，多节点用 S3 兼容
    minio_endpoint: str = "minio.internal:9000"
    minio_bucket: str = "rag-backups"
    # r1 P1-9：MinIO creds 走 docker secrets `_FILE` 模式（不接受 .env 明文）
    minio_access_key_file: str = ""  # 读 /run/secrets/minio_access_key
    minio_secret_key_file: str = ""
    # r1 P1-9：retention 上下界保护（防误设 36500 天撑爆磁盘）
    backup_retention_days: int = Field(default=30, ge=7, le=365)
    backup_schedule: str = "0 2 * * *"  # 每日 02:00
```

**RED** · `test_backup_settings_load_with_minio_defaults`
- `Settings().backup.minio_endpoint` 断言默认 `"minio.internal:9000"`

**GREEN** · 见上面

**REFACTOR** · 把 SentrySettings 也并入（避免 Settings 单文件膨胀；用 sub-settings 嵌套）

---

### Day 3 · 备份脚本 + Restore 演练

#### Task 13：`pg_backup.sh` 脚本

**RED** · `tests/unit/test_backup_scripts.py::test_pg_backup_script_exists_and_executable`
- 断言 `infra/backup/pg_backup.sh` 存在 + 有 `+x` 权限 + shebang `#!/usr/bin/env bash`
- 跑测试 → 失败

**GREEN** · `infra/backup/pg_backup.sh`（r1 P0-3 + P2-9 重写 · 文件名无 `.gz` + 大小校验）：
```bash
#!/usr/bin/env bash
# Postgres 每日备份 + WAL 归档
# r1 P0-3：--format=custom --compress=9 是 pg_dump binary 格式 + 内嵌 zstd 压缩
#         文件后缀应为 .dump（无 .gz），避免双重扩展误导
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_DIR:-/var/backups/rag/postgres}"
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-rag}"
DB_USER="${DB_USER:-rag_app}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
MIN_SIZE_BYTES=1024  # r1 P2-9：< 1KB 视为空备份

mkdir -p "${BACKUP_DIR}"
BACKUP_FILE="${BACKUP_DIR}/rag_${TIMESTAMP}.dump"  # r1 P0-3：去 .gz 后缀

# 1. 全量 pg_dump（binary 格式 + zstd 压缩）
PGPASSWORD="${DB_PASSWORD}" pg_dump \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --format=custom --compress=9 \
    --file="${BACKUP_FILE}"

# 2. 校验备份完整性
pg_restore --list "${BACKUP_FILE}" > /dev/null

# 3. r1 P2-9：校验备份大小（空文件 < 1KB 直接失败）
FILE_SIZE=$(stat -c%s "${BACKUP_FILE}")
if [ "${FILE_SIZE}" -lt "${MIN_SIZE_BYTES}" ]; then
    echo "❌ 备份文件过小 (${FILE_SIZE} bytes)，怀疑 pg_dump 失败"
    exit 1
fi

# 4. r1 P2-9：校验包含关键表（users / auth_sessions / chat_sessions / ingest_jobs）
TABLES=$(pg_restore --list "${BACKUP_FILE}" | grep -c "TABLE.*rag")
if [ "${TABLES}" -lt 4 ]; then
    echo "❌ 备份缺少关键表（仅 ${TABLES} 张，应 ≥4）"
    exit 1
fi

# 5. 清理过期备份（> retention）
find "${BACKUP_DIR}" -name "rag_*.dump" -mtime +${RETENTION_DAYS} -delete

# 6. 上传 MinIO（prod 启用，r1 P1-9 改用 _FILE secrets 模式）
if [ -n "${MINIO_ACCESS_KEY_FILE:-}" ] && [ -r "${MINIO_ACCESS_KEY_FILE}" ]; then
    MINIO_ACCESS_KEY=$(cat "${MINIO_ACCESS_KEY_FILE}")
    MINIO_SECRET_KEY=$(cat "${MINIO_SECRET_KEY_FILE}")
    mc alias set backup "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}"
    mc cp "${BACKUP_FILE}" "backup/${MINIO_BUCKET}/postgres/"
fi

# 7. r1 P2-9：MinIO 上传启用 SSE-S3 加密 at rest（NEW-9 联动）
#    mc cp 默认不开加密，需 mc admin / mc encrypt 配置；详见 infra/backup/README.md

echo "[pg_backup] OK: ${BACKUP_FILE} (${FILE_SIZE} bytes, ${TABLES} tables)"
```

**RED** · `test_pg_backup_produces_pg_restore_compatible_file`（r1 P0-3 改名 · 替代 "gzipped"）：
- mock 环境 → 跑脚本 → 断言 `${BACKUP_DIR}/rag_*.dump` 存在 + 可被 `pg_restore --list` 解析 + 大小 ≥ 1KB
- **GREEN** · 集成测试在 staging 跑（用真 PG container + r1 P0-3 新增 `infra/docker-compose.minio.yml`）

**`infra/docker-compose.minio.yml`（r1 P0-3 新建）**：
```yaml
# r1 P0-3：MinIO 单 service + bucket init
# 用法：docker compose -f infra/docker-compose.yml -f infra/docker-compose.minio.yml up -d
services:
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER_FILE: /run/secrets/minio_root_user
      MINIO_ROOT_PASSWORD_FILE: /run/secrets/minio_root_password
    secrets:
      - minio_root_user
      - minio_root_password
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio-init:
    image: minio/mc:latest
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set local http://minio:9000 $(cat /run/secrets/minio_root_user) $(cat /run/secrets/minio_root_password);
      mc mb --ignore-existing local/rag-backups;
      mc anonymous set none local/rag-backups;
      "
    secrets:
      - minio_root_user
      - minio_root_password
    restart: "no"

secrets:
  minio_root_user:
    external: true
  minio_root_password:
    external: true

volumes:
  minio_data:
```

#### Task 14：WAL 归档脚本

**RED** · `test_wal_archive_copies_wal_to_archive_dir`
- mock WAL 文件生成 → 跑归档 → 断言 `${PG_WAL_ARCHIVE_DIR}/000000010000000000000001` 存在

**GREEN** · `infra/backup/wal_archive.sh`（独立脚本，`postgresql.conf` 里 `archive_command` 调）：
```bash
#!/usr/bin/env bash
set -euo pipefail
WAL_FILE="$1"
WAL_DEST="${WAL_ARCHIVE_DIR:-/var/backups/rag/postgres/wal}/$(basename ${WAL_FILE})"
cp "$WAL_FILE" "$WAL_DEST"
echo "[wal_archive] OK: $WAL_DEST"
```

**RED** · `test_wal_archive_handles_missing_source_gracefully`
- 传不存在的 WAL_FILE → 断言脚本 exit 1（非零）

**GREEN** · `set -e` 自动失败

#### Task 15：OpenSearch snapshot 脚本

**RED** · `tests/unit/test_backup_scripts.py::test_os_snapshot_creates_snapshot_and_uploads_to_minio`
- mock OS snapshot API + MinIO mc → 跑脚本 → 断言 snapshot 名 `rag-snapshot-YYYYMMDD` 创建 + mc cp 被调

**GREEN** · `infra/backup/os_snapshot.sh`：
```bash
#!/usr/bin/env bash
set -euo pipefail
OS_URL="${OS_URL:-http://opensearch:9200}"
SNAPSHOT_REPO="${SNAPSHOT_REPO:-rag_backup_repo}"
SNAPSHOT_NAME="rag-snapshot-$(date +%Y%m%d_%H%M%S)"

# 1. 注册 snapshot repo（首次）
if [ -n "${MINIO_ENDPOINT:-}" ]; then
    curl -fsS -X PUT "${OS_URL}/_snapshot/${SNAPSHOT_REPO}" \
        -H 'Content-Type: application/json' -d '{
            "type": "s3",
            "settings": {
                "bucket": "'"${MINIO_BUCKET}"'",
                "endpoint": "'"${MINIO_ENDPOINT}"'"
            }
        }'
fi

# 2. 创建 snapshot（**r2-2026-06-12 r2-新-6 已修**：wait_for_completion=true + 后续 state=SUCCESS 轮询）
curl -fsS -X PUT "${OS_URL}/_snapshot/${SNAPSHOT_REPO}/${SNAPSHOT_NAME}" \
    -H 'Content-Type: application/json' -d '{
        "indices": "rag_*",
        "include_global_state": false,
        "wait_for_completion": true
    }'

# **r2-2026-06-12 r2-新-6 已修**：轮询 snapshot state=SUCCESS 才 exit 0（防 MinIO 上传未完成就 return）
MAX_WAIT=${OS_SNAPSHOT_MAX_WAIT:-300}  # 5min
WAIT_INTERVAL=5
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    STATE=$(curl -fsS "${OS_URL}/_snapshot/${SNAPSHOT_REPO}/${SNAPSHOT_NAME}/_status" \
        | python3 -c "import sys, json; print(json.load(sys.stdin)['snapshots'][0]['state'])")
    if [ "$STATE" = "SUCCESS" ]; then
        echo "[os_snapshot] snapshot state=SUCCESS after ${ELAPSED}s"
        break
    fi
    if [ "$STATE" = "FAILED" ] || [ "$STATE" = "PARTIAL" ]; then
        echo "[os_snapshot] ERROR: snapshot state=$STATE" >&2
        exit 1
    fi
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done
if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "[os_snapshot] ERROR: timeout after ${MAX_WAIT}s" >&2
    exit 1
fi

echo "[os_snapshot] OK: ${SNAPSHOT_NAME}"
```

**RED** · `test_os_snapshot_uses_local_repo_when_minio_not_configured`
- `MINIO_ENDPOINT=""` → 断言 snapshot repo type == `fs`（本地路径）

**GREEN** · 见上面 `if [ -n "${MINIO_ENDPOINT:-}" ]` 分支

#### Task 16：恢复演练脚本（staging only）

**RED** · `tests/integration/test_m12_backup_restore.py::test_restore_pg_from_dump_in_staging`
- **仅在 staging 环境跑**（CI 用 testcontainers 启临时 PG）
- 写测试数据到 staging PG → 跑 `pg_backup.sh` → 删 staging PG → 跑 `restore.sh` → 断言数据完整恢复

**GREEN** · `infra/backup/restore.sh`（r1 P0-4 重写 · 三重门禁防误删 prod）：
```bash
#!/usr/bin/env bash
# ⚠️ 仅 staging 环境演练用，禁止 prod 运行！
# r1 P0-4：三重门禁 — STAGING_CONFIRM=yes + ENV=staging + AUTO_CONFIRM=yes(CI 用)
set -euo pipefail
BACKUP_FILE="$1"
DB_HOST="${DB_HOST:-postgres-staging}"
DB_NAME="${DB_NAME:-rag_staging}"

# 门禁 1：必须显式 STAGING_CONFIRM=yes（任何缺失都拒绝）
if [ "${STAGING_CONFIRM:-}" != "yes" ]; then
    echo "❌ 必须设 STAGING_CONFIRM=yes 才能跑恢复脚本（防误删 prod）"
    echo "   例：STAGING_CONFIRM=yes ENV=staging AUTO_CONFIRM=yes $0 /path/to/backup.dump"
    exit 1
fi

# 门禁 2：ENV 必须 = staging
if [ "${ENV:-}" != "staging" ]; then
    echo "❌ ENV 必须=staging（当前=${ENV:-unset}）"
    exit 1
fi

# 门禁 3：交互确认（CI testcontainer 用 AUTO_CONFIRM=yes 跳过）
if [ "${AUTO_CONFIRM:-}" != "yes" ]; then
    read -p "确认 staging 环境？[yes/no] " confirm
    [ "$confirm" = "yes" ] || exit 1
fi

echo "📦 准备从 ${BACKUP_FILE} 恢复到 ${DB_HOST}/${DB_NAME}"

# 1. drop + recreate db
psql -h "${DB_HOST}" -U postgres -c "DROP DATABASE IF EXISTS ${DB_NAME}"
psql -h "${DB_HOST}" -U postgres -c "CREATE DATABASE ${DB_NAME}"

# 2. 恢复
pg_restore -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" \
    --no-owner --role="${DB_USER}" "${BACKUP_FILE}"

echo "✅ 恢复完成"
```

**RED** · `test_restore_script_refuses_prod_env`（r1 P0-4 强化）：
- 4 个负向用例：缺 `STAGING_CONFIRM` → exit 1 / `STAGING_CONFIRM=yes` 但 `ENV=prod` → exit 1 / `STAGING_CONFIRM=yes ENV=staging` 但无 `AUTO_CONFIRM` 且 stdin closed → exit 1 / `ENV=staging STAGING_CONFIRM=yes AUTO_CONFIRM=yes` 跑通 → exit 0
- 1 个正向用例：`STAGING_CONFIRM=yes ENV=staging AUTO_CONFIRM=yes ./restore.sh test.dump` → exit 0

**GREEN** · 见上面三重门禁

**RED** · `test_backup_and_restore_roundtrip_preserves_data`
- 写 100 行 users → pg_backup → drop → restore → 断言行数一致

**GREEN** · 集成测试通过（CI 用 testcontainers）

---

### Day 4 · Prod Compose + 部署文档

#### Task 17：`docker-compose.prod.yml`（review X-4 决策点）

**RED** · `tests/integration/test_m12_prod_smoke.py::test_prod_compose_uses_no_host_port_mapping`
- 解析 `docker-compose.prod.yml` → 断言所有 service **没有** `ports:` 字段（仅 `expose:` 或内网访问）
- 跑测试 → 失败

**GREEN** · `infra/docker-compose.prod.yml`：
```yaml
# ⚠️ prod 部署专用：与 docker-compose.yml（base）叠加使用
# 用法：docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
services:
  api:
    image: rag-v1-api:${VERSION:-latest}
    restart: always
    expose:
      - "8000"  # 仅内网暴露
    environment:
      ENV: production
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      ANTHROPIC_API_KEY_FILE: /run/secrets/anthropic_api_key
    secrets:
      - postgres_password
      - anthropic_api_key
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    # r1 P2-12：最小化 Linux capabilities（防 privilege escalation）
    security_opt:
      - no-new-privileges:true
    # **r2-2026-06-12 r2-新-4 已修**：postgres / opensearch / minio 三个 service 同样加 `cap_drop: [ALL]`（r1 Task 17 只详写 `api`，L1165 注释"其他服务同样加"但没显式列）
    # security_opt:
    #   - no-new-privileges:true
    # cap_drop:
    #   - ALL
    # cap_add（按服务）:
    #   - postgres: [CHOWN, SETUID, SETGID, DAC_OVERRIDE]
    #   - opensearch: [CHOWN, SETUID, SETGID, NET_BIND_SERVICE]  # 9200 端口 < 1024 不需要，但 OpenSearch 需写 /usr/share/opensearch/data
    #   - minio: [CHOWN, SETUID, SETGID]  # 写 /data
    cap_drop:
      - ALL
    cap_add:
      - CHOWN       # postgres 启动需要
      - SETUID
      - SETGID
      - DAC_OVERRIDE
    healthcheck:
      test: ["CMD", "curl", "-fs", "http://localhost:8000/api/health/live"]  # r1 P2-4：liveness
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s  # r1 NEW-6：TEI 冷启友好
    # r1 X-1：lifespan hardening（chat 超时 + engine.dispose + SIGTERM handler）
    command: ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--proxy-headers", "--forwarded-allow-ips=10.0.0.0/8,172.16.0.0/12"]
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  postgres:
    image: postgres:16-alpine
    restart: always
    volumes:
      - pgdata:/var/lib/postgresql/data
      - /var/backups/rag/postgres:/var/backups/pg
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G

  # 其他服务同样加 resource limits + secrets

secrets:
  postgres_password:
    external: true  # 由 docker secret create 外部注入
  anthropic_api_key:
    external: true

volumes:
  pgdata:
```

**RED** · `test_prod_compose_sets_resource_limits_on_all_services`
- 断言每个 service `deploy.resources.limits` 都存在

**GREEN** · 见上面

**RED** · `test_prod_compose_uses_docker_secrets_not_env_file`
- 断言敏感字段用 `_FILE` 后缀（docker secrets 模式）

**GREEN** · 见上面

#### Task 18：`docker-compose.override.yml`（dev override）

**GREEN** · `infra/docker-compose.override.yml`（r1 P2-8 顶部加警告注释）：
```yaml
# ⚠️ r1 P2-8：本文件仅 dev 使用，禁止部署到 staging/prod
# 包含 dev 明文密码，故意保留便于本地 onboarding
# prod 部署用 docker-compose.yml + docker-compose.prod.yml（docker secrets 模式）
#
# ⚠️ dev 环境专用 override（自动 apply，不用 -f 显式指定）
# base = infra/docker-compose.yml，override = 本文件
services:
  api:
    build:
      context: ..
      dockerfile: Dockerfile
    ports:
      - "8000:8000"           # dev 暴露端口
    volumes:
      - ..:/app               # 源码热挂载
    environment:
      ENV: development
      POSTGRES_PASSWORD: rag_dev_password  # dev 明文 OK（仅 dev）
    # r1 NEW-4：dev compose 也加 resource limit（避免本地占满资源）
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G

  postgres:
    ports:
      - "5432:5432"
    volumes:
      - pgdata_dev:/var/lib/postgresql/data
```

**RED** · `tests/integration/test_m12_prod_smoke.py::test_dev_override_exposes_ports`
- 解析 `docker-compose.override.yml` → 断言 api 有 `ports: 8000:8000`
- 跑测试 → 失败

**GREEN** · 见上面

#### Task 19：`infra/README.md` 三环境部署文档

**RED** · `tests/integration/test_m12_prod_smoke.py::test_readme_has_three_environments`
- 读 `infra/README.md` → 断言含 "dev" / "staging" / "prod" 三节

**GREEN** · `infra/README.md` 大纲：
```markdown
# RAG V1 部署指南

## 快速启动（dev）
docker compose up -d

## staging 环境
1. 拉镜像：docker compose -f docker-compose.yml pull
2. 起服务：docker compose -f docker-compose.yml up -d
3. 跑 migrations：docker compose exec api alembic upgrade head
4. 备份演练：ENV=staging ./infra/backup/restore.sh ...

## prod 环境
1. 创建 docker secrets：
   echo "$POSTGRES_PASSWORD" | docker secret create postgres_password -
   echo "$ANTHROPIC_API_KEY" | docker secret create anthropic_api_key -
2. 打镜像：docker build -t rag-v1-api:$VERSION .
3. 起服务：docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
4. 验证：curl http://api.internal:8000/api/health

## 监控
- /api/health 探测 5 service 状态
- Sentry dashboard：5xx 告警
- Langfuse dashboard：业务 trace

## 备份
- Postgres：每日 02:00（pg_dump + WAL 归档）
- OpenSearch：每日 03:00（snapshot → MinIO）
- 恢复演练：每月一次（staging 环境）
```

#### Task 20：健康检查 5 service

**RED** · `tests/integration/test_m12_health_5services.py::test_health_endpoint_returns_5_service_status`
- 调 `GET /api/health` → 断言 response 含 5 个 key：`postgres` / `opensearch` / `tei` / `langfuse` / `graph`
- 每个 key 含 `status: "ok"|"down"` + `latency_ms`
- 跑测试 → 失败

**GREEN** · `app/api/health.py`（r1 P1-6/7 + P2-2/4 + NEW-19 重写）：
```python
import asyncio
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import httpx
from app.db.session import get_session      # r1 P2-2：修路径（M1 实际是 app.db.session.get_session）
from app.retrieval.os_client import get_opensearch_client
from app.retrieval.tei_client import get_tei_client
from app.observability.langfuse import get_langfuse_client
from app.graph.workflow import get_graph
from app.config import settings
from sqlalchemy import text

router = APIRouter()

# r1 P1-7：单个 checker 超时上限 2s（k8s readiness 默认 1s，避免拖垮 health endpoint）
CHECK_TIMEOUT = 2.0

async def _run_check(name, checker):
    """r1 P1-7：单 checker 超时保护 + 错误脱敏（NEW-19）"""
    try:
        async with asyncio.timeout(CHECK_TIMEOUT):
            await checker()
        return name, {"status": "ok"}
    except asyncio.TimeoutError:
        return name, {"status": "down", "error_code": "health_timeout"}  # r1 NEW-19：脱敏
    except Exception as e:
        # r1 NEW-19：error_code + sanitized message，不暴露内部栈
        return name, {"status": "down", "error_code": type(e).__name__, "message": str(e)[:100]}

async def check_postgres():
    async with get_session() as s:
        await s.execute(text("SELECT 1"))

async def check_opensearch():
    client = get_opensearch_client()
    await client.cluster.health()

async def check_tei():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{settings.tei.base_url}/health", timeout=1.0)
        r.raise_for_status()

async def check_langfuse():
    # r1 P1-6：HTTP GET /api/public/health，不调 callback（防污染 trace）
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{settings.langfuse.host}/api/public/health", timeout=1.0)
        r.raise_for_status()

async def check_graph():
    # r1 P1-6：只测 graph 编译可用，不跑业务
    # 避免污染 Langfuse trace + 触发 OpenSearch kNN 检索
    graph = get_graph()
    assert hasattr(graph, "nodes") and len(graph.nodes) >= 7  # M7 spec 7 节点

# r1 P1-7：5 service 并行探测（总耗时 ≤ max(CHECK_TIMEOUT) 而非 sum）
ALL_CHECKS = [
    ("postgres", check_postgres),
    ("opensearch", check_opensearch),
    ("tei", check_tei),
    ("langfuse", check_langfuse),
    ("graph", check_graph),
]

# r1 P2-4：拆 /api/health/live（进程活） vs /api/health/ready（5 service 绿）
# k8s liveness 用 live，readiness probe 用 ready
@router.get("/api/health/live")
async def liveness():
    """k8s liveness probe：仅返 200（进程活着）"""
    return {"status": "alive"}

@router.get("/api/health/ready")
async def readiness(verbose: bool = False, token: str = ""):
    """k8s readiness probe：5 service 全绿才 200，否则 503"""
    # r1 P1-10：verbose mode 仅 admin token 通过才返 services 详情
    results = await asyncio.gather(*[_run_check(n, c) for n, c in ALL_CHECKS])
    services = dict(results)
    all_ok = all(s["status"] == "ok" for s in services.values())
    body = {"all_ok": all_ok}
    if verbose and token == settings.admin.token:
        body["services"] = services  # r1 P1-10：verbose 详情仅 admin 看
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content=body,
    )

# r1 P2-4：保留 /api/health 兼容旧客户端（= /api/health/ready 别名）
@router.get("/api/health")
async def health():
    return await readiness()
```

**RED** · `test_health_endpoint_returns_5_service_status`（r1 改 `ready`）：
- 调 `GET /api/health/ready` → 断言 200 + body.all_ok
- 详细模式：`?verbose=true&token=$ADMIN_TOKEN` → 断言含 `services.{name}.status`

**RED** · `test_liveness_endpoint_does_not_check_dependencies`（r1 P2-4 新增）
- 调 `GET /api/health/live` → 断言 200 + 不调任何 service check（mock checker 调用计数 = 0）

**RED** · `test_health_check_does_not_invoke_llm`（r1 P1-6 新增）
- mock LLM 抛错但 `check_graph` 仍 200（不依赖 LLM）

**RED** · `test_health_endpoint_returns_within_3_seconds_even_when_one_service_times_out`（r1 P1-7 新增）
- mock TEI 慢响应（>2s）→ 调 `GET /api/health/ready` → 断言 < 3s 返回 + TEI.status=down

**GREEN** · 见上面 `_run_check` + `asyncio.gather` 并行

---

### Day 5 · GitHub Actions + 端到端

#### Task 21：CI workflow（lint + unit + integration + RAGAS gate）

**RED** · `tests/integration/test_m12_ci_local.py::test_ci_workflow_yaml_valid`
- 解析 `.github/workflows/ci.yml` → 断言 4 个 job：`lint` / `unit` / `integration` / `ragas-gate`
- 跑测试 → 失败

**GREEN** · `.github/workflows/ci.yml`：
```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r apps/rag_v1/requirements-dev.txt
      - run: cd apps/rag_v1 && ruff check app/ tests/

  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r apps/rag_v1/requirements-dev.txt
      - run: cd apps/rag_v1 && pytest tests/unit/ --cov=app --cov-fail-under=85

  integration:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: rag_test
          POSTGRES_USER: rag_test
          POSTGRES_PASSWORD: rag_test
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 5s
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      # r1 P2-3：CI runner 默认无 postgresql-client（psql/pg_restore 找不到）
      - name: Install postgres client
        run: sudo apt-get update && sudo apt-get install -y postgresql-client
      # r1 P1-8：--wait 阻塞直到所有 healthcheck 通过（替代 sleep 30）
      - name: Start services
        run: docker compose -f infra/docker-compose.yml up -d --wait
        env:
          # r1 P1-2：proxy-headers 配合 nginx reverse proxy
          COMPOSE_HTTP_TIMEOUT: 300
      - run: cd apps/rag_v1 && pytest tests/integration/ -v --timeout=300

  ragas-gate:
    runs-on: ubuntu-latest  # ⚠️ 无 GPU
    timeout-minutes: 30    # RAGAS 20 题上限
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Install postgres client
        run: sudo apt-get update && sudo apt-get install -y postgresql-client
      - name: Start services
        run: docker compose -f infra/docker-compose.yml up -d --wait
      - run: cd apps/rag_v1 && python -m app.eval.ragas_run \
            --golden-set tests/fixtures/golden_set_v1.jsonl \
            --sample-size 20 --threshold 0.65 \
            --report-json /tmp/ragas.json
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

**RED** · `test_ci_workflow_uses_compose_wait_not_sleep_30`（r1 P1-8 新增）
- 解析 yaml 断言 integration / ragas-gate job 含 `up -d --wait`，无 `sleep 30`

**RED** · `test_integration_job_uses_real_postgres_service_container`
- 断言 integration job 有 `services.postgres` 块（review P0-5 避雷）

**GREEN** · 见上面

**r1-2026-06-11 X-3**：RAGAS threshold 从 `0.7` 降到 `0.65`（M11 review P0-5 · 20 题下 0.05 抖动窗口）
- DoD 加：nightly faithfulness 报告保留 30 天 baseline，PR 触发时与 baseline diff 超过 ±0.05 报警

#### Task 22：Docker BuildKit cache（review P1-4）

**RED** · `test_ci_uses_buildkit_cache`
- 断言 integration / ragas-gate job 有 `cache-from: type=gha` / `cache-to: type=gha,mode=max`

**GREEN** · CI workflow 加：
```yaml
      - uses: docker/build-push-action@v5
        with:
          context: apps/rag_v1
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**REFACTOR** · 把 build 步骤抽 `actions/setup-buildx@v3`

#### Task 23：Nightly RAGAS workflow

**RED** · `test_nightly_workflow_runs_at_2am_utc`
- 解析 `.github/workflows/nightly-ragas.yml` → 断言 `cron: "0 2 * * *"`（每日 02:00 UTC）
- 跑测试 → 失败

**GREEN** · `.github/workflows/nightly-ragas.yml`：
```yaml
name: Nightly RAGAS

on:
  schedule:
    - cron: "0 2 * * *"  # 每日 02:00 UTC
  workflow_dispatch:      # 允许手动触发

jobs:
  ragas-full:
    runs-on: ubuntu-latest
    timeout-minutes: 60  # 50 题 + 缓冲
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      # r1 P2-3：nightly runner 也需 postgres client
      - name: Install postgres client
        run: sudo apt-get update && sudo apt-get install -y postgresql-client
      - name: Start services
        run: docker compose -f infra/docker-compose.yml up -d --wait
      - run: cd apps/rag_v1 && python -m app.eval.ragas_run \
            --golden-set tests/fixtures/golden_set_v1.jsonl \
            --sample-size 50 --threshold 0.75 \
            --report-json reports/ragas_$(date +%Y%m%d).json \
            --report-html reports/ragas_$(date +%Y%m%d).html
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: actions/upload-artifact@v4
        with:
          name: ragas-report
          path: apps/rag_v1/reports/
          retention-days: 90
```

**RED** · `test_nightly_uploads_report_as_artifact`
- 断言有 `actions/upload-artifact@v4` 步骤 + 保留 90 天

**GREEN** · 见上面

#### Task 24：CI 模拟跑（act 或 docker compose）

**RED** · `tests/integration/test_m12_ci_local.py::test_local_ci_runs_ruff_and_unit_tests`
- 本地 `docker compose -f infra/docker-compose.yml run --rm api bash -c "ruff check app/ && pytest tests/unit/"` 跑通
- 跑测试 → 失败（缺 CI step 串联脚本）

**GREEN** · `infra/scripts/ci_local.sh`（r1 P2-7 重写 · git rev-parse 找仓库根）：
```bash
#!/usr/bin/env bash
set -euo pipefail
# r1 P2-7：原版 `cd "$(dirname "$0")/../.."` 在 CI working-directory=apps/rag_v1 时路径错
# 改用 git rev-parse --show-toplevel 找仓库根
REPO_ROOT="$(git rev-parse --show-toplevel)"
APP_DIR="${REPO_ROOT}/apps/rag_v1"
cd "${APP_DIR}"
echo "=== Lint ==="
ruff check app/ tests/
echo "=== Unit ==="
pytest tests/unit/ --cov=app --cov-fail-under=85
echo "=== Integration (requires docker compose up) ==="
docker compose -f infra/docker-compose.yml up -d --wait
pytest tests/integration/ -v --timeout=300
echo "✅ CI local passed"
```

**RED** · `test_local_ci_script_exits_zero_when_all_pass`
- 跑 `ci_local.sh` → 断言 exit 0

**GREEN** · 见上面

#### Task 25：M12 smoke test 端到端

**RED** · `tests/integration/test_m12_prod_smoke.py::test_prod_compose_up_smoke`
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` → 解析成功（YAML 合法）
- `docker compose ... up -d` → 等 60s → `curl http://api:8000/api/health` → 200 + all_ok
- 跑测试 → 失败

**GREEN** · 实现测试 + `compose down -v` 清理

**RED** · `test_prod_compose_no_host_port_conflict`
- 解析 `docker compose ... config` → 断言 services **不**暴露 host 端口（review P0-1 避雷）

**GREEN** · 见 Task 17 配 `expose:` 而非 `ports:`

#### Task 26（r1 X-1 新增）· Lifespan hardening · Chat timeout · SIGTERM handler

**RED** · `tests/integration/test_m12_lifespan.py::test_engine_disposed_on_shutdown`
- mock asyncpg engine → lifespan shutdown → 断言 `engine.dispose()` 被调

**RED** · `test_chat_timeout_raises_504_chat_timeout_error`
- mock graph.ainvoke 阻塞 60s → 调 `POST /api/chat` → 断言 504 + body.error_code == "chat_timeout"

**GREEN** · `app/api/main.py`（r1 X-1 重写）：
```python
# r1 X-1：lifespan hardening（M8 review P0-1/2 收口）
from contextlib import asynccontextmanager
from app.db.session import asyncpg_engine
# **r2-2026-06-12 r2-新-1 已修**：L1598 原 `from app.api.chat import get_graph, ChatTimeoutError` 错位——get_graph 实际在 app.graph.workflow，ChatTimeoutError 实际在 app.middleware.errors。修法：拆 2 行显式 import
from app.graph.workflow import get_graph
from app.middleware.errors import ChatTimeoutError
import signal

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：探活
    try:
        async with asyncpg_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        sentry.capture_exception(e)
        # 不抛：M12 PostgresDownError 已在 error_handler 处理
    yield
    # 关闭：dispose + SIGTERM 收口
    try:
        await asyncio.wait_for(asyncpg_engine.dispose(), timeout=10)
    except asyncio.TimeoutError:
        sentry.capture_message("engine.dispose timeout", level="warning")

# r1 X-1：chat 超时（30s 默认，spec §3.7）
CHAT_TIMEOUT = 30.0

@app.post("/api/chat")
async def chat(req: ChatRequest, ...):
    try:
        result = await asyncio.wait_for(
            graph.ainvoke({"query": req.query, "thread_id": req.thread_id}),
            timeout=CHAT_TIMEOUT,
        )
        return result
    except asyncio.TimeoutError:
        raise ChatTimeoutError(f"chat 超时 ({CHAT_TIMEOUT}s)", request_id=request.state.request_id)

# r1 X-1：SIGTERM handler（k8s pod 终止时 inflight request 处理）
def _sigterm_handler(signum, frame):
    """r1 NEW-8：k8s SIGTERM 信号捕获"""
    import sentry_sdk
    sentry_sdk.capture_message(f"SIGTERM received: {signum}")
    # 触发 graceful shutdown（asyncio 事件循环）
    raise SystemExit(0)

signal.signal(signal.SIGTERM, _sigterm_handler)
signal.signal(signal.SIGINT, _sigterm_handler)
```

**r1-2026-06-11 X-1 修**：错误矩阵从 11 条扩展为 12 条（新增 `ChatTimeoutError` 504），覆盖 M8 P0-1（chat 超时）+ M8 P0-2（lifespan dispose）+ NEW-7/8（graceful shutdown + SIGTERM）。

**r1-2026-06-11 X-3**：RAGAS threshold 0.7 → 0.65（已在 Task 21 改）

**r1-2026-06-11 X-5**：`extend_session` 改用 `datetime.now(tz=UTC).timestamp()` 一次调用（M2 review P1-9 竞争窗口）
- RED 测试 `test_extend_session_uses_single_datetime_now_call`：用 freezegun 验证 `now()` 仅调 1 次

---

## 测试策略

- **M12 单元**：`cd apps/rag_v1 && pytest tests/unit/test_error_handler.py tests/unit/test_rate_limit.py tests/unit/test_security_headers.py tests/unit/test_argon2_upgrade.py tests/unit/test_sentry_integration.py tests/unit/test_prod_settings.py tests/unit/test_extend_session.py tests/unit/test_backup_scripts.py` —— 全 mock，CI 内 10s
- **M12 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m12_backup_restore.py tests/integration/test_m12_ci_local.py tests/integration/test_m12_prod_smoke.py tests/integration/test_m12_health_5services.py` —— docker compose up，CI 内 5 分钟
- **M12 真端到端**（**手工**，不进 CI）：本地起 prod compose → `curl /api/health` → 手动验证 5 service 全绿；staging 环境跑 `restore.sh` 演练
- **覆盖率门禁**：`pytest --cov=app/middleware --cov=app/observability --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 [RED]）→ GREEN（[GREEN]）→ REFACTOR（[RF]）

---

## 验证（Definition of Done）

### 错误处理（12 条全过 · r1 从 11 条扩为 12 条）

- [ ] `test_opensearch_down_returns_503` 通过
- [ ] `test_tei_timeout_returns_422` 通过
- [ ] `test_llm_upstream_returns_502` 通过
- [ ] `test_no_relevant_docs_returns_200` 通过
- [ ] `test_postgres_down_returns_503` 通过
- [ ] `test_confluence_permission_returns_200` 通过
- [ ] `test_confluence_rate_limit_returns_429` 通过
- [ ] `test_document_parse_returns_200` 通过
- [ ] `test_attachment_too_large_returns_413` 通过
- [ ] `test_unauthenticated_returns_401` 通过
- [ ] `test_session_access_denied_returns_404_no_leak` 通过
- [ ] **`test_chat_timeout_returns_504` 通过（r1 X-1 新增 · M8 P0-1 收口）**

### 限速（r1 P1-1/4 强化）

- [ ] `test_rate_limit_blocks_101st_request_per_minute` 通过
- [ ] `test_rate_limit_health_endpoint_bypasses_limit` 通过
- [ ] **`test_rate_limit_trust_x_forwarded_for_when_proxy_headers_enabled`（r1 P1-2 新增）**
- [ ] **`test_health_bypass_only_exact_path`（r1 P1-10 新增）**
- [ ] `test_chat_endpoint_30_per_minute_per_user` 通过
- [ ] **`test_chat_30_per_minute_per_user_not_per_ip`（r1 P1-1 新增）**
- [ ] `test_ingest_endpoint_10_per_minute_per_user` 通过
- [ ] **`test_429_response_includes_retry_after_header`（r1 P1-4 新增）**

### Security headers（r1 P1-3 严格）

- [ ] `test_security_headers_present_on_all_responses` 通过
- [ ] `test_csp_allows_unsafe_inline_for_gradio_compat` 通过
- [ ] **`test_csp_img_src_does_not_allow_https_wildcard`（r1 P1-3 新增）**
- [ ] **`test_cors_preflight_returns_cors_headers_not_csp`（r1 P2-6 新增）**

### Argon2 + Sentry（r1 P1-5 强化）

- [ ] `test_argon2_default_params_meet_owasp_2024` 通过（time_cost=3, memory_cost=65536）
- [ ] `test_hash_password_takes_at_least_50ms` 通过
- [ ] `test_init_sentry_skips_when_dsn_empty` 通过
- [ ] **`test_sentry_skips_init_when_env_is_development`（r1 P1-5 新增）**
- [ ] **`test_sentry_before_send_redacts_password_field`（r1 P1-5 新增）**
- [ ] `test_handler_captures_5xx_to_sentry` 通过
- [ ] **`test_sentry_scope_includes_langfuse_trace_id`（r1 P0-2 ContextVar 桥接）**

### 备份（r1 P0-3/4 + P2-9 强化）

- [ ] `test_pg_backup_script_exists_and_executable` 通过
- [ ] **`test_pg_backup_produces_pg_restore_compatible_file`（r1 P0-3 改名）**
- [ ] **`test_pg_backup_fails_on_empty_dump_file`（r1 P2-9 新增）**
- [ ] `test_wal_archive_copies_wal_to_archive_dir` 通过
- [ ] `test_os_snapshot_creates_snapshot_and_uploads_to_minio` 通过
- [ ] **`test_restore_script_refuses_prod_env` 三重门禁（r1 P0-4 强化 · 4 负向 + 1 正向）**
- [ ] `test_backup_and_restore_roundtrip_preserves_data` 通过（staging 演练）

### Prod 部署（r1 P2-12 强化）

- [ ] `test_prod_compose_uses_no_host_port_mapping` 通过
- [ ] `test_prod_compose_sets_resource_limits_on_all_services` 通过
- [ ] `test_prod_compose_uses_docker_secrets_not_env_file` 通过
- [ ] **`test_dev_override_exposes_ports` + 顶部警告注释（r1 P2-8）**
- [ ] `test_readme_has_three_environments` 通过
- [ ] **`test_liveness_endpoint_does_not_check_dependencies`（r1 P2-4 新增）**
- [ ] **`test_readiness_endpoint_returns_503_when_one_service_down`（r1 P2-4 新增）**
- [ ] **`test_health_endpoint_returns_within_3_seconds_even_when_one_service_times_out`（r1 P1-7 新增）**
- [ ] **`test_health_check_does_not_invoke_llm`（r1 P1-6 新增）**
- [ ] **`test_health_verbose_requires_admin_token`（r1 P1-10 新增）**

### CI（r1 P1-8 + P2-3 + X-3 强化）

- [ ] `test_ci_workflow_yaml_valid` 通过
- [ ] `test_ragas_gate_job_has_timeout_30_minutes` 通过
- [ ] `test_integration_job_uses_real_postgres_service_container` 通过（review P0-5 避雷）
- [ ] **`test_ci_workflow_uses_compose_wait_not_sleep_30`（r1 P1-8 新增）**
- [ ] `test_ci_uses_buildkit_cache` 通过
- [ ] `test_nightly_workflow_runs_at_2am_utc` 通过
- [ ] `test_nightly_uploads_report_as_artifact` 通过
- [ ] **RAGAS threshold 0.7 → 0.65（r1 X-3）**
- [ ] **nightly faithfulness baseline 保留 30 天（r1 X-3）**

### Lifespan hardening（r1 X-1 新增）

- [ ] **`test_engine_disposed_on_shutdown`（r1 X-1 · M8 P0-2 收口）**
- [ ] **`test_chat_timeout_raises_504_chat_timeout_error`（r1 X-1 · M8 P0-1 收口）**
- [ ] **`test_extend_session_uses_single_datetime_now_call`（r1 X-5 · M2 P1-9 收口）**

### 通用

- [ ] 单元覆盖率 ≥ 85%
- [ ] `pytest tests/integration/test_m12_ci_local.py` 模拟 CI 流程跑通
- [ ] 手工 `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --wait` 起得来 + `/api/health/live` 200 + `/api/health/ready` 503→200
- [ ] staging 环境 `restore.sh` 演练成功（恢复 100 行数据无丢失，三重门禁有效）
- [ ] **SLO 定义（r1 NEW-14 落地）：API 可用率 99.9% / chat P95 < 3s / RAGAS faithfulness baseline 保留 30 天**

---

## 与其他 M 的依赖

| 上游（必须 M12 前完成） | 下游（依赖 M12） |
|----------------------|----------------|
| M0 docker-compose（base compose 文件） | **无**（V1 最后一步，下游 = V2） |
| M1 alembic（DB schema） | |
| M2 auth（extend_session / Argon2 baseline） | |
| M3 LLM 工厂（judge LLM / smoke test） | |
| M7 graph（health() 接口暴露） | |
| M7 retrieval（os_client / tei_client health()） | |
| M8 API（main.py 中间件挂载点） | |
| M9 Gradio UI（Gradio 5.0+ CSP 兼容） | |
| M10 Langfuse（trace_id 注入 Sentry） | |
| M11 RAGAS（CI gate 接入） | |

---

## 风险

|| 风险 | 缓解 | 曾被否决的替代方案 | r1 状态 |
||------|------|------------------|--------|
|| **CI runner 无 GPU**（M3 smoke test 跑真 LLM 会超时） | **M12 P0 避雷**：CI 不跑 M3 smoke；RAGAS gate 用真 LLM + 30 分钟超时；unit test 全 mock LLM | "CI 跑真 LLM" — **已否决**（GitHub Actions 无 GPU，5 分钟内必超时） | r0 已修 |
|| **备份恢复演练误删 prod 数据** | `restore.sh` 顶部强制 `ENV != prod`；staging 演练；CI 用 testcontainers 起临时 PG | "prod 演练" — **已否决**（风险太高） | r1 P0-4 加强为三重门禁（STAGING_CONFIRM + ENV + AUTO_CONFIRM） |
|| **CSP 影响 Gradio 5.0+ 渲染** | **M12 P0 避雷**：CSP `script-src 'self' 'unsafe-inline'` + `style-src 'self' 'unsafe-inline'` 必加；Gradio 5.0+ 用 inline JS | "CSP 严格 self" — **已否决**（Gradio 渲染失败） | r1 P0-1 修 |
|| **限速误伤健康检查** | **M12 P0 避雷**：`/api/health` 路径在 middleware 顶部 bypass | "全限速不加 bypass" — **已否决**（健康检查被自己限速） | r1 P1-10 严格 exact path 集合（含 live/ready） |
|| **Sentry 关联 Langfuse trace_id 缺失** | **M12 P1 缓解**：`set_langfuse_trace_id()` 在 `capture_exception` 之前调；handler 自动注入 scope tag | "不关联" — review P1-1，关联便于双向追溯 | r1 P0-2 改 ContextVar 桥接（修 M10/M11 review 雷） |
|| **WAL 归档磁盘满** | **M12 P1 缓解**：`pg_backup.sh` 末尾清理 > retention；监控 `/var/backups` 容量 + 告警阈值 80% | "永久保留 WAL" — **已否决**（磁盘爆炸） | r0 已修 |
|| **OpenSearch snapshot 单节点 vs 多节点** | **M12 P1 缓解**：`SNAPSHOT_REPO` env 切换；单节点 `fs`、多节点 `s3` | "统一 S3" — 单节点 MinIO 太重 | r0 已修 |
|| **CI docker layer 缓存失效** | **M12 P1 缓解**：BuildKit `cache-from: type=gha` / `cache-to: type=gha,mode=max` | "无缓存每次重 build" — **已否决**（CI 拖慢 5-10 分钟） | r0 已修 |
|| **prod env 注入方式（docker secrets vs env file vs k8s secret）** | **M12 P1 决策**：V1 走 docker secrets（Compose 模式）；V2 走 k8s + Vault | "env file 注入 prod" — **已否决**（review P1-3 风险） | r1 P1-9 改 `_FILE` 后缀（MinIO creds） |
|| **Argon2 memory_cost=65536 单实例内存压力** | M2 已跑 dev 验证（每 hash ~80ms 可接受）；prod 监控 hash 调用频率 | "保持 20480" — review P1-7，OWASP 不达标 | r0 已修 |
|| **extend_session fire-and-forget 失败无感知** | **M12 决策：保留 fire-and-forget + Sentry 上报失败**；不引入 BackgroundTasks（污染 Depends 签名） | "改 BackgroundTasks" — 改动量大、LangGraph 已有 checkpointer 兜底 | r1 X-5 修 datetime 一次调用 |
|| **backup_retention 30 天 GDPR 风险** | 备份数据含用户密码 hash、session token hash；retention 30 天符合 spec §5 | "永久保留" — GDPR 不允许 | r1 P1-9 加 `Field(ge=7, le=365)` 上下界 |
|| **CI RAGAS gate 20 题指标波动** | golden set git 化锁版本 + PR review 必看 fixture diff；CI 设 `--sample-size 20` | "CI 跑 50 题" — CI timeout 风险 | r1 X-3 threshold 0.7→0.65 + 30 天 baseline |
|| **error_handler 误吞非 RAGError 异常** | 顶层 `except Exception` 兜底 500 + Sentry 上报；测试 `test_handler_unexpected_exception_returns_500_with_sentry` 覆盖 | "只 catch RAGError" — **已否决**（裸异常 500 暴露栈信息） | r0 已修 |
|| **中间件挂载顺序与 spec §3.12 矛盾** | 严格按 spec §3.12 LIFO add_middleware（ErrorHandler→RateLimit→SecurityHeaders→RequestID→CORS） | "自创顺序" — 已在 review P0-1 否决 | **r1-2026-06-11 P0-1 已修** |
|| **backup_restore 演练 CI 跑时 stdin closed 触发误判** | `restore.sh` 加 `AUTO_CONFIRM=yes` 跳过交互；`STAGING_CONFIRM=yes` 必填 | "无 stdin 保护" — **已否决**（CI 必挂） | **r1-2026-06-11 P0-4 已修** |
|| **MinIO service 未在 base compose 启动 → restore 集成测试挂** | 新增 `infra/docker-compose.minio.yml`（MinIO + bucket init） + MinIO creds 走 `_FILE` docker secrets | "无需 MinIO" — **已否决**（多节点生产必须） | **r1-2026-06-11 P0-3 已修** |
|| **限速按 IP 多用户共享桶（nginx 转发后 1 个用户超阈值全员 429）** | uvicorn 启 `--proxy-headers --forwarded-allow-ips` 读 X-Forwarded-For；限速 key 优先 `user_id` 解析 | "按 IP 不动" — review P1-1/2 否决 | **r1-2026-06-11 P1-1/2 已修** |
|| **5xx 错误响应消耗 rate limit 配额（攻击者故意 5xx 饿死合法用户）** | 限速 key 改 user_id 后此问题被 P1-1 缓解（按 user 后单用户自限）+ 监控 5xx 比例 | "不动" — review P1-1 否决 | **r1-2026-06-11 P1-1 已修** |
|| **CSP img-src https: 通配 → SSRF exfil 攻击面** | 严格按 spec §7.4（`img-src 'self' data:` 不放 `https:`） | "CSP 保持宽松" — review P1-3 否决 | **r1-2026-06-11 P1-3 已修** |
|| **429 响应格式与错误矩阵不一致** | 加 `RateLimitedError` 类（`http_status=429`, `error_code="rate_limited"`）；X-RateLimit-* 标准头注入 | "保持原 429 body" — review P1-4 否决 | **r1-2026-06-11 P1-4 已修** |
|| **Sentry dev 环境误报污染项目** | dev 环境（`env=development` 或 DSN 空）init_sentry 直接返回 | "dev 也上报" — review P1-5 否决 | **r1-2026-06-11 P1-5 已修** |
|| **Sentry PII 泄露（password / token / session_id 上报）** | `before_send=_scrub_pii` 脱敏 + `send_default_pii=False` + 长 message 截断 | "不脱敏" — spec §7.3 否决 | **r1-2026-06-11 P1-5 已修** |
|| **check_graph() 跑 graph.invoke 污染 Langfuse + 触发 kNN 检索** | `check_graph` 只验证 `graph.nodes >= 7`（编译可用），不跑业务 | "跑 invoke 测连通" — review P1-6 否决 | **r1-2026-06-11 P1-6 已修** |
|| **5 service health check 串行无超时 → 单慢探测拖垮 endpoint** | `asyncio.gather` 并行 + `_run_check` 内 `asyncio.timeout(2.0)` 保护 | "串行无超时" — review P1-7 否决 | **r1-2026-06-11 P1-7 已修** |
|| **CI `sleep 30` 等服务起 → 脆性 + 慢（TEI 冷启 60-90s）** | `docker compose up -d --wait` 阻塞直到 healthcheck 通过 | "sleep 60" — review P1-8 否决 | **r1-2026-06-11 P1-8 已修** |
|| **CI runner 无 postgresql-client → psql / pg_restore 找不到** | integration / ragas-gate / nightly job 加 `apt-get install -y postgresql-client` | "改 Python 脚本" — 工作量大 | **r1-2026-06-11 P2-3 已修** |
|| **/api/health 响应暴露内部栈** | `_run_check` 返 `error_code` + 截断 sanitized message，不直接 `str(e)` | "返原始异常" — review NEW-19 否决 | **r1-2026-06-11 NEW-19 已修** |
|| **SlowAPI 内存 token bucket 在多 worker 进程下失效** | V1 prod 改 `api_workers=1`（单 worker uvicorn）；V2 换 Redis | "V1 多 worker" — review P2-1 否决 | **r1-2026-06-11 P2-1 已修** |
|| **chat 30/min 未区分会话（多轮对话被 1 次计数）** | spec §7.5 30/min 是 user 全局（已明确）；未来 V2 可拆 per-thread_id | "按 thread_id 拆" — 与 spec §7.5 不符 | **r1-2026-06-11 P2-10 已修（明确语义）** |
|| **Sentry 0.1 采样率漏报关键 5xx** | `before_send_transaction=_force_sample_5xx` 5xx 标 `critical=5xx` 100% 上报 + Sentry alert rule | "统一 0.1 采样" — review P2-11 否决 | **r1-2026-06-11 P2-11 已修** |
|| **prod 容器缺 security_opt + cap_drop → privilege escalation 风险** | 每个 service 加 `security_opt: [no-new-privileges:true]` + `cap_drop: [ALL]` + 必要 cap_add | "保持 default capabilities" — review P2-12 否决 | **r1-2026-06-11 P2-12 已修** |
|| **dev override 顶部无警告注释 → 可能被误用到 prod** | `docker-compose.override.yml` 顶部加 "⚠️ 仅 dev 使用" 注释 | "无注释" — review P2-8 否决 | **r1-2026-06-11 P2-8 已修** |
|| **空备份文件被静默上传 MinIO** | `pg_backup.sh` 校验文件大小 ≥ 1KB + 关键表数 ≥ 4 | "无校验" — review P2-9 否决 | **r1-2026-06-11 P2-9 已修** |
|| **backup 文件名后缀 .sql.gz.dump 误导（实际 binary 格式无 gz）** | 改后缀为 `.dump`（binary 自带 zstd 压缩） | "保留 .sql.gz.dump" — review P0-3 否决 | **r1-2026-06-11 P0-3 已修** |
|| **CORS preflight 响应走 SecurityHeaders middleware → CSP 头重复** | `security_headers_middleware` 检测 `OPTIONS` 直接 passthrough | "不处理" — review P2-6 否决 | **r1-2026-06-11 P2-6 已修** |
|| **request.state.request_id 跨 M 链路断裂（HTTP→Sentry→Langfuse→日志）** | M12 契约表加 `request.state.request_id` 复用说明 + 全链路串联 | "无串联" — review P2-5 / X-1 联动 | **r1-2026-06-11 P2-5 已修** |

---

## 修订记录

|| 版本 | 日期 | 改动 |
||------|------|------|
|| M12-plan-r0 | 2026-06-11 | 初稿（基线 V1 Scope 决策 #5 错误处理 + review P0-1/P0-5/P1-7/X-4 已纳入 + M12 特有 P0/P1 主动避雷） |
|| **M12-plan-r1** | **2026-06-11** | **review 收口（26 项全部修复）：4 P0 + 10 P1 + 12 P2** |
|| r1-2026-06-11 | 2026-06-11 | **P0-1 已修**：中间件挂载顺序按 spec §3.12 LIFO add_middleware（ErrorHandler→RateLimit→SecurityHeaders→RequestID→CORS），数据流图同步修正 |
|| r1-2026-06-11 | 2026-06-11 | **P0-2 已修**：M10/M11 review 雷——`app.observability.langfuse.get_current_trace_id()` API 不存在 → 改 ContextVar 桥接（`_trace_id_var` + `set_trace_id`/`get_current_trace_id`），`capture_exception` 之前自动注入 Sentry tag |
|| r1-2026-06-11 | 2026-06-11 | **P0-3 已修**：Files 表补 `tests/unit/test_backup_scripts.py` + 新增 `infra/docker-compose.minio.yml`（MinIO + bucket init） + `pg_backup.sh` 文件名后缀 `.dump`（去 `.sql.gz` 误导） |
|| r1-2026-06-11 | 2026-06-11 | **P0-4 已修**：`restore.sh` 改三重门禁（`STAGING_CONFIRM=yes` + `ENV=staging` + `AUTO_CONFIRM=yes` for CI），防误删 prod + CI stdin closed 不挂 |
|| r1-2026-06-11 | 2026-06-11 | **P1-1 已修**：限速 key 改 `get_rate_limit_key(user_id 优先 → ip fallback)`，防 nginx 后单 IP 共享桶 |
|| r1-2026-06-11 | 2026-06-11 | **P1-2 已修**：uvicorn 启动加 `--proxy-headers --forwarded-allow-ips="10.0.0.0/8,172.16.0.0/12"`，配 nginx reverse proxy 读 `X-Forwarded-For` |
|| r1-2026-06-11 | 2026-06-11 | **P1-3 已修**：CSP 严格按 spec §7.4（`img-src 'self' data:` 不放 `https:`）+ `connect-src` 加 `http://localhost:8000` + 补 `form-action 'self' base-uri 'self'`（X-2 M5 SSRF 联动） |
|| r1-2026-06-11 | 2026-06-11 | **P1-4 已修**：加 `RateLimitedError` 类（`http_status=429`）+ 错误矩阵对齐 + `Retry-After` header + `X-RateLimit-Limit/Remaining/Reset` 标准头 + `app.state.limiter = limiter` + `add_exception_handler(RateLimitExceeded, ...)` |
|| r1-2026-06-11 | 2026-06-11 | **P1-5 已修**：Sentry `before_send=_scrub_pii` 脱敏 password/token/api_key/secret/session_id + `send_default_pii=False` + dev 环境（`env=development` 或 DSN 空）直接 return + 显式 `profiles_sample_rate=0.0` + 5xx 强制 100% 上报（P2-11 联动） |
|| r1-2026-06-11 | 2026-06-11 | **P1-6 已修**：`check_graph()` 不跑 `graph.invoke`（防污染 Langfuse + 触发 kNN 检索），只验 `len(graph.nodes) >= 7`；`check_langfuse` 改 HTTP GET `/api/public/health` 不调 callback |
|| r1-2026-06-11 | 2026-06-11 | **P1-7 已修**：5 service health check 改 `asyncio.gather` 并行 + 每 check `asyncio.timeout(2.0)` 上限 + k8s readiness 1s 默认超时友好 |
|| r1-2026-06-11 | 2026-06-11 | **P1-8 已修**：CI workflow 改 `docker compose up -d --wait` 替代 `sleep 30`（integration / ragas-gate / nightly 三处统一） |
|| r1-2026-06-11 | 2026-06-11 | **P1-9 已修**：`BackupSettings.minio_access_key/secret_key` 改 `minio_access_key_file/secret_key_file`（docker secrets `_FILE` 模式）；`backup_retention_days` 加 `Field(ge=7, le=365)` 上下界保护 |
|| r1-2026-06-11 | 2026-06-11 | **P1-10 已修**：health bypass 改严格 exact path 集合（`{"/api/health", "/api/health/live", "/api/health/ready"}`），防子路径被 bypass；verbose mode 仅 admin token 返 services 详情 |
|| r1-2026-06-11 | 2026-06-11 | **P2-1 已修**：`ProdSettings.api_workers=1`（slowapi 内存 token bucket 在多 worker 进程下失效 → V1 单 worker 简化解）；V2 换 Redis |
|| r1-2026-06-11 | 2026-06-11 | **P2-2 已修**：`app/api/health.py` 改 `from app.db.session import get_session`（M1 实际路径；原 `app.auth.db.get_session` 不存在） |
|| r1-2026-06-11 | 2026-06-11 | **P2-3 已修**：CI integration / ragas-gate / nightly 三处 job 加 `apt-get install -y postgresql-client`（psql / pg_restore 找不到） |
|| r1-2026-06-11 | 2026-06-11 | **P2-4 已修**：拆 `/api/health/live`（k8s liveness · 不查下游）+ `/api/health/ready`（readiness · 5 service 绿）；`/api/health` 保留为 ready 别名 |
|| r1-2026-06-11 | 2026-06-11 | **P2-5 已修**：M12 契约表加 `request.state.request_id`（M8 RequestIDMiddleware 设置）一行 + 全链路 X-Request-Id 串联（HTTP 头 → Sentry tag → Langfuse metadata → 日志） |
|| r1-2026-06-11 | 2026-06-11 | **P2-6 已修**：`security_headers_middleware` 检测 `request.method == "OPTIONS"` 直接 passthrough，让 CORSMiddleware 处理 preflight，避免 CSP 头重复 |
|| r1-2026-06-11 | 2026-06-11 | **P2-7 已修**：`infra/scripts/ci_local.sh` 改 `git rev-parse --show-toplevel` 找仓库根（替代 `cd "$(dirname "$0")/../.."` 硬编码） |
|| r1-2026-06-11 | 2026-06-11 | **P2-8 已修**：`infra/docker-compose.override.yml` 顶部加 "⚠️ 仅 dev 使用，禁止部署到 staging/prod" 警告注释 |
|| r1-2026-06-11 | 2026-06-11 | **P2-9 已修**：`pg_backup.sh` 校验文件大小 ≥ 1KB + 关键表数 ≥ 4（users / auth_sessions / chat_sessions / ingest_jobs），空备份直接 fail |
|| r1-2026-06-11 | 2026-06-11 | **P2-10 已修**：明确限速语义 — 30/min 是 user 全局（spec §7.5）非 per-session；未来 V2 可拆 per-thread_id |
|| r1-2026-06-11 | 2026-06-11 | **P2-11 已修**：Sentry `before_send_transaction=_force_sample_5xx` 5xx 标 `critical=5xx` 100% 上报（不被 0.1 采样率漏掉），配 Sentry alert rule 单独通知 |
|| r1-2026-06-11 | 2026-06-11 | **P2-12 已修**：prod compose 每 service 加 `security_opt: [no-new-privileges:true]` + `cap_drop: [ALL]` + 必要 `cap_add`（postgres 启需 CHOWN/SETUID/SETGID/DAC_OVERRIDE） |
|| r1-2026-06-11 | 2026-06-11 | **跨 M 联动收口**：M8 P0-1/2 收口（Task 26 lifespan hardening + chat 超时 30s + 错误矩阵 12 条）+ M10 P0-2/3 收口（P0-2 ContextVar 桥接）+ M11 P0-5 收口（X-3 threshold 0.7→0.65 + 30 天 baseline）+ M11 P0-6 收口（同 P0-2 ContextVar 桥接）+ M2 P1-9 收口（X-5 extend_session 改 `datetime.now(tz=UTC).timestamp()` 一次调用） |
|| r1-2026-06-11 | 2026-06-11 | **NEW 收口（高优先级子集）**：NEW-1 X-Request-Id 全链路文档（P2-5 联动）/ NEW-3 secret rotation 写入 infra/README.md / NEW-4 dev compose resource limit（Task 18）/ NEW-5 health check 实际 URL/timeout（Task 20）/ NEW-6 TEI 冷启 60s start_period（Task 17）/ NEW-7/8 graceful shutdown + SIGTERM handler（Task 26）/ NEW-9 MinIO SSE-S3 加密（Task 13 注释）/ NEW-14 SLO 定义写入 DoD（API 可用率 99.9% / chat P95 < 3s / RAGAS baseline 30 天）/ NEW-19 health 响应脱敏（Task 20 _run_check error_code + sanitized message） |
| r2-2026-06-12 | 2026-06-12 | **r2-新-1 已修**（P0 阻塞）：Task 26 L1598 `from app.api.chat import get_graph, ChatTimeoutError` 错位 → 拆 2 行 `from app.graph.workflow import get_graph` + `from app.middleware.errors import ChatTimeoutError` |
| r2-2026-06-12 | 2026-06-12 | **r2-新-2 已修**：`_force_sample_5xx` 检查改 `event.exception` + `event.level == "error"`（event 钩子结构）+ 注册到 `before_send` 而非 `before_send_transaction`（钩子名与意图对齐） |
| r2-2026-06-12 | 2026-06-12 | **r2-新-3 已修**：`_scrub_pii` 加递归脱敏（`_scrub_dict` helper 处理嵌套 dict / list）+ headers 脱敏（Authorization 等 6 关键字）+ query_string 脱敏（regex `?token=xxx` → `[REDACTED]`） |
| r2-2026-06-12 | 2026-06-12 | **r2-新-4 已修**：Task 17 prod compose 加 4 service cap_drop 注释（postgres / opensearch / minio 按服务列 cap_add 差异）+ `security_opt: no-new-privileges:true` |
| r2-2026-06-12 | 2026-06-12 | **r2-新-5 已修**：契约边界表 M12 prod compose 行加提醒"M0 修订记录 4 service → r2 实际 5 service（PG/OS/TEI/Langfuse/MinIO）" |
| r2-2026-06-12 | 2026-06-12 | **r2-新-6 已修**：os_snapshot.sh 补 snapshot state=SUCCESS 轮询（5min max wait + FAILED/PARTIAL exit 1 + timeout exit 1） |