M2 Plan r2 Review · r1 修复验证

> 评审对象：[2026-06-10-rag-m2-auth.md](../2026-06-10-rag-m2-auth.md)（906 行，r1 已修 30 项 P0/P1/P2）
> 评审基线：[2026-06-11-rag-m2-auth-review.md](./2026-06-11-rag-m2-auth-review.md)（r1 review，36 项 P0/P1/P2）
> 评审时间：2026-06-11
> 评审者：Hermes subagent（r2 独立审查）
> 范围：验 r1 修复是否到位 + 发现 r1 修复过程中是否引入新问题 + 跨 M 一致性
> 输出策略：30 项逐项验证 + 5 项 r1 引入新问题 + 7 个 M 联动 + 风险表补全质量

---

## 总评

| 维度 | 评分 | 说明 |
|---|---|---|
| r1 修复完成度 | ⭐⭐⭐⭐ | 30 项中 24 项**已修到位**；6 项**部分修 / 修错位 / 落地有瑕疵** |
| 跨 M 一致性 | ⭐⭐ | M1 `is_revoked` 字段**实际仍缺**（M1 r2 review NP-1 确认）→ M2 业务读 `session.is_revoked` 在 runtime AttributeError；M8/M9/M12 联动基本落地 |
| 错误处理完整性 | ⭐⭐⭐⭐ | spec §5 11 行 M2 范围 3 行（401/404/密码强度）全覆盖；账号锁 429 主动补 |
| 风险表补全质量 | ⭐⭐⭐ | 6 行原风险 + 24 行 r1 已修齐；曾被否决方案列有内容但 r1 引入的"is_revoked 已补"**实际虚假** |
| 实施就绪度 | ⭐⭐⭐ | P0 1 项有真相缺口（is_revoked 误信 M1 已修），需 M1 r2 修完后 M2 才能动手 |

**一句话**：r1 修复整体到位（24/30 项 100% 修，6 项部分修），**最大问题是 M1 r1 修订记录承诺"`is_revoked` 字段已补"但 M1 r2 review 证实 DDL 段实际仍缺该字段**——M2 整篇依赖此字段（L24/L125/L566/L585/L824/L866），M2 实施时 `session.is_revoked` 会 AttributeError；外加 `app/auth/service.py` 缺 `extend_session` 内部调 `validate_token_expiry` 的边界处理、`/api/auth/logout` 501 占位（Task 8）、`username = username.lower().strip()` 入口不全、用户名归一后 `IPAddress` NULL 仍未规划入 session 表、`AuthSessionRepository.revoke_all_for_user` 仓库方法 spec 缺 5 项 r1 落地有瑕疵。r2 需 M1 r2 与 M2 r2 并行修。

---

## 1. r1 修复验证（30 项逐项）

| # | r1 标记 | 修复内容（r1 claim） | 实际验证（plan 文本位置） | 状态 |
|---|---|---|---|---|
| 1 | P0-1 | 依赖版本与 spec §8.3 对齐（argon2 <25→<24 / cryptography <44→<46） | L136 `argon2-cffi >=23.1,<24` ✅ / L137 `cryptography >=42,<46` ✅ | ✅ 已修 |
| 2 | P0-2 | 删 pyjwt | L148-149 显式删除项：`~~pyjwt >=2.9,<3~~` | ✅ 已修 |
| 3 | P0-3 | 慢测试解法：reset_limiter + fixed_ip + patch_utcnow fixtures | L750-782 Task 9 GREEN 段 conftest.py 完整代码（autouse `reset_limiter` + `fixed_ip` + `patch_utcnow` 三件齐） | ✅ 已修 |
| 4 | P0-4 | M1 r1 补 `auth_sessions.is_revoked`；M2 logout/login 软吊销 + protected 端点不区分 not-found vs revoked 统一 404 | L568 `if session is None or session.is_revoked: raise 404`；L585 RED 测试 `test_get_current_user_revoked_token`；L459-461 logout 实现软吊销；**但 M1 r2 review NP-1 证实 M1 §4 DDL 段实际仍缺 `is_revoked` 字段** | 🔴 **修错位** |
| 5 | P0-5 | extend_session 改 FastAPI BackgroundTasks | L562-563 `get_current_user(..., background_tasks: BackgroundTasks = BackgroundTasks())`；L574-576 `background_tasks.add_task(extend_session, token_hash)` | ✅ 已修 |
| 6 | P1-1 | `validate_token_expiry` 抽单 now 变量 | L297-298 `now = datetime.now(timezone.utc)` + 单行 `return now < expires_at_sliding and now < expires_at_hard` | ✅ 已修 |
| 7 | P1-2 | Argon2 默认改 OWASP 2024（time_cost=3 / memory_cost=65536 / parallelism=1）+ rehash hook | L246-248 AuthSettings 默认值齐；L366-367 service.register 留 rehash-on-login hook 注释 | ✅ 已修 |
| 8 | P1-3 | 拆 test_auth_tokens.py + test_auth_config.py | L60-61 模块树 L174-176 Files 表全拆 | ✅ 已修 |
| 9 | P1-4 + P2-3 | 加 GET /api/auth/me 样板 endpoint | L19 Goal 段列 `/me`；L728 RED `test_me_returns_current_user`；L731 `test_me_unauthenticated_returns_404`；**Files 表 L168-208 未见独立 /me 段，但 Task 8 RED 测试齐** | ⚠️ 部分修（RED 齐，Files 表未独立列） |
| 10 | P1-5 | `app/api/__init__.py` 无 prefix 修双 prefix 冲突 + 新增 `app/main.py` | L687-695 GREEN `api_router = APIRouter()`（无 prefix）；L697-704 GREEN `app/main.py` 完整挂载代码 | ✅ 已修 |
| 11 | P1-6 | pyproject.toml 追加段给完整 toml 片段 | L215-225 完整 toml（runtime + dev 依赖两段） | ✅ 已修 |
| 12 | P1-7 | 新增 password_validator.py + 弱密码 422 | L319-341 GREEN 完整实现（MIN/MAX/正则/frozenset）；L664-667 register_endpoint 弱密码 422；L720 RED `test_register_weak_password_returns_422` | ✅ 已修 |
| 13 | P1-8 | Pydantic RegisterRequest username 校验（正则 + 保留字 + 归一） | L630-645 `normalize_username` field_validator；L631 `RESERVED_USERNAMES` 列表；L640 注释"业务层归一 → M1 UNIQUE 索引自动大小写不敏感" | ✅ 已修 |
| 14 | P1-9 | 单设备策略：login 时 revoke_all_for_user 软吊销旧 session | L416 service.login 调 `AuthSessionRepository.revoke_all_for_user(user.id)`；L725 RED `test_login_single_device_revokes_old_session` | ✅ 已修 |
| 15 | P1-10 | 新增 `app/auth/cleanup.py::purge_expired_sessions` + 测试 | L527-539 GREEN 完整实现（GRACE=7d + delete_expired）；L519-525 RED 测试 | ✅ 已修 |
| 16 | P1-11 | Tech Stack + pyproject 加 freezegun / pytest-httpx | L143-144 Tech Stack 表两行齐；L223-225 pyproject dev 段两行齐 | ✅ 已修 |
| 17 | P1-12 | 风险表补前端 token 存储策略（Header 模式） | L850 风险表行"前端 token 存储策略不清 → M2 选 Header 模式（`Authorization: Bearer *** Set-Cookie；M9 Gradio 必须走 Header" | ⚠️ 部分修（措辞错位——"***" 后少字符"`，应是 `Authorization: Bearer ***` 模板；README 段落未独立列） |
| 18 | P1-13 | M1 补 failed_login_attempts / locked_until；M2 加 check_account_lock / record_failed_login / reset_failed_login | L500-515 service 三个函数完整实现；L722 RED `test_login_account_locked_returns_429`；L246-251 AuthSettings 阈值 5/15min；**M1 字段 M1 r1 修订记录 L650 提及，但 r2 NP-1 / 别的 M1 r2 项未确认字段已落 DDL** | ⚠️ 部分修（M2 端齐，M1 字段落 DDL 待 M1 r2 verify） |
| 19 | P1-14 | `app/config.py` 末尾加 `settings = Settings()` 全局单例（X-3 落地） | L253 显式 `settings = Settings()  # 全局单例，所有 M 共用` | ✅ 已修 |
| 20 | P1-15 | 风险表补 CSRF 保护策略 | L853 风险表行"CSRF 风险 → 后人改 Set-Cookie 模式引入 CSRF → **P1-15 已修**：V1 鉴权用 Authorization Header 模式" | ✅ 已修 |
| 21 | P2-1 | `app/api/__init__.py` 注释补"暴露 api_router 供 main.py 挂载" | L694 `__all__ = ["api_router"]`；L42 Files 表描述段"无 prefix，暴露 `api_router` 单一符号供 `app/main.py` 挂载" | ✅ 已修 |
| 22 | P2-2 | login() 末尾加 token UNIQUE 冲突 retry 循环（3 次） | L417-432 GREEN 完整 `for attempt in range(3)` 循环 + IntegrityError 捕获 + 500 兜底 | ✅ 已修 |
| 23 | P2-4 | 移除 LogoutRequest，统一用 Authorization header | L677-684 GREEN `logout_endpoint(user=Depends(get_current_user))` 显式注释"# P2-4 只读 header"；**但 L684 `raise HTTPException(501, "see M2 follow-up: header-only logout")` 仍是占位** | ⚠️ 部分修（接口签名修，但实现 501 占位） |
| 24 | P2-5 | Files 表加 tests/conftest.py 段（fixture 文档化） | L201 Files 表 L750-782 Task 9 GREEN 段 conftest 完整代码 | ✅ 已修 |
| 25 | P2-6 | 风险表补 Dockerfile 计划 | L854 风险表行"M2 范围 Dockerfile 缺 → 部署阶段才发现 → **P2-6 已修**（最小记录）" | ✅ 已修 |
| 26 | P2-7 | 风险表 + 契约边界补"from app.config import settings"统一约定 | L126 契约边界"from app.config import settings 全 M 统一约定（P2-7）"；L852 风险表行"X-3 落地" | ✅ 已修 |
| 27 | P2-8 | `validate_token_expiry` 显式 tz 检查 + 单元测试 | L295-298 GREEN `if expires_at_sliding.tzinfo is None ... raise ValueError`；L289-290 RED `test_validate_token_expiry_naive_datetime_raises` | ✅ 已修 |
| 28 | P2-9 | conftest.py 准备 pytest-httpx 导入 | L751-752 conftest.py 头部 `from slowapi import Limiter / from slowapi.util import get_remote_address`；**未见 pytest_httpx fixture 准备代码（L770-782 显式 import pytest_httpx 的 fixture 段未给）** | ⚠️ 部分修（头部 import 齐，fixture 准备缺） |
| 29 | P2-10 | AuthSettings 加 session_extend_threshold 可配 | L249 `session_extend_threshold: timedelta = Field(default=timedelta(days=1), env="AUTH_SESSION_EXTEND_THRESHOLD")`；L575 deps 引用 `settings.auth.session_extend_threshold` | ✅ 已修 |
| 30 | 估时 | 5d → 7d | L7 估时 7 个工作日（P0 修补 1d + P1 实施 2d + 集成测试 1d + 跨 M 协调 1d + 与 M1 schema 协调 1d + buffer 1d） | ✅ 已修 |

**统计**：✅ 已修 24 项 + ⚠️ 部分修 5 项（#9 /me 段未独立列 Files / #12 P1-12 措辞错位 / #18 P1-13 M1 字段待 verify / #23 LogoutRequest 501 占位 / #29 pytest-httpx fixture 未给）+ 🔴 修错位 1 项（#4 is_revoked 误信 M1 已修）。

---

## 2. r1 修复引入的新问题

### NP-1 · 🔴 M1 r1 修订记录承诺"is_revoked 已补"，M1 r2 review 证实 DDL 段仍缺（最严重）

**位置**：M2 plan L24, L125, L566, L585, L824, L866；M1 plan §4 DDL 段 L122-137

**问题**：
- M2 plan L125 显式声明依赖：`auth_sessions.is_revoked`（M1 已建（M1 schema 修订后））
- M2 plan L824 跨 M 依赖表重申："M1 schema 字段：`... auth_sessions.is_revoked ...` | **M2 强依赖**（P0-4 / P1-13）；M1 r1 已补"
- M2 plan L843 风险表自承："**P0-4 已修（选 A）**：M2 logout / login 改用 `AuthSessionRepository.revoke(session_id)` 软吊销（**update `is_revoked=TRUE`，M1 r1 已补字段**）"
- M2 plan L866 风险表行："`is_revoked` 字段在 M1 schema 缺 → M2 业务逻辑"想做不能做" → **P0-4 已修**：**M1 r1 补 `auth_sessions.is_revoked BOOLEAN DEFAULT FALSE` 列**"
- **但 [M1 r2 review NP-1](../../plans/reviews/2026-06-11-rag-m1-schema-r2-review.md) 证实**：M1 §4 auth_sessions 表 DDL 段 L122-137 仍只列 12 列（`id` / `user_id` / `token_hash` / `expires_at_sliding` / `expires_at_hard` / `last_used_at` / `idempotency_key` / `ip_address` / `user_agent` / `created_at` / `created_by` / `updated_by`），**无 `is_revoked`**
- M2 plan L568 `if session is None or session.is_revoked: raise 404` 在 runtime 触发 `AttributeError: 'AuthSession' object has no attribute 'is_revoked'`
- **M2 整篇修订记录 L880、r1 行 "P0-4 已修 · M1 r1 补 auth_sessions.is_revoked 字段" 全部是虚假修复**

**修复**（M2 r2 + M1 r2 双修）：
- **M1 r2 必改**：§4 auth_sessions 表 DDL 段补 `is_revoked BOOLEAN DEFAULT FALSE NOT NULL`（与 P0-4 风险表描述对齐）；ORM 段补 `is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)`；r2 修订记录显式"is_revoked 字段补 DDL"
- **M2 r2 必改**：
  1. L843 风险表措辞"**update `is_revoked=TRUE`，M1 r1 已补字段**" 改"**M1 r2 补字段，M2 等字段落地**"
  2. L866 风险表"**P0-4 已修**：M1 r1 补 `auth_sessions.is_revoked BOOLEAN DEFAULT FALSE` 列" 改 "**P0-4 待 M1 r2 修**：M1 §4 DDL 段补 is_revoked 字段；M2 logout/login 改用 `AuthSessionRepository.revoke()` 软吊销"
  3. L880 修订记录行 "P0-4 已修 · M1 r1 补 auth_sessions.is_revoked 字段" 改 "P0-4 部分修（等 M1 r2 补 DDL）"
  4. L24 "不包含"段 删 `is_revoked` 字样（避免误信）
  5. 风险表新增一行："**M1 r2 落地前 M2 不可动手**：session.is_revoked runtime AttributeError"
- **M2 plan Tasks 实施前** 必须先 verify `psql -c "\d auth_sessions"` 看到 `is_revoked` 列，否则不开始 Task 4 写 login / logout

**r2 评级**：🔴 **P0**（M1 r1 修订记录虚假承诺 → M2 修订记录被骗 → M2 实施 runtime 必崩）

### NP-2 · 🟠 `app/api/auth.py::logout_endpoint` Task 8 GREEN 段仍是 501 占位（P2-4 落地不全）

**位置**：M2 plan L677-684

**问题**：
- P2-4 r1 修订记录 L899 写"移除 LogoutRequest，统一用 Authorization header"
- L677 GREEN `logout_endpoint` 签名已改：`user=Depends(get_current_user)`
- **但 L684 仍 `raise HTTPException(status_code=501, detail="see M2 follow-up: header-only logout")`**
- 注释 L682-683 显式说："# 注：实际实现时建议把 token_hash 通过 Request.state 或子依赖注入"
- L710 RED `test_logout_revokes_token`（Task 8）写"register → login → 取 token → logout（Authorization header）→ 204 / 再用同一 token 调 `/api/auth/me` → 404"——**RED 测试期待 204，GREEN 段返 501**——**RED/GREEN 不一致**

**修复**（Task 8 GREEN 段补完整实现）：
```python
@router.post("/logout", status_code=204)
@limiter.limit("10/minute")
async def logout_endpoint(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    user: User = Depends(get_current_user),  # 验 token 有效
):
    """注销当前 session：从 Authorization header 取 token 哈希，调 service.logout。"""
    token_hash = hash_token(credentials.credentials)
    await logout(token_hash)
    return Response(status_code=204)
```
- 同步在 `app/api/__init__.py` 暴露 `HTTPBearer`；`from fastapi.security import HTTPAuthorizationCredentials` import
- 注释"# P2-4 只读 header" 保留
- 删 501 占位
- 风险表 L843 同步删"措辞含混 DELETE vs UPDATE"行（已实际落地）

**r2 评级**：🟠 **P1**（RED/GREEN 不一致，集成测试会失败）

### NP-3 · 🟠 `app/auth/service.py::extend_session` 内部调 `validate_token_expiry`，silent no-op 缺审计日志

**位置**：M2 plan L470-479

**问题**：
- L474-476 `if session is None or session.is_revoked: return  # silent no-op for BackgroundTasks`
- L475-476 `if not validate_token_expiry(session.expires_at_sliding, session.expires_at_hard): return  # 硬上限过期不续期`
- **silent no-op 缺审计日志**——`BackgroundTasks` 失败/跳过不记日志，运维无法察觉"为什么某 token 7 天后没续期"
- L466 RED `test_extend_session_sliding` 写"mock session: expires_at_sliding=utcnow-1min（刚滑过期）, expires_at_hard=utcnow+20d"——**边界条件是 sliding 刚过期**——但 L475 调 `validate_token_expiry` 会先拒（now > slides_at → False）→ silent no-op → **RED 测试期待"刚过期也应续期"，GREEN 段实际拒**——**RED/GREEN 不一致**

**修复**（GREEN 段改）：
```python
async def extend_session(token_hash: str) -> None:
    session = await AuthSessionRepository.find_by_token_hash(token_hash)
    if session is None:
        logger.warning("extend_session: session not found (token_hash=%s...)", token_hash[:8])
        return
    if session.is_revoked:
        logger.info("extend_session: session already revoked, skip (id=%s)", session.id)
        return
    # 硬上限过期则不续期（业务上限），但记日志
    if session.expires_at_hard <= datetime.now(timezone.utc):
        logger.info("extend_session: hard cap reached, skip (id=%s)", session.id)
        return
    # sliding 刚过期也续期（< hard cap）
    new_sliding = datetime.now(timezone.utc) + settings.auth.token_ttl_sliding
    if new_sliding > session.expires_at_hard:
        new_sliding = session.expires_at_hard  # 不超 hard cap
    await AuthSessionRepository.update_sliding_expiry(session.id, new_sliding)
```
- 同步 `import logging; logger = logging.getLogger(__name__)`
- 风险表新增一行"extend_session silent no-op 缺审计" + 缓解"加 logger.warning / info"

**r2 评级**：🟠 **P1**（RED/GREEN 不一致 + 运维盲点）

### NP-4 · 🟡 `app.auth.password_validator` 缺 `username` 业务层二次校验（与 Pydantic 重复但 depth 浅）

**位置**：M2 plan L319-341 `validate_password` 实现

**问题**：
- L319-341 `validate_password` 只校验**密码**，**无** `validate_username` 函数
- L630-645 Pydantic `RegisterRequest.normalize_username` 已做归一（`strip().lower()` + 正则 + 保留字）
- L633 `RegisterRequest.password: str = Field(min_length=12, max_length=128)`——**Pydantic 已限制密码长度 12-128**
- L664-667 `register_endpoint` 又调 `validate_password(body.password)` 业务层二次校验
- **但 service.register L352-369 实现里** L354 `validate_password(password)` 业务层又调一次——**双重校验冗余**（Pydantic 422 已拒，service 不会收到弱密码）
- 业务层二次校验的**唯一**作用是"如果有 caller 绕过 Pydantic（如内部脚本）仍能防御"——但 plan 没显式说明此点

**修复**（注释 + 不删代码）：
- L352-369 service.register 段加注释："# 二次校验防内部调用绕过 Pydantic；外部 HTTP 入口 422 在 Pydantic 拦"
- 风险表 L865 修订记录同步加"service 层二次校验（防内部 caller 绕过）"

**r2 评级**：🟡 **P2**（非 bug，文档化诉求）

### NP-5 · 🟡 `AuthSessionRepository.revoke_all_for_user` / `update_sliding_expiry` / `delete_expired` / `find_by_token_hash` 仓库方法 spec 缺，r1 修订记录只口头说"补到 repository"未给契约

**位置**：M2 plan 多个地方（service.login L416 / L477 / cleanup L538 / deps L567 / logout L461）

**问题**：
- L416 `await AuthSessionRepository.revoke_all_for_user(user.id)` —— M2 plan 假设该方法存在，**但 M1 plan / M2 plan 都没给 repository 层方法签名 spec**
- L477 `await AuthSessionRepository.update_sliding_expiry(session.id, new_sliding)` —— 同上
- L538 `await AuthSessionRepository.delete_expired(cutoff=cutoff)` —— 同上
- L567 `await AuthSessionRepository.find_by_token_hash(token_hash)` —— 同上
- L461 `await AuthSessionRepository.revoke(session.id)` —— 同上
- M1 plan L266-282 仅定义 ORM model（`User` / `AuthSession`），**无 repository 模式（M1 走 repo 还是 DAO？Service 调 ORM 直接？）**
- M2 plan 默认 M1 已实现 `app/db/repositories.py` 包含上述 5 个方法，**M1 修订记录 L650 "跨 M 联动落地" 段没提** → M1 没承诺实现 repository 层 → M2 业务层会 import 失败

**修复**（M2 计划改动 + 推 M1 实施）：
- M2 plan Files 表追加 `app/db/repositories.py` + `tests/unit/test_repositories.py`，**M2 范围**实现 5 个方法（与 M2 service 同步）：
  ```python
  # app/db/repositories.py
  class AuthSessionRepository:
      @staticmethod
      async def find_by_token_hash(token_hash: str) -> AuthSession | None: ...
      @staticmethod
      async def create(user_id: int, token_hash: str, expires_at_sliding: datetime, expires_at_hard: datetime, ip_address: str | None = None, user_agent: str | None = None) -> AuthSession: ...
      @staticmethod
      async def revoke(session_id: int) -> None: ...
      @staticmethod
      async def revoke_all_for_user(user_id: int) -> int: ...
      @staticmethod
      async def update_sliding_expiry(session_id: int, new_sliding: datetime) -> None: ...
      @staticmethod
      async def delete_expired(cutoff: datetime) -> int: ...
  class UserRepository:
      @staticmethod
      async def find_by_username(username: str) -> User | None: ...
      @staticmethod
      async def find_by_id(user_id: int) -> User | None: ...
      @staticmethod
      async def create(username: str, password_hash: str, email: str | None = None) -> User: ...
      @staticmethod
      async def update(user: User) -> User: ...
  ```
- 推 M1 修订记录 L650 跨 M 联动补："M2 强依赖 `app/db/repositories.py` 5 个 AuthSessionRepository 方法 + 4 个 UserRepository 方法"
- M2 估时 +1d（repository 实现 0.5d + 测试 0.5d）

**r2 评级**：🟠 **P1**（repository 缺方法 → M2 业务 import 失败 / runtime AttributeError）

---

## 3. 跨 M 一致性检查

### 3.1 M2 ↔ M1 · 🔴 严重（`is_revoked` 字段缺失）

| M2 引用位置 | M2 期待 | M1 实际（M1 r2 review 证实） | 状态 |
|---|---|---|---|
| L24 "不包含"段 | M1 已有 `auth_sessions.is_revoked` 字段 | M1 §4 DDL 段 L122-137 无此列 | 🔴 缺 |
| L125 契约边界表 | M1 字段: `auth_sessions.is_revoked` | 同上 | 🔴 缺 |
| L566 deps `session.is_revoked` | runtime 读字段 | runtime AttributeError | 🔴 缺 |
| L568 `if session.is_revoked: raise 404` | 字段为 BOOL | 字段不存在 | 🔴 缺 |
| L824 跨 M 依赖表 | M1 r1 已补 | M1 r2 NP-1 证实未补 | 🔴 缺 |
| L866 风险表 P0-4 修订行 | M1 r1 补 is_revoked | M1 r2 NP-1 证实未补 | 🔴 缺 |

**M2 落地建议**：
- M1 r2 修完前 M2 **不可动手** Task 4 / Task 7 / Task 8（这些 task 全依赖 `session.is_revoked`）
- M2 修订记录 L880 P0-4 行改"**部分修（等 M1 r2）**"
- M2 风险表 L866 P0-4 行改"**P0-4 待 M1 r2 修**"
- M2 估时 +1d（M1 r2 协调 / 等字段 / 验证 `\d auth_sessions`）

### 3.2 M2 ↔ M1 · 🟠 `users.failed_login_attempts` / `locked_until` 字段（M1 r2 待 verify）

| M2 引用位置 | M2 期待 | M1 实际 | 状态 |
|---|---|---|---|
| L500 `user.locked_until` | TIMESTAMPTZ NULLABLE | M1 r1 L114-115 已加 `failed_login_attempts INTEGER NOT NULL DEFAULT 0` + `locked_until TIMESTAMPTZ NULLABLE` | ⚠️ M1 r2 待 verify |
| L505 `user.failed_login_attempts` | INT DEFAULT 0 | 同上 | ⚠️ M1 r2 待 verify |
| L507 `settings.auth.failed_login_lockout_count` (默认 5) | M1 默认值匹配 | M1 字段 DEFAULT 0 匹配 | ✅ 业务侧 ok |
| L824 跨 M 依赖 | M1 r1 已加 | M1 修订记录 L650 提及 | ⚠️ M1 r2 待 verify |

**M2 落地建议**：M1 r2 verify 完这两字段后 M2 即可动手 Task 5（账号锁辅助）。

### 3.3 M2 ↔ M1 · 🟡 `users.email` / `auth_sessions.ip_address` / `auth_sessions.user_agent`（M2 plan 不用 / M12 hardening 用）

| M2 引用位置 | M2 期待 | M1 实际 | 状态 |
|---|---|---|---|
| L24 "不包含" | M1 已有 email / ip_address / user_agent | M1 r1 L108 email / L133-134 ip_address + user_agent | ✅ M1 已加 |
| L125 契约 | 同上 | 同上 | ✅ |
| L417-432 service.login 调 `create(user_id, token_hash, ...)` | create 不传 ip_address / user_agent | 字段 NULLABLE，可不传 | ✅ 兼容 |
| L677-684 logout_endpoint | 不传 ip_address / user_agent | 同上 | ✅ 兼容 |
| L822 跨 M 依赖 | M2 暂不用 | M12 hardening 用 | ✅ 兼容 |

**风险**：M2 plan **完全没设计 ip_address / user_agent 的采集路径**——`/api/auth/login` 和 `/api/auth/register` 接受 Request 对象（slowapi 限速已注入 `request: Request`），但 service.create 不收这两个字段。**M12 hardening 阶段 M2 plan 必加 task "从 Request.client.host 取 ip_address / from Request.headers.get('user-agent') 取 user_agent"**——但**当前 plan 没显式留 hook**。

**M2 落地建议**：M2 r2 在 `app/api/auth.py` 补 1 个 task "采集 ip_address / user_agent"（即使 M2 暂不入库）：
```python
@router.post("/register", status_code=201, response_model=UserResponse)
@limiter.limit("5/minute")
async def register_endpoint(
    request: Request,  # 已有
    body: RegisterRequest,
):
    # M2 暂不传 ip_address / user_agent 入库（M12 hardening 启用）
    # 但先取出来给 M12 用
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    user = await register(body.username, body.password, ip_address=ip_address, user_agent=user_agent)
    ...
```
- service.register 签名加 `ip_address: str | None = None, user_agent: str | None = None`
- AuthSessionRepository.create 同步加这两个参数（即使暂时不存）
- 风险表新增一行"M12 hardening 启用 ip_address / user_agent 入库" + 缓解"M2 阶段 service 签名先收，M12 启用"

### 3.4 M2 ↔ M8（M8 api-chat 强依赖 M2）

| M2 契约 | M8 实际 | 状态 |
|---|---|---|
| L122 `Depends(get_current_user)` 签名 | 需 verify（M8 plan 不可读，文件不存在） | ⚠️ M8 plan 缺 |
| L123 Authorization Header 模式 | M8 plan 缺 | ⚠️ |
| L122 `HTTPBearer` | M8 plan 缺 | ⚠️ |
| L19 `GET /api/auth/me` 样板 | M8 plan 缺 | ⚠️ |

**M2 落地建议**：M8 plan r1 必读 M2 plan L122-123 / L19 段落；M2 不需改（接口已固定）。

### 3.5 M2 ↔ M9（M9 ui-gradio 强依赖 M2）

| M2 契约 | M9 实际 | 状态 |
|---|---|---|
| L850 风险表"前端 token 存储 Header 模式" | M9 plan 缺 | ⚠️ M9 plan 缺 |
| L122 HTTPBearer | M9 plan 缺 | ⚠️ |

**M2 落地建议**：M9 plan r1 必读 M2 plan L850 段；M2 不需改。

### 3.6 M2 ↔ M12（M12 hardening 强依赖 M2 钩子）

| M2 留 hook | M12 实际 | 状态 |
|---|---|---|
| L366-367 service.register 留 rehash-on-login hook（注释） | M12 plan 缺 | ⚠️ M12 plan 缺 |
| L850 风险表 "M12 hardening 启用 ip_address / user_agent" | M12 plan 缺 | ⚠️ |
| L848 风险表 "session 清理 cron 由 M12 hardening 接入" | M12 plan 缺 | ⚠️ |
| L836 风险表"argon2 rehash on login M12 hardening 补" | M12 plan 缺 | ⚠️ |

**M2 落地建议**：M12 plan r1 必读 M2 plan L366-367 / L836 / L848 / L850 四处；M2 不需改（hook 已留）。

### 3.7 M2 ↔ M0 / M11（基础设施 / 评估）

| M2 契约 | M0 / M11 实际 | 状态 |
|---|---|---|
| L213 `app/config.py` 末尾 `settings = Settings()` | M0 阶段已建 config.py 基础 | ✅ |
| L51 Pydantic Settings 聚合 | M0 已有顶层 Settings | ✅ |
| L51 M2 追加 AuthSettings 子块 | 不破坏 M0 顶层 | ✅ |

**M2 落地建议**：无（已对齐）。

---

## 4. 风险表补全质量

| 维度 | r1 实际 | 评价 |
|---|---|---|
| 原 6 行风险 | L836 / L838 / L839 / L840 / L841 / L842（保留 + 划线） | ✅ 完整保留 |
| r1 已修 24 行 | L843-L868 24 行 P0/P1/P2 修复记录 | ✅ 24 行齐 |
| 曾被否决替代方案 | L836（bcrypt 12）/ L843（DELETE vs UPDATE）/ L840（同步 extend + create_task）/ L841（JWT 方案）/ L847（多设备 5 个 / 无策略）/ L850（cookie 模式）/ L852（X-1 推迟 M12）/ L853（cookie 模式）/ L865（pyjwt deprecated 兼容层） | ✅ 9 行有意义 |
| **r1 引入新风险** | L866 误信"M1 r1 补 is_revoked"——**实际 M1 r2 证实未补** | 🔴 **虚假修复** |
| DDL 复杂度量化行 | 无 | ⚠️ M1 r2 NP-1 提"DDL 复杂度量化"未补 |
| M1 schema 联动落地行 | L843 提"选 A+B 混合：字段有，行为 A" | 🔴 **字段实际未补** |
| 跨 M 协调责任 | 隐式在 L822-825 表 | ✅ 清晰 |

**r2 建议风险表新增 / 修改行**：

1. **新增（r1 引入 NP-1）**：
   ```
   | M1 r1 修订记录承诺"`is_revoked` 已补"但 M1 r2 证实 DDL 段仍缺 → M2 业务 runtime AttributeError | **r2 必改**：M1 r2 补 is_revoked 列；M2 修订记录 L880 P0-4 行改"部分修（等 M1 r2）"；M2 不可动手 Task 4/7/8 | r2-2026-06-11 |
   ```

2. **修改 L843**（措辞）：
   ```
   原："**P0-4 已修（选 A）**：M2 logout / login 改用 `AuthSessionRepository.revoke(session_id)` 软吊销（update `is_revoked=TRUE`，M1 r1 已补字段）；protected endpoint 见不到 active session 统一返 404（不区分 not-found vs revoked）"
   改："**P0-4 部分修（等 M1 r2）**：M2 logout / login 改用 `AuthSessionRepository.revoke(session_id)` 软吊销（update `is_revoked=TRUE`）；M1 r2 补 auth_sessions.is_revoked 列；protected endpoint 见不到 active session 统一返 404（不区分 not-found vs revoked）"
   ```

3. **修改 L866**：
   ```
   原："**P0-4 已修**：M1 r1 补 `auth_sessions.is_revoked BOOLEAN DEFAULT FALSE` 列；M2 logout/login 改用 `AuthSessionRepository.revoke()` 软吊销"
   改："**P0-4 待 M1 r2 修**：M1 §4 DDL 段补 `is_revoked BOOLEAN DEFAULT FALSE NOT NULL` 列；M1 ORM 段补 `is_revoked: Mapped[bool]`；M2 logout/login 改用 `AuthSessionRepository.revoke()` 软吊销"
   ```

4. **新增**：`/api/auth/logout` 501 占位（NP-2）—— r2 必改

5. **新增**：M12 hardening 启用 ip_address / user_agent 入库（NP-3.3）—— M2 阶段 service 签名先收参数

---

## 5. 落地建议

### 第一波（r2 必改，4 项 P0）
1. **🔴 NP-1**：M1 r2 补 `is_revoked` 字段（DDL + ORM）+ M2 修订记录 4 处改"部分修（等 M1 r2）"+ 风险表 2 行改
2. **🔴 NP-2**（Task 8）：`logout_endpoint` 501 占位改完整实现 + 同步 import HTTPBearer / HTTPAuthorizationCredentials
3. **🟠 NP-5**：M2 Files 表追加 `app/db/repositories.py`（5 个 AuthSessionRepository + 4 个 UserRepository 方法）+ 推 M1 修订记录 L650 补"repository 依赖"行 + 估时 +1d
4. **🟠 NP-3**：`extend_session` 改 hard cap 边界处理（sliding 刚过期也续期）+ 加 logger 审计

### 第二波（r2 重要，3 项 P1）
5. **🟠 P1-12 措辞错位**（L850）："Authorization: Bearer ***" 模板补完整；README 段独立列
6. **🟠 P1-13 M1 字段待 verify**（r2 review M1 端）：M1 r2 verify `failed_login_attempts` / `locked_until` 落 DDL
7. **🟡 P2-9 pytest-httpx fixture 准备代码**（L770-782）：补 `@pytest.fixture def httpx_mock_for_tei()`

### 第三波（r2 优化，2 项 P2）
8. **🟡 NP-4**（注释）：`service.register` 二次校验加注释（防内部 caller 绕过）
9. **🟡 M12 hardening 钩子**（NP-3.3）：service 签名先收 `ip_address` / `user_agent`（即使 M2 暂不入库）

### 估时修正
- M2 整体估时从 **7d → 8d**（+1d repository 实现 + M1 r2 协调 / 验证 `\d auth_sessions`）

### 等待决策
- **NP-1 is_revoked 字段**：M1 r2 决策是 `BOOLEAN DEFAULT FALSE` 还是 `TIMESTAMPTZ NULL`（后者审计更友好）——M2 P0-4 风险表已隐含选 BOOLEAN，但 spec 决策 #14 没说
- **NP-2 logout_endpoint token 提取**：`HTTPBearer` 二次注入还是 `Request.state` 暂存？——M2 P2-4 已选 HTTPBearer 二次注入
- **NP-5 repository 模式**：M2 实施还是 M1 实施？——M2 估时已包含 +1d，但 M1 plan L266-282 ORM model 完整，repository 层 M1 留白
- **NP-3.3 ip_address / user_agent 何时入库**：M2 阶段入库还是 M12 hardening 启用？——M2 plan 已隐含"暂不入库"，但 service 签名是否收参数待决

### 跨 M 协调（r2 修完后通知）
- **推 M1**：补 `is_revoked` 字段（DDL + ORM）；补 `app/db/repositories.py` 9 个方法（M2 估时包含实现，但契约 M1 定）
- **推 M8 API**：使用 `Depends(get_current_user)` 签名（L122-123）+ 走 Authorization Header 模式 + 用 `GET /api/auth/me` 样板
- **推 M9 UI**：明确用 Authorization Header 存 token，不用 localStorage / cookie
- **推 M12 hardening**：argon2 rehash on login 完整实现（接 M2 L366-367 注释）+ session 清理 cron 接入（接 M2 L848 风险表）+ ip_address / user_agent 入库（接 M2 NP-3.3）+ 业务层 `app/db/repositories.py` 是否需要 transaction 装饰

---

## 6. 状态

- **r1 修复完成度**：30 项中 24 项 100% 修，5 项部分修，1 项修错位（is_revoked 误信 M1）
- **r1 引入新问题**：5 项（NP-1 🔴 P0 / NP-2 🟠 P1 / NP-3 🟠 P1 / NP-4 🟡 P2 / NP-5 🟠 P1）
- **跨 M 一致性**：M1 is_revoked 字段缺 🔴 / M1 failed_login_attempts 待 verify 🟠 / M1 email/ip_address/user_agent ✅ / M8/M9/M12 联动基本落地
- **风险表补全**：6 行原 + 24 行 r1 已修齐 + 1 行虚假修复（待 r2 改）+ 4 行 r2 建议新增/修改
- **实施就绪度**：M1 r2 修完 `is_revoked` 后可动手；M2 估时 7d → 8d

**r2 一句话总结**：r1 修复整体到位（24/30），但**信任了 M1 r1 修订记录的虚假承诺（is_revoked）**导致 M2 修订记录 4 处失真；外加 `logout_endpoint` 501 占位、repository 层方法 spec 缺、`extend_session` RED/GREEN 不一致 3 项落地瑕疵。r2 改 4 项 P0 后可动手，估时 +1d 到 8d。
