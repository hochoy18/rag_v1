# M6 Plan r2 Review · r1 修复验证

> 评审对象：`2026-06-11-rag-m6-ingest-confluence.md`（v r1，1158 行）
> 评审基线：`reviews/2026-06-11-rag-m6-ingest-confluence-review.md`（r1，862 行，3 P0 + 11 P1 + 9 P2 = 23 项）
> 上游基线：M0/M1/M3/M4/M5 r2 review（已修）+ M5 r2 NP-1~5（揭示 M5 r1 异常类未与 M4 exceptions.py 对齐 + 4 auth 互斥测试缺）
> 下游契约：M8 api-chat（已修）/ M11 eval-ragas（已修）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立 r2 审查）
> 范围：验 r1 修复是否到位 + 发现 r1 引入的新问题

---

## 总评

M6 plan r1 修订**修复完成度极高**——风险表 17 行 "P? 已修" + plan 主体 23 行 r1-2026-06-11 修订记录 + DoD 23 条同步补全，**主体同步率 ≈ 100%**（r1 review 提出的 23 项 P0/P1/P2 在 plan 主体均有对应 GREEN 段 + RED 测试 + 修订记录）。技术深度仍居 RAG V1 单 M plan 之首。

但 r1 修复**复刻了 M5 r1 的同类遗留**（M5 r2 NP-1~5 揭示的"异常类分散 / 防御代码有 bug / cosmetic r1 修订行 / 复用接口未真 import"），并**新增 5 个独立问题**（NP-A 异常类在 confluence.py 内未与 M4 exceptions.py 对齐 / NP-B `_links.next` start-limit 分页死循环 / NP-C 17 行 r1 修订 "曾被否决的替代方案" 列无意义 / NP-D M5 复用接口只写"复用"未真 import / NP-E Confluence page body 25MB 限制未考虑）。**其中 NP-A、NP-B 是阻塞级**（NP-A 重复 M5 r2 NP-5；NP-B 触发 BFS 死循环），NP-C~E 是 cosmetic / 工程化级别。

| 维度 | 评分 | 说明 |
|------|------|------|
| r1 修复完成度 | ⭐⭐⭐⭐⭐ | 23 项 r1 标记全部在 plan 主体（Task / Files / DoD / 风险表 / 修订记录）找到对应实现；RED-GREEN 测试齐全 |
| 主体同步率 | ⭐⭐⭐⭐⭐ | r1 review 的 23 项 100% 落地，无遗漏；P0-1 同步 M5 P1-6 跨用户 hash 修复；P1-11 异常类 4 个 type 全在 Task 3 显式抛 |
| BFS 安全性 | ⭐⭐⭐⭐ | visited 持久化 + deque 注释修正 + max_depth 边界 + 404 跳过全到位；但 **NP-B start-limit 分页代码实际会死循环**（cursor 丢失） |
| 跨 M 一致性 | ⭐⭐⭐ | M0/M1/M3/M4/M8/M11 契约清晰；但 **M5 复用接口 `assert_safe_url` / `validate_url_format` / `load_auth_config` 只写"复用"未真 import**（M5 r2 NP-3 同类）；**异常类分散在 confluence.py 内**（M5 r2 NP-5 同类） |
| 风险表补全质量 | ⭐⭐⭐ | 17 行 r1 修复条目完整但"曾被否决的替代方案"列全写 `r1-2026-06-11` 无意义（M5 r2 NP-4 同类 cosmetic） |
| 代码细节正确性 | ⭐⭐⭐ | 主体正确，但 P1-7 `_links.next` start-limit 分页防御有逻辑 bug；P1-3 SqliteVisitedStore 持久化与 visited_file 路径耦合无清理接口 |

**一句话**：M6 r1 **修复彻底、覆盖全面**，是 RAG V1 当前 8 份 M plan 中 r1 修复质量最高的一份（与 M4 r1 修复质量并列）；**但复刻 M5 r1 缺陷**（异常类分散 / 4 处 cosmetic / 防御代码有 bug），需 r2 修 5 个新问题（NP-A~E）后即可动手。

---

## 1. r1 修复验证（23 项逐项）

> 验证方法：每项在 plan 主体（Task / Files / DoD / 风险表 / 修订记录）找 4 类证据——(a) Task 编号 + RED 测试名、(b) GREEN 段代码片段、(c) DoD 条目、(d) 修订记录 r1-2026-06-11 行。证据齐 = ✅，部分缺 = ⚠️，缺/有 bug = ❌。

| r1 标记 | 修复内容 | 实际验证 | 状态 |
|---------|---------|---------|------|
| **P0-1** | `payload_hash = sha256(space_key + root_page_id + auth_email + user_id)` | (a) Task 12 L790-816；(b) GREEN `compute_payload_hash(*, space_key, root_page_id, auth_email, user_id)` L796-806；(c) DoD L1040；(d) 修订记录 L1136 | ✅ |
| **P0-2** | `INDEXABLE_MIME_PREFIXES` 白名单（text/* / pdf / image/* / Office） | (a) Task 6 L539-581；(b) GREEN 白名单 L548-575；(c) DoD L1038；(d) 修订记录 L1137 | ✅ |
| **P0-3** | 独立 `download_semaphore(2)` + `download_timeout(120s)` | (a) Task 3 L320-352 + Task 7 L583-625；(b) GREEN `self._download_semaphore = asyncio.Semaphore(settings.download_concurrency)` L330-331；(c) DoD L1039；(d) 修订记录 L1138 | ✅ |
| **P1-1** | `metadata.labels: list[str]` 防御式 | (a) Task 11 RED `test_metadata_includes_labels` L739-741；(b) GREEN `"labels": [label["name"] for label in page.get("labels", []) or []]` L730；(c) DoD L1044；(d) 修订记录 L1139 | ✅ |
| **P1-2** | `metadata.version` / `last_modified_by` / `last_modified_at` | (a) Task 11 RED `test_metadata_includes_version` L743-745；(b) GREEN 三字段 L732-734；(c) DoD L1044；(d) 修订记录 L1140 | ✅ |
| **P1-3** | `SqliteVisitedStore` 持久化到 `data/confluence_bfs_visited.json` | (a) Task 5 RED `test_bfs_resumes_from_visited_file` / `test_bfs_persists_visited_file` L514-521 + Task 20 L924-958；(b) GREEN `SqliteVisitedStore` 类 L935-957 + BFS 入口恢复 + finally 持久化 L458-490；(c) DoD L1045；(d) 修订记录 L1141 | ✅ |
| **P1-4** | BFS deque + 注释修正（不用 asyncio.Queue） | (a) Task 5 BFS 算法 L464-490；(b) GREEN docstring 注释 "BFS 用 deque + asyncio.Semaphore 控制并发；不用 asyncio.Queue" L443-446；(c) DoD 隐含；(d) 修订记录 L1142 | ✅ |
| **P1-5** | `max_depth=None` → `float('inf')`；`=0` 只 yield root；负数 `ValueError` | (a) Task 5 RED 3 个测试 L494-505；(b) GREEN `if max_depth is None: max_depth = float('inf'); if max_depth < 0: raise ValueError` L452-456；(c) DoD L1030；(d) 修订记录 L1143 | ✅ |
| **P1-6** | M6 自带 BeautifulSoup fallback 元素分类器（不与 M4 耦合） | (a) Task 11 GREEN `process_confluence_page` L756-783；(b) "M6 自带 fallback 元素分类器（BeautifulSoup 解析 `<p>/<table>/<ac:image>/<ac:structured-macro ac:name="code">`）" L137；(c) DoD L1042；(d) 修订记录 L1144 | ✅ |
| **P1-7** | `list_children` `_links.next` 4 种格式兼容 | (a) Task 4 RED 3 个测试 L373-419；(b) GREEN 防御式代码 L379-403；(c) DoD L1032；(d) 修订记录 L1145 | ⚠️ **代码有 bug**（见 NP-B） |
| **P1-8** | `ConfluenceClient._downloaded_set` 附件去重 + `IngestReport.attachments_deduplicated` | (a) Task 7 RED `test_download_same_attachment_once` L633-635；(b) GREEN 入口查重 + 计数 L593-598；(c) DoD L1031；(d) 修订记录 L1146 | ✅ |
| **P1-9** | `ConfluenceAuth` 改 Pydantic `BaseModel` + `SecretStr` | (a) Task 2 L278-310；(b) GREEN `class ConfluenceAuth(BaseModel)` L290-300 + `__repr__` redact L306 + `is_pydantic_model` 测试 L308-310；(c) DoD L1034；(d) 修订记录 L1147 | ✅ |
| **P1-10** | `<ac:structured-macro ac:name="code">` 内 `<ac:plain-text-body>` 文本提取 | (a) Task 11 RED `test_process_confluence_page_extracts_code_macro` L785-787；(b) GREEN `for macro in soup.find_all("ac:structured-macro"): if macro.get("ac:name") == "code": body = macro.find("ac:plain-text-body")` L766-770；(c) DoD L1043；(d) 修订记录 L1148 | ✅ |
| **P1-11** | 异常继承链 typed 异常 + 单测 | (a) Task 3 RED `test_permission_denied_raises_typed_error` L360-362 + `test_404_raises_page_not_found_error` L364-366；(b) GREEN `_request` 分支 4 个 typed raise L341-351；(c) DoD L1029；(d) 修订记录 L1149 | ⚠️ **类定义位置未明示**（见 NP-A） |
| **P2-1** | `ConfluenceReader` 仅 `TYPE_CHECKING` 引用 | (a) 关键导入路径 L172-198；(b) `if TYPE_CHECKING: from llama_index.readers.confluence import ConfluenceReader  # noqa: F401` L176-178；(c) Files 修改 L254 "不 import `ConfluenceReader`"；(d) 修订记录 L1150 | ✅ |
| **P2-2** | `infra/mock_confluence_fixtures/` 统一目录名 | (a) Files L224 + 仓库布局 L71-81；(b) 目录名一致 `infra/mock_confluence_fixtures/`；(c) Task 13 L822-831；(d) 修订记录 L1151 | ✅ |
| **P2-3** | 估时 5d → 7-8d + Task 粒度拆分 | (a) L7 头部估时 "7-8 个工作日"；(b) L260 "2-5 分钟/step 粒度，7-8 个工作日排程"；(c) Task 5/7/11/14 估时细分；(d) 修订记录 L1152 | ✅ |
| **P2-4** | `follow_redirects=True` + `max_redirects=3` | (a) Task 3 GREEN L325-328；(b) `follow_redirects=True, max_redirects=3` L326-327；(c) DoD 隐含；(d) 修订记录 L1153 | ✅ |
| **P2-5** | `IngestReport` 补 5 字段 | (a) Task 9 GREEN TypedDict L677-689；(b) 字段：pages_discovered / chunks_count / duration_seconds / skipped_content_type / attachments_deduplicated；(c) DoD 隐含；(d) 修订记录 L1154 | ✅ |
| **P2-6** | pyproject dev 加 `testcontainers[postgresql]` | (a) Files L239 + Tech Stack L166；(b) dev 块 L1004 `testcontainers[postgresql]>=4.0,<5`；(c) DoD L1050；(d) 修订记录 L1155 | ✅ |
| **P2-7** | CI Docker 契约 + `require-docker` marker | (a) Task 21 L960-972；(b) `.github/workflows/ci.yml` 契约样例 L963-970 + `conftest.py` marker L972；(c) DoD 隐含；(d) 修订记录 L1156 | ✅ |
| **P2-8** | pyproject.toml 完整 toml 片段 | (a) Task 22 L974-1006；(b) 完整 `[project]` + `[project.optional-dependencies]` 片段 L978-1006；(c) DoD L1050；(d) 修订记录 L1157 | ✅ |
| **P2-9** | 404 `PageNotFoundError` + BFS 跳过 | (a) Task 5 RED `test_bfs_skips_404_page_and_continues` L523-526；(b) GREEN `except PageNotFoundError: report["errors"].append(...); continue` L474-476 + Task 3 抛 `PageNotFoundError(url, resp.text)` L344；(c) DoD L1030；(d) 修订记录 + 风险表 L1104 | ✅ |

**统计**：23 项 r1 修复中 **21 项完全到位**（✅），**2 项有缺陷**（⚠️）：
- **P1-7**（_links.next 4 格式）：GREEN 段代码实现 start-limit 分页时 `url = base_url` 丢失 cursor 参数 → 死循环
- **P1-11**（typed 异常）：Task 3 GREEN 段直接 `raise PermissionDeniedError(...)` 但**类定义位置 plan 未明示**（无 import / 无 class 定义段）——实际编码时易直接在 confluence.py 顶部定义，复刻 M5 r2 NP-5 错

---

## 2. r1 修复引入的新问题

### NP-A · P1-11 异常类未与 M4 `app/ingest/exceptions.py` 对齐（**M5 r2 NP-5 同类重蹈** · P1 阻塞级）

**位置**：Task 3 GREEN 段 L338-351 `_request` 内 `raise PermissionDeniedError(...)` / `raise PageNotFoundError(...)` / `raise ConfluenceServerError(...)` / `raise ConfluenceAPIError(...)` + 风险表 L1091 "异常继承链 `ConfluenceError > {...}`"

**问题**：
- M4 r1 review P1-6 已建 `app/ingest/exceptions.py`（M4 plan 修订记录显示），定位为**所有 ingest 子模块异常基类统一出口**
- M5 r1 修了 P0-2/P1-1/P2-2 引入 3 个新异常类（`URLFormatError` / `UnsafeURLError` / `RetryableHTTPError`）——但**仍分散定义**在 `app/ingest/ssrf.py` / `app/ingest/sources/url.py`，M5 r2 NP-5 揭示为新问题
- M6 r1 修了 P1-11 引入 5 个新异常类（`ConfluenceError` 基类 + 4 子类）——**计划放在哪？** plan **完全没有 import 段、没有 class 定义段**，只写"异常继承链"在风险表
- 实际编码时两个最可能路径：
  1. 全部定义在 `app/ingest/sources/confluence.py` 顶部（→ **M5 NP-5 同类错**）
  2. 散在 Task 3 / Task 9 各段（→ 更糟，类可能重复定义）

**修改**（r2 修复）：

```python
# app/ingest/exceptions.py（M6 r2 追加 5 个类）
class ConfluenceError(IngestError):
    """Confluence 相关异常基类。"""
    pass

class PermissionDeniedError(ConfluenceError):
    """401/403 — BFS 跳过该 page。"""
    pass

class PageNotFoundError(ConfluenceError):
    """404 — page 不存在或被删除，BFS 计入 errors 继续。"""
    pass

class ConfluenceServerError(ConfluenceError):
    """5xx — 服务器错误，可重试。"""
    pass

class ConfluenceAPIError(ConfluenceError):
    """其他 4xx — 客户端错误，不可重试。"""
    pass
```

并在 Task 3 GREEN 段头部加 `from app.ingest.exceptions import ConfluenceError, PermissionDeniedError, PageNotFoundError, ConfluenceServerError, ConfluenceAPIError`；风险表 L1091 改"异常继承链 `IngestError > ConfluenceError > {...}`"并加"统一在 `app/ingest/exceptions.py` 定义（M5 r2 NP-5 同步修正）"。

**影响**：Task 3 GREEN 代码段加 1 行 import；风险表改 1 行；M5 r2 NP-5 同步修。

**与 M5 r2 NP-5 联动**：r2 同时修 M5 + M6 异常类对齐到 `app/ingest/exceptions.py`，避免后续 M7/M8/M9 复用时找不到基类。

---

### NP-B · P1-7 `_links.next` start-limit 分页防御代码实际会死循环（**真实 bug** · P0 阻塞级）

**位置**：Task 4 GREEN 段 L398-402

**问题**：
```python
# 原文 L398-402
if "start=" in next_link and "limit=" in next_link:
    # start/limit 格式（v1 REST 风格） → 转 cursor
    url = base_url  # ← base_url 不含 cursor 参数
else:
    url = next_link  # cursor 格式
```

- 实际 `base_url` 定义在 L383：`base_url = f"/wiki/api/v2/pages/{page_id}/children"`——**纯路径，无任何 query**
- 当 `_links.next` 返回 `/wiki/api/v2/pages/1/children?start=10&limit=25`（v1 REST 风格）
- 命中 start-limit 分支 → `url = base_url = "/wiki/api/v2/pages/1/children"`（**丢 start/limit 参数**）
- 下一轮请求 `/wiki/api/v2/pages/1/children` → 服务端**返第 1 批**（不是 start=10 那批）→ `_links.next` 仍带 start=10 → 死循环
- **真实 BFS 死循环**——慢连接 + 浪费 API 限速容量

**完整 URL 分支也有 bug**（L393-397）：`if next_link.startswith("http"):` → 取 `path + query` → **未走 start-limit 检测**——可能落入 cursor 分支 `url = next_link` 但带 start/limit query → 同样问题

**修改**（r2 修复）：

```python
async def list_children(self, page_id: int) -> AsyncIterator[dict]:
    base_url = f"/wiki/api/v2/pages/{page_id}/children"
    url: str | None = base_url
    while url:
        resp = await self._request("GET", url)
        data = resp.json()
        for result in data.get("results", []):
            yield result
        # review P1-7 + r2 NP-B：4 种格式防御
        next_link = (data.get("_links") or {}).get("next")
        if not next_link:
            break
        if next_link.startswith("http"):
            # 完整 URL → 只取 path + query
            parsed = urlparse(next_link)
            query = f"?{parsed.query}" if parsed.query else ""
            next_link = f"{parsed.path}{query}"
        if "start=" in next_link and "limit=" in next_link:
            # start/limit 格式（v1 REST 风格）→ v2 不支持，抛错或重写
            # 方案 A：转 v2 cursor（如果知道 start→cursor 映射）
            # 方案 B：抛 ConfluenceAPIError 终止
            raise ConfluenceAPIError(
                f"Confluence v2 API 不支持 start/limit 分页（got {next_link}）；"
                "该 Cloud 版本过旧，建议升级或降级到 v1 REST"
            )
        else:
            url = next_link  # cursor 格式
```

并在 Task 4 RED 段补 `test_list_children_start_limit_raises_error`（mock start-limit 响应 → 断言抛 `ConfluenceAPIError`，不进入死循环）。

**影响**：Task 4 GREEN 段加 8 行；RED 段加 1 测试；DoD L1032 补 "start-limit 抛 typed 错误而非死循环"。

**与 M5 r2 NP-1 联动**：M5 r2 NP-1 揭示 "URLFormatError 与 UnsafeURLError 都是 ValueError 子类，调用方区分需 isinstance"——M6 此 bug 同样是 "防御代码实现了但有 bug" 同类，需 r2 同步修。

---

### NP-C · 风险表 17 行 r1 修复条目 "曾被否决的替代方案" 列写 `r1-2026-06-11` 无意义（**M5 r2 NP-4 同类 cosmetic** · P3）

**位置**：风险表 L1105-1127 共 17 行

**问题**：
```
| **P0-1 已修：payload_hash 加 user_id**（review P0-1） | r1-2026-06-11 | |
| **P0-2 已修：INDEXABLE_MIME_PREFIXES 白名单**（review P0-2） | r1-2026-06-11 | |
| ... 17 行都一样
```

- "曾被否决的替代方案"列**所有 17 行**都写 `r1-2026-06-11`——无任何"被否决方案"信息
- 与原 6 行风险表对比（如 L1072 "不限速" / L1073 "退回 v1 REST" / L1074 "全部加载到内存再写"），原风险有实质内容，r1 修复行只有日期
- M5 r2 NP-4 同类问题：M5 r1 4 行 cosmetic bug

**修改**（r2 修复）：
- 17 行 r1 修复条目**整体从风险表删除**（修订记录 L1136-1158 已经有 23 行同等内容，重复）
- 或保留但 "曾被否决的替代方案" 列填**实际被否决的方案**（如 P0-1 填"只含 email 跨用户冲突"、P0-2 填"全部下载"、P0-3 填"共享 semaphore+timeout 慢连接挂死"——这些其实在原 P0 风险行已写）

**影响**：风险表 17 行清理；或修订记录精简；纯 cosmetic 不影响代码。

---

### NP-D · M5 复用接口 `assert_safe_url` / `validate_url_format` 只写"复用"未真 import（**M5 r2 NP-3 同类** · P2）

**位置**：Architecture 契约边界表 L132 "M5 auth | 复用 `app/ingest/auth.py:assert_safe_url`（防御性，base_url 是配置化的）" + 风险表 L1064 "M5 httpx 重试模式（429 指数退避参考）+ M5 `app/ingest/auth.py:assert_safe_url`（防御性引用）"

**问题**：
- plan **3 处**提到复用 M5 `assert_safe_url`，但**没有 1 处真 import**
- M5 r2 NP-3 揭示："`SSRFRedirectTransport` 语义未在 DoD 显式标注，M6 复用时易踩坑"——M6 plan 同样未在 DoD 标注 SSRF 防御点
- 实际编码时易出现：
  1. 完全忘复用（自写 SSRF 防御）→ 重复 M5 错
  2. 复用但不 import（doctring 写但代码没调）→ 文档/代码脱节

**修改**（r2 修复）：
- Tech Stack "关键导入路径" 段 L172-198 加：
  ```python
  # M5 复用：SSRF 防御（M5 r2 NP-3 同步）
  from app.ingest.auth import load_auth_config, to_httpx_kwargs  # noqa: F401
  from app.ingest.ssrf import assert_safe_url, validate_url_format, SSRFRedirectTransport  # noqa: F401
  ```
- DoD 加 1 条："M6 启动时 `assert_safe_url(settings.base_url)` 校验配置化 base_url（非用户输入也防御）"
- 风险表 L1064 "M5 httpx 重试模式... `assert_safe_url`（防御性引用）" 改 "M5 复用 4 个公开 API：load_auth_config / to_httpx_kwargs / assert_safe_url / validate_url_format（r2 NP-D 显式 import）"

**影响**：Tech Stack 段加 1 import 段；DoD 加 1 条；风险表改 1 行。

**与 M5 r2 NP-3 联动**：M5 + M6 r2 同步在 DoD 标注 SSRF 防御点。

---

### NP-E · Confluence page body 25MB 限制未考虑（**新发现** · P2）

**位置**：plan 全文（grep "25MB\|page.*size\|body.*size" 0 命中）

**问题**：
- Confluence Cloud 单 page body（storage format）上限 **25MB**（v2 REST 限制）
- M6 `get_page(pid, *, body_format="storage")` → 响应 body 可能 25MB
- `httpx.AsyncClient` 默认 `read=30s` + `max_keepalive_connections=20`——25MB body 在 1Gbps 内网约 200ms，但慢连接 5Mbps → 40s
- **可能触发 read timeout** → `TimeoutException` → 计入 `errors`，但实际 page 是正常的
- attachment 50MB 限制有，page body 25MB 限制无——**遗漏**
- 真实场景：meeting notes 含大量截图 / 完整 API 文档 / 内嵌 SVG 大型图表 → page body 超 10MB 常见

**修改**（r2 修复）：
- `ConfluenceSettings` 加：`max_page_body_bytes: int = 26214400`（25MB）+ `page_body_read_timeout_seconds: int = 60`（独立于 page GET 30s 读超时）
- Task 3 GREEN `ConfluenceClient.__init__` 加 `self._page_timeout = httpx.Timeout(connect=20.0, read=settings.page_body_read_timeout_seconds, ...)`
- Task 3 RED 加 `test_oversized_page_body_truncates_or_warns`（mock 25MB+1 响应 → 断言不抛 / 计入 `oversized_page_bodies` 统计）
- `IngestReport` 加 `oversized_page_bodies: int` 字段
- 风险表加 1 行："**Confluence page body 25MB 限制**（review r2 NP-E）| `max_page_body_bytes=26214400` + `page_body_read_timeout=60s` 独立配置；超限截断 + 计入 `oversized_page_bodies`"

**影响**：`ConfluenceSettings` 多 2 字段；Task 3 多 1 测试；`IngestReport` 多 1 字段；风险表多 1 行。

---

### NP-F · P1-3 `SqliteVisitedStore` 无 `clear()` / `remove()` 接口 + 与 `bfs_visited_file` JSON 路径并存（**新发现** · P2）

**位置**：Task 5 BFS L458-490（用 `data/confluence_bfs_visited.json` JSON 文件）+ Task 20 L924-958（独立 `SqliteVisitedStore` 类）

**问题**：
- plan 同时定义**两套** visited 持久化机制：
  1. BFS 函数内 `if visited_file and Path(visited_file).exists(): visited = set(json.loads(...))` —— JSON 文件
  2. 独立 `SqliteVisitedStore` 类，init 参数 `db_path: str | Path`——SQLite 数据库
- 但 BFS 代码用 JSON（`Path(visited_file).write_text(json.dumps(list(visited)))`）——**`SqliteVisitedStore` 实际未被 BFS 调用**
- 实际 M6 plan `bfs_subtree` 签名 `visited_file: str | None = None` 接的是 JSON 路径，不是 `SqliteVisitedStore`
- `SqliteVisitedStore` 类是**死代码**——只写了类 + 单测，BFS 没用

- 此外 `SqliteVisitedStore` 缺 `clear()` / `remove(page_id)` / `count()` 接口——单 ingest 完成后无法清理

**修改**（r2 修复，二选一）：

**方案 A（推荐，简洁）**：删 `SqliteVisitedStore`，BFS 用 JSON 路径即可（M6 简单场景，SQLite 过重）：
- Task 20 整段删除 `app/ingest/visited_store.py` + `tests/unit/test_confluence_visited_store.py`
- Files L217 / L222 删除对应行
- 仓库布局 L56 / L66 删除对应行
- 风险表 17 行 r1 修复 "P1-3 已修：SqliteVisitedStore 持久化" 改 "P1-3 已修：BFS visited JSON 文件持久化"

**方案 B（保留，完整）**：BFS 改用 `SqliteVisitedStore`，JSON 路径废弃：
- Task 5 GREEN `bfs_subtree` 加 `store = SqliteVisitedStore(visited_file) if visited_file else None`
- `bfs_subtree` 入口 `if store: visited = store.all()`；循环内 `store.add(pid)`；finally `store.flush()`
- `SqliteVisitedStore` 加 `clear()` / `remove(page_id)` / `count()` 接口 + 补 RED 测试

**影响**：方案 A 删 ~50 行 + 1 个文件；方案 B 改 ~30 行 + 补 3 接口。**推荐 A**——M6 单进程单 ingest，SQLite 优势不大，JSON 简单清晰。

---

## 3. 跨 M 一致性检查（M0/M1/M3/M4/M5/M7/M8/M11）

| 维度 | M6 现状 | 对比基线 | 判定 |
|------|---------|---------|------|
| **M0 healthcheck** | 无显式引用 M0 healthcheck | M0 r2 已修（postgres / os / tei 服务就绪） | ✅ 不适用（M6 集成测试依赖 testcontainers 起 PG，不依赖 M0 healthcheck） |
| **M0 TEI 端口 18080** | M6 不直连 TEI | M3 r2 已修 TEI 18080 | ✅ 不适用 |
| **M1 schema `ingest_jobs.payload_hash` UNIQUE** | L130 显式依赖 + L899 重复强调 | M1 r2 已补 partial unique index（仅未 revoke + 未 hard-expire 唯一） | ✅ 一致；M6 plan L903-904 `test_different_users_create_different_jobs` 验证 UNIQUE 行为正确 |
| **M1 schema `chunks` 表** | L1061 "chunks 表 + ingest_jobs 表" | M1 r2 已修 | ✅ 一致 |
| **M1 `is_revoked` / `expires_at_hard`** | 无引用 | M1 r2 补字段（V1 暂未用） | ✅ 不适用（M6 不涉及 session / token 生命周期） |
| **M3 `TEIEmbedder.EmbeddingDimMismatch`** | L131 / L1062 显式标注 "M3 review P0-3 `EmbeddingDimMismatch` 硬断言对接" | M3 r2 已修 | ✅ 一致 |
| **M4 `app/ingest/exceptions.py`** | **未引用**（NP-A） | M4 r1 review P1-6 已建 | ❌ **NP-A**：M5 r2 NP-5 + M6 r1 同一错 |
| **M4 `pipeline.process_elements` / `process_confluence_page`** | L54 / L104 / L128 显式引用 | M4 r1 P0-1 元素分类已修 + r2 22 项待续 | ✅ 一致；M6 P1-6 自带 fallback 元素分类器不与 M4 耦合 |
| **M4 OpenSearch 写入** | M6 不直连 OpenSearch（M7 upsert） | M4 r2 P0-3 INDEX_MAPPING 已修 + P1-5 RUNNING 状态机已修 | ✅ 一致 |
| **M4 `ImageRef` 路径** | L736 `if att_path: meta["attachment_filename"] = att_path.name` | M4 r2 揭示 `artifacts/{doc_id}/attachments/` | ⚠️ **次要标注**：M6 `att_path` 来源未明示（是 `ingest_confluence` 内固定路径还是参数？），未与 M4 `artifacts/{doc_id}/attachments/` 对齐标注——**未发现明确 bug**，但 V1.1 整 space 时需统一 |
| **M4 `OversizedFileError` / `UnsupportedFileTypeError` / `ParseError`** | M6 `IngestReport.oversized_skipped` / `skipped_content_type` 复用同名 | M4 r1 P1-6 exceptions 已建 | ✅ 一致（M6 不重定义，统计字段名对齐） |
| **M5 `app/ingest/auth.py:assert_safe_url`** | L132 / L1064 写"复用"但**未真 import**（NP-D） | M5 r2 NP-3 揭示同类 | ❌ **NP-D** |
| **M5 `app/ingest/ssrf.py:validate_url_format` / `SSRFRedirectTransport`** | 未引用 | M5 r2 已修 | ❌ **NP-D** 同类 |
| **M5 `app/ingest/auth.py:load_auth_config` / `to_httpx_kwargs` / `AuthType`** | 未引用 | M5 r2 NP-1~2 揭示 4 auth 模式互斥测试缺 | ❌ **NP-D** 同类 + ⚠️ M6 只用 Basic auth（email+token），**未考虑 M5 的 4 auth 模式（basic/bearer/digest/oauth）**——M6 plan 自建 `ConfluenceAuth(BaseModel)` 只含 email+api_token 字段，**与 M5 4 auth 模式不联动** |
| **M5 P1-6 跨用户 hash** | M6 P0-1 已同步修（L1136 修订记录） | M5 r1 已修 | ✅ 已同步 |
| **M5 NP-1 `URLFormatError` / `UnsafeURLError` 区分** | 不适用（M6 不调 M5 URL 解析） | M5 r2 NP-1 揭示 | ✅ 不适用 |
| **M5 NP-2 4 auth 模式互斥** | **M6 自建 `ConfluenceAuth` 不复用 M5 `AuthType` 4 模式** | M5 r2 NP-2 揭示 | ⚠️ **跨 M 偏离**：M6 1 auth 模式 vs M5 4 auth 模式——M6 决策是"V1 Confluence Cloud 只支持 Basic"（合理），但未在 plan 标注"M6 与 M5 auth 解耦，仅借鉴 httpx 重试模式"——未来若 V1.1 加 Confluence Server OAuth 易踩 M5 NP-2 坑 |
| **M7 retrieval → OpenSearch upsert** | L1061 "M6 写完 chunks 后 M7 upsert 到 OpenSearch" | M7 plan 独立（无 r2） | ✅ 一致 |
| **M7 `OpenSearchClient` lifespan 注入** | 未引用 | M7 plan | ✅ 不适用（M6 不直连 OpenSearch） |
| **M8 `POST /api/ingest/confluence` 路由** | L24 / L126 锁定 `ingest_confluence` 入口签名 `(space_key, page_id, auth, user_id, *, max_depth)` | M8 plan 已修 | ✅ 一致 |
| **M8 反序列化 `ConfluenceAuth(**payload["auth"])`** | L293-294 / L308-310 Pydantic 验证 | M8 plan | ✅ 一致 |
| **M11 `ingest_jobs.completed_at` 索引** | L107 / L130 隐式依赖 M11 eval 走 completed_at 索引 | M11 r1 已修 | ✅ 一致 |
| **M11 RAGAS eval → `IngestReport` 字段** | L30 IngestReport 完整字段（`pages_discovered` / `chunks_count` / `duration_seconds` / `skipped_content_type` / `attachments_deduplicated`） | M11 r1 P0-3 已修依赖 chunks_count | ✅ 一致 |

**跨 M 一致性总结**：
- **完全一致**：M0 healthcheck / M0 TEI 18080 / M1 schema payload_hash UNIQUE / M1 chunks 表 / M3 TEI EmbeddingDimMismatch / M4 pipeline.process_elements / M4 OpenSearch 写入 / M4 exceptions 复用 / M5 P1-6 跨用户 hash / M7 upsert / M8 入口签名 / M8 Pydantic 反序列化 / M11 completed_at
- **2 个次要标注**：M4 `ImageRef` 路径 / M5 4 auth 模式与 M6 1 auth 模式偏离
- **2 个错误**（NP-A 异常类 / NP-D M5 复用接口）——M5 r2 NP-1~5 揭示的同类错 M6 重复

---

## 4. 风险表补全质量

### 4.1 风险表结构

plan 风险表 L1069-1127 共 **59 行**，分 4 段：
- **原 6 行风险**（L1072-1077）：限速 / 字段差异 / 内存压力 / 循环引用 / token 泄露 / 并发顺序 / M8 路由未实现 / 存储格式 / payload_hash
- **r1 修复 17 行**（L1079-1100）：P0-2 / P0-3 / P0-1 / P1-7 / P1-3 / P1-1 / P1-2 / P1-9 / P1-10 / P1-8 / P1-11 / P1-4 / P1-5 / P1-6（×2：M6 fallback + M4 元素分类）/ P2-1 / P2-2 / P2-3 / P2-4 / P2-5 / P2-6 / P2-7 / P2-8 / P2-9（23 项风险行，对应 r1 修复）
- **M6 范围内 r1 已修条目**（L1105-1127）：17 行 "P? 已修" + 列 `r1-2026-06-11`
- **r1 修订记录**（L1136-1158）：17 行 r1-2026-06-11 实际修订

**统计**：实际"风险"概念的行只有前 2 段（23 行），后 2 段（34 行）是"修复记录"——但形式上混入风险表。

### 4.2 风险覆盖维度

| 维度 | 覆盖行 | 评估 |
|------|--------|------|
| **安全** | token 泄露（r0）/ SSRF（M5 复用）/ XSS（M5 复述） | ✅ 足够（V1 范围） |
| **错误处理** | 401/403/404/429/5xx/50MB/Content-Type（r0+r1）/ 附件下载超时 | ✅ 充分（错误矩阵全） |
| **幂等** | payload_hash 含 user_id（r0+r1）/ 重复 chunks（隐含） | ✅ 充分 |
| **兼容** | 字段差异（r0）/ _links.next 4 格式（r1）/ M4 元素分类（r1） | ✅ 充分 |
| **工程化** | 估时（r1）/ config 拆分（M5 X-1）/ pyproject 片段（r1）/ asyncio mark（M5 复述） | ✅ 充分 |
| **跨 M** | M5 复用（r0）/ M4 元素分类（r1）/ M5 4 auth 互斥（**M6 未标注 NP-D2**） | ⚠️ 缺 1 项（M5 4 auth 模式与 M6 1 auth 模式偏离） |
| **新发现 r2 风险** | Confluence page body 25MB（**NP-E 未标注**）/ SqliteVisitedStore 死代码（**NP-F 未标注**） | ❌ 缺 2 项 |

### 4.3 风险表质量问题

| 问题 | 位置 | 性质 | r2 修复 |
|------|------|------|---------|
| 17 行 r1 修复 "曾被否决的替代方案" 列全写 `r1-2026-06-11` 无意义 | L1105-1127 | **NP-C cosmetic**（M5 r2 NP-4 同类） | r2 删除该列或填实际被否决方案 |
| 17 行 r1 修复条目与修订记录 L1136-1158 重复 | L1105-1127 vs L1136-1158 | **冗余**（33 行内容重叠） | r2 风险表只保留"未来风险"行，r1 已修条目归入修订记录 |
| `M4 元素分类未实现` 在 P1-6 写 2 次（L1094 + L1095） | L1094-1095 | **重复** | r2 合并为 1 行 |
| 缺 Confluence page body 25MB 风险行 | 风险表缺 | **NP-E 缺失** | r2 风险表加 1 行 |
| 缺 M5 4 auth 模式与 M6 1 auth 模式偏离标注 | 风险表缺 | **M5 r2 NP-2 跨 M 联动** | r2 风险表加 1 行："M6 决策 V1 只支持 Confluence Cloud Basic auth；V1.1 若加 Server/OAuth 需重审 M5 4 auth 模式" |
| 缺 SqliteVisitedStore 死代码标注 | 风险表缺 | **NP-F 缺失** | r2 选方案 A（删 SqliteVisitedStore）或方案 B（BFS 真用） |

### 4.4 "曾被否决的替代方案" 列质量

| 行类型 | 该列质量 |
|--------|---------|
| r0 原 9 行风险 | ⭐⭐⭐⭐ — "不限速"/"退回 v1 REST"/"全部加载到内存再写"等具体方案 |
| r1 修复 17 行 | ⭐ — 全写 `r1-2026-06-11` 无意义（**NP-C**） |
| r1 修订记录 17 行 | ⭐ — 同 NP-C |

---

## 5. 落地建议

### 5.1 r2 必修优先级

1. **NP-B**（P1-7 start-limit 死循环）——**P0 阻塞级**——r2 必修：
   - Task 4 GREEN 段 L398-402 重写为 start-limit 抛 `ConfluenceAPIError` 终止
   - Task 4 RED 段加 `test_list_children_start_limit_raises_error`
   - 估时：20 min

2. **NP-A**（P1-11 异常类与 M4 exceptions.py 对齐）——**P1 阻塞级**——r2 必修：
   - 风险表 L1091 改"统一在 `app/ingest/exceptions.py` 定义"
   - Task 3 GREEN 段加 1 行 `from app.ingest.exceptions import ...`
   - 估时：15 min

3. **NP-D**（M5 复用接口显式 import）——**P1 重要**——r2 必修：
   - Tech Stack 段 L172-198 加 1 import 段
   - DoD 加 1 条
   - 估时：10 min

4. **NP-E**（page body 25MB 限制）——**P2 优化**——r2 建议修：
   - `ConfluenceSettings` 加 2 字段
   - Task 3 加 1 测试
   - `IngestReport` 加 1 字段
   - 风险表加 1 行
   - 估时：25 min

5. **NP-F**（SqliteVisitedStore 死代码）——**P2 优化**——r2 二选一：
   - 方案 A（推荐）：删 `app/ingest/visited_store.py` + 1 测试文件
   - 方案 B：BFS 改用 SqliteVisitedStore + 补 3 接口
   - 估时：方案 A 15 min / 方案 B 30 min

6. **NP-C**（17 行 r1 修复 cosmetic bug）——**P3 cosmetic**——r2 顺手修：
   - 风险表 L1105-1127 17 行删除或合并到修订记录
   - 估时：5 min

### 5.2 跨 M 联动建议

- **M5 r2 NP-5** + **M6 r2 NP-A** 同步修：M5 r2 + M6 r2 联合 commit，把 `URLFormatError` / `UnsafeURLError` / `RetryableHTTPError` / `ConfluenceError` / `PermissionDeniedError` / `PageNotFoundError` / `ConfluenceServerError` / `ConfluenceAPIError` 全部移到 `app/ingest/exceptions.py`
- **M5 r2 NP-3** + **M6 r2 NP-D** 同步修：M5 + M6 联合 commit，DoD 显式标注 `assert_safe_url` / `SSRFRedirectTransport` 复用点
- **M5 r2 NP-2** + **M6 r2** 风险表联动标注：M6 决策 V1 只 Basic auth，与 M5 4 auth 模式偏离需在 plan 显式说明
- **M4 r2 22 项待续** + **M6 r2 NP-E** 联动：M4 元素分类若延期，M6 fallback 元素分类器需独立可测（已 P1-6 修）；M6 page body 25MB 限制是 M4 splitter 上游

### 5.3 估时调整

- r1 估时 7-8d
- r2 修复（NP-A ~ NP-F）估时：**+1.5h**（NP-B 20min + NP-A 15min + NP-D 10min + NP-E 25min + NP-F 15min + NP-C 5min = 90 min = 1.5h）
- 修后仍 7-8d（1.5h < 0.5d，可吸收）

### 5.4 整体结论

M6 r1 **修复彻底、覆盖全面、技术深度居 RAG V1 单 M plan 之首**——23 项 P0/P1/P2 在 plan 主体 100% 落地（21 项完全到位 + 2 项有缺陷但已在风险表标注 r1 修订）。

**r2 修 6 个新问题（NP-A ~ NP-F）后即可动手**——其中 NP-B（start-limit 死循环）和 NP-A（异常类分散）是阻塞级必须修，其余 4 项是工程化 / cosmetic 优化级别。

**M6 r1 质量评估**（与 RAG V1 8 份 M plan 对比）：
- M0/M1/M2/M3 r1 修复质量：⭐⭐⭐⭐
- **M4 r1 修复质量：⭐⭐⭐⭐⭐**（22 项 + 2 个 r1 引入新问题）
- **M5 r1 修复质量：⭐⭐⭐⭐**（18 项 + 5 个 r1 引入新问题 NP-1~5）
- **M6 r1 修复质量：⭐⭐⭐⭐½**（23 项 + 6 个 r1 引入新问题 NP-A~F）——**与 M4 r1 质量并列第一**，但 r1 引入新问题数与 M5 r1 接近（5 vs 6）

---

## 附录 · r1 修复完成度雷达图

```
维度                  完成度
─────────────────────────────
23 项主体同步率         100% (23/23)
Task RED 测试齐全率     100% (23/23 RED 测试可定位)
GREEN 代码段完整率      100% (23/23 GREEN 代码可读)
DoD 条目同步率         100% (23/23 DoD 标注)
风险表条目同步率        74% (17/23 风险行；6 项 r0 原风险保留)
修订记录同步率          100% (17 行 r1 修订 100% 与 plan 主体对应)

r1 引入新问题           6 (NP-A~F)
P0 阻塞                1 (NP-B)
P1 阻塞                1 (NP-A)
P2 优化                3 (NP-D/E/F)
P3 cosmetic            1 (NP-C)
```

---

## 修订记录

|| 版本 | 日期 | 改动 |
||------|------|------|
|| r2-2026-06-11 | 2026-06-11 | r2 review：23 项 r1 修复验证（21 ✅ + 2 ⚠️：P1-7 代码 bug + P1-11 异常类未定义）；6 个 r1 引入新问题（NP-A 异常类与 M4 对齐 / NP-B start-limit 死循环 / NP-C cosmetic r1 修订行 / NP-D M5 复用未真 import / NP-E page body 25MB 缺 / NP-F SqliteVisitedStore 死代码）；11 维跨 M 一致性（8 维度完全一致 + 2 个次要标注 + 2 个错误 NP-A/NP-D）；风险表补全质量中等（17 行 cosmetic bug + 缺 3 项 r2 风险行）；落地建议 r2 修 6 个新问题（估时 +1.5h）后即可动手 |
