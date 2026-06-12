# M1 Plan · Schema 层（Alembic 迁移 + 4 张核心表 + Pydantic Settings 集成）

> 所属：RAG V1 M0–M12 实施路线 · 第 1 步
> 范本目的：M1 是 RAG V1 路线第二个 plan，给 M2/M4-M12 提供"数据层"前置定义（M0 review P2-2 同源）
> 代码根目录：`apps/rag_v1/`
> 基线 spec：[V1 Scope §7 M1 Schema](../specs/2026-06-10-rag-v1-scope.md#7-v1-milestonesm0m12) · [决策总表 #13/#14](../specs/2026-06-10-rag-v1-scope.md#0-决策总表)
> 脑暴基线：`session 20260608_145040_7202e5` msg 193 §1.7（用户系统表结构）+ msg 195 §2（否决 OpenSearch checkpointer，确认 Postgres 为 checkpointer 存储）
> 估时：3 个工作日

---

## Goal

把 v1-scope 决策 #13（Postgres 用户系统）和 #14（鉴权依赖的表结构）落成可执行数据库层：

1. Alembic 初始化 + 4 张核心表（`users`, `auth_sessions`, `chat_sessions`, `ingest_jobs`），含完整列定义、约束、索引
2. SQLAlchemy 2.0 asyncio ORM models + async session factory
3. Pydantic Settings 集成（复用 M0 config.py，补充 DB 相关配置聚合）
4. 单元测试验证 model 定义、alembic 配置可达性
5. 集成测试验证：`alembic upgrade head` → 4 表存在 → INSERT + SELECT 各表 works

**不包含**（其他 M 负责）：M2 auth 业务逻辑（密码 hash / token 生成）、M7 PostgresCheckpointer（不同表结构）、M4–M6 ingest job 状态机逻辑

---

## Architecture

### 仓库布局（apps/rag_v1/）

```
apps/
└── rag_v1/                          # RAG V1 项目根
    ├── infra/                       # 基础设施配置（M0 已建）
    │   ├── docker-compose.yml       # M0 已建
    │   └── init.sql                 # M0 已建
    │
    ├── app/                         # 应用代码
    │   ├── __init__.py
    │   ├── config.py                # M0 已有，M1 追加 DB 子配置
    │   ├── db/                      # 数据层（M1 新增）
    │   │   ├── __init__.py
    │   │   ├── models.py            # SQLAlchemy ORM — 4 张表 + 3 个 enum
    │   │   ├── session.py           # async engine + async_session_factory
    │   │   └── base.py              # DeclarativeBase + 公用列 Mixin
    │   └── ...
    │
    ├── alembic.ini                  # Alembic 配置文件（M1 新增）
    ├── alembic/                     # Alembic 迁移目录（M1 新增）
    │   ├── env.py                   # 环境加载 + SQLAlchemy metadata
    │   ├── script.py.mako           # 迁移模板
    │   └── versions/
    │       └── 0001_initial_schema.py  # 初始迁移：4 张表
    │
    ├── tests/                       # 测试
    │   ├── __init__.py
    │   ├── unit/
    │   │   ├── __init__.py
    │   │   ├── test_config.py       # M0 已有，M1 追加 DB 配置测试
    │   │   ├── test_models.py       # ORM 模型定义 + 约束测试
    │   │   └── test_config_alembic.py  # Alembic 配置可达性测试
    │   └── integration/
    │       ├── __init__.py
    │       └── test_m1_schema_migration.py  # 完整迁移 + CRUD 验证
    │
    ├── pyproject.toml               # M0 已有，M1 追加 4 个 DB 包
    ├── .env.example                 # M0 已有，M1 追加 DB 连接串
    └── README.md                    # M0 已有，M1 追加迁移步骤
```

### M1 模块树

```
apps/rag_v1/
├── app/
│   ├── auth/                       # 鉴权相关（M1 新增 P1-8，定 password_validator 签名供 M2 接）
│   │   ├── __init__.py             # 包标识
│   │   └── password_validator.py   # validate_password(pw: str) -> None  # raise ValueError
│   └── db/
│       ├── __init__.py             暴露 engine / async_session / async_session_factory / get_session / AsyncSession
│       ├── base.py                 DeclarativeBase + TimestampMixin
│       ├── models.py               User, AuthSession, ChatSession, IngestJob
│       └── session.py              async_engine / async_session_factory / get_session dependency
│
├── alembic.ini                     sqlalchemy.url = postgresql+asyncpg://...
├── alembic/
│   ├── env.py                      加载 app.db.base 的 metadata
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py  4 张表 CREATE TABLE
│
└── tests/
    ├── unit/
    │   ├── test_models.py          ORM 字段类型 / 约束 / 关系
    │   └── test_config_alembic.py  alembic.ini 存在 / env.py 可导入
    └── integration/
        └── test_m1_schema_migration.py  upgrade → 表存在 → INSERT → SELECT
```

### 4 张表结构定义

#### `users`

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | `UUID` | PK, default=uuid4 | 主键 |
| `username` | `VARCHAR(64)` | UNIQUE, NOT NULL | 用户名（P1-19：M2 业务层 `username = username.lower().strip()` 后入库，UNIQUE 索引等效 case-insensitive；不装 citext 扩展） |
| `password_hash` | `VARCHAR(255)` | NOT NULL | argon2id hash |
| `email` | `VARCHAR(255)` | UNIQUE, NULLABLE | P1-4 邮箱（M12 hardening 密码重置/找回/异常登录告警必加，nullable 不影响 V1 注册） |
| `email_verified_at` | `TIMESTAMPTZ` | NULLABLE | P1-4 邮箱验证时间 |
| `display_name` | `VARCHAR(128)` | NULLABLE | 显示名 |
| `is_active` | `BOOLEAN` | DEFAULT TRUE | 软禁用 |
| `last_login_at` | `TIMESTAMPTZ` | NULLABLE | 最后登录时间 |
| `idempotency_key` | `VARCHAR(64)` | UNIQUE, NULLABLE | P2-8 通用幂等键（M8 API 客户端重试用） |
| `failed_login_attempts` | `INTEGER` | NOT NULL, DEFAULT 0 | P2-4 连续登录失败计数（M2 防爆破：5 次错锁 15 分钟） |
| `locked_until` | `TIMESTAMPTZ` | NULLABLE | P2-4 锁定截止时间（NULL=未锁） |
| `deleted_at` | `TIMESTAMPTZ` | NULLABLE, INDEX | P1-5 软删除（与 `is_active` 语义不同：is_active=管理员禁用；deleted_at=用户自删，30d 硬删）。**NP-2 r2 已修**：partial unique index `CREATE UNIQUE INDEX uq_users_username_active ON users(username) WHERE deleted_at IS NULL` —— username 复用（已删用户 username 可被新用户用），但活用户内仍 UNIQUE。ORM：`__table_args__ = (Index("uq_users_username_active", "username", postgresql_where=text("deleted_at IS NULL"), unique=True),)` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, auto-update | 更新时间 |
| `created_by` | `UUID` | NULLABLE, FK→users.id | P1-3 审计（V2 多租户+admin 后台必加） |
| `updated_by` | `UUID` | NULLABLE, FK→users.id | P1-3 审计（V2 多租户+admin 后台必加） |

#### `auth_sessions`

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | `UUID` | PK, default=uuid4 | 主键 |
| `user_id` | `UUID` | FK→users.id, NOT NULL | 用户 |
| `token_hash` | `VARCHAR(64)` | UNIQUE, NOT NULL | SHA-256(token) |
| `expires_at_sliding` | `TIMESTAMPTZ` | NOT NULL | 7d 滑上限 |
| `expires_at_hard` | `TIMESTAMPTZ` | NOT NULL | 30d 硬上限 |
| `last_used_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() | 最后使用时间 |
| `idempotency_key` | `VARCHAR(64)` | UNIQUE, NULLABLE | P2-8 通用幂等键 |
| `ip_address` | `INET` | NULLABLE | P2-6 登录 IP（M12 异常登录告警"陌生 IP"必加；PG 原生 INET 类型） |
| `user_agent` | `VARCHAR(512)` | NULLABLE | P2-6 浏览器 UA |
| `is_revoked` | `BOOLEAN` | NOT NULL, DEFAULT FALSE, **INDEX** | **NP-1 r2 已修**：M2 plan L125/L824 强依赖，主动撤销 / admin 强制下线；M2 logout / login 软吊销走 `update is_revoked=TRUE`（r1 review 时该字段在 DDL 段漏，已补） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() | 创建时间 |
| `created_by` | `UUID` | NULLABLE, FK→users.id | P1-3 审计（V2 必加，M2 可填注册者） |
| `updated_by` | `UUID` | NULLABLE, FK→users.id | P1-3 审计 |

#### `chat_sessions`

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | `UUID` | PK, default=uuid4 | 主键 |
| `user_id` | `UUID` | FK→users.id, NOT NULL | 用户 |
| `thread_id` | `UUID` | UNIQUE, NOT NULL | LangGraph thread_id |
| `title` | `VARCHAR(255)` | NULLABLE | 会话标题 |
| `is_active` | `BOOLEAN` | DEFAULT TRUE | 软删除 |
| `idempotency_key` | `VARCHAR(64)` | UNIQUE, NULLABLE | P2-8 通用幂等键 |
| `last_message_at` | `TIMESTAMPTZ` | NULLABLE, INDEX | P1-6 最后消息时间（M8 API 列表按此排序；M7 graph save_memory 时显式更新） |
| `session_metadata` | `JSONB` | NULLABLE, DEFAULT '{}' | P2-7 会话元数据（M7 graph 节点扩展：model preference / 提示词版本 / 会话配置） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, auto-update | 更新时间 |
| `created_by` | `UUID` | NULLABLE, FK→users.id | P1-3 审计 |
| `updated_by` | `UUID` | NULLABLE, FK→users.id | P1-3 审计 |

Indexes: `(user_id, is_active, updated_at DESC)` — P1-2：M8 API `GET /api/sessions` 加 `WHERE is_active=TRUE` 走 index scan；`thread_id` 上 UNIQUE INDEX（M7 graph 跨 M 依赖）

#### `ingest_jobs`

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | `UUID` | PK, default=uuid4 | 主键 |
| `user_id` | `UUID` | FK→users.id, NOT NULL | 用户 |
| `source` | `VARCHAR(16)` | NOT NULL, CHECK IN file/url/confluence | 数据源 |
| `status` | `VARCHAR(16)` | NOT NULL, DEFAULT pending | pending/running/indexed/failed |
| `payload_hash` | `VARCHAR(64)` | NOT NULL, **UNIQUE INDEX uq_ingest_jobs_payload_hash** | SHA-256(source + payload)；P1-1：UNIQUE 是幂等键，M4 用 `ON CONFLICT (payload_hash) DO NOTHING` |
| `payload` | `JSONB` | NULLABLE | 原始请求 payload |
| `chunks_count` | `INTEGER` | DEFAULT 0 | 已索引 chunk 数 |
| `error` | `TEXT` | NULLABLE | 失败原因 |
| `idempotency_key` | `VARCHAR(64)` | UNIQUE, NULLABLE | P2-8 通用幂等键 |
| `retry_count` | `INTEGER` | NOT NULL, DEFAULT 0 | P2-5 已重试次数 |
| `max_retries` | `INTEGER` | NOT NULL, DEFAULT 3 | P2-5 最大重试次数 |
| `next_retry_at` | `TIMESTAMPTZ` | NULLABLE, INDEX | P2-5 下次重试时间（指数退避） |
| `started_at` | `TIMESTAMPTZ` | NULLABLE | 开始时间 |
| `completed_at` | `TIMESTAMPTZ` | NULLABLE | 完成时间 |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, auto-update | 更新时间 |
| `created_by` | `UUID` | NULLABLE, FK→users.id | P1-3 审计（M4 创建 ingest 任务时填 user_id） |
| `updated_by` | `UUID` | NULLABLE, FK→users.id | P1-3 审计 |

Indexes (P1-7：PG 不会自动给 FK 建索引，必须显式)：
- `ix_auth_sessions_user_id` ON `auth_sessions(user_id)`
- `ix_auth_sessions_expires_at_hard` ON `auth_sessions(expires_at_hard)` — **NP-3 r2 已修**：M2 cleanup job `DELETE FROM auth_sessions WHERE expires_at_hard < NOW()`（r1 review 漏加索引，1M+ token 表全表扫）
- `ix_chat_sessions_user_id` ON `chat_sessions(user_id)`
- `ix_ingest_jobs_user_id_created_at` ON `ingest_jobs(user_id, created_at)` — 按用户查历史
- `ix_ingest_jobs_status_created_at` ON `ingest_jobs(status, created_at)` — M4 worker 轮询 `WHERE status='pending' ORDER BY created_at LIMIT 10`
- `ix_ingest_jobs_completed_at` ON `ingest_jobs(completed_at)` — M11 RAGAS 评测"最近 7 天 ingest 成功率"

**P1-18**：所有 `op.create_index(...)` 用 `postgresql_concurrently=True`，避免 prod users 表 1M+ rows 时锁表几分钟。空表 dev 阶段无差别。

**P1-14 ORM `__table_args__` 集中声明示例**：
```python
class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint("thread_id", name="uq_chat_sessions_thread_id"),  # M7 跨 M
        Index("ix_chat_sessions_user_active_updated", "user_id", "is_active", "updated_at"),
        Index("ix_chat_sessions_last_message_at", "last_message_at"),
    )
```
所有 CHECK / UNIQUE / INDEX 都集中在 `__table_args__`，autogenerate 行为可预测。

### M1 与其他 M 的契约边界

| 调用方 | 用的接口 | 备注 |
|--------|---------|------|
| M2 auth | `User` / `AuthSession` model + `async_session` | M2 业务逻辑直接 import models + session |
| M7 graph | `chat_sessions` 表（thread_id 关联） | M7 PostgresCheckpointer 读取 thread_id |
| M4–M6 ingest | `IngestJob` model | M4 创建/更新 ingest job 记录 |
| M8 API | `/api/sessions` 查 `chat_sessions` 表 | M8 路由通过 session.py 连 DB |

---

## Tech Stack

| 层 | 选型 | 版本（精确） |
|----|------|------------|
| ORM | `sqlalchemy[asyncio]` | `>=2.0.30,<3` |
| Migration | `alembic` | `>=1.13,<2` |
| Async PG 驱动 | `asyncpg` | `>=0.29,<1` |
| 同步 PG 驱动 | `psycopg2-binary` | `>=2.9,<3` |
| 配置 | `pydantic-settings` | `>=2.3,<3` |
| 数据校验 | `pydantic` | `>=2.7,<3` |
| Web 框架 | `fastapi` | `>=0.115,<1` |
| 测试 | `pytest` / `pytest-asyncio` | — |

**P1-10 设计决策**：不引入 `sqlalchemy Enum` 类型，`source` / `status` 用 `String + CheckConstraint`。
- 改值只需 `ALTER TABLE ... DROP/ADD CONSTRAINT`，app 端 Python enum 同步
- 比 PG 原生 `CREATE TYPE ... AS ENUM` 加 value 简单（PG 9.6+ `ADD VALUE` 还在事务内限制）

**关键导入路径**：

```python
# ORM 基类
from app.db.base import DeclarativeBase, TimestampMixin

# Model 定义
from app.db.models import User, AuthSession, ChatSession, IngestJob

# Async session
from app.db.session import async_session, get_session, engine

# Alembic env.py
from app.db.base import DeclarativeBase  # target_metadata = DeclarativeBase.metadata
```

**Python 导入规则**（从 `apps/rag_v1/` 内部）：
- `app.db.*` —— `app` 是 `apps/rag_v1/app/`
- `tests.unit.test_models` —— 跑测试时 `cd apps/rag_v1 && pytest`

---

## Files

**新增**（5 个源文件 + 4 个迁移文件 + 4 个测试文件）：

| 路径（相对 `apps/rag_v1/`） | 作用 |
|------|------|
|| `app/db/__init__.py` | 暴露 `engine` / `async_session` / `async_session_factory` / `get_session` / `AsyncSession`（P0-5 统一：Files 表 L207 与 REFACTOR L279 原本矛盾，本次补齐 engine） |
| `app/db/base.py` | `DeclarativeBase` + `TimestampMixin`（`created_at`, `updated_at`） |
| `app/db/models.py` | 4 个 ORM 类：`User`, `AuthSession`, `ChatSession`, `IngestJob` |
| `app/db/session.py` | `async_engine` / `async_session_factory` / `get_session` async generator |
| `app/auth/__init__.py` | P1-8 鉴权包标识 |
| `app/auth/password_validator.py` | P1-8 `validate_password(pw: str) -> None` 抛 ValueError（最小长度 12 / 大小写 / 数字 / 常见密码 blacklist hook） |
| `alembic.ini` | 配置 `sqlalchemy.url` 模板 |
| `alembic/env.py` | 加载 `app.db.base` 的 `metadata` + async migration runner |
| `alembic/script.py.mako` | 模板 |
| `alembic/versions/0001_initial_schema.py` | 4 张表 CREATE TABLE |
| `tests/unit/test_models.py` | ORM 字段类型 / 约束 / 关系测试 |
| `tests/unit/test_config_alembic.py` | alembic env 导入 + ini 配置可达性 |
| `tests/integration/test_m1_schema_migration.py` | upgrade → 表存在 → INSERT → SELECT |

**P1-8 追加**：
- `tests/unit/test_password_validator.py` | 弱密码（短/纯数字/常见词） / 强密码 / 边界值（M2 直接复用）

**修改**：
- `app/config.py` → **P2-1 等待 X-1 决议**：若 X-1 决定 M0 拆 `app/configs/` 子目录，则改为 `app/configs/db.py` 新建（alembic env.py 引用 `app.configs.db` 比 `app.config.db` 更清晰）；M1 阶段先按 `app/config.py` 推进，X-1 落地后切到子目录
- 追加 `DBSettings`（`database_url: str` / `pool_size: int` / `max_overflow: int` / `echo: bool`）
- `pyproject.toml`：追加 4 个新直接依赖（`sqlalchemy[asyncio]` / `alembic` / `asyncpg` / `psycopg2-binary`）
- `.env.example`：追加 `DATABASE_URL=postgresql+asyncpg://rag_app:rag_app_password@postgres:5432/rag`

**不修改**：`infra/docker-compose.yml`（M0 已配 Postgres）、`README.md`（M1 追加迁移步骤即可）

---

## Tasks（2-5 分钟/step 粒度）

### Task 1：app/config.py DB 配置追加

**RED** · `tests/unit/test_config.py::test_db_settings_loads`（追加）
- mock `DATABASE_URL=postgresql+asyncpg://u:p@h:5432/db` → 断言 `settings.db.database_url` 正确解析
- 跑测试 → 失败（`DBSettings` 尚未定义）

**GREEN** · 改 `app/config.py`：
- 新增 `class DBSettings(BaseSettings)`：`database_url: str` / `pool_size: int = 10` / `max_overflow: int = 20` / `echo: bool = False`
- `Settings` 聚合 `db: DBSettings = DBSettings()`
- **P1-17 文件末尾追加全局单例**（X-3 决议，M0 review P1-9 同源）：
  ```python
  settings = Settings()  # 全局单例，env.py / session.py / 业务层统一 from app.config import settings
  ```

### Task 2：SQLAlchemy base + models

**RED** · `tests/unit/test_models.py::test_user_model_has_columns`
- 用 `pytest-postgresql` 启临时 PG → `Base.metadata.create_all(...)` → 断言 `User` 有 `id` / `username` / `password_hash` / `created_at` / `updated_at` 列
- 断言 `username` 列 `unique=True`
- 跑测试 → 失败（models.py 不存在）
- **不用 sqlite**：JSONB（`ingest_jobs.payload`）/ INET / partial unique index 均为 PG-only 类型，sqlite 测会"假绿"（自动降级为 TEXT，PG 上一迁移就挂）

**GREEN** · 实现 `app/db/base.py` + `app/db/models.py`：
- `class TimestampMixin`（P0-7 docstring 显式写 onupdate 限制 + M4 bulk update caveat）：
  ```python
  class TimestampMixin:
      """updated_at only auto-updates on ORM-level dirty detection
      (session.execute(update(Model)) with dirty tracking, or session.add()).

      For bulk update via session.execute(update(...).values(...)), updated_at
      will NOT auto-update — you must pass updated_at=func.now() explicitly.
      See M4 ingest_jobs worker (UPDATE ingest_jobs SET status=..., chunks_count=...).
      """
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          server_default=func.now(),  # P1-15 显式 server-side
          nullable=False,
      )
      updated_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          server_default=func.now(),
          onupdate=func.now(),  # 仅 ORM dirty 时触发，bulk update 无效
          nullable=False,
      )
  ```
- `class DeclarativeBase(Base)`：SQLAlchemy 2.0 `DeclarativeBase`
- 4 个 ORM 类如上 §4 张表结构定义
- **P1-15 约定**：全部时间字段用 `TIMESTAMPTZ` + `server_default=func.now()`，**禁止** `default=datetime.now`（client-side 多进程时区漂移）
- **P2-9 推荐 `MappedAsDataclass` 模式**（SQLAlchemy 2.0 原生）简化 boilerplate：
  ```python
  from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

  class Base(DeclarativeBase, MappedAsDataclass):
      pass

  class User(Base, TimestampMixin):  # 自动生成 __init__(id, username, password_hash, ...)
      __tablename__ = "users"
      id: Mapped[uuid.UUID] = mapped_column(default_factory=uuid4, primary_key=True)
      username: Mapped[str] = mapped_column(String(64), unique=True)
      # ... 不再手写 __init__
  ```

**RED** · `test_auth_session_has_user_relationship`
- 断言 `AuthSession.user` 类型是 `Mapped[User]`→ 断言 `back_populates="auth_sessions"`
- 跑测试 → 失败

**GREEN** · 加 `User.auth_sessions = relationship("AuthSession", back_populates="user")`

**RED** · `test_ingest_job_status_enum_default`
- `IngestJob(status="").status` → 断言 default 是 "pending"

**GREEN** · `server_default="'pending'"` + Column-level CHECK

### Task 3：异步 session factory

**RED** · `tests/unit/test_models.py::test_async_session_creates_tables`
- 用 `async_session` 建表 → 断言无抛错
- 跑测试 → 失败（session.py 不存在）

**GREEN** · 实现 `app/db/session.py`（P1-11 + P1-12）：
- `engine = create_async_engine(settings.db.database_url, pool_size=10, max_overflow=20, pool_recycle=1800, pool_pre_ping=True, connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}, echo=settings.db.echo)`
- 依据：V1 单副本 30 连接，PG 默认 `max_connections=100` 占 30%，预留 70 给 Langfuse / LangGraph checkpointer / M11 RAGAS / 调试客户端；`pool_recycle=1800` 防 stale connection；`pool_pre_ping=True` 防 PG 端断连；`statement_cache_size=0` 兼容 pgbouncer transaction pool
- `async_session = async_sessionmaker(engine, expire_on_commit=False)`
- `async def get_session(): async with async_session() as s: yield s`

**RED** · `test_get_session_yields_working_session`
- `async with async_session() as s: result = await s.execute(text("SELECT 1"))` → 断言 1

**GREEN** · 确保 session factory 可连接（需 M0 postgres 容器运行；单测走 `pytest-postgresql` 起临时 PG，不再用 sqlite+aiosqlite）

**REFACTOR** · 把 `engine` / `async_session` / `async_session_factory` 声明移到 `__init__.py` 提供 `__all__`（P0-5：统一暴露面）

```python
# app/db/__init__.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session, async_session_factory, engine, get_session

__all__ = ["AsyncSession", "async_session", "async_session_factory", "engine", "get_session"]
```

### Task 4：Alembic 初始化 + migration 脚本

**RED** · `tests/unit/test_config_alembic.py::test_alembic_env_imports`
- 从 `alembic/env.py` 导入 → 断言无 `ImportError` / `ModuleNotFoundError`
- 断言 `target_metadata` 是 `DeclarativeBase.metadata`
- 跑测试 → 失败（env.py 不存在）

**GREEN** · 初始化 Alembic：`cd apps/rag_v1 && alembic init alembic` → 改 `alembic.ini` 中的 `sqlalchemy.url` 模板
- `alembic.ini`：`sqlalchemy.url =`（**留空**，Alembic 1.13+ 弃用 ConfigParser `%(VAR)s` interpolation，URL 在 env.py 注入）
- `alembic.ini` 追加 `file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s` 让初始迁移文件名为 `20260611_2230_initial_schema.py`（与 plan §仓库布局 描述一致）
- `alembic/env.py`：
  - `from app.config import settings` + `config.set_main_option("sqlalchemy.url", settings.db.database_url)` 注入 DSN
  - `import app.db.base` → `target_metadata = app.db.base.DeclarativeBase.metadata`
  - async migration runner：用 `run_async` 模式（Alembic 1.13+ async support，见 P0-6 完整模板）

**GREEN** · 生成初始迁移：`cd apps/rag_v1 && alembic revision --autogenerate -m "initial_schema"`
- 检查生成的 migration 确认 4 张表全部在 `upgrade()` 中
- 手动补 CHECK / INDEX / FK 约束（autogenerate 可能遗漏）
- **手写 `downgrade()`** 删除 4 表 + drop enum（如有）+ drop index（P1-9）

**env.py 完整模板**（P0-6 替换"用 run_async 模式" 1 句话，async migration 需要 `asyncio.run()` + `connection.run_sync()` 包裹）：
```python
# alembic/env.py
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.config import settings
from app.db.base import DeclarativeBase
import app.db.models  # noqa: F401  触发 model 注册

config = context.config
config.set_main_option("sqlalchemy.url", settings.db.database_url)  # P0-1

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = DeclarativeBase.metadata


def do_run_migrations(connection: Connection) -> None:
    # P1-13 并发锁：CI alembic + 容器启动 alembic 不会撞车
    connection.exec_driver_sql("SELECT pg_advisory_lock(0x5241475631)")  # 'RAG_V1' hex
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=False,  # P1-18 PG 用 False
        )
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.exec_driver_sql("SELECT pg_advisory_unlock(0x5241475631)")


async def run_async_migrations() -> None:
    connectable = create_async_engine(settings.db.database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_online()
```

~~**RED** · `test_migration_has_all_tables`~~  → **删除**
- 原计划解析 `0001_initial_schema.py` 断言 4 个 `op.create_table()`——脆（AST 解析对注释/字符串内嵌/换行敏感，且 alembic 默认文件名为 hex revision id `7f8a9b2c3d4e_initial_schema.py`，与 plan 写的 `0001_` 前缀不一致，**永远过不了**）
- 改走 Task 5 集成测试 `test_migrate_up_creates_tables` 验证（`alembic upgrade head` → 查 `information_schema.tables` 断言 4 表存在），覆盖更稳
- alembic `file_template` 在 `alembic.ini` 配为 `%%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s`（见 P0-1）才会产生 `20260611_2230_initial_schema.py`

**RED** · `test_migration_downgrade_works`（P1-9）
- subprocess `alembic upgrade head` → 4 表在 → `alembic downgrade base` → 4 表全没了
- 保证 `downgrade()` 完整：drop 4 表 + drop enum（如有）+ drop index + drop extension（如果 P1-19 装了 citext）

### Task 5：集成测试 —— 真实 PG 迁移 + CRUD

**RED** · `tests/integration/test_m1_schema_migration.py::test_migrate_up_creates_tables`
- subprocess `alembic upgrade head` → 断言 exit_code=0
- async connect to PG → `SELECT table_name FROM information_schema.tables WHERE table_schema='public'` → 断言 4 表存在
- 跑测试 → 失败（PG 未迁移或 env 未配置）

**GREEN** · 确保 `alembic upgrade head` 跑通；修任何 FK / 索引 / 类型错误

**RED** · `test_insert_select_user`
- INSERT User(username="test_user", password_hash="argon2-hash")
- SELECT → 断言 id / username / password_hash / created_at 非空
- 跑测试 → 失败

**GREEN** · 确认 CRUD 可用

**RED** · `test_insert_select_auth_session`
- INSERT User → INSERT AuthSession(user_id=..., token_hash="abc", expires_at_sliding=..., expires_at_hard=...)
- SELECT via `AuthSession.user` relationship → 断言 user.username = "test_user"

**GREEN** · 确认 relationship / FK 可用

**RED** · `test_insert_uniqueness_violation`
- INSERT 同 username 两次 → 断言 IntegrityError 抛

**GREEN** · 确认约束生效

### Task 6：pyproject.toml + .env.example 更新

**GREEN（直接写）**：
- `pyproject.toml` 追加：
  ```toml
  [project.dependencies]
  sqlalchemy[asyncio] = ">=2.0.30,<3"
  alembic = ">=1.13,<2"
  asyncpg = ">=0.29,<1"
  psycopg2-binary = ">=2.9,<3"

  [project.optional-dependencies.dev]
  # 单测用 pytest-postgresql 起临时 PG（不用 sqlite：JSONB/INET/partial index 是 PG-only）
  pytest-postgresql = ">=6.0,<7"
  testcontainers = {extras = ["postgresql"], version = ">=4.0,<5"}

  # P1-16 pytest 配置：X-2 决议
  [tool.pytest.ini_options]
  asyncio_mode = "auto"  # 不加则 async def test_xxx 不会被 pytest-asyncio 识别
  testpaths = ["tests"]
  addopts = "-v --tb=short --strict-markers"
  markers = [
    "require_docker: marks tests as requiring docker compose up",
  ]
  ```
- `.env.example` 追加（P2-3 含密码一致性注释，避免新人 copy 后与 init.sql 不一致）：
  ```bash
  # DB（M1 范围）
  DATABASE_URL=postgresql+asyncpg://rag_app:rag_app_password@postgres:5432/rag
  # 注意：rag_app / rag_app_password 必须与 infra/init.sql 的 POSTGRES_USER / POSTGRES_PASSWORD 一致
  ```

---

## 测试策略

- **M1 单元**：`cd apps/rag_v1 && pytest tests/unit/test_models.py tests/unit/test_config_alembic.py` —— 走 `pytest-postgresql` 临时 PG（**不用 sqlite**：JSONB/INET/partial index 是 PG-only），CI 内 <5s
- **M1 集成**：`cd apps/rag_v1 && pytest tests/integration/test_m1_schema_migration.py --require-docker` —— 需 `docker compose -f infra/docker-compose.yml up -d postgres` 运行中
- **覆盖率门禁**：`pytest --cov=app.db --cov=alembic --cov-fail-under=85`
- **TDD 红绿**：每个 task 强制 RED（commit 标 [RED]）→ GREEN（commit 标 [GREEN]）→ REFACTOR（commit 标 [RF]）

---

## 验证（Definition of Done）

- [ ] `alembic upgrade head` → `information_schema` 可见 4 张表（users / auth_sessions / chat_sessions / ingest_jobs）
- [ ] 每张表都有 `id`（UUID PK）/ `created_at` / `updated_at`（TimestampMixin 继承）
- [ ] INSERT + SELECT 各表 works（含 relationship / FK 验证）
- [ ] 唯一约束生效（username 重复 → IntegrityError）
- [ ] `app/config.py` 加载 `DATABASE_URL` / `pool_size` / `max_overflow`
- [ ] pytest 单元 + 集成全绿
- [ ] 单元覆盖率 ≥ 85%
- [ ] `.env.example` 含 `DATABASE_URL` 模板
- [ ] `pyproject.toml` 含 4 个新 DB 依赖
- [ ] `apps/rag_v1/` 仓库布局中 db 模块落地

---

## 与其他 M 的依赖

| 上游（必须 M1 前完成） | 下游（依赖 M1） |
|----------------------|----------------|
| M0 `docker-compose.yml`（postgres 容器） | M2 auth（操作 users + auth_sessions 表） |
| M0 `app/config.py`（M1 追加 DBSettings） | M7 graph（操作 chat_sessions 表） |
| M0 `.env.example`（M1 追加 DATABASE_URL） | M4–M6 ingest（操作 ingest_jobs 表） |
| | M8 API（操作 chat_sessions 表） |

---

## 风险

| 风险 | 缓解 | 曾被否决的替代方案 |
|------|------|------------------|
| Alembic autogenerate 遗漏 CHECK / INDEX / FK | migration 生成后人工 review + 集成测试 `test_migrate_up_creates_tables` 断言 `information_schema.tables` 4 表存在（P0-4 删原脆测） | 手写全部 migration — 可考虑，但 autogenerate 减少遗漏 |
| `asyncpg` 与 `psycopg2-binary` 版本兼容性 | CI 锁版本区间；M1 集成测试跑真实 PG | 只用 asyncpg — alembic upgrade 需要同步驱动 fallback |
| UUID 主键在 PG 中性能问题 | PG 原生 `UUID` 类型，建索引；V1 规模（<1M rows）无瓶颈 | 自增 `BIGSERIAL` — 20260608_145040_7202e5 讨论 UUID 更好（分布/安全） |
| `DeclarativeBase` vs `Base` 命名混淆 | 显式命名为 `DeclarativeBase` 避免与 SQLAlchemy 内部 `Base` 混淆 | 沿用 `Base` — 20260608_145040_7202e5 msg 193 无此讨论，团队习惯选清晰 |
| PG 连接池泄漏 | `expire_on_commit=False` + `pool_size=10` / `max_overflow=20` / `pool_recycle=1800` / `pool_pre_ping=True`；`get_session` 为 async generator 确保 `finally: await session.close()`；依据：V1 单副本 30 连接占 PG `max_connections=100` 的 30%，预留 70 给 Langfuse / LangGraph checkpointer / M11 RAGAS / 调试客户端 | 无连接池（每请求新建）— V1 规模不需要优化 |
| alembic.ini 硬编码 URL 模板 | `sqlalchemy.url=` 留空（P0-1：弃用 `%(VAR)s` interpolation），env.py `from app.config import settings` + `config.set_main_option("sqlalchemy.url", settings.db.database_url)` 注入；env.py 注释说明 | env.py 直读 env var — 但 pydantic-settings 已封装 |
| enum 选择（PG ENUM vs VARCHAR+CHECK）| 选 VARCHAR+CHECK：改值只需 `ALTER TABLE ... DROP/ADD CONSTRAINT`，ORM 层 Python enum 同步；PG ENUM `ADD VALUE` 有事务内限制。V1 状态机 4 值 + 数据量小，锁表 < 100ms 可接受 | PG 原生 `CREATE TYPE ... AS ENUM` — autogenerate 支持不完善 |
| pgbouncer transaction pool 兼容 | `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}` 关闭 asyncpg prepared statement 缓存；M12 加 pgbouncer 后零改动 | 默认 cache — `PreparedStatementError` 在 prod 必踩 |
| alembic 进程并发（CI + 容器启动）| env.py `do_run_migrations` 前后 `SELECT pg_advisory_lock(0x5241475631)` / `_unlock`（P1-13）| 无锁 — 两进程同时改 schema 必冲突 |
| postgresql_concurrently=True 缺失（prod 锁表）| 4 表所有 `op.create_index` 加 `postgresql_concurrently=True`（P1-18）| 默认 `op.create_index` — prod users 1M+ rows 锁几分钟 |
| PG-only 类型在 sqlite 上"假绿" | 单测走 `pytest-postgresql` 临时 PG（不用 sqlite：JSONB/INET/partial index 是 PG-only） | sqlite — 自动降级 TEXT，PG 上一迁移就挂 |
| `TimestampMixin.updated_at` 在 bulk update 时不自动更新 | docstring 显式说明（P0-7）；M4 ingest worker `UPDATE ingest_jobs SET status=..., chunks_count=...` 时**显式**传 `updated_at=func.now()` | 依赖 `onupdate=func.now()` — 只 ORM dirty 触发 |
| username 大小写敏感 | M2 业务层 `username = username.lower().strip()` 后入库（P1-19）；UNIQUE 索引等效 case-insensitive | 装 citext 扩展 — M0 init.sql 不必加 |
| FK 列缺索引（PG 不会自动建）| `__table_args__` 集中声明 FK + 查询列索引（P1-7 / P1-14）| 散落 `index=True` — autogenerate 难预测 |
| aiosqlite 缺依赖导致单测挂 | dev 依赖加 `pytest-postgresql >=6.0,<7` + `testcontainers[postgresql] >=4.0,<5`（P0-3）| 用 sqlite 内存 — PG-only 类型假绿 |
| `app/db/__init__.py` 暴露面矛盾 | Files 表 / 仓库布局 / REFACTOR 段统一为 `engine / async_session / async_session_factory / get_session / AsyncSession`（P0-5） | 文档不一致 — M2/M4 import 时混乱 |
| `app/config.py` 拆分 `configs/` 子目录（X-1 待落地）| M1 阶段先按 `app/config.py` 推进，X-1 决议后切到 `app/configs/db.py`（P2-1）| 现在拆 — 等 M0 一致 |
| pytest `asyncio_mode` 未设 → async 单测挂 | `pyproject.toml [tool.pytest.ini_options]` 加 `asyncio_mode = "auto"`（P1-16 / X-2） | 单测同步 — async 业务层无法测 |
| `settings` 全局单例缺失（X-3 待落地）| `app/config.py` 末尾 `settings = Settings()`（P1-17）| 业务层各自 `Settings()` — env.py / 测试无法 import 一致 |
| `downgrade()` 不写导致回滚卡住 | migration 手写 `downgrade()`：drop 4 表 + drop enum + drop index + drop extension；RED 测试 `test_migration_downgrade_works`（P1-9） | 不写 — 调试 `alembic downgrade -1` 必卡 |
| 4 表缺 `created_by` / `updated_by`（V2 多租户）| M1 阶段补 `UUID NULLABLE FK→users.id`，V2 直接填，无需 backfill（P1-3）| 推 V2 — 多 1 次 migration + backfill NULL |
| users 缺 email（M12 hardening 密码重置）| `email VARCHAR(255) UNIQUE NULL` + `email_verified_at`（P1-4）| 推 M12 — 多 1 次 migration |
| users 缺 `deleted_at` / 防爆破字段 | `deleted_at TIMESTAMPTZ NULL` + INDEX；`failed_login_attempts INTEGER DEFAULT 0` + `locked_until TIMESTAMPTZ NULL`（P1-5 / P2-4）| 推 M2 — 多 1 次 migration |
| chat_sessions 缺 `last_message_at` / `session_metadata` | `last_message_at` 单独字段（区别于 `updated_at`）+ `session_metadata JSONB DEFAULT '{}'`（P1-6 / P2-7） | 复用 `updated_at` — UI 改 title 也会被算 |
| ingest_jobs 缺 `retry_count` / `next_retry_at` | `retry_count` + `max_retries` + `next_retry_at`（P2-5）；M4-M6 失败重试不爆表 | 推 M4 — 多 1 次 migration |
| auth_sessions 缺 `ip_address` / `user_agent` | `ip_address INET NULL` + `user_agent VARCHAR(512) NULL`（P2-6）；M12 异常登录告警用 | 推 M12 — 多 1 次 migration |
| 4 表缺 `idempotency_key`（M8 API 重试）| `VARCHAR(64) UNIQUE NULL` 4 表通用（P2-8） | 仅 ingest_jobs.payload_hash — chat_sessions 没法幂等 |
| `MappedAsDataclass` boilerplate 未启用 | 推荐 `class Base(DeclarativeBase, MappedAsDataclass)` 模式（P2-9） | 手写 `__init__` — 4 表 boilerplate 多 1 倍 |
| alembic env.py 缺 `run_async` 完整模板 | 附完整 `run_async_migrations() + connection.run_sync(do_run_migrations)` 模板（P0-6） | 1 行注释"用 run_async 模式" — 实际照抄 `ProgrammingError` |
| `test_migration_has_all_tables` 脆（AST 解析 + 命名不一致）| 删测试，改走集成测试 `test_migrate_up_creates_tables`（P0-4）；alembic `file_template` 配为 `20260611_2230_initial_schema.py` 时间戳格式 | 解析 AST — 注释/字符串敏感，文件命名永远对不上 |
| server-side default 缺显式（client-side 时区漂移）| 全部时间字段 `server_default=func.now()` 显式声明（P1-15） | `default=datetime.now` — 多进程时区漂移 |
| pyproject 缺 `[tool.pytest.ini_options]` | 加 `asyncio_mode = "auto"` + `markers` + `addopts`（P1-16 / X-2）| 跑测报 "async def not natively supported" |
| 4 表新增审计/幂等/重试字段导致 DDL 复杂度 | 集中在 `__table_args__` 声明；DDL 总行数 ~20% 增长但 autogenerate 可预测 | 后续 migration 补 — 每补 1 次要 1 个 alembic rev |
| session.py 连接池缺 `connect_args` 兼容 pgbouncer | `statement_cache_size=0` + `prepared_statement_cache_size=0` 显式设（P1-12）| 走默认 — M12 加 pgbouncer 必报 `PreparedStatementError` |
| `chat_sessions.thread_id` 缺 UNIQUE 索引 | `UniqueConstraint("thread_id", name="uq_chat_sessions_thread_id")` 在 `__table_args__`；M7 PostgresCheckpointer 跨 M 依赖 | 列上 `unique=True` — autogenerate 与 `__table_args__` 混用难预测 |
| app/auth/ 子包 M1 是否要建 | M1 建 `app/auth/__init__.py` + `password_validator.py`（P1-8），M2 直接接业务；不在 M1 建则 M2 还得补建 | 推 M2 — 必加的 modules 提前到 M1 减分支 |

---

## 修订记录

| 版本 | 日期 | 改动 |
|------|------|------|
| M1-plan-r0 | 2026-06-10 | 初稿（基线 V1 Scope §7 M1 + 决策 #13/#14） |
| r1-2026-06-11 | 2026-06-11 | **35 项 P0/P1/P2 全部修复**（详见 review `2026-06-11-rag-m1-schema-review.md` 落地） |
| r1-2026-06-11 | 2026-06-11 | **P0-1 已修** · alembic.ini `sqlalchemy.url` 留空 + env.py 注入 DSN + `file_template=%(year)d%(month)d%(day)d%(hour)d%(minute)d_%%(rev)s_%%(slug)s` |
| r1-2026-06-11 | 2026-06-11 | **P0-2 已修** · 单测改 `pytest-postgresql` 临时 PG（不测 sqlite 走 JSONB/INET） |
| r1-2026-06-11 | 2026-06-11 | **P0-3 已修** · dev 依赖加 `pytest-postgresql` + `testcontainers[postgresql]` |
| r1-2026-06-11 | 2026-06-11 | **P0-4 已修** · 删 `test_migration_has_all_tables` 脆测 + 改走集成测试 `test_migrate_up_creates_tables` |
| r1-2026-06-11 | 2026-06-11 | **P0-5 已修** · 统一 `app/db/__init__.py` 暴露 engine/async_session/async_session_factory/get_session/AsyncSession |
| r1-2026-06-11 | 2026-06-11 | **P0-6 已修** · env.py 完整 `run_async_migrations` 模板（asyncio.run + connection.run_sync） |
| r1-2026-06-11 | 2026-06-11 | **P0-7 已修** · TimestampMixin docstring 显式 onupdate 限制 + M4 bulk update caveat |
| r1-2026-06-11 | 2026-06-11 | **P1-1 已修** · `ingest_jobs.payload_hash` 加 UNIQUE + `idempotency_key` UNIQUE |
| r1-2026-06-11 | 2026-06-11 | **P1-2 已修** · `chat_sessions` 索引改 `(user_id, is_active, updated_at DESC)` 复合索引 |
| r1-2026-06-11 | 2026-06-11 | **P1-3 已修** · 4 表全加 `created_by` / `updated_by` UUID FK→users.id |
| r1-2026-06-11 | 2026-06-11 | **P1-4 已修** · users 加 `email VARCHAR(255) UNIQUE NULLABLE` + `email_verified_at TIMESTAMPTZ NULLABLE` |
| r1-2026-06-11 | 2026-06-11 | **P1-5 已修** · users 加 `deleted_at TIMESTAMPTZ NULLABLE INDEX` + partial unique index（username 复用） |
| r1-2026-06-11 | 2026-06-11 | **P1-6 已修** · chat_sessions 加 `last_message_at TIMESTAMPTZ NULLABLE INDEX` |
| r1-2026-06-11 | 2026-06-11 | **P1-7 已修** · FK 列 + 状态/时间列全加索引（auth_sessions.user_id / chat_sessions.user_id / ingest_jobs.user_id 等） |
| r1-2026-06-11 | 2026-06-11 | **P1-8 已修** · 新建 `app/auth/password_validator.py` + 单测（长度/字符集/常用密码字典） |
| r1-2026-06-11 | 2026-06-11 | **P1-9 已修** · 手写 `downgrade()` + RED 测试 `test_migration_downgrade_works` |
| r1-2026-06-11 | 2026-06-11 | **P1-10 已修** · 风险表补 enum vs VARCHAR+CHECK 决策（status/source 选 VARCHAR+CHECK） |
| r1-2026-06-11 | 2026-06-11 | **P1-11 已修** · `pool_recycle=1800` + `pool_pre_ping=True`（防 stale connection） |
| r1-2026-06-11 | 2026-06-11 | **P1-12 已修** · `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}` 兼容 pgbouncer |
| r1-2026-06-11 | 2026-06-11 | **P1-13 已修** · env.py 加 `pg_advisory_lock(0x5241475631)` 并发锁防 alembic 并发迁移 |
| r1-2026-06-11 | 2026-06-11 | **P1-14 已修** · `__table_args__` 集中声明索引 + UNIQUE（autogenerate 可预测） |
| r1-2026-06-11 | 2026-06-11 | **P1-15 已修** · server-side default 显式声明约定（`server_default=func.now()`，不用 `default=datetime.now`） |
| r1-2026-06-11 | 2026-06-11 | **P1-16 已修** · `pyproject.toml [tool.pytest.ini_options]` 加 `asyncio_mode = "auto"` |
| r1-2026-06-11 | 2026-06-11 | **P1-17 已修** · `app/config.py` 末尾 `settings = Settings()` 全局单例（X-3 落地） |
| r1-2026-06-11 | 2026-06-11 | **P1-18 已修** · `op.create_index` 加 `postgresql_concurrently=True`（生产加索引不锁表） |
| r1-2026-06-11 | 2026-06-11 | **P1-19 已修** · users.username 走 M2 业务层 `.lower().strip()` 方案（不装 citext 扩展） |
| r1-2026-06-11 | 2026-06-11 | **P2-1 已修** · `app/config.py` 等待 X-1 决议切到 `app/configs/db.py`（标记待跨 M 协同） |
| r1-2026-06-11 | 2026-06-11 | **P2-2 已修** · 头部加"范本目的"段（与 M3 一致） |
| r1-2026-06-11 | 2026-06-11 | **P2-3 已修** · `.env.example` 加密码一致性注释（POSTGRES_PASSWORD 与 LANGFUSE 等联动） |
| r1-2026-06-11 | 2026-06-11 | **P2-4 已修** · users 加 `failed_login_attempts` + `locked_until`（M2 防爆破必用） |
| r1-2026-06-11 | 2026-06-11 | **P2-5 已修** · ingest_jobs 加 `retry_count` + `max_retries` + `next_retry_at`（M4 retry 调度） |
| r1-2026-06-11 | 2026-06-11 | **P2-6 已修** · auth_sessions 加 `ip_address INET` + `user_agent VARCHAR(512)` |
| r1-2026-06-11 | 2026-06-11 | **P2-7 已修** · chat_sessions 加 `session_metadata JSONB DEFAULT '{}'` |
| r1-2026-06-11 | 2026-06-11 | **P2-8 已修** · 4 表加 `idempotency_key VARCHAR(64) UNIQUE NULLABLE` |
| r1-2026-06-11 | 2026-06-11 | **P2-9 已修** · 推荐 `MappedAsDataclass` 模式（减少 boilerplate） |
| r1-2026-06-11 | 2026-06-11 | **跨 M 联动落地** · M2 依赖 is_revoked / failed_login_attempts / locked_until；M4 依赖 retry_count / next_retry_at / payload_hash；M7 依赖 thread_id UNIQUE / session_metadata / last_message_at；M8 依赖 chat_sessions 复合索引 + idempotency_key；M11 依赖 ingest_jobs.completed_at 索引；M12 依赖 auth_sessions.ip_address / user_agent |
| r2-2026-06-11 | 2026-06-11 | **NP-1 r2 已修** · §4 auth_sessions DDL 段补 `is_revoked BOOLEAN NOT NULL DEFAULT FALSE` 列（M2 plan L125/L824 强依赖；r1 漏写，r2 已补） |
| r2-2026-06-11 | 2026-06-11 | **NP-2 r2 已修** · users.deleted_at 段补 partial unique index 显式 SQL：`CREATE UNIQUE INDEX uq_users_username_active ON users(username) WHERE deleted_at IS NULL` + ORM `postgresql_where=text("deleted_at IS NULL")` |
| r2-2026-06-11 | 2026-06-11 | **NP-3 r2 已修** · §4 Indexes 段补 `ix_auth_sessions_expires_at_hard ON auth_sessions(expires_at_hard)`（M2 cleanup job 强依赖；r1 漏加，1M+ token 表全表扫） |
