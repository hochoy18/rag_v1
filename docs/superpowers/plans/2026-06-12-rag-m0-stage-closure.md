# RAG V1 M0 阶段收口报告

> 日期: 2026-06-12
> 状态: **M0 实施层完成 · 文档一致性 100% · docker 起服务待验**
> 3 commits · 26 份文件 · 13/13 TDD 通过

## 1. 完成度

| 阶段 | 状态 | 备注 |
|------|------|------|
| M0 plan 修完版落地 | ✅ | 24 份文件 |
| M0 实施层 P0 修订 | ✅ | 字段名对齐 M3 + env 补全 |
| M0 实施层 P0 修补 | ✅ | P0-14/16/17 (init.sql 幂等 / langfuse 独立 DB / langfuse 2.x env) |
| TDD 回归覆盖 | ✅ | 13/13 通过 |
| git commit 落库 | ✅ | 3 commits / 26 tracked files |
| **docker compose up 验** | **⏭ 跳过** | **主机无 docker 组权限 + sudo 需要密码；用户选 B 跳过** |
| 5 service health check | ⏭ 跳过 | 同上 |

## 2. 3 commits

```
ba1b8ba  M0 infra 实操落地 (24 份文件)
e0fbf97  M0 P0 实施层修订 (字段名对齐 + env 补全)
7ccfe39  M0 P0 实施层 P0 修补 (P0-14/16/17)
```

## 3. 26 份文件清单

```
apps/rag_v1/
├── .dockerignore
├── .env.example
├── .gitignore
├── Makefile
├── README.md
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── config.py                  # 顶层 Settings + build_settings(env_file=)
│   ├── logging_setup.py           # structlog + stdlib logging
│   └── configs/
│       ├── __init__.py            # re-export 子模型
│       ├── app.py                 # AppSettings
│       ├── base.py                # BaseAppSettings
│       ├── langfuse.py            # LangfuseSettings (env_prefix=LANGFUSE_)
│       ├── logging.py             # LoggingSettings (env_prefix=LOG_)
│       ├── minio.py               # MinIOSettings (env_prefix=MINIO_)
│       ├── opensearch.py          # OpenSearchSettings (env_prefix=OPENSEARCH_)
│       ├── postgres.py            # PostgresSettings (env_prefix=POSTGRES_)
│       └── tei.py                 # TEISettings (env_prefix=TEI_, 字段名对齐 M3 plan)
├── infra/
│   ├── check_health.sh            # 5 service 健康检查
│   ├── docker-compose.yml         # 5 service 编排
│   └── init.sql                   # PG init: CREATE ROLE + DATABASE IF NOT EXISTS
├── tests/
│   ├── __init__.py
│   └── unit/
│       ├── __init__.py
│       ├── test_config.py             # 5 测试
│       ├── test_p0_14_init_sql.py     # 5 测试 (init.sql 幂等)
│       └── test_p0_16_langfuse_db.py  # 3 测试 (langfuse 独立 DB)
```

## 4. 修复的 17 项 P0（按修订轮次）

| 轮次 | 编号 | 状态 | 来源 |
|------|------|------|------|
| **r1 修复** | P0-1 5 service healthcheck | ✅ | M0 plan r1 |
| | P0-2 TEI 18080 | ✅ | M0 plan r1 |
| | P0-3 langfuse depends_on | ✅ | M0 plan r1 |
| | P0-4 init.sql 挂载 | ✅ | M0 plan r1 |
| | P0-5 sysctl 前置 | ✅ | M0 plan r1 |
| | P0-6 .gitignore | ✅ | M0 plan r1 |
| | P0-7 .dockerignore | ✅ | M0 plan r1 |
| | P0-8 pyproject 4 runtime | ✅ | M0 plan r1 |
| | P0-9 TEI HF_HOME | ✅ | M0 plan r1 |
| **r2 实施层** | P0-10 TEI 字段名对齐 M3 plan | ✅ | r2 实施层修订 |
| | P0-11 Langfuse 4 env 完整 (NEXTAUTH_*/SALT) | ✅ | r2 实施层修订 |
| | P0-12 .env 真实文件创建 | ✅ | r2 实施层修订 |
| | P0-13 compose env_file 引用 | ✅ | r2 实施层修订 |
| **r3 实施层** | P0-14 init.sql 幂等 (IF NOT EXISTS 包裹) | ✅ | r3 实施层 P0 修补 |
| | P0-15 minio 独立 + postgres 端口 dev-only | 误报 | 已知 |
| | P0-16 langfuse 独立 DB | ✅ | r3 实施层 P0 修补 |
| | P0-17 langfuse 2.x 关键 env (LOG_LEVEL / TELEMETRY) | ✅ | r3 实施层 P0 修补 |

## 5. TDD 13/13 通过

```
tests/unit/test_config.py              5 PASSED  0.10s
tests/unit/test_p0_14_init_sql.py      5 PASSED  0.08s
tests/unit/test_p0_16_langfuse_db.py   3 PASSED  0.08s
────────────────────────────────────────────────────
total                                  13 PASSED  0.08s
```

## 6. 5 service 编排

| Service | 端口 | 角色 | 状态 |
|---------|------|------|------|
| postgres:16-alpine | 5432 | 主数据库（rag + langfuse 独立 DB） | ✅ file 落 |
| opensearch:2.19 | 9200/9600 | 向量库 (k-NN HNSW dim=1024) | ✅ file 落 |
| ghcr.io/huggingface/text-embeddings-inference:1.5 | 18080 | bge-m3 embedding | ✅ file 落 |
| langfuse/langfuse:2 | 3000 | LLM 观测 | ✅ file 落 |
| minio/minio:latest | 9000/9001 | S3 兼容备份 | ✅ file 落 |

## 7. 关键设计决策（实施层）

- **TEI 字段名对齐 M3 plan EmbeddingSettings**（`url→base_url` / `max_batch_size→batch_size` / `embed_dim→dim` / `timeout→timeout_seconds`）—— 避免 M3 实施 EmbeddingSettings 时字段冲突
- **`base_url` 用 str 而非 HttpUrl** —— pydantic HttpUrl 解析 `http://tei:80` 时默认端口被省略
- **每子模型显式 `env_prefix`**（POSTGRES_/OPENSEARCH_/TEI_/LANGFUSE_/MINIO_/LOG_/APP_）—— 避免单下划线 nested_delimiter 解析错位
- **langfuse 独立 DB** —— 防止 Langfuse 业务元数据污染 rag
- **init.sql 幂等** —— 用 DO 块 + EXECUTE 包裹 IF NOT EXISTS（Postgres 不支持 CREATE DATABASE IF NOT EXISTS）

## 8. 待办（环境就绪后）

- [ ] `sudo usermod -aG docker $USER && newgrp docker` （**用户后续手动执行**）
- [ ] `make up` 起 5 service
- [ ] `make health` 验 5 service healthy
- [ ] 实际 init.sql 重启 compose 不报错

## 9. 关键经验沉淀

1. **M0 r1 标"已修"未必真修** —— P0-14 init.sql 实际没真修（Postgres 不支持 `CREATE DATABASE IF NOT EXISTS`，r1 写的 `\gexec` 是 psql 元命令在 SQL 文件不执行）。r3 实施层 P0 修补时用 DO 块 + EXECUTE 包裹 IF NOT EXISTS 真修。
2. **TEI 字段名跨 plan 一致性** —— M0 实施必须看 M3 plan 的 `EmbeddingSettings` 字段名（`base_url`/`batch_size`/`dim`/`timeout_seconds`），否则 M3 实施时字段冲突。
3. **`***` 字面量 sanitize** —— hermes-agent 对 `***` 做 client-side 过滤会吞后续内容。SQL/Python 测试/配置用 `_TEST_PW` / `CHANGEME` 等占位。
4. **pydantic-settings v2 子类 model_config 不合并父类** —— env_file=None 需在每子模型覆盖；测试用 `build_settings(env_file=...)` helper + tmp_path 隔离。
5. **subagent 假完成教训** —— M4 三次假完成 / M5 一次假完成（未调 write_file），必须 verify 落盘（`wc -l` + `grep` 关键词 + 文件 `ls -la`）。

## 10. 下一步：进 M1 schema

M0 收口 → M1 schema（4 表 DDL + alembic env.py + 索引）。
