"""M2 Auth 业务异常 (HTTPException 工厂集中).

来源: 2026-06-10-rag-m2-auth.md
- V1 决策 #7: 越权 session_id → 404, 不暴露存在性
- 弱密码 → 422 (P1-7)
- 账号锁 → 429 (P1-13)
- token 过期 → 401
- 重复 username → 409
- 内部 token 生成失败 → 500

集中管理: service / deps / api 层共用, 避免散落 HTTPException 拼装不一致.
"""
from fastapi import HTTPException


def weak_password(detail: str) -> HTTPException:
    """422 Unprocessable Entity — 弱密码拒绝 (P1-7)."""
    return HTTPException(status_code=422, detail=detail)


def username_taken() -> HTTPException:
    """409 Conflict — username 唯一约束冲突."""
    return HTTPException(status_code=409, detail="username already exists")


def account_locked() -> HTTPException:
    """429 Too Many Requests — 账号锁中 (P1-13)."""
    return HTTPException(status_code=429, detail="Account locked, try later")


def invalid_credentials() -> HTTPException:
    """404 Not Found — 用户名或密码错误 (不暴露区分, V1 决策 #7)."""
    return HTTPException(status_code=404, detail="invalid credentials")


def wrong_password() -> HTTPException:
    """401 Unauthorized — 密码错误 (login 流程细分)."""
    return HTTPException(status_code=401, detail="invalid credentials")


def session_not_found() -> HTTPException:
    """404 Not Found — session 不存在或已吊销 (P0-4 不区分)."""
    return HTTPException(status_code=404, detail="session not found")


def token_expired() -> HTTPException:
    """401 Unauthorized — token 过期 (sliding 或 hard cap)."""
    return HTTPException(status_code=401, detail="token expired")


def user_not_found() -> HTTPException:
    """404 Not Found — User 不存在 (虽然 session 有效)."""
    return HTTPException(status_code=404, detail="user not found")


def token_collision() -> HTTPException:
    """500 Internal Server Error — token UNIQUE 冲突 3 次后兜底."""
    return HTTPException(status_code=500, detail="token generation failed")


__all__ = [
    "weak_password",
    "username_taken",
    "account_locked",
    "invalid_credentials",
    "wrong_password",
    "session_not_found",
    "token_expired",
    "user_not_found",
    "token_collision",
]