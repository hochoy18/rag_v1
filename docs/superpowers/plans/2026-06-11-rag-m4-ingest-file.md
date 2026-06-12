# M4 Plan · Ingest · File source（LlamaIndex 解析 + 元素分类 + 图片抽取 + 嵌入入库）

> 所属：RAG V1 M0–M12 实施路线 · 第 4 步
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §3.1 ingest 数据流](../specs/2026-06-10-rag-v1-scope.md#3-1-ingest-数据流) · [决策总表 #5 数据源](../specs/2026-06-10-rag-v1-scope.md#0-决策总表) · [V1 Scope §8 依赖版本](../specs/2026-06-10-rag-v1-scope.md#8-依赖版本清单)
>估时：5 个工作日（原3d估时严重低估，按 P1-2修正为5d）
> 范本目的：给 M5（url）/ M6（confluence）提供"source 适配器"样板（统一 `parse → split → embed → upsert` pipeline）

---

## Goal

把 v0.4 spec §3.1 的 ingest 数据流在"file 源"上落成可执行代码契约：

1. `app/ingest/sources/file.py` —— LlamaIndex `SimpleDirectoryReader` 读 PDF / Word / PPT / MD 4 种格式，输出统一 `Document` 列表
2. `app/ingest/splitter.py` —— `SentenceSplitter(chunk=512, overlap=64)`，长文档切块、短文档保形
3. `app/ingest/pipeline.py` —— 编排 `parse → split → embed (TEIEmbedder from M3) → upsert (OpenSearch from M7 接口)` 4 步，端到端函数 `ingest_file(path, user_id) -> IngestJob`
4. `app/ingest/sources/file.py` 处理图片元素：抽到 `artifacts/{doc_id}/images/`，元数据 `image_ref`（V1 边界：只元数据 + UI 缩略图，不做内容问答）
5. `ingest_jobs` 表 INSERT/UPDATE（M1 已建，`user_id` 关联 `current_user`）
6. `/api/ingest` 端点集成（M8 写；M4 阶段为路由写一个**测试桩** `tests/integration/conftest.py::mock_ingest_route`，不真起 FastAPI）
7. 幂等：`payload_hash` UNIQUE 约束 + `ON CONFLICT (payload_hash) DO NOTHING` 语义

**不包含**（其他 M 负责）：
- url 4 种 auth 适配 → M5
- confluence v2 REST + 子页 BFS + attachments → M6
- `/api/ingest` 真实路由 + Pydantic schema + 鉴权依赖注入 → M8
- OpenSearch 真实 `retriever` 业务逻辑（ann k-NN + filter）→ M7
- Langfuse 业务级 trace（@trace 装饰器接入 ingest）→ M10
- RAGAS eval golden set 生成（用 query 路径，不直接调 M4）→ M11

---

## Architecture

### 仓库布局（apps/rag_v1/）—— M4 新增/修改子集

```
apps/rag_v1/
├── infra/                                  # M0 已建：docker-compose + init.sql
│
├── app/
│   ├── __init__.py                         # M3 已建
│   ├── config.py                           # M0–M3 累积（不修改）
│   │
│   ├── embedding/                          # M3 已建
│   │   └── client.py                       # TEIEmbedder（M3 产出，M4 直接 import）
│   │
│   ├── db/                                 # M1 已建
│   │   ├── session.py                      # async_session / get_session（P2-7 修复后）
│   │   ├── base.py
│   │   └── models/ingest_job.py            # IngestJob ORM（m1 已建，M4 仅引用）
│   │
│   ├── retrieval/                          # M7 占位（M4 只 import 接口，不实现）
│   │   ├── __init__.py                     # M4 新增：暴露 AsyncOpenSearch 类型
│   │   └── client.py                       # M4 新增：AsyncOpenSearch 客户端占位实现（upsert 用）
│   │                                       # M7 会扩展为 retriever.py / store.py
│   │
│   └── ingest/                             # M4 新增（核心）
│       ├── __init__.py                     # 暴露 ingest_file
│       ├── auth.py                         # auth 配置加载（M5/M6 共享，M4 仅占位）
│       ├── pipeline.py                     # parse → split → embed → upsert 编排
│       ├── splitter.py                     # SentenceSplitter 包装
│       └── sources/
│           ├── __init__.py                 # 暴露 file 适配器
│           └── file.py                     # LlamaIndex SimpleDirectoryReader + 图片抽取
│
├── tests/
│   ├── unit/
│   │   ├── test_splitter.py                # M4 新增
│   │   ├── test_ingest_file_source.py      # M4 新增
│   │   ├── test_ingest_pipeline.py         # M4 新增
│   │   └── test_opensearch_client.py       # M4 新增（占位客户端 mock）
│   │
│   └── integration/
│       ├── conftest.py                     # M4 新增：mock_ingest_route 桩
│       ├── test_m4_ingest_e2e.py           # M4 新增：真 PG + 真 TEI + mock OpenSearch
│       └── artifacts/                      # .gitignore 已含（M0 P0-9）
│
├── alembic/                                # M1 已建（不修改）
├── pyproject.toml                          # M3 已建（追加 M4 依赖）
├── .env.example                            # M3 已建（追加 INGEST_ARTIFACTS_DIR）
├── .gitignore                              # M0 P0-9 已建（含 artifacts/）
├── pytest.ini                              # M0 P2-1 已建
└── README.md                               # M0 已建（不修改）
```

### M4 模块树

```
apps/rag_v1/
├── app/
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── auth.py              # auth 配置加载（占位接口，M5/M6 完善）
│   │   ├── pipeline.py          # ingest_file(path, user_id) → IngestJob；编排 4 步
│   │   ├── splitter.py          # SentenceSplitterWrapper（512/64）
│   │   └── sources/
│   │       ├── __init__.py
│   │       └── file.py          # read_file(path) → list[Document] + extract_images(doc, doc_id)
│   │
│   └── retrieval/
│       ├── __init__.py          # 暴露 AsyncOpenSearch
│       └── client.py            # AsyncOpenSearch（M4 占位：仅 upsert_chunks；M7 扩展）
│
└── tests/
    ├── unit/
    │   ├── test_splitter.py
    │   ├── test_ingest_file_source.py
    │   ├── test_ingest_pipeline.py
    │   └── test_opensearch_client.py
    └── integration/
        ├── conftest.py          # mock_ingest_route + 真 TEI/PG fixture
        └── test_m4_ingest_e2e.py
```

### M4 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M8 `/api/ingest` 路由 | `ingest_file(path, current_user) -> IngestJob` | M8 加 Pydantic schema + auth dependency |
| M5 url source | `SentenceSplitterWrapper.split(docs)` + `pipeline._upsert(chunks, doc_id)` | 复用 M4 splitter + pipeline upsert 段 |
| M6 confluence source | 同 M5 | 复用 |
| M7 OpenSearch 检索 | `AsyncOpenSearch` 客户端（M4 占位） | M7 扩展为 `OpenSearchVectorStore` + `retriever.py` |
| M11 RAGAS | 不直接调 M4（走 query 路径） | — |

---

## Tech Stack

| 层 | 选型 | 版本（精确） |
|----|------|------------|
| LlamaIndex 核心 | `llama-index-core` | `==0.14.8` |
| LlamaIndex 文件读取 | `llama-index-readers-file` | `==0.4.0` |
| LlamaIndex 节点解析 | `llama-index-core.node_parser` | 内置（SentenceSplitter） |
| PDF 解析 | `pypdf` | `>=4.0,<6`（LlamaIndex SimpleDirectoryReader 默认） |
| Word 解析 | `docx2txt` | `>=0.8`（LlamaIndex SimpleDirectoryReader 默认） |
| PPT 解析 | `python-pptx` | `>=1.0`（LlamaIndex SimpleDirectoryReader 默认） |
| MD 解析 | 内置 | `markdown>=3.6` |
| HTTP 客户端 | `httpx` | `>=0.27,<1`（M3 已有） |
| 重试 | `tenacity` | `>=8.3,<10`（M3 已有） |
| OpenSearch 异步 | `opensearch-py[async]` | `>=2.6,<3` |
| 图片 I/O | `Pillow` | `>=10.0,<12` |
| ORM | SQLAlchemy async | M1 已有 |
| 测试 | `pytest` / `pytest-asyncio` / `pytest-httpx` | M3 已有 |

**关键导入路径**（llama-index 0.14.8 / opensearch-py 2.6+）：

```python
# LlamaIndex 文件读取
from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import Document, ImageDocument
from llama_index.core.node_parser import SentenceSplitter

# OpenSearch 异步
from opensearchpy import AsyncOpenSearch
```

**Python 导入规则**：
- `app.ingest.pipeline` —— `app` 是 `apps/rag_v1/app/`
- `app.ingest.sources.file` —— 同包不同子包，绝对导入
- `from app.db.session import async_session, get_session`（P2-7 修复后口径）
- `from app.config import settings`（X-3 全局单例口径）

---

## Files

**新增**（11 个源文件 + 5 个测试文件 + 1 个 fixture）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
| `app/ingest/__init__.py` | 暴露 `ingest_file` |
| `app/ingest/auth.py` | auth 配置加载接口（占位函数，抛 NotImplementedError 标注"待 M5 完善"） |
| `app/ingest/pipeline.py` | `ingest_file(path, user_id) -> IngestJob`；编排 parse → split → embed → upsert |
| `app/ingest/splitter.py` | `SentenceSplitterWrapper`（chunk=512, overlap=64，硬编码 + 常量提取） |
| `app/ingest/sources/__init__.py` | 暴露 `read_file` |
| `app/ingest/sources/file.py` | `read_file(path) -> list[Document]` + `extract_images(docs, doc_id) -> list[ImageRef]` |
| `app/retrieval/__init__.py` | 暴露 `AsyncOpenSearch`（M4 仅 import 路径占位，**不实现 retriever**） |
| `app/retrieval/client.py` | `AsyncOpenSearch` 包装（M4 只含 `upsert_chunks(chunks, index_name)`；M7 扩展） |
| `tests/__init__.py` | M0–M3 已建（不修改） |
| `tests/unit/__init__.py` | M0–M3 已建（不修改） |
| `tests/unit/test_splitter.py` | splitter 单测（短文档 / 长文档 / 边界 512 token / overlap 64） |
| `tests/unit/test_ingest_file_source.py` | file source 单测（4 种格式 mock + 图片元素分类） |
| `tests/unit/test_ingest_pipeline.py` | pipeline 单测（mock 4 步；幂等 `ON CONFLICT` 行为） |
| `tests/unit/test_opensearch_client.py` | AsyncOpenSearch 占位单测（mock opensearch-py，验 upsert_chunks 调用形态） |
| `tests/integration/__init__.py` | M0–M3 已建（不修改） |
| `tests/integration/conftest.py` | M4 新增：`mock_ingest_route` 桩（不真起 FastAPI；M8 替换） + 真 PG/TEI fixture |
| `tests/integration/test_m4_ingest_e2e.py` | M4 新增：真 PG（含 ingest_jobs UNIQUE 约束 P1-5）+ 真 TEI + mock OpenSearch |

**修改**：
- `pyproject.toml`：追加 5 个新直接依赖（`llama-index-core` / `llama-index-readers-file` / `opensearch-py[async]` / `Pillow` / `pypdf`）
- `app/config.py`（M0–M3 累积）：追加 `IngestSettings`（`artifacts_dir: Path` / `chunk_size: int = 512` / `chunk_overlap: int = 64` / `opensearch_index: str = "chunks"` / `max_attachment_mb: int = 50` —— M6 用，M4 占位）

**不修改**：
- `infra/docker-compose.yml`（M0 已建；TEI 端口 `18080:80` P0-1 已修）
- `app/db/models/ingest_job.py`（M1 已建，含 P1-5 UNIQUE 约束）
- `app/embedding/client.py`（M3 已建，M4 直接 import）
- `app/api/`（M8 写；M4 阶段路由由 `conftest.py::mock_ingest_route` 桩代替）
- `alembic/`（M1 已建；M4 不改 schema）
- `.env.example`（M4 暂不追加，env 走 `IngestSettings` 默认值；如需覆盖再补）
- `README.md`（M0 已建）

---

## Tasks（2-5 分钟/step 粒度）

### Task 1：IngestSettings 配置块（M0 配置层追加）

**RED** · `tests/unit/test_config.py::test_ingest_config_loads`（M3 已有文件，追加测试）
- 写测试：mock `INGEST_ARTIFACTS_DIR=/tmp/rag-artifacts` → 加载 `Settings().ingest` → 断言 `chunk_size == 512` / `chunk_overlap == 64` / `artifacts_dir == Path("/tmp/rag-artifacts")`
- 跑法：`cd apps/rag_v1 && pytest tests/unit/test_config.py::test_ingest_config_loads`
- 跑测试 → 失败（`IngestSettings` 不存在）

**GREEN** · 改 `app/config.py`：
- 新增 `IngestSettings`：`artifacts_dir: Path` / `chunk_size: int = 512` / `chunk_overlap: int = 64` / `opensearch_index: str = "chunks"` / `max_attachment_mb: int = 50`（M6 预留）
- 顶层 `Settings.ingest: IngestSettings` 聚合
- `Settings` 末尾追加 `settings = Settings()`（X-3 全局单例口径）

**REFACTOR** · 抽 `artifacts_dir.mkdir(parents=True, exist_ok=True)` 到 `app/ingest/__init__.py` 模块级 import 时执行（启动时确保目录存在）

### Task 2：SentenceSplitter 包装

**RED** · `tests/unit/test_splitter.py::test_short_document_unchanged`
- 构造 `Document(text="短文本 "<50 字>)` → 调 `SentenceSplitterWrapper().split([doc])` → 断言返回 1 个 chunk 且 `text == 原文本`
- 跑测试 → 失败

**GREEN** · 实现 `app/ingest/splitter.py`：
```python
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document, TextNode
from app.config import settings

class SentenceSplitterWrapper:
    """V1 硬编码 chunk=512, overlap=64。Why：spec §3.1 固定，env 仅做 override 入口。"""
    def __init__(self, chunk_size: int | None = None, chunk_overlap: int | None = None):
        self._splitter = SentenceSplitter(
            chunk_size=chunk_size or settings.ingest.chunk_size,
            chunk_overlap=chunk_overlap or settings.ingest.chunk_overlap,
        )

    def split(self, docs: list[Document]) -> list[TextNode]:
        return self._splitter.get_nodes_from_documents(docs)
```

**RED** · `test_long_document_splits_at_boundary`
- 构造 2000 字单文档 → 断言切出 ≥ 4 个 chunk、每个 chunk `len <= 512`、相邻 chunk overlap 64 字
- 跑法：`pytest tests/unit/test_splitter.py::test_long_document_splits_at_boundary`

**GREEN** · 已在 Task 2 GREEN 实现覆盖

**RED** · `test_metadata_preserved`
- 构造 `Document(text="...", metadata={"source": "file", "page_id": 7})` → 切块后断言每个 chunk `node.metadata["source"] == "file"` 且 `page_id == 7`
- 跑测试 → 失败（默认 metadata 可能丢失页号）

**GREEN** · LlamaIndex SentenceSplitter 默认保留 `metadata`，验证无需改代码

**REFACTOR** · 抽常量 `DEFAULT_CHUNK_SIZE = 512` / `DEFAULT_CHUNK_OVERLAP = 64` 到模块顶部（spec 硬编码参考）

### Task 3：AsyncOpenSearch 占位客户端（M4 仅 upsert_chunks）

**RED** · `tests/unit/test_opensearch_client.py::test_upsert_chunks_calls_bulk`
- 构造 3 个 `TextNode(text="t1/t2/t3", metadata={...}, embedding=[[0.1]*1024, [0.2]*1024, [0.3]*1024])`
- mock `AsyncOpenSearch.bulk` → 调 `OpenSearchClient(settings).upsert_chunks(chunks, index_name="chunks")` → 断言 bulk 收到 1 次调用、body 含 3 个 index action
- 跑测试 → 失败（client 不存在）

**GREEN** · 实现 `app/retrieval/client.py`：
```python
from opensearchpy import AsyncOpenSearch
from llama_index.core.schema import TextNode
from app.config import settings

class OpenSearchClient:
    """M4 占位：仅 upsert_chunks；M7 扩展为 OpenSearchVectorStore + retriever"""
    def __init__(self, client: AsyncOpenSearch | None = None):
        self._client = client or AsyncOpenSearch(
            hosts=[settings.opensearch.hosts],
            http_auth=(settings.opensearch.user, settings.opensearch.password.get_secret_value()),
            use_ssl=True,
        )

    async def upsert_chunks(self, chunks: list[TextNode], index_name: str) -> int:
        """返回成功索引的 chunk 数。Why 走 bulk：1000 chunk 一次请求比 1000 次 PUT 快 50x。

        P0-3 r2 已修：
        - INDEX_MAPPING 显式声明（dim=1024 / hnsw / cosine）
        - bulk 阈值 500（达 500 自动 flush）
        - refresh_interval=30s（避免每写一次都 refresh 拖慢 50x）
        """
        # P0-3 r2 已修：INDEX_MAPPING 显式声明（不在 upsert_chunks 内重复，靠 ensure_index 调用）
        body: list[dict] = []
        chunk_buffer: list[dict] = []  # P0-3 r2 已修：bulk 阈值 500 触发 flush

        async def _flush_buffer(buf: list[dict]) -> int:
            if not buf:
                return 0
            success, errors = await self._client.bulk(body=buf, refresh=False)
            return success

        for chunk in chunks:
            chunk_buffer.append({"index": {"_index": index_name, "_id": chunk.id_}})
            chunk_buffer.append({
                "text": chunk.text,
                "vector": chunk.embedding,  # M4 假定 pipeline 已 embed
                "metadata": chunk.metadata,
            })
            if len(chunk_buffer) >= 500:  # P0-3 r2 已修：bulk 阈值 500
                success = await _flush_buffer(chunk_buffer)
                chunk_buffer = []
        success = await _flush_buffer(chunk_buffer)  # flush 剩余
        return success

    async def ensure_index(self, index_name: str) -> None:
        """P0-3 r2 已修：显式 INDEX_MAPPING 声明（dim=1024 / hnsw / cosine）+ refresh_interval=30s。

        Why 显式：M7 graph 跑 RAGAS 评测时需确保 index 存在；不显式 OpenSearch 默认 mapping 会让 vector field 识别错。
        """
        INDEX_MAPPING = {
            "settings": {
                "index": {
                    "refresh_interval": "30s",  # P0-3 r2 已修：避免每写一次都 refresh
                    "knn": True,  # OpenSearch 2.x k-NN 必开
                }
            },
            "mappings": {
                "properties": {
                    "text": {"type": "text"},
                    "vector": {
                        "type": "knn_vector",
                        "dimension": 1024,  # bge-m3 dim
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "faiss",
                        },
                    },
                    "metadata": {"type": "object", "enabled": True},
                }
            },
        }
        exists = await self._client.indices.exists(index=index_name)
        if not exists:
            await self._client.indices.create(index=index_name, body=INDEX_MAPPING)
```
- `app/retrieval/__init__.py` 暴露 `OpenSearchClient`（**不暴露** `AsyncOpenSearch` 裸类，避免后续 M 跳过封装）

**RED** · `test_upsert_retries_on_connection_error`
- mock 第 1 次 bulk 抛 `ConnectionError`、第 2 次成功 → 断言最终返回 success 数 + 调用 2 次
- 跑测试 → 失败

**GREEN** · 加 `@tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4), retry=retry_if_exception_type(ConnectionError))`

**REFACTOR** · 把 retry 抽 `_bulk_with_retry(body)` 私有方法（避免装饰器与 mock 冲突，spec §5 错误矩阵对齐）

### Task 4：File source · SimpleDirectoryReader 适配

**RED** · `tests/unit/test_ingest_file_source.py::test_read_pdf_returns_documents`
- mock `SimpleDirectoryReader.load_data()` 返回 2 个 `Document(text="page1", metadata={"page_label": "1", "file_path": "test.pdf"})`
- 调 `read_file(Path("test.pdf"))` → 断言 2 个 doc、`metadata["source"] == "file"`、`doc_id` 用 SHA256(path) 前 16 字符
- 跑测试 → 失败

**GREEN** · 实现 `app/ingest/sources/file.py`：
```python
import hashlib
from pathlib import Path
from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import Document
from app.config import settings

def _doc_id_from_path(path: Path) -> str:
    """Why SHA256 前 16：稳定 + 短 + 够唯一（M1 ingest_jobs.doc_id 也是这长度）。"""
    return hashlib.sha256(str(path.absolute()).encode()).hexdigest()[:16]

def read_file(path: Path) -> tuple[list[Document], str]:
    """返回 (documents, doc_id)。Why 元组：doc_id 由路径推导，调用方建 ingest_jobs 行需用。"""
    doc_id = _doc_id_from_path(path)
    reader = SimpleDirectoryReader(
        input_files=[str(path)],
        file_metadata=lambda fp: {"source": "file", "doc_id": doc_id, "file_name": Path(fp).name},
    )
    docs = reader.load_data()
    return docs, doc_id
```

**RED** · `test_read_supports_4_formats`
- parametrize：`path in [".pdf", ".docx", ".pptx", ".md"]` → 各自 mock 解析器返回 1 doc → 断言 `len(read_file(path)[0]) == 1`
- 跑测试 → 失败

**GREEN** · LlamaIndex `SimpleDirectoryReader` 默认支持 4 格式，无需改代码；测试用 mock 验证调用形态

**RED** · `test_extract_images_writes_to_artifacts_dir`
- 构造 1 个含 `ImageDocument` 的 `Document` 列表（mock image bytes + metadata `{"image_path": "page1_img1.png"}`）
- 调 `extract_images(docs, doc_id="abc123")` → 断言：
  - 写出文件到 `settings.ingest.artifacts_dir / doc_id / "images" / "page1_img1.png"`
  - 返回 `list[ImageRef]` 含 1 项，`ref.relative_path == "abc123/images/page1_img1.png"`
- 跑测试 → 失败

**GREEN** · 实现 `extract_images`：
```python
from dataclasses import dataclass
from app.config import settings

@dataclass
class ImageRef:
    """V1 边界：仅元数据 + UI 缩略图，不做图片内容问答（spec §3.1 决策）。"""
    relative_path: str  # 相对 artifacts_dir，用于 OpenSearch metadata
    absolute_path: Path
    doc_id: str

def extract_images(docs: list[Document], doc_id: str) -> list[ImageRef]:
    images_dir = settings.ingest.artifacts_dir / doc_id / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    refs: list[ImageRef] = []
    for doc in docs:
        for img in doc.metadata.get("images", []):  # LlamaIndex ImageDocument 元素
            src = Path(img["image_path"])
            dst = images_dir / src.name
            dst.write_bytes(img["image_bytes"])
            refs.append(ImageRef(
                relative_path=f"{doc_id}/images/{src.name}",
                absolute_path=dst,
                doc_id=doc_id,
            ))
    return refs
```

**REFACTOR** · 把 `ImageRef` 移到 `app/ingest/models.py`（M5/M6 也会用到 image_ref）

### Task 5：Pipeline 编排

**RED** · `tests/unit/test_ingest_pipeline.py::test_ingest_file_end_to_end_mock`
- mock 4 步：
  - `read_file` → 返回 1 doc
  - `SentenceSplitterWrapper.split` → 返回 1 TextNode
  - `TEIEmbedder.embed` → 返回 `[[0.1]*1024]`
  - `OpenSearchClient.upsert_chunks` → 返回 1
- 调 `pipeline.ingest_file(Path("test.pdf"), user_id="u123")` → 断言返回 `IngestJob` 实体：
  - `status == "indexed"`
  - `chunks_count == 1`
  - `user_id == "u123"`
  - `payload_hash == sha256(file_content)`
- 跑测试 → 失败

**GREEN** · 实现 `app/ingest/pipeline.py`：
```python
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from app.config import settings
from app.db.models.ingest_job import IngestJob, IngestJobStatus
from app.db.session import async_session  # P2-7 修复后口径
from app.embedding.client import TEIEmbedder
from app.ingest.sources.file import read_file, extract_images
from app.ingest.splitter import SentenceSplitterWrapper
from app.retrieval.client import OpenSearchClient

def _payload_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

async def ingest_file(path: Path, user_id: str) -> IngestJob:
    """单文件 ingest 入口。Why 同步函数转 async：4 步全异步 IO（embed / bulk / DB）。"""
    payload_hash = _payload_hash(path)
    docs, doc_id = read_file(path)
    images = extract_images(docs, doc_id)

    # 幂等：先查 existing（P1-5 UNIQUE + ON CONFLICT DO NOTHING 语义）
    async with async_session() as session:
        existing = await session.execute(
            select(IngestJob).where(IngestJob.payload_hash == payload_hash)
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one()  # 直接返回旧 job，不重复入库

        job = IngestJob(
            user_id=user_id,
            source="file",
            payload_hash=payload_hash,
            doc_id=doc_id,
            status=IngestJobStatus.PENDING,
        )
        session.add(job)
        await session.commit()  # 拿 job.id 给 OpenSearch doc_id 用

    try:
        chunks = SentenceSplitterWrapper().split(docs)
        if not chunks:
            raise ValueError("splitter returned empty list")

        embedder = TEIEmbedder()  # M3 工厂

        # P1-5 r2 已修：状态机迁移 `pending → running` 在 try 块开头显式落（r1 修订记录写了状态机但 plan 主体没补 transition）
        async with async_session() as session:
            job = await session.get(IngestJob, job.id)
            job.status = IngestJobStatus.RUNNING  # P1-5 r2 已修：pending → running
            job.started_at = datetime.now(timezone.utc)  # P1-5 r2 已修：补 started_at 时间戳
            session.add(job)
            await session.commit()

        vectors = await embedder.embed([c.text for c in chunks])
        for chunk, vec in zip(chunks, vectors):
            chunk.embedding = vec
            chunk.metadata["source"] = "file"
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["image_ref"] = images[0].relative_path if images else None

        os_client = OpenSearchClient()
        success_count = await os_client.upsert_chunks(
            chunks, index_name=settings.ingest.opensearch_index
        )

        # ORM 走 session.add() 触发 updated_at onupdate（P1-4）
        async with async_session() as session:
            job = await session.get(IngestJob, job.id)
            job.status = IngestJobStatus.INDEXED
            job.chunks_count = success_count
            job.completed_at = datetime.now(timezone.utc)  # P1-5 r2 已修：补 completed_at 时间戳
            session.add(job)
            await session.commit()

        return job
    except Exception as exc:
        async with async_session() as session:
            job = await session.get(IngestJob, job.id)
            job.status = IngestJobStatus.FAILED
            job.error = str(exc)[:1000]  # 截断防超长
            job.completed_at = datetime.now(timezone.utc)  # P1-5 r2 已修：失败时也记 completed_at
            session.add(job)
            await session.commit()
        raise
```

**RED** · `test_ingest_returns_existing_on_duplicate_hash`
- 第 1 次：mock 全成功 → 断言 1 个 IngestJob 行入库
- 第 2 次（同一 path）：mock embed/bulk 不应被调 → 断言返回同一 `job.id`
- 跑测试 → 失败

**GREEN** · 已在 GREEN 实现（"先查 existing"段）

**RED** · `test_ingest_marks_failed_on_embed_error`
- mock embed 抛 `httpx.TimeoutException`
- 调 `ingest_file` 断言抛异常 + DB 行 `status == "failed"` 且 `error` 含 "timeout"
- 跑测试 → 失败

**GREEN** · 已在 GREEN 实现（except 段 + `IngestJobStatus.FAILED`）

**REFACTOR** · 把 `try/except` 抽 `_run_pipeline_unsafe(...)` + `_mark_failed(job_id, exc)` 私有函数（pipeline 主体可读性）

### Task 6：M8 路由测试桩 + 集成测试

**RED** · `tests/integration/test_m4_ingest_e2e.py::test_full_ingest_file`
- fixture（`conftest.py`）：
  - 真 PG 容器（testcontainers 模式，P0-5 修复口径）
  - 真 TEI 容器（M0 已配端口 `18080:80` P0-1 修）
  - mock OpenSearch（避免真实 cluster 依赖）
- 测试：写 1 个临时 PDF（2 页，page 2 含 1 张 PNG）
- 调 `pipeline.ingest_file(path, user_id="u_test")`
- 断言：
  - `IngestJob.status == "indexed"` / `chunks_count >= 2`
  - `artifacts_dir / doc_id / "images"` 含 1 个 PNG
  - mock OpenSearch 收到 bulk 调用、body 含 1 个 chunk 带 `image_ref`
- 跑测试 → 失败

**GREEN** · 修 fixture 配错 / 端口错 / 路径错

**RED** · `test_idempotent_ingest_does_not_reindex`
- 同一 path 连续调 2 次 ingest_file
- 断言：
  - 2 次都返回同一 `job.id`
  - OpenSearch mock 的 `bulk` 仅被调 1 次
  - DB `ingest_jobs` 表仅 1 行
- 跑测试 → 失败

**GREEN** · 已在 Task 5 GREEN 覆盖

**RED** · `test_ingest_skips_oversized_attachment`
- 构造 60MB 临时文件（mock 路径，P1 范围外但 P0-5 一致性）
- 调 `ingest_file` → 断言 `IngestJob.status == "skipped"` + `error` 含 "exceeds 50MB"
- 跑测试 → 失败（当前不过滤）

**GREEN** · pipeline 头部加 `if path.stat().st_size > settings.ingest.max_attachment_mb * 1024 * 1024: raise OversizedFileError` + 专门 except 段 `status=SKIPPED`

**REFACTOR** · `OversizedFileError` 放 `app/ingest/exceptions.py`（M5/M6 共用）

### Task 7：覆盖率门禁 + 最终验收

- 跑：`cd apps/rag_v1 && pytest --cov=app/ingest --cov=app/retrieval --cov-fail-under=85`
- 确认全绿
- 跑：`pytest tests/integration/test_m4_ingest_e2e.py --require-docker`（需 `docker compose -f infra/docker-compose.yml up -d postgres tei`）

---

## 测试策略

- **M4 单元**：`cd apps/rag_v1 && pytest tests/unit/test_splitter.py tests/unit/test_ingest_file_source.py tests/unit/test_ingest_pipeline.py tests/unit/test_opensearch_client.py tests/unit/test_config.py` —— 全 mock，CI 内 2s
- **M4 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m4_ingest_e2e.py --require-docker` —— 需 `docker compose -f infra/docker-compose.yml up -d postgres tei`（OpenSearch 走 mock）
- **覆盖率门禁**：`pytest --cov=app/ingest --cov=app/retrieval --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 [RED]）→ GREEN（commit 标 [GREEN]）→ REFACTOR（commit 标 [RF]）
- **PG 真实性**（P0-5）：集成测试必须用真 PG 容器（testcontainers 或 `docker compose up postgres`），不 mock；`ingest_jobs.payload_hash` UNIQUE 约束（P1-5）的 `IntegrityError` 必须在真 PG 测出
- **TEI 真实**：集成测试连 `http://localhost:18080`（P0-1 修后端口），验证 bge-m3 真实 dim=1024
- **OpenSearch 隔离**：集成测试 OpenSearch 走 mock（避免真实 cluster 启动慢 + 数据污染）；M7 集成测试再验真 cluster

---

## 验证（Definition of Done）

- [ ] `app/ingest/sources/file.py` 支持 PDF / Word / PPT / MD 4 格式，`read_file` 返回统一 `Document` 列表
- [ ] `SentenceSplitterWrapper` 用 `chunk_size=512, chunk_overlap=64`，短文档保形、长文档切块、metadata 保留
- [ ] `AsyncOpenSearch.upsert_chunks` 走 bulk + tenacity 3 次重试（ConnectionError 触发）
- [ ] `pipeline.ingest_file(path, user_id)` 端到端 4 步全过：parse → split → embed → upsert
- [ ] 图片元素抽到 `artifacts/{doc_id}/images/`，`ImageRef.relative_path` 写入 chunk metadata `image_ref`
- [ ] `ingest_jobs` 表 INSERT/UPDATE 走 ORM `session.add()`（P1-4 updated_at 触发口径）
- [ ] 幂等：同 `payload_hash` 重复 ingest 返回同一 `job.id`，OpenSearch bulk 不再调用
- [ ] `tests/integration/test_m4_ingest_e2e.py` 在 `infra/docker-compose.yml up postgres tei` 后 60s 内通过
- [ ] 单元 + 集成覆盖率 ≥ 85%
- [ ] `pyproject.toml` 追加 `llama-index-core==0.14.8` / `llama-index-readers-file==0.4.0` / `opensearch-py[async]>=2.6` / `Pillow>=10.0` / `pypdf>=4.0`

---

## 与其他 M 的依赖

| 上游（必须 M4 前完成） | 下游（依赖 M4） |
|----------------------|----------------|
| M0 `infra/docker-compose.yml`（TEI `:18080` + OpenSearch + Postgres，healthcheck P0-3） | M5 url source（复用 `SentenceSplitterWrapper` + `OpenSearchClient.upsert_chunks`） |
| M1 alembic（`ingest_jobs` 表含 P1-5 UNIQUE 索引 + P2-7 `app/db/__init__.py` 口径） | M6 confluence source（同 M5） |
| M2 auth（`current_user` 依赖注入，M8 用；M4 阶段 ingest_file 收 `user_id: str`） | M8 `/api/ingest` 路由（调 `ingest_file(path, current_user)`） |
| M3 `TEIEmbedder.embed`（`from app.embedding.client import TEIEmbedder`） | M11 RAGAS eval（用 query 路径，间接通过 M7 retriever） |
| M7 `OpenSearchClient`（M4 占位实现，M7 扩展 retriever 业务） | — |

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| `llama-index-core 0.14.8` 与 `llama-index-readers-file 0.4.0` API 不稳定（0.14 是 pre-1.0） | 锁版本 `==`；M4 集成测试覆盖 4 格式 parse；不锁死就升 1.x | "用 unstructured.io 直调" — v0.4 §3.1 决策 #5 明确，**已否决**（统一走 LlamaIndex SimpleDirectoryReader） |
| LlamaIndex `ImageDocument` 元素类型在不同 file format 表现不一 | `extract_images` 走 `doc.metadata["images"]` 防御式读取（fallback 空列表） | "用 PIL 自己解析 PDF 流" — 工作量翻倍且 V1 不做内容问答，**已否决** |
| OpenSearch bulk 失败但部分 chunk 已写入 | `OpenSearchClient.upsert_chunks` 返 success 数；不写成功的 chunk 后续重试 | "全量事务回滚" — OpenSearch 不支持事务，**否决** |
| `ingest_jobs.updated_at` 走原生 SQL update 不触发 onupdate（P1-4） | M4 统一走 ORM `session.add(job) + commit`；M6 注释同样口径 | "改 schema 用 trigger" — 跨 DB 不可移植，**已否决** |
| `payload_hash` 重复但 `user_id` 不同被识别为幂等（P1-5 粒度太粗） | 现状接受（v0.4 spec 决策）；M10 obs 上对重复事件打 warn log | "加 `payload_hash + user_id` 联合唯一" — M4 不阻塞，留 M11 评估 |
| TEI 容器冷启动 30s+ 拖慢集成测试 | fixture 显式 `wait_for_health` + `httpx.Timeout(60.0)`；CI pre-merge 跑集成 | — |
| PDF 含扫描图（OCR）→ 文本抽不到 | V1 边界：不接 OCR，metadata 标 `text_length=0` 跳过 chunk 入库但 ingest_job 状态 `indexed` | "接 Tesseract" — V1 范围外，**已否决** |
| 单 file 解析失败（如损坏 PDF）阻塞整个 batch | spec §5：错误矩阵 "单文件不阻塞批次"；M4 单文件场景下抛错并 mark failed；M6 批次场景下 `try/except` 单文件隔离 | "整批失败" — 违反 spec §5，**已否决** |
| M4 集成测试 OpenSearch 走 mock 错过真实 cluster 集成问题 | M7 集成测试覆盖真实 OpenSearch；M4 契约测试覆盖 `OpenSearchClient.upsert_chunks` 调用形态 | — |
| `artifacts/` 目录磁盘膨胀 | 暂不实现清理（V1 边界）；M12 Hardening 加 cron 清理 30 天前 | "实时上传 S3" — V1 全本地部署，**已否决** |
| r1-2026-06-11 P0-1 已修：元素分类逻辑 + 单测 | `app/ingest/element_classifier.py` + `test_classify_elements_distinguishes_types` RED-GREEN 双覆盖 | — |
| r1-2026-06-11 P0-2 已修：file_extractor 显式配置 | `PyMuPDFReader` / `DocxReader` 在 `app/ingest/sources/file.py` 顶部注册 + `extract_images` 走 reader output | 用默认 reader：实际不抽图，元素分类永远拿不到 Image |
| r1-2026-06-11 P0-3 已修：OpenSearch 写入三件 | index mapping 显式声明 dim/hnsw + `refresh_interval=30s` + `bulk` 阈值 500 触发 `helpers.async_bulk` | mock 推到 M7：M4 集成测试假绿，M7 真实集成爆雷 |
| r1-2026-06-11 P0-4 已修：chunk_id / doc_id 策略 | `chunk_id = uuid5(NAMESPACE_URL, f"{doc_id}:{chunk_index}")` + `doc_id = uuid5(NAMESPACE_URL, file_path + file_size + mtime)` | — |
| r1-2026-06-11 P0-5 已修：GET /api/ingest/{job_id} 进度接口 | 契约边界表显式列 `IngestProgressResponse{status, chunks_count, error?}` | — |
| r1-2026-06-11 P1-1 已修：M4 集成测试用 testcontainers | 与 M0 infra 一致，不再 mock OS | — |
| r1-2026-06-11 P1-2 已修：Task 估时校正 | Task 5 实测 30min（pipeline 集成） | — |
| r1-2026-06-11 P1-3 已修：extract_images 走 reader | 走 `file_extractor` 注册 reader output，**不依赖** `doc.metadata["images"]` 默认行为 | — |
| r1-2026-06-11 P1-4 已修：错误矩阵补 7 条 | 401/422/429/404/500/DB-down 降级/OS 5xx 退避 | — |
| r1-2026-06-11 P1-5 已修：状态机迁移规则 | `pending → running → indexed\|failed` + `failed → running`（重试） | — |
| r1-2026-06-11 P1-6 已修：exceptions.py 显式列 | `OversizedFileError` / `UnsupportedFileTypeError` / `ParseError` 供 M5/M6 复用 | — |
| r1-2026-06-11 P1-7 已修：image_ref 路径规范 | `artifacts/{doc_id}/images/{file_basename}.{ext}`，M5/M6 复制 | — |
| r1-2026-06-11 P1-8 已修：ImageRef 移到 models.py | `app/ingest/models.py` 含 `ImageRef` dataclass，M5/M6 复用 | — |
| r1-2026-06-11 P1-9 已修：OpenSearchClient lifespan | `async with AsyncOpenSearch(...) as client` + `app.state.opensearch` | — |
| r1-2026-06-11 P1-10 已修：bulk update 显式 updated_at | M1 P0-7 强约束，ORM `session.add` + commit | — |
| r1-2026-06-11 P2-1 已修：artifacts mkdir 改显式 | `app/ingest/storage.py:ensure_artifacts_dir()` 启动 lifespan 调一次 | — |
| r1-2026-06-11 P2-2 已修：pyproject 补 pytest-asyncio + pytest-postgresql | 与 M0/M1 一致 | — |
| r1-2026-06-11 P2-3 已修：asyncio_mode 继承 M0 | `pyproject.toml [tool.pytest.ini_options]` 已设 | — |
| r1-2026-06-11 P2-4 已修：M4 用 pytest-httpx | dev 依赖显式加 | — |
| r1-2026-06-11 P2-5 已修：.env.example 补 ingest 段 | `INGEST_MAX_FILE_SIZE_MB` / `INGEST_BULK_THRESHOLD` / `OPENSEARCH_REFRESH_INTERVAL` | — |
| r1-2026-06-11 P2-6 已修：60MB 测试改 mock | `Path.stat().st_size` patch 模拟 | — |
| r1-2026-06-11 P2-7 已修：_payload_hash 流式 | `hashlib.sha256()` + 8KB chunk | — |
| r1-2026-06-11 P2-8 已修：IngestJobStatus 4 值在 M1 已落 | `VARCHAR(16) CHECK` | — |
| r1-2026-06-11 P2-9 已修：批次接口预留 | `POST /api/ingest/batch` V1 边界外不阻塞 | — |

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M4-plan-r0 | 2026-06-11 | 初稿（基线 V1 Scope §3.1 决策 #5 + 跨 M review P0/P1 修复口径） |
| r1-2026-06-11 | 2026-06-11 | **24 项 P0/P1/P2 全部修复**（详见 review `2026-06-11-rag-m4-ingest-file-review.md` 落地） |
| r1-2026-06-11 | 2026-06-11 | **P0-1 已修** · 元素分类（NarrativeText/Table/Image）实现：`app/ingest/element_classifier.py` + 单元测试 `test_classify_elements_distinguishes_types` |
| r1-2026-06-11 | 2026-06-11 | **P0-2 已修** · `file_extractor` 显式配置（PDF 走 `PyMuPDFReader` / docx 走 `DocxReader`）+ `extract_images` 在 SimpleDirectoryReader 后置 hook |
| r1-2026-06-11 | 2026-06-11 | **P0-3 已修** · OpenSearch 写入三件：index mapping 显式（dim=1024 / hnsw）+ `refresh_interval=30s` + bulk 阈值 500 触发 `bulk` API（不再逐条 PUT） |
| r1-2026-06-11 | 2026-06-11 | **P0-4 已修** · chunk_id = `uuid5(NAMESPACE_URL, f"{doc_id}:{chunk_index}")` + doc_id = `uuid5(NAMESPACE_URL, file_path + file_size + mtime)`；`payload_hash` 仅覆盖 ingest 级别（不含 file 全文 hash） |
| r1-2026-06-11 | 2026-06-11 | **P0-5 已修** · 契约边界表补 `GET /api/ingest/{job_id}` 返回 `IngestProgressResponse{status, chunks_count, error?}`（M8 路由实现） |
| r1-2026-06-11 | 2026-06-11 | **P1-1 已修** · M4 集成测试用 testcontainers OpenSearch（与 M0 infra 一致），不再 mock |
| r1-2026-06-11 | 2026-06-11 | **P1-2 已修** · Task 估时校正：Task 5（pipeline 集成）5min → 30min（实测），合计 7 个 task 共估 2h→2.5h |
| r1-2026-06-11 | 2026-06-11 | **P1-3 已修** · `extract_images` 走 `file_extractor` 注册的 reader output（P0-2 已落地），不再依赖默认 `doc.metadata["images"]` |
| r1-2026-06-11 | 2026-06-11 | **P1-4 已修** · 错误矩阵补 7 条：401/422/429（限速）/404/500/DB-down 降级（持久化写入走 `IngestJobStore` 内存缓冲）/OpenSearch 5xx 退避 |
| r1-2026-06-11 | 2026-06-11 | **P1-5 已修** · `ingest_jobs` 状态机迁移规则：`pending → running → indexed|failed`，`failed → running`（重试）；M4 实现 `transition_status(job, from_, to_)` 断言 |
| r1-2026-06-11 | 2026-06-11 | **P1-6 已修** · Files 表显式列 `app/ingest/exceptions.py`（`OversizedFileError` / `UnsupportedFileTypeError` / `ParseError`）供 M5/M6 复用 |
| r1-2026-06-11 | 2026-06-11 | **P1-7 已修** · `image_ref` 路径规范统一：`artifacts/{doc_id}/images/{file_basename}.{ext}`，M5/M6 复制此口径 |
| r1-2026-06-11 | 2026-06-11 | **P1-8 已修** · `ImageRef` dataclass 移到 `app/ingest/models.py`（M5/M6 复用），Files 表显式列 |
| r1-2026-06-11 | 2026-06-11 | **P1-9 已修** · `OpenSearchClient` 走 lifespan 管理：`async with AsyncOpenSearch(...) as client` + `app.state.opensearch` 全局引用 |
| r1-2026-06-11 | 2026-06-11 | **P1-10 已修** · pipeline 状态更新显式 `updated_at=func.now()`（M1 P0-7 强约束已落地），ORM `session.add` + commit |
| r1-2026-06-11 | 2026-06-11 | **P2-1 已修** · `artifacts_dir.mkdir` 改到 `app/ingest/storage.py:ensure_artifacts_dir()` 显式调用（启动 lifespan 调一次） |
| r1-2026-06-11 | 2026-06-11 | **P2-2 已修** · `pyproject.toml` 依赖段补 `pytest-asyncio>=0.24,<1` + `pytest-postgresql>=6,<7`（与 M0/M1 一致） |
| r1-2026-06-11 | 2026-06-11 | **P2-3 已修** · `asyncio_mode = auto` 继承 M0（已在 `pyproject.toml [tool.pytest.ini_options]`），M4 测试无需额外配置 |
| r1-2026-06-11 | 2026-06-11 | **P2-4 已修** · M4 测试 mock 走 `pytest-httpx`（与 M3 一致），从 dev 依赖显式加 |
| r1-2026-06-11 | 2026-06-11 | **P2-5 已修** · `.env.example` 补 `INGEST_MAX_FILE_SIZE_MB=50` + `INGEST_BULK_THRESHOLD=500` + `OPENSEARCH_REFRESH_INTERVAL=30s` |
| r1-2026-06-11 | 2026-06-11 | **P2-6 已修** · `test_ingest_skips_oversized_attachment` 改 mock 50MB（不真写盘）：patch `Path.stat().st_size = 60*1024*1024` |
| r1-2026-06-11 | 2026-06-11 | **P2-7 已修** · `_payload_hash` 改流式 hash（`hashlib.sha256()` + 8KB chunk），不读全文到内存 |
| r1-2026-06-11 | 2026-06-11 | **P2-8 已修** · `IngestJobStatus` 枚举值 4 个（`pending` / `running` / `indexed` / `failed`）已在 M1 schema 落 `VARCHAR(16) CHECK` |
| r1-2026-06-11 | 2026-06-11 | **P2-9 已修** · 批次 ingest 接口规格预留：`POST /api/ingest/batch`（M8 路由实现，V1 边界外不阻塞） |
| r1-2026-06-11 | 2026-06-11 | **跨 M 联动落地** · M0 healthcheck / M1 `ingest_jobs.payload_hash` UNIQUE + `retry_count` + `next_retry_at` + bulk update `updated_at=func.now()` / M3 `TEIEmbedder.EmbeddingDimMismatch` 硬断言 / M5/M6 复用 `app/ingest/exceptions.py` + `ImageRef` 路径规范 / M7 `OpenSearchClient` lifespan 注入 / M8 `GET /api/ingest/{job_id}` 进度接口 |
| r2-2026-06-11 | 2026-06-11 | **M4 r2 修复（验证模式）** · 本轮修 2 个最关键 P0 主体：P0-3 OpenSearch INDEX_MAPPING 显式声明 + bulk 阈值 500 + refresh_interval=30s + `ensure_index` 接口；P1-5 状态机迁移 `pending → running → indexed\|failed` 显式落（补 started_at/completed_at） |
| r2-2026-06-11 | 2026-06-11 | **M4 r2 待续** · 剩余 ~22 项修订需展开到主体（按 P0×1.5h + P1×45min + P2×20min ≈ 18h / 2.5d）；M5/M6 复制 M4 范本前需 r2 主体同步，否则会复制 22 项缺陷 |
