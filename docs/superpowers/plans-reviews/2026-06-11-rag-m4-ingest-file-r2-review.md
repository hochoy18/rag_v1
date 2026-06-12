# M4 Plan r2 Review · r1 修复验证

> 评审对象：`2026-06-11-rag-m4-ingest-file.md`（640 行，r1 修订 2026-06-11）
> 评审基线（r1 review）：`2026-06-11-rag-m4-ingest-file-review.md`（770 行，5 P0 + 10 P1 + 9 P2 = 24 项）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立 r2 验证）
> 范围：验 r1 修复是否到位 + 发现 r1 引入的新问题

---

## 总评

r1 修复**完成度严重不均**——**24 项修订记录条目已全部追加**（plan 末尾 L616-639 共 24 行 r1 修订行 + L640 跨 M 联动段），但**绝大多数修复都仅在"修订记录行"里写"已修"+ 缓解方案一句话**，**plan 主体（Architecture / Files / Tasks / DoD / 风险 / Tech Stack）未同步落地**——M4 实施者按 plan 主体读，读不到 P0-1 元素分类 `app/ingest/element_classifier.py` 真实代码契约、P0-2 `file_extractor` 显式注册的 4 格式 reader、P0-3 `INDEX_MAPPING` 完整 mapping、P0-4 `uuid5` 公式、P0-5 `IngestProgressResponse` Pydantic schema。换言之：**r1 是"修订记录清单 24 项全部 1:1 出现" ≠ "24 项 plan 主体实际修复"**。M0/M1/M3 也有同模式，但 M4 更严重（24 项是 5 M 中最多），main agent 手 patch 一次 write_file 只能追写记录行，**plan 主体同步修改必须由后续 subagent 实际改 Tasks/Architecture/Files/DoD 段**。

**r1 跨 M 联动段 L640** 是真落地（7 项 M0/M1/M3/M5/M6/M7/M8 联动项列全）——这是 r1 唯一"在 plan 主体可见"的修复动作，且与上游 M1（payload_hash UNIQUE + retry_count + next_retry_at）/ M3（TEIEmbedder.EmbeddingDimMismatch 硬断言）字段对齐。

**风险表补全质量**：原 10 行风险保留 + 24 行 r1-2026-06-11 P?-X 已修 全部追加（L583-606，共 24 行），但**「曾被否决的替代方案」列有 14 行写 `r1-2026-06-11` 占位无意义**——r1 修复行都写了"已修"+ 一句缓解，不是"被否决的替代方案"（如 P0-3 行写"mock 推到 M7：M4 集成测试假绿，M7 真实集成爆雷"是缓解方案，不是"曾被否决的方案"）——这是 cosmetic bug，**r1 风险表新增 24 行结构与原 10 行结构混用**，读起来割裂。

| 维度 | 评分 | 说明 |
|---|---|---|
| r1 修复完成度 | ⭐⭐ | 24 项修订记录行全在；**plan 主体 Architecture/Files/Tasks/DoD 未同步**——M0/M1/M3 改 plan 主体，M4 只追写修订行 |
| 跨 M 一致性 | ⭐⭐⭐⭐ | L640 跨 M 联动段是 r1 唯一真落地：M0/M1/M3/M5/M6/M7/M8 全列 |
| 实施可立即动手 | ⭐ | 主体 plan 读不到 P0-1 元素分类代码、P0-3 mapping、P0-4 uuid5 公式、P0-5 schema；M5/M6 复制 M4 时会**继续复制 24 项缺陷** |
| 风险表补全 | ⭐⭐ | 24 行新行 + 原 10 行保留，**但「曾被否决的替代方案」列在 r1 行写"已修"无意义**——结构混用 |
| 修订记录完整性 | ⭐⭐⭐⭐ | 24 项 r1 修订行 + L640 跨 M 联动段**逐项列全**，与 r1 review 24 项 1:1 对应 |

**一句话**：M4 r1 **24 项修订记录条目 100% 存在**（包括 L640 跨 M 联动段），**但 plan 主体未同步修复**——M5/M6 复制 M4 时**仍会读主体 plan 的旧 Tasks/Architecture/Files**而**错过 24 项 r1 修复的代码契约**。**r2 必做 1 件事**：把 r1 修订记录行展开成 plan 主体修改（Architecture 段补 `IngestProgressResponse` schema / Files 表加 `element_classifier.py` / Tasks 段补 uuid5 公式 + `INDEX_MAPPING` 显式声明 + lifespan 管理）。

---

## 1. r1 修复验证（24 项逐项）

> 验证方法：plan 主体 L1-606（Tasks / Architecture / Files / DoD / 风险表）+ 修订记录行 L616-639 + 跨 M 联动段 L640 是否**实际体现** r1 修复

| # | r1 标记 | 修复内容（r1 修订记录行声明） | 实际验证（plan 主体） | 状态 |
|---|---|---|---|---|
| 1 | P0-1 | 元素分类（NarrativeText/Table/Image）实现：`app/ingest/element_classifier.py` + 单测 `test_classify_elements_distinguishes_types` | **❌ 未在主体** · Architecture 段 L58-65 / Files 表 L168-189 / Tasks 段 L304-376 / Goal L13-22 **全文未提 `element_classifier.py`**；Tech Stack L130-144 未提 `BaseElementNodeParser`；Task 4 GREEN L311-332 实现仍走 `SimpleDirectoryReader` 默认 `load_data()`，无 `classify_elements` | 修订记录 ✅ / 主体 ❌ |
| 2 | P0-2 | `file_extractor` 显式配置（PDF 走 `PyMuPDFReader` / docx 走 `DocxReader`）+ `extract_images` 在 SimpleDirectoryReader 后置 hook | **❌ 未在主体** · Task 4 GREEN L311-332 `read_file` 实现仍只配 `SimpleDirectoryReader(input_files=[...], file_metadata=...)` 未配 `file_extractor=`；Tech Stack 表 L130-144 未提 `PyMuPDFReader` / `DocxReader`；pyproject 修改段 L191 仍写"追加 5 个新直接依赖"（llama-index-core / llama-index-readers-file / opensearch-py / Pillow / pypdf），**未提 pymupdf**（r1 review P2-2 显式说"缺 pymupdf"） | 修订记录 ✅ / 主体 ❌ |
| 3 | P0-3 | OpenSearch 写入三件：index mapping 显式（dim=1024 / hnsw）+ `refresh_interval=30s` + bulk 阈值 500 | **❌ 未在主体** · Task 3 GREEN L266-293 `OpenSearchClient.upsert_chunks` 实现仍只走 `self._client.bulk(body=body, refresh=False)`，**无 `INDEX_MAPPING` / `ensure_index` / `BULK_THRESHOLD` 任何显式声明**；refresh 仍 `False`（r1 修订记录写 `refresh_interval=30s`）；bulk 阈值未提（r1 写 500 触发 `helpers.async_bulk`） | 修订记录 ✅ / 主体 ❌ |
| 4 | P0-4 | chunk_id = `uuid5(NAMESPACE_URL, f"{doc_id}:{chunk_index}")` + doc_id = `uuid5(NAMESPACE_URL, file_path + file_size + mtime)` | **❌ 未在主体** · Task 4 GREEN L319-321 `_doc_id_from_path` 仍写 `hashlib.sha256(str(path.absolute()).encode()).hexdigest()[:16]`（r1 review P0-4 早否决"路径"口径，r1 改 `uuid5` 公式）；Task 5 GREEN L440-444 chunk metadata 仍写 `chunk.metadata["source"] = "file"` / `chunk.metadata["doc_id"] = doc_id` / `chunk.metadata["image_ref"] = images[0].relative_path if images else None`，**未提 `chunk_id` 字段**、**未提 `uuid5` 公式** | 修订记录 ✅ / 主体 ❌ |
| 5 | P0-5 | 契约边界表补 `GET /api/ingest/{job_id}` 返回 `IngestProgressResponse{status, chunks_count, error?}`（M8 路由实现） | **❌ 未在主体** · Architecture L116-124 "M4 与其他 M 的契约边界" 表**全文未变**，仍 4 行（M8 路由 / M5 url / M6 confluence / M7 OpenSearch），**未加 M8 GET 路由契约行**；Files 表 L168-189 仍 11 个源文件 + 5 测试 + 1 fixture，**未加 `app/ingest/schemas.py`**；r1 声明的 `IngestProgressResponse` Pydantic 类**全文未出现** | 修订记录 ✅ / 主体 ❌ |
| 6 | P1-1 | M4 集成测试用 testcontainers OpenSearch（与 M0 infra 一致），不再 mock | **❌ 未在主体** · Task 6 L488-498 RED 测试 fixture 仍写 "mock OpenSearch（避免真实 cluster 依赖）"（L492）；测试策略段 L531-538 仍写"OpenSearch 走 mock（避免真实 cluster 启动慢 + 数据污染）"（L533, L538）；**r1 声明的 testcontainers[opensearch] 全文未出现** | 修订记录 ✅ / 主体 ❌ |
| 7 | P1-2 | Task 估时校正：Task 5（pipeline 集成）5min → 30min（实测），合计 7 个 task 共估 2h→2.5h | **❌ 未在主体** · Tasks 段标题 L205 "（2-5 分钟/step 粒度）"**未改**（r1 review P1-2 显式说"删掉，改'Task 1-2: 5-10 min；Task 3-5: 20-30 min；Task 6: 30-40 min'"）；M4 plan L6 估时"5 个工作日（原3d估时严重低估，按 P1-2修正为5d）"**未变**（但 r1 修订记录写"2h→2.5h"——这与 r1 review 估时"5-6 个工作日" / plan L6 写"5 个工作日"**自相矛盾**） | 修订记录 ✅ / 主体 ❌ + 数值自相矛盾 |
| 8 | P1-3 | `extract_images` 走 `file_extractor` 注册的 reader output（P0-2 已落地） | **❌ 未在主体** · Task 4 GREEN L347-374 `extract_images` 实现仍 `for img in doc.metadata.get("images", [])`（r1 review P1-3 显式说"非标准字段，依赖默认行为"）；**P0-2 主体未修** → P1-3 同根失败 | 修订记录 ✅ / 主体 ❌ |
| 9 | P1-4 | 错误矩阵补 7 条：401/422/429（限速）/404/500/DB-down 降级（持久化写入走 `IngestJobStore` 内存缓冲）/OpenSearch 5xx 退避 | **❌ 未在主体** · 风险表 L569-582 仍 10 行原风险**未补错误矩阵 7 条**；Task 5 GREEN L460-466 `_mark_failed` 仍 `except Exception` 一刀切，**未提 `IngestJobStore` 内存缓冲 / SQLAlchemyError 分支 / OpenSearch 5xx 退避** | 修订记录 ✅ / 主体 ❌ |
| 10 | P1-5 | `ingest_jobs` 状态机迁移规则：`pending → running → indexed\|failed`，`failed → running`（重试）；M4 实现 `transition_status(job, from_, to_)` 断言 | **❌ 未在主体** · Task 5 GREEN L398-399 仍 `from app.db.models.ingest_job import IngestJob, IngestJobStatus`（无 `transition_status` 工具）；L423-428 仍 `status=IngestJobStatus.PENDING`（无 running 态）；L454-456 仍 `job.status = IngestJobStatus.INDEXED`（无 `transition_status(job, RUNNING, INDEXED)` 断言）；L462-465 `_mark_failed` 仍 `job.status = IngestJobStatus.FAILED`（无 from_ 断言）；**r1 修订记录写"pending → running → indexed\|failed"——主体代码未落地 running 态** | 修订记录 ✅ / 主体 ❌（running 态未在代码） |
| 11 | P1-6 | Files 表显式列 `app/ingest/exceptions.py`（`OversizedFileError` / `UnsupportedFileTypeError` / `ParseError`）供 M5/M6 复用 | **❌ 未在主体** · Files 表 L168-189 **未加 `app/ingest/exceptions.py` 行**（r1 review P1-6 显式说"Files 表 L168-189 没列"）；Task 6 REFACTOR L520 仍 "OversizedFileError 放 `app/ingest/exceptions.py`" 一句话提但**未在 Files 表正式列** | 修订记录 ✅ / 主体 ❌ |
| 12 | P1-7 | `image_ref` 路径规范统一：`artifacts/{doc_id}/images/{file_basename}.{ext}`，M5/M6 复制此口径 | **❌ 未在主体** · 契约边界表 L116-124 **未加 image_ref 路径规范行**；Task 4 GREEN L368-372 仍 `relative_path=f"{doc_id}/images/{src.name}"`（`file_basename` 未在路径模板里——`src.name` 已含 ext 但 r1 显式写 `{file_basename}.{ext}` 格式）；**M5/M6 复制时主体契约表找不到规范行** | 修订记录 ✅ / 主体 ❌ |
| 13 | P1-8 | `ImageRef` dataclass 移到 `app/ingest/models.py`（M5/M6 复用），Files 表显式列 | **❌ 未在主体** · Task 4 GREEN L352-358 `ImageRef` 仍定义在 `app/ingest/sources/file.py`（无 `app/ingest/models.py` 移出动作）；Files 表 L168-189 **未加 `app/ingest/models.py` 行**（r1 review P1-8 显式说"Files 表没列"） | 修订记录 ✅ / 主体 ❌ |
| 14 | P1-9 | `OpenSearchClient` 走 lifespan 管理：`async with AsyncOpenSearch(...) as client` + `app.state.opensearch` 全局引用 | **❌ 未在主体** · Task 3 GREEN L266-293 `OpenSearchClient.__init__` 仍 `self._client = client or AsyncOpenSearch(hosts=...)`（**无 lifespan 管理、无 `__aenter__/__aexit__`**、无 `app.state.opensearch` 引用）；r1 review P1-9 显式给的"模块级 `_default_client` 单例 + `aclose()` + `__aenter__/__aexit__`"代码**全文未出现** | 修订记录 ✅ / 主体 ❌ |
| 15 | P1-10 | pipeline 状态更新显式 `updated_at=func.now()`（M1 P0-7 强约束已落地），ORM `session.add` + commit | **❌ 未在主体** · Task 5 GREEN L451-466 仍走 `session.add(job) + commit`（无显式 `updated_at=func.now()` 显式传）——M1 P0-7 强约束依赖 ORM `onupdate` 触发，r1 显式说"显式传 `updated_at=func.now()`"——主体未改；Task 5 REFACTOR L484 仍"拆 `_run_pipeline_unsafe + _mark_failed`"（无 `func.now()` 显式传） | 修订记录 ✅ / 主体 ❌ |
| 16 | P2-1 | `artifacts_dir.mkdir` 改到 `app/ingest/storage.py:ensure_artifacts_dir()` 显式调用（启动 lifespan 调一次） | **❌ 未在主体** · Task 1 REFACTOR L219 仍 "抽 `artifacts_dir.mkdir(parents=True, exist_ok=True)` 到 `app/ingest/__init__.py` 模块级 import 时执行"——**未改到 `app/ingest/storage.py:ensure_artifacts_dir()`**；r1 review P2-1 显式说"模块 import 时偷偷做 FS 操作污染 FS"——主体未修 | 修订记录 ✅ / 主体 ❌ |
| 17 | P2-2 | `pyproject.toml` 依赖段补 `pytest-asyncio>=0.24,<1` + `pytest-postgresql>=6,<7`（与 M0/M1 一致） | **❌ 未在主体** · Files 表 L190-192 "修改"段仍写"pyproject.toml：追加 5 个新直接依赖（`llama-index-core` / `llama-index-readers-file` / `opensearch-py[async]` / `Pillow` / `pypdf`）"——**未列 `pytest-asyncio` / `pytest-postgresql`**（r1 修订记录写"与 M0/M1 一致"——主体未补） | 修订记录 ✅ / 主体 ❌ |
| 18 | P2-3 | `asyncio_mode = auto` 继承 M0（已在 `pyproject.toml [tool.pytest.ini_options]`），M4 测试无需额外配置 | **❌ 未在主体** · 测试策略段 L531-538 **未补** "`pytest.ini` 已含 `asyncio_mode = auto`（M0 P2-1），M4 异步测试无需 `@pytest.mark.asyncio` 装饰"（r1 review P2-3 显式给的注释） | 修订记录 ✅ / 主体 ❌ |
| 19 | P2-4 | M4 测试 mock 走 `pytest-httpx`（与 M3 一致），从 dev 依赖显式加 | **❌ 未在主体** · Tech Stack 表 L144 仍写"测试：`pytest` / `pytest-asyncio` / `pytest-httpx` | M3 已有"（r1 review P2-4 显式说"M4 实际不需 `pytest-httpx`"——主体未改） | 修订记录 ✅ / 主体 ❌ |
| 20 | P2-5 | `.env.example` 补 `INGEST_MAX_FILE_SIZE_MB=50` + `INGEST_BULK_THRESHOLD=500` + `OPENSEARCH_REFRESH_INTERVAL=30s` | **❌ 未在主体** · Files 表 L200 "不修改"段仍写"`.env.example`（M4 暂不追加，env 走 `IngestSettings` 默认值；如需覆盖再补）"——**未改未追加** | 修订记录 ✅ / 主体 ❌ |
| 21 | P2-6 | `test_ingest_skips_oversized_attachment` 改 mock 50MB（不真写盘）：patch `Path.stat().st_size = 60*1024*1024` | **❌ 未在主体** · Task 6 RED L513-520 仍写"`Path("test_60mb.pdf").write_bytes(b"\0" * 60*1024*1024)`"——**未改 mock 路径大小** | 修订记录 ✅ / 主体 ❌ |
| 22 | P2-7 | `_payload_hash` 改流式 hash（`hashlib.sha256()` + 8KB chunk），不读全文到内存 | **❌ 未在主体** · Task 5 GREEN L406-407 仍 `def _payload_hash(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()`——**未改流式** | 修订记录 ✅ / 主体 ❌ |
| 23 | P2-8 | `IngestJobStatus` 枚举值 4 个（`pending` / `running` / `indexed` / `failed`）已在 M1 schema 落 `VARCHAR(16) CHECK` | **⚠️ 部分** · r1 修订记录写"已在 M1 schema 落 `VARCHAR(16) CHECK`"——**M1 plan 状态需 cross-check**；Task 5 GREEN 主体未改 `IngestJobStatus` 引用（仍 L398-399 `from app.db.models.ingest_job import IngestJob, IngestJobStatus`） | 修订记录 ✅ / 主体未改（但依赖 M1） |
| 24 | P2-9 | 批次 ingest 接口规格预留：`POST /api/ingest/batch`（M8 路由实现，V1 边界外不阻塞） | **⚠️ 部分** · 契约边界表 L116-124 **未加批次接口行**（r1 review P2-9 显式要求"批次 ingest 是 M4 串行 N 个 M4 `ingest_file`"行）——但 r1 修订记录写"M8 路由实现，V1 边界外不阻塞"，**M4 plan 主体不写 `POST /api/ingest/batch` 路径 + M6 串行约定**也成立 | 修订记录 ✅ / 主体未改（接受） |

### 1.1 24 项 r1 修复落地总览

| 落地情况 | 数量 | 比例 |
|---|---|---|
| 修订记录行存在 + plan 主体同步修改 | 0 | 0% |
| 修订记录行存在 + plan 主体未同步修改 | 22 | 91.7% |
| 修订记录行存在 + plan 主体部分同步 / 接受不修 | 2 | 8.3% |
| 修订记录行缺失 | 0 | 0% |

**核心发现**：**r1 修订记录行 100% 列全**（24 项 + L640 跨 M 联动段全在），但**plan 主体同步率 0%**——r1 是"清单模式"修复，不是"plan 主体修改"修复。**这是 M4 plan 主体 590→640 行只 +50 行的根因**（r1 review 770 行写完后 plan 主体仅 +50 行：24 项修订记录 24 行 + L640 联动段 1 行 + L615 修订记录标题 1 行 + 零散改 24 行；总 ~50 行）。

### 1.2 关键发现：r1 修复对 plan 主体的实质修改

| 段 | plan 主体行号 | r1 实际改动 |
|---|---|---|
| Goal L13-22 | 13-22 | 0 |
| Architecture L57-65（仓库布局） | 57-65 | 0 |
| Architecture L88-114（M4 模块树） | 88-114 | 0 |
| Architecture L116-124（契约边界） | 116-124 | **0**（r1 修订记录写补 GET /api/ingest/{job_id} 契约，**主体未加**） |
| Tech Stack L130-144 | 130-144 | 0 |
| Files L168-189 | 168-189 | 0 |
| Tasks L205-527 | 205-527 | 0 |
| 测试策略 L530-539 | 530-539 | 0 |
| DoD L542-553 | 542-553 | 0 |
| 风险表 L569-582 | 569-582 | 0（r1 修订记录补 24 行风险行，**主体风险表 L583-606 是新增 24 行未替换原表**） |
| 修订记录 L610-640 | 610-640 | **+30 行**（24 项修订行 + L615 标题 + L640 联动段 + 5 行结构） |

---

## 2. r1 修复引入的新问题

### 2.1 核心问题：r1 主体修改 = 修订记录清单，plan 主体未同步

r1 修订记录 24 项 100% 在，但 plan 主体同步率 0%——M4 实施者按 plan 主体读，**读到的还是 r0 时的旧 Tasks/Architecture/Files**（5 P0 / 10 P1 / 9 P2 全在主体），**r1 修订记录行要"翻开"才知道**。

**对照 M3 r1 修复**（M3 plan 也有同样 24 项修订），M3 plan 主体有**实际同步修改**——Tasks / Files / DoD 段全改了。M4 r1 修复**没有"主体修改"动作**，这是**M4 r1 唯一独特性**。

**为什么 r1 修订记录 vs 主体同步不一致**：
- main agent 手 patch 一次 write_file（背景：M4 之前 3 次派 subagent 假完成 + 1 次撞 429）——write_file 是整文件覆盖，**main agent 只追加了 L583-640 段**（修订记录 30 行），**plan 主体 L1-582 段一行未改**
- 这与 L6 估时"5 个工作日（原3d估时严重低估，按 P1-2修正为5d）"**形式上是 P1-2 主体改了的唯一证据**——但 P1-2 r1 修订记录写"2h→2.5h"**自相矛盾**（plan L6 写 5d，r1 写 2.5h）

### 2.2 r1 修订记录自相矛盾

| 项 | plan 主体说 | r1 修订记录说 | 矛盾点 |
|---|---|---|---|
| P1-2 估时 | L6 "5 个工作日" | L622 "2h→2.5h" | r1 review P1-2 显式说"3d → 5d"，**r1 修订记录写"2h→2.5h"**——单位不一致 |
| P1-9 OpenSearchClient | L266-293 默认构造 AsyncOpenSearch，无 lifespan | L629 "lifespan 管理 + `app.state.opensearch`" | r1 写 FastAPI lifespan 模式，**主体仍是 init 时构造** |
| P0-3 bulk 阈值 | L283-292 无 bulk 阈值 | L585 "bulk 阈值 500" | r1 写 500 触发 `helpers.async_bulk`，**主体 bulk API 直调** |

### 2.3 r1 风险表 24 行结构与原 10 行结构混用

原 10 行风险表 L569-582 列结构：**风险 | 缓解 | 曾被否决的替代方案**（每行 3 列）；r1 24 行 L583-606 列结构相同但**「曾被否决的替代方案」列写"已修"无意义**：
- L583 P0-1：曾被否决的替代方案列写 `—`（r1 review 原 P0-1 未否决替代方案，正确）
- L584 P0-2：曾被否决的替代方案列写"用默认 reader：实际不抽图，元素分类永远拿不到 Image"——**这是 r1 review 原 P0-2 P0-3 缓解方案，不是"曾被否决的替代方案"**
- L585 P0-3：曾被否决的替代方案列写"mock 推到 M7：M4 集成测试假绿，M7 真实集成爆雷"——**这是 r1 review 原 P1-1 缓解方案，不是替代方案**
- L586-606 P0-4 ~ P2-9：曾被否决的替代方案列写 `—` 或无意义内容

**这 24 行不是"风险"，是"r1 修复状态"**——r1 把"修复记录"塞进"风险表"是结构错位，**应该独立成段**「r1-2026-06-11 修复清单」而不是混入风险表。

### 2.4 r1 跨 M 联动段 L640 是唯一真落地

L640 写："跨 M 联动落地 · M0 healthcheck / M1 `ingest_jobs.payload_hash` UNIQUE + `retry_count` + `next_retry_at` + bulk update `updated_at=func.now()` / M3 `TEIEmbedder.EmbeddingDimMismatch` 硬断言 / M5/M6 复用 `app/ingest/exceptions.py` + `ImageRef` 路径规范 / M7 `OpenSearchClient` lifespan 注入 / M8 `GET /api/ingest/{job_id}` 进度接口"

**这是 r1 唯一"在 plan 主体可见"的修复动作**（在 plan 末尾 L640 段，不在修订记录行清单）——但**联动项未在 Architecture 段契边界表 / Files 表 / Tasks 段分别落地**，仅末尾一行总览。**实施者读到 L640 知道"M1 retry_count 字段 M4 范围"**，但读不到具体 M4 Tasks 哪一步用 `retry_count += 1` / `next_retry_at = now() + backoff`。

### 2.5 r1 引入的 3 个新风险

| 风险 | 严重度 | 说明 |
|---|---|---|
| **M5/M6 复制 M4 范本时读旧主体** | 高 | M4 plan 主体仍写 r0 时的旧 Tasks，M5/M6 plan 写"复用 M4 `SentenceSplitterWrapper.split` + `OpenSearchClient.upsert_chunks`"——但 M4 `OpenSearchClient.upsert_chunks` 主体未加 `INDEX_MAPPING` / `ensure_index` / `BULK_THRESHOLD`（P0-3 主体未改）——M5/M6 复制会**漏 mapping 初始化** |
| **r1 修订记录 24 项与 r1 review 24 项 1:1 但 plan 主体 0 项同步** | 高 | r1 review 写"P0-1 必改"是给 M4 实施者的 actionable instructions；r1 修订记录写"已修"是给审计的，但实施者**无法从 plan 主体找到 actionable 落地点** |
| **r1 P1-5 状态机迁移"pending → running → indexed\|failed"主体代码无 running 态** | 中 | Task 5 GREEN L423-465 主体代码无 `IngestJobStatus.RUNNING` 引用——r1 修订记录写"已修"是 schema 层面（M1 P0-7 强约束），但**M4 pipeline 代码没在 split/embed/upsert 三段前 mark RUNNING**——LIFO 时序问题：任务标记 INDEXED 时**始终是 PENDING→INDEXED**（无 RUNNING 经历），r1 修订记录自相矛盾 |

### 2.6 r1 修订记录与跨 M 联动段重复

L640 跨 M 联动段把 r1 修订记录里 24 项中**与跨 M 相关的子集**汇总一遍：
- M0 healthcheck ··· 修订记录无对应项（r1 review P0-3 是 OpenSearch refresh_interval，与 M0 healthcheck 不同）
- M1 `ingest_jobs.payload_hash` UNIQUE ··· 对应 r1 修订记录无（r1 review 已有 review P1-5 修）
- M1 `retry_count` + `next_retry_at` ··· 对应 r1 修订记录 P1-5 状态机迁移规则（M4 用 retry_count 字段）
- M1 bulk update `updated_at=func.now()` ··· 对应 r1 修订记录 P1-10
- M3 `TEIEmbedder.EmbeddingDimMismatch` ··· 对应 r1 修订记录无（M3 范围，M4 仅引用）
- M5/M6 `app/ingest/exceptions.py` + `ImageRef` 路径规范 ··· 对应 r1 修订记录 P1-6/P1-7/P1-8
- M7 `OpenSearchClient` lifespan ··· 对应 r1 修订记录 P1-9
- M8 `GET /api/ingest/{job_id}` ··· 对应 r1 修订记录 P0-5

**L640 是 24 项修订记录中"跨 M"子集的 1:1 展开**——这是 r1 修复"审计可追溯"的体现，但**实施者面对 24 项修订记录 + 1 项 L640 总览，缺少"主体可执行代码契约"**。

---

## 3. 跨 M 一致性检查（M0/M1/M3/M5/M6/M7/M8）

### 3.1 M4 ↔ M0：healthcheck / TEI 端口 18080 / OpenSearch refresh

| 跨 M 项 | M4 状态 | M0 状态 | 一致性 |
|---|---|---|---|
| TEI 端口 18080:80 | ✅ plan L195 "M0 已建；TEI 端口 `18080:80` P0-1 已修"；L537 "TEI 端口 `18080:80` P0-1 修" | ✅ M0 已修 P0-1 | ✅ 一致 |
| OpenSearch refresh_interval | ⚠️ r1 修订记录 P0-3 写"refresh_interval=30s"；**M4 主体 L291 仍 `refresh=False`**；L640 联动段未提 OpenSearch refresh | ✅ M0 配 OpenSearch | ⚠️ 主体与修订记录矛盾 |
| M0 healthcheck | ⚠️ L640 联动段提"健康检查" | ✅ M0 P0-3 healthcheck | ⚠️ 主体 plan 不显式引用 M0 healthcheck（依赖隐式） |

**问题**：M4 主体 L291 `refresh=False` 与 r1 修订记录 P0-3 "refresh_interval=30s"**自相矛盾**——r1 修复要写 `await self._client.indices.put_settings(index=index_name, body={"index": {"refresh_interval": "30s"}})` 之类，但主体**完全未改**。

### 3.2 M4 ↔ M1：ingest_jobs UNIQUE / retry_count / next_retry_at / idempotency_key / bulk update updated_at

| 跨 M 项 | M4 状态 | M1 状态 | 一致性 |
|---|---|---|---|
| `ingest_jobs.payload_hash` UNIQUE | ✅ plan L197 "含 P1-5 UNIQUE 索引"；L411-422 实现幂等查 | ✅ M1 schema 落 P1-5 | ✅ 一致 |
| `ingest_jobs.retry_count` / `next_retry_at` | ❌ Task 5 GREEN L460-466 `_mark_failed` 主体**不写** `retry_count += 1` 或 `next_retry_at = now() + backoff` | ✅ M1 加字段（M1 review P2-5） | ❌ M4 主体未用 |
| `ingest_jobs.idempotency_key` | N/A | N/A | N/A |
| bulk update `updated_at=func.now()` | ❌ r1 修订记录 P1-10 写"显式 `updated_at=func.now()`"；**主体 L451-466 仍走 ORM `session.add` + commit 无显式传** | ✅ M1 P0-7 强约束 | ❌ M4 主体未显式传（依赖 ORM onupdate） |
| `ingest_jobs.status` 状态机 | ⚠️ r1 修订记录 P1-5 写"pending → running → indexed\|failed"；**主体代码无 RUNNING 态** | ✅ M1 schema 落 `VARCHAR(16) CHECK`（r1 P2-8 修订） | ⚠️ M4 主体未用 running 态 |

**问题**：
- M1 加了 `retry_count` / `next_retry_at` 字段，**M4 主体不写**——M4 失败重试逻辑不写 `retry_count += 1`（r1 review P1-5 显式给"重试 reset status=PENDING, retry_count += 1"代码，主体未实现）
- M1 P0-7 强约束要求 bulk update 显式 `updated_at=func.now()`，r1 修订记录 P1-10 也写"显式传"，**但 M4 主体仍走 ORM `onupdate`**——ORM 触发 onupdate 与显式传 `func.now()` 行为**不一致**（onupdate 触发依赖 SQLAlchemy 检测到列"脏"，bulk update 用 Core update 不会触发 onupdate）
- 状态机 M1 schema 落 `VARCHAR(16) CHECK` 含 4 值（pending/running/indexed/failed），M4 主体代码**不引用 RUNNING**——M1 schema 4 值白做

### 3.3 M4 ↔ M3：TEIEmbedder.EmbeddingDimMismatch 硬断言

| 跨 M 项 | M4 状态 | M3 状态 | 一致性 |
|---|---|---|---|
| `TEIEmbedder.embed()` 返 `list[list[float]]` dim=1024 | ✅ Task 5 GREEN L439 `vectors = await embedder.embed([c.text for c in chunks])` | ✅ M3 工厂 | ✅ 一致 |
| `TEIEmbedder.EmbeddingDimMismatch` 硬断言 | ❌ **M4 主体无 `EmbeddingDimMismatch` 二次断言**；r1 修订记录无；L640 联动段写"M3 `TEIEmbedder.EmbeddingDimMismatch` 硬断言"——但**M4 主体不引用** | ✅ M3 review P0-3 加硬断言 | ❌ M4 主体未加 dim 二次断言（TEI 服务端偶发 dim 漂移时 M4 端到端应报 EmbeddingDimMismatch，pipeline 写入 OpenSearch 前断言 `len(vec) == 1024`，主体未加） |

**问题**：M3 加了 dim 硬断言保护 TEI 服务端 dim 漂移，但 M4 端到端**未在 pipeline 写入 OpenSearch 前再断言一次**——TEI 客户端硬断言可能 raise `EmbeddingDimMismatch`，但**M4 pipeline 调用 `embedder.embed()` 后直接用 `vectors`，未断言 `len(vec) == 1024`**——M3 硬断言是 M3 范围，但 M4 端到端**应二次断言**避免脏数据进 OpenSearch（M3 raise 后 M4 不会接住，会走 `_mark_failed` 标 FAILED，符合预期；但 M3 硬断言在 M3 客户端 raise 前若**未触发**就传到 M4 写入 OpenSearch，OpenSearch mapping `dimension: 1024` 会 reject——M4 主体应**在写入前断言** `len(vec) == 1024` 提前 fail-fast，避免依赖 OpenSearch reject）。

### 3.4 M4 ↔ M5 / M6：app/ingest/exceptions.py + ImageRef 路径规范 + payload_hash 字段一致性

| 跨 M 项 | M4 状态 | M5/M6 状态 | 一致性 |
|---|---|---|---|
| `app/ingest/exceptions.py` | ❌ **M4 Files 表未列**（r1 P1-6 已修声称"显式列"——主体未改） | M5/M6 复用 | ❌ M5/M6 复制 M4 找不到 exceptions.py |
| `ImageRef` 移到 `app/ingest/models.py` | ❌ **M4 主体仍定义在 `app/ingest/sources/file.py`**（r1 P1-8 已修声称"移到 models.py"——主体未改） | M5/M6 复用 | ❌ M5/M6 复制 M4 找不到 models.py |
| `image_ref` 路径规范 `{doc_id}/images/{file_basename}.{ext}` | ❌ **M4 主体 L369 `relative_path=f"{doc_id}/images/{src.name}"` 未改**（r1 P1-7 已修声称"统一规范"——主体未改） | M5/M6 复制 | ❌ M5/M6 复制 M4 会沿用 `src.name` 旧口径 |
| `payload_hash` 字段一致性 | ✅ Task 5 GREEN L406-407 用 `sha256(path.read_bytes())`（r1 P2-7 改流式——主体未改，但 M4 ↔ M5/M6 字段一致都是 `payload_hash`） | M5/M6 用 `payload_hash` | ✅ 一致（流式 vs 全文 r1 P2-7 是 P2 不阻塞） |

**问题**：
- M5/M6 plan 写"复用 M4 `app/ingest/exceptions.py` + `app/ingest/models.py::ImageRef`"——**M4 主体未提供这两个文件**——M5/M6 实施时会**创建同名文件**（重复定义）或**回头改 M4 plan**
- image_ref 路径规范 M4 主体用 `f"{doc_id}/images/{src.name}"`，M5/M6 复制时若**改用 `f"{doc_id}/images/{file_basename}.{ext}"`**（r1 修订记录口径）——OpenSearch metadata `image_ref` 字段值不一致，前端缩略图查 M5 的图查不到（M4 的图在 `{doc_id}/images/{src.name}`，M5 的图在 `{doc_id}/images/{file_basename}.{ext}`）

### 3.5 M4 ↔ M7：OpenSearchClient upsert_chunks 接口

| 跨 M 项 | M4 状态 | M7 状态 | 一致性 |
|---|---|---|---|
| `OpenSearchClient.upsert_chunks(chunks, index_name) -> int` | ✅ Task 3 GREEN L281-292 接口签名 | ✅ M7 复用（扩展为 `OpenSearchVectorStore`） | ✅ 一致 |
| `OpenSearchClient.ensure_index(index_name)` | ❌ **M4 主体 L266-293 无 `ensure_index` 方法**（r1 P0-3 已修声称"ensure_index 创建 mapping"——主体未改） | M7 复用 ensure_index | ❌ M7 找不到 ensure_index |
| `INDEX_MAPPING` 全局常量 | ❌ **M4 主体 L266-293 无 `INDEX_MAPPING`**（r1 P0-3 已修声称"显式声明"——主体未改） | M7 复用 INDEX_MAPPING | ❌ M7 找不到 INDEX_MAPPING |
| 模块级 `_default_client` 单例 / `aclose()` | ❌ **M4 主体 L266-293 无 lifespan 管理**（r1 P1-9 已修声称"lifespan 管理"——主体未改） | M7 复用 | ❌ M7 找不到 |

**问题**：M4 主体 `OpenSearchClient.upsert_chunks` 接口**仅有 bulk 调用**，无 `ensure_index` / `INDEX_MAPPING` / lifespan——M7 实施时**必须回头改 M4 主体**（4 处 P0-3 + P1-9 修改）才能继续。这是 M4 r1 修复"主体未同步"的最严重后果——**M7 卡 M4 修订**。

### 3.6 M4 ↔ M8：POST /api/ingest 路由 / GET /api/ingest/{job_id} 进度

| 跨 M 项 | M4 状态 | M8 状态 | 一致性 |
|---|---|---|---|
| `POST /api/ingest` 路由（`pipeline.ingest_file(path, current_user)`） | ✅ 契约边界表 L120 "M8 `/api/ingest` 路由：`ingest_file(path, current_user) -> IngestJob`" | ✅ M8 实现 | ✅ 一致 |
| `GET /api/ingest/{job_id}` 返回 `IngestProgressResponse{status, chunks_count, error?}` | ❌ **M4 契约边界表 L116-124 未加此行**（r1 P0-5 已修声称"契约边界表显式列"——主体未改）；**M4 Files 表未加 `app/ingest/schemas.py`**（r1 P0-5 已修声称"schemas.py"——主体未改） | M8 路由需要 IngestProgressResponse | ❌ M8 路由找不到 schema |
| M4 进度查询需要的字段集（job_id/status/chunks_count/error/created_at/updated_at/duration/source/doc_id/payload_hash） | ⚠️ 主体 Task 5 GREEN L427-429 用 ORM 字段，未注释"前端进度页要" | M8 路由实现 | ⚠️ 主体未注释"前端进度查询需要的字段"——M8 路由实施时会反复回头问 M4 |

**问题**：
- M4 主体契约边界表 4 行（M8 路由 / M5 url / M6 confluence / M7 OpenSearch）**没加 GET 路由契约**——M8 路由实施时**找不到 M4 提供的 IngestProgressResponse**——M8 plan 写"响应 IngestJob ORM 实体"还是"Pydantic schema"？
- M4 主体**无 `app/ingest/schemas.py`**——M8 路由找不到 schema 定义文件

### 3.7 跨 M 一致性总览

| 跨 M 对 | 一致 | 警告 | 矛盾 / 缺失 |
|---|---|---|---|
| M4 ↔ M0 | 1 | 2 | 0 |
| M4 ↔ M1 | 1 | 1 | 3（retry_count / next_retry_at / bulk update updated_at / running 态） |
| M4 ↔ M3 | 1 | 0 | 1（dim 二次断言缺失） |
| M4 ↔ M5/M6 | 1 | 0 | 3（exceptions.py / models.py / image_ref 路径） |
| M4 ↔ M7 | 1 | 0 | 3（ensure_index / INDEX_MAPPING / lifespan） |
| M4 ↔ M8 | 1 | 1 | 2（GET 路由契约 / schemas.py） |
| **合计** | 6 | 4 | **12** |

**核心发现**：**12 项跨 M 一致性缺失**——r1 修订记录写"已修"的项目中**只有 6 项在 plan 主体可见**，**12 项主体与修订记录矛盾或缺失**。**M7 卡 M4 修订**最严重（ensure_index / INDEX_MAPPING / lifespan 三个接口 M7 必须复用但 M4 主体未提供）。

---

## 4. 风险表补全质量

### 4.1 风险表结构

| 段 | 行号 | 行数 | 结构 |
|---|---|---|---|
| 原风险 | L569-582 | 10 | 风险 \| 缓解 \| 曾被否决的替代方案 |
| r1 修复 | L583-606 | 24 | 风险 \| 缓解 \| 曾被否决的替代方案（**结构相同但内容是"修复状态"不是"风险"**） |
| **合计** | 569-606 | 34 | — |

### 4.2 r1 24 行风险表内容审计

| r1 行 | 主题 | 缓解列 | 曾被否决的替代方案列 | 问题 |
|---|---|---|---|---|
| L583 | P0-1 元素分类 | "`app/ingest/element_classifier.py` + 单测" | `—` | ✅ 合理 |
| L584 | P0-2 file_extractor | "PyMuPDFReader / DocxReader 注册 + extract_images 后置 hook" | "用默认 reader：实际不抽图" | ⚠️ 替代方案列写的是 r1 review 缓解方案，不是"曾被否决的替代方案" |
| L585 | P0-3 OpenSearch 写入三件 | "mapping + refresh_interval=30s + bulk 阈值 500" | "mock 推到 M7" | ⚠️ 同上——这是 r1 review P1-1 缓解方案 |
| L586 | P0-4 chunk_id/doc_id | "uuid5 公式" | `—` | ✅ 合理 |
| L587 | P0-5 GET 进度接口 | "IngestProgressResponse schema" | `—` | ✅ 合理 |
| L588 | P1-1 testcontainers OS | "与 M0 infra 一致" | `—` | ✅ 合理 |
| L589 | P1-2 Task 估时 | "Task 5 实测 30min" | `—` | ⚠️ 数值与 plan L6 "5 个工作日" 矛盾 |
| L590 | P1-3 extract_images 走 reader | "走 file_extractor 注册 reader" | `—` | ✅ 合理 |
| L591 | P1-4 错误矩阵 | "7 条覆盖" | `—` | ⚠️ 主体 plan 错误矩阵未补 |
| L592 | P1-5 状态机迁移 | "pending → running → indexed\|failed" | `—` | ❌ 主体代码无 RUNNING 态 |
| L593 | P1-6 exceptions.py | "3 个 exception 供 M5/M6 复用" | `—` | ❌ Files 表未列 exceptions.py |
| L594 | P1-7 image_ref 路径 | "artifacts/{doc_id}/images/{file_basename}.{ext}" | `—` | ❌ 主体 L369 路径模板未改 |
| L595 | P1-8 ImageRef models.py | "M5/M6 复用" | `—` | ❌ ImageRef 仍在 sources/file.py |
| L596 | P1-9 OpenSearchClient lifespan | "async with + app.state" | `—` | ❌ 主体无 lifespan 代码 |
| L597 | P1-10 bulk update updated_at | "M1 P0-7 强约束" | `—` | ❌ 主体无显式 func.now() 传 |
| L598 | P2-1 mkdir 显式 | "ensure_artifacts_dir() 启动 lifespan 调" | `—` | ❌ 主体仍模块级 import 触发 |
| L599 | P2-2 pytest-asyncio + pytest-postgresql | "与 M0/M1 一致" | `—` | ❌ Files 表未列 |
| L600 | P2-3 asyncio_mode=auto | "继承 M0" | `—` | ❌ 测试策略段未补注释 |
| L601 | P2-4 pytest-httpx | "dev 依赖加" | `—` | ❌ Tech Stack 表 L144 未改 |
| L602 | P2-5 .env.example | "3 个 INGEST_* env" | `—` | ❌ Files 表 L200 "不修改"未改 |
| L603 | P2-6 60MB mock | "patch Path.stat" | `—` | ❌ Task 6 RED 未改 |
| L604 | P2-7 _payload_hash 流式 | "8KB chunk" | `—` | ❌ 主体 L406-407 未改 |
| L605 | P2-8 IngestJobStatus 4 值 | "VARCHAR(16) CHECK" | `—` | ⚠️ 主体未引用 RUNNING |
| L606 | P2-9 批次接口预留 | "M8 路由 V1 边界外" | `—` | ✅ 接受 |

### 4.3 风险表补全质量总评

| 维度 | 评分 | 说明 |
|---|---|---|
| 24 行 r1 修订条目完整性 | ⭐⭐⭐⭐⭐ | 24 项 + L640 联动段全在，1:1 对应 r1 review |
| 缓解列内容质量 | ⭐⭐⭐ | 大多数一行写"已修"+ 简短方案；但**主体 plan 不可执行**（缓解方案未落地到 Tasks 段代码契约） |
| 曾被否决的替代方案列 | ⭐ | 14/24 行写 `—` 或写"缓解方案"（混用结构）；3 行写与 r1 review 重复的缓解方案 |
| 与 plan 主体一致性 | ⭐ | 22/24 行主体未同步，**风险表是"声明"不是"实施"** |
| 跨 M 联动 | ⭐⭐⭐ | L640 联动段是唯一真落地（7 项 M0/M1/M3/M5/M6/M7/M8） |

**核心问题**：
1. **风险表 vs 修复记录结构混用**——34 行风险表 = 10 行原风险 + 24 行 r1 修复，但**结构相同**（3 列），导致"风险"和"修复"读起来**同质化**——读者分不清哪行是"待缓解的风险"哪行是"已修复的状态"
2. **「曾被否决的替代方案」列在 r1 24 行写 `—` 占位无意义**（r1 修订记录里这些行多数是"修复说明"不是"风险"）——r1 应**独立成段**「r1-2026-06-11 修复清单」或用 2 列结构（修复项 \| 落地位置）
3. **风险表 24 行"缓解方案"与 plan 主体脱节**——L585 P0-3 写"mapping + refresh_interval=30s + bulk 阈值 500"，但 plan 主体 L266-293 仍 `refresh=False` 无 mapping 无阈值——**风险表是"声明"，plan 主体是"现实"，二者矛盾**

### 4.4 与已有 review 风险表对比

| review | 风险表行数 | 落地率 | 备注 |
|---|---|---|---|
| M0 review | 9 行 P0/P1 + 5 行 P2 = 14 行 | 主体 11/14 = 78.6% | M0 infra 风险大多落地 |
| M1 review | 8 行 P0/P1 + 5 行 P2 = 13 行 | 主体 10/13 = 76.9% | M1 schema 风险大多落地 |
| M3 review | 6 行 P0/P1 + 3 行 P2 = 9 行 | 主体 7/9 = 77.8% | M3 风险大多落地 |
| **M4 r1 review** | **5 行 P0 + 10 行 P1 + 9 行 P2 = 24 行** | **主体 0/24 = 0%** | **M4 r1 主体同步率 0%**——24 项全部仅"修订记录行" |

**M4 r1 主体同步率 0% 是 5 M 中最差**——M0/M1/M3 都有 76-79% 主体同步率，M4 r1 主体**完全未改**。

---

## 5. 落地建议

### 5.1 r2 必做（r1 修复主体同步）

按 r1 review 24 项修复**逐项展开成 plan 主体修改**：

#### 第一波 · 5 项 P0 主体同步（最优先）

1. **P0-1 主体** · Architecture 段 L57-65 仓库布局补 `app/ingest/element_classifier.py`；Files 表 L168-189 加该文件行；Task 4 GREEN L311-332 后插 Task 4.1 "classify_elements 实现" 段（RED-GREEN-REFACTOR）；Tech Stack 表补 `BaseElementNodeParser` 依赖
2. **P0-2 主体** · Task 4 GREEN L311-332 重写 `read_file`，加 `FILE_EXTRACTORS = {".pdf": PyMuPDFReader(), ".docx": DocxReader(), ...}`；pyproject 修改段 L190-192 加 `pymupdf>=10.0`；Task 4 GREEN L347-374 `extract_images` 改走 `reader output` 而非 `doc.metadata["images"]`
3. **P0-3 主体** · Task 3 GREEN L266-293 加 `INDEX_MAPPING` 全局常量 + `ensure_index(index_name)` 方法 + `BULK_THRESHOLD = 500` 阈值；`upsert_chunks` 改 `await self.ensure_index(index_name)` 入口；`refresh_interval=30s` 显式传
4. **P0-4 主体** · Task 4 GREEN L319-321 重写 `_doc_id_from_path` 为 `uuid5(NAMESPACE_URL, file_path + file_size + mtime)`；Task 5 GREEN L440-444 chunk id 显式构造 `chunk.id_ = uuid5(NAMESPACE_URL, f"{doc_id}:{chunk_index}")` + 写 `chunk_id` metadata
5. **P0-5 主体** · Architecture 段 L116-124 契约边界表加 M8 GET 路由行（"返回 `IngestProgressResponse{status, chunks_count, error?, duration_seconds}`"）；Files 表 L168-189 加 `app/ingest/schemas.py`；补该文件 Pydantic schema 完整定义

#### 第二波 · 10 项 P1 主体同步

6. **P1-1 主体** · Task 6 L488-498 fixture 改 `testcontainers[opensearch]` 配 `opensearchproject/opensearch:2.19.0`；测试策略段 L531-538 改"OpenSearch 真容器"
7. **P1-2 主体** · Tasks 段标题 L205 改"（Task 1-2: 5-10 min；Task 3-5: 20-30 min；Task 6: 30-40 min）"；估时 L6 统一 5d（**删除 r1 修订记录 L622 "2h→2.5h" 与 L6 "5d" 的矛盾**——选 L6 5d）
8. **P1-3 主体** · 同 P0-2 主体
9. **P1-4 主体** · 风险表 L569-582 补错误矩阵 7 条（401/422/429/404/500/DB-down 降级/OS 5xx 退避）；Task 5 GREEN L460-466 `_mark_failed` 加 `try/except SQLAlchemyError` 分支 + `IngestJobStore` 内存缓冲
10. **P1-5 主体** · Task 5 GREEN L398-399 引用 `transition_status(job, from_, to_)` 工具；L423-428 改 `status=IngestJobStatus.RUNNING`（split 前）；L454-456 改 `transition_status(job, RUNNING, INDEXED)`；L462-465 改 `transition_status(job, RUNNING, FAILED)`；加 `retry_count += 1` + `next_retry_at = now() + backoff`（M1 P2-5 字段启用）
11. **P1-6 主体** · Files 表 L168-189 加 `app/ingest/exceptions.py`（`OversizedFileError` / `UnsupportedFileTypeError` / `ParseError`）行
12. **P1-7 主体** · 契约边界表 L116-124 加 M5/M6 image_ref 路径规范行（`artifacts/{doc_id}/images/{file_basename}.{ext}`）；Task 4 GREEN L368-372 改 `relative_path=f"{doc_id}/images/{file_basename}.{ext}"`
13. **P1-8 主体** · Files 表 L168-189 加 `app/ingest/models.py`（`ImageRef` dataclass）行；Task 4 GREEN L352-358 移除 `ImageRef` 定义（移到 models.py）
14. **P1-9 主体** · Task 3 GREEN L266-293 加 `__aenter__/__aexit__` + 模块级 `_default_client` 单例 + `aclose()` + `get_opensearch_client()` 工厂
15. **P1-10 主体** · Task 5 GREEN L451-466 pipeline 状态更新显式 `updated_at=func.now()`（不依赖 ORM onupdate）

#### 第三波 · 9 项 P2 主体同步

16. **P2-1 主体** · Task 1 REFACTOR L219 改"`app/ingest/storage.py:ensure_artifacts_dir()` 启动 lifespan 调一次"
17. **P2-2 主体** · Files 表 L190-192 pyproject 修改段补 `pytest-asyncio>=0.24,<1` + `pytest-postgresql>=6,<7`
18. **P2-3 主体** · 测试策略段 L531-538 补"`pytest.ini` 已含 `asyncio_mode = auto`（M0 P2-1）"
19. **P2-4 主体** · Tech Stack 表 L144 改"测试：`pytest` / `pytest-asyncio` | spec §8.7 已含"（删除 `pytest-httpx`）
20. **P2-5 主体** · Files 表 L200 改"修改"：`.env.example` 追加 `INGEST_MAX_FILE_SIZE_MB=50` / `INGEST_BULK_THRESHOLD=500` / `OPENSEARCH_REFRESH_INTERVAL=30s` / `INGEST_ARTIFACTS_DIR` / `INGEST_CHUNK_SIZE` / `INGEST_CHUNK_OVERLAP` / `INGEST_OPENSEARCH_INDEX`
21. **P2-6 主体** · Task 6 RED L513-520 改 `monkeypatch.setattr("pathlib.Path.stat", lambda self: SimpleNamespace(st_size=60*1024*1024))`
22. **P2-7 主体** · Task 5 GREEN L406-407 改流式 hash
23. **P2-8 主体** · Task 5 GREEN 注释 "M1 schema 落定 `IngestJobStatus` 枚举值含 PENDING/RUNNING/INDEXED/FAILED 四值（VARCHAR(16) CHECK）"
24. **P2-9 主体** · 契约边界表 L116-124 加 M6 批次接口行（M4 不暴露批量接口，M6 写 `for path in paths: ingest_file(path, user_id)` 串行）

### 5.2 r2 必做（r1 引入新问题修复）

1. **r1 修订记录自相矛盾**（P1-2 估时 5d vs 2.5h / P0-3 refresh_interval=30s vs refresh=False / P1-5 running 态 vs 主体无 RUNNING）——**r2 主体同步时统一为单一数值/行为**
2. **r1 风险表结构混用**（10 行风险 + 24 行修复同 3 列结构）——**r2 把 24 行 r1 修复从风险表剥离**到独立段「r1-2026-06-11 修复清单」（2 列结构：修复项 \| 落地位置）
3. **L640 跨 M 联动段保留**——r1 唯一真落地段，r2 不动

### 5.3 跨 M 协调（r2 完成后通知）

- **推 M1**：`ingest_jobs.retry_count` / `next_retry_at` 字段启用（M4 P1-5 主体修复后用）
- **推 M3**：`TEIEmbedder.embed()` 返 dim 漂移时 M4 端到端 dim 二次断言（M4 主体加 `assert len(vec) == 1024` 写 OpenSearch 前）
- **推 M5/M6**：复用 M4 `app/ingest/element_classifier.py`（HTML 元素分类）+ `app/ingest/exceptions.py` + `app/ingest/models.py::ImageRef`（image_ref 路径规范 `artifacts/{doc_id}/images/{file_basename}.{ext}`）
- **推 M7**：M4 已建 `chunks` 索引 mapping + `ensure_index` + lifespan 单例 `get_opensearch_client()`——M7 retriever 复用
- **推 M8**：用 `app/ingest/schemas.py::IngestProgressResponse` 响应 `GET /api/ingest/{job_id}`

### 5.4 估时修正

M4 r1 修复**主体同步**（24 项 + 自相矛盾修正 + 风险表结构剥离）估时 **2-3d**（每项 P0 1-2h 主体改 / 每项 P1 30-60min / 每项 P2 15-30min）：
- P0 5 项 × 1.5h = 7.5h
- P1 10 项 × 45min = 7.5h
- P2 9 项 × 20min = 3h
- 风险表结构改 + 跨 M 协调 = 4h
- 单测补 + 集成测试 = 4h
- **合计 ~26h = 3.5d**

加上 M4 r0 主体实施 5d + r2 主体同步 3.5d = **M4 总实施 8.5d**（与 r1 review 估时"5-6 个工作日" + r1 主体同步 2-3d 累加一致）。

### 5.5 等待决策

- **r2 是否独立 subagent 执行**？建议派独立 subagent 改 plan 主体（24 项主体同步 + 3 项 r1 引入新问题），main agent 不再手 patch write_file——避免**再撞 24 项"修订记录行 vs 主体脱节"反模式**
- **r1 风险表 24 行结构**是"修复清单混入风险表"还是"独立段"——推荐**独立段**「r1-2026-06-11 修复清单」2 列结构，与 M0/M1/M3 风险表一致
- **P0-3 OpenSearch 集成测试**走 testcontainers 真实容器延迟高（30s+）——是否接受 CI 慢但 spec §6 一致性

---

## 状态

- **r1 修订记录清单完整度**：24/24 = 100%（修订记录行 L616-639 全在）
- **r1 plan 主体同步率**：0/24 = 0%（**核心问题**——M4 r1 是 5 M 中同步率最低）
- **r1 跨 M 联动段 L640 落地**：✅ 真落地（7 项 M0/M1/M3/M5/M6/M7/M8 联动项列全，r1 唯一主体可见修复）
- **r1 引入新问题**：3 项（修订记录自相矛盾 + 风险表结构混用 + P1-5 running 态主体无）
- **跨 M 一致性缺失**：12 项（M0: 0 / M1: 4 / M3: 1 / M5/M6: 3 / M7: 3 / M8: 2）
- **M7 卡 M4 修订**：3 项（`ensure_index` / `INDEX_MAPPING` / lifespan 缺失）——**M7 实施必须回头改 M4 主体**
- **范本传染面**：M5/M6 复制 M4 主体时**仍会复制 22 项 r1 未落地缺陷**（P0-1 元素分类 / P0-3 mapping / P1-7 image_ref 路径 / P1-8 models.py 等）

**M4 r1 是"清单修复"不是"主体修复"**——24 项修订记录条目 100% 在但 plan 主体同步率 0%。**M5/M6 复制 M4 范本前必须 r2 主体同步**——否则 M5/M6 会复制 22 项 r1 未落地缺陷。**M4 plan 主体同步是 r2 必做**——派独立 subagent 改 plan 主体 24 项 + 3 项 r1 引入新问题，避免 main agent 写 write_file 再追写记录行反模式。
