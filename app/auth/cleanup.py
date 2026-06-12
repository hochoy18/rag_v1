"""Session cleanup (M2 Task 6 — P1-10 清理过期 session).

来源: 2026-06-10-rag-m2-auth.md Task 6 GREEN 段
- 删除 expires_at_hard + 7d grace 之前的行
- 生产 cron 由 M12 hardening 接入

返回 rowcount (caller 用于 audit / metrics).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import AuthSessionRepository

GRACE = timedelta(days=7)


async def purge_expired_sessions(db: AsyncSession) -> int:
    """DELETE FROM auth_sessions WHERE expires_at_hard < NOW() - 7d."""
    cutoff = datetime.now(timezone.utc) - GRACE
    return await AuthSessionRepository.delete_expired(db, cutoff)


__all__ = ["purge_expired_sessions"]