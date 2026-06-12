"""M2 auth 实施层 TDD (Task 6 endpoint + Task 1-5 service/repository).

来源: 2026-06-10-rag-m2-auth.md 修完版

r3 实施层修订: 避免 import sqlalchemy/arg2 全 db 实例, 用 unit-level 测关键函数
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# PYTHONPATH 注入 (CI/local 都用同一套)
SITE_PACKAGES = "/home/hochoy/.hermes/profiles/coder/home/.local/lib/python3.11/site-packages"
if SITE_PACKAGES not in sys.path:
    sys.path.insert(0, SITE_PACKAGES)


class TestAuthExceptions:
    """app.auth.exceptions: HTTPException 工厂函数集合."""

    def test_weak_password_returns_422(self):
        from app.auth.exceptions import weak_password
        exc = weak_password("too short")
        assert exc.status_code == 422
        assert "too short" in str(exc.detail)

    def test_username_taken_returns_409(self):
        from app.auth.exceptions import username_taken
        exc = username_taken()
        assert exc.status_code == 409

    def test_account_locked_returns_429(self):
        from app.auth.exceptions import account_locked
        exc = account_locked()
        assert exc.status_code == 429

    def test_invalid_credentials_returns_404(self):
        """V1 决策 #7: 不暴露 username 是否存在 -> 404."""
        from app.auth.exceptions import invalid_credentials
        exc = invalid_credentials()
        assert exc.status_code == 404

    def test_token_expired_returns_401(self):
        from app.auth.exceptions import token_expired
        exc = token_expired()
        assert exc.status_code == 401


class TestAuthTokens:
    """app.auth.tokens: token 生成 + hash + 过期校验."""

    def test_generate_token_returns_string(self):
        from app.auth.tokens import generate_token
        token = generate_token()
        assert isinstance(token, str)
        assert len(token) >= 32  # secrets.token_urlsafe(32) -> 43 chars

    def test_hash_token_returns_64_char_hex(self):
        from app.auth.tokens import hash_token
        h = hash_token("test_token")
        assert len(h) == 64
        assert re.match(r"^[0-9a-f]{64}$", h)

    def test_hash_token_same_input_same_output(self):
        from app.auth.tokens import hash_token
        assert hash_token("test") == hash_token("test")

    def test_hash_token_different_input_different_output(self):
        from app.auth.tokens import hash_token
        assert hash_token("a") != hash_token("b")

    def test_validate_token_expiry_sliding(self):
        from datetime import datetime, timedelta, timezone
        from app.auth.tokens import validate_token_expiry
        # sliding 过期 -> False
        now = datetime.now(timezone.utc)
        s = validate_token_expiry(
            now - timedelta(days=8),  # 已过 sliding
            now + timedelta(days=20),  # hard 未过
        )
        assert s is False

    def test_validate_token_expiry_hard(self):
        from datetime import datetime, timedelta, timezone
        from app.auth.tokens import validate_token_expiry
        now = datetime.now(timezone.utc)
        s = validate_token_expiry(
            now + timedelta(days=1),  # sliding 未过
            now - timedelta(days=1),  # hard 已过
        )
        assert s is False

    def test_validate_token_expiry_valid(self):
        from datetime import datetime, timedelta, timezone
        from app.auth.tokens import validate_token_expiry
        now = datetime.now(timezone.utc)
        s = validate_token_expiry(
            now + timedelta(days=6),  # sliding 未过 (7d 内)
            now + timedelta(days=29),  # hard 未过 (30d 内)
        )
        assert s is True


class TestPasswordValidator:
    """app.auth.password_validator: 弱密码拒绝 (P1-7 422)."""

    def test_validate_password_accepts_strong(self):
        from app.auth.password_validator import validate_password
        # 不抛错
        validate_password("A_str0ng_P@ssw0rd_2026")

    def test_validate_password_rejects_too_short(self):
        from app.auth.password_validator import validate_password
        with pytest.raises(ValueError):
            validate_password("short")

    def test_validate_password_rejects_common(self):
        from app.auth.password_validator import validate_password
        with pytest.raises(ValueError):
            validate_password("password123!")

    def test_validate_password_rejects_no_uppercase(self):
        from app.auth.password_validator import validate_password
        with pytest.raises(ValueError):
            validate_password("all_lowercase_2026!")

    def test_validate_password_rejects_no_digit(self):
        from app.auth.password_validator import validate_password
        with pytest.raises(ValueError):
            validate_password("No_Digits_Here!")


class TestAuthAPI:
    """app.api.auth: 4 endpoint 路由存在 + 状态码."""

    def test_router_has_4_endpoints(self):
        from app.api.auth import router
        assert len(router.routes) == 4, f"expected 4 endpoints, got {len(router.routes)}"

    def test_router_prefix_is_api_auth(self):
        from app.api.auth import router
        assert router.prefix == "/api/auth"

    def test_endpoints_methods(self):
        """register=POST, login=POST, logout=POST, me=GET."""
        from app.api.auth import router
        # 注: route.path 已含 prefix /api/auth
        methods_by_path = {}
        for route in router.routes:
            path = route.path
            methods = list(route.methods) if route.methods else []
            methods_by_path[path] = methods
        assert "POST" in methods_by_path.get("/api/auth/register", [])
        assert "POST" in methods_by_path.get("/api/auth/login", [])
        assert "POST" in methods_by_path.get("/api/auth/logout", [])
        assert "GET" in methods_by_path.get("/api/auth/me", [])

    def test_logout_returns_204(self):
        """NP-2 r2 修复: logout 501 -> 204 完整实现."""
        from app.api.auth import router
        logout_route = next(r for r in router.routes if r.path == "/api/auth/logout")
        assert logout_route.status_code == 204, \
            f"logout must be 204 (r2 NP-2 fix), got {logout_route.status_code}"


class TestPasswordHasher:
    """app.auth.service._build_hasher: argon2id 哈希 + 验签."""

    def test_hash_password_format(self):
        from app.auth.service import _build_hasher
        ph = _build_hasher()
        h = ph.hash("A_str0ng_P@ssw0rd_2026")
        # argon2id encoded format: $argon2id$v=19$m=...,t=...,p=...$salt$hash
        assert h.startswith("$argon2id$"), f"hash must be argon2id, got: {h[:30]}"

    def test_verify_password_correct(self):
        from app.auth.service import _build_hasher
        ph = _build_hasher()
        h = ph.hash("A_str0ng_P@ssw0rd_2026")
        assert ph.verify(h, "A_str0ng_P@ssw0rd_2026") is True

    def test_verify_password_wrong(self):
        from app.auth.service import _build_hasher
        ph = _build_hasher()
        h = ph.hash("A_str0ng_P@ssw0rd_2026")
        # argon2.verify 抛错当密码错
        with pytest.raises(Exception):
            ph.verify(h, "wrong_password")


class TestMiddleware:
    """app.auth.middleware.get_client_ip (M2 ↔ M12 联动)."""

    def test_get_client_ip_returns_str(self):
        from app.auth.middleware import get_client_ip
        # mock Request
        request = MagicMock()
        request.client.host = "192.168.1.1"
        result = get_client_ip(request)
        assert result == "192.168.1.1"

    def test_get_client_ip_no_client(self):
        """无 client 时 slowapi.get_remote_address fallback 行为."""
        from app.auth.middleware import get_client_ip
        request = MagicMock()
        # slowapi.get_remote_address 取 request.client.host
        # 模拟: 无 client 时直接 return 一个 default IP
        request.client = None
        # 实际不会抛错 (slowapi 内部处理), 只 verify 函数可调用
        result = get_client_ip(request)
        assert result is None or isinstance(result, str)
