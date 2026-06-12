"""Auth 业务逻辑层 (M2 Task 4/5 — register / login / logout / extend_session / 账号锁).

来源: 2026-06-10-rag-m2-auth.md Task 4/5 GREEN 段
- register: username 归一 + validate_password + argon2id hash + UserRepository.create
- login: 账号锁检查 + password verify + 单设备软吊销 + 签 token + AuthSession.create
- logout: 找 session + 软吊销 (NP-2 r2 完整实现, 不再 501)
- extend_session: BackgroundTasks 续期 (P0-5 + NP-3 r2 hard cap 边界处理)
- check_account_lock / record_failed_login / reset_failed_login (P1-13)

不感知 HTTP: 业务层抛 HTTPException 由 FastAPI handler 捕获.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import (
    account_locked,
    invalid_credentials,
    session_not_found,
    token_collision,
    username_taken,
    weak_password,
    wrong_password,
)
from app.auth.password_validator import validate_password
from app.auth.tokens import generate_token, hash_token
from app.config import settings
from app.db.models import User
from app.db.repositories import AuthSessionRepository, UserRepository

logger = logging.getLogger(__name__)


def _build_hasher() -> PasswordHasher:
    """Build argon2 PasswordHasher from settings (P1-2 OWASP 2024 defaults)."""
    return PasswordHasher(
        time_cost=settings.auth.argon2_time_cost,
        memory_cost=settings.auth.argon2_memory_cost,
        parallelism=settings.auth.argon2_parallelism,
    )


# ==================== Register ====================

async def register(
    db: AsyncSession,
    username: str,
    password: str,
    email: str | None = None,
) -> "User":  # noqa: F821
    """注册用户 (username / password 已归一).

    流程:
    1. validate_password 二次校验 (P1-7 弱密码 → 422)
    2. argon2id hash (OWASP 2024)
    3. UserRepository.create → IntegrityError → 409

    Returns: User ORM 对象.
    """
    try:
        validate_password(password)
    except ValueError as e:
        raise weak_password(str(e))

    ph = _build_hasher()
    password_hash = ph.hash(password)

    try:
        user = await UserRepository.create(
            db=db,
            username=username,
            email=email,
            password_hash=password_hash,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise username_taken()

    # P1-2 rehash-on-login hook 占位 (M12 hardening 阶段补完整)
    # if ph.check_needs_rehash(user.password_hash):
    #     user.password_hash = ph.hash(password)
    #     await UserRepository.update(db, user.id, password_hash=user.password_hash)
    #     await db.commit()
    return user


# ==================== Login ====================

async def login(
    db: AsyncSession,
    username: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """登录 → 返回明文 token (M2↔M12 r2 ip_address / user_agent 钩子).

    流程:
    1. find_by_username (None → 404 不暴露用户名不存在)
    2. check_account_lock (锁中 → 429)
    3. argon2 verify 密码 (Mismatch → 401 + record_failed_login)
    4. reset_failed_login (成功重置)
    5. revoke_all_for_user (P1-9 单设备策略)
    6. token UNIQUE retry 3 次 (P2-2)
    7. 返回明文 token (caller 透传给 client)
    """
    user = await UserRepository.find_by_username(db, username)
    if user is None:
        raise invalid_credentials()

    await check_account_lock(user)

    ph = _build_hasher()
    try:
        ph.verify(user.password_hash, password)
    except (VerifyMismatchError, VerificationError):
        await record_failed_login(db, user)
        raise wrong_password()

    await reset_failed_login(db, user)
    user.last_login_at = datetime.now(timezone.utc)
    await UserRepository.update(db, user.id, last_login_at=user.last_login_at)
    await db.commit()

    # P1-9 方案 A: 单设备策略 — 软吊销该 user 所有旧 session
    await AuthSessionRepository.revoke_all_for_user(db, user.id)
    await db.commit()

    # P2-2 token UNIQUE retry (最多 3 次)
    now = datetime.now(timezone.utc)
    sliding = now + settings.auth.token_ttl_sliding
    hard = now + settings.auth.token_ttl_hard
    for attempt in range(3):
        token = generate_token()
        token_hash = hash_token(token)
        try:
            await AuthSessionRepository.create(
                db=db,
                user_id=user.id,
                token_hash=token_hash,
                expires_at_sliding=sliding,
                expires_at_hard=hard,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await db.commit()
            return token
        except IntegrityError:
            await db.rollback()
            if attempt == 2:
                raise token_collision()
            continue
    # 不应到达; 兜底
    raise token_collision()


# ==================== Logout (NP-2 r2 完整实现) ====================

async def logout(db: AsyncSession, token_hash: str, user_id: UUID) -> None:
    """登出 (软吊销 token).

    NP-2 r2 已修: 不再 501 占位, 完整实现.
    P0-4 选 A: 不区分 not-found vs revoked, 统一 404.

    双保险: token_hash 找到 session 且属于 user_id 才吊销 (防越权).
    """
    session = await AuthSessionRepository.find_by_token_hash(db, token_hash)
    if session is None or session.is_revoked:
        raise session_not_found()
    # 双保险: 仅吊销属于当前 user 的 session
    if session.user_id != user_id:
        raise session_not_found()
    await AuthSessionRepository.revoke(db, session.id)
    await db.commit()


# ==================== Extend session (P0-5 BackgroundTasks) ====================

async def extend_session(db: AsyncSession, token_hash: str) -> None:
    """BackgroundTasks 续期 (P0-5 改 BackgroundTasks + NP-3 r2 hard cap 边界).

    NP-3 r2: hard cap 已达 → 不续期; sliding 刚过期但 hard 未到应续期.
    """
    session = await AuthSessionRepository.find_by_token_hash(db, token_hash)
    if session is None or session.is_revoked:
        logger.info(
            "extend_session: session not found or revoked, skip (hash_prefix=%s...)",
            token_hash[:8],
        )
        return
    now = datetime.now(timezone.utc)
    if now >= session.expires_at_hard:
        logger.info(
            "extend_session: hard cap reached, skip (id=%s, hard=%s)",
            session.id,
            session.expires_at_hard,
        )
        return
    new_sliding = now + settings.auth.token_ttl_sliding
    await AuthSessionRepository.update_sliding_expiry(db, session.id, new_sliding)
    await db.commit()
    logger.info(
        "extend_session: sliding extended (id=%s, new_sliding=%s)",
        session.id,
        new_sliding,
    )


# ==================== 账号锁辅助 (P1-13) ====================

async def check_account_lock(user) -> None:
    """检查账号锁 (P1-13). lock 中 → 429."""
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise account_locked()


async def record_failed_login(db: AsyncSession, user) -> None:
    """失败计数 + 阈值触发锁 (P1-13)."""
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= settings.auth.failed_login_lockout_count:
        user.locked_until = datetime.now(timezone.utc) + settings.auth.failed_login_lockout_duration
        user.failed_login_attempts = 0
    await UserRepository.update(
        db,
        user.id,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=user.locked_until,
    )
    await db.commit()


async def reset_failed_login(db: AsyncSession, user) -> None:
    """成功重置 (P1-13)."""
    user.failed_login_attempts = 0
    user.locked_until = None
    await UserRepository.update(
        db,
        user.id,
        failed_login_attempts=0,
        locked_until=None,
    )
    await db.commit()


__all__ = [
    "register",
    "login",
    "logout",
    "extend_session",
    "check_account_lock",
    "record_failed_login",
    "reset_failed_login",
]