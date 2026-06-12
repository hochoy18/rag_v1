# M1 Plan Review · Schema 层

> 评审对象：M1 (2026-06-10-rag-m1-schema.md, 395 行)
> 评审基线：V1 Scope v0.4 spec（§0 决策 #13/#14 / §1 架构 / §2 模块树 / §3.2 Auth 数据流 / §5 错误矩阵 / §8 依赖清单）+ 已有 review 报告 + M0 review + M3 范本 11 段
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M1 plan 完整覆盖 11 段模板（Goal / 不包含 / Architecture / Tech Stack / Files / Tasks / 测试 / DoD / 依赖 / 风险 / 修订记录），4 张表 DDL 定义完整且与 spec §3.2 Auth 数据流对齐。但**实施就绪度不足**——alembic.ini 模板语法错（已知 P0-4）、sqlite 测 PG-only 类型的"假绿"风险（已知 P0-5）、aiosqlite 缺依赖（已知 P0-6）、test_migration_has_all_tables 脆（已知 P0-7）这 4 个 P0 必改；**外加本 review 新发现的 15+ 个问题**，覆盖审计字段、索引策略、连接池配置、enum 设计、alembic 生产化选项、跨 M 配置接口等领域。

|| 维度 | 评分 | 说明 |
||---|---|---|
|| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐，仓库布局 / 模块树 / 契约边界表完整 |
|| DDL 完整性 | ⭐⭐⭐⭐ | 4 表列 / 约束 / 索引都有，缺 UNIQUE 索引和部分查询索引 |
|| 一致性 | ⭐⭐⭐ | 表字段与 spec §3.2 对齐；但 alembic.ini 模板错 / `app/db/__init__.py` 暴露不一致 / `app/config.py` 全局单例未落实（X-3） |
|| 实施就绪度 | ⭐⭐ | P0-4 ~ P0-7 全未改；TDD 粒度看似 2-5 分钟，alembic 配置 + async migration 实测超 5 分钟 |
|| 错误处理 | ⭐⭐⭐ | risk 表 6 行覆盖主要风险，但缺 alembic 并发 / asyncpg + pgbouncer 兼容性 / 缺 enum 类型一致性 |
|| 跨 M 契约 | ⭐⭐⭐ | 契约表清晰，但 `app/config.py` 拆分（X-1）和全局单例（X-3）都未决议 |

**一句话**：M1 plan 框架对、DDL 主体对，但 alembic 工程化与生产化考虑严重不足，**未修 P0 + 6 个新 P0 之前不可直接动手**。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · alembic.ini 模板 `%(VAR)s` 占位符语法错（已有 review 重复）

**位置**：M1 Task 4 GREEN 段 L289
```
sqlalchemy.url = postgresql+asyncpg://%(DB_USER)s:%(DB_PASS)s@%(DB_HOST)s:%(DB_PORT)s/%(DB_NAME)s
```

**问题**：Alembic 1.13+ `sqlalchemy.url` 必须是完整 DSN 或留空，`%(VAR)s` 这种 ConfigParser interpolation 已被弃用。占位符要在 `env.py` 用 `config.set_main_option(...)` 设置。

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

**已有 review**：P0-4 已列，本次 verify **仍未改**。

---

### P0-2 · 单元测试用 sqlite，但 4 张表含 PG-only 类型

**位置**：M1 Task 2 RED 段 L243 / Task 3 GREEN 段 L277
```python
# sqlite 内存数据库建表 → 断言 User 有 id/username/...
# 单元测试 mock DB_URL 用 sqlite+aiosqlite 也行
```

**问题**：
- `ingest_jobs.payload` 列定义是 `JSONB`——sqlite 不支持，会降级为 `TEXT`
- `auth_sessions.token_hash` 等 VARCHAR(64) 在 PG 有 UNIQUE 约束，sqlite 测 `IntegrityError` 形态可能不一致
- 4 表全用 PG 原生 `UUID`——sqlite 存没问题但 PK 类型语义不同
- 单测在 sqlite 全绿，但 `alembic upgrade head` 在 PG 上挂——**假绿**

**修改**：
- 方案 A（推荐）：删 sqlite 单测，全部走 `pytest-postgresql` / testcontainers
- 方案 B：单测只测"模型类可 import / 字段名正确 / `__table_args__` 含预期约束"，不真正 DDL 化

**已有 review**：P0-5 已列。

---

### P0-3 · aiosqlite 缺依赖却要用

**位置**：M1 Task 3 GREEN 段 L277
```
单元测试 mock DB_URL 用 sqlite+aiosqlite 也行
```

**问题**：`pyproject.toml` 依赖列表**没有 aiosqlite**。`pip install` 后单测 `import aiosqlite` 失败。即使改用方案 A（testcontainers），P0-2 的 dev 依赖也要列。

**修改**：
- 走方案 A：dev 依赖加 `pytest-postgresql >=6.0,<7` + `testcontainers[postgresql] >=4.0,<5`
- 走方案 B（保留 sqlite 备选）：dev 依赖加 `aiosqlite >=0.20,<1`（spec §8.5 已声明此版本，可直接复用）

**已有 review**：P0-6 已列。

---

### P0-4 · `test_migration_has_all_tables` 测试脆

**位置**：M1 Task 4 RED 段 L298-299
```python
# 解析 0001_initial_schema.py → 断言 upgrade 包含 4 个 op.create_table() 调用
```

**问题**：
- alembic 默认生成的 revision 文件名是 hex revision id（如 `7f8a9b2c3d4e_initial_schema.py`），**不是** plan 里写的 `0001_initial_schema.py`——这个测试**永远**过不了
- 即使改文件名，AST 解析对注释 / 字符串内嵌 / 换行敏感
- 真验证应走 `alembic upgrade head` → 查 `information_schema`

**修改**：
1. **删这个测试**（Task 5 集成测试 `test_migrate_up_creates_tables` 已经覆盖）
2. 同步：plan Files 表 + 任务描述里把所有 `0001_initial_schema.py` 改为 `7f8a9b2c3d4e_initial_schema.py`（或用 `alembic init --package` 生成的 hex 名），或显式说明"用 `alembic revision --autogenerate` 生成后改名为 `0001_` 前缀"
3. file_naming_convention 也要在 env.py 配：`file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s` 才会产生 `20260611_2230_initial_schema.py`

**已有 review**：P0-7 已列前半段（脆），本 review **新发现**文件命名规范与 plan 描述不一致。

---

### P0-5 · `app/db/__init__.py` 暴露 API 描述内部矛盾

**位置**：M1 Files 表 L207 + 仓库布局 L75 + Task 3 REFACTOR 段 L279

**问题**：
- Files 表 L207："暴露 `async_session` / `get_session` / `AsyncSession`"
- 仓库布局 L75："暴露 `async_session` / `get_session` / `AsyncSession`"
- Task 3 REFACTOR L279："把 `engine` / `async_session` 声明移到 `__init__.py` 提供 `__all__`"

**矛盾**：Files 表**不包含** `engine`，REFACTOR 段**包含** `engine`。

**修改**：统一为 `__init__.py` 暴露：
```python
# app/db/__init__.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session, async_session_factory, engine, get_session

__all__ = ["AsyncSession", "async_session", "async_session_factory", "engine", "get_session"]
```

**已有 review**：P2-7 已列。

---

### P0-6 · alembic env.py 缺 `target_metadata` 与 `run_async` 配置细节

**位置**：M1 Task 4 GREEN 段 L290-292
```python
# alembic/env.py
import app.db.base
target_metadata = app.db.base.DeclarativeBase.metadata
# async migration runner：用 run_async 模式（Alembic 1.13+ async support）
```

**问题**：
- "用 run_async 模式" 是 Alembic 1.13+ 的 async migration 模板，**不是一行配置**——需要 `asyncio.run()` 包装 + `connection.run_sync(...)` 包裹 `context.run_migrations()`
- 直接照 plan 抄会让 `alembic upgrade head` 在 async engine 上失败：`ProgrammingError: cannot run sync operation in async context`
- env.py 还需 `connectable = create_async_engine(...)` + `async def run_async_migrations()`

**修改**（env.py 完整模板）：
```python
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.config import settings
from app.db.base import DeclarativeBase
import app.db.models  # noqa: F401 触发 model 注册

config = context.config
config.set_main_option("sqlalchemy.url", settings.db.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = DeclarativeBase.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(settings.db.database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_online()
```

**新发现**（已有 review 未列）。

---

### P0-7 · `TimestampMixin.updated_at` onupdate 限制未在 plan 注释化

**位置**：M1 Task 2 GREEN 段 L248
```python
updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

**问题**：
- `onupdate=func.now()` **只在 ORM `session.execute(update(Model))` 之外、不带 values 时触发**；走 bulk update `session.execute(update(Model).values(...))` 不会动 `updated_at`
- M4 ingest pipeline 走 `UPDATE ingest_jobs SET status=..., chunks_count=... WHERE id=?` 形式——`updated_at` **不会**自动更新
- plan 缺这个 caveat，M4 实现时会踩坑

**修改**：在 TimestampMixin docstring 显式写：
```python
class TimestampMixin:
    """updated_at only auto-updates on ORM-level dirty detection.
    For bulk update via session.execute(update(...).values(...)),
    pass updated_at=func.now() explicitly. See M4 ingest_jobs.
    """
```

**已有 review**：P1-4 已列。

---

## P1 · 重要

### P1-1 · `ingest_jobs.payload_hash` 缺 UNIQUE 约束（与 idempotency 语义不符）

**位置**：M1 §4 ingest_jobs 表 L144
```
| `payload_hash` | `VARCHAR(64)` | NOT NULL | SHA-256(source + payload) |
```

**问题**：
- spec §3.1 写"`INSERT ingest_jobs (status=pending, source, payload_hash)`"——payload_hash 是幂等键
- 列定义只 NOT NULL **没 UNIQUE**——同 payload 可被 INSERT 多次，破坏幂等
- M4 ingest pipeline 要用 `ON CONFLICT (payload_hash) DO NOTHING` 语义，没 UNIQUE 约束就没法 `ON CONFLICT`

**修改**：补 `UNIQUE INDEX uq_ingest_jobs_payload_hash ON ingest_jobs(payload_hash)`

**已有 review**：P1-5 已列。

---

### P1-2 · `chat_sessions` 缺 `(user_id, is_active, updated_at DESC)` 复合索引

**位置**：M1 §4 chat_sessions 表 L134
```
Indexes: (user_id, updated_at DESC) — 按用户查询最近会话
```

**问题**：
- spec §3.2 写"GET /api/sessions → SELECT * FROM chat_sessions WHERE user_id=current_user ORDER BY updated_at DESC"
- 现有索引 `(user_id, updated_at DESC)` 已能服务这个查询，但**没考虑 `is_active=FALSE` 软删除**——M8 API 实际查询要加 `WHERE is_active=TRUE`
- 加 `is_active` 到索引才能走 index scan

**修改**：索引改为 `(user_id, is_active, updated_at DESC)`，加速"按用户查活跃会话"

**已有 review**：P1-6 已列。

---

### P1-3 · 缺 `users.created_by` / `users.updated_by` 审计字段（V2 必加）

**位置**：M1 §4 users 表 L98-108

**问题**：
- 4 表都没审计字段 `created_by` / `updated_by`
- V1 spec §9 明说"单租户"——但 V2 切多租户 + admin 后台必加
- M1 schema 阶段补 2 个 nullable 列零成本；V2 再加要做 migration 还得 backfill NULL

**修改**：在 users / auth_sessions / chat_sessions / ingest_jobs 都加：
```python
created_by: Mapped[uuid.UUID | None] = mapped_column(UUID, ForeignKey("users.id"), nullable=True)
updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID, ForeignKey("users.id"), nullable=True)
```

**新发现**。

---

### P1-4 · 缺 `users.email` 字段（M12 hardening 几乎必加）

**位置**：M1 §4 users 表

**问题**：
- V1 用户系统只 `username`+`password_hash`，没 `email`
- M12 hardening 要做"密码重置邮件 / 账号找回 / 异常登录告警"——100% 缺 email
- M1 阶段加 `email VARCHAR(255) UNIQUE NULL` 零成本（先 nullable 不影响注册）

**修改**：
```python
email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**新发现**。

---

### P1-5 · 缺 `users.deleted_at` 软删除字段（与 `is_active` 实现不同）

**位置**：M1 §4 users 表

**问题**：
- 现有 `is_active BOOLEAN` 是"软禁用"标记，但删除用户要走"完全隐藏 + 30 天可恢复"语义
- M2 logout 不会动 `is_active`；真正删账号时是 `is_active=FALSE` 还是 `deleted_at=NOW()`？两者语义不同：
  - `is_active=FALSE` → 管理员禁用（账号仍占位）
  - `deleted_at` → 用户自删（30 天硬删）

**修改**：
- 加 `deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)`
- 加 unique partial index：`CREATE UNIQUE INDEX uq_users_username_active ON users(username) WHERE deleted_at IS NULL`——允许"已删用户的 username 被新用户复用"

**新发现**。

---

### P1-6 · 缺 `chat_sessions.last_message_at` 字段（M8 API 排序用）

**位置**：M1 §4 chat_sessions 表

**问题**：
- 现有 `updated_at` 既会被任何 UPDATE 触发（M9 UI 改 title、未来的 metadata 改动），不能准确反映"最后消息时间"
- M8 API `/api/sessions` 返回的列表前端通常按"最后消息时间"排序
- M7 graph 节点 save_memory 时应显式 `last_message_at = NOW()`

**修改**：
```python
last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
```

**新发现**。

---

### P1-7 · 缺 `ingest_jobs.completed_at` / `auth_sessions.expires_at_hard` / `auth_sessions.user_id` 索引

**位置**：M1 §4 多张表

**问题**：
- 4 表的 FK 列（`auth_sessions.user_id` / `chat_sessions.user_id` / `ingest_jobs.user_id`）都**没显式索引**——虽然 PG 不会自动给 FK 建索引
- `ingest_jobs.status` 经常被 M4 worker 轮询（`WHERE status='pending' ORDER BY created_at LIMIT 10`），缺 `(status, created_at)` 复合索引会全表扫
- `auth_sessions.expires_at_hard` 被 M2 cleanup job 用来"清理过期 token"（`WHERE expires_at_hard < NOW()`），缺索引会随表增大变慢
- M11 RAGAS 评测要"最近 7 天 ingest 的成功率"——`ingest_jobs.completed_at` 缺索引

**修改**：
```python
# auth_sessions
__table_args__ = (
    Index("ix_auth_sessions_user_id", "user_id"),
    Index("ix_auth_sessions_expires_at_hard", "expires_at_hard"),
)

# ingest_jobs
__table_args__ = (
    Index("ix_ingest_jobs_user_id_created_at", "user_id", "created_at"),
    Index("ix_ingest_jobs_status_created_at", "status", "created_at"),
    Index("ix_ingest_jobs_completed_at", "completed_at"),
    UniqueConstraint("payload_hash", name="uq_ingest_jobs_payload_hash"),
)
```

**新发现**（FK 自动索引这件事 PG 不会做，必须显式）。

---

### P1-8 · 缺 `app/auth/password_validator.py` 函数（M2 必用，M1 可定）

**位置**：M1 plan 整篇

**问题**：
- spec §3.2 写"POST /api/auth/register → 校验（用户名唯一、密码强度）"
- M2 auth 业务逻辑要用"密码强度校验"函数，但 plan 整篇没规划
- M1 schema 阶段定 `app/auth/password_validator.py` 签名（含最小长度 / 字符类型 / 常见密码 blacklist hook），M2 只接业务

**修改**（Files 表追加 M1 新增）：
```
app/auth/__init__.py                # 包标识
app/auth/password_validator.py      # validate_password(pw: str) -> None  # raise ValueError
tests/unit/test_password_validator.py  # 弱密码 / 强密码 / 边界值
```

实现草稿：
```python
# app/auth/password_validator.py
import re

MIN_LENGTH = 12
MAX_LENGTH = 128
COMMON_PASSWORDS = {"password", "12345678", "qwerty", ...}  # 简化

def validate_password(pw: str) -> None:
    if not (MIN_LENGTH <= len(pw) <= MAX_LENGTH):
        raise ValueError(f"Password length must be {MIN_LENGTH}-{MAX_LENGTH}")
    if pw.lower() in COMMON_PASSWORDS:
        raise ValueError("Password too common")
    if not re.search(r"[a-z]", pw) or not re.search(r"[A-Z]", pw):
        raise ValueError("Password must contain mixed case")
    if not re.search(r"\d", pw):
        raise ValueError("Password must contain digit")
```

**新发现**。

---

### P1-9 · 缺 `downgrade()` 实现要求（alembic 默认要可回滚）

**位置**：M1 Task 4 GREEN 段 L294-296
```
# 生成初始迁移：cd apps/rag_v1 && alembic revision --autogenerate -m "initial_schema"
# 检查生成的 migration 确认 4 张表全部在 upgrade() 中
# 手动补 CHECK / INDEX / FK 约束（autogenerate 可能遗漏）
```

**问题**：
- plan 只说"补 CHECK/INDEX/FK"，没说 `downgrade()` 也要补
- alembic 1.13+ 默认要求 `downgrade()` 必须能跑（`alembic downgrade base` 要回到空 schema）
- 初始 migration 不写 downgrade 等于关掉回滚能力——以后想 `alembic downgrade -1` 调试会卡住

**修改**：Task 4 GREEN 段补"手写 `downgrade()` 删除 4 表 + drop enum（如有）+ drop index"，并加 RED 测试 `test_migration_downgrade_works`（`alembic downgrade base` → 4 表全没了）。

**新发现**。

---

### P1-10 · 缺 enum 类型 vs VARCHAR+CHECK 的设计决策

**位置**：M1 §4 ingest_jobs 表 L143-144
```
| `source` | `VARCHAR(16)` | NOT NULL, CHECK IN file/url/confluence | 数据源 |
| `status` | `VARCHAR(16)` | NOT NULL, DEFAULT pending | pending/running/indexed/failed |
```

**问题**：
- spec §0 决策表（其他位置）暗示 "status enum" 概念（pending/running/indexed/failed 是状态机的离散状态）
- M1 plan 用 VARCHAR+CHECK——可以，但跟 PG 原生 `CREATE TYPE ... AS ENUM` 比：
  - VARCHAR+CHECK：加新值只需 `ALTER TABLE ... DROP CONSTRAINT ... ADD CONSTRAINT ... CHECK (...)`，改 app 端 enum 同步
  - PG ENUM：加新值需 `ALTER TYPE ... ADD VALUE '...'`（PG 9.6+ 还要 `IF NOT EXISTS` 兼容老 enum value）
  - VARCHAR+CHECK 在 ORM 层更灵活
- plan **没在风险表记录这个选择**——M4-M6 worker 写代码时会有"为什么不用 enum"的疑问

**修改**：
- 风险表补一行：`enum 选择` | 风险：PG ENUM 加 value 不能在事务内 / VARCHAR+CHECK 改 CHECK 约束要锁表（M4 写入时短暂锁）| 缓解：V1 状态机简单（4 值）+ 数据量小，锁表 < 100ms 可接受
- Tech Stack 表加一句"不引入 sqlalchemy Enum 类型，用 String + CheckConstraint"

**新发现**。

---

### P1-11 · 缺 connection pool 配置细节（pool_size 10 / max_overflow 20 依据）

**位置**：M1 Task 3 GREEN 段 L270 + 风险表 L386
```
engine = create_async_engine(settings.db.database_url, pool_size=..., max_overflow=..., echo=...)
```

**问题**：
- 风险表说"pool_size=10 / max_overflow=20"——**没给依据**
- V1 单进程 / 单副本 fastapi + 1 ingest worker，10+20=30 连接是 PG 默认 `max_connections=100` 的 30%
- 没依据的默认值会让 M8 API 流量上来后变瓶颈

**修改**：
- 风险表该行改：`依据：V1 单副本 30 连接，预留 70 给 Langfuse / LangGraph checkpointer / M11 RAGAS / 调试客户端` + 加 `pool_recycle=1800`（防 stale connection，30 分钟回收）+ `pool_pre_ping=True`（防连接被 PG 端断）
- Tech Stack 表补 `pool_recycle=1800` 字段

**新发现**。

---

### P1-12 · 缺 asyncpg + pgbouncer 兼容配置（prod 必踩）

**位置**：M1 Task 3 GREEN 段 L270

**问题**：
- M12 hardening 几乎必加 pgbouncer（transaction pool 模式）
- asyncpg 在 transaction pool 模式下**默认**会缓存 prepared statement——pgbouncer 不支持 → 报错 `PreparedStatementError`
- 必须显式 `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}`

**修改**（env.py 或 session.py 显式注释）：
```python
engine = create_async_engine(
    settings.db.database_url,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    pool_pre_ping=True,
    connect_args={
        "statement_cache_size": 0,      # 兼容 pgbouncer transaction pool
        "prepared_statement_cache_size": 0,
    },
    echo=settings.db.echo,
)
```

并在风险表补一行：`pgbouncer transaction pool 兼容` | 风险：asyncpg 默认 cache prepared statement 会报 `PreparedStatementError` | 缓解：`statement_cache_size=0` + M12 加 pgbouncer 后零改动

**新发现**。

---

### P1-13 · 缺 DB migration 并发锁（alembic 同时跑两个会冲突）

**位置**：M1 plan 整篇

**问题**：
- 部署场景：CI 跑 `alembic upgrade head` + 容器启动时跑 `alembic upgrade head`——两进程同时改 schema 必冲突
- PG 自带 `pg_advisory_lock` 可在 env.py 里 `context.run_migrations()` 前 `SELECT pg_advisory_lock(alembic_lock_id)`，但 plan 没说

**修改**（env.py 补 advisory lock）：
```python
# alembic/env.py
ALEMBIC_LOCK_ID = 0x5241475631  # 'RAG_V1' hex

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # ... 其他参数
    )
    connection.exec_driver_sql(f"SELECT pg_advisory_lock({ALEMBIC_LOCK_ID})")
    try:
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.exec_driver_sql(f"SELECT pg_advisory_unlock({ALEMBIC_LOCK_ID})")
```

**新发现**。

---

### P1-14 · 缺 `__table_args__` 集中声明索引（vs 在列里声明）

**位置**：M1 §4 4 张表 L97-153

**问题**：
- 现有 DDL 表只写"Indexes: `(user_id, updated_at DESC)`" 是注释形式
- SQLAlchemy 2.0 推荐用 `__table_args__ = (Index(...), UniqueConstraint(...), CheckConstraint(...))` 集中声明
- 列里用 `index=True` 散落 + `__table_args__` 混用，autogenerate 难预测

**修改**：plan §4 张表结构每表都加 `__table_args__` 块示意：
```python
class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_sessions_user_active_updated", "user_id", "is_active", "updated_at"),
        Index("ix_chat_sessions_last_message_at", "last_message_at"),
    )
```

**新发现**。

---

### P1-15 · 缺 server-side default 显式声明 vs client-side

**位置**：M1 §4 users 表 L107-108
```
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, auto-update | 更新时间 |
```

**问题**：
- "DEFAULT now()" 语义模糊：可以是 client-side `default=datetime.now` 或 server-side `server_default=text("now()")`
- M4 ingest worker 多进程同时写入，client-side `datetime.now()` 会**不同时区漂移**
- 必须显式 `server_default=func.now()` 让 PG 端统一时间

**修改**：plan GREEN 段统一：
```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),  # PG 端 now()，统一时区
    nullable=False,
)
```

并在注释里写"全部时间字段用 TIMESTAMPTZ + server_default=func.now()，禁止 client-side default"

**新发现**。

---

### P1-16 · 缺 `pytest.ini` 的 `[tool.pytest.ini_options]`（X-2 待落地）

**位置**：M1 plan 整篇

**问题**：
- 已有 review X-2 决议"5 份 plan 同步更新 pytest.ini rootdir"
- M1 plan 整篇**没提到** `pytest.ini` 或 `pyproject.toml` 的 pytest 配置
- 没有 `asyncio_mode = "auto"`，单测 `async def test_xxx` 不会自动被 pytest-asyncio 识别
- M1 集成测试 `test_m1_schema_migration.py` 全是 async，没 `asyncio_mode = "auto"` 直接报错

**修改**（Task 6 旁补 Task 7）：
```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short --strict-markers"
markers = [
    "require_docker: marks tests as requiring docker compose up (deselect with '-m \"not require_docker\"')",
]
```

**已有 review**：P2-1 / X-2 已列。

---

### P1-17 · 缺 `app/config.py` 全局单例约定（X-3 待落地）

**位置**：M1 Task 1 GREEN 段 L236-238
```python
class DBSettings(BaseSettings): ...
Settings 聚合 db: DBSettings = DBSettings()
```

**问题**：
- 已有 review X-3 决议"`app/config.py` 末尾 `settings = Settings()` 暴露全局单例"
- M1 Task 1 没落实这行
- M1 集成测试 `test_m1_schema_migration.py` 用 `subprocess alembic upgrade head`——alembic 进程**重新 import** `app.config`，不会复用 FastAPI 进程的单例
- 解决：env.py 也 `from app.config import settings` + `config.set_main_option("sqlalchemy.url", settings.db.database_url)`（P0-1 修法已含）

**修改**：Task 1 GREEN 段末尾补：
```python
# app/config.py 文件末尾
settings = Settings()  # 全局单例
```

**已有 review**：X-3 / M0 review P1-9 已列。

---

### P1-18 · 缺 `postgresql_concurrently=True` 选项（生产加索引）

**位置**：M1 plan 整篇

**问题**：
- `op.create_index(...)` 默认**非 concurrently**——会锁表
- 4 表的索引创建在 dev 环境（空表）瞬间完成，但生产环境 users 表 1M+ rows 时会锁几分钟
- M12 hardening 切 prod 前必改

**修改**（env.py 显式声明 + migration 文件用 op.create_index(..., postgresql_concurrently=True)）：
```python
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=False,  # PG 用 False，SQLite 才用 True
    )
```

并在 migration 0001 里所有 `op.create_index` 改 `postgresql_concurrently=True`。

**新发现**。

---

### P1-19 · 缺 `users.username` citext / 大小写处理决策

**位置**：M1 §4 users 表 L102
```
| `username` | `VARCHAR(64)` | UNIQUE, NOT NULL | 用户名 |
```

**问题**：
- `VARCHAR(64)` 默认大小写敏感——`Alice` 和 `alice` 视为不同
- 实际 UX 通常希望"大小写不敏感唯一"
- 方案 A：装 `citext` 扩展，列改 `CITEXT`
- 方案 B：存时统一 `username.lower()`，unique 索引
- 方案 C：保持现状，UX 警告

**修改**：
- 风险表补：`username 大小写` | 风险：Alice/alice 双注册 | 缓解：M2 业务层 `username = username.lower().strip()`，UNIQUE 索引实际是 case-insensitive
- 或：装 citext 扩展 + M0 init.sql 补 `CREATE EXTENSION IF NOT EXISTS citext;`

**新发现**。

---

## P2 · 优化

### P2-1 · 缺 `app/configs/` 拆分决策（X-1 待落地）

**位置**：M1 Files 表 + 修订记录

**问题**：
- 已有 review X-1 决议"M0 直接拆 `app/configs/` 子目录"
- M1 跟着在 M0 拆好后只追加 `db.py` 文件即可
- M1 plan 当前描述的是"M0 已有 app/config.py，M1 追加 DBSettings"——**没意识到 X-1 落地后会变成子目录**

**修改**：
- Files 表"修改"段改：`app/configs/db.py`（新建子目录文件）
- 跨 M 协调段加"等待 X-1 决议后再定"

**已有 review**：X-1 已列。

---

### P2-2 · 缺 M1 plan 头部"范本目的"段

**位置**：M1 plan L1-7

**问题**：
- M3 范本 L8 有"`> 范本目的：给 M0/M1/M2/M4–M12 提供"单里程碑"计划的结构样板`"
- M1 plan 头部**没**这行
- M0 review P2-2 提了 M0 缺，M1 同样缺

**修改**：M1 plan L1-7 末尾加：
```
> 范本目的：M1 是 RAG V1 路线第二个 plan，给 M2/M4-M12 提供"数据层"前置定义
```

**新发现**（M0 review P2-2 已类比）。

---

### P2-3 · 缺 `.env.example` 完整内容（M1 范围）

**位置**：M1 Task 6 GREEN 段 L339
```
.env.example 追加 DATABASE_URL=postgresql+asyncpg://rag_app:rag_app_password@postgres:5432/rag
```

**问题**：
- 只追加 1 行，**没说**前面 M0 加的 `POSTGRES_PASSWORD` 等是否要在 .env.example 显式声明
- 新人 copy `.env.example` → `.env` 时，`rag_app_password` 与 init.sql 不一致会连不上
- 缺 1 行注释：`# 此处密码必须与 infra/init.sql 的 POSTGRES_PASSWORD 一致`

**修改**：
```
# DB
DATABASE_URL=postgresql+asyncpg://rag_app:rag_app_password@postgres:5432/rag
# 注意：rag_app / rag_app_password 必须与 infra/init.sql 的 POSTGRES_USER / POSTGRES_PASSWORD 一致
```

**新发现**。

---

### P2-4 · 缺 `users.failed_login_attempts` / `locked_until` 字段（M2 防爆破用）

**位置**：M1 §4 users 表

**问题**：
- M2 auth 业务做"连续 5 次密码错锁 15 分钟"是基本防爆破
- 字段在 M2 加要做 migration；M1 加零成本

**修改**：
```python
failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**新发现**。

---

### P2-5 · 缺 `ingest_jobs.retry_count` / `next_retry_at` 字段（M4-M6 重试用）

**位置**：M1 §4 ingest_jobs 表

**问题**：
- M4 ingest pipeline TEI/Confluence 失败要重试（spec §5 错误矩阵：TEI 指数退避 3 次，Confluence 429 token bucket）
- 没 retry_count 字段，每次重试要新建 ingest_job 记录——表会爆
- M2 实施时建议先预留

**修改**：
```python
retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**新发现**。

---

### P2-6 · 缺 `auth_sessions.ip_address` / `user_agent` 字段（M2 异常登录告警用）

**位置**：M1 §4 auth_sessions 表

**问题**：
- M12 hardening 异常登录告警要"陌生 IP 登录"——没存 ip 就没法分析
- M1 加零成本，nullable

**修改**：
```python
ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)  # PG 原生 INET
user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
```

**新发现**。

---

### P2-7 · 缺 `chat_sessions.metadata` JSONB 字段（M7 graph 节点扩展用）

**位置**：M1 §4 chat_sessions 表

**问题**：
- M7 graph node 想存"会话配置 / model preference / 提示词版本"等元数据
- 没 metadata 字段就要么新加表，要么塞 title 里——都不优雅

**修改**：
```python
session_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
```

**新发现**。

---

### P2-8 · 缺 4 表的 `idempotency_key` 通用字段（API 重试用）

**位置**：M1 plan 整篇

**问题**：
- M8 API 客户端重试会"重复创建 chat_session" / "重复创建 ingest_job"
- 当前靠 payload_hash 兜 ingest_job，chat_session 没幂等键
- 通用做法：每表加 `idempotency_key VARCHAR(64) UNIQUE NULL` 字段

**修改**（4 表都加）：
```python
idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
```

**新发现**。

---

### P2-9 · `TimestampMixin` 没继承 `MappedAsDataclass` 简化 boilerplate

**位置**：M1 Task 2 GREEN 段 L248

**问题**：
- SQLAlchemy 2.0 支持 `class User(Base, TimestampMixin, MappedAsDataclass)` 自动生成 `__init__`
- 4 个 ORM 类 boilerplate 减半

**修改**：plan 推荐 `MappedAsDataclass` 模式

**新发现**。

---

## 与已有 review 交叉验证

|| ID | 已有 review 项 | M1 plan 是否已改 | 本报告 |
||----|--------------|--------------|-------|
|| P0-4 | alembic.ini `%(VAR)s` 占位符语法错 | ❌ 未改 | P0-1 |
|| P0-5 | sqlite 测 JSONB 等 PG-only 类型 | ❌ 未改 | P0-2 |
|| P0-6 | aiosqlite 缺依赖 | ❌ 未改 | P0-3 |
|| P0-7 | test_migration_has_all_tables 脆 | ❌ 未改 | P0-4（+ 新发现命名规范不一致） |
|| P1-4 | TimestampMixin.updated_at onupdate 限制 | ❌ 未改 | P0-7 |
|| P1-5 | ingest_jobs.payload_hash 缺 UNIQUE | ❌ 未改 | P1-1 |
|| P1-6 | chat_sessions 缺复合索引 | ❌ 未改 | P1-2 |
|| P2-7 | app/db/__init__.py 暴露不一致 | ❌ 未改 | P0-5 |
|| X-1 | app/config.py 拆分 | ❌ 未改 | P2-1 |
|| X-2 | pytest.ini rootdir | ❌ 未改 | P1-16 |
|| X-3 | settings 全局单例 | ❌ 未改 | P1-17 |
|| M0 P1-9 | config.py 末尾 settings = Settings() 单例 | ❌ 未改 | P1-17 |

**结论**：M1 范围内已有 review 列出的 12 项，**全部 ❌ 未改**。plan 作者需在动手前批量更新。

---

## 你发现的新问题（已有 review 未列）

合计 **15 个新问题**：

1. **P0-4 后半段** · alembic 默认 hex revision id 与 plan 写 `0001_` 前缀不一致
2. **P0-6** · alembic env.py 缺 `run_async_migrations()` 完整模板
3. **P1-3** · 4 表缺 `created_by` / `updated_by` 审计字段（V2 多租户必加）
4. **P1-4** · users 缺 `email` + `email_verified_at`（M12 密码重置必加）
5. **P1-5** · users 缺 `deleted_at` 软删除字段（与 `is_active` 语义不同）
6. **P1-6** · chat_sessions 缺 `last_message_at`（M8 API 排序用）
7. **P1-7** · FK 列 + 查询列缺索引（PG 不会自动给 FK 建索引）
8. **P1-8** · 缺 `app/auth/password_validator.py` 函数（M2 必用）
9. **P1-9** · 缺 `downgrade()` 实现要求
10. **P1-10** · 缺 enum vs VARCHAR+CHECK 的设计决策记录
11. **P1-11** · 缺 connection pool recycle + pre_ping（防 stale connection）
12. **P1-12** · 缺 asyncpg + pgbouncer 兼容配置（statement_cache_size=0）
13. **P1-13** · 缺 DB migration 并发锁（pg_advisory_lock）
14. **P1-14** · 缺 `__table_args__` 集中声明索引
15. **P1-15** · 缺 server-side default 显式声明（vs client-side timezone 漂移）
16. **P1-18** · 缺 `postgresql_concurrently=True` 选项（生产加索引）
17. **P1-19** · 缺 `users.username` citext / 大小写处理决策
18. **P2-2** · 缺 M1 plan 头部"范本目的"段
19. **P2-3** · 缺 `.env.example` 完整内容 + 密码一致性注释
20. **P2-4** · 缺 `users.failed_login_attempts` / `locked_until`（M2 防爆破）
21. **P2-5** · 缺 `ingest_jobs.retry_count` / `next_retry_at`（M4-M6 重试）
22. **P2-6** · 缺 `auth_sessions.ip_address` / `user_agent`（M12 异常登录告警）
23. **P2-7** · 缺 `chat_sessions.metadata` JSONB（M7 graph 扩展）
24. **P2-8** · 缺 4 表的 `idempotency_key` 字段（API 重试幂等）
25. **P2-9** · 缺 `MappedAsDataclass` boilerplate 简化

---

## 落地建议

按 P0 → P1 → P2 优先级：

### 第一波（本轮必改，7 项 P0）
1. P0-1 alembic.ini 留空 + env.py 注入
2. P0-2 删 sqlite 单测，走 testcontainers
3. P0-3 dev 依赖加 `pytest-postgresql` + `testcontainers[postgresql]`
4. P0-4 删 `test_migration_has_all_tables` + 改 file_template 让 revision id 可控
5. P0-5 统一 `__init__.py` 暴露 `engine` / `async_session` / `async_session_factory` / `get_session` / `AsyncSession`
6. P0-6 env.py 给完整 `run_async_migrations` 模板
7. P0-7 TimestampMixin docstring 显式写 onupdate 限制 + M4 bulk update caveat

### 第二波（重要，19 项 P1）
8. P1-1 ingest_jobs.payload_hash 加 UNIQUE
9. P1-2 chat_sessions 索引加 is_active
10. P1-3 4 表加 created_by / updated_by
11. P1-4 users 加 email
12. P1-5 users 加 deleted_at + partial unique index
13. P1-6 chat_sessions 加 last_message_at
14. P1-7 FK 列 + 状态/时间列全加索引
15. P1-8 app/auth/password_validator.py + 单元测试
16. P1-9 显式写 downgrade() + RED 测试
17. P1-10 风险表补 enum vs VARCHAR+CHECK 选择
18. P1-11 pool_recycle=1800 + pool_pre_ping=True
19. P1-12 connect_args statement_cache_size=0
20. P1-13 env.py 加 pg_advisory_lock
21. P1-14 __table_args__ 集中声明索引
22. P1-15 server_default=func.now() 统一
23. P1-16 pyproject.toml 加 [tool.pytest.ini_options]
24. P1-17 app/config.py 末尾 `settings = Settings()` 单例
25. P1-18 op.create_index postgresql_concurrently=True
26. P1-19 users.username citext 决策（选 M2 业务 lower() 方案）

### 第三波（优化，9 项 P2）
27-35. P2-1 ~ P2-9

### 跨 M 协调（M1 改完后通知）
- 通知 M2：users 表已有 `email` / `deleted_at` / `failed_login_attempts` / `locked_until` 字段；`app/auth/password_validator.py` 已存在
- 通知 M4：ingest_jobs 表已有 `retry_count` / `next_retry_at` / `metadata` / `idempotency_key`；bulk update 时显式传 `updated_at=func.now()`
- 通知 M7：chat_sessions 表已有 `last_message_at` / `metadata` JSONB 字段
- 通知 M8：chat_sessions 索引已是 `(user_id, is_active, updated_at DESC)` + `last_message_at`
- 通知 M12：auth_sessions 表已有 `ip_address` / `user_agent`；prod 部署时 connection_args 已含 `statement_cache_size=0` 兼容 pgbouncer

### 估时修正
- M1 整体估时从 **3d → 5d**（P0 修补 1d + P1 实施 1d + 集成测试 1d + buffer 1d）

### 等待决策
- X-1 `app/config.py` 拆分 `configs/` 子目录是否在 M1 阶段就动手（推荐是，alembic env.py 引用 `app.configs.db` 比 `app.config.db` 更清晰）
- P1-10 enum vs VARCHAR+CHECK 是否要在 M1 阶段换 enum（推荐不换，autogenerate 对 enum 支持不完善）

---

## 状态

- **不可动手**：P0-1 ~ P0-7 共 7 项必改
- **建议本轮改**：P1-1 ~ P1-19 共 19 项
- **可下轮改**：P2-1 ~ P2-9 共 9 项
- **新问题合计**：25 个（已有 review 未列），覆盖 DDL 字段、索引、alembic 工程化、连接池配置、跨 M 协调
- **已有 review 验证**：M1 范围内 12 项，全部 ❌ 未改

M1 plan **结构齐、DDL 主体对，但 alembic 工程化与生产化考虑严重不足，schema 层就缺了 M2/M4/M7/M8/M12 多个后续 M 必用字段**。修完 P0 + P1 前 7 项可动手，后 12 项 P1 强烈建议同轮修完以避免 schema migration 回滚成本。
