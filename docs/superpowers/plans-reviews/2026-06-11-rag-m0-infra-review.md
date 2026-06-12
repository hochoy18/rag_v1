# M0 Plan Review · 基础设施层

> 评审对象：M0 (2026-06-10-rag-m0-infra.md, 313 行)
> 评审基线：V1 Scope v0.4 spec（决策表 / §1 / §5 / §7 / §8）+ 已有 review 报告 + M3 范本（11 段模板）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

## 总评

M0 plan 按 M3 范本 11 段走齐（Goal / 不包含 / Architecture / Tech Stack / Files / Tasks / 测试 / DoD / 依赖 / 风险 / 修订记录），但**缺"范本目的"段**、**多处就绪度不足**——单 docker-compose.yml 一段就要补 healthcheck × 4 + depends_on + resource limits + 完整 env，不止 5 分钟。

|| 维度 | 评分 | 说明 |
|---|---|---|---|
| 结构完整性 | ⭐⭐⭐⭐ | 11 段都齐，唯缺"范本目的"段 |
| 一致性 | ⭐⭐⭐ | 端口、env、service name 与 spec §8 对齐；但 LANGFUSE_NEXTAUTH_* / TEI cache path 漏 |
| 实施就绪度 | ⭐⭐ | Tasks 粒度看似 2-5 分钟，实测会爆（Task 1 完整 compose ≥ 20 分钟）；DoD 部分项弱 |
| 错误处理 | ⭐⭐⭐ | spec §5 错误矩阵在 M0 范围有 3 条触及（OS/PG/TEI 启动失败），plan 只在风险表一笔带过 |
| TDD 标注 | ⭐⭐⭐⭐⭐ | 基础设施 GREEN / 业务 RED-GREEN 区分清晰 |
| 跨 M 契约 | ⭐⭐⭐ | 契约表清晰，但 config.py 单例、X-1 拆分未决留下隐患 |

**一句话**：plan 框架对、内容薄；启动前需补至少 8 个 P0。**已可读、可派工，但不可直接动手。**

---

## P0 · 阻塞级（动手前必改）

### P0-1 · docker-compose.yml 缺 healthcheck 块（4 服务全无）

**位置**：M0 Task 1 GREEN 段（仅写 image/ports/env/network/volumes，无 healthcheck）

**问题**：
- 4 个容器全无 `healthcheck` 块 → Langfuse `depends_on: condition: service_healthy` 没法工作
- M3 smoke test 启动后立即调 TEI/Langfuse，TEI 冷启动 30-60s 模型加载，没 healthcheck 会 race condition
- 已有 review P0-3 已建议，本次 verify **仍未改**

**修改**（追加到 4 个 service 各自下）：
```yaml
  postgres:
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U rag_app -d rag"], interval: 5s, timeout: 3s, retries: 10 }
  opensearch:
    healthcheck: { test: ["CMD-SHELL", "curl -fs http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=2s || exit 1"], interval: 10s, timeout: 5s, retries: 12, start_period: 30s }
  tei:
    healthcheck: { test: ["CMD-SHELL", "curl -fs http://localhost:80/health || exit 1"], interval: 10s, timeout: 5s, retries: 12, start_period: 60s }
  langfuse:
    healthcheck: { test: ["CMD-SHELL", "curl -fs http://localhost:3000/api/public/health || exit 1"], interval: 10s, timeout: 5s, retries: 12, start_period: 30s }
```

---

### P0-2 · TEI 端口 8080 本机冲突风险（plan 自警未解决）

**位置**：M0 Task 1（`ports: "8080:80"`）+ 风险 L302

**问题**：
- plan 自己写"8080 本机已有"作已知风险，但没给默认避雷方案
- 8080 = python http.server / Node dev / Spring 常见端口，冲突概率高
- 已有 review P0-1 已建议改 `18080:80`，本次 verify **未改**

**修改**：
- 默认改 `ports: "18080:80"`
- `.env.example` 的 `TEI_URL=http://tei:8080` 不变（容器内端口），但 README 注 host 走 `localhost:18080`
- README 注明"如 18080 也占用，改 `18090:80` 并同步 .env"

---

### P0-3 · Langfuse 缺 `depends_on: postgres condition: service_healthy`

**位置**：M0 Task 1（langfuse service 定义段）

**问题**：
- 风险 L303 写"设 `depends_on: postgres: condition: service_healthy`"——Task 1 实际**没加**
- Langfuse v2 启动自带 DB migration，会立刻试连 PG；PG 未 init 完成则 Langfuse 反复重连刷日志，health 失败

**修改**：
```yaml
  langfuse:
    depends_on:
      postgres: { condition: service_healthy }
      opensearch: { condition: service_started }
```

---

### P0-4 · init.sql 漏挂载到 `/docker-entrypoint-initdb.d/`

**位置**：M0 Task 1（postgres volumes 段）+ Task 2（init.sql 内容）

**问题**：
- Postgres 官方约定：`/docker-entrypoint-initdb.d/*.sql` 才会自动执行
- Task 1 volumes 段只说 `pg_data` 持久化，**完全没说** init.sql 挂载
- 不挂载 → `CREATE DATABASE rag` 不执行 → M1/M2/M7 全连不上 `rag` DB

**修改**：
```yaml
  postgres:
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
```

---

### P0-5 · README 启动步骤缺 `vm.max_map_count` 前置

**位置**：M0 Task 6 README

**问题**：
- 风险 L300 写"需 `vm.max_map_count=262144`，README 显式写 sysctl 前置"——Task 6 实际**没写**
- OpenSearch 容器启动时 host 没设这个值会立刻报 `max virtual memory areas vm.max_map_count [65530] is too low` 然后 exit
- 新人 100% 卡这里，浪费 30 分钟 google

**修改**（README 启动步骤前置）：
```bash
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
```

（已有 review P1-1 已提，本次 verify 未改）

---

### P0-6 · 缺 `.gitignore`

**位置**：M0 plan 整篇未提及

**问题**：
- `.env`（含密码）/ `__pycache__` / `.venv` / `*.db` / `artifacts/` / `infra/pg_data/` 这些**必须** ignore
- 不写 → 新人 `git add .` 后 push → 密码泄漏 / 大文件污染 repo
- 已有 review P0-9 已建议，本次 verify **仍未改**

**修改**（新增 Task 7）：
```gitignore
# env
.env
.env.local
.env.*.local
!.env.example
# python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/
# venv
.venv/ venv/ env/
# db
*.db *.sqlite *.sqlite3
# artifacts
artifacts/ uploads/
# os/editor
.DS_Store .idea/ .vscode/
# coverage
.coverage htmlcov/
```

---

### P0-7 · 缺 `.dockerignore`（新发现）

**位置**：M0 plan 未提及

**问题**：
- M3 之后可能加自定义 app 镜像，不写 `.dockerignore` 会把 `.venv`（几百 MB）/ `__pycache__` / `.git` 打进 build context
- 当前虽然 M0 没自定义 build，但 TEI 启动会拉取镜像 + M3 起的 smoke test 会 build context，预留总是对的

**修改**（新增 Task 8）：
```dockerignore
.git .gitignore
.env .env.* !.env.example
__pycache__ *.py[cod]
.pytest_cache .mypy_cache .ruff_cache
.venv venv env
*.egg-info
.coverage htmlcov
artifacts uploads
docs *.md !README.md
```

**注**：这是 review 报告**新发现的**，不在已有 review 列表里。

---

### P0-8 · pyproject.toml 内容完全未给出

**位置**：M0 Task 4 GREEN 段

**问题**：
- Task 4 写"pyproject.toml 依赖 base 栈（fastapi + uvicorn + pydantic + sqlalchemy）"——但 GREEN 段**没列文件内容**
- 已有 review P0-8 指出 M0 根本不用 fastapi/uvicorn/sqlalchemy，纯属过度装包
- 已有 review P2-2 指出 `[project]` 块全 plan 缺

**修改**（Task 4 GREEN 段给完整 pyproject.toml）：
```toml
[project]
name = "rag-v1"
version = "0.1.0"
requires-python = ">=3.11"
readme = "README.md"
dependencies = [
  "pydantic>=2.7,<3",
  "pydantic-settings>=2.3,<3",
  "python-dotenv>=1.0,<2",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.24,<1",
  "pytest-cov>=5.0,<7",
]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short --strict-markers"
```

M0 阶段只装 pydantic/pydantic-settings/python-dotenv；fastapi/uvicorn/sqlalchemy 留给 M1/M2/M8 按需加。

---

### P0-9 · TEI 容器缺 HF_HOME / TRANSFORMERS_CACHE 挂载路径（新发现）

**位置**：M0 Task 1（TEI service）

**问题**：
- TEI 首次启动要下载 bge-m3（~2.3GB），风险 L301 说"CI 缓存 tei_cache volume"——但 Task 1 volumes 段写的 `tei_cache` **没指定挂载路径**
- TEI 默认模型缓存路径在容器内 `/data`，不是 host volume
- volume 名字建了但没 mount → 模型每次启动重下，CI 没法用

**修改**：
```yaml
  tei:
    volumes:
      - tei_cache:/data
    environment:
      HF_HUB_DISABLE_TELEMETRY: "1"
      HF_HOME: /data
      TRANSFORMERS_CACHE: /data
```

**注**：这是 review 报告**新发现**的。

---

## P1 · 重要

### P1-1 · 缺 docker-compose 资源限制（mem_limit / cpus）

**位置**：M0 Task 1

**修改**（4 个 service 各加 `mem_limit` / `cpus`）：
```yaml
  postgres:    { mem_limit: 512m, cpus: "1.0" }
  opensearch:  { mem_limit: 2g,   cpus: "2.0" }
  tei:         { mem_limit: 4g,   cpus: "2.0" }
  langfuse:    { mem_limit: 1g,   cpus: "1.0" }
```

TEI 加载 bge-m3 峰值 4-5 GB，OS JVM 1-2 GB，不限资源本机易 OOM。（已有 review P1-2 已提，本次 verify 未改）

---

### P1-2 · init.sql 密码明文

**位置**：M0 Task 2

**问题**：
- `CREATE ROLE rag_app WITH LOGIN PASSWORD 'rag_app_password';` —— 明文
- v0.4 整体强调 argon2id / token SHA-256 调性下不一致

**修改**（dev-only 标注 + 防重复执行）：
```sql
-- dev only，prod 走 secret manager
CREATE DATABASE rag;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='rag_app') THEN
    CREATE ROLE rag_app WITH LOGIN PASSWORD 'rag_app_password';
  END IF;
END $$;
GRANT ALL PRIVILEGES ON DATABASE rag TO rag_app;
```

（已有 review P1-3 已提）

---

### P1-3 · Langfuse 缺 `NEXTAUTH_URL` 和 `NEXTAUTH_SECRET`（新发现）

**位置**：M0 Task 1（langfuse env）+ Task 3（`.env.example`）

**问题**：
- Langfuse v2 **必需** `NEXTAUTH_SECRET`（≥32 字符）+ `NEXTAUTH_URL` 才能完成 NextAuth 初始化
- Task 1 步骤只写 `DATABASE_URL` / `NEXTAUTH_SECRET` / `SALT`——**漏 NEXTAUTH_URL**
- `.env.example` L202-206 同样缺这两个 key

**修改**（`.env.example` Langfuse 段补）：
```
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=pk-lf-dev-placeholder
LANGFUSE_SECRET_KEY=sk-lf-dev-placeholder-min-32-chars-required
LANGFUSE_NEXTAUTH_SECRET=dev-secret-change-me-min-32-chars-please
LANGFUSE_NEXTAUTH_URL=http://localhost:3000
LANGFUSE_DATABASE_URL=postgresql://rag_app:rag_app_password@postgres:5432/rag
```

compose env 同步补 `NEXTAUTH_URL: ${LANGFUSE_NEXTAUTH_URL}`。

**注**：review 报告**新发现**。

---

### P1-4 · OpenSearch 缺 `OPENSEARCH_JAVA_OPTS` 等关键 env（新发现）

**位置**：M0 Task 1（opensearch service env）

**问题**：
- OS 2.19 默认 JVM heap 是 50% 容器内存——但 M0 还没设 mem_limit 时，OS 按 host 内存 50% 算，**易 OOM kill**
- 缺 `cluster.name` / `discovery.type=single-node` 显式声明

**修改**：
```yaml
  opensearch:
    environment:
      cluster.name: docker-rag-cluster
      node.name: rag-os-node-1
      discovery.type: single-node
      bootstrap.memory_lock: "true"
      DISABLE_SECURITY_PLUGIN: "true"
      DISABLE_INSTALL_DEMO_CONFIG: "true"
      OPENSEARCH_JAVA_OPTS: "-Xms512m -Xmx512m"
    ulimits:
      memlock: { soft: -1, hard: -1 }
      nofile:  { soft: 65536, hard: 65536 }
```

**注**：review 报告**新发现**。

---

### P1-5 · Postgres 缺 `POSTGRES_INITDB_ARGS` 显式声明（新发现）

**位置**：M0 Task 1（postgres env）

**问题**：
- 缺 `POSTGRES_INITDB_ARGS=--encoding=UTF-8 --locale=C` 显式声明
- 默认 UTF-8 + en_US，但下游 M1 migration 可能用到 citext/trgm 等 locale-sensitive 操作
- 容器跨 host（dev/CI/prod）locale 不一致会导致全文检索 / 排序行为不同

**修改**：
```yaml
  postgres:
    environment:
      POSTGRES_USER: rag_app
      POSTGRES_PASSWORD: rag_app_password
      POSTGRES_DB: rag
      POSTGRES_INITDB_ARGS: "--encoding=UTF-8 --locale=C"
```

**注**：review 报告**新发现**。

---

### P1-6 · 缺日志策略（structlog / log level 默认）（新发现）

**位置**：M0 Task 4（config.py）

**问题**：
- `.env.example` L209 写了 `LOG_LEVEL=INFO`，但 plan 没说怎么消费它
- v0.4 spec §8.8 把 `structlog>=24.1,<26` 列为正式依赖
- M0 不实现 logging setup → M3/M7/M10 各自加一遍，重复且不一致

**修改**（Task 4 GREEN 段补 logging 设置 + pyproject 加 structlog）：
```python
# app/logging_setup.py（M0 新增）
import logging, sys
from app.config import settings

def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)

# app/config.py 追加
class LoggingSettings(BaseSettings):
    level: str = "INFO"
```

**注**：review 报告**新发现**。

---

### P1-7 · `infra/check_health.sh` 测试策略提到但 Files 表未列（新发现）

**位置**：M0 测试策略 L262 + Files 表

**问题**：
- 测试策略写"`./infra/check_health.sh`（shell 脚本，手动/CI 可用）"
- Files 表**没列**这文件，也没说谁来写

**修改**（Files 表补 + Task 6 旁新增 Task 7 写脚本）：
```bash
#!/usr/bin/env bash
set -e
echo "== postgres ==" && pg_isready -h localhost -p 5432
echo "== opensearch ==" && curl -fs http://localhost:9200/_cluster/health
echo "== tei ==" && curl -fs http://localhost:18080/health
echo "== langfuse ==" && curl -fs http://localhost:3000/api/public/health
echo "all green"
```

**注**：review 报告**新发现** plan 内部不一致。

---

### P1-8 · 缺 Makefile 收录常用命令（新发现）

**位置**：M0 plan 整篇

**问题**：
- README 写"启动 / 停止 / 测试 / health / logs" 5+ 命令散落
- M3 smoke test 也要 `docker compose -f infra/docker-compose.yml up -d tei langfuse postgres`，统一入口更好

**修改**（Files 表补 `Makefile`）：
```makefile
.PHONY: up down logs health test-unit test-integration clean

up:        ; docker compose -f infra/docker-compose.yml up -d
down:      ; docker compose -f infra/docker-compose.yml down
logs:      ; docker compose -f infra/docker-compose.yml logs -f
health:    ; ./infra/check_health.sh
test-unit:        ; cd apps/rag_v1 && pytest tests/unit
test-integration: ; cd apps/rag_v1 && pytest tests/integration --require-docker
clean:     ; docker compose -f infra/docker-compose.yml down -v
```

**注**：review 报告**新发现**。

---

### P1-9 · 缺 `app/config.py` 全局单例约定（X-3 决议待落地）

**位置**：M0 Task 4 GREEN 段

**问题**：
- 已有 review X-3 决议"在 `app/config.py` 末尾 `settings = Settings()` 暴露全局单例"——本次 M0 plan **未落实**
- M2/M3/M7/M10 预期 `from app.config import settings` 语法，没单例只能 `Settings()` 每次重建

**修改**（Task 4 GREEN 段末尾补）：
```python
# 文件末尾
settings = Settings()  # 全局单例，所有 M 共用
```

**注**：跨 M 一致性 X-3。

---

## P2 · 优化

### P2-1 · `version: "3.8"` 在 Compose v2+ 已弃用（新发现）

**位置**：M0 Task 1（compose 文件头）

**修改**：删 `version: "3.8"`，改 `name: rag_v1`（Compose v2+ 推荐）。

**注**：review 报告**新发现**。

---

### P2-2 · 缺范本目的段（与 M3 范本不齐）

**位置**：M0 plan 开头（与 M3 L8 对齐）

**修改**：在文件头部加 `> 范本目的：M0 是 RAG V1 路线起点 plan，给后续 M 提供"基础设施层"前置定义`。

---

### P2-3 · `app/config.py` 单文件 vs 子目录决策点（X-1 决议待落地）

**位置**：M0 Task 4 REFACTOR L230

**修改**：M0 直接拆 `app/configs/` 子目录（postgres.py / opensearch.py / tei.py / langfuse.py / base.py），保留 `app/config.py` 做 backward-compat re-export。

**注**：跨 M 一致性 X-1。

---

### P2-4 · Task 4 RED 测试缺"类型校验"覆盖

**位置**：M0 Task 4

**修改**（Task 4 RED 段补）：
```python
def test_settings_type_validation() -> None:
    os.environ["POSTGRES_PORT"] = "not-a-port"
    with pytest.raises(ValidationError):
        Settings()
```

---

### P2-5 · `.env.example` 缺 `LANGFUSE_DATABASE_URL` 注释密码来源

**位置**：M0 Task 3 `.env.example` L206

**修改**：把 `***` 占位改成 `rag_app_password`（与 POSTGRES_PASSWORD 对齐），加注释"用户/密码必须与 postgres service 的 POSTGRES_USER/POSTGRES_PASSWORD 一致"。

---

### P2-6 · Task 1 估时 5 分钟，实测 20-30 分钟（新发现）

**位置**：M0 Task 1 GREEN 段

**问题**：Task 1 要写完 4 服务 + network + 4 volume + healthcheck × 4 + depends_on + env vars，实测 20-30 分钟。估时跟实际差 4-6 倍 → M0 整体 2d 估时会爆到 3-4d。

**修改**：Task 1 拆成 Task 1a（postgres）/ 1b（opensearch）/ 1c（tei）/ 1d（langfuse）/ 1e（network+volumes），或诚实标"Task 1 ~25 分钟"。

**注**：review 报告**新发现**。

---

### P2-7 · DoD "3 分钟起全部服务"对冷启动不现实（新发现）

**位置**：M0 DoD L278

**问题**：TEI 首次启动下载 bge-m3 45s+，OS 启动 20s+，Langfuse migration 30s+，串行总 100s+，不算 docker pull。"3 分钟起"只对镜像+模型已 cached 场景成立。

**修改**：DoD 拆两档——
- [ ] 镜像已缓存 + 模型已缓存：3 分钟内 4 服务全部 healthy
- [ ] 首次启动（无缓存）：docker pull + 模型下载允许 10 分钟

**注**：review 报告**新发现**。

---

### P2-8 · M0 风险表 6 行全是抽象缓解，缺量化指标

**位置**：M0 风险表 L300-305

**修改**：风险表每行加数字（如 "Langfuse migration 失败：自动重试 3 次（间隔 10s），仍失败则 `docker compose logs langfuse` 提示手工"）。

---

## 与已有 review 报告交叉验证

| ID | 已有 review 项 | M0 现状 | 本报告 |
|----|--------------|--------|-------|
| P0-1 | TEI 端口 8080 → 18080 | ❌ 未改 | P0-2 |
| P0-2 | `.env.example` LANGFUSE_DATABASE_URL `***` 占位 | ❌ 未改 | P2-5 |
| P0-3 | 4 服务缺 healthcheck | ❌ 未改 | P0-1 |
| P0-4 / 5 / 6 / 7 / 10 | M1 / M7 范围 | N/A | — |
| P0-8 | M0 pyproject 过度装包 | ❌ 未改 | P0-8 给完整模板 |
| P0-9 | 缺 .gitignore | ❌ 未改 | P0-6 |
| P1-1 | README 缺 vm.max_map_count | ❌ 未改 | P0-5 |
| P1-2 | 缺 mem_limit | ❌ 未改 | P1-1 |
| P1-3 | init.sql 密码明文 | ❌ 未改 | P1-2 |
| P2-1 | 缺 pytest.ini / [tool.pytest.ini_options] | ❌ 未改 | P0-8 整合 |
| P2-2 | 缺 [project] 块 | ❌ 未改 | P0-8 整合 |
| X-1 | app/config.py 拆分 | ❌ 未改 | P2-3 |
| X-2 | CI 路径假设 / pytest.ini | ❌ 未改 | P0-8 整合 |
| X-3 | settings 全局单例 | ❌ 未改 | P1-9 |
| X-4 | dev/prod 分离 | N/A（M12） | — |

**结论**：已有 review 列出的 10 个 P0 中，**4 个在 M0 范围内**（P0-1 / P0-3 / P0-8 / P0-9），全部 ❌ 未改；M0 范围内 P1 共 3 项，全部 ❌ 未改；P2 共 2 项，全部 ❌ 未改；跨 M 一致性 3 项（X-1 / X-2 / X-3），全部 ❌ 未改。

---

## 你发现的新问题（已有 review 未列）

合计 **9 个新问题**：

1. **P0-7** · 缺 `.dockerignore`（防 build context 巨大）
2. **P0-9** · TEI 缺 HF_HOME / TRANSFORMERS_CACHE 挂载路径
3. **P1-3** · Langfuse 缺 NEXTAUTH_URL 和 NEXTAUTH_SECRET
4. **P1-4** · OpenSearch 缺 OPENSEARCH_JAVA_OPTS / cluster.name / ulimits
5. **P1-5** · Postgres 缺 POSTGRES_INITDB_ARGS 显式声明
6. **P1-6** · 缺全局 logging 策略（spec §8.8 声明了 structlog 但 M0 没装）
7. **P1-7** · `infra/check_health.sh` 测试策略提到但 Files 表未列（plan 内部不一致）
8. **P1-8** · 缺 Makefile（up/down/logs/health/test-unit/test-integration/clean 常用命令无统一入口）
9. **P2-1** · docker-compose `version: "3.8"` 在 Compose v2+ 已弃用

外加 review 过程的额外发现：

10. **P2-6** · Task 1 估时 5 分钟与实测 20-30 分钟差 4-6 倍
11. **P2-7** · DoD "3 分钟起全部服务"对冷启动场景不现实

---

## 落地建议

按 P0 → P1 → P2 优先级：

### 第一波（本轮必改，9 项 P0）

1. P0-1 补 4 服务 healthcheck 块
2. P0-2 TEI host 端口改 18080
3. P0-3 Langfuse 加 `depends_on: postgres condition: service_healthy`
4. P0-4 postgres volumes 段补 init.sql 挂载点
5. P0-5 README 启动步骤前置 sysctl vm.max_map_count
6. P0-6 新增 Task 写 `.gitignore`
7. P0-7 新增 Task 写 `.dockerignore`
8. P0-8 Task 4 给完整 `pyproject.toml`（只装 pydantic/pydantic-settings/python-dotenv）
9. P0-9 TEI volumes 挂到 `/data` + HF_HOME env

### 第二波（重要，9 项 P1）

10. P1-1 4 服务 mem_limit / cpus limits
11. P1-2 init.sql 密码明文注释 + dev-only 标注
12. P1-3 Langfuse env 补 NEXTAUTH_URL + NEXTAUTH_SECRET
13. P1-4 opensearch env 补 OPENSEARCH_JAVA_OPTS / cluster.name / ulimits
14. P1-5 postgres env 补 POSTGRES_INITDB_ARGS
15. P1-6 新增 logging_setup.py + pyproject 加 structlog
16. P1-7 Files 表补 check_health.sh + Task 内容
17. P1-8 新增 Makefile
18. P1-9 config.py 末尾 `settings = Settings()` 全局单例

### 第三波（优化，8 项 P2）

19. P2-1 docker-compose 删 version: "3.8"，改 name: rag_v1
20. P2-2 M0 plan 头部补"范本目的"段
21. P2-3 M0 直接拆 `app/configs/` 子目录（X-1 落地）
22. P2-4 Task 4 RED 测试补类型校验
23. P2-5 `.env.example` LANGFUSE_DATABASE_URL 改合法占位
24. P2-6 Task 1 拆 5 子任务 或 诚实标 25 分钟
25. P2-7 DoD 拆 warm-cache (3min) / cold-start (10min) 两档
26. P2-8 风险表每行加量化指标

### 跨 M 协调（M0 改完后通知）

- 通知 M3 / M7 / M10：`TEI_URL=http://tei:8080`（容器内端口不变），`TEI_HOST_PORT=18080`（host 端口）
- 通知 M1：`app/config.py` 末尾有 `settings = Settings()` 单例，alembic env.py 引用 `settings.db.database_url`
- 通知 M2：`app/config.py` 加 `AuthSettings` 时遵守单文件 vs 子目录决议（推荐子目录）

### 估时修正

- M0 整体估时从 **2d → 3d**（含 P0 修补 + cold-start 镜像下载预留 1d）

### 等待决策

- X-1 `app/config.py` 是否在 M0 直接拆 `configs/` 子目录（已有 review 决议"是"，本报告 P2-3 重复）
- X-4 dev/prod 分离放 M12 还是 M0 提早定调（推荐 M0 README 至少写一段"prod 部署走 M12 hardening"）

---

## 状态

- **不可动手**：P0-1 ~ P0-9 共 9 项必改
- **建议本轮改**：P1-1 ~ P1-9 共 9 项
- **可下轮改**：P2-1 ~ P2-8 共 8 项
- **新问题合计**：9 个（已有 review 未列），外加 2 个附加发现
- **已有 review 验证**：M0 范围内 12 项（含 4 个 P0 + 3 个 P1 + 2 个 P2 + 3 个跨 M），全部 ❌ 未改

M0 plan **结构对、内容薄、估时低、漏启动前关键 env 与挂载点**。修完 P0 即可开 git 仓库初始化 + 实际写代码。