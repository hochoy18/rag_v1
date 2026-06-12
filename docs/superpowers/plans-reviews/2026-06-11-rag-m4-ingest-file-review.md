# M4 Plan Review · Ingest File Source

> 评审对象：`2026-06-11-rag-m4-ingest-file.md`（590 行，v0 初稿 2026-06-11）
> 评审基线：V1 Scope v0.4 spec §0 决策 #4/#18/#19 · §2 模块树 ingest+retrieval+db 段 · §3.1 Ingest 数据流 · §4 API `GET /api/ingest/{job_id}` · §5 错误矩阵 11 条 · §6 测试策略 · §8.2 Embedding & 文档解析栈 7 包；M0/M1/M2/M3 review P0/P1 全部；总 review `2026-06-11-rag-plans-review.md` P0-1/P0-5/P1-4/P1-5/P1-16/P2-7/X-1/X-3；M3 review 新增（TEIEmbedder dim 硬断言等）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M4 plan 是 V1 ingest 路线**首个 source 实现**，结构完整（11 段：Goal/不包含/Architecture/Tech Stack/Files/Tasks RED-GREEN/测试/DoD/依赖/风险/修订记录），技术版本与 spec §8.2 **精确对齐**（llama-index==0.14.8 / llama-index-readers-file==0.4.0 / httpx>=0.27 / tenacity>=8.3 / opensearch-py>=2.6），并**主动吸收**了跨 M review 的关键 P0/P1（端口 18080 P0-1、真 PG 容器 P0-5、updated_at ORM 走 session.add P1-4、payload_hash UNIQUE 约束 P1-5、settings 全局单例 X-3、async_session 口径 P2-7），仓库布局与 M3 范本一致，契约边界表覆盖 M5/M6/M7/M8/M11 全部下游。

但作为"source 适配器样板"（自警 L7：M4 给 M5/M6 提供 parse→split→embed→upsert 样板），实施就绪度**严重不足**：

1. **元素分类完全缺**：Goal L18 写"处理图片元素"，但全文**没有"元素分类"的代码或测试**——`NarrativeText / Table / Image` 这层 LlamaIndex `BaseElementNodeParser` 完全没提
2. **图片抽取**是 spec §3.1 显式要求，Task 4 GREEN 段 `extract_images` 实现**依赖 LlamaIndex Reader 默认产出 `doc.metadata["images"]`**——但 `SimpleDirectoryReader` 默认**不抽图片**，需要显式配 `pdf_as_image=True` 或用 `ImageParser` 组合；L573 风险表自警"不同 file format 表现不一"但**没给 `file_extractor` 显式配置**这一关
3. **OpenSearch 写入层三件缺**——Index mapping 显式声明、refresh interval 策略、bulk vs single 切换，**全没写**；M4 集成测试 OpenSearch 走 mock，M7 才接真 cluster → M4 写完到 M7 接入会爆雷
4. **chunk ID 生成策略 / 重复文档检测 / 文件 hash vs payload_hash 关系 / chunks_count 事务边界**——4 个核心一致性细节**全没写**
5. **spec §4 显式要求的 `GET /api/ingest/{job_id}` 进度查询接口**——M4 plan 不实现（M8 写）但**完全没在契约边界表列出**，M8 API 设计与 M4 实现的 `IngestJob` 字段（status / chunks_count / error / created_at / updated_at）会脱节
6. **每 Task 写 2-5 分钟但部分超**（Task 5 实际 4 个 RED 测试 + ORM + bulk + 异常处理，**实测 25-30 分钟**，与 M0 review P2-6 / M3 review P1-6 同类问题）

| 维度 | 评分 | 说明 |
|---|---|---|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐，Goal/不包含/契约边界表/风险表 都齐 |
| 一致性 | ⭐⭐⭐⭐ | 5 个直接依赖版本逐一对齐 spec §8.2；主动吸收了 6 项已有 P0/P1 |
| 实施就绪度 | ⭐⭐ | 元素分类、图片抽取、OpenSearch 写入层、chunk ID、进度接口契约——5 大块缺 |
| 错误处理 | ⭐⭐ | spec §5 错误矩阵 11 条覆盖 4 条（OpenSearch / TEI / 解析失败 / 附件超大），缺 7 条 |
| 范本示范性 | ⭐⭐ | "M4 给 M5/M6 提供 source 样板"——但元素分类和图片抽取两块是 M5/M6 **都会复用**的核心，缺了会复制缺陷 |
| 跨 M 契约 | ⭐⭐⭐ | 边界表覆盖 M5/M6/M7/M8/M11，**漏 `GET /api/ingest/{job_id}` 契约** |

**一句话**：M4 plan **结构对、版本对、主动修了 6 项已有 P0/P1**，但作为"source 样板"**5 大实施细节缺**（元素分类 / 图片抽取配置 / OpenSearch 写入层 / chunk ID / 进度接口契约）；M4 集成测试 OpenSearch 走 mock 会**延迟爆雷到 M7**。**修完 5 个 P0 + 6 个 P1 后是合格 source 实现**；P0+P1+P2 修完后才能作为 M5/M6 范本。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · 元素分类（NarrativeText / Table / Image）完全缺实现与测试

**位置**：Goal L18 写"处理图片元素：抽到 `artifacts/{doc_id}/images/`，元数据 `image_ref`"；spec §3.1 显式写"元素分类（NarrativeText / Table / Image / ...）"；但 Tech Stack 表 / Architecture / Tasks / Files **全没提 `BaseElementNodeParser` / `SimpleNodeParser` / `UnstructuredElementNodeParser`**

**问题**：
- LlamaIndex `SimpleDirectoryReader.load_data()` 默认**只产 `Document`**，不分元素类型——`doc.metadata["images"]` 不是 SimpleDirectoryReader 的输出，需要先跑 `BaseElementNodeParser`（用 `unstructured.io` 后端）才出 `ImageDocument` / `TextNode` 含 `node_type`
- 实际代码段（Task 4 GREEN L347-374）`for img in doc.metadata.get("images", []):` 拿不到任何东西（`doc.metadata["images"]` 默认不存在），`extract_images` 永远返空 list → 集成测试 L497 断言 "artifacts_dir / doc_id / images 含 1 个 PNG" 假绿
- spec §3.1 显式要求"元素分类"——M4 跳过，M5（url HTML）/ M6（Confluence storage format）**会全部需要这层**，M4 不做意味着 M5/M6 都要重做
- 元素分类决定**表格内容是否要单独 chunk**——`Table` 元素应整表一个 chunk（不切碎），`NarrativeText` 才走 `SentenceSplitter`——M4 不分类导致 table 也被 512 token 切碎，**信息丢失**（表格行一半在 chunk A、一半在 chunk B）

**修改**（Task 4 GREEN 段加，插在 `read_file` 之后、`extract_images` 之前）：

```python
# app/ingest/sources/file.py（追加）
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core.schema import Document, ImageDocument, TextNode, BaseNode, NodeRelationship, RelatedNodeInfo

def classify_elements(docs: list[Document]) -> list[BaseNode]:
    """把 Document 拆成 BaseNode 列表，按 node_type 分流。

    V1 策略：
      - ImageDocument → 抽到 artifacts_dir/doc_id/images/，写 image_ref metadata
      - TextNode / Table（type_='table'）→ 保留，append 到 nodes 列表
      - 其余 → 走 SentenceSplitter 二次切分
    """
    parser = SimpleNodeParser()  # 或 UnstructuredElementNodeParser
    nodes: list[BaseNode] = []
    for doc in docs:
        if isinstance(doc, ImageDocument):
            # 抽到 artifacts_dir（走 extract_images 同一路径）
            nodes.extend(_handle_image(doc))
            continue
        # 文本类（含 table）→ 走 node_parser
        nodes.extend(parser.get_nodes_from_documents([doc]))
    return nodes
```

并在 Files 表新增：
- `app/ingest/elements.py` —— `classify_elements` 实现 + `is_table_node` 工具
- `tests/unit/test_ingest_elements.py` —— 单测覆盖 ImageDocument / TextNode / Table 三类

**注**：P1-13/M1 范围未列，**M4 独有**——M5/M6 复用这层会改 3 份 plan。

### P0-2 · 图片抽取依赖 SimpleDirectoryReader 默认行为（不抽图），但 plan 没给 `file_extractor` 显式配置

**位置**：Task 4 GREEN L347-374 `extract_images` 实现；风险表 L573 自警"LlamaIndex `ImageDocument` 元素类型在不同 file format 表现不一"

**问题**：
- `SimpleDirectoryReader` 默认**对 PDF 不抽内嵌图片**——只抽文本流；只有显式配 `file_extractor` 含 `PDFParser` 且 `pdf_as_image=True` 才会出图
- 风险表 L574 提到"走 `doc.metadata["images"]` 防御式读取（fallback 空列表）"——但这就是承认**默认读不到图**，集成测试必然假绿
- 不同 file format 图片抽取 API 不一样：
  - PDF：`PyMuPDFReader` / `PDFParser`（pymupdf 依赖）
  - Word（docx）：`docx2txt` 默认抽，但**内嵌图需解 zip+xml**
  - PPT：内嵌图在 `ppt/media/`
  - MD：图片是外链，**不抽本地图**
- 任务里说"4 种格式"，但代码完全没考虑格式差异；M4 集成测试**只测 PDF**，M5/M6 复制代码后**Word/PPT 图片都丢**

**修改**（Task 4 GREEN 段 + Files 表）：

```python
# app/ingest/sources/file.py（重写 read_file）
from llama_index.core import SimpleDirectoryReader
from llama_index.core.readers.file import PDFParser, DocxParser, PptxParser, MarkdownParser
from pathlib import Path

FILE_EXTRACTORS = {
    ".pdf": PDFParser(),  # 显式构造，pymupdf 后端
    ".docx": DocxParser(),
    ".pptx": PptxParser(),
    ".md": MarkdownParser(),
}

def read_file(path: Path) -> tuple[list[Document], str]:
    ext = path.suffix.lower()
    if ext not in FILE_EXTRACTORS:
        raise UnsupportedFormatError(
            f"Unsupported file format: {ext}. "
            f"Supported: {list(FILE_EXTRACTORS.keys())}"
        )
    reader = SimpleDirectoryReader(
        input_files=[str(path)],
        file_extractor=FILE_EXTRACTORS,
    )
    docs = reader.load_data()
    return docs, _doc_id_from_path(path)
```

并补：
- `app/ingest/exceptions.py` 新增 `UnsupportedFormatError`
- `pyproject.toml` 显式声明 `pymupdf>=10.0` 依赖（PDFParser 走 pymupdf 后端）
- `tests/unit/test_ingest_file_source.py` 加 `test_unsupported_format_raises` RED 测试

### P0-3 · OpenSearch 写入层三件缺（index mapping / refresh interval / bulk 阈值），M4 mock 推到 M7 才爆雷

**位置**：Task 3 GREEN L266-293 `OpenSearchClient.upsert_chunks`；DoD L546 写"AsyncOpenSearch.upsert_chunks 走 bulk + tenacity 3 次重试"

**问题**：
- **Index mapping 完全没显式声明**：`chunks` 索引需要建 `vector: knn_vector, dim=1024, similarity=cosine` + `text: text` + `metadata: object` + `metadata.doc_id: keyword`（filter 用）——M4 集成测试 OpenSearch 走 mock（Task 6 L492 "OpenSearch 走 mock"），**M4 写完到 M7 集成测试首次跑真 cluster 会全报错**："no handler found for [vector]" / "similarity=cosine" 拼错
- **refresh interval 没设**：`refresh=False`（当前写法）→ ingest 完成后立刻 query 查不到新数据，RAG 端到端**首次 ingest 后第一次 query 返回 0 chunk**——这是 M4 集成测试不查 OpenSearch 所以**永远发现不了**的真问题
- **bulk 阈值没定**：1000 chunk 一次 bulk vs 拆 100+100+... vs chunk 极少时直接 single index；当前代码**无条件走 bulk**，50 个 chunk 也走 bulk 性能不如 single
- 风险表 L575 写"OpenSearch bulk 失败但部分 chunk 已写入" — 这条缓解措施需要 mapping 一致才能复现，**mock 验不出**

**修改**（Task 3 GREEN 段补 + 新 Task 3.5）：

```python
# app/retrieval/client.py（追加）
INDEX_MAPPING = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_construction": 256,  # bge-m3 cosine 经验值
            "refresh_interval": "5s",                # ingest 后 5s 内可查
        }
    },
    "mappings": {
        "properties": {
            "text":     {"type": "text", "analyzer": "ik_max_word"},  # 中文友好
            "vector":   {"type": "knn_vector", "dimension": 1024, "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "nmslib"}},
            "metadata": {"properties": {
                "source":     {"type": "keyword"},
                "doc_id":     {"type": "keyword"},
                "page_id":    {"type": "integer"},
                "image_ref":  {"type": "keyword"},
                "chunk_id":   {"type": "keyword"},
                "user_id":    {"type": "keyword"},
            }},
        }
    },
}

BULK_THRESHOLD = 100  # 低于此走 single，高于此走 bulk

class OpenSearchClient:
    async def ensure_index(self, index_name: str) -> None:
        exists = await self._client.indices.exists(index=index_name)
        if not exists:
            await self._client.indices.create(index=index_name, body=INDEX_MAPPING)

    async def upsert_chunks(self, chunks: list[TextNode], index_name: str) -> int:
        await self.ensure_index(index_name)
        if len(chunks) < BULK_THRESHOLD:
            return await self._upsert_single(chunks, index_name)
        return await self._upsert_bulk(chunks, index_name)
```

并补：
- 单测 `test_ensure_index_creates_with_mapping`
- 单测 `test_upsert_below_threshold_uses_single`
- 集成测试在 M4 阶段跑**真 OpenSearch 容器**（不 mock）——这是 M7 验收提前到 M4，避免 P0-3 延迟爆雷

### P0-4 · chunk ID / doc_id 生成策略 + payload_hash 与文件 hash 关系完全没定

**位置**：Task 4 GREEN L319-321 `_doc_id_from_path` 用 `sha256(absolute_path)[:16]`；Task 5 GREEN L406-407 `_payload_hash` 用 `sha256(file_content)`；Task 5 GREEN L443-444 chunk metadata 没 chunk_id 字段

**问题**：
- **doc_id 由路径决定**——同一文件 `cp a.pdf b.pdf`（不同路径）**生成不同 doc_id**，导致同一内容**索引两套 chunk**（重复入库，但 payload_hash 幂等也救不了——查的是 payload_hash 不是 doc_id）
- **chunk_id 字段缺失**：`OpenSearchClient.upsert_chunks` 用 `chunk.id_`（LlamaIndex TextNode 默认 UUID）——但 LlamaIndex 默认 ID 不稳定（同一 doc 多次 split 出来 ID 不同），OpenSearch upsert 用 `chunk.id_` 作 `_id` 会**每次都新建不更新**
- **payload_hash 重复粒度粗**（spec 决策，M1 review P1-5 已修 UNIQUE 约束）：同一文件**不同用户上传**（M4 走 `user_id` 但 hash 不含 user_id）被识别为幂等——A 上传完，B 上传同文件**看不到自己的 ingest_job 行**
- **file hash 与 payload_hash 重复**：`_payload_hash` 读全文，doc_id 用 `sha256(path)[:16]`——但**集成测试**断言"payload_hash == sha256(file_content)"**没断言"doc_id == sha256(path) 前 16"**（M1 schema `ingest_jobs.doc_id` 是 16 字符还是 32 字符没在 M1 review 锁定）

**修改**（Task 4 GREEN + Task 5 GREEN + 单测补）：

```python
# app/ingest/sources/file.py（_doc_id_from_path 重构）
import uuid

def _doc_id_from_path_and_content(path: Path, content: bytes) -> str:
    """doc_id = sha256(content) 前 32 字符（与 M1 ingest_jobs.doc_id VARCHAR(32) 对齐）。

    Why：用内容而非路径——同一文件多路径 / 移动位置不重复入库。
    """
    return hashlib.sha256(content).hexdigest()[:32]
```

```python
# app/ingest/pipeline.py（chunks id 稳定化）
for chunk, vec in zip(chunks, vectors):
    chunk.embedding = vec
    # chunk_id 显式构造：f"{doc_id}:{chunk_index}" 跨调用稳定
    chunk.id_ = f"{doc_id}:{chunks.index(chunk):04d}"
    chunk.metadata["chunk_id"] = chunk.id_  # 写入 metadata 给 OpenSearch filter 用
    chunk.metadata["user_id"] = user_id     # 解决"payload_hash 跨用户"问题（filter 时用）
    ...
```

并补：
- 集成测试 `test_doc_id_stable_across_path_rename`（同内容不同路径 → 同 doc_id）
- 集成测试 `test_chunk_id_stable_across_reingest`（同 doc_id 重新 split → chunk_id 一致）
- Task 5 GREEN 段注释明确"payload_hash + user_id"是幂等键，doc_id 跨用户可相同

### P0-5 · spec §4 显式要求的 `GET /api/ingest/{job_id}` 进度查询接口在契约边界表里完全没列

**位置**：spec §4 API 表 L272 写 `GET /api/ingest/{job_id} | 有 | 进度查询`；M4 plan Architecture L118-124 "M4 与其他 M 的契约边界" 表**没列**；M4 plan L29 "不包含：/api/ingest 真实路由 + Pydantic schema + 鉴权依赖注入 → M8"

**问题**：
- M8 写 `/api/ingest` 路由时，**必须知道** `IngestJob` ORM 暴露哪些字段给前端——M4 plan **没明确列出"前端进度查询需要的字段集"**
- 实际前端要查的字段：`job_id` / `status`（pending/indexed/failed/skipped）/ `chunks_count` / `error` / `created_at` / `updated_at` / `duration` / `source` / `doc_id` / `payload_hash` —— M4 写 IngestJob 时**没注释"这些字段前端进度页要"**
- M4 plan L427-429 `IngestJob` 字段没在 plan 完整列出（M1 review 修了 P1-1 / P2-5 / P2-7 等字段，但 M4 写 pipeline 时**只引用** `IngestJob` 实体，不显式列字段）
- 进度查询是**长任务前端**必备，缺了 M8 路由实现时**反复回头改 M4 pipeline 加字段**

**修改**（Architecture 段补"前端进度接口契约"小节 + Files 表加 `app/ingest/schemas.py`）：

```python
# app/ingest/schemas.py（新文件）
from pydantic import BaseModel
from datetime import datetime

class IngestJobProgress(BaseModel):
    """M4 提供 / M8 路由 GET /api/ingest/{job_id} 序列化契约。
    
    Why 显式 schema：M8 路由不需再 import M1 ORM 实体，避免耦合。
    """
    job_id: str
    status: str             # pending / indexed / failed / skipped
    source: str             # file / url / confluence
    doc_id: str
    chunks_count: int
    error: str | None
    created_at: datetime
    updated_at: datetime
    duration_seconds: float  # computed: updated_at - created_at
```

并在契约边界表加：
- M8 `/api/ingest` 路由 GET 分支用 `IngestJobProgress` 响应

**注**：spec §4 + M1 schema 已有 `ingest_jobs` 表字段 + M4 plan L413-428 写 ORM 用法——但**响应 schema** 是新文件，显式列 M4 范围内。

---

## P1 · 重要

### P1-1 · M4 集成测试 OpenSearch 走 mock（Task 6 L492），延迟爆雷到 M7

**位置**：Task 6 L488-498 RED 测试 "test_full_ingest_file"；L492 "mock OpenSearch（避免真实 cluster 依赖）"

**问题**：
- 跨 M review P0-5 已修"PG 必须真"，但** OpenSearch 反着走 mock **——这与 spec §6 测试策略"集成：起真实 OpenSearch + TEI + Postgres + Langfuse"冲突
- 风险表 L581 自警"M4 集成测试 OpenSearch 走 mock 错过真实 cluster 集成问题 / 缓解：M7 集成测试覆盖真实 OpenSearch"——这是**主动选择延迟**，但 M4 写完到 M7 接入如果 OpenSearch 索引 mapping 错、bulk API 调用错、refresh 策略错，**M7 集成测试会发现一堆 M4 引入的 bug**
- spec §6 L308 显式要求"集成：起真实 OpenSearch + TEI + Postgres + Langfuse"

**修改**：Task 6 fixture 改：
```yaml
# conftest.py（追加）
@pytest.fixture(scope="session")
def opensearch_container():
    """真 OpenSearch 容器，dim=1024 HNSW cosine 预建索引。"""
    with testcontainers_opensearch(
        image="opensearchproject/opensearch:2.19.0",
        env={"discovery.type": "single-node", "DISABLE_SECURITY_PLUGIN": "true"},
    ) as container:
        client = AsyncOpenSearch(hosts=[container.http_uri])
        # 预建 chunks 索引（P0-3 mapping）
        await client.indices.create(index="chunks", body=INDEX_MAPPING)
        yield client
```

并在 testcontainers 列表加 `testcontainers[opensearch]` 到 dev 依赖。

### P1-2 · 7 个 Task 估时 2-5 分钟，实测多数超（Task 5 实际 25-30 分钟）

**位置**：Tasks 段 L205-527 标"（2-5 分钟/step 粒度）"；M4 plan 估时 3 个工作日

**问题**：
- Task 5 RED 段 L380-484 实际含 4 个 RED 测试 + 1 个 GREEN 实现 + 1 个 REFACTOR 拆函数：拆开看每步 5-10 分钟，**Task 5 总耗时 30-40 分钟**
- Task 6 RED 段 L488-520 实际含 3 个 RED 测试 + 3 个 GREEN 段：20-30 分钟
- Task 4 含 4 个 RED + 2 个 GREEN + 1 个 REFACTOR：30 分钟
- 这是 M0 review P2-6 / M3 review P1-6 同类问题——M4 复制了"估时 2-5 分钟"反模式
- 3 个工作日估时（`/home/hochoy/.hermes/profiles/coder/docs/superpowers/specs/2026-06-10-rag-v1-scope.md` §7 L334）也是**严重低估**——元素分类 + 图片抽取 + OpenSearch 写入层 + 集成测试 P1-1 修正后，实际 5-6 个工作日

**修改**：
- Tasks 段标题"（2-5 分钟/step 粒度）"删掉，改"（Task 1-2: 5-10 min；Task 3-5: 20-30 min；Task 6: 30-40 min）"
- 估时从 3d 改 5d
- DoD 标注"Task 5 实测 30-40 min"防止低估传染

### P1-3 · `extract_images` 假设 `doc.metadata["images"]` 默认存在，但 SimpleDirectoryReader 默认不抽图

**位置**：Task 4 GREEN L347-374；详见 P0-2

**问题**（独立 P1 视角）：
- 即便补了 P0-2 的 `file_extractor` 显式配置，`doc.metadata["images"]` 仍是**非标准字段**——LlamaIndex Reader 不保证产出这个 key
- PDFParser / DocxParser / PptxParser / MarkdownParser **各自 metadata schema 不一样**
- `extract_images` 应该走 `BaseElementNodeParser` 输出的 `ImageDocument`（标准 schema）而非 `doc.metadata["images"]`（自定义）

**修改**：与 P0-1 合并实现——`classify_elements` 拆出 `ImageDocument` 后调 `_handle_image` 写 artifacts，无需依赖 `doc.metadata["images"]`。

### P1-4 · 错误矩阵 spec §5 11 条仅覆盖 4 条，缺 7 条（鉴权、Postgres 降级、OpenSearch 限速、Confluence 等）

**位置**：风险表 L570-582 9 条；spec §5 L285-299 11 条

**问题**：
- spec §5 错误矩阵 11 条：
  1. OpenSearch 不可达 → spec 写"503 + 管理员提示" → M4 写 `OpenSearchClient.upsert_chunks` 重试 3 次后**没标最终失败行为**
  2. TEI embedding 超时 → spec 写"指数退避 3 次 → 报错；ingest 任务标 failed，可重试" → M4 L477-484 有 test_ingest_marks_failed_on_embed_error OK
  3. LLM 4xx/5xx → **M4 不涉及**（LLM 在 M7/M8）
  4. 检索 top-k 全 0 分 → **M4 不涉及**
  5. Postgres 不可达 → spec 写"checkpointer 不可用 → 降级本地 SQLite；UI 告警" → M4 写 ingest_jobs 写入，**完全没提 Postgres 不可达**
  6. Confluence API 401/403 → **M4 不涉及**（M6）
  7. Confluence 429 → **M4 不涉及**（M6）
  8. 文档解析失败（PDF 损坏） → spec 写"单文件失败不阻塞批次" → M4 L580 自警"单 file 解析失败抛错并 mark failed；M6 批次场景 try/except 单文件隔离"——M4 是单文件场景，**M4 plan 应给完整 try/except 实现而非"M6 完善"**
  9. 附件超大 (>50MB) → spec 写"跳过，记日志，不进 RAG" → M4 L513-520 `test_ingest_skips_oversized_attachment` OK
  10. 用户未登录访问 /api/chat → **M4 不涉及**（M8）
  11. session_id 越权 → **M4 不涉及**（M8）

- M4 范围**应覆盖**的错误矩阵：1 / 2 / 5 / 8 / 9（5 条）。当前覆盖 1（部分）/ 2 / 9 = 2.5 条，**缺 2.5 条**。
- **Postgres 不可达**（#5）——M4 写 ingest_jobs INSERT 时 PG 挂了，pipeline 标 FAILED 都没法写 → **M4 缺这个 fallback**

**修改**（Task 5 GREEN 段补）：
```python
# pipeline.py
async def _mark_failed(job_id: int, exc: Exception, session_factory=async_session) -> None:
    """PG 不可达时用 SQLite 降级写 failure log（M1 review X-3 同款 fallback）。"""
    try:
        async with session_factory() as session:
            job = await session.get(IngestJob, job_id)
            job.status = IngestJobStatus.FAILED
            job.error = str(exc)[:1000]
            session.add(job)
            await session.commit()
    except SQLAlchemyError as pg_err:
        # PG 完全不可达，fallback SQLite 写运维日志
        await _log_to_sqlite_fallback(job_id, str(exc), str(pg_err))
```

并在 spec §5 错误矩阵"OpenSearch 不可达"行加缓解细节：
- ingest 阶段：tenacity 3 次重试失败 → 标 FAILED，**不写 OpenSearch 的 chunk 留 staging**
- retrieval 阶段：M7 retriever 走 503 兜底（spec §5 已写）

### P1-5 · `ingest_jobs` 状态机在 plan 里只写 4 个值，缺迁移规则

**位置**：Task 5 GREEN L423-467 用 `IngestJobStatus.PENDING/INDEXED/FAILED`；L514-520 加 `SKIPPED`

**问题**：
- 状态机缺**显式转移规则**——PENDING → INDEXED OK、PENDING → FAILED OK、INDEXED → ?（重跑？）、FAILED → PENDING（重试）？
- spec §3.1 写"UPDATE ingest_jobs (status=indexed|failed, chunks_count, error?)"——只有 indexed/failed 两态
- M1 review P2-5 加 `retry_count` / `next_retry_at` 字段——M4 写 FAILED 时**没写 retry_count++ 和 next_retry_at = now() + backoff**
- M4 plan L577 风险表自警"payload_hash 重复但 user_id 不同被识别为幂等"——解决方法是**已有 job.status=INDEXED 时新请求走 200 返已有 job**，M4 L419-422 实现是"返已有 job 但不区分状态"——失败后重试（FAILED 状态）会被错认幂等

**修改**（Task 5 GREEN 段补状态机注释）：

```python
# 状态机：PENDING → INDEXED/FAILED/SKIPPED
#   INDEXED → 已成功，不允许重跑（payload_hash 幂等）
#   FAILED → 允许重跑（payload_hash 重复时返 old job 标 retried）
#   SKIPPED → 跳过（文件超大 / 不支持格式），不允许重跑
# 转移规则：
#   新文件 → INSERT PENDING
#   已存在 payload_hash 且 status=INDEXED → 返 old（幂等）
#   已存在 payload_hash 且 status=FAILED → UPDATE 为 PENDING 重跑
#   已存在 payload_hash 且 status=SKIPPED → 返 old（不重试）
```

并在 pipeline 头部加：
```python
if existing and existing.status == IngestJobStatus.FAILED:
    # 重试：reset status=PENDING, retry_count += 1
    existing.status = IngestJobStatus.PENDING
    existing.retry_count = (existing.retry_count or 0) + 1
    ...
```

### P1-6 · `OversizedFileError` 放 `app/ingest/exceptions.py`，M5/M6 复用——但 plan 没在 Files 表显式列

**位置**：Task 6 REFACTOR L520 "OversizedFileError 放 `app/ingest/exceptions.py`（M5/M6 共用）"

**问题**：
- Files 表 L168-189 **没列 `app/ingest/exceptions.py`**——M4 计划新增但 plan Files 表漏
- M5/M6 复用这个 exception 时**找不到定义文件**
- REFACTOR 段一句话提但**没在 Files 表正式列**

**修改**：Files 表 L168-189 加：
| `app/ingest/exceptions.py` | M4 新增：`OversizedFileError` / `UnsupportedFormatError` / `IngestPipelineError`，M5/M6 复用 |

### P1-7 · `image_ref` 路径规范 `artifacts/{doc_id}/images/{file_name}` 在 M5/M6 复制时会不一致

**位置**：Task 4 GREEN L368-372 `relative_path = f"{doc_id}/images/{src.name}"`；M4 plan L581 风险表

**问题**：
- M4 用 `{doc_id}/images/{file_name}` 作 relative_path——M5 URL source（trafilatura 抽出来的图）**没有 doc_id 概念**（doc_id 是文件 hash）→ M5 会改 schema 成 `{url_hash}/images/{file_name}` 或类似
- M6 Confluence 的图来自 attachment / page，**doc_id 是 page hash**——同样会改
- M4 没把 image_ref 路径规范**显式定义在 M4 plan 的契约边界表**——M5/M6 写时会**各自一套**

**修改**：契约边界表 L118-124 加：
| M5/M6 image source | 复用 `app/ingest/sources/file.py::extract_images` | image_ref 路径规范：`{doc_id}/images/{file_name}`（`doc_id` 由 source hash 决定） |

### P1-8 · `ImageRef` 移到 `app/ingest/models.py`（M5/M6 复用），但 Files 表没列

**位置**：Task 4 REFACTOR L376

**问题**：
- 与 P1-6 同类——Files 表没列 `app/ingest/models.py`
- M5/M6 引用 `ImageRef` 找不到

**修改**：Files 表加 `app/ingest/models.py` —— `ImageRef` / M5/M6 复用的 dataclass 集合。

### P1-9 · Task 3 GREEN 段 `OpenSearchClient` 默认构造 + 全局 `AsyncOpenSearch` 单例缺生命周期管理

**位置**：Task 3 GREEN L272-279 `OpenSearchClient.__init__` 默认构造 AsyncOpenSearch

**问题**：
- 每次 `OpenSearchClient()` 都新建 `AsyncOpenSearch` —— **没连接池**——M4 测试场景多次 upsert 反复创建连接
- 缺 `aclose()` 析构——M4 集成测试结束**httpx 连接池 / asyncio 资源不释放**，pytest 报"unclosed client session"
- 跨 M 缺 `app.retrieval.client` 全局单例（M3 review X-3 同类问题）——M7 retriever 写时**也新建** AsyncOpenSearch

**修改**（Task 3 GREEN 段 + REFACTOR）：

```python
# app/retrieval/client.py
class OpenSearchClient:
    def __init__(self, client: AsyncOpenSearch | None = None):
        self._client = client or _default_opensearch_client()
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

# app/retrieval/client.py（模块级单例）
_default_client: AsyncOpenSearch | None = None

def _default_opensearch_client() -> AsyncOpenSearch:
    global _default_client
    if _default_client is None:
        _default_client = AsyncOpenSearch(
            hosts=[settings.opensearch.hosts],
            http_auth=(settings.opensearch.user, settings.opensearch.password.get_secret_value()),
            use_ssl=True,
        )
    return _default_client

async def get_opensearch_client() -> OpenSearchClient:
    """M4/M7 共用入口。"""
    return OpenSearchClient(_default_opensearch_client())
```

补单测 `test_default_client_is_singleton` + `test_aclose_closes_only_when_owned`。

### P1-10 · M4 pipeline `try/except` 段重置 `updated_at` 不显式（已有 review P1-4 在 M4 范围）

**位置**：Task 5 GREEN L451-466 "ORM 走 session.add() 触发 updated_at onupdate（P1-4）"

**问题**：
- 已有 review P1-4 已修"M1 TimestampMixin onupdate 走 ORM 触发"——M4 注释里写"走 session.add() + commit" ✓
- 但 L460-466 `except` 段 `_mark_failed` 用 `session.get(IngestJob, job.id)` + `session.add()` + `commit()`——**没显式断言 `updated_at` 被刷新**
- 单元测试 `test_ingest_marks_failed_on_embed_error` 只断言 `status == "failed"` 和 `error` 含 "timeout"——**没断言 `updated_at > created_at`**

**修改**：补单测 `test_updated_at_changes_on_status_update`（mock time.sleep 验证时间差），并在 `_mark_failed` 函数 docstring 写"P1-4 必须走 session.add() 触发 onupdate"。

---

## P2 · 优化

### P2-1 · Task 1 REFACTOR 段 `artifacts_dir.mkdir` 在模块 import 时执行，不优雅

**位置**：Task 1 REFACTOR L219 "抽 artifacts_dir.mkdir(parents=True, exist_ok=True) 到 app/ingest/__init__.py 模块级 import 时执行（启动时确保目录存在）"

**问题**：
- 模块 import 时**偷偷做文件系统操作**——测试 import `app.ingest` 时就触发 mkdir，**污染文件系统**（pytest tmpdir 失效）
- 单测 `test_ingest_file_source.py` 期望在 `tmp_path` 下，但 `settings.ingest.artifacts_dir` 是 `Path("/tmp/rag-artifacts")`——**测试污染本机 /tmp**
- 应该 lazy 初始化（首次 `ingest_file` 调用时建） 或 pytest fixture 里 `monkeypatch.setenv("INGEST_ARTIFACTS_DIR", str(tmp_path))`

**修改**：Task 1 REFACTOR 改写：
```python
# app/ingest/__init__.py
def _ensure_artifacts_dir():
    settings.ingest.artifacts_dir.mkdir(parents=True, exist_ok=True)
    return settings.ingest.artifacts_dir

# 改：暴露 ensure_artifacts_dir() 函数，由 ingest_file 入口调
# 单测 fixture monkeypatch INGEST_ARTIFACTS_DIR 到 tmp_path
```

### P2-2 · `pyproject.toml` 依赖追加段没给完整内容（已有 review X-3 + 缺具体行）

**位置**：M4 plan L191 "pyproject.toml：追加 5 个新直接依赖"

**问题**：
- 5 个依赖：`llama-index-core` / `llama-index-readers-file` / `opensearch-py[async]` / `Pillow` / `pypdf` —— 但**没给完整 toml 段**
- 缺 `pymupdf`（P0-2 修复后必加）
- 缺 `pyyaml`（spec §8.1 LLM 编排栈需要 `PyYAML`，M3 已加但 M4 没确认）
- DoD L553 写"`pyproject.toml` 追加 5 个新直接依赖"——没具体行无法验证

**修改**：M4 Files 表"修改"段 L190-192 补完整 toml：
```toml
[project]
dependencies = [
  # M0-M3 已有省略
  "llama-index-core==0.14.8",
  "llama-index-readers-file==0.4.0",
  "opensearch-py[async]>=2.6,<3",
  "Pillow>=10.0,<12",
  "pypdf>=4.0,<6",
  "pymupdf>=10.0,<11",  # PDFParser 后端
]
```

### P2-3 · `asyncio_mode = auto` 在 `pytest.ini` 是 M0 决定的（M2 review P1-11），M4 没继承确认

**位置**：M4 隐式依赖 M0 pytest.ini 配置

**问题**：
- M4 所有 `async def ingest_file` / `async def upsert_chunks` / `async def _mark_failed` 都需要 `pytest-asyncio` 异步跑
- M0 review P2-1 决定加 `pytest.ini` 含 `asyncio_mode = auto`——M4 plan **没引用也没确认**

**修改**：M4 测试策略段 L531-539 补一行："`pytest.ini` 已含 `asyncio_mode = auto`（M0 P2-1），M4 异步测试无需 `@pytest.mark.asyncio` 装饰。"

### P2-4 · M4 plan 引用的 `pytest-httpx` 在 M3 已用但 M4 不显式需要（mock 走 unittest.mock 而非 pytest-httpx）

**位置**：Tech Stack 表 L144 "测试：`pytest` / `pytest-asyncio` / `pytest-httpx` | M3 已有"

**问题**：
- M4 mock OpenSearch 走 `unittest.mock.AsyncMock`（代码段暗示）——`pytest-httpx` 不必
- Tech Stack 表误导——M4 实际不需要 `pytest-httpx`（M3 测 TEI 必用）
- 混用会让人误以为 M4 测试要装 `pytest-httpx`

**修改**：Tech Stack 段改：
```text
| 测试 | `pytest` / `pytest-asyncio` | spec §8.7 已含 |
```

### P2-5 · M4 没显式声明 `.env.example` 修改内容（与 M3 范本 X-3 不齐）

**位置**：M4 plan L200 "`.env.example`（M4 暂不追加，env 走 `IngestSettings` 默认值；如需覆盖再补）"

**问题**：
- M3 范本 Files 表 L172 显式列 `.env.example` 追加 `ANTHROPIC_API_KEY` / `LANGFUSE_*` / `TEI_URL` ——M4 Files 表 L200 "不修改"反着
- M4 加了 `IngestSettings`（L192）含 `artifacts_dir` / `chunk_size` / `chunk_overlap` / `opensearch_index` / `max_attachment_mb` —— **5 个 env var 没人知道怎么覆盖**
- 默认值硬编码（M4 L215）→ **部署到生产** 50MB 默认不够，需要 env 覆盖

**修改**：M4 plan L200 反过来，加：
```ini
# .env.example（M4 追加）
INGEST_ARTIFACTS_DIR=/var/lib/rag/artifacts
INGEST_CHUNK_SIZE=512
INGEST_CHUNK_OVERLAP=64
INGEST_OPENSEARCH_INDEX=chunks
INGEST_MAX_ATTACHMENT_MB=50
OPENSEARCH_HOSTS=https://opensearch:9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=***  # from secret manager
```

### P2-6 · Task 6 RED 测试 `test_ingest_skips_oversized_attachment` 测 60MB 文件写盘慢，CI 卡 10s+

**位置**：Task 6 RED L513-520

**问题**：
- 60MB 临时文件 `Path("test_60mb.pdf").write_bytes(b"\0" * 60*1024*1024)` ——**单测写 60MB 慢**
- 60MB 测的是 `path.stat().st_size > 50MB` 早返，但**测试本身**要写 60MB
- CI runner IO 慢可能 30s+

**修改**：mock 路径大小（`monkeypatch.setattr("pathlib.Path.stat", lambda self: SimpleNamespace(st_size=60*1024*1024))`），不真写 60MB。

### P2-7 · `_payload_hash` 读全文到内存（path.read_bytes()）大文件 OOM 风险

**位置**：Task 5 GREEN L406-407 `_payload_hash(path) = sha256(path.read_bytes()).hexdigest()`

**问题**：
- 100MB PDF 一次性 `read_bytes()` → Python bytes 100MB + sha256 对象 + 后续 `SimpleDirectoryReader.load_data()` 解析后**Document 列表可能再放大 10x**（PDF 流对象）
- 50MB 限制（spec §5）能挡住，但**接近 50MB 的文件 + PDF 流解析** → 500MB-1GB 内存峰值
- 单测 / 集成测试都是小文件（10-100KB），**生产才爆**

**修改**：分块 hash（10MB chunk）：
```python
def _payload_hash(path: Path, chunk_size: int = 10 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()
```

补单测 `test_payload_hash_handles_large_file_streamed`（构造 100MB mock 验证内存不爆）。

### P2-8 · M4 plan 引用的 `IngestJobStatus` 枚举值在 M1 schema 没列出

**位置**：Task 5 GREEN L398-399 `from app.db.models.ingest_job import IngestJob, IngestJobStatus`

**问题**：
- M1 schema 写 ingest_jobs.status VARCHAR(20) + CHECK constraint（具体值 M1 plan 没在本文列出，依赖 M1 review P1-10 决定）
- M4 plan L398 引用 `IngestJobStatus.PENDING/INDEXED/FAILED` + L514 `SKIPPED` —— **M1 没在 schema 注释中确认这 4 个值都允许**
- M1 review P1-10 写"缺 enum 类型 vs VARCHAR+CHECK 的设计决策"——M4 plan 默认 enum，但 M1 可能选了 VARCHAR+CHECK

**修改**：Task 5 GREEN 段加注释："依赖 M1 schema 落定 `IngestJobStatus` 枚举值含 PENDING/INDEXED/FAILED/SKIPPED 四个；若 M1 选 VARCHAR+CHECK，需在本 plan 同步补 CHECK in 字符串。"

### P2-9 · M4 plan 缺"批次 ingest"接口规格（M6 用，但 M4 应预留）

**位置**：M4 plan Goal L13-22 全是单文件；Architecture L96 `ingest_file(path, user_id)` 单文件

**问题**：
- spec §3.1 写"单文件失败不阻塞批次"——M6 批次场景**用 M4 的 `ingest_file` 单文件入口串行调**
- 但 M4 plan **没在契约边界表说明"批次 ingest 是 M6 串行 N 个 M4 `ingest_file`"**
- M6 plan 写时会问"是串行 M4 入口 还是 M4 暴露 `ingest_files(paths, user_id)` 批量入口"

**修改**：契约边界表 L118-124 加：
| M6 confluence 批次 | M4 单文件入口串行调 | M4 不暴露批量接口，M6 自己写 `for path in paths: ingest_file(path, user_id)`，失败用 try/except 隔离 |

---

## 与已有 review 交叉验证

| 已有 review 问题 | M4 plan 状态 | 备注 |
|---|---|---|
| **总 review P0-1** · TEI 端口 8080 → 18080 | ✅ 已修 | M4 plan L537 显式说"TEI 端口 `18080:80` P0-1 修"；Files 表 L195 标"infra/docker-compose.yml（M0 已建；TEI 端口 `18080:80` P0-1 已修）" |
| **总 review P0-5** · 集成测试必须用真 PG | ✅ 已修 | M4 plan L492-498 显式"真 PG 容器（testcontainers 模式，P0-5 修复口径）"；L536 "PG 真实性（P0-5）"；P1-1 是 M4 反向（OpenSearch 走 mock） |
| **总 review P1-4** · updated_at 走 ORM | ✅ 已修 | M4 plan L451 注释"P1-4"；P1-10 是同源问题（_mark_failed 没显式验证） |
| **总 review P1-5** · payload_hash UNIQUE 约束 | ✅ 已修 | M4 plan L197 注释"含 P1-5 UNIQUE 索引"；L411-422 实现 |
| **总 review P1-16** · store vs retriever 边界 | ✅ 已修 | M4 plan L122 "M7 OpenSearch 检索：AsyncOpenSearch 客户端（M4 占位）"；L56 "M4 新增：AsyncOpenSearch 客户端占位实现（upsert 用）"——边界明确 |
| **总 review P2-7** · async_session | ✅ 已修 | M4 plan L49 注释"M1 P2-7 修复后"；L161 "from app.db.session import async_session, get_session（P2-7 修复后口径）"；L400 同 |
| **总 review X-3** · settings 全局单例 | ✅ 已修 | M4 plan L162 "from app.config import settings（X-3 全局单例口径）"；L217 "Settings 末尾追加 `settings = Settings()`" |
| **总 review X-1** · config 拆分 | ❌ 未修 | M4 plan L192 仍然追加 IngestSettings 到 `app/config.py`，**没拆 `app/configs/ingest.py`**——M1/M2/M3 review 都建议"现在拆"，M4 跳过 |
| **M3 review P0-3** · TEIEmbedder 缺 dim 硬断言 | ❌ 未在 M4 范围 | M3 范围；M4 引用 M3 TEIEmbedder 但**没在 pipeline 加 dim 二次断言**——TEI 服务端偶发 dim 漂移时 M4 端到端应报 `EmbeddingDimMismatch`（pipeline 写入 OpenSearch 前断言 `len(vec) == 1024`）|
| **M3 review P1-4** · LLMSettings.model 冲突 | N/A | M4 不涉及 LLM |
| **M1 review P1-1** · ingest_jobs.payload_hash UNIQUE | ✅ 已修 | 同总 review P1-5 |
| **M1 review P2-5** · ingest_jobs.retry_count / next_retry_at | ❌ 未在 M4 范围用 | M1 加了字段（M1 review P2-5）但 M4 plan **没用**——Task 5 GREEN 段没写 `retry_count += 1` 或 `next_retry_at = now() + backoff`（P1-5 同源）|
| **M1 review P2-7** · chat_sessions.metadata JSONB | N/A | M4 不涉及 |
| **M1 review P1-17** · app/config.py 全局单例 | ✅ 已修 | 同 X-3 |
| **M1 review P2-1** · app/configs/ 拆分 | ❌ 未修 | 同 X-1 |

**M4 主动吸收率 7/8 = 87.5%**（X-1 config 拆分没改），是 M0/M1/M2/M3/M4 五份 plan 中**吸收率第二高**（M3 也是 87.5%）。

---

## 你发现的新问题（已有 review 未列）

合计 **22 个新问题**（P0 5 项 + P1 10 项 + P2 9 项，已在上面详细列出；下表为摘要索引）：

| # | 等级 | 主题 | 一句话 |
|---|---|---|---|
| 1 | **P0-1** | 元素分类完全缺 | `BaseElementNodeParser` / `ImageDocument` / Table 整表 1 chunk 都没实现 |
| 2 | **P0-2** | `file_extractor` 显式配置缺 | `SimpleDirectoryReader` 默认不抽图；4 格式 metadata schema 不一 |
| 3 | **P0-3** | OpenSearch 写入层三件缺 | mapping / refresh interval / bulk 阈值全没；M4 mock 推迟爆雷 |
| 4 | **P0-4** | chunk ID / doc_id / payload_hash 关系 | doc_id 用路径（重命名爆雷）、chunk_id 不稳定、payload_hash 跨用户幂等错 |
| 5 | **P0-5** | `GET /api/ingest/{job_id}` 契约缺 | M8 路由不知道 M4 暴露哪些字段 |
| 6 | **P1-1** | 集成测试 OpenSearch 走 mock | 与 spec §6 冲突，延迟爆雷到 M7 |
| 7 | **P1-2** | 7 个 Task 估时 2-5 分钟实际超 | Task 5 实测 30-40 分钟；3d → 5d 估时修正 |
| 8 | **P1-3** | `extract_images` 依赖非标准 metadata | 同 P0-1 修复一并实现 |
| 9 | **P1-4** | 错误矩阵 spec §5 11 条仅覆盖 4 条 | 缺 Postgres 不可达 / 解析失败 / OpenSearch 最终失败 |
| 10 | **P1-5** | 状态机缺显式转移规则 | INDEXED 不允许重跑、FAILED → PENDING 重跑、SKIPPED 不重试 |
| 11 | **P1-6** | `app/ingest/exceptions.py` Files 表漏列 | M5/M6 复用找不到 |
| 12 | **P1-7** | `image_ref` 路径规范没在契约边界表 | M5/M6 会各自一套 |
| 13 | **P1-8** | `app/ingest/models.py` Files 表漏列 | 同 P1-6 |
| 14 | **P1-9** | `OpenSearchClient` 缺连接池 + aclose | httpx 连接不释放；缺单例 |
| 15 | **P1-10** | `_mark_failed` 没显式验证 `updated_at` 刷新 | P1-4 在 M4 范围落地测试 |
| 16 | **P2-1** | 模块 import 时 `artifacts_dir.mkdir` 污染 FS | 单测 tmpdir 失效 |
| 17 | **P2-2** | `pyproject.toml` 缺 `pymupdf` / `pyyaml` | P0-2 修复后必加 |
| 18 | **P2-3** | `asyncio_mode = auto` 没确认 | M0 决定的 M4 隐式依赖 |
| 19 | **P2-4** | `pytest-httpx` Tech Stack 误列 | M4 实际不需 |
| 20 | **P2-5** | `.env.example` 标"不修改"反着 | IngestSettings 5 个 env 没人知道怎么覆盖 |
| 21 | **P2-6** | `test_ingest_skips_oversized_attachment` 写 60MB | 测 IO 慢 |
| 22 | **P2-7** | `_payload_hash` 全文 read_bytes() OOM | 50MB 接近 + PDF 解析可能 1GB 内存 |
| 23 | **P2-8** | `IngestJobStatus` 枚举值依赖 M1 | M1 VARCHAR+CHECK vs enum 不定 |
| 24 | **P2-9** | 批次 ingest 接口规格缺 | M6 串行 M4 单文件入口，但契约边界表没说 |

**对照 4 份已有 review**（总 review + M0 + M1 + M2 + M3 review 列出过的"新问题"）：
- 与 M0 新问题**不重复**（M0 关注 infra / docker / env / gitignore）
- 与 M1 新问题**不重复**（M1 关注 schema / FK / 索引 / 审计字段）
- 与 M2 新问题**不重复**（M2 关注鉴权 / token / session）
- 与 M3 新问题**不重复**（M3 关注 LLM 工厂 / TEI 客户端 / prompt yaml）
- 与总 review 新问题**不重复**（总 review 关注跨 M 一致性）

**M4 plan 22 个新问题 100% 是 M4 范围内的"source 适配器样板"细节**——元素分类 / 图片抽取 / OpenSearch 写入层 / chunk ID / 状态机 / 错误处理 / 测试策略（OpenSearch 真假）/ 范本传染面（image_ref 路径、exceptions、models）——都是 M5/M6 复制 M4 时会**复制的缺陷**。

---

## 落地建议

按 P0 → P1 → P2 优先级：

### 第一波（本轮必改，5 项 P0）

1. **P0-1** Task 4 加 `app/ingest/elements.py` `classify_elements` 实现 + `tests/unit/test_ingest_elements.py` 覆盖 ImageDocument / TextNode / Table 三类；Tables 整表 1 chunk 不切碎
2. **P0-2** Task 4 GREEN 段重写 `read_file` 显式配 `FILE_EXTRACTORS`（PDFParser/DocxParser/PptxParser/MarkdownParser），pyproject 加 `pymupdf>=10.0`，补 `UnsupportedFormatError`
3. **P0-3** Task 3 GREEN 段加 `INDEX_MAPPING` 显式声明（knn_vector dim=1024 cosine + metadata 字段类型）+ `ensure_index` 方法 + `BULK_THRESHOLD=100` 阈值；Task 6 集成测试**改跑真 OpenSearch**（testcontainers[opensearch]）
4. **P0-4** Task 4 `doc_id` 改用 `sha256(content)[:32]` 而非路径；Task 5 chunk `id_` 显式构造 `f"{doc_id}:{idx:04d}"` + 写 `chunk_id` / `user_id` metadata
5. **P0-5** Files 表加 `app/ingest/schemas.py` 定义 `IngestJobProgress`（前端进度页契约），契约边界表加 M8 GET 路由依赖

### 第二波（重要，10 项 P1）

6. **P1-1** Task 6 fixture 改 testcontainers[opensearch]，预建 `chunks` 索引（用 P0-3 mapping）
7. **P1-2** Tasks 段标题"（2-5 分钟/step 粒度）"删掉；估时 3d → 5d
8. **P1-3** 与 P0-1 合并实现
9. **P1-4** 错误矩阵覆盖 5 条（OpenSearch 不可达最终失败 / TEI 超时 / Postgres 不可达 fallback / PDF 损坏单文件隔离 / 附件超大），Task 5 GREEN 补 `_mark_failed` PG fallback
10. **P1-5** Task 5 GREEN 段加状态机注释：INDEXED 不重跑 / FAILED → PENDING 重跑 / SKIPPED 不重试
11. **P1-6** Files 表加 `app/ingest/exceptions.py`（M5/M6 复用）
12. **P1-7** 契约边界表加 image_ref 路径规范 `{doc_id}/images/{file_name}`（`doc_id` 由 source hash 决定）
13. **P1-8** Files 表加 `app/ingest/models.py`（M5/M6 复用）
14. **P1-9** `OpenSearchClient` 加 `aclose` + `__aenter__/__aexit__` + 模块级 `_default_client` 单例
15. **P1-10** 单测补 `test_updated_at_changes_on_status_update` 显式断言

### 第三波（优化，9 项 P2）

16-24. **P2-1 ~ P2-9** 全部优化

### 跨 M 协调（M4 改完后通知）

- **推 M1 schema**：`IngestJobStatus` 枚举值确认含 PENDING/INDEXED/FAILED/SKIPPED（P2-8 推动 M1 schema 注释补完整）
- **推 M5 url source**：复用 `app/ingest/elements.py::classify_elements`（HTML 元素分类）+ `app/ingest/exceptions.py` + `app/ingest/models.py::ImageRef`（image_ref 路径规范 `{doc_id}/images/{file_name}`）
- **推 M6 confluence source**：与 M5 同 + 批次 ingest 用 M4 `ingest_file` 串行 + try/except 隔离（spec §5 错误矩阵）
- **推 M7 graph/retrieval**：M4 已建 `chunks` 索引 mapping（M4 P0-3），M7 retriever 复用 `INDEX_MAPPING` + 模块级单例 `get_opensearch_client()`
- **推 M8 API**：用 `app/ingest/schemas.py::IngestJobProgress` 响应 `GET /api/ingest/{job_id}`（P0-5 契约）
- **推 M10 obs-langfuse**：M4 pipeline 4 步埋点用 `@trace` 装饰器（M10 范围）——M4 plan 不实现
- **推 M12 hardening**：`artifacts/` 目录 30 天清理 cron（M4 风险表 L582 已留 M12）；`ingest_jobs.retry_count` 字段启用（P1-5 重跑逻辑）

### 估时修正

- M4 整体估时从 **3d → 5d**（P0 修补 1d + P1 实施 1d + 集成测试 1d + 跨 M 协调 0.5d + buffer 1.5d）
- Tasks 标"2-5 分钟/step"实际多数 10-30 分钟，**M4 估时反模式与 M0 review P2-6 / M3 review P1-6 同源**

### 等待决策

- X-1 `app/config.py` 拆分 `configs/` 子目录是否在 M4 阶段就动手（推荐是，避免 M5/M6/M7 改 6+ import 路径）
- P0-3 OpenSearch 集成测试**集成 vs mock**——集成（testcontainers）延迟高但符合 spec §6；mock 快但延迟爆雷
- P0-4 `chunk_id` 稳定化策略选 A（`f"{doc_id}:{idx:04d}"`）还是 B（`sha256(doc_id + chunk_text)[:16]`）——A 简单但需保证 split 顺序；B 抗重排但 OpenSearch upsert 用作 _id 时可能改

---

## 状态

- **不可动手**：P0-1 ~ P0-5 共 5 项必改
- **建议本轮改**：P1-1 ~ P1-10 共 10 项
- **可下轮改**：P2-1 ~ P2-9 共 9 项
- **新问题合计**：24 个（已有 review 未列），其中 5 个 P0
- **已有 review 验证**：M4 范围 8 项（总 review P0-1/P0-5/P1-4/P1-5/P1-16/P2-7/X-1/X-3 + M3 P0-3 + M1 P1-1/P1-17/P2-1/P2-5），**已修 7 项 / 未修 5 项**（X-1 / M3 P0-3 / M1 P2-5 retry 字段 / M1 P2-1 拆分）
- **范本定位**：M4 plan 自警 L7"给 M5/M6 提供 source 适配器样板"——**结构对、版本对、主动修 7 项已有 P0/P1**；**作为范本的内容示范严重不足**（元素分类 / 图片抽取配置 / OpenSearch 写入层 / chunk ID / 状态机 / 错误矩阵 / 进度接口契约——7 大块缺）。**修完 5 个 P0 + 10 个 P1 后是合格 source 实现；P0+P1+P2 修完后才能作为 M5/M6 范本**。

M4 plan **结构对、版本对、契约表清**；**作为 source 样板的内容缺 7 大块**——元素分类、图片抽取配置、OpenSearch 写入层、chunk ID/状态机、错误处理、进度接口契约、批次接口规格。**M5/M6 复制前必须修完 P0+P1**。
