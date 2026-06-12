"""Pydantic schemas for M2 auth API (HTTP 适配层).

来源: 2026-06-10-rag-m2-auth.md Task 8 GREEN 段
- RegisterRequest: username + password + 归一化 (P1-8)
- LoginRequest: username + password + 归一化
- UserResponse: 返回用户信息 (无 password_hash)
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")
RESERVED_USERNAMES = frozenset({
    "admin", "root", "system", "api", "null", "undefined",
})


class RegisterRequest(BaseModel):
    """POST /api/auth/register body — P1-8 username 归一 + 校验."""

    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        v_norm = v.strip().lower()
        if not USERNAME_RE.match(v_norm):
            raise ValueError("Username must be 3-32 chars: a-z, 0-9, _")
        if v_norm in RESERVED_USERNAMES:
            raise ValueError("Username is reserved")
        return v_norm


class LoginRequest(BaseModel):
    """POST /api/auth/login body — username 归一."""

    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    """GET /api/auth/me + POST register response."""

    id: str
    username: str
    created_at: str

    @classmethod
    def from_orm_user(cls, user) -> "UserResponse":
        created_at = user.created_at
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        else:
            created_at_str = str(created_at)
        return cls(
            id=str(user.id),
            username=user.username,
            created_at=created_at_str,
        )


__all__ = ["RegisterRequest", "LoginRequest", "UserResponse"]