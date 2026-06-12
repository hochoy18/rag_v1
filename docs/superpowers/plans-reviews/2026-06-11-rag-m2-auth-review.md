# M2 Plan Review · Auth 鉴权层

> 评审对象：`plans/2026-06-10-rag-m2-auth.md`（M2 Auth 鉴权层，448 行）
> 评审基线：V1 Scope v0.4 spec（§0 决策 #5/#6/#7/#14、§2 模块树 auth 段、§3.2 Auth 数据流、§5 错误矩阵、§8.3 鉴权依赖）+ 已有 review 报告（P0-P2 共 36 项）+ M0/M1 review 报告 + M3 范本 11 段
> 评审时间：2026-06-11
> 评审者：Hermes subagent（独立审查）

---

## 总评

M2 plan **按 11 段模板走齐**（Goal / 不包含 / Architecture / Tech Stack / Files / Tasks / 测试 / DoD / 依赖 / 风险 / 修订记录），且**自带"范本目的"段**（L8），比 M0/M1 多 1 段。Tasks 6 个、RED-GREEN-REFACTOR 节奏清晰，单 Task 2-5 分钟目标基本可达。**但实施就绪度中等偏下**——已有 review 列出的 4 项 P1（P1-7 argon2 参数 / P1-8 extend_session fire-and-forget / P1-9 双 datetime.now() / P1-11 protected endpoint mock）**全部未改**；M1 schema 缺的 `is_revoked` / `failed_login_attempts` / `ip_address` / `user_agent` 字段会让 M2 业务逻辑"想做但 schema 不支持"；**外加本 review 新发现 16+ 个问题**，覆盖密码强度、token 轮换、CSRF/cookie 安全、session 清理、并发登录冲突、慢测试解法、错误矩阵对齐等领域。

| 维度 | 评分 | 说明 |
|---|---|---|
| 结构完整性 | ⭐⭐⭐⭐⭐ | 11 段齐 + 范本目的段齐 |
| TDD 标注 | ⭐⭐⭐⭐⭐ | RED-GREEN-REFACTOR 完整；RED 测试写法具体 |
| 任务粒度 | ⭐⭐⭐⭐ | 多数 2-5 分钟，Task 3 / Task 4 略超 5 分钟（多个 RED） |
| 一致性 | ⭐⭐⭐ | 版本与 spec §8.3 错位（argon2 <25 vs spec <24 / cryptography <44 vs spec <46）；slowapi 限速与 TestClient 兼容性 plan 自身承认"标 @pytest.mark.slow" 但无完整解法 |
| 实施就绪度 | ⭐⭐ | 已有 review P1-7~P1-11 全部未改；M1 schema 缺字段让 M2 业务"想做不能做"；pyjwt 标"备用"但 pyproject 写"主路径不用" 矛盾 |
| 错误处理 | ⭐⭐⭐ | spec §5 错误矩阵 M2 范围 5 条（401/404/409/429/argon2）plan 都覆盖，但**注册密码弱、限速计数竞争、token 错误计数锁账号、session 清理** 4 条没规划 |
| 跨 M 契约 | ⭐⭐⭐⭐ | `Depends(get_current_user)` 签名 / M1 schema 字段对齐清晰，但 `app/config.py` 拆分（X-1）/ 全局单例（X-3）/ `.env.example` 完整内容 都待跨 M 协调 |

**一句话**：M2 plan **结构好、TDD 节奏好、与 spec 决策对齐好**，但**版本号 2 处与 spec §8.3 不一致、慢测试解法只给一半、密码强度与 token 轮换 / session 清理 / 并发冲突这些基础功能没设计**。修完 P0 + P1 前 6 项可动手，后 10 项 P1 建议同轮改完以避免 M3 接入 auth 时再回溯 M2。

---

## P0 · 阻塞级（动手前必改）

### P0-1 · 依赖版本与 spec §8.3 不一致（2 处）

**位置**：M2 Tech Stack 表 L113-114
```
| `argon2-cffi` | `>=23.1,<25` |
| `cryptography` | `>=42.0,<44` |
```

**问题**：
- spec §8.3 L402-403 明确：`argon2-cffi >=23.1,<24` / `cryptography >=42,<46`
- M2 改 `argon2-cffi <25` 多了 24.x 一档；`cryptography <44` 砍掉了 44-45 两档（cryptography 43/44/45 是 OpenSSL 3.0.x 关键安全 fix 区间）
- 跨 M 编译环境会装到不同 minor 版本，导致 dev/prod 行为漂移

**修改**：
```python
# 与 spec §8.3 对齐
"argon2-cffi>=23.1,<24",
"cryptography>=42,<46",
"pyjwt>=2.9,<3",       # 保持
"slowapi>=0.1.9,<1",   # 保持
```

**已有 review**：未列（已有 review P0-1~P0-10 是跨 M 端口/env/PE 8 项，M0 评审视角），M2 范围**新发现**。

### P0-2 · `pyjwt` 列为"备用"但 pyproject 写"主路径不用"，引入无意义依赖

**位置**：M2 Tech Stack 表 L115
```
| JWT 备用 | `pyjwt` | `>=2.9,<3` （仅备用，主路径不用） |
```

**问题**：
- spec 决策 #5 明确否决 JWT，spec §8.3 仍把 `pyjwt` 列入"鉴权 & 安全 3 包"——这是 spec 自身的不一致
- M2 plan 写"备用"但**没说明**何时会启用；"备用"是 v2 才有需求（V1 spec §9 明确"鉴权 V1：用户名密码 + token"——V1 范围没有 JWT 需求）
- 装但不用 = 攻击面（pyjwt 历史出过 CVE-2022-29217 algorithm confusion）+ 维护成本

**修改**（二选一）：
- 方案 A（推荐）：M2 删 `pyjwt` 依赖，spec §8.3 也同步删，与"否决 JWT"决策保持一致
- 方案 B：保留 `pyjwt` 但在 Files 表加 `app/auth/jwt_legacy.py` 显式声明"deprecated 兼容层"——并写明"无 caller，仅占位"

**新发现**（已有 review 未列）。

### P0-3 · 慢测试（slowapi + TestClient 兼容性）解法不完整

**位置**：M2 风险表 L437
```
| slowapi 与 FastAPI `TestClient` 限速计数不一致导致集成测试不稳定 | 测试环境设高限速阈值（如 1000/minute）；集成测试标记 `@pytest.mark.slow` 可选 |
```

**问题**：
- "标 @pytest.mark.slow 可选"——意味着 CI 不跑就**永远**没人发现限速阈值错配；"标了但跳过"等于**没测**
- TestClient 共享 slowapi in-memory storage 是已知问题（issue: slowapi 不识别 starlette TestClient 的 client IP），简单改阈值**不解决**计数共享问题
- 集成测试 `test_password_rate_limit` 跑 11 次 login，每次都触发限速 → 真在 CI 跑会留下 state 影响后续测试

**修改**（给完整解法）：
```python
# tests/conftest.py
import pytest
from slowapi import Limiter
from slowapi.util import get_remote_address

@pytest.fixture(autouse=True)
def reset_limiter():
    """每个测试前清空 slowapi 计数器 + 注入可控 IP。"""
    from app.api.auth import limiter
    limiter.reset()
    yield
    limiter.reset()

@pytest.fixture
def fixed_ip(monkeypatch):
    """TestClient 默认 127.0.0.1 全测试共享，monkeypatch get_remote_address 让每个测试独立计数。"""
    from app.api import auth
    counter = {"ip": "127.0.0.1"}
    monkeypatch.setattr(auth, "get_remote_address", lambda: counter["ip"])
    return counter
```

并在 plan Task 6 段补："`test_password_rate_limit` 不再标 @pytest.mark.slow，而是真跑（用 reset_limiter fixture 隔离）"。

**已有 review**：未深入（仅一笔带过"标 @pytest.mark.slow"），本 review **新发现**需完整解法。

### P0-4 · `is_revoked` 字段在 M1 schema 缺，M2 业务逻辑"想做不能做"

**位置**：M2 业务逻辑 L299、326 等多处依赖 `session.is_revoked`

**问题**：
- M2 plan 假设 `AuthSession.is_revoked: bool` 字段存在（`if session.is_revoked: raise 401`）
- M1 schema 实际**没定义** `is_revoked` 字段（grep 验证：`/home/hochoy/.hermes/profiles/coder/docs/superpowers/plans/2026-06-10-rag-m1-schema.md` L116-118 只定义 `token_hash` / `expires_at_sliding` / `expires_at_hard` 三列 + `is_active`-like 列未确认）
- 没有 `is_revoked` 字段 → M2 "吊销"逻辑只能"DELETE auth_sessions"（spec §3.2 写的）——但 DELETE 后再用同 token 调 protected endpoint 会 404（找不到 session），不是 401（revoked）
- 404 vs 401 区分了"token 不存在"和"token 已被吊销"——**泄漏信息**

**修改**（二选一）：
- 方案 A（推荐，遵守 spec §3.2 "DELETE auth_sessions"）：M2 改用 DELETE，protected endpoint 见不到 session 即 404（不区分 revoked vs never-existed）——但**要 M1 显式确认 schema 不需要 is_revoked 字段**（M1 plan L116-118 没列 `is_revoked`）
- 方案 B：M1 追加 `is_revoked BOOLEAN DEFAULT FALSE` 列（M2 不动），M2 logout 改 UPDATE 软吊销

**当前 plan 矛盾**：
- 风险表 L437-438 "logout 吊销 token"措辞含混——是 DELETE 还是 UPDATE？
- 业务逻辑 L299 写 `if session.is_revoked: raise HTTPException(400, "already revoked")`——**既不是 404 也不是 401**，且用 400（客户端错）描述服务端状态，错误码选择也错

**新发现**（M1 review P2-6 仅提"auth_sessions.ip_address / user_agent 缺"，未提 `is_revoked` 缺）。

### P0-5 · 慢测试隔离（`extend_session` fire-and-forget）实现风险无解

**位置**：M2 Task 4 GREEN 段 L327 + 风险表 L439
```python
# 如果 sliding 将过期（剩余 < 1d）：异步 fire-and-forget extend_session(token_hash)（不阻塞请求）
```
```
| `extend_session` 在 Depends 中 fire-and-forget 导致异步上下文问题 | 使用 `asyncio.create_task()` + 独立 DB session；失败不阻塞请求 |
```

**问题**：
- `asyncio.create_task()` 在 FastAPI Depends 路径里**会被 GC**——task 没 await 就丢
- "独立 DB session"——没说是 `async_session_factory()` 还是 `async_scoped_session`——session 生命周期不明
- 失败不阻塞请求 → 任务静默失败 → sliding 过期前 1d 触发后没真续期 → 用户滚动 6d 后突然 401
- 风险表说"已否决同步 extend（增加请求延迟）"——但没量化"增加多少 ms"；`UPDATE auth_sessions SET expires_at_sliding = ...` 在 indexed PG 上是 < 5ms

**修改**（重新选型）：
- 方案 A（推荐）：改用 `BackgroundTasks`（FastAPI 原生支持，会在 response 发送前完成）：
  ```python
  from fastapi import BackgroundTasks
  async def get_current_user(..., background_tasks: BackgroundTasks):
      ...
      if sliding_will_expire_soon:
          background_tasks.add_task(extend_session, token_hash)
  ```
  这样**不阻塞** response（response 立即返回）+ **不丢** task（FastAPI 等待所有 background_tasks 完成才关闭连接）
- 方案 B：保留 `asyncio.create_task()` 但显式保引用：`tasks.add(task)` 存 module-level set
- 方案 C：把"sliding 过期前 1d 才续期"阈值调到"3d"，**大幅减少触发频率**（多数请求不触发）

**已有 review**：P1-8 已列前半段（fire-and-forget 风险），本 review **新发现**完整解法 + threshold 调整建议。

---

## P1 · 重要

### P1-1 · `validate_token_expiry` 双 `datetime.now()` 毫秒级竞争（已知未改）

**位置**：M2 Task 2 GREEN 段 L239
```python
return datetime.now(timezone.utc) < expires_at_sliding and datetime.now(timezone.utc) < expires_at_hard
```

**修改**：
```python
def validate_token_expiry(expires_at_sliding: datetime, expires_at_hard: datetime) -> bool:
    now = datetime.now(timezone.utc)
    return now < expires_at_sliding and now < expires_at_hard
```

**已有 review**：P1-9 已列，本次 verify **仍未改**。

### P1-2 · Argon2 参数过弱（生产环境）

**位置**：M2 Task 1 AuthSettings 默认值
```python
argon2_time_cost: int = 2
argon2_memory_cost: int = 19456
```

**问题**：
- OWASP 2024 推荐 `time_cost=3, memory_cost=65536`（~64MB）
- "决策 #6 已定 argon2id baseline"——baseline 不等于"baseline 就够"；baseline 是"用了什么算法"，强度参数可调
- 风险表 L435 自承"在生产环境偏弱"——但又说"安全加固在 M12 hardening 阶段"——**M2 把弱参数 ship 出去**，M12 hardening 时已注册用户全用弱 hash 哈希过

**修改**：
```python
# 默认就用 OWASP 2024 推荐值
argon2_time_cost: int = 3
argon2_memory_cost: int = 65536
argon2_parallelism: int = 1  # 显式声明，避免 argon2-cffi 内部默认值漂移
```

外加 M12 hardening 阶段加 "rehash on login"：login 成功后检查 hash 参数是否匹配当前 settings，不匹配就 rehash 存新 hash。M2 至少要在 `app/auth/service.py` 留 hook：
```python
# login() 末尾
if ph.check_needs_rehash(user.password_hash):
    user.password_hash = ph.hash(password)
    await UserRepository.update(user)
```

**已有 review**：P1-7 已列，本次 verify **仍未改**。

### P1-3 · `test_auth_tokens.py` 同时含 config 测试（拆文件）

**位置**：M2 Files 表 L170 + Task 1 RED L189-193

**问题**：token 工具函数测试 vs config 加载测试混一个文件，CI 失败时定位变慢

**修改**：拆成 `test_auth_tokens.py`（token 工具）+ `test_auth_config.py`（config 加载），Files 表同步更新

**已有 review**：P1-10 已列。

### P1-4 · Task 5 末尾 `test_nonexistent_token_returns_404` 标"mock endpoint"

**位置**：M2 Task 5 末 L380
```python
# 用随机 token 调 `/api/protected`（或 mock endpoint）→ 断言 404
```

**问题**：
- M2 范围不创建 `/api/protected`
- "或 mock endpoint"——mock 测的不是真鉴权路径，没意义
- 应该在 M2 范围**加一个 minimal protected endpoint**（如 `/api/auth/me`）做 smoke

**修改**：Files 表追加 `app/api/auth.py` 加 `GET /api/auth/me` endpoint（鉴权 + 返回 user info），作为 M3+ protected endpoint 的样板

**已有 review**：P1-11 已列。

### P1-5 · `app/api/__init__.py` 聚合代码段过简

**位置**：M2 Task 5 GREEN L362-365
```python
from app.api.auth import router as auth_router
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
```

**问题**：
- `auth_router` 自身已设 `prefix="/api/auth"`（L356）——再被 `api_router(prefix="/api")` 包含后路径变 `/api/api/auth/...`（双 prefix 冲突）
- 实际应该是：`api_router = APIRouter()`（无 prefix）→ `api_router.include_router(auth_router)` → 整体挂到 FastAPI app 时 `app.include_router(api_router, prefix="/api")`
- plan 没说怎么挂到 FastAPI app

**修改**：
```python
# app/api/__init__.py
from fastapi import APIRouter
from app.api.auth import router as auth_router

api_router = APIRouter()
api_router.include_router(auth_router)
__all__ = ["api_router"]
```

```python
# app/main.py（M0/M8 还没建，M2 plan Files 表追加）
from fastapi import FastAPI
from app.api import api_router

app = FastAPI()
app.include_router(api_router, prefix="/api")
```

**已有 review**：P2-6 已列"仓促"，本 review **新发现**双 prefix 冲突。

### P1-6 · pyproject.toml 依赖追加段未给完整内容

**位置**：M2 Files "修改" 段 L178
```
- `pyproject.toml`：追加 3 个新直接依赖（`argon2-cffi` / `cryptography` / `slowapi`）
```

**问题**：
- 没说追加到 `[project.dependencies]` 还是 dev 依赖——这 3 个都是 runtime 必需（不是测试专用）
- 没给完整 toml 片段，新人 copy plan 不知道怎么改

**修改**（Files 表"修改"段补完整片段）：
```toml
# apps/rag_v1/pyproject.toml [project.dependencies] 追加：
"argon2-cffi>=23.1,<24",
"cryptography>=42,<46",
"slowapi>=0.1.9,<1",
```

**新发现**。

### P1-7 · 缺密码强度校验（spec §3.2 显式要求）

**位置**：M2 整篇 + spec §3.2 L196
```
POST /api/auth/register {username, password}
  → 校验（用户名唯一、密码强度）
```

**问题**：
- spec **显式**写"密码强度校验"，M2 plan 整篇**没设计**这个函数
- 没有密码强度 → 用户注册 "x"（1 字符）也能通过 → 爆破成本 0
- M1 review P1-8 已建议在 M1 schema 阶段定 `app/auth/password_validator.py` 签名——**M1 没采纳**（本次 review M1 范围内未提 P1-8），所以 M2 必须自己写

**修改**（M2 范围内补）：
- Files 表追加 `app/auth/password_validator.py` + `tests/unit/test_password_validator.py`
- GREEN 段给完整实现：
  ```python
  # app/auth/password_validator.py
  import re
  from pathlib import Path
  
  MIN_LENGTH = 12
  MAX_LENGTH = 128
  _COMMON_FILE = Path(__file__).parent / "common_passwords.txt"
  _COMMON_PASSWORDS = frozenset(_COMMON_FILE.read_text().splitlines()) if _COMMON_FILE.exists() else frozenset()
  
  def validate_password(pw: str) -> None:
      """Raises ValueError on weak password."""
      if not isinstance(pw, str):
          raise ValueError("Password must be a string")
      if not (MIN_LENGTH <= len(pw) <= MAX_LENGTH):
          raise ValueError(f"Password length must be {MIN_LENGTH}-{MAX_LENGTH}")
      if pw.lower() in _COMMON_PASSWORDS:
          raise ValueError("Password too common")
      if not re.search(r"[a-z]", pw) or not re.search(r"[A-Z]", pw):
          raise ValueError("Password must contain mixed case")
      if not re.search(r"\d", pw):
          raise ValueError("Password must contain digit")
  ```
- 集成测试 Task 5 加 RED：`test_register_weak_password_returns_422`
- 注册失败用 422（Unprocessable Entity，FastAPI Pydantic 默认）而不是 400

**新发现**（M1 review P1-8 未被 M1 采纳，转 M2 实施）。

### P1-8 · 缺 username 校验（长度 / charset / reserved words）

**位置**：M2 整篇

**问题**：
- plan 假设 `username: str` 透传，**没长度限制、字符集限制、保留字检查**
- M1 schema `username VARCHAR(64) UNIQUE NOT NULL`——64 字符够长，但允许 `admin` / `root` / `system` / 空字符串 / 纯空格 / emoji
- 用户名冲突排查时，"alice" / "Alice" / " alice " / "alice​"（零宽字符）视为不同——**扰乱审计**

**修改**（Pydantic schema 校验）：
```python
# app/api/auth.py
from pydantic import BaseModel, Field, field_validator
import re

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")
RESERVED_USERNAMES = frozenset(["admin", "root", "system", "api", "null", "undefined"])

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)
    
    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v_normalized = v.strip().lower()
        if not USERNAME_RE.match(v_normalized):
            raise ValueError("Username must be 3-32 chars: a-z, 0-9, _")
        if v_normalized in RESERVED_USERNAMES:
            raise ValueError("Username is reserved")
        return v_normalized  # 存 normalized form
```

**注意**：username 存 normalized form → M1 schema UNIQUE 索引**自动**实现大小写不敏感（无需 citext 扩展）。这同时解决了 M1 review P1-19 的 username 大小写问题。

**新发现**。

### P1-9 · 缺 token 轮换策略（每次 login 是否吊销旧 token？）

**位置**：M2 业务逻辑 Task 3 L268-276

**问题**：
- plan 写"INSERT auth_sessions"——同 user 可登录多次，每次 INSERT 新 session，**旧 session 仍有效**
- 结果：用户改密码后旧 device 的 token 仍能用（spec 决策 #14 没明确说"改密码吊销所有 token"）
- 多设备登录策略：V1 是否支持？plan 没设计

**修改**（明确策略，Files 表改写）：
- 方案 A（推荐 V1 简化）：**单设备策略**——login 时 `UPDATE auth_sessions SET is_revoked=TRUE WHERE user_id=? AND is_revoked=FALSE`（软吊销所有旧 session），新登录签发唯一新 token
  - 需要 `is_revoked` 字段（见 P0-4）
- 方案 B（多设备）：不吊销旧 session，最多 5 个并发 session（`COUNT(*) WHERE user_id=? AND is_revoked=FALSE` 超 5 则吊销最旧）
- 方案 C（无策略）：保持现状，plan 风险表补"暂不支持踢出旧 session"——M12 hardening 阶段补

**新发现**。

### P1-10 · 缺 session 表清理策略（`expires_at_hard` 过期怎么清理？）

**位置**：M2 整篇

**问题**：
- spec §3.2 写"DELETE auth_sessions WHERE token_hash=?"（logout 时硬删）——但 hard expire 30d 后的 session **没 DELETE**，只 `is_revoked`（如果 P0-4 选 B）或 `is_revoked` 不存在（P0-4 选 A 的话就靠 hard cap 过期但 DB 行还在）
- 30 天后表里堆积 30 天前的 revoked/expired session，PG 越来越大
- slowapi 限速是 in-memory，进程重启丢——但 DB 表不会丢

**修改**（Files 表追加 + 任务追加）：
- Files 表追加 `app/auth/cleanup.py` + `tests/unit/test_auth_cleanup.py`
- 实现：
  ```python
  # app/auth/cleanup.py
  async def purge_expired_sessions() -> int:
      """DELETE FROM auth_sessions WHERE expires_at_hard < NOW() - INTERVAL '7 days'
      Returns rowcount."""
      ...
  ```
- DoD 补："CI 跑一次 `purge_expired_sessions()`，返回 rowcount ≥ 0"
- 实际生产清理需要 cron（spec §12 部署节奏没列，M12 hardening 阶段补 external cron 触发）

**新发现**。

### P1-11 · 缺 `pytest-httpx` / `freezegun` 依赖声明（M2 测试必用）

**位置**：M2 Tech Stack L120 + 测试策略 L399-402

**问题**：
- 测试 `test_expired_token_returns_401`（L383-384）写"mock datetime.now，让 token 显示已过期"——需要 `freezegun` 库
- spec §8.7 L446 把 `freezegun >=1.5,<2` 列为正式依赖
- spec §8.7 L443 把 `pytest-httpx >=0.30,<1` 列为正式依赖
- M2 Tech Stack 表**完全没列**这两个库

**修改**（Tech Stack 补）：
```python
| 测试 datetime mock | `freezegun` | `>=1.5,<2` |
| 测试 HTTPX mock | `pytest-httpx` | `>=0.30,<1` |
```

**新发现**。

### P1-12 · 缺 cookie 安全设置（httpOnly / secure / sameSite）

**位置**：M2 整篇

**问题**：
- plan 用 `Authorization: Bearer <token>` Header 模式（不存 cookie）——**这个方案本身没 cookie 问题**
- 但 spec §3.2 写"`POST /api/auth/login` → return `{user_id, token}`"——前端 Gradio（M9）怎么存？
  - 存 localStorage → XSS 风险
  - 存 cookie → httpOnly / secure / sameSite 必须设
- M2 plan 没设计前端 token 存储策略

**修改**（M2 范围内补一个 task）：
- 风险表补："前端 token 存储"行
- 方案 A（推荐）：Gradio 用 Authorization Header + 后端不 Set-Cookie（无 cookie 风险）——明确写到 README
- 方案 B：M2 加 Set-Cookie endpoint（`POST /api/auth/login` 同时设 httpOnly cookie + 返 body 含 token），但要 `secure=True`（仅 HTTPS）/ `samesite="lax"`——增加攻击面

**新发现**。

### P1-13 · 缺 token 错误计数（多次错误 token 是否触发账号锁？）

**位置**：M2 整篇 + spec §5 错误矩阵

**问题**：
- spec §5 L298-299 只说"用户未登录 401"——没提"账号锁定"
- 没账号锁 → 攻击者可暴力枚举 token（2^256 空间对随机 token 安全，但对"已知 user_id + 已知 session_id 前缀"的预测攻击不设防）
- M1 review P2-4 已建议加 `users.failed_login_attempts` + `locked_until` 字段

**修改**（最小可行）：
- M1 schema 追加：`failed_login_attempts INT DEFAULT 0` + `locked_until TIMESTAMPTZ NULL`（参考 M1 review P2-4）
- M2 login() 业务：
  ```python
  user = await UserRepository.find_by_username(username)
  if user.locked_until and user.locked_until > utcnow():
      raise HTTPException(429, "Account locked, try later")
  try:
      ph.verify(user.password_hash, password)
  except VerifyMismatchError:
      user.failed_login_attempts += 1
      if user.failed_login_attempts >= 5:
          user.locked_until = utcnow() + timedelta(minutes=15)
          user.failed_login_attempts = 0
      await UserRepository.update(user)
      raise HTTPException(401, "invalid credentials")
  # 成功 → reset
  user.failed_login_attempts = 0
  user.locked_until = None
  ```
- 风险表补："账号锁策略 V1 简化版：5 次/15min"

**新发现**（已有 review 未列）。

### P1-14 · 缺 `app/config.py` 全局单例约定（X-3 待落地）

**位置**：M2 Task 1 GREEN 段 L196-201

**问题**：
- 已有 review X-3 决议"`app/config.py` 末尾 `settings = Settings()` 暴露全局单例"
- M2 Task 1 写 `auth: AuthSettings = AuthSettings()`——是**嵌套实例**而不是 `Settings().auth`——这要求 `Settings()` 顶层有 `auth` 字段
- M0 review P1-9 已建议 M0 阶段加 `settings = Settings()` 单例——M2 阶段在 `app/config.py` 末尾追加即可

**修改**（Task 1 GREEN 段末尾补）：
```python
# app/config.py 文件末尾
settings = Settings()  # 全局单例，所有 M 共用
```

并在 Task 1 RED 测试改：
```python
from app.config import settings  # 不是 Settings()
assert settings.auth.token_ttl_sliding == timedelta(days=7)
```

**已有 review**：X-3 已列。

### P1-15 · 缺 CSRF 保护策略说明（FastAPI Header 模式默认安全，但要显式写）

**位置**：M2 整篇

**问题**：
- V1 鉴权用 `Authorization: Bearer <token>` Header——Header **不自动随请求发**（不像 cookie）——天然防 CSRF
- 但 M9 Gradio + M8 API 文档要**明确**说"不要用 cookie 模式存 token"，否则后人改 Set-Cookie 模式引入 CSRF

**修改**（M2 风险表补一行）：
```
| CSRF 风险 | 缓解：V1 鉴权用 Authorization Header 模式（不 Set-Cookie），M9 Gradio 也要走 Header | 已否决 cookie 模式（spec §0 决策 #14 不强制 cookie） |
```

**新发现**。

---

## P2 · 优化

### P2-1 · M2 plan 头部"范本目的"段已有但 Files 表缺 M2 头部模板注释

**位置**：M2 Files 表 L162 `app/api/__init__.py`

**修改**：补一行"暴露 `api_router` 单一符号供 `app/main.py` 挂载"

### P2-2 · `secrets.token_urlsafe(32)` 与 DB UNIQUE 冲突的 retry 逻辑只写风险没写实现

**位置**：M2 风险表 L436
```
| `secrets.token_urlsafe(32)` 与 DB 唯一约束冲突概率虽低但仍存在 | DB 加 UNIQUE(token_hash) + retry 逻辑（最多 3 次重试生成） |
```

**修改**（Files 表追加 + 任务实现）：
- `app/auth/service.py::login()` 末尾加：
  ```python
  for attempt in range(3):
      try:
          await AuthSessionRepository.create(...)
          break
      except IntegrityError:
          if attempt == 2:
              raise HTTPException(500, "token generation failed")
          continue
  ```
- 风险表改"已落实到 Task 3 GREEN 段 L268-276"

### P2-3 · `GET /api/auth/me` 样板 endpoint 缺（M3 接入样板）

**位置**：M2 整篇（见 P1-4）

**修改**：Files 表追加 `@router.get("/me", response_model=UserResponse)` 用 `Depends(get_current_user)`，作为 M3+ 所有 protected endpoint 的样板

### P2-4 · `LogoutRequest` 设计冗余（前端 logout 已有 Authorization header）

**位置**：M2 Task 5 GREEN L359
```python
@router.post("/logout", status_code=204)：读 `LogoutRequest(token)` 或从 header 取 → 调 `logout()` → 204
```

**问题**：前端用 Authorization header 调 `/api/auth/logout`——为啥还要 body 传 token？冗余 + 容易写错

**修改**：统一为只读 Authorization header（与 GET /me 一致），`LogoutRequest` 不需要

### P2-5 · 慢测试 fixture 设计文档化

**位置**：见 P0-3

**修改**：Files 表追加 `tests/conftest.py`（含 P0-3 给的 `reset_limiter` / `fixed_ip` fixture），并加 README 段落"测试隔离策略"

### P2-6 · 缺 `Dockerfile` 文档（部署用，M0/M2 没建）

**位置**：M2 整篇

**问题**：
- spec §6 决策"部署：Docker Compose 4 service"——但 M0 docker-compose.yml **没建 app 服务**（只 4 基础设施）
- M2 应该是 app 镜像起点，但 plan 没提 Dockerfile

**修改**：M2 风险表补一行："M8 API / M9 UI 阶段补 `apps/rag_v1/Dockerfile`（multi-stage Python:3.11-slim + uvicorn）"；本 M2 不写 Dockerfile

### P2-7 · `from app.config import settings` 全 M 统一约定（X-3 配套）

**位置**：M2 Task 1 / Task 3 / Task 4 多个 `from app.config import ...`

**修改**：M2 风险表补一行（与 P1-14 配套）："`from app.config import settings` 是跨 M 唯一导入方式，禁止 `Settings()` 重复实例化"

### P2-8 · `validate_token_expiry` 没显式说明 timezone 假设

**位置**：M2 Task 2 L238-239

**问题**：函数没强制 `expires_at_sliding` / `expires_at_hard` 是 `datetime(timezone.utc)`——如果 caller 传 `datetime.now()`（naive）会和 `datetime.now(timezone.utc)`（aware）比较 → `TypeError: can't compare offset-naive and offset-aware datetimes`

**修改**：
```python
def validate_token_expiry(expires_at_sliding: datetime, expires_at_hard: datetime) -> bool:
    if expires_at_sliding.tzinfo is None or expires_at_hard.tzinfo is None:
        raise ValueError("Datetimes must be timezone-aware (UTC)")
    now = datetime.now(timezone.utc)
    return now < expires_at_sliding and now < expires_at_hard
```

### P2-9 · 缺 `pytest-httpx` mock tei / langfuse 健康检查的示例

**位置**：M2 测试策略

**问题**：M3+ 业务会调 TEI / Langfuse HTTP——M2 阶段就应在 conftest.py 准备 httpx_mock fixture（虽然 M2 暂不用）

**修改**：M2 风险表补："M3 阶段启用 `pytest-httpx` mock TEI/Langfuse；M2 阶段先在 conftest.py 准备好 import"

### P2-10 · `extend_session` 触发条件（sliding 剩余多久才续期）没量化

**位置**：M2 Task 4 GREEN L327
```python
# 如果 sliding 将过期（剩余 < 1d）：异步 fire-and-forget extend_session(token_hash)
```

**问题**："剩余 < 1d" 是 hardcoded 数字——应该可配（不同 M8 业务可能想调）

**修改**：
```python
# app/config.py AuthSettings 追加
session_extend_threshold: timedelta = Field(default=timedelta(days=1), env="AUTH_SESSION_EXTEND_THRESHOLD")
```

---

## 与已有 review 交叉验证

| ID | 已有 review 项 | M2 plan 是否已改 | 本报告 |
|---|---|---|---|
| P1-7 | Argon2 参数弱（time_cost=2, memory=19456） | ❌ 未改 | P1-2 |
| P1-8 | `extend_session` fire-and-forget 风险 | ❌ 未改 | P0-5（升级到 P0 + 给完整解法） |
| P1-9 | `validate_token_expiry` 双 `datetime.now()` | ❌ 未改 | P1-1 |
| P1-10 | `test_auth_tokens.py` 含 config 测试混文件 | ❌ 未改 | P1-3 |
| P1-11 | M2 末尾 `test_nonexistent_token` mock endpoint | ❌ 未改 | P1-4 |
| P2-6 | `app/api/__init__.py` 聚合缺 | ❌ 未改 | P1-5（升级到 P1 + 新发现双 prefix 冲突） |
| X-1 | `app/config.py` 拆分 `configs/` 子目录 | ❌ 未改 | P2-7（建议 M2 阶段拆） |
| X-3 | `app.config` 末尾 `settings = Settings()` 单例 | ❌ 未改 | P1-14 |
| M1 P2-4 | 缺 `users.failed_login_attempts` / `locked_until` | ❌ 未改（M2 plan 也没用） | P1-13（M2 应推动 M1 补字段） |
| M1 P2-6 | 缺 `auth_sessions.ip_address` / `user_agent` | ❌ 未改（M2 plan 也没用） | 不进 M2 必改（M12 hardening 必加） |
| M1 P1-19 | `users.username` citext / 大小写处理 | ❌ 未改 | P1-8（M2 Pydantic 业务层 `username.lower().strip()` 解决） |

**结论**：M2 范围内已有 review 列出的 9 项，**全部 ❌ 未改**。plan 作者需在动手前批量更新。

**新发现**（不在 M2 已有 review 列表）：P0-1 ~ P0-4（4 项）+ P1-6、P1-7、P1-8、P1-9、P1-10、P1-11、P1-12、P1-13、P1-15（9 项）+ P2-1 ~ P2-10（10 项） = **23 个新问题**。

---

## 你发现的新问题（已有 review 未列）

合计 **23 个新问题**：

1. **P0-1** · 依赖版本与 spec §8.3 不一致（argon2 <25 vs spec <24 / cryptography <44 vs spec <46）
2. **P0-2** · `pyjwt` 标"备用"但引入无意义依赖（建议删）
3. **P0-3** · 慢测试（slowapi + TestClient）解法不完整，需 reset_limiter + fixed_ip fixture
4. **P0-4** · `is_revoked` 字段在 M1 schema 缺，M2 业务逻辑"想做不能做"
5. **P0-5** · `extend_session` fire-and-forget 完整解法 + threshold 调整
6. **P1-6** · pyproject.toml 依赖追加段未给完整内容
7. **P1-7** · 缺密码强度校验（spec §3.2 显式要求）
8. **P1-8** · 缺 username 校验（长度 / charset / reserved words / 大小写归一）
9. **P1-9** · 缺 token 轮换策略（单设备 vs 多设备）
10. **P1-10** · 缺 session 表清理策略（`expires_at_hard` 过期后 DELETE）
11. **P1-11** · 缺 `pytest-httpx` / `freezegun` 依赖声明（M2 测试必用）
12. **P1-12** · 缺 cookie 安全设置 / 前端 token 存储策略
13. **P1-13** · 缺 token 错误计数（5 次/15min 账号锁）
14. **P1-15** · 缺 CSRF 保护策略说明（Header 模式天然安全但要显式写）
15. **P2-1** · Files 表缺 M2 头部模板注释
16. **P2-2** · `secrets.token_urlsafe` UNIQUE retry 逻辑只写风险没写实现
17. **P2-3** · `GET /api/auth/me` 样板 endpoint 缺（M3 接入样板）
18. **P2-4** · `LogoutRequest` 设计冗余（前端已有 Authorization header）
19. **P2-5** · 慢测试 fixture 设计文档化
20. **P2-6** · 缺 `Dockerfile` 文档（部署用）
21. **P2-7** · `from app.config import settings` 全 M 统一约定
22. **P2-8** · `validate_token_expiry` 没显式说明 timezone 假设
23. **P2-9** · 缺 `pytest-httpx` mock tei / langfuse 健康检查的示例
24. **P2-10** · `extend_session` 触发条件 hardcoded（应可配）

外加 M1 范围内的关键提醒（推动 M1 补字段）：
- M1 P2-4 `users.failed_login_attempts` / `locked_until`（M2 P1-13 必用）
- M1 P2-6 `auth_sessions.ip_address` / `user_agent`（M12 hardening 必用，M2 可暂不用）
- M1 P1-19 `users.username` citext（已通过 P1-8 业务层 lower() 解决）

---

## 落地建议

按 P0 → P1 → P2 优先级：

### 第一波（本轮必改，5 项 P0）
1. P0-1 依赖版本与 spec §8.3 对齐
2. P0-2 删 `pyjwt` 依赖或显式声明 deprecated 兼容层
3. P0-3 补 reset_limiter + fixed_ip fixture + 真实跑限速测试
4. P0-4 与 M1 协调 is_revoked 字段（选 A：DELETE 不留行 / 选 B：M1 加 is_revoked 列）
5. P0-5 `extend_session` 改 BackgroundTasks 或显式 task 引用

### 第二波（重要，14 项 P1）
6. P1-1 `validate_token_expiry` 抽单 `now` 变量
7. P1-2 Argon2 默认改 time_cost=3, memory=65536，加 rehash on login hook
8. P1-3 拆 `test_auth_tokens.py` 与 `test_auth_config.py`
9. P1-4 + P2-3 加 `GET /api/auth/me` 样板 endpoint
10. P1-5 修 `app/api/__init__.py` 双 prefix 冲突 + 写 `app/main.py` 挂载代码
11. P1-6 pyproject.toml 追加段给完整 toml
12. P1-7 加 `app/auth/password_validator.py` + 集成测试 weak password 422
13. P1-8 Pydantic RegisterRequest 加 username 校验
14. P1-9 明确 token 轮换策略（推荐方案 A 单设备）
15. P1-10 加 `app/auth/cleanup.py` purge_expired_sessions
16. P1-11 Tech Stack 补 `freezegun` / `pytest-httpx`
17. P1-12 风险表补前端 token 存储策略（推荐 Header 模式）
18. P1-13 推动 M1 补 `users.failed_login_attempts` / `locked_until` 字段
19. P1-14 `app/config.py` 末尾加 `settings = Settings()` 全局单例
20. P1-15 风险表补 CSRF 保护策略（Header 模式天然安全）

### 第三波（优化，10 项 P2）
21-30. P2-1 ~ P2-10

### 跨 M 协调（M2 改完后通知）
- **推 M1**：补 `users.failed_login_attempts` / `locked_until` 字段（M2 P1-13 必用）；补 `auth_sessions.is_revoked` 字段（M2 P0-4 必用）
- **推 M8 API**：使用 `GET /api/auth/me` 作为 protected endpoint 样板
- **推 M9 UI**：明确用 Authorization Header 存 token，不用 localStorage / cookie
- **推 M12 hardening**：argon2 rehash on login 完整实现；session 清理 cron 接入；M1 review P2-6 的 `ip_address` / `user_agent` 字段启用

### 估时修正
- M2 整体估时从 **5d → 7d**（P0 修补 1d + P1 实施 2d + 集成测试 1d + 跨 M 协调 1d + buffer 1d + 与 M1 schema 协调 1d）

### 等待决策
- X-1 `app/config.py` 拆分 `configs/` 子目录是否在 M2 阶段就动手（推荐是，避免 M7 时再拆要改 ~10 个 import 路径）
- P0-4 is_revoked 字段选 A（DELETE）还是 B（M1 补字段软吊销）——影响 M1 / M2 实施范围
- P1-9 token 轮换策略选 A（单设备）/ B（多设备最多 5 个）/ C（无策略延后）——影响 spec §9 V2 边界
- P1-13 账号锁阈值 5 次/15min 是否合理（spec §5 错误矩阵没明说）

---

## 状态

- **不可动手**：P0-1 ~ P0-5 共 5 项必改
- **建议本轮改**：P1-1 ~ P1-15 共 15 项
- **可下轮改**：P2-1 ~ P2-10 共 10 项
- **新问题合计**：24 个（已有 review 未列），覆盖依赖版本、慢测试解法、密码强度、token 轮换、session 清理、CSRF/cookie 安全、账号锁、timezone 假设
- **已有 review 验证**：M2 范围内 9 项，全部 ❌ 未改

M2 plan **结构齐、TDD 节奏好、与 spec 决策对齐好**，但**版本号不一致、慢测试解法只给一半、密码强度与 token 轮换 / session 清理 / 并发冲突 / 账号锁这些基础安全功能没设计**。修完 P0 + P1 前 6 项可动手，后 9 项 P1 强烈建议同轮改完以避免 M3 接入 auth 时再回溯 M2。
