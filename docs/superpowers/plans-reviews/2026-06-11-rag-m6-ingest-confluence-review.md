# M6 Plan Review · Ingest Confluence Source（子页 BFS + 附件抓取）

> 评审对象：`2026-06-11-rag-m6-ingest-confluence.md`（606 行，v0 初稿 2026-06-11）
> 评审基线：V1 Scope v0.4 spec（§0 决策 #4/#19 · §3.1 Ingest 数据流 confluence 段 · §5 错误矩阵 11 条 · §8.2 Embedding & 文档解析栈 7 包）;
> 已有 review 总报告 `2026-06-11-rag-plans-review.md` P0-1/P0-5/P1-5;
> M0/M1/M2/M3/M4/M5 独立 review 报告（reviews/ 目录 6 份）;
> M5 review P0-1 SSRF redirect bypass / P1-6 payload_hash 跨用户冲突;
> M4 review P0-1 元素分类 / P0-3 OpenSearch 写入层
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M6 plan 是 RAG V1 ingest Confluence source 的完整实现方案，**11 段模板走齐**（Goal / 不包含 / Architecture / Tech Stack / Files / Tasks RED-GREEN / 测试策略 / DoD / 依赖 / 风险 / 修订记录），**主动吸收了**跨 M review 的 2 项关键 P0/P1（P0-5 真 PG testcontainers / P1-5 payload_hash UNIQUE 约束），**Confluence v2 REST 端点选择正确**（4 端点：GET pages/{id} / children / attachments / download），**错误矩阵覆盖完整**（401/403/429/50MB/5xx），**并发控制设计合理**（semaphore(5) + 十acity 指数退避），**附件流式写盘避免 OOM**，**BFS 深度限制 + visited set 防循环引用**，**payload_hash 幂等设计清晰**。**整体技术深度高于 M4/M5 同期水平，是当前 RAG V1 路线中结构与深度最均衡的一份 plan。**

但作为 V1 中最大的 ingest 里程碑（估时 5 个工作日，占 M4-M6 总估时的 45%），**仍有 14 个实施前必须解决的问题和 18 个重要优化**：

| 维度 | 评分 | 说明 |
|------|------|------|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐；Goal/不包含（含 M6 vs 其他 M 的契约边界表）/ Architecture（仓库布局 + 模块树）/ Tech Stack（版本精确到 <1 级）/ Files / Tasks 19 个 + DoD 16 条 + 风险 8 行——是已审查 6 份 M plan 中**最完整的一份** |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 19 个 Task 全 RED-GREEN；RED 测试名具体、GREEN 代码段完整（非伪代码）；Day 5 集成 Task 16 个 RED 覆盖全部错误矩阵 |
| 技术深度 | ⭐⭐⭐⭐ | Confluence v2 REST 端点、BFS + asyncio.Queue、stream 流式下载、token redact —— 深度足够；但**缺 6 项工程细节**（附件 Content-Type 过滤、下载超时隔离、visited set 持久化、label/version/author 元数据、分页 _links 字段差异处理） |
| 错误处理 | ⭐⭐⭐⭐ | spec §5 错误矩阵 M6 范围 6 条全部覆盖（401/403/429/50MB/5xx/存储格式）；但**缺 Content-Type 校验、下载超时、分页空响应处理** |
| 跨 M 契约 | ⭐⭐⭐⭐ | M4 pipeline / M8 入口签名 / M7 OpenSearch upsert / V1.1 CQL 复用边界清晰；但 `process_confluence_page` 修改 M4 pipeline 未确认 M4 plan 兼容性 |
| 一致性 | ⭐⭐⭐⭐ | 主动吸收了 2 项已有 P0/P1；版本与 spec §8.2 对齐；但 payload_hash 未含 user_id（M5 review P1-6 同类问题未同步修正） |

**一句话**：M6 plan **结构对、版本对、技术深度够**，是当前 RAG V1 路线中**最成熟的单 M plan**；但 **payload_hash 跨用户冲突（P0-1）是阻塞级设计缺陷**，**附件 Content-Type 过滤缺失（P0-2）会导致 binary 进索引**，**download 超时未隔离（P0-3）会在慢连接时挂死 BFS**。修完 3 个 P0 + 11 个 P1 + 9 个 P2 后是可直接动手的合格 plan。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · payload_hash 不含 user_id，跨用户同 space+page+email 被识别为幂等（M5 review P1-6 同类遗漏）

**位置**：Task 12 GREEN 段 L438-439；Goal L23；风险表 L598

**问题**：

```
payload_hash = sha256(f"{space_key}:{root_page_id}:{auth_email}")
```

M5 review P1-6（`2026-06-11-rag-m5-ingest-url-review.md` L306-321）已指出同类问题：**跨用户幂等冲突**：

1. 用户 A ingest `space_key="S"` + `page_id=1` + `email=a@t.com` → job1, payload_hash = H
2. 用户 B ingest 同 space+page+email（可能有不同 API token） → payload_hash 相同 → 幂等返 job1 → **用户 B 以为自己 ingest 了但实际是 A 的 job**
3. 用户 B 的 API token **不会用于抓取**（幂等返旧 job）
4. 即使 API token 不同（Cloud Basic auth 是 email+token 对），payload_hash 只含 email 不含 token → 不同 token 同 email 撞 hash

**修改**（Task 12 GREEN 段改 `compute_payload_hash`）：

```python
def compute_payload_hash(*, space_key: str, root_page_id: int, auth_email: str, user_id: int) -> str:
    """payload_hash = sha256(space_key + root_page_id + auth_email + user_id)。

    Why 含 user_id：同 space+page+email 但不同用户 → 不同 payload_hash（M5 review P1-6）。
    """
    return hashlib.sha256(
        f"{space_key}:{root_page_id}:{auth_email}:{user_id}".encode()
    ).hexdigest()
```

并在：

- Task 12 RED 测试 `test_payload_hash_is_deterministic` 加 `user_id` 参数
- Task 17 幂等验证断言跨用户不碰撞
- DoD 第 8 条补 `user_id` 字段
- Goal L23 补 `user_id`

**影响**：Task 12 / Task 14 RED 测试签名全部需加 `user_id` 参数。`ingest_confluence` 签名原本已有 `user_id: int`，所以入口不改。

**已有 review**：M5 review P1-6 已明确，M6 未同步。**严重遗漏**。

---

### P0-2 · 缺附件 Content-Type / 文件类型过滤，exe/zip/binary 能进索引但无法索引

**位置**：Task 6-8 全篇；Task 11 元数据段；DoD 第 9 条

**问题**：

- M6 下载任何 attachment（Task 6 `list_attachments` 返回 `id` / `title` / `size` / `download_path`）——**没有 Content-Type / MIME 检查**
- Confluence API v2 `GET /wiki/api/v2/pages/{id}/attachments` 返回 `metadata` 含 `mediaType` 字段（如 `application/pdf`, `image/png`, `application/x-msdownload`）
- 不检查类型 → exe / zip / macOS .dmg / `.DS_Store` 等**无法解析的 binary** 也会被下载 + 标记 metadata + 写入 chunks 表（`attachment_filename` 有值但内容为 0）
- M4 splitter（预计 PDF/DOCX→text）遇到 exe/zip 抛解析异常 → ingest 任务标 failed
- 50MB 检查只拦大小不拦类型——小 exe（如 100KB）通过

**修改**（Task 6 GREEN 段 `list_attachments` 加 filter，Task 8 加类型检查）：

```python
# Confluence 附件可索引 Content-Type 白名单（V1 范围）
INDEXABLE_MIME_PREFIXES = (
    "text/",           # txt, csv, html, xml
    "application/pdf", # pdf
    "application/vnd.openxmlformats-officedocument.",  # docx/xlsx/pptx
    "application/msword",
    "application/vnd.ms-",
    "image/",          # png/jpg/gif/webp（M4 image extraction）
    "message/rfc822",  # .eml
)

async def list_attachments(self, page_id: int) -> AsyncIterator[dict]:
    async for att in super().list_attachments(page_id):
        mime = (att.get("metadata") or {}).get("mediaType", "")
        if not any(mime.startswith(p) for p in INDEXABLE_MIME_PREFIXES):
            logger.info("skipped non-indexable attachment", extra={
                "att_id": att["id"], "title": att.get("title"), "mime": mime
            })
            self._report.skipped_content_type += 1
            continue
        yield att
```

并在：

- `IngestReport` 加 `skipped_content_type: int` 字段
- DoD 第 6 条（50MB 跳过）旁边加 `skipped_content_type` 条目
- 风险表加：不可索引附件漏入导致 pipeline 解析异常

**影响**：Task 6 RED 测试 `test_list_attachments_returns_metadata` 需补 `test_list_attachments_filters_non_indexable`。DoD 加 1 条。

**新发现**（已有 review 未列）。

---

### P0-3 · 附件下载超时未隔离，BFS 并发可能被慢连接 hang 死

**位置**：Task 3 GREEN 段 L237；Task 7 GREEN 段 L330-331；Task 7 全篇

**问题**：

- `ConfluenceClient.__init__` 构造 `httpx.AsyncClient(timeout=30.0)`——**全局 timeout 30s**
- `download_attachment` 复用同一 client，但附件下载是 stream 操作：`async for chunk in r.aiter_bytes(chunk_size=65536)`
- 慢连接（如 50MB 附件在 1Mbps 网络 → ~400s）+ 30s timeout = **中途超时断开** → 文件不完整（partial write）+ `TimeoutException`
- 最大问题：**`download_attachment` 和 `get_page` 共享 semaphore(5)**——plan 没有单独 `download_semaphore`
  - 1 个慢附件下载占用 1 个 slot 长达 400s → 阻塞 4 个 page GET / children 请求 → BFS 几乎停下
  - 5 个同时下载（每个 30s 超时）= 30s 内 BFS 完全阻塞 → BFS 总耗时从预计 30s 膨胀到 400s+

**修改**（Task 3 GREEN 段 + Task 7 GREEN 段）：

```python
# ConfluenceClient.__init__ 加独立 timeout 和 semaphore
class ConfluenceClient:
    def __init__(self, base_url, auth, settings):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=20.0,     # 建连
                read=30.0,        # page GET / children / attachments
                write=None,
                pool=None,
            ),
            auth=auth.to_httpx(),
        )
        self._page_semaphore = asyncio.Semaphore(settings.concurrency)  # page GET 用
        self._download_semaphore = asyncio.Semaphore(2)                 # 下载专用，最多 2 并发
        self._download_timeout = httpx.Timeout(
            connect=30.0,
            read=120.0,          # 附件 stream 独立超时（大文件慢连接）
            write=None,
            pool=None,
        )

    async def download_attachment(self, *, att_id: str, dest_path: Path) -> int | None:
        async with self._download_semaphore:  # 独立 semaphore，不阻塞 BFS
            async with self._client.stream(
                "GET",
                f"/wiki/api/v2/attachments/{att_id}/download",
                timeout=self._download_timeout,
            ) as r:
                ...
```

并在：

- `ConfluenceSettings` 加 `download_concurrency: int = 2` / `download_timeout_seconds: int = 120`
- 单测 `test_download_semaphore_does_not_block_page_fetch`（mock 慢下载 → 断言 BFS 仍能 GET）
- 风险表加一行：下载超时 + semaphore 饥饿

**影响**：`ConfluenceSettings` 多 2 个字段；Task 3 RED 测试补签名；Task 7 补隔离验证。

**新发现**（已有 review 未列）。

---

## P1 · 重要

### P1-1 · 缺 page labels / tags 元数据抽取

**位置**：Task 11 GREEN 段 L405-416 元数据 dict

**问题**：

- Confluence v2 REST `GET /wiki/api/v2/pages/{id}` 在 Cloud 版返回 `labels` 数组（`[{"id": "...", "name": "label-name", "prefix": "global"}]`）
- labels 是 Confluence 核心分类机制（类似 tag），对 RAG 检索过滤极有价值
- 当前 metadata 只含 `source / page_id / space_key / parent_id / depth / title`——没 labels
- 例：用户标 `label: "meeting-notes"` → RAG 检索可 filter `metadata.labels contains "meeting-notes"`——M7 retrieval 需 metadata 支持

**修改**（Task 11 GREEN 段元数据补）：

```python
meta = {
    "source": "confluence",
    "page_id": page["id"],
    "space_key": space_key,
    "parent_id": page.get("parent_id"),
    "depth": page["depth"],
    "title": page["title"],
    "labels": [label["name"] for label in page.get("labels", [])],  # P1-1
}
```

并在：

- DoD 第 9 条补 `labels` 断言
- 单测 `test_metadata_includes_labels`
- 风险表注：Confluence Cloud 返回 labels 字段格式可能变，`page.get("labels", [])` 防御式读取

**影响**：微。

**新发现**。

---

### P1-2 · 缺 page version / last modifier 元数据

**位置**：Task 11 GREEN 段 L405-416

**问题**：

- Confluence v2 REST page 响应含 `version` 对象（`{number: 3, by: {displayName: "...", email: "..."}, when: "..."}`）
- 版本号对审计、增量同步（V1.1）、chunk 去重（同 page 更新后 chunk 变更检测）极有价值
- 当前 metadata 完全不获取 `version` / `last_modifier` / `last_modified_at`

**修改**（Task 11 GREEN 段补）：

```python
meta = {
    ...
    "version": page.get("version", {}).get("number"),           # P1-2
    "last_modified_by": page.get("version", {}).get("by", {}).get("displayName"),
    "last_modified_at": page.get("version", {}).get("when"),
}
```

并在 DoD 第 9 条补 `version` 和 `last_modified_by` 断言。

**影响**：微。

**新发现**。

---

### P1-3 · BFS visited set 未持久化，中断后全量重跑

**位置**：Task 5 GREEN 段 BFS 算法 L282-289

**问题**：

- `visited: set[int]` 只在内存——如果 BFS 处理到第 50 页（共 200 页）时进程中断/超时，**下次全量重跑**
- 对于大子树（200+ 子页），每次重跑都是重复工作，浪费 API 限速容量（Confluence Cloud 5000 req/h/user）
- M6 风险表已自警\"巨型子树\"——但没给缓解
- V1.1 整 space CQL 抓取（可能上万页）这个问题会严重 100 倍

**修改**（Task 5 GREEN 段 + Config 层）：

方案 A（轻量，推荐 M6 用）：在 `bfs_subtree` 内部 `try/finally` 把 `visited` 写临时文件：

```python
# M6 范围：简单 JSON 文件持久化
_VISITED_FILE = Path("data/confluence_bfs_visited.json")

async def bfs_subtree(self, root_page_id, *, max_depth=3) -> list[PageNode]:
    visited = set()
    # 恢复已访问 page（中断恢复）
    if _VISITED_FILE.exists():
        visited = set(json.loads(_VISITED_FILE.read_text()))
    try:
        # ... BFS 逻辑（现有）...
    finally:
        _VISITED_FILE.parent.mkdir(parents=True, exist_ok=True)
        _VISITED_FILE.write_text(json.dumps(list(visited)))
```

方案 B（M12 hardening 做）：用 Postgres 存 BFS 进度表——M6 不做。

**影响**：Config 加 `bfs_visited_file: str = "data/confluence_bfs_visited.json"`。Task 5 补 RED 测试 `test_bfs_resumes_from_visited_file`。

**新发现**。

---

### P1-4 · BFS asyncio.Queue 算法在 GREEN 段用 deque，不一致

**位置**：Task 5 GREEN 段 L277-289

**问题**：

- 代码伪代码用 `deque([(root_page_id, 0)])` 和 `queue.popleft()`——是同步 deque BFS
- 注释写 \"用 `asyncio.Queue` 实现真正的并发 BFS（不用 deque）\"
- 两者不一致：`asyncio.Queue` 是 async producer-consumer，不推荐做 BFS 遍历（需要用 `task_done` / `join` 模式）
- 实际 BFS 用 deque + semaphore 控制并发（sem 在 `get_page` 处）是正确选择——`asyncio.Queue` 会增加复杂性

**修改**：删注释\"用 asyncio.Queue 实现真正的并发 BFS\"，改为：

```python
# BFS 用 deque + asyncio.Semaphore 控制并发。
# 不用 asyncio.Queue——BFS 是单 producer 遍历，deque 更高效。
# 并发由 get_page 内的 self._page_semaphore 控制。
```

**影响**：零（注释修正）。

**新发现**。

---

### P1-5 · depth=0 行为未定义（max_depth=0 时走不召子页还是自身都不召）

**位置**：Task 5 GREEN 段 L280-290 BFS 算法

**问题**：

- `max_depth: int = 3`（默认 3）
- BFS 算法：`queue = deque([(root_page_id, 0)])` → yield root → `if depth >= max_depth: continue` → `if 0 >= 0: continue` → **root 被 yield 了但 children 全跳过**
- max_depth=0 时：只出 root 自己，不出任何子页——合理
- 但 **max_depth=None 或 -1**（\"不限深度\"）呢？plan 入口签名 `max_depth: int | None = None`——但 BFS 代码里 `if depth >= max_depth` 在 max_depth=None 时 `TypeError: '>=' not supported between instances of 'int' and 'NoneType'`

**修改**（Task 5 GREEN 段补边界处理）：

```python
async def bfs_subtree(self, root_page_id, *, max_depth=3) -> list[PageNode]:
    if max_depth is None:
        max_depth = float('inf')  # 不限深度
    if max_depth < 0:
        raise ValueError(f"max_depth must be >= 0 or None, got {max_depth}")
    ...
```

并在 Task 5 RED 段补 `test_bfs_with_max_depth_none` 和 `test_bfs_with_max_depth_0`。

**影响**：Task 5 RED 补 2 个测试。

**新发现**。

---

### P1-6 · process_confluence_page 修改 M4 pipeline 但未确认 M4 plan 兼容性（跨 M 契约风险）

**位置**：Task 11 GREEN 段 L424-430；Files 修改表 L188

**问题**：

- M6 plan 说在 `app/ingest/pipeline.py` 加 `process_confluence_page(page_body_html, meta) -> list[Element]`
- 但 **M4 plan 的元素分类实现（P0-1 元素分类）本身是 P0 待修状态**——M4 review 指出 M4 完全缺元素分类
- M4 plan 如果采用不同的元素分类策略（如走 LlamaIndex `BaseElementNodeParser`），M6 的 `process_confluence_page` 可能不兼容
- M6 用 BeautifulSoup 解析 Confluence storage HTML → 产三类元素（NarrativeText / Table / Image）→ 喂 M4 `process_elements`
- M4 review 建议走 `SimpleNodeParser`（LlamaIndex 原生）而非 `BeautifulSoup`——两者输出不一致

**修改**（在 Architecture 契约边界表 + Files 修改表补）：

```
契约边界补充（M6 → M4）：
- M6 产 Element 列表格式：list[dict] | list[BaseNode] —— 需与 M4 review P0-1 对齐
- M6 依赖 M4 pipeline 提供 `process_confluence_page_stub(page_body, meta) -> list[Element]`
- 若 M4 plan 未实现元素分类 → M6 需自己实现 fallback 元素分类器
```

并在风险表加一行：

| M4 元素分类未实现，M6 的 `process_confluence_page` 无兼容上游 | M6 自带 fallback 元素分类器（BeautifulSoup + `<p>/<table>/<ac:image>` 规则），不与 M4 耦合 | \"阻塞等 M4 完成\" — 拖累 M6 工期 |

**影响**：低——补充契约注释，不影响代码。

**新发现**。

---

### P1-7 · Confluence API v2 分页 `_links.next` 格式在不同 Cloud 版本不一致

**位置**：Task 4 GREEN 段 L259-260 分页 cursor

**问题**：

- Confluence API v2 分页 `_links.next` 的值在不同 Cloud 版本有差异：
  - **新版本**（2024+）：`"/wiki/api/v2/pages/{id}/children?cursor=abc"`
  - **旧版本**（2023）：`"/wiki/rest/api/content/{id}/child?start=10&limit=25"`（v1 REST 风格）
  - **Data Center 版**：`"/rest/api/v2/pages/..."`（路径不含 `/wiki`）
- plan 的 `list_children` 假设 `_links.next` 是相对路径（以 `/` 开头），用 `params={"cursor": cursor}` 传——这在新 Cloud 版本正确
- 但如果 `_links.next` 是完整 URL（旧版本）或含 `start/limit` 参数，cursor 方式不工作

**修改**（Task 4 GREEN 段补防御）：

```python
async def list_children(self, page_id: int) -> AsyncIterator[dict]:
    url = f"/wiki/api/v2/pages/{page_id}/children"
    while url:
        resp = await self._request("GET", url)
        data = resp.json()
        for result in data.get("results", []):
            yield result
        # 防御式处理 _links.next 格式变化
        next_link = data.get("_links", {}).get("next")
        if not next_link:
            break
        if next_link.startswith("http"):
            # 完整 URL → 只取 path
            from urllib.parse import urlparse
            next_link = urlparse(next_link).path + ("?" + urlparse(next_link).query if urlparse(next_link).query else "")
        if "?" in next_link:
            # start/limit 格式 → 转成 cursor
            url = f"/wiki/api/v2/pages/{page_id}/children"  # 重置 base
        else:
            url = next_link  # cursor 格式
```

并在 DoD 补：`list_children` 分页在 mock 环境下覆盖 URL 格式差异。

**影响**：Task 4 RED 测试补 `test_list_children_paginates_via_url` / `test_list_children_paginates_via_full_url`。

**新发现**。

---

### P1-8 · 附件下载缓存策略缺失——同一 attachment 被多个 page 引用时重复下载

**位置**：Task 7 全篇；Task 11 metadata

**问题**：

- Confluence page body 里 `<ac:image><ri:attachment ri:filename="logo.png"/></ac:image>` 引用 attachment
- 同一 attachment 可能被多个 page 引用（如公司 logo 在 10 个页面出现）
- `fetch_with_attachments` 对每个 page 独立调 `list_attachments` + `download_attachment`——**同一 attachment 下载 10 次**
- `payload_hash` 幂等是 job 级别，不解决**单次 ingest 内**的附件去重

**修改**（Task 7 GREEN 段 + fetch_with_attachments）：

```python
class ConfluenceClient:
    def __init__(self, ...):
        ...
        self._downloaded_set: set[str] = set()  # 记录已下载 att_id

    async def download_attachment(self, *, att_id: str, dest_path: Path) -> int | None:
        if att_id in self._downloaded_set:
            logger.debug("attachment already downloaded in this ingest", extra={"att_id": att_id})
            return 0  # 返回 0 表示已存在，不计入下载计数
        # ... 实际下载 ...
        self._downloaded_set.add(att_id)
```

并在 `IngestReport` 加 `attachments_deduplicated: int` 字段统计去重数。

**影响**：Task 7 RED 补 `test_download_same_attachment_once`。

**新发现**。

---

### P1-9 · ingest_confluence 函数签名未对齐 M8 契约（`auth` 参数类型未定）

**位置**：Task 18 GREEN 段 L527-530；Goal L24

**问题**：

- plan 定义 `ingest_confluence(space_key, page_id, auth, user_id, *, max_depth=3) -> IngestReport`
- 其中 `auth` 是 `ConfluenceAuth` 类型（含 `email` + `api_token`）
- M8 路由 POST `/api/ingest` 的 payload 是 JSON `{ source: "confluence", payload: { space_key, page_id, auth: { email, api_token } } }`
- M8 需要反序列化 JSON → M6 的 `ConfluenceAuth`——但 M6 plan **没定义 `ConfluenceAuth` 的 Pydantic schema 版本**
- `ConfluenceAuth` 被定义为 Python class，不是 Pydantic `BaseModel`——M8 路由无法 `ConfluenceAuth(**payload["auth"])`
- 如果 M8 路由用 `from app.ingest.sources.confluence import ConfluenceAuth`——但这不是 Pydantic，没 `.model_dump()` 和 `.model_validate()`

**修改**（Task 2 GREEN 段 `ConfluenceAuth` 改 Pydantic）：

```python
from pydantic import BaseModel, SecretStr

class ConfluenceAuth(BaseModel):
    """Confluence Cloud Basic auth（email + API token）。
    
    这是 Pydantic BaseModel——M8 路由直接 `ConfluenceAuth(**payload["auth"])` 反序列化。
    """
    email: str
    api_token: SecretStr

    def to_httpx(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(self.email, self.api_token.get_secret_value())

    def __repr__(self) -> str:
        return f"ConfluenceAuth(email='{self.email}', api_token='***')"
```

并在 Task 2 RED 段补 `test_auth_is_pydantic_model`。

**影响**：Task 2 RED 测试可能需调（Pydantic 默认用 `model_dump()` 而非 `__dict__`）。

**新发现**。

---

### P1-10 · 缺 Confluence body storage format 中 `<ac:structured-macro>` 等复杂标签处理

**位置**：Task 11 GREEN 段 L424-430

**问题**：

- Confluence Storage Format 不只有 `<p>` / `<table>` / `<ac:image>`——还含：
  - `<ac:structured-macro>`（如代码块、JIRA 引用、图表宏、任务列表）
  - `<ac:task-list>` / `<ac:task>`（Confluence 任务）
  - `<ac:plain-text-body>` 内嵌宏内容
  - `<ri:page ri:content-title="..."/>`（page 引用）
- `process_confluence_page` 用 BeautifulSoup 解析时：
  - `<ac:structured-macro>` 内容在 `<ac:plain-text-body><ac:parameter ac:name="body">` 内——不是自然文本，全部丢失
  - 代码块 `<ac:structured-macro ac:name="code">` 内的 `<ac:plain-text-body><![CDATA[...]]>` —— 也是代码内容，应保留
  - JIRA 表格引用 `<ac:structured-macro ac:name="jira">` → HTML 页面显示为 embed——内容完全不可索引

**修改**（Task 11 GREEN 段 + 风险表）：

```python
# process_confluence_page 增强
def _extract_macro_content(soup: BeautifulSoup) -> list[str]:
    """提取 Confluence macro 内的可索引文本。"""
    texts = []
    for macro in soup.find_all("ac:structured-macro"):
        name = macro.get("ac:name", "")
        # 代码块：取 ac:plain-text-body 内文本
        if name == "code":
            body = macro.find("ac:plain-text-body")
            if body:
                texts.append(body.get_text(strip=True))
        # TODO: 其他 macro 类型（jira / chart / expand）—— V1.1 实现
    return texts
```

并在风险表补：

| Confluence `storage` 格式含 `<ac:structured-macro>` 内容 | V1 只处理 `<p>/<table>/<ac:image>`，macro 内容丢失；风险接受，注释标注 V1.1 增强 | 全量解析 — 影响 M6 工期 |

**影响**：Task 11 RED 补测试 `<ac:structured-macro ac:name="code">` 内容被保留。

**新发现**。

---

### P1-11 · 单测 `test_confluence_auth.py` 缺 `PermissionDeniedError` 类型断言

**位置**：Task 9 RED 段 L368-380

**问题**：

- Task 9 RED 测试 `test_permission_denied_skips_page_and_continues` 断言 `report.permission_denied_count == 1`
- 但 **不断言** 异常具体是 `PermissionDeniedError` 还是 `ConfluenceAPIError`（status_code=401）
- 如果 Task 3 的 `_request` 抛的是通用 `ConfluenceAPIError(401)` 而不是 `PermissionDeniedError`，Task 9 的 skip 逻辑 `except PermissionDeniedError` **不会触发**——跳不过
- 缺少类型安全——断言的捕获依赖于异常类型精确匹配

**修改**（Task 3 GREEN 段 + Task 9 RED 段）：

Task 3 明确异常类型：

```python
class ConfluenceError(Exception): ...
class PermissionDeniedError(ConfluenceError): ...  # 401/403
class PageNotFoundError(ConfluenceError): ...      # 404
class ConfluenceAPIError(ConfluenceError): ...     # 其他 4xx
class ConfluenceServerError(ConfluenceError): ...  # 5xx
```

Task 9 RED 补：

```python
def test_permission_denied_raises_typed_error():
    """验证 401 抛 PermissionDeniedError（不是通用 ConfluenceAPIError）。"""
    respx_mock.get("...").mock(return_value=httpx.Response(401))
    with pytest.raises(PermissionDeniedError):
        await client.get_page(1)
```

**影响**：Task 3 RED 补 1 个测试。Task 9 已有测试不变。

**新发现**。

---

## P2 · 优化

### P2-1 · llama-index-readers-confluence 保留为依赖但 M6 主体自建 client——版本锁定应确认不存在内部 v2 REST 调用冲突

**位置**：Tech Stack L136-137；关键导入路径 L148-150

**问题**：

- `llama-index-readers-confluence==0.4.4` 作为依赖保留（仅类型/兼容性参考）
- 但 M6 自建 client 与 `ConfluenceReader` 内部实现可能冲突——当两个模块同时 import 会创建 2 个 `httpx.AsyncClient`、2 套 auth 逻辑
- 同一进程同时存在两套 Confluence client，可能相互干扰（环境变量、logger、事件循环）
- 建议把 `ConfluenceReader` 移出 `app/ingest/sources/confluence.py` 的 import 层，只在测试中 import

**修改**：
```python
# app/ingest/sources/confluence.py 不 import ConfluenceReader
# from llama_index.readers.confluence import ConfluenceReader  ← 删掉

# 只在类型注释中引用（TypeGuard 用）
# if TYPE_CHECKING:
#     from llama_index.readers.confluence import ConfluenceReader
```

**影响**：零。

---

### P2-2 · Mock Confluence server fixture 目录名 mid-plan 从 `mock_confluence` 改 `mock_confluence_fixtures`——需确认 DoD 和 Files 表一致

**位置**：Files 新增表 L173 `infra/mock_confluence/`；Task 13 L460-461 注释说改名 `mock_confluence_fixtures/`

**问题**：

- Files 表写 `infra/mock_confluence/`
- Task 13 注释说\"`infra/mock_confluence/` 改名为 `infra/mock_confluence_fixtures/`（仅静态文件）\"
- **不一致**——命名不统一，新人会创建错目录

**修改**：统一为 `infra/mock_confluence_fixtures/`（Files 表 L173 改名），Task 13 目录名保持一致。

**影响**：低。

---

### P2-3 · 19 个 Task 全标 2-5 分钟，但部分 Task 实际超（Task 11 含 RED×4 + GREEN×2 = 25-30 分钟；Task 14 含 2 个 RED + 完整 wiring = 30-40 分钟）

**位置**：Tasks 段 L193 标题\"（2-5 分钟/step 粒度）\"

**修改**：拆/标注：

| Task | 估时 | 说明 |
|------|------|------|
| Task 11（元数据 + 元素分类） | 25-30min | 4 个 RED + GREEN `process_confluence_page` + BeautifulSoup 解析 |
| Task 14（集成测试 wiring） | 30-40min | 串 BFS + attachments + pipeline + chunks 写入 |
| Task 5（BFS + 深度 + 循环 + 并发） | 20-25min | 4 个 RED + asyncio 并发控制 |
| Task 7（下载 + 流式 + 大小检查） | 20-25min | 3 个 RED + green 流式实现 |

---

### P2-4 · `ConfluenceClient._request` 未实现 retry 重定向（`follow_redirects=False` vs True）

**位置**：Task 3 GREEN 段 L236-238

**问题**：

- `httpx.AsyncClient(timeout=30.0, auth=auth.to_httpx())`——缺 `follow_redirects` 参数
- Confluence Cloud API **不应当返回 redirect**（v2 REST 端点设计），但如果配置了反向代理可能会
- 默认 `follow_redirects=False` → 302 时返回 302 body 而非目标内容——M6 不处理会抛意外错误
- 应显式设 `follow_redirects=True` + `max_redirects=3` 防御

**修改**：
```python
self._client = httpx.AsyncClient(
    timeout=30.0,
    auth=auth.to_httpx(),
    follow_redirects=True,
    max_redirects=3,
)
```

**影响**：微。

---

### P2-5 · `IngestReport` 缺 `total_pages_discovered` 和 `chunks_count` 字段，M8 路由进度查询需要

**位置**：Task 9 GREEN 段 L372-373

**问题**：

- M4 review P0-5 指出 `GET /api/ingest/{job_id}` 进度查询需要完整字段集
- `IngestReport` 当前字段：`pages_processed / attachments_downloaded / permission_denied_pages / oversized_skipped / errors / payload_hash`
- 缺 `total_pages_discovered`（BFS 总发现页数，含被跳过/无权限的）——前端进度条分母
- 缺 `chunks_count`（实际写入 chunks 表数）——与 M4 `IngestJob.chunks_count` 一致
- 缺 `duration_seconds`——前端预计剩余时间

**修改**：
```python
IngestReport = TypedDict("IngestReport", {
    "pages_processed": int,
    "pages_discovered": int,           # BFS 总发现
    "attachments_downloaded": int,
    "attachments_deduplicated": int,   # P1-8
    "permission_denied_pages": list[int],
    "oversized_skipped": int,
    "skipped_content_type": int,       # P0-2
    "chunks_count": int,               # 写入 chunks 表数
    "errors": list[str],
    "payload_hash": str,
    "duration_seconds": float,         # 任务运行秒数
})
```

**影响**：Task 9 签名和测试断言需更新。

---

### P2-6 · `testcontainers` 依赖未在 pyproject 声明

**位置**：Tech Stack L141-143（只列 `pytest-httpserver` / `aiohttp` / `respx`）

**问题**：

- 集成测试 `test_m6_ingest_confluence.py` 用 testcontainers 起真 PG 容器（P0-5 强制要求）
- `pyproject.toml` 依赖表只写了 `respx>=0.21`，**没写 `testcontainers[postgresql]`**
- 新人跑集成测试 `pytest tests/integration/` → `ModuleNotFoundError: No module named 'testcontainers'`

**修改**（Files 修改表 L187 补）：

```toml
[project.optional-dependencies]
dev = [
  # ...
  "testcontainers[postgresql]>=4.0,<5",
  "respx>=0.21",
  "pytest-httpserver>=1.1,<2",
]
```

---

### P2-7 · Integration test 在 CI 中需要 Docker——但 CI pipeline（M14）未配置

**位置**：测试策略 L542

**问题**：

- 集成测试标记 `--require-docker` 是自定义 marker——plan 没写如何实现
- CI GitHub Actions runner 默认没有 Docker socket，需显式配置 `services: docker` 或 `run-pytest-in-docker`
- plan 只写了\"需 docker compose up postgres\"，没给 CI 配置样例

**修改**：在测试策略段补：

```yaml
# .github/workflows/ci.yml（M14 范围，M6 仅记录契约）
# 集成测试步骤：
# - name: Start Docker services
#   run: docker compose -f infra/docker-compose.yml up -d postgres
# - name: Run integration tests
#   run: cd apps/rag_v1 && pytest tests/integration/ --require-docker -m integration
```

并在 `conftest.py` 加 `pytest_configure` 注册 `require-docker` marker，加 `pytest_collection_modifyitems` 检查 Docker 可用性。

**影响**：低——仅注释。

---

### P2-8 · pyproject.toml 依赖表只列 2 个新包，但需 append 到 M4/M5 已有列表——缺完整 toml 片段

**位置**：Files 修改段 L184-188

**问题**：

- 与 M5 review P2-4 同类问题——只写\"追加 `llama-index-readers-confluence==0.4.4` / `respx>=0.21`\"，没给完整 dependencies toml 片段
- 新人不知道是加到 `[dependencies]` 还是 `[optional-dependencies].dev` 还是加到哪个位置

**修改**：给完整片段：

```toml
# pyproject.toml（M6 追加）
dependencies = [
  # ... M0-M5 已有 ...
  "llama-index-readers-confluence==0.4.4",
]
[project.optional-dependencies]
dev = [
  # ... M0-M5 已有 ...
  "respx>=0.21",
  "pytest-httpserver>=1.1,<2",
  "testcontainers[postgresql]>=4.0,<5",
]
```

---

### P2-9 · 风险表缺 Confluence API v2 `GET /pages/{id}/attachments` 可能的 404/403 响应（当 page 无 attachments 或权限不足）

**位置**：风险表 L589-598

**问题**：

- 当前风险表 8 行，覆盖：限速、字段差异、内存压力、循环引用、token 泄露、并发顺序、M8 路由未实现、存储格式、payload_hash
- **缺**：`list_attachments` 对无附件 page 返回 404 的可能性——Confluence Cloud 在 page 无附件时可能返 404 而非空列表
- 缺：`list_attachments` 在 page 有 attachment 但用户有 page 读权限无附件下载权限时返 403
- 缺：BFS 过程中 `get_page(pid)` 返回 404（页面被删除但 children 列表仍引用）——当前只处理 401/403，404 未捕获

**修改**（风险表补 3 行 + Task 5 BFS 补 404 处理）：

```python
# bfs_subtree 内
try:
    page = await self.get_page(pid)
except PermissionDeniedError:
    report.permission_denied_pages.append(pid)
    continue
except PageNotFoundError:          # ← 新增
    report.errors.append(f"page {pid} not found (可能被删除)")
    continue
```

---

## 已有 review P0/P1 交叉验证

| 已有 review 项 | M6 状态 | 判定 |
|----------------|---------|------|
| **P0-1 端口 18080**（总 review） | M6 不涉及端口配置 | ✅ 不适用 |
| **P0-5 真 PG 集成测试**（总 review） | M6 测试策略 L542 强制 testcontainers 真 PG；DoD L566 注明 | ✅ **已修** |
| **P1-5 payload_hash UNIQUE**（总 review） | M6 Task 17 L521 显式依赖 `ingest_jobs.payload_hash UNIQUE` 约束 | ✅ **已修** |
| **M5 P0-1 SSRF redirect bypass** | M6 Confluence base_url 是配置化的（非用户输入），不涉及 SSRF redirect | ✅ 不适用 |
| **M5 P1-6 payload_hash 跨用户冲突** | M6 payload_hash 同样不含 `user_id`——**未同步修正** | ❌ **P0-1** |
| **M4 P0-1 元素分类** | M6 `process_confluence_page` 依赖 M4 元素分类——M4 review 指 M4 本空缺 | ⚠️ **P1-6** |
| **M4 P0-3 OpenSearch 写入层** | M6 不直接写 OpenSearch（写 chunks 表，M7 upsert） | ✅ 不适用 |
| **M3 P0-3 TEI dim 断言** | M6 不直接调 TEI（走 M4 pipeline） | ✅ 不适用 |
| **M2 P0-1 依赖版本漂移** | M6 依赖版本与 spec §8.2 对齐（llama-index-readers-confluence==0.4.4） | ✅ 无问题 |
| **X-1 config 拆分** | M6 `ConfluenceSettings` 放 `app/config.py`，未走 X-1 建议的 `app/configs/confluence.py` | ⚠️ 与已有 review 不一致，但 M6 独立 |

**总结**：P0-5/P1-5 已修；P0-1/P0-3/P0-4/P0-6/P0-7/P1-6（总 review）不适用或由其他 M 负责；**M5 P1-6 是唯一跨 M 已审但 M6 未同步的 P1**（升级为 P0-1）。

---

## 新发现摘要

上述 review 共发现 **3 个 P0 + 11 个 P1 + 9 个 P2**，其中关键项：

| # | 等级 | 概要 | 位置 |
|---|------|------|------|
| 1 | **P0-1** | payload_hash 不含 user_id → 跨用户冲突（M5 P1-6 未同步） | Task 12 |
| 2 | **P0-2** | 缺附件 Content-Type 过滤 → exe/zip 进索引不可解析 | Task 6-8 |
| 3 | **P0-3** | 附件下载超时未隔离 → 慢连接挂死 BFS + semaphore 饥饿 | Task 3/7 |
| 4 | P1-1 | 缺 labels/tags 元数据 | Task 11 |
| 5 | P1-2 | 缺 page version / last modifier 元数据 | Task 11 |
| 6 | P1-3 | BFS visited set 未持久化 → 中断全量重跑 | Task 5 |
| 7 | P1-4 | BFS asyncio.Queue vs deque 算法不一致 | Task 5 |
| 8 | P1-5 | max_depth=None → TypeError 未处理 | Task 5 |
| 9 | P1-6 | process_confluence_page 修改 M4 pipeline 未确认兼容性 | Task 11 |
| 10 | P1-7 | API v2 分页 _links.next 格式在不同 Cloud 版本不一致 | Task 4 |
| 11 | P1-8 | 附件下载去重缺失（同一附件多 page 引用重复下载） | Task 7 |
| 12 | P1-9 | ConfluenceAuth 非 Pydantic → M8 路由无法反序列化 | Task 2 |
| 13 | P1-10 | `<ac:structured-macro>` 等复杂标签内容丢失 | Task 11 |
| 14 | P1-11 | PermissionDeniedError 缺类型断言安全 | Task 3/9 |

---

## 落地建议

1. **优先级**：先修 P0-1（payload_hash 加 user_id）→ P0-2（Content-Type 过滤）→ P0-3（下载超时隔离），三者互不阻塞，可并行
2. **同步确认 M4 pipeline 状态**：在 `process_confluence_page` 实现前确认 M4 的元素分类方案，避免两边各自实现两套
3. **M6 估时调整**：当前 5 个工作日（19 个 Task），修完上述 3 P0 + 11 P1 后约 7-8 个工作日（增加 Task 1-2 天 + 测试补全 1-2 天）
4. **V1.1 预留**：p1-3（visited 持久化）在 M12 hardening 强化；P2-7（CI Docker）在 M14 实现；P1-1/P1-2（labels/version）标记 V1.1 增量检出

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M6-review-r0 | 2026-06-11 | 初稿（独立 review，3 P0 + 11 P1 + 9 P2 + 交叉验证） |
