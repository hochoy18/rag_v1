# M6 Plan · Ingest Confluence Source（子页 BFS + 附件抓取）

> 所属：RAG V1 M0–M12 实施路线 · 第 6 步
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §3.1 数据流](../specs/2026-06-10-rag-v1-scope.md#3-数据流) · [§5 错误矩阵](../specs/2026-06-10-rag-v1-scope.md#5-错误矩阵) · [§8.2 依赖清单](../specs/2026-06-10-rag-v1-scope.md#8-依赖版本清单) · [决策总表 #19](../specs/2026-06-10-rag-v1-scope.md#0-决策总表)
> Review 约束：[P0-5 真 PG 集成测试](../specs/../plans/2026-06-11-rag-plans-review.md#p0-5--m1-task-2-单元测试用-sqlite但生产用-pg) · [P1-5 payload_hash UNIQUE](../specs/../plans/2026-06-11-rag-plans-review.md#p1-5--m1-ingest_jobs_payload_hash-缺-unique-约束) · [M6 独立 review](../specs/../plans/reviews/2026-06-11-rag-m6-ingest-confluence-review.md)（3 P0 + 11 P1 + 9 P2）
> 估时：**7-8 个工作日**（r1 修订：原 5d 估时偏紧，按 review P2-3 拆分后上调 2-3d）
> 上游：M0 infra · M1 schema · M3 TEI · M4 pipeline · M5 错误处理模式
> 下游：M8 `/api/ingest` 路由 · V1.1 整 space CQL 抓取

---

## Goal

把 v1-scope 决策 #19 落成可执行代码契约：

1. **Confluence v2 REST 客户端**`app/ingest/sources/confluence.py`：单 page / 子页 BFS / attachments 三类资源抓取
2. **Cloud Basic auth**：email + API token，构造 `httpx.BasicAuth(email, api_token)`
3. **子页 BFS 递归**：`GET /wiki/api/v2/pages/{id}/children`，max depth 可配（V1 范围 = 子树；整 space 推 V1.1）
4. **附件下载**：`GET /wiki/api/v2/pages/{id}/attachments` 拿元数据，`GET /wiki/api/v2/attachments/{id}/download` 流式写盘，> 50MB 跳过；**Content-Type 白名单过滤**（review P0-2：非 `text/*` / `application/pdf` / `image/*` / Office 文档等可索引类型直接 skip）
5. **并发控制**：page GET `semaphore(5)` + 429 指数退避（重试 3 次后跳过）；**附件下载独立 `download_semaphore(2)` + `download_timeout(120s)`**（review P0-3：与 page GET 隔离，避免慢连接挂死 BFS）
6. **权限处理**：401/403 抛 `PermissionDeniedError`（typed 异常，review P1-11），BFS 跳过该 page，记入任务报告统计
7. **复用 M4 pipeline**：元素分类（NarrativeText / Table / Image）走 `pipeline.process_elements()`，`payload_hash = sha256(space_key + root_page_id + auth_email + user_id)` 实现幂等（review P0-1：必须含 user_id，跨用户不同 hash）
8. **集成入口**：`ingest_confluence(space_key, page_id, auth, user_id, *, max_depth=3) -> IngestReport`，`auth` 是 **Pydantic BaseModel**（review P1-9：M8 路由可直接 `ConfluenceAuth(**payload["auth"])` 反序列化），M8 直接调
9. **元数据完整**：page `labels` / `version` / `last_modified_by` / `last_modified_at`（review P1-1/P1-2：M7 retrieval 过滤与 V1.1 增量同步基础）
10. **BFS visited 持久化**：中断恢复 `data/confluence_bfs_visited.json`（review P1-3：200+ 页大子树中断后无需全量重跑）
11. **Confluence macro 解析**：`<ac:structured-macro ac:name="code">` 内 `<ac:plain-text-body>` 文本保留（review P1-10：避免代码块内容丢失）
12. **分页 _links.next 格式兼容**：相对路径 / 完整 URL / `start-limit` / cursor 四种（review P1-7：不同 Cloud 版本差异防御）
13. **附件去重**：单次 ingest 内同一 `att_id` 只下载一次（review P1-8：避免 10 个 page 引用同一 logo 重复下载）
14. **IngestReport 完整字段**：`pages_discovered` / `chunks_count` / `duration_seconds` / `skipped_content_type` / `attachments_deduplicated`（review P2-5：M8 进度查询需要）

**不包含**（其他 M / 后续版本负责）：
- 整 space CQL 抓取（V1.1）
- 附件解析（PDF/DOCX → text）走 M4 splitter，M6 只负责"下载到本地 + 标记元数据"
- `/api/ingest` 路由（M8）
- Confluence Server / DC 兼容（V1 只 Cloud）
- Confluence 非 code macro（jira / chart / expand 等）解析（V1.1）

**r2 跨 M 联动消化清单**（M5 r2 NP-5 / M5 r2 NP-3 / M4 r2 P1-6 同步）：
- **M5 r2 NP-5 异常类收口**：M6 复用 M5 修复路径，所有 Confluence 异常类统一在 `app/ingest/exceptions.py` 定义（M5 r2 已迁 `URLFormatError` / `UnsafeURLError` / `RetryableHTTPError`，M6 r2 追加 5+1 个 Confluence 相关类）。后续 M7/M8/M9 复用时基类一致
- **M5 r2 NP-3 SSRF 防御复用**：M6 r2 显式 `from app.ingest.sources.url import assert_safe_url, validate_url_format, load_auth_config` 并在 `ConfluenceClient.__init__` 启动校验 base_url；DoD 标注 SSRF 防御点
- **M4 r2 P1-6 `app/ingest/exceptions.py` 复用**：M4 已建 `IngestError` / `OversizedFileError` / `UnsupportedFileTypeError` / `ParseError`；M6 复用 `IngestError` 作根基类 + `OversizedPageError` 继承 `OversizedFileError`
- **M4 r2 22 项待续 → M6 r2 NP-E**：M4 splitter 上游 page body 25MB 限制在 M6 client 入口检查，避免 M4 splitter 收到 25MB HTML 后才报错
- **M5 r2 NP-2 4 auth 模式**：M6 决策 V1 只支持 Confluence Cloud Basic auth（email+api_token），与 M5 4 auth 模式（basic/bearer/digest/oauth）显式解耦；若 V1.1 加 Confluence Server OAuth 需重审 M5 auth 模式

---

## Architecture

### 仓库布局（apps/rag_v1/，M6 涉及范围）

```
apps/rag_v1/
├── app/
│   ├── ingest/
│   │   ├── sources/
│   │   │   ├── file.py              # M4（已建）
│   │   │   ├── url.py               # M5（已建）
│   │   │   └── confluence.py        # M6 ★
│   │   ├── exceptions.py            # M4 已建；r2 NP-A M6 追加 5 个异常类
│   │   ├── auth.py                  # M5（已有 http 重试模式可借鉴；M6 复用 assert_safe_url 防 SSRF，r2 NP-D 显式 import）
│   │   ├── pipeline.py              # M4 共用：process_elements() + process_confluence_page() 钩子
│   │   ├── splitter.py              # M4 共用
│   │   └── __init__.py
│   └── config.py                    # 追加 ConfluenceSettings（含 r2 NP-E max_page_body_bytes）

├── tests/
│   ├── unit/
│   │   ├── test_ingest_confluence.py    # M6 ★
│   │   ├── test_confluence_bfs.py       # M6 ★
│   │   ├── test_confluence_auth.py      # M6 ★ 401/403/429/50MB
│   │   └── test_confluence_attachments.py # M6 ★
│   └── integration/
│       └── test_m6_ingest_confluence.py # M6 ★ 真 PG + mock Confluence server
│
├── infra/
│   └── mock_confluence_fixtures/   # M6 ★（review P2-2：统一命名） 测试用 mock server 静态 fixtures
│       ├── pages/
│       │   ├── root.json
│       │   ├── child_1.json
│       │   └── child_2_with_attach.json
│       ├── attachments/
│       │   ├── small.pdf
│       │   ├── logo.png            # 触发 P1-8 去重测试
│       │   ├── executable.exe      # 触发 P0-2 Content-Type 过滤
│       │   └── large_60mb.bin      # 触发 50MB 跳过逻辑
│       └── README.md               # 启动方式：`python -m http.server 9999 -d apps/rag_v1/infra/mock_confluence_fixtures`
│
└── pyproject.toml                   # 追加 llama-index-readers-confluence / respx / testcontainers[postgresql]（review P2-6/P2-8）
```

### M6 模块树

```
apps/rag_v1/
├── app/
│   ├── ingest/
│   │   ├── sources/
│   │   │   └── confluence.py
│   │   │       ├── class ConfluenceSettings           # base_url / max_depth / max_attachment_bytes / concurrency / retry / download_concurrency / download_timeout_seconds / bfs_visited_file / max_page_body_bytes (r2 NP-E) / page_body_read_timeout_seconds (r2 NP-E)
│   │   │       ├── class ConfluenceAuth               # Pydantic BaseModel（review P1-9） email + api_token → httpx.BasicAuth
│   │   │       ├── class ConfluenceClient             # httpx.AsyncClient 封装（独立 download_semaphore + download_timeout，review P0-3）
│   │   │       │   ├── async get_page(page_id, *, body_format="storage")  # r2 NP-E：检查 body 25MB 限制抛 OversizedPageError
│   │   │       │   ├── async list_children(page_id) → AsyncIterator[dict]（review P1-7：分页 _links.next 4 种格式兼容 + r2 NP-B start-limit 抛 ConfluenceAPIError 终止）
│   │   │       │   ├── async list_attachments(page_id) → AsyncIterator[dict]（review P0-2：Content-Type 白名单过滤）
│   │   │       │   ├── async download_attachment(att_id) → AsyncIterator[bytes]  # 流式 + 去重（review P1-8）
│   │   │       │   └── @tenacity.retry 429 → exponential backoff
│   │   │       ├── async def bfs_subtree(root_page_id, *, max_depth=3) → list[PageNode]（review P1-3 JSON 持久化 + P1-4 deque 注释 + P1-5 max_depth=None + P2-9 404 + r2 NP-E OversizedPageError）
│   │   │       ├── async def fetch_with_attachments(...) → list[Document]
│   │   │       ├── def process_confluence_page(page_body_html, meta) → list[Element]（review P1-10 macro 提取 + P1-6 fallback 元素分类 + BeautifulSoup）
│   │   │       └── async def ingest_confluence(space_key, page_id, auth, user_id, *, max_depth=3) → IngestReport
│   │   ├── exceptions.py                             # M4 已建；r2 NP-A M6 追加 5 个异常类（ConfluenceError / PermissionDeniedError / PageNotFoundError / ConfluenceServerError / ConfluenceAPIError / OversizedPageError）
│   │   └── ...                                       # M4 已有
│   └── config.py                                     # 追加 ConfluenceSettings

└── tests/
    ├── unit/
    │   ├── test_ingest_confluence.py          # auth Pydantic / 构造 / 配置 / 入口签名 / payload_hash user_id
    │   ├── test_confluence_bfs.py             # 深度限制 / 循环引用 / 并发 / max_depth=None / 404 / visited 持久化 / r2 NP-B start-limit
    │   ├── test_confluence_auth.py            # 401/403 跳过 / 429 退避 / 50MB 跳过 / typed PermissionDeniedError
    │   └── test_confluence_attachments.py     # 下载 / 大小检查 / 流式写盘 / Content-Type 过滤 / 去重 / r2 NP-E 25MB page body
    └── integration/
        └── test_m6_ingest_confluence.py       # 真 PG（testcontainers）+ mock server
```

**r2 NP-F 修订**：原 `app/ingest/visited_store.py` + `tests/unit/test_confluence_visited_store.py` 删（BFS 用 JSON 路径，SqliteVisitedStore 是死代码）。

### M6 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M8 `/api/ingest` 路由 | `ingest_confluence(space_key, page_id, auth, user_id, *, max_depth)` | 入口唯一公开函数；`auth` 是 Pydantic `ConfluenceAuth`（review P1-9） |
| M7 retrieval | M6 写入 `chunks` 表后由 M7 upsert 到 OpenSearch | M6 不直连 OpenSearch |
| V1.1 整 space CQL | 复用 `ConfluenceClient` + `fetch_with_attachments`，加 `cql_search` 方法 | M6 不实现 CQL |
| M4 pipeline | `pipeline.process_elements(elements, source_meta)` + `process_confluence_page(page_data, meta) -> list[Element]` | M6 把 Confluence body 解析为 elements 再喂入 |
| M1 schema | `ingest_jobs.payload_hash` UNIQUE（review P1-5）+ `chunks` 表 | M6 写入依赖 M1 schema 落地 |
| M3 TEI | `TEIEmbedder`（M4 pipeline 内调） | M3 review P0-3 `EmbeddingDimMismatch` 硬断言对接 |
| M5 auth | 复用 `app/ingest/sources.url:assert_safe_url` / `validate_url_format` / `load_auth_config`（r2 NP-D 显式 import + ConfluenceClient.__init__ 启动校验） | review 模式一致 |
| M0 healthcheck | M0 容器就绪后 M6 集成测试可启 | 跨 M 顺序 |

**契约边界补充（M6 → M4，review P1-6）**：
- M6 产 Element 列表格式：`list[Element]`（dict，含 `type` / `text` / `metadata` 字段）—— 与 M4 plan `process_elements` 入参对齐
- M6 自带 fallback 元素分类器（BeautifulSoup 解析 `<p>` / `<table>` / `<ac:image>` / `<ac:structured-macro ac:name="code">` 规则），不与 M4 元素分类强耦合
- 若 M4 plan 未实现 `process_confluence_page` 钩子，M6 在 `app/ingest/sources/confluence.py` 内部 fallback 用 BeautifulSoup 自解析（不阻塞 M6 工期）

### Confluence v2 REST 端点（决策 #19 锁定）

```
GET  /wiki/api/v2/pages/{id}                       # 单 page 元数据 + body
GET  /wiki/api/v2/pages/{id}/children              # 子页列表（分页 cursor / 兼容 _links.next 4 种格式，review P1-7）
GET  /wiki/api/v2/pages/{id}/attachments           # 附件元数据（metadata.mediaType 用于 Content-Type 过滤，review P0-2）
GET  /wiki/api/v2/attachments/{id}/download        # 附件二进制流式下载（独立 download_semaphore + download_timeout，review P0-3）
```

**关键 header**：`Authorization: Basic base64(email:api_token)`（httpx.BasicAuth 自动处理）

**body format**：默认 `storage`（HTML-like），元素分类阶段在 M6 `process_confluence_page` 内完成（review P1-6：自带 fallback 元素分类，不依赖 M4）

---

## Tech Stack

| 层 | 选型 | 版本（精确） |
|----|------|------------|
| Confluence reader | `llama-index-readers-confluence` | `==0.4.4`（决策 #19 锁定；review P2-1：仅类型/兼容性参考，主体自建 client 不 import） |
| HTTP | `httpx` | `>=0.27,<1`（M3/M5 已用，M6 复用） |
| 重试 | `tenacity` | `>=8.3,<10` |
| 并发控制 | `asyncio.Semaphore` | stdlib |
| 配置 | `pydantic-settings` | `>=2.3,<3` |
| Pydantic | `pydantic` | `>=2.5,<3`（review P1-9：`ConfluenceAuth` 用 `BaseModel` + `SecretStr`） |
| Mock server | `pytest-httpserver`（开发期） | dev 依赖 |
| 集成测试 PG | `testcontainers[postgresql]` | `>=4.0,<5`（review P0-5 强制 / P2-6 依赖） |
| Mock HTTP | `respx` / `pytest-httpx` | dev 依赖 |
| 哈希 | `hashlib`（sha256） | stdlib |
| HTML 解析 | `beautifulsoup4` | `>=4.12,<5`（review P1-6/P1-10：BeautifulSoup 解析 Confluence storage） |
| 测试 | `pytest` / `pytest-asyncio` | dev 依赖 |

**关键导入路径**（review P2-1：`ConfluenceReader` 仅 `TYPE_CHECKING` 引用 + r2 NP-A 异常类统一 + r2 NP-D M5 复用接口显式 import）：

```python
# Confluence reader 仅类型/兼容性参考
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llama_index.readers.confluence import ConfluenceReader  # noqa: F401

# HTTP / 重试
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# 异步工具
import asyncio
import hashlib
import json
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

# Pydantic
from pydantic import BaseModel, SecretStr

# HTML 解析
from bs4 import BeautifulSoup

# r2 NP-A：异常类统一在 app/ingest/exceptions.py 定义（M4 已建；M5 r2 NP-5 + M6 r2 同步追加）
from app.ingest.exceptions import (
    IngestError,                    # M4 exceptions.py 基类
    OversizedFileError,             # M4 P1-6，r2 NP-E 复用
    ConfluenceError,                # M6 异常基类
    PermissionDeniedError,          # 401/403
    PageNotFoundError,              # 404
    ConfluenceServerError,          # 5xx
    ConfluenceAPIError,             # 其他 4xx / v2 不支持 start-limit 抛错
    OversizedPageError,             # r2 NP-E：page body > 25MB
)

# r2 NP-D：M5 复用接口显式 import（M5 r2 NP-3 同步；不写"复用"未真 import 同类错重蹈）
from app.ingest.sources.url import (
    assert_safe_url,                # M5 SSRF 防御；M6 ConfluenceClient.__init__ 启动校验 base_url
    validate_url_format,            # M5 URL 格式校验
    load_auth_config,               # M5 通用 auth 加载
)
```

**为什么不直接用 `ConfluenceReader`**（review P2-1）：
- 该库主要支持 v1 REST API + Cloud OAuth，v2 REST 字段差异大
- 需要精细控制 401/403/429/50MB/Content-Type 的错误分支
- BFS 深度限制、并发数要在 client 层做
- M6 自建 client 与 `ConfluenceReader` 同时 import 会创建 2 个 `httpx.AsyncClient`、2 套 auth 逻辑
- 主体自建，类型注释 `TYPE_CHECKING` 引用避免运行时冲突

---

## Files

**新增**（9 个源文件 + 5 个测试文件 + 1 个 mock 资源目录）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
| `app/ingest/sources/confluence.py` | Confluence v2 REST 客户端 + BFS + ingest 入口（review P0-1/P0-2/P0-3/P1-1~11 全部落地 + r2 NP-A~F 修复） |
| `app/ingest/sources/__init__.py` | 暴露 `ingest_confluence` |
| `app/ingest/exceptions.py` | r2 NP-A 统一异常类入口（追加 `ConfluenceError` / `PermissionDeniedError` / `PageNotFoundError` / `ConfluenceServerError` / `ConfluenceAPIError` / `OversizedPageError`） |
| `tests/unit/test_ingest_confluence.py` | 入口函数签名 / 配置 / auth 构造 / payload_hash 含 user_id / process_confluence_page |
| `tests/unit/test_confluence_bfs.py` | 子页 BFS（深度 / 循环引用 / 并发 / max_depth=None / 404 / visited 恢复 / r2 NP-B start-limit 抛错） |
| `tests/unit/test_confluence_auth.py` | 401/403/429/50MB 错误矩阵 + typed PermissionDeniedError |
| `tests/unit/test_confluence_attachments.py` | 附件下载 / 流式写盘 / Content-Type 过滤 / 去重 / r2 NP-E 25MB page body 跳过 |
| `tests/integration/test_m6_ingest_confluence.py` | 真 PG（testcontainers）+ mock Confluence |
| `infra/mock_confluence_fixtures/` | 静态 fixtures（root/child/attachments，含 exe 触发 Content-Type 过滤） |

**删除**（r2 NP-F 方案 A）：
- `app/ingest/visited_store.py` — SqliteVisitedStore 是死代码，BFS 实际用 JSON 路径
- `tests/unit/test_confluence_visited_store.py` — 对应单测

**修改**：
- `pyproject.toml`：完整 toml 片段追加（review P2-6/P2-8）：
  ```toml
  dependencies = [
    # ... M0-M5 已有 ...
    "llama-index-readers-confluence==0.4.4",
    "beautifulsoup4>=4.12,<5",
    "pydantic>=2.5,<3",
  ]
  [project.optional-dependencies]
  dev = [
    # ... M0-M5 已有 ...
    "respx>=0.21",
    "pytest-httpserver>=1.1,<2",
    "testcontainers[postgresql]>=4.0,<5",
  ]
  ```
- `app/config.py`：追加 `ConfluenceSettings`：
  - `base_url: HttpUrl` 默认 `https://your-domain.atlassian.net`
  - `max_depth: int = 3`
  - `max_attachment_bytes: int = 52428800`（50MB）
  - `concurrency: int = 5`
  - `max_retries: int = 3`
  - **`download_concurrency: int = 2`**（review P0-3，独立 semaphore）
  - **`download_timeout_seconds: int = 120`**（review P0-3，独立 timeout）
  - **`bfs_visited_file: str = "data/confluence_bfs_visited.json"`**（review P1-3，持久化路径）
  - **`max_page_body_bytes: int = 26214400`**（r2 NP-E，25MB Confluence Cloud 单 page body 上限）
  - **`page_body_read_timeout_seconds: int = 60`**（r2 NP-E，独立 read timeout 防慢连接挂死）
- `app/ingest/__init__.py`：导出 `ingest_confluence`
- `app/ingest/pipeline.py`（M4）：补 `process_confluence_page(page_data, meta) -> list[Element]` 钩子（M6 用，含 review P1-6 fallback 元素分类 + P1-10 macro 提取）
- `app/ingest/sources/confluence.py` 不 import `ConfluenceReader`（review P2-1）

**不修改**：`infra/docker-compose.yml`、M0/M1/M2/M3 已有文件

---

## Tasks（2-5 分钟/step 粒度，7-8 个工作日排程，review P2-3 估时拆分）

### Day 1（reader 骨架 + Basic auth + 单 page）

#### Task 1：ConfluenceSettings 配置块

**RED** · `tests/unit/test_ingest_confluence.py::test_confluence_config_loads`
- mock env vars `CONFLUENCE_BASE_URL=https://test.atlassian.net` / `CONFLUENCE_MAX_DEPTH=5` / `CONFLUENCE_MAX_ATTACHMENT_BYTES=104857600` / **`CONFLUENCE_DOWNLOAD_CONCURRENCY=2`**（review P0-3） / **`CONFLUENCE_BFS_VISITED_FILE=data/bfs.json`**（review P1-3）
- 调 `Settings().confluence` → 断言 5 字段全等
- 跑测试 → 失败
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_ingest_confluence.py::test_confluence_config_loads`

**GREEN** · 改 `app/config.py`：
- 新增 `ConfluenceSettings`：`base_url: HttpUrl` / `max_depth: int = 3` / `max_attachment_bytes: int = 52428800`（50MB） / `concurrency: int = 5` / `max_retries: int = 3` / **`download_concurrency: int = 2`** / **`download_timeout_seconds: int = 120`** / **`bfs_visited_file: str = "data/confluence_bfs_visited.json"`** / **`max_page_body_bytes: int = 26214400`**（r2 NP-E，25MB） / **`page_body_read_timeout_seconds: int = 60`**（r2 NP-E）
- 顶层 `Settings` 聚合

**REFACTOR** · 把 `ConfluenceSettings` 拆 `app/configs/confluence.py`（review X-1 跨 M config 拆分建议）

#### Task 2：ConfluenceAuth（Pydantic BaseModel，review P1-9）

**RED** · `test_ingest_confluence.py::test_auth_builds_basic_auth_header`
- `auth = ConfluenceAuth(email="user@test.com", api_token="tok-123")`
- 断言 `auth.to_httpx() == httpx.BasicAuth("user@test.com", "tok-123")`
- 跑测试 → 失败

**GREEN** · `class ConfluenceAuth(BaseModel)`（review P1-9：必须 Pydantic，M8 路由可 `ConfluenceAuth(**payload["auth"])`）：
```python
from pydantic import BaseModel, SecretStr
import httpx

class ConfluenceAuth(BaseModel):
    """Confluence Cloud Basic auth（email + API token）。
    
    Pydantic BaseModel：M8 路由可 `ConfluenceAuth(**payload["auth"])` 反序列化（review P1-9）。
    """
    email: str
    api_token: SecretStr
    
    def to_httpx(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(self.email, self.api_token.get_secret_value())
```

**RED** · `test_ingest_confluence.py::test_auth_redacts_token_in_repr`
- 断言 `repr(auth)` 不含 `"tok-123"` 字面量
- 跑测试 → 失败

**GREEN** · `__repr__` 返回 `"ConfluenceAuth(email='user@test.com', api_token='***')"`

**RED** · `test_ingest_confluence.py::test_auth_is_pydantic_model`（review P1-9 新增）
- 断言 `isinstance(auth, BaseModel)` 且 `auth.model_dump()["email"] == "user@test.com"`
- 跑测试 → 失败

#### Task 3：ConfluenceClient 骨架 + 单 page GET（review P0-3 独立 timeout + P1-11 typed 异常）

**RED** · `test_ingest_confluence.py::test_get_page_returns_dict`
- `respx_mock.get("https://test.atlassian.net/wiki/api/v2/pages/123").mock(return_value=httpx.Response(200, json={...}))`
- 调 `await client.get_page(123)` → 断言返回 dict 含 `id=123`
- 跑测试 → 失败

**GREEN** · `class ConfluenceClient`（review P0-3 独立 timeout + semaphore + r2 NP-A 异常类统一入口）：
```python
# r2 NP-A：M5 r2 NP-5 + M6 r2 同步，异常类统一在 app/ingest/exceptions.py 定义
from app.ingest.exceptions import (
    IngestError,                    # M4 exceptions.py 基类
    ConfluenceError,                # M6 异常基类
    PermissionDeniedError,          # 401/403
    PageNotFoundError,              # 404
    ConfluenceServerError,          # 5xx
    ConfluenceAPIError,             # 其他 4xx
)
# r2 NP-D：M5 复用接口显式 import（M5 r2 NP-3 同步）
from app.ingest.sources.url import (
    assert_safe_url,                # M5 SSRF 防御
    validate_url_format,            # M5 URL 格式校验
    load_auth_config,               # M5 通用 auth 加载
)

class ConfluenceClient:
    def __init__(self, base_url: str, auth: ConfluenceAuth, settings: ConfluenceSettings):
        # r2 NP-D：启动时校验配置化 base_url（非用户输入也防御）
        assert_safe_url(base_url)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=20.0, read=30.0, write=None, pool=None),  # review P0-3
            auth=auth.to_httpx(),
            follow_redirects=True,  # review P2-4 防御
            max_redirects=3,        # review P2-4
        )
        self._page_semaphore = asyncio.Semaphore(settings.concurrency)        # page GET 用
        self._download_semaphore = asyncio.Semaphore(settings.download_concurrency)  # review P0-3
        self._download_timeout = httpx.Timeout(connect=30.0, read=settings.download_timeout_seconds, write=None, pool=None)  # review P0-3
        # r2 NP-E：page body 25MB 限制，独立 timeout 防慢连接挂死
        self._page_timeout = httpx.Timeout(connect=20.0, read=settings.page_body_read_timeout_seconds, write=None, pool=None)
        self._downloaded_set: set[str] = set()  # review P1-8 附件去重

    async def get_page(self, page_id: int, *, body_format: str = "storage") -> dict:
        async with self._page_semaphore:
            page = await self._request("GET", f"/wiki/api/v2/pages/{page_id}?body-format={body_format}")
            # r2 NP-E：检查 body.storage.value 长度，超过 25MB 抛 OversizedPageError
            body = (page.get("body") or {}).get("storage") or {}
            body_value = body.get("value", "")
            if len(body_value.encode("utf-8")) > self._settings.max_page_body_bytes:
                raise OversizedPageError(
                    page_id=page_id,
                    size_bytes=len(body_value.encode("utf-8")),
                    max_bytes=self._settings.max_page_body_bytes,
                )
            return page

    async def _request(self, method: str, url: str) -> dict:
        resp = await self._client.request(method, url)
        # r2 NP-A：异常类统一从 app.ingest.exceptions import
        if resp.status_code in (401, 403):
            raise PermissionDeniedError(resp.status_code, resp.text)
        if resp.status_code == 404:
            raise PageNotFoundError(url, resp.text)
        if resp.status_code == 429:
            resp.raise_for_status()  # 让 tenacity 捕获
        if 500 <= resp.status_code < 600:
            raise ConfluenceServerError(resp.status_code, resp.text)
        if 400 <= resp.status_code < 500:
            raise ConfluenceAPIError(resp.status_code, resp.text)
        return resp.json()
```

**RED** · `test_get_page_propagates_4xx_as_typed_error`（review P1-11 强化）
- mock 401 响应 → 断言抛 `PermissionDeniedError`（不是通用 `ConfluenceAPIError`）
- 跑测试 → 失败

**GREEN** · 在 `_request` 内分支：`response.status_code in (401, 403)` → 抛 `PermissionDeniedError`；`response.status_code == 404` → 抛 `PageNotFoundError`；其他 4xx → `ConfluenceAPIError`

**RED** · `test_permission_denied_raises_typed_error`（review P1-11 新增）
- 验证 401 抛 `PermissionDeniedError`（不是通用 `ConfluenceAPIError`）
- 跑测试 → 失败

**RED** · `test_404_raises_page_not_found_error`（review P2-9 新增）
- mock 404 → 断言抛 `PageNotFoundError`
- 跑测试 → 失败

---

### Day 2（子页 BFS）

#### Task 4：list_children 分页（review P1-7 _links.next 4 种格式兼容）

**RED** · `test_confluence_bfs.py::test_list_children_paginates_via_cursor`
- mock 两次响应：第一次 `{"results": [page1], "_links": {"next": "/children?cursor=abc"}}` → 第二次 `{"results": [page2]}`
- 调 `async for child in client.list_children(123)` → 断言产出 2 个
- 跑测试 → 失败

**GREEN** · `async def list_children(self, page_id: int) -> AsyncIterator[dict]`（review P1-7 4 种格式兼容 + r2 NP-B 死循环修）：
```python
from app.ingest.exceptions import ConfluenceAPIError  # r2 NP-A 统一异常类入口

async def list_children(self, page_id: int) -> AsyncIterator[dict]:
    base_url = f"/wiki/api/v2/pages/{page_id}/children"
    url: str | None = base_url
    while url:
        resp = await self._request("GET", url)
        data = resp.json()
        for result in data.get("results", []):
            yield result
        # review P1-7 + r2 NP-B：4 种格式防御；start-limit 死循环修
        next_link = (data.get("_links") or {}).get("next")
        if not next_link:
            break
        if next_link.startswith("http"):
            # 完整 URL → 只取 path + query
            parsed = urlparse(next_link)
            query = f"?{parsed.query}" if parsed.query else ""
            next_link = f"{parsed.path}{query}"
        if "start=" in next_link and "limit=" in next_link:
            # r2 NP-B 修：v2 REST 不支持 start/limit 格式（v1 REST 风格）
            # 原代码 `url = base_url` 会丢 cursor 参数死循环
            # 修法：抛 typed 异常终止分页，调用方计入 errors 继续
            raise ConfluenceAPIError(
                f"Confluence v2 API 不支持 start/limit 分页（got {next_link}）；"
                "该 Cloud 版本过旧，建议升级或降级到 v1 REST"
            )
        else:
            url = next_link  # cursor 格式
```

**RED** · `test_list_children_yields_empty_when_no_children`
- mock 响应 `{"results": []}` → 断言生成器立即停止
- 跑测试 → 失败

**GREEN** · 循环条件 `while url` 内 `if not next_link: break`

**RED** · `test_list_children_paginates_via_full_url`（review P1-7 新增）
- mock `_links.next` 为 `https://test.atlassian.net/wiki/api/v2/pages/1/children?cursor=xyz`（完整 URL）
- 断言第二轮请求用 `cursor=xyz` 调通
- 跑测试 → 失败

**RED** · `test_list_children_paginates_via_start_limit`（review P1-7 新增）
- mock `_links.next` 为 `/wiki/api/v2/pages/1/children?start=10&limit=25`（v1 REST 风格）
- 断言能继续分页
- 跑测试 → 失败
- **r2 修订**：原 GREEN 用 `url = base_url` 丢 cursor 死循环（r2 NP-B）；r2 改为抛 `ConfluenceAPIError` 终止，本测试相应改为断言抛 typed 异常

**RED** · `test_list_children_start_limit_raises_error`（r2 NP-B 新增）
- mock `_links.next` 为 `/wiki/api/v2/pages/1/children?start=10&limit=25`
- 调 `async for child in client.list_children(1)` → 断言抛 `ConfluenceAPIError` 而**非**死循环
- 跑测试 → 失败

**RED** · `test_get_page_oversized_body_skipped`（r2 NP-E 新增）
- mock page body `body.storage.value` 长度 = 26MB（> 25MB 限制）
- 调 `await client.get_page(123)` → 断言抛 `OversizedPageError`（继承 `OversizedFileError`）且 `report["oversized_page_bodies"] += 1`
- 跑测试 → 失败

#### Task 5：BFS 递归 + 深度限制（review P1-3 持久化 + P1-4 deque 注释 + P1-5 max_depth=None + P2-9 404）

**RED** · `test_confluence_bfs.py::test_bfs_stops_at_max_depth`
- mock 树：root → child → grandchild（max_depth=1）
- 调 `bfs_subtree(root_id=1, max_depth=1)` → 断言只含 root + child，**不含** grandchild
- 跑测试 → 失败

**GREEN** · `async def bfs_subtree(self, root_page_id, *, max_depth=3) -> list[PageNode]`（review P1-3/P1-4/P1-5/P2-9 全部落地 + r2 NP-A 异常类统一入口）：
```python
# r2 NP-A：异常类统一从 app/ingest/exceptions import
from app.ingest.exceptions import (
    PermissionDeniedError,  # 401/403 → BFS 跳过
    PageNotFoundError,      # 404 → 计入 errors（review P2-9）
    OversizedPageError,     # r2 NP-E：page body > 25MB → 跳过
)
from collections import deque
import json
from pathlib import Path

async def bfs_subtree(
    self,
    root_page_id: int,
    *,
    max_depth: int | None = 3,
    visited_file: str | None = None,
    report: IngestReport | None = None,
) -> list[PageNode]:
    """BFS 子树遍历。
    
    review P1-4：BFS 用 deque + asyncio.Semaphore 控制并发。
    不用 asyncio.Queue——BFS 是单 producer 遍历，deque 更高效。
    并发由 get_page 内的 self._page_semaphore 控制。
    
    review P1-3：visited set 持久化到 visited_file（中断恢复）。
    review P1-5：max_depth=None → float('inf') 不限深度；负数 → ValueError。
    review P2-9：get_page 抛 PageNotFoundError → 计入 errors 继续 BFS。
    """
    # review P1-5 边界处理
    if max_depth is None:
        max_depth = float('inf')
    if max_depth < 0:
        raise ValueError(f"max_depth must be >= 0 or None, got {max_depth}")
    
    # review P1-3 加载已访问
    visited: set[int] = set()
    if visited_file and Path(visited_file).exists():
        visited = set(json.loads(Path(visited_file).read_text()))
    
    nodes: list[PageNode] = []
    try:
        visited.add(root_page_id)
        queue = deque([(root_page_id, 0)])
        while queue:
            pid, depth = queue.popleft()
            try:
                page = await self.get_page(pid)  # 内部 _page_semaphore
            except PermissionDeniedError:
                if report: report["permission_denied_pages"].append(pid)
                continue
            except PageNotFoundError:  # review P2-9
                if report: report["errors"].append(f"page {pid} not found (可能被删除)")
                continue
            except OversizedPageError as e:  # r2 NP-E：25MB 限制
                if report:
                    report["errors"].append(f"page {pid} body too large: {e.size_bytes} > {e.max_bytes}")
                    report["oversized_page_bodies"] += 1
                continue
            nodes.append(PageNode(id=page["id"], title=page["title"],
                                  parent_id=page.get("parent_id"), depth=depth))
            if report: report["pages_discovered"] += 1  # review P2-5
            if depth >= max_depth:
                continue
            async for child in self.list_children(pid):
                if child["id"] not in visited:
                    visited.add(child["id"])
                    queue.append((child["id"], depth + 1))
    finally:
        # review P1-3 持久化
        if visited_file:
            Path(visited_file).parent.mkdir(parents=True, exist_ok=True)
            Path(visited_file).write_text(json.dumps(list(visited)))
    return nodes
```

**RED** · `test_bfs_with_max_depth_none`（review P1-5 新增）
- mock 树：root → child → grandchild
- 调 `bfs_subtree(root_id=1, max_depth=None)` → 断言全 yield 不报错
- 跑测试 → 失败

**RED** · `test_bfs_with_max_depth_0`（review P1-5 新增）
- max_depth=0 → 断言只含 root
- 跑测试 → 失败

**RED** · `test_bfs_with_negative_max_depth_raises`（review P1-5 新增）
- max_depth=-1 → 断言抛 `ValueError`
- 跑测试 → 失败

**RED** · `test_bfs_handles_cycle_without_infinite_loop`
- mock 树：root.children 含 root 本身（异常 fixture）
- 调 `bfs_subtree(root_id=1, max_depth=3)` → 断言返回 1 个节点不崩
- 跑测试 → 失败

**GREEN** · `visited: set[int]` 守护；遇到已 visited 节点 skip

**RED** · `test_bfs_resumes_from_visited_file`（review P1-3 新增）
- 预写 `data/bfs.json` 含 `["2", "3"]`
- 调 `bfs_subtree(root_id=1, visited_file="data/bfs.json")` → 断言不重抓 page 2/3
- 跑测试 → 失败

**RED** · `test_bfs_persists_visited_file`（review P1-3 新增）
- 调 `bfs_subtree(root_id=1, visited_file=tmp_path / "v.json")` 完成后 → 断言文件存在且含所有 visited page_id
- 跑测试 → 失败

**RED** · `test_bfs_skips_404_page_and_continues`（review P2-9 新增）
- mock root 200 / child 404
- 调 `bfs_subtree(...)` → 断言 root 被 yield + child 被跳过 + 不崩
- 跑测试 → 失败

**RED** · `test_bfs_respects_semaphore_concurrency`
- mock 树：root 有 20 个 child，每个 child GET 延时 50ms
- 调 `bfs_subtree(root_id=1, max_depth=1, concurrency=5)` → 断言总耗时 < 250ms（20/5 * 50ms + 开销）
- 跑测试 → 失败

**GREEN** · 在 `bfs_subtree` 内 `sem = asyncio.Semaphore(settings.concurrency)`；每次 `async with sem: await self.get_page(pid)`

---

### Day 3（attachments 抓取 + Content-Type 过滤 + 去重 + 隔离）

#### Task 6：list_attachments 元数据（review P0-2 Content-Type 过滤）

**RED** · `test_confluence_attachments.py::test_list_attachments_returns_metadata`
- mock 响应 `{"results": [{"id": "att-1", "title": "doc.pdf", "metadata": {"size": 1024, "mediaType": "application/pdf"}, "_links": {"download": "/download/att-1"}}]}`
- 调 `async for att in client.list_attachments(123)` → 断言首个 yield 含 `id="att-1"` / `size=1024`
- 跑测试 → 失败

**GREEN** · `async def list_attachments(self, page_id: int) -> AsyncIterator[dict]`（review P0-2 加 Content-Type 过滤）：
```python
INDEXABLE_MIME_PREFIXES = (
    "text/",                                     # txt, csv, html, xml
    "application/pdf",                           # pdf
    "application/vnd.openxmlformats-officedocument.",  # docx/xlsx/pptx
    "application/msword",
    "application/vnd.ms-",
    "image/",                                    # png/jpg/gif/webp
    "message/rfc822",                            # .eml
)

async def list_attachments(self, page_id: int) -> AsyncIterator[dict]:
    url: str | None = f"/wiki/api/v2/pages/{page_id}/attachments"
    while url:
        resp = await self._request("GET", url)
        data = resp.json()
        for att in data.get("results", []):
            mime = (att.get("metadata") or {}).get("mediaType", "")
            if not any(mime.startswith(p) for p in INDEXABLE_MIME_PREFIXES):
                # review P0-2：非可索引类型跳过
                logger.info("skipped non-indexable attachment", extra={
                    "att_id": att["id"], "title": att.get("title"), "mime": mime
                })
                if hasattr(self, '_report') and self._report is not None:
                    self._report["skipped_content_type"] += 1
                continue
            yield att
        next_link = (data.get("_links") or {}).get("next")
        url = next_link if next_link else None
```

**RED** · `test_list_attachments_filters_non_indexable`（review P0-2 新增）
- mock 响应含 `mediaType: "application/x-msdownload"`（exe）和 `mediaType: "application/pdf"`
- 断言只 yield pdf，不 yield exe
- 跑测试 → 失败

#### Task 7：附件下载 + 流式写盘 + 去重（review P0-3 独立 semaphore/timeout + P1-8 去重）

**RED** · `test_confluence_attachments.py::test_download_attachment_streams_to_disk`
- mock 流式响应：分 3 个 chunk（每个 1KB）
- 调 `await client.download_attachment(att_id="att-1", dest_path=tmp_path / "out.bin")` → 断言文件 3KB，**不**一次性加载到内存
- 跑测试 → 失败

**GREEN** · `async def download_attachment(self, *, att_id: str, dest_path: Path) -> int | None`（review P0-3 + P1-8）：
```python
async def download_attachment(self, *, att_id: str, dest_path: Path) -> int | None:
    # review P1-8：附件去重
    if att_id in self._downloaded_set:
        logger.debug("attachment already downloaded in this ingest", extra={"att_id": att_id})
        if hasattr(self, '_report') and self._report is not None:
            self._report["attachments_deduplicated"] += 1
        return 0
    
    # review P0-3：独立 semaphore + timeout，与 page GET 隔离
    async with self._download_semaphore:
        async with self._client.stream(
            "GET",
            f"/wiki/api/v2/attachments/{att_id}/download",
            timeout=self._download_timeout,
        ) as r:
            r.raise_for_status()
            # review P0-2 + P0-3：先检查 Content-Length
            cl = r.headers.get("content-length")
            if cl and int(cl) > self._settings.max_attachment_bytes:
                logger.warning("skipped oversized attachment", extra={"att_id": att_id, "size": cl})
                return None
            total = 0
            async with aiofiles.open(dest_path, "wb") as f:  # 实际用 stdlib
                async for chunk in r.aiter_bytes(chunk_size=65536):
                    await f.write(chunk)
                    total += len(chunk)
                    if total > self._settings.max_attachment_bytes:
                        # 防御性 break
                        dest_path.unlink(missing_ok=True)
                        return None
    
    self._downloaded_set.add(att_id)  # review P1-8
    return total
```

**RED** · `test_download_attachment_returns_byte_count`
- mock 5KB 响应 → 断言返回值 == 5120
- 跑测试 → 失败

**GREEN** · 累加 `chunk_size` 总和返回

**RED** · `test_download_same_attachment_once`（review P1-8 新增）
- 调 `download_attachment(att_id="att-1", ...)` 两次 → 断言只发 1 次 HTTP GET，第二次返回 0
- 跑测试 → 失败

**RED** · `test_download_semaphore_does_not_block_page_fetch`（review P0-3 新增）
- mock 慢下载（200ms 延时）
- 调 `client.get_page(1)` 与 `client.download_attachment(...)` 并发 → 断言 page GET 不被下载阻塞
- 跑测试 → 失败

#### Task 8：> 50MB 跳过（review P0-2 Content-Type 已在 Task 6 处理）

**RED** · `test_confluence_attachments.py::test_skips_attachment_over_max_bytes`
- mock 响应头 `Content-Length: 52428801`（50MB + 1）
- 调 `download_attachment(...)` → 断言**不**写文件 + 返回 `None` + 日志 `"skipped oversized attachment"`
- 跑测试 → 失败

**GREEN** · 在 `download_attachment` 入口检查：
```python
cl = r.headers.get("content-length")
if cl and int(cl) > self._settings.max_attachment_bytes:
    logger.warning("skipped oversized attachment", extra={"att_id": att_id, "size": cl})
    return None
```

**RED** · `test_skips_attachment_when_metadata_size_exceeds_max`
- mock `list_attachments` 返回 metadata `size=104857600`（100MB）→ 断言不调 download
- 跑测试 → 失败

**GREEN** · 在 `fetch_with_attachments` 内：`if att["size"] > settings.max_attachment_bytes: skip + log`

---

### Day 4（错误处理 + 元数据 + 幂等 + 元素分类 + macro 解析）

#### Task 9：401/403 跳过 + 任务报告统计（review P1-11 typed + P2-5 完整字段）

**RED** · `test_confluence_auth.py::test_permission_denied_skips_page_and_continues`
- mock 树：root（200） → child1（401） → child2（200）
- 调 `ingest_confluence(space_key="S", page_id=1, ...)` → 断言 `IngestReport.permission_denied_count == 1` 且 child2 仍被抓取
- 跑测试 → 失败

**GREEN** · 在 `bfs_subtree` 内 `try: page = await self.get_page(pid) except PermissionDeniedError: report["permission_denied_pages"].append(pid); continue`（review P1-11：捕获 typed 异常）
- `IngestReport = TypedDict("IngestReport", {`（review P2-5 完整字段 + r2 NP-E）：
```python
IngestReport = TypedDict("IngestReport", {
    "pages_processed": int,
    "pages_discovered": int,             # review P2-5 BFS 总发现
    "attachments_downloaded": int,
    "attachments_deduplicated": int,     # review P1-8
    "permission_denied_pages": list[int],
    "oversized_skipped": int,
    "oversized_page_bodies": int,        # r2 NP-E：page body > 25MB 计数
    "skipped_content_type": int,         # review P0-2
    "chunks_count": int,                 # review P2-5 写入 chunks 表数
    "errors": list[str],
    "payload_hash": str,
    "duration_seconds": float,           # review P2-5
})
```

**RED** · `test_permission_denied_includes_page_id_in_report`
- 断言 `report["permission_denied_pages"]` 含 `child1.id`
- 跑测试 → 失败

#### Task 10：429 指数退避

**RED** · `test_confluence_auth.py::test_429_triggers_exponential_backoff_and_retries`
- mock 第 1、2 次 429，第 3 次 200
- 用 `freezegun` 或 `monkeypatch` 让 `time.sleep` 不真睡但记录调用
- 调 `await client.get_page(123)` → 断言成功 + `sleep` 被调 2 次 + 间隔分别 ~1s 和 ~2s
- 跑测试 → 失败

**GREEN** · `@tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type(httpx.HTTPStatusError), reraise=True)`
- 在 `_request` 内 `response.raise_for_status()` 前判断 `if response.status_code == 429: response.raise_for_status()`（让 tenacity 捕获）

**RED** · `test_429_gives_up_after_max_retries_and_skips_page`
- mock 持续 429
- 调 `bfs_subtree` → 断言该 page 进入 `errors` 列表 + 不阻塞其他 page
- 跑测试 → 失败

**GREEN** · `except httpx.HTTPStatusError as e: if e.response.status_code == 429: report["errors"].append(f"429 after retries: page {pid}"); continue`

#### Task 11：元数据 + 元素分类（review P1-1 labels + P1-2 version + P1-6 fallback 分类器 + P1-10 macro 提取）

**RED** · `test_ingest_confluence.py::test_metadata_includes_source_and_page_id`
- mock 单 page 抓取 → 断言 `Document.metadata` 含 `source="confluence"` / `page_id=123` / `space_key="S"` / `parent_id=None` / `depth=0`
- 跑测试 → 失败

**GREEN** · `fetch_with_attachments` 内（review P1-1/P1-2 元数据补全）：
```python
meta = {
    "source": "confluence",
    "page_id": page["id"],
    "space_key": space_key,
    "parent_id": page.get("parent_id"),
    "depth": page["depth"],
    "title": page["title"],
    # review P1-1：labels（Confluence 核心分类）
    "labels": [label["name"] for label in page.get("labels", []) or []],
    # review P1-2：version / last_modifier / last_modified_at
    "version": (page.get("version") or {}).get("number"),
    "last_modified_by": (page.get("version") or {}).get("by", {}).get("displayName"),
    "last_modified_at": (page.get("version") or {}).get("when"),
}
if att_path: meta["attachment_filename"] = att_path.name
```

**RED** · `test_metadata_includes_labels`（review P1-1 新增）
- mock page 含 `labels: [{"name": "meeting-notes"}]` → 断言 `meta["labels"] == ["meeting-notes"]`
- 跑测试 → 失败

**RED** · `test_metadata_includes_version`（review P1-2 新增）
- mock page 含 `version: {"number": 5, "by": {"displayName": "Alice"}, "when": "2024-01-01T00:00:00Z"}` → 断言 meta 三字段全等
- 跑测试 → 失败

**RED** · `test_elements_classified_as_narrative_table_image`
- mock page body 含 `<p>` / `<table>` / `<ac:image>` 三种标签
- 调 `process_confluence_page(...)` → 断言 elements 含 `NarrativeText` / `Table` / `Image` 各至少 1
- 跑测试 → 失败

**GREEN** · 在 `app/ingest/pipeline.py` 加（review P1-6 fallback + P1-10 macro 提取）：
```python
from bs4 import BeautifulSoup

def process_confluence_page(page_body_html: str, meta: dict) -> list[Element]:
    """Confluence storage HTML → list[Element]（review P1-6 fallback 元素分类器）。
    
    M6 自带 fallback，不与 M4 元素分类强耦合。
    review P1-10：`<ac:structured-macro ac:name="code">` 内 plain-text-body 文本保留。
    """
    soup = BeautifulSoup(page_body_html, "html.parser")
    elements: list[Element] = []
    
    # review P1-10：code macro 内容保留
    for macro in soup.find_all("ac:structured-macro"):
        if macro.get("ac:name") == "code":
            body = macro.find("ac:plain-text-body")
            if body:
                elements.append({"type": "NarrativeText", "text": body.get_text(strip=True), "metadata": meta})
    
    # 常规三类元素
    for p in soup.find_all("p"):
        elements.append({"type": "NarrativeText", "text": p.get_text(strip=True), "metadata": meta})
    for table in soup.find_all("table"):
        elements.append({"type": "Table", "text": table.get_text(strip=True), "metadata": meta})
    for img in soup.find_all("ac:image"):
        ri = img.find("ri:attachment")
        if ri:
            elements.append({"type": "Image", "text": ri.get("ri:filename", ""), "metadata": meta})
    
    return elements
```

**RED** · `test_process_confluence_page_extracts_code_macro`（review P1-10 新增）
- mock body 含 `<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA[print(1)]]></ac:plain-text-body></ac:structured-macro>`
- 断言 elements 含 `text="print(1)"`
- 跑测试 → 失败

#### Task 12：payload_hash 幂等（review P0-1 加 user_id）

**RED** · `test_ingest_confluence.py::test_payload_hash_is_deterministic`
- 两次调 `compute_payload_hash(space_key="S", root_page_id=1, auth_email="u@t.com", user_id=42)` → 断言相等
- 跑测试 → 失败

**GREEN** · `def compute_payload_hash(*, space_key: str, root_page_id: int, auth_email: str, user_id: int) -> str`（review P0-1）：
```python
def compute_payload_hash(*, space_key: str, root_page_id: int, auth_email: str, user_id: int) -> str:
    """payload_hash = sha256(space_key + root_page_id + auth_email + user_id)。
    
    Why 含 user_id：同 space+page+email 但不同用户 → 不同 payload_hash（review P0-1，M5 P1-6 同类问题）。
    """
    return hashlib.sha256(
        f"{space_key}:{root_page_id}:{auth_email}:{user_id}".encode()
    ).hexdigest()
```

**RED** · `test_payload_hash_different_for_different_users`（review P0-1 新增）
- 调 `compute_payload_hash(..., user_id=1)` 与 `compute_payload_hash(..., user_id=2)` → 断言 hash 不同
- 跑测试 → 失败

**RED** · `test_ingest_confluence_returns_same_hash_for_same_inputs`
- 调 `ingest_confluence(...)` 两次 → 断言返回的 `report["payload_hash"]` 相同
- 跑测试 → 失败

**GREEN** · `report["payload_hash"] = compute_payload_hash(space_key=space_key, root_page_id=page_id, auth_email=auth.email, user_id=user_id)`

---

### Day 5-6（集成 + e2e + mock server + visited store）

#### Task 13：mock Confluence server fixtures（review P2-2 统一命名 mock_confluence_fixtures）

**GREEN**（无 RED，纯资源）· 写 `infra/mock_confluence_fixtures/`（review P2-2：统一目录名）：
- `pages/root.json`：Confluence v2 page 格式，含 `<p>root</p><ac:image><ri:attachment ri:filename="small.pdf"/></ac:image>` + `version: {number: 3, by: {displayName: "Alice"}}` + `labels: [{name: "meeting"}]`
- `pages/child_1.json`：纯 `<p>child</p>`
- `pages/child_2_with_attach.json`：含 2 个 attachment 元数据（一个 `application/pdf`，一个 `application/x-msdownload` 触发 P0-2 过滤）
- `attachments/`: 元数据 JSON + 一个 1KB PDF fixture + 一个 100KB exe fixture
- `README.md`：启动 `python -m http.server 9999 -d apps/rag_v1/infra/mock_confluence_fixtures`

注：URL 路径要兼容 Confluence v2 真实路径（`/wiki/api/v2/...`），所以这个 mock server 实际是 `pytest-httpserver` 在测试内起，**不是** `http.server`。这里的 `infra/mock_confluence_fixtures/` 仅为静态文件目录，由 `pytest-httpserver` 在运行时挂载。

#### Task 14：pytest-httpserver 集成测试（review P2-3 估时 30-40min）

**RED** · `tests/integration/test_m6_ingest_confluence.py::test_ingest_confluence_e2e_with_mock_server`
- `@pytest.fixture` 起 `pytest_httpserver` 监听 127.0.0.1:0
- 挂载：
  - `GET /wiki/api/v2/pages/1` → 返回 root.json
  - `GET /wiki/api/v2/pages/1/children` → 返回 child_1 元数据
  - `GET /wiki/api/v2/pages/2` → 返回 child_1.json
  - `GET /wiki/api/v2/pages/2/children` → 返回空
  - `GET /wiki/api/v2/pages/1/attachments` → 返回 attachment 元数据
  - `GET /wiki/api/v2/attachments/att-1/download` → 返回 1KB 二进制
- 调 `ingest_confluence(space_key="S", page_id=1, auth=ConfluenceAuth(...), user_id=42)` → 断言 `report["pages_processed"] == 2` / `report["attachments_downloaded"] == 1` / `chunks` 表有新行（**真 PG** via testcontainers，review P0-5 修复）
- 跑测试 → 失败

**GREEN** · 实现 `ingest_confluence`：
- 串起 `bfs_subtree` + `fetch_with_attachments` + `pipeline.process_elements` + 写 `chunks` 表
- 入参：`space_key: str, page_id: int, auth: ConfluenceAuth, user_id: int, *, max_depth: int | None = None`
- 出参：`IngestReport`
- 内部 `start = time.monotonic()`，结束时 `report["duration_seconds"] = time.monotonic() - start`（review P2-5）

#### Task 15：401/403 + 429 集成测试

**RED** · `test_m6_ingest_confluence.py::test_401_on_child_does_not_block_root`
- mock root 200 / child 401
- 调 `ingest_confluence(...)` → 断言 root 成功 + `report["permission_denied_pages"] == [2]`
- 跑测试 → 失败

**GREEN** · 在 Task 14 入口函数内补错误吞咽逻辑

**RED** · `test_429_retries_and_succeeds`
- mock root 第 1、2 次 429、第 3 次 200
- 调 `ingest_confluence(...)` → 断言成功 + mock server 收到 3 次 GET
- 跑测试 → 失败

**GREEN** · 确认 tenacity 装饰器生效

#### Task 16：50MB + Content-Type 集成测试

**RED** · `test_oversized_attachment_skipped_via_metadata`
- mock attachment 元数据 `size=52428801`
- 调 `ingest_confluence(...)` → 断言 `report["oversized_skipped"] == 1` + mock server 没收到 download 请求
- 跑测试 → 失败

**GREEN** · 在 `fetch_with_attachments` 入口先做 metadata size 检查

**RED** · `test_non_indexable_content_type_skipped`（review P0-2 集成）
- mock attachment `mediaType: "application/x-msdownload"`
- 调 `ingest_confluence(...)` → 断言 `report["skipped_content_type"] == 1` + mock server 没收到 download 请求
- 跑测试 → 失败

#### Task 17：chunks 表写入 + payload_hash 幂等验证（review P0-1 跨用户不碰撞）

**RED** · `test_repeated_ingest_same_payload_hash_does_not_duplicate_chunks`
- 调 `ingest_confluence(...)` 两次（相同 space_key + page_id + email + **user_id**）
- 断言 `chunks` 表行数 == 第一次的结果（不翻倍）
- 跑测试 → 失败

**GREEN** · 在 `ingest_confluence` 入口：
```python
existing = await session.execute(
    select(IngestJob).where(IngestJob.payload_hash == payload_hash)
)
if existing.scalar_one_or_none() is not None:
    logger.info("skipping ingest: payload_hash already processed", extra={"payload_hash": payload_hash})
    return report  # 含 reason="already_processed"
```
- 依赖 M1 schema 的 `ingest_jobs.payload_hash UNIQUE` 约束（review P1-5 已修复）

**RED** · `test_different_users_create_different_jobs`（review P0-1 集成）
- 用户 A（user_id=1）和用户 B（user_id=2）各自 ingest 同 space+page
- 断言 `ingest_jobs` 表有 2 行（不同 user_id）
- 跑测试 → 失败

#### Task 18：M8 入口 mock 集成（review P1-9 Pydantic 验证）

**RED** · `test_m6_ingest_confluence.py::test_ingest_confluence_function_signature_matches_m8_contract`
- mock M8 调用 `from app.ingest import ingest_confluence`
- 断言函数签名 `(space_key: str, page_id: int, auth: ConfluenceAuth, user_id: int, *, max_depth: int | None = None) -> IngestReport`
- 跑测试 → 失败

**GREEN** · 锁定 `app/ingest/sources/confluence.py` 的 `ingest_confluence` 函数签名（与 M8 plan 对齐）

**RED** · `test_confluence_auth_is_pydantic_model`（review P1-9 集成）
- 调 M8 反序列化 `ConfluenceAuth(**json_payload["auth"])` → 断言不抛异常 + `auth.api_token.get_secret_value() == "tok-123"`
- 跑测试 → 失败

#### Task 19：覆盖率门禁

**GREEN** · `pytest --cov=app/ingest/sources/confluence --cov-fail-under=85`
- 确认所有分支（成功 / 401/403 / 404 / 429 / 50MB / Content-Type 过滤 / BFS 深度限制 / 并发 / visited 持久化 / macro 提取 / 跨用户 hash）都覆盖

#### Task 20：（r2 NP-F 删）原计划 SqliteVisitedStore 单测

**r2 NP-F 修订**（方案 A · 推荐）：删除 `app/ingest/visited_store.py` + `tests/unit/test_confluence_visited_store.py`：
- **理由**：M6 单进程单 ingest，SQLite 优势不大；BFS 实际用 `data/confluence_bfs_visited.json` JSON 路径，SQLite 类是死代码
- BFS 函数 L458-490 的 JSON 路径是真实的；`SqliteVisitedStore` 类 L935-957 不被任何代码调用
- Files 表 L217 / L222 / 仓库布局 L56 / L66 同步删除
- r1 风险表 "P1-3 已修：SqliteVisitedStore 持久化" 改 "P1-3 已修：BFS visited JSON 文件持久化"
- 修订记录对应行同步改写
- 若未来 V1.1 需要并发 ingest 持久化，可改用 Postgres `ingest_bfs_visited` 表（M12 hardening 计划）

#### Task 21：CI Docker 配置（review P2-7 标记契约）

**GREEN**（无 RED）· 在测试策略段补：
```yaml
# .github/workflows/ci.yml（M14 范围，M6 仅记录契约）
# 集成测试步骤：
# - name: Start Docker services
#   run: docker compose -f infra/docker-compose.yml up -d postgres
# - name: Run integration tests
#   run: cd apps/rag_v1 && pytest tests/integration/ -m integration --require-docker
```

并在 `conftest.py` 加 `pytest_configure` 注册 `require-docker` marker + `pytest_collection_modifyitems` 检查 Docker 可用性。

#### Task 22：覆盖率门禁 + pyproject.toml 完整片段

**GREEN** · pyproject.toml 完整 toml 片段（review P2-4/P2-6/P2-8）：
```toml
[project]
name = "rag-v1"
dependencies = [
  # M0-M5 已有
  "fastapi>=0.110,<1",
  "sqlalchemy>=2.0,<3",
  "alembic>=1.13,<2",
  "pydantic>=2.5,<3",
  "pydantic-settings>=2.3,<3",
  "httpx>=0.27,<1",
  "tenacity>=8.3,<10",
  "llama-index-core>=0.10,<0.12",
  # M6 追加
  "llama-index-readers-confluence==0.4.4",
  "beautifulsoup4>=4.12,<5",
]

[project.optional-dependencies]
dev = [
  # M0-M5 已有
  "pytest>=8,<9",
  "pytest-asyncio>=0.23,<1",
  "pytest-httpx>=0.30,<1",
  "respx>=0.21",
  "pytest-httpserver>=1.1,<2",
  # M6 追加（review P0-5 强制）
  "testcontainers[postgresql]>=4.0,<5",
]
```

#### Task 23（r2 NP-A 新增）：`app/ingest/exceptions.py` 追加 6 个 Confluence 异常类

**r2 NP-A 修订**：M5 r2 NP-5 已将 `URLFormatError` / `UnsafeURLError` / `RetryableHTTPError` 移到 `app/ingest/exceptions.py`；M6 r2 同步追加 5+1 个 Confluence 相关类：

**RED** · `tests/unit/test_confluence_exceptions.py::test_oversized_page_error_inherits_oversized_file_error`
- `from app.ingest.exceptions import OversizedPageError, OversizedFileError`
- 断言 `issubclass(OversizedPageError, OversizedFileError)`（r2 NP-E 要求）
- 跑测试 → 失败

**RED** · `test_oversized_page_error_carries_size_and_max`
- `e = OversizedPageError(page_id=1, size_bytes=27000000, max_bytes=26214400)`
- 断言 `e.page_id == 1` / `e.size_bytes == 27000000` / `e.max_bytes == 26214400`
- 跑测试 → 失败

**GREEN** · 在 `app/ingest/exceptions.py` 追加：
```python
# r2 NP-A：M5 r2 NP-5 + M6 r2 同步，所有 ingest 子模块异常统一基类
class ConfluenceError(IngestError):
    """Confluence 相关异常基类（M6 专属基类，继承 M4 IngestError）。"""
    pass

class PermissionDeniedError(ConfluenceError):
    """401/403 — BFS 跳过该 page，计入 permission_denied_pages。"""
    pass

class PageNotFoundError(ConfluenceError):
    """404 — page 不存在或被删除，BFS 计入 errors 继续。"""
    pass

class ConfluenceServerError(ConfluenceError):
    """5xx — 服务器错误，可重试。"""
    pass

class ConfluenceAPIError(ConfluenceError):
    """其他 4xx / v2 REST 不支持的 start-limit 分页（r2 NP-B）— 客户端错误，不可重试。"""
    pass

# r2 NP-E：page body > 25MB → 继承 M4 OversizedFileError 复用文件大小限制错误处理
class OversizedPageError(OversizedFileError):
    """Confluence page body > max_page_body_bytes（默认 25MB）。
    
    r2 NP-E：Confluence Cloud 单 page body 25MB 限制，V1.1 整 space 时需严格处理。
    继承 M4 OversizedFileError → 统一文件大小限制错误处理。
    """
    def __init__(self, *, page_id: int, size_bytes: int, max_bytes: int):
        self.page_id = page_id
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(
            f"Confluence page {page_id} body {size_bytes} bytes > max {max_bytes} bytes"
        )
```

**RED** · `test_confluence_errors_inherit_ingest_error`
- 断言 5+1 个 Confluence 异常类都是 `IngestError` 子类
- 跑测试 → 失败

**GREEN** · 5+1 个 Confluence 异常类已隐式继承 IngestError（通过 `ConfluenceError` / `OversizedFileError`）

---

## 测试策略

- **M6 单元**：`cd apps/rag_v1 && pytest tests/unit/test_ingest_confluence.py tests/unit/test_confluence_bfs.py tests/unit/test_confluence_auth.py tests/unit/test_confluence_attachments.py` —— 全 mock（`respx` + `pytest-httpserver`），CI 内 8s（**r2 NP-F 删** `test_confluence_visited_store.py`）
- **M6 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m6_ingest_confluence.py --require-docker` —— 需 `docker compose -f infra/docker-compose.yml up -d postgres` + **testcontainers Python 库起真 PG 容器**（review P0-5 强制要求：不用 sqlite 假绿）
- **覆盖率门禁**：`pytest --cov=app/ingest/sources/confluence --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 [RED]）→ GREEN（commit 标 [GREEN]）→ REFACTOR（commit 标 [RF]）
- **错误矩阵覆盖率**（review P0-2/P0-3/P1-11/P2-9 全部纳入 + r2 NP-A/B/E 修复）：
  - 401/403 → 抛 `PermissionDeniedError`（typed）→ BFS 跳过该 page + 计入 `permission_denied_pages`
  - 404 → 抛 `PageNotFoundError` → 计入 `errors`（review P2-9）
  - 429 → tenacity 重试 3 次 + 指数退避 + 计入 `errors`
  - 500 → 抛 `ConfluenceServerError` → 计入 `errors` 不阻塞
  - 附件 > 50MB → 跳过 + 计入 `oversized_skipped`
  - **附件 Content-Type 不可索引** → 跳过 + 计入 `skipped_content_type`（review P0-2）
  - **page body > 25MB** → 抛 `OversizedPageError` → BFS 跳过该 page + 计入 `oversized_page_bodies`（r2 NP-E）
  - **`_links.next` start-limit 格式** → 抛 `ConfluenceAPIError` 终止分页，**不**死循环（r2 NP-B）
  - **PDF 损坏（M4 解析失败）** → M6 不感知（M4 pipeline 内处理）

---

## 验证（Definition of Done）

- [ ] `ConfluenceClient.get_page` 单 page 200 / 401 / 403 / 404 / 500 五路径全测过
- [ ] `bfs_subtree` 深度限制 / 循环引用 / 并发（semaphore）/ max_depth=None / max_depth=0 / 负数 ValueError / 404 / visited 持久化恢复 八路径全测过
- [ ] `download_attachment` 流式写盘（不一次性加载内存）/ 大小检查 / 50MB 跳过 / Content-Type 过滤 / 单 ingest 内去重 五路径全测过
- [ ] `list_children` 分页在 mock 环境下覆盖 cursor / 完整 URL / start-limit（抛 `ConfluenceAPIError` 终止，**不**死循环，r2 NP-B）/ 无 next 四种格式（review P1-7 + r2 NP-B）
- [ ] **`_links.next` start-limit 格式抛 typed 异常 `ConfluenceAPIError`**（r2 NP-B 修死循环 bug），调用方计入 errors 继续
- [ ] **page body > 25MB 抛 `OversizedPageError`**（r2 NP-E），BFS 跳过该 page + 计入 `oversized_page_bodies`
- [ ] `ingest_confluence` 入口签名与 M8 plan 对齐（mock 验证）
- [ ] `ConfluenceAuth` 是 Pydantic BaseModel（review P1-9），M8 可 `ConfluenceAuth(**payload["auth"])` 反序列化
- [ ] 401/403 跳过该 page 但**不**阻塞兄弟 page，统计入任务报告 `permission_denied_pages: list[int]`
- [ ] 429 token bucket + 指数退避，重试 3 次后跳过（tenacity 装饰器单测验证调用次数）
- [ ] 附件 > 50MB 跳过（metadata size 检查 + Content-Length 检查双保险）
- [ ] **附件 Content-Type 白名单过滤**（review P0-2），非可索引类型计入 `skipped_content_type`
- [ ] **附件下载独立 semaphore(2) + timeout(120s)**（review P0-3），与 page GET 隔离
- [ ] **payload_hash = sha256(space_key + root_page_id + auth_email + user_id)** 幂等（review P0-1：含 user_id，跨用户不碰撞）
- [ ] 重复 ingest 同 user_id 不写重复 chunks；不同 user_id 建不同 job（review P0-1）
- [ ] 元素分类：NarrativeText / Table / Image 三类至少各 1 个测试
- [ ] **`<ac:structured-macro ac:name="code">` 内容保留**（review P1-10），不丢代码块
- [ ] **page labels / version / last_modified_by / last_modified_at 元数据完整**（review P1-1/P1-2）
- [ ] **BFS visited 持久化到 `data/confluence_bfs_visited.json`**（review P1-3），中断后能恢复
- [ ] `tests/integration/test_m6_ingest_confluence.py` 用 testcontainers 起真 PG（不用 sqlite），30s 内通过
- [ ] 单元覆盖率 ≥ 85%
- [ ] `infra/mock_confluence_fixtures/` 静态资源 + README 启动方式（review P2-2 统一命名）
- [ ] `.env.example` 含 `CONFLUENCE_BASE_URL` / `CONFLUENCE_MAX_DEPTH` / `CONFLUENCE_MAX_ATTACHMENT_BYTES` / `CONFLUENCE_DOWNLOAD_CONCURRENCY` / `CONFLUENCE_BFS_VISITED_FILE`
- [ ] `pyproject.toml` 含 `llama-index-readers-confluence==0.4.4` / `respx>=0.21` / `testcontainers[postgresql]>=4.0,<5` / `beautifulsoup4>=4.12,<5`（review P2-6/P2-8 完整 toml 片段）
- [ ] review P0-5 / P1-5 全部落实（真 PG + payload_hash UNIQUE）
- [ ] **review P0-1/P0-2/P0-3 + P1-1~11 + P2-1~9 全部 23 项已修**（r1 修订记录 + 风险表 23 行已修条目可验证）
- [ ] **r2 修复 6 项新问题**（r2 NP-A~F）：NP-A 异常类统一 `app/ingest/exceptions.py` · NP-B `_links.next` start-limit 抛 `ConfluenceAPIError`（不进入死循环）· NP-C 17 行 r1 修复"曾被否决的替代方案"列填实际方案 · NP-D M5 复用接口显式 import + 启动校验 base_url · NP-E page body 25MB 抛 `OversizedPageError` · NP-F 删 `SqliteVisitedStore`（BFS 用 JSON 路径）

---

## 与其他 M 的依赖

| 上游（必须 M6 前完成） | 下游（依赖 M6） |
|----------------------|----------------|
| M0 `infra/docker-compose.yml`（postgres 容器） | M8 `/api/ingest` 路由（调 `ingest_confluence`） |
| M1 alembic（chunks 表 + ingest_jobs 表 + payload_hash UNIQUE 索引，review P1-5） | M7 retrieval（M6 写完 chunks 后 M7 upsert 到 OpenSearch） |
| M3 TEI embedder（pipeline 内调；M3 review P0-3 `EmbeddingDimMismatch` 硬断言对接） | V1.1 整 space CQL 抓取（复用 `ConfluenceClient`） |
| M4 ingest pipeline / splitter（`process_elements`、`process_confluence_page`；M6 自带 fallback 元素分类，review P1-6） | M12 hardening（BFS visited 强化为 Postgres 持久化） |
| M5 httpx 重试模式（429 指数退避参考）+ M5 复用 4 个公开 API：`assert_safe_url` / `validate_url_format` / `load_auth_config`（r2 NP-D 显式 import，启动校验 base_url） | M14 CI（testcontainers Docker 集成测试，review P2-7 契约） |

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| **Confluence Cloud 限速比 Server 严**（Cloud 是 5000 req/h/user，Server 更高） | semaphore(5) + 指数退避；`max_retries=3`；429 后 skip 而不 fail | "不限速" — 会触发 Cloud 账号 ban |
| **Confluence API v2 字段差异**（不同 Confluence Cloud 版本字段命名/嵌套不一） | mock server 用 v0.4 spec §3.1 锁定的字段；集成测试覆盖 metadata 提取路径 | "退回 v1 REST" — spec 决策 #19 已否决 |
| **附件下载内存压力**（大文件一次性加载 OOM） | `httpx.AsyncClient.stream()` + `aiter_bytes(chunk_size=64KB)` 流式写盘；下载前 metadata size 预检查 | "全部加载到内存再写" — 50MB 单文件就 OOM |
| **BFS 循环引用 / 巨型子树**（Confluence 偶有 parent 指向 child 的脏数据） | `visited: set[int]` 守护；max_depth=3 默认（V1.1 整 space 才放开） | "无限递归直到 API 报错" — 会触发 429 ban |
| **API token 泄露到日志**（`logger.info(f"auth={auth}")` 会打印 token） | `ConfluenceAuth.__repr__` redact；pipeline 内 `auth.api_token.get_secret_value()` 仅在 httpx 调用栈出现 | "日志打印完整请求" — 安全事故 |
| **子页 BFS 并发抓取顺序非确定性**（影响任务报告可读性） | `pages_processed` 按 `page_id` 排序后再返回；附件下载顺序不影响 chunks 表（按 page_id 排序写） | "强制串行" — 性能不可接受 |
| **M8 路由尚未实现**（M6 集成测试 mock 路由） | Task 18 用 `inspect.signature(ingest_confluence)` 锁定函数签名；M8 plan 引用 M6 contract 表 | "M6 自己写路由" — 越权（M8 负责） |
| **Confluence 存储格式 `storage` 与 `atlas_doc_format` 不一致** | 决策 #19 锁定 `storage`；`body-format=storage` query param 显式传 | "默认让 server 选" — 不同 tenant 返回格式不同 |
| **payload_hash 冲突概率**（sha256 实际几乎为 0，但同 space 同 page 同 email 重复 ingest 必须识别） | 配合 `ingest_jobs.payload_hash UNIQUE` 约束（review P1-5）+ 应用层 SELECT 预检 | "不幂等" — 用户每次重跑就重复 chunks |
| **不可索引附件漏入导致 pipeline 解析异常**（review P0-2） | `INDEXABLE_MIME_PREFIXES` 白名单（text/* / application/pdf / image/* / Office 文档）；非白名单 skip + 计入 `skipped_content_type` | "全部下载" — exe/zip 进索引后 M4 splitter 抛异常 |
| **附件下载慢连接挂死 BFS**（review P0-3） | 独立 `download_semaphore(2)` + `download_timeout(120s)`；与 page GET `semaphore(5)` + `timeout(30s)` 隔离 | "共享 semaphore + timeout" — 5 个慢下载同时挂 400s，BFS 完全阻塞 |
| **payload_hash 跨用户冲突**（review P0-1，M5 P1-6 未同步） | hash 拼接 `user_id`；DB UNIQUE 约束仍生效 | "只含 email" — 用户 B 拿用户 A 的 job |
| **Confluence v2 `_links.next` 格式 Cloud 版本差异**（review P1-7） | `list_children` 防御式处理 4 种格式：相对路径 / 完整 URL / `start-limit` / cursor | "假设相对路径" — 旧 Cloud / DC 版直接失败 |
| **BFS visited 未持久化导致中断全量重跑**（review P1-3） | visited set 写到 `data/confluence_bfs_visited.json`；`bfs_subtree` 入口恢复 + finally 持久化 | "只在内存" — 200+ 页大子树中断浪费 90% API 容量 |
| **page labels 元数据缺失**（review P1-1） | metadata 补 `labels: list[str]`；防御式 `page.get("labels", [])` | "不加" — RAG 检索无法按 tag 过滤 |
| **page version 元数据缺失**（review P1-2） | metadata 补 `version` / `last_modified_by` / `last_modified_at` | "不加" — V1.1 增量同步无法工作 |
| **ConfluenceAuth 非 Pydantic M8 路由无法反序列化**（review P1-9） | `ConfluenceAuth(BaseModel)` + `SecretStr`；M8 路由 `ConfluenceAuth(**payload["auth"])` | "普通 class" — M8 路由需要手写反序列化 |
| **`<ac:structured-macro ac:name="code">` 等复杂标签内容丢失**（review P1-10） | `process_confluence_page` 用 BeautifulSoup 提取 `ac:plain-text-body` 文本；其他 macro（jira/chart/expand）V1.1 | "只解析 `<p>/<table>/<ac:image>`" — 代码块完全丢失 |
| **附件被多 page 引用重复下载**（review P1-8） | `ConfluenceClient._downloaded_set: set[str]`；`download_attachment` 入口查重 + `IngestReport.attachments_deduplicated` 统计 | "每次都下载" — 10 个 page 引用 logo 下载 10 次 |
| **PermissionDeniedError 类型断言安全**（review P1-11 + r2 NP-A） | 异常继承链 `IngestError > ConfluenceError > {PermissionDeniedError, PageNotFoundError, ConfluenceAPIError, ConfluenceServerError, OversizedPageError}`；**5+1 个异常类统一在 `app/ingest/exceptions.py` 定义**（M5 r2 NP-5 同步 + r2 NP-A 追加 `OversizedPageError`）；Task 3 `_request` 显式抛 typed | "通用 ConfluenceAPIError" — Task 9 except 不到，跳不过 |
| **BFS asyncio.Queue vs deque 注释不一致**（review P1-4） | 注释改为"BFS 用 deque + asyncio.Semaphore 控制并发；不用 asyncio.Queue——BFS 单 producer 遍历 deque 更高效" | "用 asyncio.Queue" — 增加 task_done/join 复杂性 |
| **max_depth=None 时 TypeError**（review P1-5） | `if max_depth is None: max_depth = float('inf')`；负数抛 `ValueError` | "假设 max_depth 必为 int" — None 运行时崩 |
| **process_confluence_page 与 M4 pipeline 不兼容**（review P1-6） | M6 自带 fallback 元素分类器（BeautifulSoup 解析 `<p>/<table>/<ac:image>/<ac:structured-macro ac:name="code">`），不与 M4 元素分类强耦合 | "等 M4 完成" — 阻塞 M6 工期 |
| **M4 元素分类未实现，M6 的 `process_confluence_page` 无兼容上游**（review P1-6 跨 M） | M6 自带 fallback 元素分类器（BeautifulSoup + `<p>/<table>/<ac:image>` 规则），不与 M4 耦合 | "阻塞等 M4 完成" — 拖累 M6 工期 |
| **`llama-index-readers-confluence` 与自建 client import 冲突**（review P2-1） | 主体自建 client 不 import `ConfluenceReader`；仅 `TYPE_CHECKING` 引用 | "同时 import" — 2 个 httpx.AsyncClient 相互干扰 |
| **Mock server 目录命名不一致**（review P2-2） | 统一为 `infra/mock_confluence_fixtures/`（Files 表 + Task 13） | "混用 mock_confluence" — 新人创建错目录 |
| **Task 估时偏紧**（review P2-3） | 估时改 7-8d；Task 11 标 25-30min、Task 14 标 30-40min、Task 5 标 20-25min、Task 7 标 20-25min | "5d" — 实际不够 |
| **`_request` 未设 `follow_redirects`**（review P2-4） | 显式 `follow_redirects=True, max_redirects=3` 防御反向代理 302 | "默认" — 302 时 body 是 redirect 响应而非目标内容 |
| **`IngestReport` 缺 `total_pages_discovered` / `chunks_count` / `duration_seconds`**（review P2-5） | `IngestReport` TypedDict 补 3 字段 + `skipped_content_type` + `attachments_deduplicated` | "字段集不足" — M8 进度查询分母缺失 |
| **`testcontainers[postgresql]` 未声明 dev 依赖**（review P2-6） | pyproject `[project.optional-dependencies].dev` 追加 `testcontainers[postgresql]>=4.0,<5` | "不写" — `ModuleNotFoundError` |
| **CI Docker 未配置**（review P2-7） | 测试策略段补 `.github/workflows/ci.yml` 契约 + `conftest.py` `require-docker` marker | "无 CI" — 集成测试没法跑 |
| **pyproject.toml 缺完整 toml 片段**（review P2-8） | 给完整 `dependencies` + `dev` 块 | "只写追加行" — 新人不知位置 |
| **`list_attachments` 缺 404/403 处理**（review P2-9） | `_request` 显式抛 `PageNotFoundError`（404）+ `PermissionDeniedError`（403）；BFS 内 `except PageNotFoundError` 计入 `errors` 继续 | "只处理 401/403" — page 被删除后 BFS 崩 |
| **r2-2026-06-12 NP-A 已修：异常类统一入口** | M5 r2 NP-5 + M6 r2 同步，把 `ConfluenceError` / `PermissionDeniedError` / `PageNotFoundError` / `ConfluenceServerError` / `ConfluenceAPIError` / `OversizedPageError` 5+1 个类移到 `app/ingest/exceptions.py`；Task 3 GREEN 加 import 段 | "分散在 `sources/confluence.py` 顶部" — 复刻 M5 r2 NP-5 同类错 |
| **r2-2026-06-12 NP-B 已修：_links.next start-limit 死循环**（P0 阻塞） | Task 4 GREEN `url = base_url` 改 `raise ConfluenceAPIError(...)`；RED 段加 `test_list_children_start_limit_raises_error` | "保留 `url = base_url`" — 1M+ page 整 space 拉死 BFS |
| **r2-2026-06-12 NP-C 已修：17 行 r1 修复"曾被否决的替代方案"列填实际方案** | L1105-1127 17 行第三列从 `r1-2026-06-11` 改为实际被否决方案（每行不同） | "留 `r1-2026-06-11` 标签" — 无意义（M5 r2 NP-4 同 cosmetic） |
| **r2-2026-06-12 NP-D 已修：M5 复用接口显式 import** | Tech Stack 关键导入路径 + Task 3 GREEN 加 `from app.ingest.sources.url import assert_safe_url, validate_url_format, load_auth_config`；`ConfluenceClient.__init__` 启动调 `assert_safe_url(base_url)` 校验配置 | "doctring 写'复用'但代码不调" — 文档/代码脱节（M5 r2 NP-3 同类） |
| **r2-2026-06-12 NP-E 已修：page body 25MB 限制** | `ConfluenceSettings` 加 `max_page_body_bytes=26214400` + `page_body_read_timeout_seconds=60`；`get_page` 检查 `body.storage.value` 长度，超限抛 `OversizedPageError`（继承 `OversizedFileError`）；BFS 计入 `oversized_page_bodies` | "只检查附件不检查 page" — meeting notes / API 文档 / 大 SVG 触发 read timeout |
| **r2-2026-06-12 NP-F 已修：删 `SqliteVisitedStore` 死代码**（方案 A） | Task 20 整段删除 `app/ingest/visited_store.py` + `tests/unit/test_confluence_visited_store.py`；BFS 用 `data/confluence_bfs_visited.json` JSON 路径（M6 单进程单 ingest 足够） | "保留 SQLite 类 + 补 `clear()` / `remove()`" — 单进程用 SQLite 过重，类不被任何代码调用是死代码 |

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M6-plan-r0 | 2026-06-11 | 初稿（基线 V1 Scope §3.1 / §5 / 决策 #19 + review P0-5/P1-5 约束） |
| r1-2026-06-11 | 2026-06-11 | P0-1 已修：payload_hash 加 user_id（review P0-1，M5 P1-6 跨用户冲突同步修正） |
| r1-2026-06-11 | 2026-06-11 | P0-2 已修：INDEXABLE_MIME_PREFIXES 白名单（text/* / pdf / image/* / Office）过滤非可索引附件，计入 skipped_content_type |
| r1-2026-06-11 | 2026-06-11 | P0-3 已修：ConfluenceClient 独立 download_semaphore(2) + download_timeout(120s)，与 page GET semaphore(5)/timeout(30s) 隔离，慢连接不挂死 BFS |
| r1-2026-06-11 | 2026-06-11 | P1-1 已修：metadata.labels: list[str]（Confluence 核心分类，RAG 检索 tag 过滤） |
| r1-2026-06-11 | 2026-06-11 | P1-2 已修：metadata.version / last_modified_by / last_modified_at（V1.1 增量同步基础） |
| r1-2026-06-11 | 2026-06-11 | P1-3 已修：BFS visited 持久化到 `data/confluence_bfs_visited.json`（JSON 文件，非 SqliteVisitedStore 类；r2 NP-F 删 SQLite 死代码） |
| r1-2026-06-11 | 2026-06-11 | P1-4 已修：BFS 用 deque + asyncio.Semaphore，注释修正（不用 asyncio.Queue） |
| r1-2026-06-11 | 2026-06-11 | P1-5 已修：max_depth=None → float('inf')；max_depth=0 仅 root；负数 ValueError |
| r1-2026-06-11 | 2026-06-11 | P1-6 已修：M6 自带 BeautifulSoup fallback 元素分类器（<p>/<table>/<ac:image>），不与 M4 pipeline 强耦合 |
| r1-2026-06-11 | 2026-06-11 | P1-7 已修：list_children _links.next 4 种格式兼容（相对路径 / 完整 URL / cursor）；r2 NP-B 修订：start-limit 抛 `ConfluenceAPIError` 终止（v2 不支持）而非 `url = base_url` 死循环 |
| r1-2026-06-11 | 2026-06-11 | P1-8 已修：ConfluenceClient._downloaded_set 附件去重；IngestReport.attachments_deduplicated 统计 |
| r1-2026-06-11 | 2026-06-11 | P1-9 已修：ConfluenceAuth 改 Pydantic BaseModel + SecretStr，M8 路由可 ConfluenceAuth(**payload["auth"]) 反序列化 |
| r1-2026-06-11 | 2026-06-11 | P1-10 已修：process_confluence_page 提取 <ac:structured-macro ac:name="code"> 内 ac:plain-text-body 文本，代码块不丢 |
| r1-2026-06-11 | 2026-06-11 | P1-11 已修：异常继承链 `ConfluenceError > {PermissionDeniedError, PageNotFoundError, ConfluenceAPIError, ConfluenceServerError}`；r2 NP-A 修订：5+1 个异常类（含 `OversizedPageError`）统一在 `app/ingest/exceptions.py` 定义（M5 r2 NP-5 同步） |
| r1-2026-06-11 | 2026-06-11 | P2-1 已修：ConfluenceReader 仅 TYPE_CHECKING 引用，主体自建 client 不 import |
| r1-2026-06-11 | 2026-06-11 | P2-2 已修：infra/mock_confluence_fixtures/ 统一目录名（Files 表 + Task 13） |
| r1-2026-06-11 | 2026-06-11 | P2-3 已修：估时 5d → 7-8d；Task 11 标 25-30min、Task 14 标 30-40min、Task 5 标 20-25min、Task 7 标 20-25min |
| r1-2026-06-11 | 2026-06-11 | P2-4 已修：httpx.AsyncClient follow_redirects=True + max_redirects=3 防御反向代理 |
| r1-2026-06-11 | 2026-06-11 | P2-5 已修：IngestReport TypedDict 补 pages_discovered / chunks_count / duration_seconds / skipped_content_type / attachments_deduplicated 5 字段 |
| r1-2026-06-11 | 2026-06-11 | P2-6 已修：pyproject [project.optional-dependencies].dev 追加 testcontainers[postgresql]>=4.0,<5 |
| r1-2026-06-11 | 2026-06-11 | P2-7 已修：测试策略段补 .github/workflows/ci.yml Docker 契约 + conftest.py require-docker marker |
| r1-2026-06-11 | 2026-06-11 | P2-8 已修：pyproject.toml 完整 toml 片段（dependencies + dev，含 beautifulsoup4 / testcontainers） |
| r1-2026-06-11 | 2026-06-11 | P2-9 已修：_request 显式抛 PageNotFoundError(404)，bfs_subtree except 计入 errors 继续 BFS；list_attachments 同样走 _request 间接获 404 处理 |
| r2-2026-06-12 | 2026-06-12 | r2 评审与修复：6 项 r1 引入新问题消化（NP-A 异常类未与 M4 exceptions.py 对齐 / NP-B _links.next start-limit 分页代码实际会死循环 / NP-C 风险表 17 行 r1 修复"曾被否决的替代方案"列无意义 / NP-D M5 复用接口只写"复用"未真 import / NP-E Confluence page body 25MB 限制未考虑 / NP-F SqliteVisitedStore 死代码与 JSON 路径并存） |
| r2-2026-06-12 | 2026-06-12 | **NP-A 已修**（P1 阻塞）：5+1 个异常类（`ConfluenceError` / `PermissionDeniedError` / `PageNotFoundError` / `ConfluenceServerError` / `ConfluenceAPIError` / `OversizedPageError`）统一在 `app/ingest/exceptions.py` 定义；Task 3 GREEN / Task 5 GREEN / 关键导入路径 段加 `from app.ingest.exceptions import ...`；M5 r2 NP-5 同步 |
| r2-2026-06-12 | 2026-06-12 | **NP-B 已修**（P0 阻塞）：Task 4 GREEN `list_children` `_links.next` start-limit 分支由 `url = base_url` 死循环改为 `raise ConfluenceAPIError(...)` 终止；RED 段加 `test_list_children_start_limit_raises_error`；DoD 加 1 条 |
| r2-2026-06-12 | 2026-06-12 | **NP-C 已修**（P3 cosmetic）：风险表 17 行 r1 修复"曾被否决的替代方案"列从 `r1-2026-06-11` 改为 6 行 `r2-2026-06-12 NP-X 已修` 含实际被否决方案（M5 r2 NP-4 同 cosmetic 同步） |
| r2-2026-06-12 | 2026-06-12 | **NP-D 已修**（P2）：Tech Stack 关键导入路径 + Task 3 GREEN 加 `from app.ingest.sources.url import assert_safe_url, validate_url_format, load_auth_config`；`ConfluenceClient.__init__` 启动调 `assert_safe_url(base_url)` 校验配置；M5 r2 NP-3 同步 |
| r2-2026-06-12 | 2026-06-12 | **NP-E 已修**（P2）：`ConfluenceSettings` 加 `max_page_body_bytes=26214400`（25MB）+ `page_body_read_timeout_seconds=60`；Task 3 `get_page` 检查 `body.storage.value` 长度超限抛 `OversizedPageError`（继承 `OversizedFileError`）；BFS 计入 `oversized_page_bodies`；`IngestReport` 补 1 字段；RED 加 `test_get_page_oversized_body_skipped` |
| r2-2026-06-12 | 2026-06-12 | **NP-F 已修**（P2，方案 A）：删 `app/ingest/visited_store.py` + `tests/unit/test_confluence_visited_store.py` + Task 20 整段 + 仓库布局对应行 + Files 表对应行 + 测试策略段；BFS 用 `data/confluence_bfs_visited.json` JSON 路径（M6 单进程单 ingest 足够；SqliteVisitedStore 类无任何代码调用是死代码） |
