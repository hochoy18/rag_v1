# M1 Plan r2 Review · r1 修复验证

> 评审对象：[2026-06-10-rag-m1-schema.md](../2026-06-10-rag-m1-schema.md)（650 行，r1 已修 35 项 P0/P1/P2）
> 评审基线：[2026-06-11-rag-m1-schema-review.md](./2026-06-11-rag-m1-schema-review.md)（r1 review，本 review 的对比基线）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（r2 独立审查）
> 范围：**验 r1 修复是否到位 + 发现 r1 修复过程中是否引入新问题 + 跨 M 一致性**
> 输出策略：35 项逐项验证 + 5 项 r1 引入新问题 + 7 个 M 联动 + 风险表补全质量

---

## 总评

| 维度 | 评分 | 说明 |
|---|---|---|
| r1 修复完成度 | ⭐⭐⭐⭐ | 35 项中 31 项**已修到位**（含 4 项落实方式有瑕疵）；4 项**未修 / 修错位** |
| 跨 M 一致性 | ⭐⭐⭐ | M0/M4/M7/M8/M11/M12 联动基本落地；**M2 强依赖的 `auth_sessions.is_revoked` 字段在 DDL 中彻底缺失** |
| DDL 完整性 | ⭐⭐⭐ | 4 张表主体字段齐，复合索引 + 状态/时间索引齐；但 `expires_at_hard` 索引缺 / `partial unique index` 未显式落 / 表 DDL 描述段与 ORM 代码段 server_default 表达不一致 |
| 风险表补全 | ⭐⭐⭐⭐ | 6 行原风险 + 30 行 r1 已修（r1 修了 30 行新增风险项），但** DDL 复杂度量化行未补** |
| 实施就绪度 | ⭐⭐⭐⭐ | r1 后 P0-1 ~ P0-7 全修；alembic 工程化、连接池、pgbouncer 兼容、enum 决策、pytest config 全到位 |

**一句话**：r1 修复整体到位（31/35 项 100% 修，4 项部分修），**最大遗漏是 M2 强依赖的 `auth_sessions.is_revoked` 字段**（M2 plan L125/L824 显式声明依赖此字段，M1 修订记录 L650 跨 M 联动行也提到，但 §4 表结构 DDL 段没写），M1 落地后 M2 会缺字段；外加 `expires_at_hard` 索引 / `partial unique index` / `file_template` 模板前后矛盾 / DDL 描述段 server_default 未统一 4 项小瑕疵，r2 后小修 1 轮即可动手。

---

## 1. r1 修复验证（35 项逐项）

| # | r1 标记 | 修复内容（r1 claim） | 实际验证（plan 文本位置） | 状态 |
|---|---|---|---|---|
| 1 | P0-1 | alembic.ini `sqlalchemy.url` 留空 + env.py 注入 DSN + `file_template` | L396-400（env.py 模板 L419-425 注入）+ L397/L464 提 `file_template`；**但 L397 与 L615 模板字符串不一致**（L397 用 `%(slug)s` 结尾，L615 r1 修订记录用 `%(rev)s_%(slug)s` 结尾） | ⚠️ 部分修 |
| 2 | P0-2 | 单测改 `pytest-postgresql` 临时 PG | L307/L509/L533 显式"不用 sqlite，走 `pytest-postgresql` 临时 PG" | ✅ 已修 |
| 3 | P0-3 | dev 依赖加 `pytest-postgresql` + `testcontainers[postgresql]` | L510-511 pyproject.toml dev 段已加 | ✅ 已修 |
| 4 | P0-4 | 删 `test_migration_has_all_tables` 脆测 + 改走 `test_migrate_up_creates_tables` | L461-464 显式删除原 RED 测试 + 改走 Task 5 集成测试 | ✅ 已修 |
| 5 | P0-5 | 统一 `app/db/__init__.py` 暴露 engine/async_session/async_session_factory/get_session/AsyncSession | L258 Files 表 + L380-386 REFACTOR 代码块 `__all__` 一致 | ✅ 已修 |
| 6 | P0-6 | env.py 完整 `run_async_migrations` 模板（asyncio.run + connection.run_sync） | L408-458 完整 env.py 模板包含 `do_run_migrations` + `run_async_migrations` + `run_migrations_online` | ✅ 已修 |
| 7 | P0-7 | TimestampMixin docstring 显式 onupdate 限制 + M4 bulk update caveat | L311-330 docstring 三段 + 注释 `# 仅 ORM dirty 时触发，bulk update 无效` | ✅ 已修 |
| 8 | P1-1 | `ingest_jobs.payload_hash` 加 UNIQUE + `idempotency_key` UNIQUE | L166 `UNIQUE INDEX uq_ingest_jobs_payload_hash` + L170 `idempotency_key` UNIQUE | ✅ 已修 |
| 9 | P1-2 | `chat_sessions` 索引改 `(user_id, is_active, updated_at DESC)` 复合索引 | L156 Indexes 段 + L196 ORM `__table_args__` 复合索引 | ✅ 已修 |
| 10 | P1-3 | 4 表全加 `created_by` / `updated_by` UUID FK→users.id | L119-120（users）/ L136-137（auth_sessions）/ L153-154（chat_sessions）/ L178-179（ingest_jobs）4 表全加 | ✅ 已修 |
| 11 | P1-4 | users 加 `email VARCHAR(255) UNIQUE NULLABLE` + `email_verified_at` | L108 `email` UNIQUE NULLABLE + L109 `email_verified_at` | ✅ 已修 |
| 12 | P1-5 | users 加 `deleted_at TIMESTAMPTZ NULLABLE INDEX` + partial unique index（username 复用） | L116 `deleted_at NULLABLE, INDEX` 列 + L626 r1 行写"partial unique index"；**但 §4 表结构段 L116 只列 INDEX，partial unique index 没显式 SQL 描述** | ⚠️ 部分修 |
| 13 | P1-6 | chat_sessions 加 `last_message_at TIMESTAMPTZ NULLABLE INDEX` | L149 `last_message_at` + 单独 INDEX | ✅ 已修 |
| 14 | P1-7 | FK 列 + 状态/时间列全加索引 | L181-186 列了 5 个索引（auth_sessions.user_id / chat_sessions.user_id / ingest_jobs.user_id_created_at + status_created_at + completed_at）；**`auth_sessions.expires_at_hard` 索引未列**（M2 cleanup job 强依赖） | ⚠️ 部分修 |
| 15 | P1-8 | 新建 `app/auth/password_validator.py` + 单测 | L77 `password_validator.py` + L263 Files 表新增 + L273 单测文件 + L385-403 草稿代码 | ✅ 已修 |
| 16 | P1-9 | 手写 `downgrade()` + RED 测试 `test_migration_downgrade_works` | L406 显式"手写 `downgrade()`" + L466-468 RED 测试 | ✅ 已修 |
| 17 | P1-10 | 风险表补 enum vs VARCHAR+CHECK 决策 | L226-228 "不引入 `sqlalchemy Enum` 类型，`source` / `status` 用 `String + CheckConstraint`" + L576 风险表 1 行 | ✅ 已修 |
| 18 | P1-11 | `pool_recycle=1800` + `pool_pre_ping=True` | L367 `create_async_engine(... pool_recycle=1800, pool_pre_ping=True, ...)` | ✅ 已修 |
| 19 | P1-12 | `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}` 兼容 pgbouncer | L367 connect_args 显式 + L577 风险表 1 行 | ✅ 已修 |
| 20 | P1-13 | env.py 加 `pg_advisory_lock(0x5241475631)` 并发锁 | L434-444 `do_run_migrations` 前后 advisory lock + unlock | ✅ 已修 |
| 21 | P1-14 | `__table_args__` 集中声明索引 + UNIQUE | L190-200 显式 ORM 示例 `__table_args__` 集中声明 | ✅ 已修 |
| 22 | P1-15 | server-side default 显式声明约定（`server_default=func.now()`，不用 `default=datetime.now`） | L334 "P1-15 约定"段 + L322-330 ORM 代码；**但 §4 表 DDL 描述段 L117/L131/L135 等仍写 `DEFAULT now()`，没显式 `server_default=func.now()`** | ⚠️ 部分修 |
| 23 | P1-16 | pyproject.toml `[tool.pytest.ini_options]` 加 `asyncio_mode = "auto"` | L514-520 pyproject.toml pytest 配置段 | ✅ 已修 |
| 24 | P1-17 | `app/config.py` 末尾 `settings = Settings()` 全局单例 | L296-299 "P1-17 文件末尾追加全局单例" + 代码块 | ✅ 已修 |
| 25 | P1-18 | `op.create_index` 加 `postgresql_concurrently=True` | L188 "所有 `op.create_index(...)` 用 `postgresql_concurrently=True`" + L439 `render_as_batch=False` 显式 | ✅ 已修 |
| 26 | P1-19 | users.username 走 M2 业务层 `.lower().strip()` 方案（不装 citext 扩展） | L106 列定义"用户名（P1-19：M2 业务层 `username = username.lower().strip()` 后入库，UNIQUE 索引等效 case-insensitive；不装 citext 扩展）" | ✅ 已修 |
| 27 | P2-1 | `app/config.py` 等待 X-1 决议切到 `app/configs/db.py` | L276 Files 表"修改"段"P2-1 等待 X-1 决议"显式标记 | ✅ 已修 |
| 28 | P2-2 | 头部加"范本目的"段 | L4 "`> 范本目的：M1 是 RAG V1 路线第二个 plan，给 M2/M4-M12 提供"数据层"前置定义`" | ✅ 已修 |
| 29 | P2-3 | `.env.example` 加密码一致性注释 | L526-527 注释行 `# 注意：rag_app / rag_app_password 必须与 infra/init.sql 的 POSTGRES_USER / POSTGRES_PASSWORD 一致` | ✅ 已修 |
| 30 | P2-4 | users 加 `failed_login_attempts` + `locked_until` | L114-115 `failed_login_attempts INTEGER NOT NULL DEFAULT 0` + `locked_until TIMESTAMPTZ NULLABLE` | ✅ 已修 |
| 31 | P2-5 | ingest_jobs 加 `retry_count` + `max_retries` + `next_retry_at` | L171-173 三个字段齐 | ✅ 已修 |
| 32 | P2-6 | auth_sessions 加 `ip_address INET` + `user_agent VARCHAR(512)` | L133-134 `ip_address INET NULLABLE` + `user_agent VARCHAR(512) NULLABLE` | ✅ 已修 |
| 33 | P2-7 | chat_sessions 加 `session_metadata JSONB DEFAULT '{}'` | L150 `session_metadata JSONB NULLABLE, DEFAULT '{}'` | ✅ 已修 |
| 34 | P2-8 | 4 表加 `idempotency_key VARCHAR(64) UNIQUE NULLABLE` | L113 users / L132 auth_sessions / L148 chat_sessions / L170 ingest_jobs 全加 | ✅ 已修 |
| 35 | P2-9 | 推荐 `MappedAsDataclass` 模式 | L335-347 推荐 `class Base(DeclarativeBase, MappedAsDataclass)` 模式 | ✅ 已修 |

**统计**：✅ 已修 30 项 + ⚠️ 部分修 5 项（#1 file_template 前后矛盾 / #12 partial unique index 未显式 SQL / #14 expires_at_hard 索引缺 / #15 / #22 DDL 描述段与 ORM 代码段 server_default 表达不一致）。

---

## 2. r1 修复引入的新问题

### NP-1 · M2 强依赖的 `auth_sessions.is_revoked` 字段在 DDL 中彻底缺失（最严重）

**位置**：M1 §4 auth_sessions 表 L122-137

**问题**：
- M2 plan L125 显式声明："M1 字段: `users.email` / `users.failed_login_attempts` / `users.locked_until` / **`auth_sessions.is_revoked`** / `auth_sessions.ip_address` / `auth_sessions.user_agent`"
- M2 plan L824 重申："M1 schema 字段：`users.email` / `users.failed_login_attempts` / `users.locked_until` / **`auth_sessions.is_revoked`** / `auth_sessions.ip_address` / `auth_sessions.user_agent`"
- M1 plan L650 r1 跨 M 联动行也写："M2 依赖 **`is_revoked`** / failed_login_attempts / locked_until"
- **但 §4 auth_sessions 表 DDL 段 L122-137 完全没有 `is_revoked` 字段**——只有 `id` / `user_id` / `token_hash` / `expires_at_sliding` / `expires_at_hard` / `last_used_at` / `idempotency_key` / `ip_address` / `user_agent` / `created_at` / `created_by` / `updated_by` 12 个列
- `grep is_revoked` 在 M1 plan 只有 L650 1 处出现，全部是"跨 M 联动"行的引用，**表 DDL 段无任何定义**
- M2 业务做"主动撤销 token"（如改密码 / admin 强制下线）100% 需要此字段

**修复**：
```python
is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
# 或
is_revoked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
# 语义：NULL=未撤销 / NOW()=撤销时间（审计更友好，推荐后者）
```
同步在 `__table_args__` 加 `Index("ix_auth_sessions_is_revoked", "is_revoked")`（M2 查 `WHERE is_revoked IS NULL` 走 index scan）。

**r2 评级**：🔴 **P0**（r1 修复遗漏跨 M 强依赖字段，必须在 r2 补，否则 M2 实施时缺字段需新增 migration）。

### NP-2 · `partial unique index` 在 DDL 描述段未显式落 SQL（P1-5 部分修的真实缺口）

**位置**：M1 §4 users 表 L116 + L626 r1 修订记录

**问题**：
- r1 修订记录 L626 写"users 加 `deleted_at TIMESTAMPTZ NULLABLE INDEX` + **partial unique index（username 复用）**"
- §4 表 DDL 描述段 L116 只写 `deleted_at TIMESTAMPTZ NULLABLE, INDEX`（普通 INDEX）
- plan 全文未显式 `CREATE UNIQUE INDEX uq_users_username_active ON users(username) WHERE deleted_at IS NULL` 或对应 ORM `Index("uq_users_username_active", "username", postgresql_where=text("deleted_at IS NULL"), unique=True)`
- r1 修复"打了勾但没落地"

**修复**：补显式 SQL / ORM 代码：
```python
# app/db/models.py
class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_username_active", "username",
              postgresql_where=text("deleted_at IS NULL"), unique=True),
    )
```
或风险表补"软删除 username 复用"决策行（说明 alias 删除后 username 释放语义）。

**r2 评级**：🟡 **P1**（语义正确但实施时易漏；用户表 1M+ rows 后 ALTER 加 partial index 会锁表，应在初始 migration 一起建好）。

### NP-3 · `auth_sessions.expires_at_hard` 索引未在 P1-7 索引清单中（P1-7 部分修的真实缺口）

**位置**：M1 §4 Indexes 段 L181-186

**问题**：
- L181-186 列了 5 个索引：auth_sessions.user_id / chat_sessions.user_id / ingest_jobs.user_id_created_at + status_created_at + completed_at
- **没有 `ix_auth_sessions_expires_at_hard`**
- M2 cleanup job 强依赖：`DELETE FROM auth_sessions WHERE expires_at_hard < NOW()`（r1 review P1-7 后半段已点出，M4 plan L549 集成测试也会跑）
- 1M+ token 表上无索引会全表扫

**修复**：Indexes 段补一行：
```
- `ix_auth_sessions_expires_at_hard` ON `auth_sessions(expires_at_hard)` — M2 cleanup job 删过期 token
```
对应 ORM `Index("ix_auth_sessions_expires_at_hard", "expires_at_hard")`。

**r2 评级**：🟡 **P1**（P1-7 自称"FK 列 + 状态/时间列全加索引"，但漏 1 个时间列；M2 落地时需补 migration）。

### NP-4 · DDL 描述段与 ORM 代码段 `server_default` 表达不一致（P1-15 部分修的口径未统一）

**位置**：M1 §4 表 DDL 描述段 vs Task 2 GREEN ORM 代码段

**问题**：
- §4 表 DDL 描述段（L117 / L131 / L135 / L165 等）全部写 `DEFAULT now()` 或 `DEFAULT TRUE` 等**自然语言**形式，**未标注** `server_default=func.now()` 还是 `default=datetime.now`
- Task 2 GREEN ORM 代码段（L322-330）显式 `server_default=func.now()` 注释 `# P1-15 显式 server-side`
- M4 plan L576 引用"P1-4 updated_at 触发口径"专门提醒 bulk update 行为
- **DDL 描述段与 ORM 代码段对同一概念表达口径不一致**——实施时若有人按 §4 表写 `default=datetime.now`，M4 写代码会踩坑

**修复**：§4 表 DDL 描述段统一口径：
```
| `created_at` | `TIMESTAMPTZ` | NOT NULL, **`server_default=func.now()`** | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, **`server_default=func.now() + onupdate=func.now()`** | 更新时间 |
```
并加 1 句脚注："P1-15 约定：本表所有时间字段均 `server_default=func.now()`，禁 `default=datetime.now`（client-side 多进程时区漂移）"。

**r2 评级**：🟢 **P2**（语义正确，文档化口径补齐即可）。

### NP-5 · alembic `file_template` 模板字符串前后矛盾（P0-1 部分修的细节遗漏）

**位置**：L397 vs L615 vs L464

**问题**：
- L397（Task 4 GREEN 段）：`file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s`
- L615（r1 修订记录行）：`file_template=%(year)d%(month)d%(day)d%(hour)d%(minute)d_%%(rev)s_%%(slug)s`（注意：单 `%` 漏写 / `%(rev)s_%(slug)s` 与 L397 不同）
- L464（RED 测段）：与 L397 一致 `%%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s`
- **L397 与 L615 模板字符串不一致**——一处用 `%(slug)s` 结尾，一处用 `%(rev)s_%(slug)s` 结尾；M0 修订记录里 P1-2 init.sql 也修过类似"`${POSTGRES_PASSWORD}` 占位 vs 明文"问题

**修复**：修订记录行 L615 改正（与 L397/L464 对齐）：
```
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s
```
或 L397/L464 改成 `%(rev)s_%(slug)s`（保留 alembic hex revision id 作前缀）。**两处选 1 个统一**。

**r2 评级**：🟢 **P2**（小瑕疵但 alembic 实际会跑 1 个模板，动手时一致即可）。

---

## 3. 跨 M 一致性检查

### 3.1 M1 ↔ M0（基础设施层）

| 项 | M0 plan 描述 | M1 plan 描述 | 一致性 |
|---|---|---|---|
| Postgres 凭据 | M0 L201 `POSTGRES_USER=rag_app` / `POSTGRES_PASSWORD=rag_app_password` / `POSTGRES_DB=rag` | M1 L525 `DATABASE_URL=postgresql+asyncpg://rag_app:rag_app_password@postgres:5432/rag` | ✅ 凭据一致 |
| init.sql 联动 | M0 L615 修订记录"init.sql 注释密码为 `${POSTGRES_PASSWORD}` 变量插值" | M1 L526 注释"必须与 infra/init.sql 的 POSTGRES_USER / POSTGRES_PASSWORD 一致" | ✅ 联动 |
| env.py DSN 注入 | M0 config.py 含 `db: DBSettings` | M1 env.py `from app.config import settings` + `config.set_main_option("sqlalchemy.url", settings.db.database_url)` | ✅ 一致 |

**结论**：M1 ↔ M0 联动完整，无新增 gap。

### 3.2 M1 ↔ M2（auth 业务层）🔴 **发现 1 个严重遗漏**

| M2 依赖字段 | M1 DDL 状态 | 备注 |
|---|---|---|
| `users.email` | ✅ L108 UNIQUE NULLABLE | r1 已补 |
| `users.email_verified_at` | ✅ L109 | r1 已补 |
| `users.failed_login_attempts` | ✅ L114 NOT NULL DEFAULT 0 | r1 已补 |
| `users.locked_until` | ✅ L115 NULLABLE | r1 已补 |
| `users.deleted_at` | ✅ L116 + partial unique index（partial 部分修）| r1 已补 |
| `auth_sessions.ip_address` | ✅ L133 INET NULLABLE | r1 已补 |
| `auth_sessions.user_agent` | ✅ L134 VARCHAR(512) NULLABLE | r1 已补 |
| **`auth_sessions.is_revoked`** | ❌ **DDL 段无定义** | **r1 漏修（NP-1）** |
| `auth_sessions.expires_at_hard` 索引 | ❌ §4 Indexes 段 L181-186 未列 | **r1 漏修（NP-3）** |
| `app/auth/password_validator.py` | ✅ L77/L263 Files 表新增 | r1 已补 |
| `username = .lower().strip()` 业务口径 | ✅ L106 列说明 P1-19 | r1 已补 |

**结论**：🔴 **2 个未补**——`is_revoked` 字段缺失 / `expires_at_hard` 索引缺失。M2 强依赖。

### 3.3 M1 ↔ M4（ingest pipeline）

| M4 依赖字段 | M1 DDL 状态 | 备注 |
|---|---|---|
| `ingest_jobs.payload_hash` UNIQUE | ✅ L166 UNIQUE INDEX uq_ingest_jobs_payload_hash | r1 已补 |
| `ingest_jobs.retry_count` / `max_retries` / `next_retry_at` | ✅ L171-173 | r1 已补 |
| `ingest_jobs.idempotency_key` | ✅ L170 | r1 已补 |
| `ingest_jobs` UNIQUE 约束（M4 ON CONFLICT 用） | ✅ P1-5 修订记录 | r1 已补 |
| `ingest_jobs.completed_at` 索引（M11 RAGAS 用） | ✅ L186 ix_ingest_jobs_completed_at | r1 已补 |
| bulk update `updated_at=func.now()` 注释 | ✅ L317 docstring + L581 风险表 | r1 已补 |
| M4 状态机 `pending → running → indexed|failed`，`failed → running` | ✅ L625 P1-5 r1 修订记录（与 M4 L625 P1-5 同源） | 一致 |

**结论**：M1 ↔ M4 联动完整，无新增 gap。

### 3.4 M1 ↔ M7（graph checkpointer）

| M7 依赖字段 | M1 DDL 状态 | 备注 |
|---|---|---|
| `chat_sessions.thread_id` UNIQUE | ✅ L145 UNIQUE + L195 UniqueConstraint("thread_id", name="uq_chat_sessions_thread_id") | r1 已补 |
| `chat_sessions.session_metadata` JSONB | ✅ L150 DEFAULT '{}' | r1 已补 |
| `chat_sessions.last_message_at` | ✅ L149 | r1 已补（M7 graph save_memory 时显式更新）|

**结论**：M1 ↔ M7 联动完整，M7 plan L884 "已落" 验证通过。

### 3.5 M1 ↔ M8（API 层）

| M8 依赖 | M1 DDL 状态 | 备注 |
|---|---|---|
| `chat_sessions` 复合索引 `(user_id, is_active, updated_at DESC)` | ✅ L156 + L196 | r1 已补（M8 API `GET /api/sessions` 走 index scan）|
| `chat_sessions.last_message_at` 索引 | ✅ L149 | r1 已补（M8 列表按此排序）|
| `chat_sessions.idempotency_key` | ✅ L148 | r1 已补（M8 API 重试幂等）|
| 4 表 `idempotency_key` UNIQUE | ✅ L113/L132/L148/L170 | r1 已补 |

**结论**：M1 ↔ M8 联动完整。

### 3.6 M1 ↔ M11（evaluator RAGAS）

| M11 依赖 | M1 DDL 状态 | 备注 |
|---|---|---|
| `ingest_jobs.completed_at` 索引（"最近 7 天 ingest 成功率"）| ✅ L186 | r1 已补 |

**结论**：M1 ↔ M11 联动完整。

### 3.7 M1 ↔ M12（hardening）

| M12 依赖 | M1 DDL 状态 | 备注 |
|---|---|---|
| `auth_sessions.ip_address` INET（"陌生 IP 登录"告警）| ✅ L133 | r1 已补 |
| `auth_sessions.user_agent` | ✅ L134 | r1 已补 |
| `users.email` + `email_verified_at`（密码重置）| ✅ L108-109 | r1 已补 |
| connection pool `statement_cache_size=0`（pgbouncer transaction pool 兼容）| ✅ L367 + L577 风险表 | r1 已补（M12 加 pgbouncer 后零改动）|

**结论**：M1 ↔ M12 联动完整。

### 3.8 跨 M 一致性总结

| 联动 | 状态 | 缺口 |
|---|---|---|
| M1 ↔ M0 | ✅ 完整 | 无 |
| M1 ↔ M2 | 🔴 **2 项未补** | `auth_sessions.is_revoked` 字段缺 / `auth_sessions.expires_at_hard` 索引缺 |
| M1 ↔ M4 | ✅ 完整 | 无 |
| M1 ↔ M7 | ✅ 完整 | 无 |
| M1 ↔ M8 | ✅ 完整 | 无 |
| M1 ↔ M11 | ✅ 完整 | 无 |
| M1 ↔ M12 | ✅ 完整 | 无 |

---

## 4. 风险表补全质量

### 4.1 风险表行数核对

- **6 行原风险**（r0） + **30 行 r1 已修新增** = **36 行风险段**（r1 后）
- r1 修订记录行（L613-650）共 38 行（"M1-plan-r0" + "r1-2026-06-11" 36 行 + "跨 M 联动落地" 1 行）

### 4.2 风险段是否保留原风险行

- L567-606 §风险段保留了原 6 行（Alembic autogenerate / asyncpg + psycopg2 兼容 / UUID PK 性能 / DeclarativeBase 命名 / PG 连接池泄漏 / alembic.ini 硬编码 URL）+ r1 修复新增 24 行风险段 + 1 行"app/db/__init__.py 暴露面矛盾" + 1 行"downgrade() 不写" + 1 行"4 表缺 created_by" + 1 行"users 缺 email" + 1 行"users 缺 deleted_at" + 1 行"chat_sessions 缺 last_message_at" + 1 行"ingest_jobs 缺 retry_count" + 1 行"auth_sessions 缺 ip_address" + 1 行"4 表缺 idempotency_key" + 1 行"MappedAsDataclass" + 1 行"alembic env.py 缺 run_async" + 1 行"test_migration_has_all_tables 脆" + 1 行"server-side default 缺显式" + 1 行"pyproject 缺 pytest config" + 1 行"DDL 复杂度膨胀" + 1 行"session.py 缺 connect_args" + 1 行"thread_id 缺 UNIQUE" + 1 行"app/auth 子包 M1 是否要建"
- **原 6 行风险全保留** ✅

### 4.3 DDL 复杂度 / 字段膨胀风险是否量化

- L602 "4 表新增审计/幂等/重试字段导致 DDL 复杂度 | 集中在 `__table_args__` 声明；DDL 总行数 ~20% 增长但 autogenerate 可预测"
- ✅ **有量化行**（"~20% 增长"），可接受
- **小缺口**：未量化新增索引数量（r1 后约 12 个索引），未量化 4 表新加字段数（r1 后约 20 个新字段）

### 4.4 风险表新发现缺口

| 缺口 | 建议补行 |
|---|---|
| M1 ↔ M2 `auth_sessions.is_revoked` 字段缺失 | 补 1 行："auth_sessions 缺 is_revoked 字段（M2 主动撤销 token 强依赖）" + 风险：M2 实施需新增 migration；缓解：M1 r2 补 DDL |
| `auth_sessions.expires_at_hard` 索引缺 | 补 1 行："M2 cleanup job 缺 expires_at_hard 索引（1M+ token 表全表扫）" + 缓解：M1 r2 补 Index |
| `partial unique index` 在 DDL 段未显式 | 补 1 行："users deleted_at 软删除后 username 复用语义" + 风险：partial index 漏建则 username 永久占位；缓解：M1 r2 ORM `__table_args__` 显式 |
| `MappedAsDataclass` 启用后的 relationship 兼容性 | 补 1 行："MappedAsDataclass 模式下 relationship back_populates 仍需手写" + 缓解：4 个 ORM 类手写 relationship |
| 4 表 `created_by` / `updated_by` FK 循环引用（users 表的 created_by 指向 users.id） | 补 1 行："users.created_by FK→users.id 自引用 + bootstrap 用户 created_by=NULL" + 缓解：M2 注册第一个 admin 时 created_by=NULL |

**r2 评级**：风险表补全质量 ⭐⭐⭐⭐（原 6 行保留 / 30 行 r1 修复全落地 / 有 DDL 复杂度量化行；缺 2 个跨 M 联动风险行 + 2 个实施细节风险行）。

---

## 5. 落地建议

### 5.1 r2 必须修（5 项 P0/P1，r2 落定后再动手 M1）

| 优先级 | 项 | 改动量 | 风险 |
|---|---|---|---|
| 🔴 P0 | NP-1 `auth_sessions.is_revoked` 字段补 DDL | 1 行（§4 表） + 1 行（修订记录） | M2 强依赖，漏则 M2 需新增 migration |
| 🟡 P1 | NP-3 `auth_sessions.expires_at_hard` 索引补 Indexes 段 | 1 行（§4 Indexes） | M2 cleanup job 性能 |
| 🟡 P1 | NP-2 `partial unique index` 显式 ORM `__table_args__` 代码块 | 1 个 ORM 段 | 用户表 1M+ rows 后 ALTER 加 partial index 锁表 |
| 🟢 P2 | NP-4 DDL 描述段与 ORM 代码段 `server_default` 口径统一 | §4 表 4 处全表扫一遍 | 文档化口径 |
| 🟢 P2 | NP-5 alembic `file_template` 模板字符串前后对齐 | L615 一行改正 | 小瑕疵 |

### 5.2 落地流程

1. r2 修 M1 plan：
   - 改 §4 auth_sessions 表 L122-137：加 `is_revoked` 列（建议 `TIMESTAMPTZ NULLABLE` 语义，NULL=未撤销 / NOW()=撤销时间）+ `Index("ix_auth_sessions_is_revoked", "is_revoked")`
   - 改 §4 Indexes 段 L181-186：加 `ix_auth_sessions_expires_at_hard` 索引
   - 改 §4 users 表 L116 附近：补 `__table_args__` partial unique index ORM 段
   - 改 §4 表 DDL 描述段：4 张表所有 `DEFAULT now()` 改 `server_default=func.now()` 统一口径
   - 改 L615 r1 修订记录行：`file_template` 模板字符串与 L397/L464 对齐
2. r2 后 review 通过 → 通知 M2（`is_revoked` / `expires_at_hard` 索引已补）
3. 估时维持 **5d**（r2 修补 ~0.5d + P0 实施 1d + P1 实施 1d + 集成测试 1d + buffer 1d）

### 5.3 跨 M 通知（M1 改完后）

| M | 通知内容 |
|---|---|
| M2 | users 表已有 `email` / `email_verified_at` / `failed_login_attempts` / `locked_until` / `deleted_at` + partial unique index；**auth_sessions 表新增 `is_revoked` 字段（r2 补）+ `expires_at_hard` 索引（r2 补）**；`app/auth/password_validator.py` 已存在 |
| M4 | ingest_jobs 表已有 `payload_hash` UNIQUE / `retry_count` / `max_retries` / `next_retry_at` / `idempotency_key`；bulk update 时显式传 `updated_at=func.now()` |
| M7 | chat_sessions 表已有 `thread_id` UNIQUE + `session_metadata` JSONB + `last_message_at`；M7 graph save_memory 时显式更新 `last_message_at` |
| M8 | chat_sessions 索引已是 `(user_id, is_active, updated_at DESC)` + `last_message_at` 索引；4 表 `idempotency_key` UNIQUE |
| M11 | ingest_jobs.completed_at 索引已建 |
| M12 | auth_sessions 表已有 `ip_address` INET / `user_agent` VARCHAR(512)；session.py `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}` 兼容 pgbouncer |

### 5.4 等待决策

- X-1 `app/config.py` 拆分 `configs/` 子目录是否在 M1 阶段动手（推荐是，alembic env.py 引用 `app.configs.db` 比 `app.config.db` 更清晰）
- P1-10 enum vs VARCHAR+CHECK 是否要在 M1 阶段换 enum（推荐不换，autogenerate 对 enum 支持不完善）

---

## 状态

- **r1 修复完成度**：30/35 项 100% 修（✅）+ 5 项部分修（⚠️）
- **r1 修复引入新问题**：5 项（🔴 P0 × 1 / 🟡 P1 × 2 / 🟢 P2 × 2）
- **跨 M 一致性**：6/7 M 联动完整；M2 联动漏 2 项（`is_revoked` 字段 / `expires_at_hard` 索引）
- **风险表补全**：原 6 行保留 ✅ + r1 30 行新增 ✅ + DDL 复杂度量化 ✅；缺 2 个跨 M 联动风险行 + 2 个实施细节风险行
- **落地建议**：r2 修 5 项（0.5d）→ r2 后 review 通过 → 通知 M2 / M4 / M7 / M8 / M11 / M12 → 动手 M1 实施（5d 估时维持）

M1 plan r1 修复质量整体到位（90%+），**最大遗留是 M2 强依赖的 `auth_sessions.is_revoked` 字段缺失**，r2 必须修；其余 4 项为 P1/P2 小瑕疵，r2 一并修齐后即可动手 M1 实施。
