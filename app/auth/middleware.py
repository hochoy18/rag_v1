"""M2 中间件层 (rate limit state + IP 提取).

来源: 2026-06-10-rag-m2-auth.md
- V1 spec 决策: register 5 次/分钟/IP, login 10 次/分钟/IP (slowapi)
- P0-3 限速测试: reset_limiter + fixed_ip fixtures
- 限速实际挂在 endpoint 上 (@limiter.limit), middleware 只承载共享 limiter
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address


def get_client_ip(request) -> str:
    """提取 client IP (从 Request, 用于 slowapi key_func)."""
    return get_remote_address(request)


__all__ = ["get_client_ip", "Limiter"]