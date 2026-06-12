"""FastAPI Depends 注入层 (M2 Task 7 — get_current_user).

来源: 2026-06-10-rag-m2-auth.md Task 7 GREEN 段
- P0-4: 不区分 not-found vs revoked 统一 404 (V1 决策 #7)
- P0-5: BackgroundTasks 续期 (不阻塞 + 不丢)
- P2-10: 阈值可配 (settings.auth.session_extend_threshold)

签名 (M2 → M8 契约):
    async def get_current_user(
        authorization: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_session),
    ) -> User

M8+ 路由 handler 直接 `user: User = Depends(get_current_user)` 即可.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import session_not_found, token_expired, user_not_found
from app.auth.service import extend_session
from app.auth.tokens import hash_token, validate_token_expiry
from app.config import settings
from app.db.repositories import AuthSessionRepository, UserRepository
from app.db.session import get_session

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    authorization: HTTPAuthorizationCredentials = Depends(_bearer),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_session),
):
    """FastAPI Depends — 路由级注入当前 User.

    流程:
    1. SHA-256 hash token
    2. find_by_token_hash (None 或 is_revoked → 404, P0-4 不区分)
    3. validate_token_expiry (False → 401)
    4. sliding 剩余 < threshold → BackgroundTasks.add_task(extend_session)
    5. find_by_id (None → 404)
    6. 返回 User ORM 对象
    """
    token_hash = hash_token(authorization.credentials)
    session = await AuthSessionRepository.find_by_token_hash(db, token_hash)
    if session is None or session.is_revoked:
        raise session_not_found()
    if not validate_token_expiry(session.expires_at_sliding, session.expires_at_hard):
        raise token_expired()

    # P0-5 BackgroundTasks 续期 (P2-10 阈值可配)
    sliding_remaining = session.expires_at_sliding - datetime.now(timezone.utc)
    if sliding_remaining < settings.auth.session_extend_threshold:
        background_tasks.add_task(extend_session, db, token_hash)

    user = await UserRepository.find_by_id(db, session.user_id)
    if user is None:
        raise user_not_found()
    return user


__all__ = ["get_current_user"]