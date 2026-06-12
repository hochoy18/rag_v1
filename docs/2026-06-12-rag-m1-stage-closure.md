# RAG V1 M1 阶段收口报告

> 日期: 2026-06-12
> 状态: **M1 实施层完成 · 4 表 DDL + ORM + alembic + 16/16 TDD**
> 5 commits · 33 份文件 · 29/29 TDD 通过

## 1. 完成度

| Task | 状态 | 备注 |
|------|------|------|
| Task 1 DBSettings | ✅ | env_prefix=DB_，5 字段 (database_url/pool_size/max_overflow/pool_recycle_seconds/pool_pre_ping/echo) |
| Task 2 SQLAlchemy base + 4 models | ✅ | User/AuthSession/ChatSession/IngestJob + r2 NP-1/NP-2/NP-3 全部到位 |
| Task 3 Async session factory | ✅ | pgbouncer 兼容 (statement_cache_size=0) + pool_recycle 1800 + pool_pre_ping |
| Task 4 Alembic init + 0001 migration | ✅ | 4 表 DDL + 7 索引 + 3 CHECK 约束 + 1 partial unique index |
| TDD 16/16 | ✅ | 3 DBSettings + 8 Models + 5 Alembic |
| 真 PG 迁移验证 | ⏭ 跳过 | 主机无 docker / 无 PG 实例 |

## 2. 4 表 DDL 字段齐全

| 表 | 字段 | r2 修复 |
|----|------|---------|
| `users` | 18 字段 | NP-2 partial unique index `uq_users_username_active` (deleted_at IS NULL) |
| `auth_sessions` | 14 字段 | NP-1 `is_revoked` BOOLEAN DEFAULT FALSE + NP-3 `ix_auth_sessions_expires_at_hard` 索引 |
| `chat_sessions` | 13 字段 | (user_id, is_active, updated_at DESC) 复合索引 |
| `ingest_jobs` | 21 字段 | P1-1 `payload_hash` UNIQUE + status CHECK 包含 `indexed` (M4 r2 P1-5) |

## 3. 关键实施层修订 (vs M1 plan)

- **Task 2 字段名**：M1 plan `users` 表用 `id: BIGSERIAL` (autoincrement int)，实施改 `UUID` (与 `auth_sessions.user_id` 强类型一致 + V2 多租户扩展性) — 与 plan 修订
- **IngestJob.status**：plan 用 `SAEnum`，实施改 `String(16) + CHECK 约束` —— 避免 PG native enum 迁移痛点 (V1.1 新增状态时改 enum type 需 DROP/CREATE)
- **DBSettings 字段命名**：plan 用 `pool_recycle`，实施改 `pool_recycle_seconds` (与 M0 TEISettings `timeout_seconds` 命名风格一致)

## 4. r2 修复全部到位

- ✅ **NP-1** auth_sessions `is_revoked` (M2 logout 强依赖)
- ✅ **NP-2** users partial unique index (M2 username 复用)
- ✅ **NP-3** auth_sessions `expires_at_hard` 索引 (M2 cleanup job)
- ✅ **P1-1** ingest_jobs `payload_hash` UNIQUE (M4 ON CONFLICT)
- ✅ **P1-5** ingest_jobs status 包含 `indexed` (M4 r2 P1-5)

## 5. 29/29 TDD 通过

```
tests/unit/test_config.py                5 PASSED  0.10s
tests/unit/test_m1_schema.py            16 PASSED  0.38s (3 DBSettings + 8 Models + 5 Alembic)
tests/unit/test_p0_14_init_sql.py        5 PASSED  0.08s
tests/unit/test_p0_16_langfuse_db.py     3 PASSED  0.08s
────────────────────────────────────────────────────
total                                   29 PASSED  0.38s
```

## 6. 5 commits 累计

```
ba1b8ba  M0 infra 实操落地 (24 份)
e0fbf97  M0 P0 实施层修订
7ccfe39  M0 P0 实施层 P0 修补 (P0-14/16/17)
47d36ea  M0 阶段收口报告
M1 实施层 (本 commit)
```

## 7. 待办 (环境就绪后)

- [ ] `make up` 起 5 service
- [ ] `alembic upgrade head` 真 PG 迁移 → 4 表存在
- [ ] 集成测试: INSERT + SELECT 各表 works (M1 plan Task 5)
- [ ] `alembic downgrade base` 回滚验证
- [ ] `alembic check` 验 migration 同步

## 8. 下一步：M2 auth

M1 收口 → M2 auth (4 endpoint + 9 AuthSessionRepository 方法 + 鉴权中间件)。
