"""Auth API endpoints (M2 Task 6).

4 endpoint:
- POST /api/auth/register: create user
- POST /api/auth/login: verify password + return token
- POST /api/auth/logout: revoke session (set is_revoked=TRUE)
- GET /api/auth/me: return current user info

来源: 2026-06-10-rag-m2-auth.md 修完版 (NP-1/NP-2 r2 修复)

注: app.auth.exceptions 是 HTTPException 工厂函数集合
    app.auth.service 函数签名: register(db, username, password, email) -> User
                              login(db, username, password) -> tuple[User, AuthSession, token_plain]
                              logout(db, token_hash) -> None
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    LoginRequest, RegisterRequest, UserResponse,
)
from app.auth.service import login, logout, register
from app.auth.tokens import hash_token
from app.config import settings
from app.db.session import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Username already exists"},
        422: {"description": "Invalid password (M2 password validator)"},
    },
)
async def register_endpoint(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Register a new user.

    r2 NP-1: username 检查时序问题, 用 PG unique constraint 兜底 (IntegrityError -> 409).
    service.register 返回 User (不含 session/token, 因为 register 不创 session,
    V1 决策: register 后须调用 /login 拿 token, 避免 register 路径被滥用).
    """
    try:
        # V1 注册暂不存 email (M1 schema 留 email 字段但 RegisterRequest 不收)
        user = await register(db, body.username, body.password, None)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        from app.auth.exceptions import username_taken
        msg = str(e).lower()
        if "username" in msg and "exists" in msg:
            raise username_taken()
        if "weak" in msg or "password" in msg:
            from app.auth.exceptions import weak_password
            raise weak_password(str(e))
        raise HTTPException(status_code=500, detail=f"register failed: {e}")

    return {
        "user_id": str(user.id),
        "username": user.username,
        "message": "user registered, call /api/auth/login to get token",
    }


@router.post(
    "/login",
    responses={
        401: {"description": "Invalid credentials"},
        429: {"description": "Account locked (5 failed attempts)"},
    },
)
async def login_endpoint(
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Verify password + return token.

    V1 决策 #7: 不区分 username 不存在 / 密码错 (统一 401).
    """
    try:
        user, auth_session, token_plain = await login(db, body.username, body.password)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        from app.auth.exceptions import account_locked
        msg = str(e).lower()
        if "lock" in msg:
            raise account_locked()
        # 不暴露 username 是否存在
        from app.auth.exceptions import invalid_credentials
        raise invalid_credentials()

    return {
        "user_id": str(user.id),
        "username": user.username,
        "token": token_plain,
        "expires_at_sliding": auth_session.expires_at_sliding.isoformat(),
        "expires_at_hard": auth_session.expires_at_hard.isoformat(),
    }


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,  # NP-2 r2 修复: 501 -> 204 完整实现
    responses={
        401: {"description": "Missing or invalid Authorization header"},
        404: {"description": "Session not found / already revoked"},
    },
)
async def logout_endpoint(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_session),
) -> None:
    """Revoke current session (set is_revoked=TRUE)."""
    from app.auth.exceptions import session_not_found

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]  # strip "Bearer "
    token_h = hash_token(token)
    try:
        await logout(db, token_h)
    except Exception as e:
        if "not found" in str(e).lower() or "revoked" in str(e).lower():
            raise session_not_found()
        raise HTTPException(status_code=500, detail=f"logout failed: {e}")
    return None


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        401: {"description": "Missing or invalid token"},
        404: {"description": "Session or user not found"},
    },
)
async def me_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Return current user info (M2 auth 中间件)."""
    from app.auth.deps import get_current_user
    from app.auth.exceptions import session_not_found, token_expired

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth[7:]
    try:
        user = await get_current_user(db, token)
    except Exception as e:
        msg = str(e).lower()
        if "expired" in msg:
            raise token_expired()
        raise session_not_found()

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
    )
