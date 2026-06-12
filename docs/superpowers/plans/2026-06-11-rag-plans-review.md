# RAG V1 计划 Review 报告

> 评审对象：M0 / M1 / M2 / M3 / M7 五份 plan
> 评审基线：v0.4 spec 决策表 + superpowers-writing-plans 11 段模板
> 评审时间：2026-06-11
> 评审者：Hermes (MiniMax-M3)

---

## 总评

5 份 plan **结构高度一致**（Goal / Architecture / Tech Stack / Files / Tasks(RED-GREEN) / 测试 / DoD / 依赖 / 风险 / 修订记录），整体比 v0.4 spec 当时的脑暴收敛了 1-2 个数量级。但**有一致性裂缝**和**实施前必须改的 P0 阻塞**。

| 维度 | 评分 | 说明 |
|---|---|---|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 5 份都按 11 段模板走 |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 基础设施 GREEN / 业务 RED-GREEN 区分清晰 |
| 任务粒度 | ⭐⭐⭐⭐ | 多数 2-5 分钟，少量超 5 分钟 |
| 契约边界 | ⭐⭐⭐⭐ | M 之间的接口基本明确，但有一处重复定义（checkpointer） |
| 一致性 | ⭐⭐ | 跨 M 出现端口冲突、配置改两次、库重复定义 |
| 实施就绪度 | ⭐⭐ | P0 阻塞不修无法动笔 |

---

## P0 · 阻塞级（动手前必须改）

### P0-1 · 端口冲突（跨 M 一致性）

**问题**：
- M0 Task 1：TEI 容器 `ports: "8080:80"`
- M0 风险 L298-302 自身警告 "8080 本机已有"
- 8080 = 你和我前面开会时启的 `python -m http.server`，**当前还可能随时再起**

**修改**：
- TEI 改 `18080:80`（或 `8088:80`），从源头避雷
- M0 README 注明"如本机 18080 也占用，可改 `18090:80`"

**影响**：M0 启动命令、M3 smoke test URL、`.env.example` 的 `TEI_URL` 全部跟着改

---

### P0-2 · `.env.example` LANGFUSE_DATABASE_URL 密码占位错

**位置**：M0 Task 3
```
LANGFUSE_DATABASE_URL=postgresql://rag_app:***@postgres:5432/rag
```

**问题**：`***` 不是合法 DSN 占位符。新人 copy 后直接 docker compose up，Langfuse 连不上。

**修改**：
```
LANGFUSE_DATABASE_URL=postgresql://rag_app:rag_app_password@postgres:5432/rag
```

**额外**：风险表 L303 写"Langfuse 自带 CMD migration；设 `depends_on: postgres: condition: service_healthy`"——但 Task 1 实际写 docker-compose 步骤**没加**这个 depends_on。要补：
```yaml
services:
  langfuse:
    depends_on:
      postgres:
        condition: service_healthy
```

---

### P0-3 · TEI 缺 healthcheck 块

**问题**：M0 Task 1 写 4 服务，但**没设 healthcheck**——Langfuse `depends_on: condition: service_healthy` 会因 TEI / postgres 无 healthcheck 而没法用。M3 smoke 也要 health endpoint。

**修改**（追加到每个 service）：
```yaml
services:
  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag_app -d rag"]
      interval: 5s
      timeout: 3s
      retries: 10
  opensearch:
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:9200/_cluster/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
  tei:
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:80/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 60s   # bge-m3 模型加载慢
  langfuse:
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:3000/api/public/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
```

**M0 README 启动步骤**也要补：先 `sysctl -w vm.max_map_count=262144`（M0 风险 L300 提了，README 没写）。

---

### P0-4 · M1 alembic.ini sqlalchemy.url 模板语法错

**位置**：M1 Task 4 GREEN 段
```
sqlalchemy.url = postgresql+asyncpg://%(DB_USER)s:%(DB_PASS)s@%(DB_HOST)s:%(DB_PORT)s/%(DB_NAME)s
```

**问题**：Alembic 1.13+ **不支持**这种 `%(VAR)s` 占位符。`sqlalchemy.url` 必须是完整 DSN 或留空。占位符要在 `env.py` 里 `config.set_main_option("sqlalchemy.url", settings.db.database_url)` 设置。

**修改**：
```ini
# alembic.ini
sqlalchemy.url =
```

```python
# alembic/env.py
from app.config import settings
config.set_main_option("sqlalchemy.url", settings.db.database_url)
```

---

### P0-5 · M1 Task 2 单元测试用 sqlite，但生产用 PG

**位置**：M1 Task 2 RED 测试
```python
# sqlite 内存数据库建表 → 断言 User 有 id/username/...
```

**问题**：
1. `ingest_jobs.payload` 是 `JSONB` —— sqlite 不支持 JSONB（会降级为 TEXT）
2. 4 张表全用 `UUID` PK——sqlite 也能存但 PK 类型语义不同
3. `auth_sessions.token_hash VARCHAR(64)` 在 PG 里有 UNIQUE 约束，sqlite 测不出 `IntegrityError` 真实形态

**结果**：单测全绿，但 `alembic upgrade head` 在 PG 上挂。**假绿**。

**修改方案 A**（推荐）：删 sqlite 单测，全部走 testcontainers / pytest-postgresql
**修改方案 B**：单测只测"模型类能 import / 字段名正确"，不测 DDL

---

### P0-6 · M1 Task 3 缺 aiosqlite 依赖却要用

**位置**：M1 Task 3 GREEN L277 "单元测试 mock DB_URL 用 sqlite+aiosqlite 也行"

**问题**：`pyproject.toml` 依赖列表**没有 aiosqlite**。`pip install` 后单测 `import aiosqlite` 失败。

**修改**：要么加 `aiosqlite` 到 `[project.dependencies]`（仅 dev 用就放 `[project.optional-dependencies].dev`），要么这测试归到 integration 跑真 PG。

---

### P0-7 · M1 `test_migration_has_all_tables` 脆

**位置**：M1 Task 4 L298-299
```python
# 解析 0001_initial_schema.py → 断言 upgrade 包含 4 个 op.create_table() 调用
```

**问题**：换行、空格、注释、`op.execute('...')` 内嵌字符串都会误判。真验证应走 `alembic upgrade head` → 查 `information_schema`。

**修改**：直接删这个测试。Task 5 集成测试 `test_migrate_up_creates_tables` 已经覆盖。

---

### P0-8 · M0 pyproject.toml 过度装包

**位置**：M0 Tech Stack 表
```
Web 框架: fastapi >=0.115,<1
ASGI: uvicorn[standard] >=0.32,<1
数据库驱动: sqlalchemy[asyncio] >=2.0.30,<3
```

**问题**：M0 阶段**根本不用** fastapi/uvicorn/sqlalchemy。这三个是 M1/M2 用的。

**修改**：M0 pyproject.toml 只装 `pydantic-settings` + `pydantic`。其余按各 M 阶段加。

---

### P0-9 · M0 / M1 缺 .gitignore

**位置**：两份 plan 都没提到。

**问题**：`apps/rag_v1/.env` / `__pycache__` / `.venv` / `*.db` / `artifacts/` 这些**必须** ignore，否则新人 `git add .` 一次就出事。

**修改**：M0 Task 6 README 旁边**新增 Task 7** 写 `.gitignore`：
```gitignore
# env
.env
.env.local
.env.*.local
# python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
# db
*.db
*.sqlite
*.sqlite3
# artifacts (M4+)
artifacts/
# os
.DS_Store
```

---

### P0-10 · M7 checkpointer 工厂双重定义

**位置**：
- M7 Files 表 L164 `app/retrieval/store.py` 写 `LlamaIndex OpenSearchVectorStore 封装`
- M7 Files 表 L166 `app/memory/checkpointer.py` 写 `AsyncPostgresSaver 包装`
- M7 Files 表 L159 `app/graph/checkpointer.py` 写 `make_checkpointer() 工厂（PG 优先 / SQLite 降级）`

**问题**：
1. `app/memory/checkpointer.py` 和 `app/graph/checkpointer.py` **职责重复**——都是包装 checkpointer
2. v0.4 spec §2 模块树明确定义 `app/memory/checkpointer.py` 是"Postgres checkpointer 封装"，但 M7 把这个逻辑搬到 `app/graph/checkpointer.py`

**修改**：二选一——
- 方案 A（推荐，遵守 spec）：`app/graph/checkpointer.py` 只做"工厂 + 降级逻辑"（即 `make_checkpointer`），`app/memory/checkpointer.py` 删掉或只放 thread 相关
- 方案 B：`app/memory/checkpointer.py` 删了，所有 checkpointer 逻辑放 `app/graph/checkpointer.py`，并把 spec §2 模块树相应更新

无论哪种，**两个文件不要同时存在**。明确说"我选 A / B"后我再继续。

---

## P1 · 重要

### P1-1 · M0 README 启动步骤缺 vm.max_map_count

**位置**：M0 Task 6 README
**修改**：在"启动步骤"前加 `sysctl -w vm.max_map_count=262144`，并加一行注释"OpenSearch 容器启动需要"

---

### P1-2 · M0 缺 mem_limit / cpus 限制

**位置**：M0 Task 1 docker-compose
**问题**：4 个容器无资源限制，本机 OOM risk 高
**修改**：
```yaml
services:
  postgres:    { deploy: { resources: { limits: { memory: 512M, cpus: '1' } } } }
  opensearch:  { deploy: { resources: { limits: { memory: 2G,   cpus: '2' } } } }
  tei:         { deploy: { resources: { limits: { memory: 4G,   cpus: '2' } } } }
  langfuse:    { deploy: { resources: { limits: { memory: 1G,   cpus: '1' } } } }
```

---

### P1-3 · M0 init.sql 写密码明文

**位置**：M0 Task 2
```sql
CREATE ROLE rag_app WITH LOGIN PASSWORD 'rag_app_password';
```

**问题**：v0.4 整体强调 "argon2id hash / token SHA-256"，明文 password 跟调性不一致
**修改**：注释明确"仅本地开发用，prod 走 secret manager"；或者改用 `${POSTGRES_PASSWORD}` 占位符由 docker-compose env 注入

---

### P1-4 · M1 `TimestampMixin.updated_at` 用 onupdate

**位置**：M1 Task 2 GREEN 段
**修改**：注释里写"`onupdate=func.now()` 仅在 ORM `session.add()` 触发；走原生 SQL update 不会动。`ingest_jobs` 走 M4 bulk update 时需显式 `await session.execute(update(...).values(updated_at=func.now(), status=...))`"

---

### P1-5 · M1 `ingest_jobs.payload_hash` 缺 UNIQUE 约束

**位置**：M1 §4 张表结构 ingest_jobs 表
**问题**：payload_hash 语义是"幂等键"，但列定义只 NOT NULL 没 UNIQUE
**修改**：补 `UNIQUE INDEX uq_ingest_jobs_payload_hash ON ingest_jobs(payload_hash)`，配合 `ON CONFLICT (payload_hash) DO NOTHING` 语义（M4 ingest pipeline 用）

---

### P1-6 · M1 `chat_sessions` 缺复合索引

**位置**：M1 §4 张表结构 chat_sessions 表
**修改**：加 `INDEX (user_id, is_active, updated_at DESC)`，加速"按用户查活跃会话"

---

### P1-7 · M2 Argon2 参数过弱（生产环境）

**位置**：M2 Task 1 AuthSettings 默认值
```python
argon2_time_cost: int = 2
argon2_memory_cost: int = 19456
```

**问题**：OWASP 2024 推荐 `time_cost=3, memory_cost=65536`（~64MB）
**修改**：默认改 `time_cost=3, memory_cost=65536`，可被 env override

---

### P1-8 · M2 `extend_session` fire-and-forget 实现风险

**位置**：M2 Task 4 GREEN 段 L327
```python
# 如果 sliding 将过期：异步 fire-and-forget extend_session(token_hash)
```

**问题**：fire-and-forget 在 ASGI 上下文里没等结束就断连接，可能丢任务
**修改**：要么用 `asyncio.create_task()` + 明确把 task 引用存起来，要么改成同步（用 `BackgroundTasks` 调度），要么改成"sliding 过期前 1 天才续期"避免频繁触发

---

### P1-9 · M2 `validate_token_expiry` 双 `datetime.now()` 调用

**位置**：M2 Task 2 GREEN 段 L239
```python
return datetime.now(timezone.utc) < expires_at_sliding and datetime.now(timezone.utc) < expires_at_hard
```

**问题**：两次 `now()` 毫秒级不一致。理论上会引入竞争。
**修改**：抽 `now = datetime.now(timezone.utc)` 一次

---

### P1-10 · M2 模块布局里 `tests/unit/test_auth_tokens.py` 同时含 `test_generate_token_*` 和 `test_auth_config_loads`

**位置**：M2 Files 表 L170
**问题**：token 工具函数的测试 vs config 加载的测试混一个文件
**修改**：拆成 `test_auth_tokens.py`（token 工具）和 `test_auth_config.py`（config 加载）

---

### P1-11 · M2 M2 L376 RED 测试标错

**位置**：M2 Task 5 末尾 L380
```python
# 用随机 token 调 /api/protected（或 mock endpoint）→ 断言 404
```

**问题**：M2 范围不创建 `/api/protected`，需要 mock 一个。需要注释里说明"为这个测试加一个临时 protected endpoint 验证 404 行为，测试结束移除"。

---

### P1-12 · M3 `langfuse.CallbackHandler` import path

**位置**：M3 Tech Stack 关键导入路径 L133
```python
from langfuse.langchain import CallbackHandler
```

**问题**：langfuse v2 重构后 import 路径有变更风险
**修改**：在 Task 3 RED 段补一句"若 import 失败 fallback `from langfuse.callback.langchain import CallbackHandler`"

---

### P1-13 · M3 4 节点 prompt yaml 实际内容未写

**位置**：M3 Files 列出 4 个 yaml 但 GREEN 段不写内容
**问题**：DoD L283 写"4 个 prompt yaml 文件（classify/rewrite/rerank/answer）各 ≥ 50 token，含 1-shot 示例"——但 plan 里没草稿
**修改**：每 yaml 至少给 1 段伪代码草稿（5-10 行），否则 Task 4 `test_factory_binds_system_prompt` 测试不到真实 prompt 内容

---

### P1-14 · M3 `make_llm` 注入 callback 方式

**位置**：M3 Task 4 GREEN 段
```python
# 如果 get_callback_handler() is not None → 注入到 model.callbacks
```

**问题**：langchain 1.0+ 弃用 `model.callbacks`，新写法是 `model.with_config({"callbacks": [...]})` 或 invoke 时传 config
**修改**：用 `make_llm(node).with_config({"callbacks": [handler]})` 或在节点函数里传

---

### P1-15 · M7 `route_after_answer` 缺测试

**位置**：M7 Task 10
**修改**：补一个 RED 测试 `test_routes_to_save_memory_after_answer`（plan 提到但代码段截断看不到 GREEN 段，确认是否写了）

---

### P1-16 · M7 `app/retrieval/store.py` vs `retriever.py` 边界不清

**位置**：M7 Files 表 L161-165
**修改**：明确 `store.py` 只做 LlamaIndex `OpenSearchVectorStore` 实例化，`retriever.py` 做 retrieve 业务逻辑。Files 表注释里写清。

---

### P1-17 · M7 集成测试 `test_fallback_answer_on_retrieve_failure` 期望的 hardcoded 文案

**位置**：M7 Task 11 GREEN 段
**修改**：文案放进 settings（`RetrievalSettings.fallback_message`），方便 A/B 和 i18n

---

### P1-18 · M2 / M3 缺 `pytest-httpx` 声明

**位置**：M3 Tech Stack 提到 `pytest-httpx`，但 pyproject 依赖表里没写
**修改**：M3 追加 `pytest-httpx >=0.30,<1` 到 dev 依赖

---

## P2 · 优化

### P2-1 · 5 份 plan 全缺 `pytest.ini` / `pyproject.toml` 的 `[tool.pytest.ini_options]`

**修改**：M0 Task 6 README 旁边新增 Task 7 同时补 `pytest.ini`：
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
addopts = -v --tb=short
```

---

### P2-2 · 5 份 plan 全缺 `pyproject.toml` 的 `[project]` 块

**位置**：M0 Task 4
**修改**：
```toml
[project]
name = "rag-v1"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.7,<3",
  "pydantic-settings>=2.3,<3",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.24,<1",
]
```

---

### P2-3 · 5 份 plan 重复描述 "apps/rag_v1/ 是独立 Python 项目"

**修改**：抽出来写一个 `apps/rag_v1/AGENTS.md`，跨 M 复用

---

### P2-4 · M7 Task 9 `load_memory_node` 写 `cp.aget` API

**位置**：M7 Task 9 GREEN L468
**问题**：langgraph 1.0.5 的 API 是 `checkpointer.aget_tuple` 不是 `aget`
**修改**：核对 langgraph 1.0.5 文档修正

---

### P2-5 · M7 `make_checkpointer` 是 `@asynccontextmanager` 工厂

**位置**：M7 Task 2 GREEN L235
**问题**：langgraph `compile(checkpointer=...)` 期望的是 checkpointer 实例，不是 contextmanager。需要在外部 `async with` 后再 compile
**修改**：要么改成"返回非 contextmanager 的实例"，要么 plan 里明确"调用方负责 `async with make_checkpointer() as cp: ...`"

---

### P2-6 · M2 `app/api/auth.py` 没显式 `app/api/__init__.py` 聚合

**位置**：M2 Files 表 L162-164 + L207-209
**问题**：Files 表列了 `app/api/__init__.py` 和 `app/api/auth.py`，但 Task 5 段"实现 `app/api/__init__.py`" 写得仓促
**修改**：补完整 APIRouter 聚合代码

---

### P2-7 · M1 `app/db/__init__.py` 暴露 API 不一致

**位置**：M1 Files 表 L207 + L88 段 Task 3 REFACTOR
**问题**：Files 写"暴露 async_session / get_session / AsyncSession"，但 Task 3 REFACTOR 说"把 engine / async_session 声明移到 __init__.py"
**修改**：对齐为 `__init__.py` 暴露 `engine` / `async_session` / `get_session` / `AsyncSession` 四个

---

## 跨 M 一致性问题

### X-1 · `app/config.py` 跨 M 反复改

M0 建 → M1 追加 `DBSettings` → M2 追加 `AuthSettings` → M3 追加 `LLMSettings`/`EmbeddingSettings`/`LangfuseSettings` → M7 追加 `OpenSearchSettings`/`CheckpointerSettings`

**问题**：5 次改动同一文件，到 M7 已经是 8 个子配置。早期未预留扩展点。
**修改**：M0 直接把 `app/config.py` 拆 `app/configs/__init__.py` + 子文件（postgres.py / llm.py / ...）。M0 REFACTOR L230 已提"如 Task 数多 → 后续 M 做"——建议**现在做**。

---

### X-2 · CI 路径假设冲突

M0 L259 `cd apps/rag_v1 && pytest` —— GitHub Actions workflow（M14）需要在根目录设置 `working-directory: apps/rag_v1` 或用 `pytest --rootdir=apps/rag_v1`。
**修改**：M0 加 Task："写 `apps/rag_v1/pytest.ini` 锁定 rootdir"，5 份 plan 同步更新

---

### X-3 · 4 份 plan 都引 `from app.config import settings`

但 M0 用 `Settings()` 实例化的语法在 M0 L223 写 `from app.config import Settings; settings = Settings()`，M2/M3/M7 没强调这个全局单例。
**修改**：M0 决定"在 `app/config.py` 末尾 `settings = Settings()` 暴露全局单例"，5 份 plan 统一用 `from app.config import settings`

---

### X-4 · dev / prod 分离未设计

5 份 plan 全是 dev 视角。生产怎么部署、镜像怎么打、env 怎么注入**全部没说**。
**修改**：M12 Hardening 段加 prod 部署子任务（"docker-compose.override.yml 模式"或"compose.prod.yaml 分离"）

---

## 按 plan 的差异化问题

### M0 特有
- 端口冲突 P0-1 / P0-3
- README 缺 vm.max_map_count P1-1
- 缺 mem_limit P1-2
- init.sql 密码明文 P1-3
- pyproject.toml 过度装包 P0-8
- 缺 .gitignore P0-9
- 缺 [project] 块 P2-2

### M1 特有
- alembic.ini 模板语法错 P0-4
- sqlite 测 JSONB P0-5
- aiosqlite 缺依赖 P0-6
- test_migration_has_all_tables 脆 P0-7
- updated_at onupdate 限制 P1-4
- ingest_jobs.payload_hash 缺 UNIQUE P1-5
- chat_sessions 缺复合索引 P1-6
- app/db/__init__.py 暴露不一致 P2-7

### M2 特有
- Argon2 参数弱 P1-7
- extend_session fire-and-forget P1-8
- validate_token_expiry 两次 now() P1-9
- test_auth_tokens.py 含 config 测试 P1-10
- protected endpoint mock 不清 P1-11
- app/api/__init__.py 聚合缺 P2-6

### M3 特有
- langfuse import 路径风险 P1-12
- 4 yaml 内容缺草稿 P1-13
- make_llm callback 注入方式过时 P1-14
- pytest-httpx 缺声明 P1-18

### M7 特有
- checkpointer 双重定义 P0-10
- route_after_answer 测试缺 P1-15
- retrieval store vs retriever 边界不清 P1-16
- fallback 文案硬编码 P1-17
- load_memory aget API 错 P2-4
- make_checkpointer contextmanager 形态 P2-5

---

## 落地建议

按 P0 → P1 → 缺 plan → 实现的顺序：

1. **本轮**：先修 P0（10 项），开两个新 plan 文档落地 patch 记录
2. **本轮**：写 M4/M5/M6/M8/M9/M10/M11/M12 七份新 plan
3. **下轮**：M0/M1 实际改代码（按修改后的 plan）
4. **并行**：M0 git 仓库初始化（一旦 P0 修完可以独立推进）

---

## 状态

- 等待决策：P0-10 checkpointer 双重定义选 A 还是 B
- 等待决策：X-1 app/config.py 拆分是否现在做
- 等待决策：X-4 prod 分离是否在 M12 加

修完 P0 即可开 M4-M12 plan 起草。
