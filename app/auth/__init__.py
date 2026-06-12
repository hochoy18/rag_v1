"""M2 Auth package (鉴权业务层).

来源: 2026-06-10-rag-m2-auth.md
- 不感知 HTTP 细节 (无 FastAPI request 依赖)
- app/api/auth.py 是 HTTP 适配层
- app/auth/deps.py 是 FastAPI 注入层

不包含: M1 schema 定义 / OAuth / 密码找回 / admin 角色
"""
from app.auth.password_validator import validate_password
from app.auth.service import (
    check_account_lock,
    extend_session,
    login,
    record_failed_login,
    register,
    reset_failed_login,
)
from app.auth.tokens import (
    generate_token,
    hash_token,
    validate_token_expiry,
)

__all__ = [
    "validate_password",
    "login",
    "register",
    "logout",  # noqa: re-exported from service
    "extend_session",
    "check_account_lock",
    "record_failed_login",
    "reset_failed_login",
    "generate_token",
    "hash_token",
    "validate_token_expiry",
]