# M0 Plan r2 Review · r1 修复验证

> 评审对象：M0 plan `2026-06-10-rag-m0-infra.md`（r1 修订后 · 631 行）
> 评审基线（r1 review）：`2026-06-11-rag-m0-infra-review.md`（659 行 · 26 项 P0/P1/P2）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立 r2 验证）
> 范围：验 r1 修复是否到位（26 项逐项）+ 发现 r1 修复过程中是否引入新问题

---

## 总评

M0 plan 在 r1 之后从「结构对、内容薄」推进到「结构对、内容厚、但**修订记录 vs plan 主体出现 4 处严重自相矛盾** + 至少 2 处主体 bug」。具体三个维度：

| 维度 | 评分 | 说明 |
|------|------|------|
| r1 修复到位率 | ⭐⭐⭐ | 26 项中 22 项主体已落地；但 P0-8 / P1-2 / P2-3 / P2-5 这 4 项的**修订记录文本与 plan 主体文本直接矛盾**，下游实施者以谁为准无法判断 |
| 跨 M 一致性 | ⭐⭐⭐ | M0↔M3 TEI 端口 18080 / M0↔M1 PG password / M0↔M10 Langfuse NEXTAUTH_* 均对齐；M0 内部子目录 X-1 落地但 P2-3 修订记录仍写「待 M7 拍板」产生自相矛盾 |
| 风险表补全 | ⭐⭐⭐⭐ | 6 行原风险保留 + 22 行 r1-2026-06-11 已修行；量化指标已补；但「曾被否决的替代方案」列在 r1 已修行里都写「r1-2026-06-11」无意义 |
| r1 引入新问题 | ⚠️ 4 处 | 修订记录失实（P0-8 / P1-2 / P2-3 / P2-5）+ `.env.example` 主体 bug（LANGFUSE_SECRET_KEY 重复）+ P1-7/P1-8 修订记录笔误 |

**一句话**：r1 修复**质量尚可但文档一致性塌方**——若直接照 plan 实施，开发者会按主体走（OK），但按修订记录理解会严重误判（langchain 36 包 / 密码变量插值 / X-1 推迟 M7 / 错误 DSN 字符串）。**建议 r2 修补修订记录 4 处失实 + 修 LANGFUSE_SECRET_KEY 重复 + 修 P1-7/P1-8 笔误后，可动手。**

---

## 1. r1 修复验证（26 项逐项）

| r1 标记 | 修复内容 | 实际验证（plan 主体） | 状态 |
|---------|---------|----------------------|------|
| P0-1 | 4 service healthcheck + langfuse depends_on service_healthy | Task 1 L203/211/220/227 healthcheck 块齐全；L229 depends_on 链完整 | ✅ 到位 |
| P0-2 | TEI 端口 18080:80 | Task 1 L216 `18080:80` + README L427 `localhost:18080` + .env.example L275 `TEI_URL=http://tei:80` | ✅ 到位 |
| P0-3 | langfuse depends_on postgres service_healthy | Task 1 L229 langfuse depends_on 含 postgres/opensearch/tei 三条 service_healthy | ✅ 到位（与 P0-1 合并） |
| P0-4 | init.sql 挂载 /docker-entrypoint-initdb.d/ | Task 1 L202 `./init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro` | ✅ 到位 |
| P0-5 | README sysctl vm.max_map_count 前置 | Task 6 L415-419 完整 sysctl 命令 + 持久化 | ✅ 到位 |
| P0-6 | .gitignore | Task 7 L433-467 完整 30+ 行 .gitignore 内容 | ✅ 到位 |
| P0-7 | .dockerignore | Task 8 L469-494 完整 .dockerignore 内容 | ✅ 到位 |
| **P0-8** | pyproject.toml 完整内容 | **Task 4 L358-390 给完整 pyproject.toml**，dependencies = pydantic / pydantic-settings / python-dotenv / structlog（**不含 langchain/langgraph/llama-index**） | ✅ 主体到位 / ⚠️ **修订记录 L612 失实**（写「langchain==1.0.8 / langgraph==1.0.5 / llama-index==0.14.8 等 36 包」，与主体矛盾） |
| P0-9 | TEI HF_HOME/TRANSFORMERS_CACHE=/data 挂载 | Task 1 L218-219 env 完整 + volumes `tei_cache:/data` | ✅ 到位 |
| P1-1 | mem_limit / cpus（PG 512m / OS 2g / TEI 4g / LF 1g） | Task 1 L204/212/221/228 4 service 全有 | ✅ 到位 |
| **P1-2** | init.sql 密码 dev-only + IF NOT EXISTS 包裹 | Task 2 L239-253 完整 dev-only 注释 + DO $$ ... IF NOT EXISTS ... END $$ | ✅ 主体到位 / ⚠️ **修订记录 L615 失实**（写「`${POSTGRES_PASSWORD}` 变量插值」，**init.sql 在 initdb 阶段执行，env 不可用**——主体方案正确，修订记录方案是错误） |
| P1-3 | Langfuse NEXTAUTH_URL + NEXTAUTH_SECRET | Task 1 L226 含 NEXTAUTH_URL=${LANGFUSE_NEXTAUTH_URL} + .env.example L289-290 + Task 4 L310 LangfuseSettings 字段 | ✅ 到位 |
| P1-4 | OpenSearch env 完整 + ulimits | Task 1 L209-210 env 全 + ulimits memlock/nofile 齐 | ✅ 到位 |
| P1-5 | POSTGRES_INITDB_ARGS 显式声明 | Task 1 L201 `POSTGRES_INITDB_ARGS=--encoding=UTF-8 --locale=C` | ✅ 到位 |
| P1-6 | logging_setup.py + structlog 依赖 | Task 4 L311 LoggingSettings + L344-356 logging_setup.py 实现 + pyproject.toml L369 structlog 依赖 | ✅ 到位 |
| P1-7 | infra/check_health.sh + Files 表 | Files 表 L162 含 + Task 9 L496-510 完整 shell 脚本 | ✅ 主体到位 / ⚠️ **修订记录 L620 失实**（写「5 service 状态」但 plan 实际是 **4 service**；M0 只有 PG/OS/TEI/Langfuse 4 个） |
| P1-8 | Makefile 收录常用命令 | Task 10 L512-525 Makefile + Files 表 L182 | ✅ 主体到位 / ⚠️ **修订记录 L621 失实**（写「`make up / down / logs / test / migrate / check`」但主体 Makefile 是 `up / down / logs / health / test-unit / test-integration / clean`，**无 migrate / check**，migrate 是 M1 范畴） |
| P1-9 | app/config.py 末尾 settings = Settings() 全局单例 | Task 4 L328 `settings = Settings()` | ✅ 到位 |
| P2-1 | docker-compose 删 version: 改 name: | Task 1 L197 `name: rag_v1`，无 version 字段 | ✅ 到位 |
| P2-2 | 头部加「范本目的」段 | L8「范本目的：M0 是 RAG V1 路线起点 plan ...」 | ✅ 到位 |
| **P2-3** | app/config.py 拆分（X-1 落地） | Task 4 L299 「P2-3 / X-1 落地：M0 直接拆 `app/configs/` 子目录」+ 仓库布局 L42 + Files 表 L165-170 | ✅ 主体到位 / ⚠️ **修订记录 L625 失实**（写「X-1 决议待落地，文档标注等 M7 拍板」，与主体「X-1 落地」直接矛盾） |
| P2-4 | Task 4 RED 测试补类型校验 | Task 4 L336-342 test_settings_type_validation RED 用例 | ✅ 到位 |
| **P2-5** | .env.example LANGFUSE_DATABASE_URL 合法占位 | Task 3 L287 `postgresql://rag_app:***@postgres:5432/rag`（注：P2-5 修占位，但 `***` 仍非真实密码） | ⚠️ **半到位** / ⚠️ **修订记录 L627 失实**（写「`postgresql://postgres:***@postgres:5432/langfuse`」——用户名写成 `postgres`、DB 名写成 `langfuse`，**与主体 `rag_app` / `rag` 完全不一致**；且 Langfuse v2 默认用自己 DB 不是 `rag`） |
| P2-6 | Task 1 估时 5min → 25min | Task 1 L194 「实测 20-30 分钟 ... 调整为 25 分钟」 | ✅ 到位 |
| P2-7 | DoD 拆 warm-cache (3min) / cold-start (10min) | DoD L541-551 两档分明 | ✅ 到位 |
| P2-8 | 风险表每行加量化指标 | 风险表 L585-591 + 6 行量化（容器重试次数 / 超时 / 资源上下界 / cold start 时长） | ✅ 到位 |
| 估时 | M0 整体 2d → 3d | L7 估时修正「3 个工作日（r1 修正：2d 估时不计 cold-start 镜像下载 + P0/P1 修补，实际 3d）」 | ✅ 到位 |

**汇总**：26 项 r1 修复中
- 22 项**主体到位 + 修订记录与主体一致**
- 4 项**主体到位但修订记录文本失实**（P0-8 / P1-2 / P2-3 / P2-5）
- 1 项**半到位**（P2-5：`***` 仍非真实密码，但 r1 标的修改确实是「加注释 + 改占位」，没承诺改真实密码——这点偏严苛，但 .env.example 仍含 `***` 是 r1 已知遗留）
- 0 项**主体未改**

---

## 2. r1 修复引入的新问题

### 2.1 ⚠️ 修订记录失实（4 处严重）

**问题等级**：**r2 P0**——下游实施者可能照修订记录误判

| 修订位置 | 修订记录原文（错的） | plan 主体实际内容（对的） | 影响 |
|---------|-------------------|------------------------|------|
| L612 P0-8 | `pyproject.toml 完整内容（langchain==1.0.8 / langgraph==1.0.5 / llama-index==0.14.8 等 36 包 + dev 依赖 pytest 全套）` | Task 4 L365-370 完整 pyproject.toml：dependencies 仅 `pydantic / pydantic-settings / python-dotenv / structlog` | 若按修订记录装 36 包，**M0 冷启动慢 + M1/M2/M8 难以介入**（与主体 P0-8 决议「fastapi/uvicorn/sqlalchemy 留给 M1/M2/M8」完全冲突） |
| L615 P1-2 | `init.sql 注释密码为 ${POSTGRES_PASSWORD} 变量插值（避免明文 + 多环境隔离）` | Task 2 L246-250 主体仍是明文 `'rag_app_password'` + dev-only 注释 | 若按修订记录改 `${POSTGRES_PASSWORD}`，**Postgres initdb 阶段 docker-entrypoint-initdb.d 不会从 env 读变量**（该目录是 `psql -f` 执行 SQL 脚本，**不是 shell**），会产生语法错误 / password 设为字面 `${POSTGRES_PASSWORD}` 字符串。修订记录方案**逻辑错误** |
| L625 P2-3 | `app/config.py 拆分决策点（X-1 决议待落地，文档标注等 M7 拍板）` | Task 4 L299 明确写「P2-3 / X-1 落地：M0 直接拆 `app/configs/` 子目录」 | 若按修订记录理解等 M7 拍板，**M0 不拆子目录**——会与 Files 表 L165-170（已列 6 个子文件）+ 仓库布局 L42（已画 configs/ 子目录）+ Task 4 GREEN L305（已在 configs/ 下实现）全部冲突。**主体已落地，修订记录未更新** |
| L627 P2-5 | `.env.example 加 LANGFUSE_DATABASE_URL=postgresql://postgres:***@postgres:5432/langfuse 注释` | Task 3 L287 主体是 `postgresql://rag_app:***@postgres:5432/rag` | 修订记录方案**用错用户名（postgres→rag_app）+ 用错 DB 名（langfuse→rag）**。Langfuse v2 推荐独立 DB（通常叫 `langfuse`），但 r1 主体决定复用 M0 的 `rag` DB（dev 简化）。**两条方案不可调和**——下游开发者按修订记录改完会与 init.sql 的 `rag` DB 脱钩 |

**统一建议**：r2 修补修订记录 L612 / L615 / L625 / L627，让其与 plan 主体完全一致。**不允许两条方案并存**。

### 2.2 ⚠️ `.env.example` 主体 bug（1 处）

**问题等级**：**r2 P0**——M0 启动即会报错

| 位置 | bug | 影响 |
|------|------|------|
| L284-285 `.env.example` | `LANGFUSE_SECRET_KEY=sk-lf-...lder` 和 `LANGFUSE_SECRET_KEY=***=sk-lf-...lder` **出现两次**（疑似 r1 复制粘贴失误，第二次把 `***` 误当掩码插到 secret key 前面） | `docker compose up` 启动 langfuse 时 pydantic-settings 加载 .env 会**抛 ValidationError**（SecretStr 同名变量重复 / 或第二次把 `***=` 字面量当真值）；LANGFUSE 容器起不来 |

**L284-285 原文**：
```
LANGFUSE_SECRET_KEY=sk-lf-...lder
LANGFUSE_SECRET_KEY=***=sk-lf-...lder
```

**修复**：删 L285 整行（保留 L284 一行）。

### 2.3 ⚠️ P1-7 / P1-8 修订记录笔误

| 修订位置 | 修订记录原文 | 实际 | 严重度 |
|---------|-----------|------|-------|
| L620 P1-7 | `infra/check_health.sh 加进 Files 表（5 service 状态一行一查）` | M0 只有 4 service（PG/OS/TEI/Langfuse） | 低（笔误） |
| L621 P1-8 | `Makefile 收录 make up / down / logs / test / migrate / check 常用命令` | 主体 Makefile 是 `up / down / logs / health / test-unit / test-integration / clean`（**无 migrate / check**） | 中（migrate 暗示 M1 范畴被错引） |

**建议**：r2 同步修订记录文本与 Makefile / check_health.sh 实际命令名对齐。

### 2.4 r1 修复本身不引入新问题（仅 1 项遗留）

- **P2-5 半到位**：`LANGFUSE_DATABASE_URL` 占位仍是 `***`，而非真实 `rag_app_password`——但 r1 P2-5 标的是「**加注释 + 改占位**」（review P2-5 原文），没承诺改真实密码。`.env.example` 模板用 `***` 是合理做法，开发者复制后自行替换。**r2 不必再追**。
- **风险表行 r1-2026-06-11 的「曾被否决的替代方案」列**：写了 4 行 `r1-2026-06-11`（L592-595）——这列原本是「**说明为何不选其他方案**」，4 个 r1 修复行写「r1-2026-06-11」是**无意义**（修复本身没有「曾被否决的替代方案」）。**r2 建议**把 r1 已修行的「曾被否决的替代方案」列改为 `—`（不适用）或干脆合并到「缓解」列。

---

## 3. 跨 M 一致性检查

### 3.1 M0 ↔ M1（schema 迁移）

| 共享契约 | M0 主体 | M1 预期 | 一致？ |
|---------|--------|--------|-------|
| `postgres:5432` 容器名 | Task 1 L200 `ports: 5432:5432` + service name `postgres` | M1 Alembic 需 `postgresql://rag_app:***@postgres:5432/rag` | ✅ 一致（service name DNS 直连） |
| `rag` DB 存在 | Task 2 L244 `CREATE DATABASE rag` + init.sql 挂载到 docker-entrypoint-initdb.d | M1 alembic env.py 需 `dbname=rag` | ✅ 一致（**前提是 r1 P0-4 挂载点 L202 不被破坏**） |
| `POSTGRES_PASSWORD=rag_app_password` | Task 1 L200 env | M1 alembic env.py 需同 password | ✅ 一致（**但 r1 P1-2 修订记录写「`${POSTGRES_PASSWORD}` 变量插值」**——若误信，跨 M 一致性破坏） |
| `POSTGRES_INITDB_ARGS=--encoding=UTF-8 --locale=C` | Task 1 L201 | M1 migration 用 `citext` / `pg_trgm` 等 locale-sensitive 需 locale=C | ✅ 一致（**M1 alembic 升级时** locale-C 不影响 schema） |
| `app/config.py` 全局单例 `settings = Settings()` | Task 4 L328 | M1 alembic env.py `from app.config import settings` | ✅ 一致（X-3 决议落地） |
| `app/configs/postgres.py` PostgresSettings | Task 4 L307 | M1 引用 `settings.postgres.host` 等 | ✅ 一致（X-1 落地） |

### 3.2 M0 ↔ M2（auth 鉴权）

| 共享契约 | M0 主体 | M2 预期 | 一致？ |
|---------|--------|--------|-------|
| `postgres:5432` 容器 | 同上 | M2 读写 `users` / `auth_sessions` 表（在 `rag` DB 内） | ✅ |
| `app/configs/postgres.py` | 同上 | M2 扩展 `PostgresSettings` 加 `auth_db: str = 'rag'` | ✅（X-1 子目录方案支持扩展） |
| `app/config.py` 单例 | 同上 | M2 引用 `settings.postgres.password.get_secret_value()` | ✅ |
| **未发现 init.sql 与 M2 冲突** | — | M2 需 `users` / `auth_sessions` 表，但 schema 迁移归 M1 负责 | ✅ 边界清晰 |

### 3.3 M0 ↔ M3（LLM/Embed 工厂）

| 共享契约 | M0 主体 | M3 预期 | 一致？ |
|---------|--------|--------|-------|
| TEI 容器端口 `tei:80`（容器内） | Task 1 L216 `18080:80` + .env.example L275 `TEI_URL=http://tei:80` | M3 引用 `TEI_URL` 调 embed | ✅ |
| TEI host 端口 18080 | README L427 `localhost:18080` + check_health.sh L506 | M3 smoke test 走 host 端点 | ✅ |
| `tei_cache` volume /data | Task 1 L218-219 | M3 复启动后不重下 bge-m3 | ✅ |
| Langfuse `langfuse:3000` 容器内端口 | Task 1 L225 + .env.example L282 | M3 trace 上报 | ✅ |
| Langfuse NEXTAUTH_* | Task 1 L226 | M3 用 public/secret key 调 Langfuse Python SDK | ✅ |
| **未发现 M3 与 M0 冲突** | — | — | ✅ |

### 3.4 M0 ↔ M10（Langfuse 观测）

| 共享契约 | M0 主体 | M10 预期 | 一致？ |
|---------|--------|--------|-------|
| `langfuse:3000` 服务名 | Task 1 L225 | M10 在 app 代码内调 Langfuse SDK 上报 trace | ✅ |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | .env.example L283-284 | M10 应用层 SDK 读 env | ✅（**前提 L284-285 重复 bug 修掉**） |
| `LANGFUSE_DATABASE_URL=postgresql://rag_app:***@postgres:5432/rag` | Task 3 L287 | M10 不直接连 DB（Langfuse 容器内连），无需改 | ✅ |
| **未发现 M10 与 M0 冲突** | — | — | ✅ |

### 3.5 M0 内部一致性（plan 自身）

| 检查项 | 结果 |
|--------|------|
| LANGFUSE_NEXTAUTH_URL 出现在 Task 1 / .env.example / LangfuseSettings 三处 | ✅ 三处一致（Task 1 L226 / .env.example L290 / Task 4 L310） |
| LANGFUSE_SECRET_KEY 在 .env.example 出现两次 | ❌ 重复（见 2.2） |
| `app/configs/` 子目录在 Architecture / Files / Tasks / DoD / 风险表 五处出现 | ✅ 五处一致（X-1 落地完整） |
| TEI 端口 18080 在 Task 1 / .env.example / README / check_health.sh / 风险表 / DoD 六处出现 | ✅ 六处一致 |
| mem_limit 在 Task 1 + 风险表 L591 出现 | ✅ 一致（PG 512m / OS 2g / TEI 4g / LF 1g） |
| init.sql 挂载点 `/docker-entrypoint-initdb.d/01-init.sql:ro` | Task 1 L202 出现一次 | ✅ 唯一 |
| `POSTGRES_INITDB_ARGS=--encoding=UTF-8 --locale=C` | Task 1 L201 + 风险表 L589 两处 | ✅ 一致 |
| 修订记录 vs 主体一致性（P0-8 / P1-2 / P2-3 / P2-5） | ❌ **4 处矛盾**（见 2.1） |

---

## 4. 风险表补全质量

### 4.1 完整性

| 维度 | 原 r0 风险表 | r1 修订后 | 评估 |
|------|------------|---------|------|
| 风险行数 | 6 行原风险 | 6 行原风险保留 + 4 行 r1-2026-06-11 P?-X 已修 | ✅ 原风险未被覆盖 |
| 量化指标 | 全是抽象缓解（如「失败则重试」） | L585-591 六行原风险全部加量化（容器重试次数 / 超时 / 资源上下界 / cold start 时长 / port 冲突检测脚本） | ✅ P2-8 到位 |
| 曾被否决的替代方案列 | 6 行原风险都有（如 OpenSearch 替代 ES8 / SaaS / k8s / PostHog） | 原 6 行保留；4 行 r1 已修行写 `r1-2026-06-11` 占位 | ⚠️ **r1 已修行的「替代方案」列无意义**——修复行为本身没有「被否决的替代方案」（L592-595） |
| 风险类型分布 | 启动 / 端口 / 迁移 / 兼容性 / 布局 / 资源 6 类 | 同 + 4 行「修复确认」 | ✅ 覆盖到位 |

### 4.2 r1 修补记录单条核对（22 行已修行的「缓解」列内容是否与 plan 主体一致）

| r1 修订行 | 风险表「缓解」列内容 | plan 主体是否落地 | 一致？ |
|----------|------------------|----------------|-------|
| P0-1 已修（L592） | 4 service healthcheck + depends_on chain | ✅ | ✅ |
| P0-2 ~ P0-9 已修（L593） | TEI 18080 / HF_HOME / init.sql 挂载 / sysctl / .gitignore / .dockerignore / pyproject | ✅ | ✅ |
| P1-1 ~ P1-9 已修（L594） | mem_limit / IF NOT EXISTS / NEXTAUTH_* / OPENSEARCH_JAVA_OPTS / POSTGRES_INITDB_ARGS / logging_setup / check_health.sh / Makefile / settings 单例 | ✅ | ✅ |
| P2-1 ~ P2-8 已修（L595） | name: rag_v1 / 范本目的 / X-1 落地 / 类型校验 / 合法占位 / 估时 / DoD 拆档 / 量化指标 | ⚠️ 4 项与修订记录文本不一致（见 2.1） | ⚠️ **半一致** |

### 4.3 风险表整体评估

- **优点**：原 6 行风险保留、量化指标补全、4 行 r1 修复行提供变更轨迹
- **缺点**：
  1. 4 行 r1 修复行的「缓解」列写得过细、应有指向 plan 主体位置的链接（如 `Task 1 L202`）而非堆在风险表
  2. r1 已修行的「曾被否决的替代方案」列写 `r1-2026-06-11` 无意义
  3. 4 行 r1 已修行的「缓解」文本与修订记录文本有微小差异（risk L595 P2-1~8 写「`***` 改 `rag_app_password`」实际主体仍 `***`）

**建议**：r2 把 4 行 r1 已修行的「缓解」列简化为「详见本文 §Tasks 1-10 对应位置 + 修订记录 P?-X」指针形式，避免与 plan 主体文本不同步时双重失实。

---

## 5. 落地建议

### 5.1 r2 必改（4 项 r2 P0，**修完才可动手**）

按修复代价从小到大：

1. **r2 P0-A · 删 L285 重复行**：`LANGFUSE_SECRET_KEY=***=sk-lf-...lder` 整行删除（10 秒）
2. **r2 P0-B · 修 P1-7 修订记录**：L620 改「5 service 状态」→「4 service 状态」+ 指 check_health.sh 实际内容（30 秒）
3. **r2 P0-C · 修 P1-8 修订记录**：L621 改命令列表为「`up / down / logs / health / test-unit / test-integration / clean`」+ 删「migrate」（30 秒）
4. **r2 P0-D · 修 4 处修订记录失实**（L612 / L615 / L625 / L627）：
   - L612 P0-8 改「`pyproject.toml 完整内容（见 Task 4 L358-390；含 pydantic / pydantic-settings / python-dotenv / structlog + dev pytest，**不含 langchain / langgraph / llama-index**）」
   - L615 P1-2 改「`init.sql 注释密码为 dev-only 明文 + IF NOT EXISTS 包裹（initdb 阶段 env 不可用，**不**能用 `${POSTGRES_PASSWORD}` 变量插值）」——同时**解释为何不变量插值**
   - L625 P2-3 改「`app/config.py` 拆分（X-1 **已落地**：M0 直接拆 `app/configs/` 子目录，详见 Task 4 L299-330 + Files 表 L165-170）」
   - L627 P2-5 改「`.env.example` 加 `LANGFUSE_DATABASE_URL=postgresql://rag_app:***@postgres:5432/rag` 注释（**复用 M0 的 `rag` DB；不创建独立 `langfuse` DB**——dev 简化）」

### 5.2 r2 建议改（3 项 r2 P2，**可下轮改**）

1. **r2 P2-A · 风险表 4 行 r1 已修行的「替代方案」列**：改为 `—` 或合并到「缓解」列
2. **r2 P2-B · 风险表 4 行 r1 已修行的「缓解」列**：改为指针形式（如 `详见 Task 1 L202-229`），减少与 plan 主体重复失实风险
3. **r2 P2-C · P2-5 `.env.example`**：把 `***` 改 `rag_app_password` 真实值（让 docker compose up 一次成功；否则开发者得手动改 .env）

### 5.3 r2 不必改

- 26 项 r1 修复中 22 项主体已落地且与修订记录一致，**不需重做**
- 跨 M 一致性（M0↔M1/M2/M3/M10）**全部对齐**，不需跨 M 协调
- 估时 3d 修正**合理**，不需调

### 5.4 估时修正

- r2 修补：估 **30-60 分钟**（4 处修订记录失实 + 1 处主体 bug + 3 处笔误）
- r2 修补 + verify：估 **1 个工作日**
- M0 整体仍 **3d**（r1 修正后估时不变）

### 5.5 跨 M 协调（M0 改完后通知）

- 通知 M1：`POSTGRES_PASSWORD=rag_app_password`（明文固定，不变量插值；M1 alembic env.py 需用同 password）
- 通知 M2 / M3 / M7 / M10：`from app.config import settings` 语法（X-3 已落地）+ `app/configs/` 子目录可扩展（X-1 已落地）
- 通知 M3：TEI 容器内端口 80 / host 端口 18080（容器间互访用 `tei:80`，host 走 `localhost:18080`）

---

## 状态

- **r1 修复完成度**：26 项中 22 项到位、4 项主体到位但修订记录失实
- **r1 引入新问题**：4 处修订记录失实 + 1 处主体 bug（`LANGFUSE_SECRET_KEY` 重复）+ 2 处笔误（P1-7 5 service / P1-8 migrate）
- **跨 M 一致性**：全部对齐
- **风险表补全**：原 6 行保留 + 量化指标补全；但 4 行 r1 已修行的「替代方案」列无意义
- **建议**：r2 修补 4 处修订记录失实 + 1 处主体 bug + 2 处笔误后（约 30-60 分钟），**可动手**
- **不可直接动手**：L284-285 `LANGFUSE_SECRET_KEY` 重复会导致 langfuse 容器起不来（**r2 P0 阻塞**）

M0 plan **结构完整、跨 M 对齐、22/26 r1 修复到位**，但**修订记录自相矛盾 + 1 处主体 bug** 需 r2 修补后才是「真正可动手」状态。
