"""DB repository layer (M2 NP-5 r2 — 9 方法 spec).

来源: 2026-06-10-rag-m2-auth.md Files 表 NP-5 r2 repository 契约段
- AuthSessionRepository (6 方法): create / find_by_token_hash / revoke /
  revoke_all_for_user / update_sliding_expiry / delete_expired
- UserRepository (4 方法): create / find_by_username / find_by_id / update

实现策略 (r2 修订):
- 静态方法 + AsyncSession 参数注入 → 便于测试 mock + 单测直接调
- 真实 DB 写入走 sqlalchemy session.add + commit / update + commit
- mock 测试中单测直接 monkeypatch 整个类

不包含: 事务管理 (caller 决定 boundary) / connection pool (M1 已有)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthSession, User
from app.db.session import async_session_factory


class AuthSessionRepository:
    """AuthSession CRUD (6 方法).

    所有方法接收 db: AsyncSession 参数 (caller 注入, 便于事务管理 + 测试 mock).
    """

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: UUID,
        token_hash: str,
        expires_at_sliding: datetime,
        expires_at_hard: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuthSession:
        """INSERT auth_sessions (P2-6 + M12 ip_address / user_agent 钩子).

        r2: 当前 M2 阶段 ip_address / user_agent 默认 None 不入库,
        M12 hardening 阶段由 caller (login_endpoint) 从 Request 注入.
        """
        session_obj = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at_sliding=expires_at_sliding,
            expires_at_hard=expires_at_hard,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(session_obj)
        await db.flush()
        return session_obj

    @staticmethod
    async def find_by_token_hash(
        db: AsyncSession,
        token_hash: str,
    ) -> Optional[AuthSession]:
        """SELECT FROM auth_sessions WHERE token_hash = :token_hash."""
        result = await db.execute(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke(db: AsyncSession, session_id: UUID) -> None:
        """P0-4 软吊销: UPDATE auth_sessions SET is_revoked = TRUE WHERE id = :id.

        r2: M1 schema 已补 is_revoked 字段 (NP-1).
        """
        await db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id)
            .values(is_revoked=True)
        )

    @staticmethod
    async def revoke_all_for_user(db: AsyncSession, user_id: UUID) -> int:
        """P1-9 单设备策略: login 时软吊销该 user 所有 active session.

        返回受影响行数 (caller 决定是否需要 assert).
        """
        result = await db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.is_revoked == False,  # noqa: E712
            )
            .values(is_revoked=True)
        )
        return result.rowcount or 0

    @staticmethod
    async def update_sliding_expiry(
        db: AsyncSession,
        session_id: UUID,
        new_expiry: datetime,
    ) -> None:
        """UPDATE auth_sessions SET expires_at_sliding = :new_expiry WHERE id = :id.

        P0-5 BackgroundTasks 续期路径.
        """
        await db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id)
            .values(expires_at_sliding=new_expiry)
        )

    @staticmethod
    async def delete_expired(
        db: AsyncSession,
        cutoff: datetime,
    ) -> int:
        """P1-10 cleanup: DELETE FROM auth_sessions WHERE expires_at_hard < :cutoff.

        cutoff 通常为 datetime.now(UTC) - 7d grace period.
        返回 rowcount.
        """
        result = await db.execute(
            delete(AuthSession).where(AuthSession.expires_at_hard < cutoff)
        )
        return result.rowcount or 0


class UserRepository:
    """User CRUD (4 方法)."""

    @staticmethod
    async def create(
        db: AsyncSession,
        username: str,
        email: Optional[str],
        password_hash: str,
    ) -> User:
        """INSERT users. username / email 已在 caller 归一.

        抛 IntegrityError 时 (unique partial index) caller 决定映射到 409.
        """
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
        )
        db.add(user)
        await db.flush()
        return user

    @staticmethod
    async def find_by_username(
        db: AsyncSession,
        username: str,
    ) -> Optional[User]:
        """SELECT FROM users WHERE username = :u AND deleted_at IS NULL."""
        result = await db.execute(
            select(User).where(
                User.username == username,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_id(
        db: AsyncSession,
        user_id: UUID,
    ) -> Optional[User]:
        """SELECT FROM users WHERE id = :id."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        db: AsyncSession,
        user_id: UUID,
        **fields: Any,
    ) -> None:
        """UPDATE users SET ... WHERE id = :id.

        fields 可包含: failed_login_attempts / locked_until / last_login_at /
        email / display_name / is_active / deleted_at / password_hash 等.
        """
        if not fields:
            return
        await db.execute(
            update(User).where(User.id == user_id).values(**fields)
        )


# Re-export IntegrityError for service 层捕获 username 冲突
__all__ = [
    "AuthSessionRepository",
    "UserRepository",
    "IntegrityError",
]