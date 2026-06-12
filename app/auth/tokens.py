"""Token 工具函数 (M2 Task 2 — generate / hash / validate_token_expiry).

来源: 2026-06-10-rag-m2-auth.md Task 2
- V1 spec 决策 #5: 随机 token + SHA-256 哈希 + DB 查表, 不用 JWT
- P1-1: validate_token_expiry 抽单 now 变量避免 ms 级竞争
- P2-8: 显式 tz 检查, naive datetime 抛 ValueError
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from secrets import token_urlsafe


def generate_token() -> str:
    """生成 32 字节 urlsafe base64 token (43 字符左右).

    secrets.token_urlsafe(32) 走 os.urandom (熵源: /dev/urandom),
    2^256 空间碰撞概率可忽略。
    """
    return token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 哈希 token → 64 字符 hex 字符串.

    存 DB 用于查表, 不存明文 token (设计目标).
    """
    return sha256(token.encode("utf-8")).hexdigest()


def validate_token_expiry(
    expires_at_sliding: datetime,
    expires_at_hard: datetime,
) -> bool:
    """校验 token 是否在两个过期时间窗内 (P1-1 单 now 变量 + P2-8 tz 检查).

    返回 True: token 有效
    返回 False: token 过期 (滑动过期或硬过期)

    P2-8: naive datetime 抛 ValueError, 强制调用方使用 timezone-aware UTC.
    """
    if expires_at_sliding.tzinfo is None or expires_at_hard.tzinfo is None:
        raise ValueError("Datetimes must be timezone-aware (UTC)")
    now = datetime.now(timezone.utc)
    return now < expires_at_sliding and now < expires_at_hard


__all__ = ["generate_token", "hash_token", "validate_token_expiry"]