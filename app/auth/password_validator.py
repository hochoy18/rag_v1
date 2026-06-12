"""密码强度校验 (M2 Task 3 — P1-7 独立任务, 前置 Task 4 register).

来源: 2026-06-10-rag-m2-auth.md Task 3 GREEN 段
- 长度 12-128
- 大小写混合
- 含数字
- 黑名单 (常见密码 top 100)

V1 spec §3.2: 显式要求密码强度, 否则用户注册 "x" 也能通过。

r3 实施修订: _TEST_PW 占位符避开 hermes-agent 对 *** 字面量的 sanitize.
"""
from __future__ import annotations

import re
from pathlib import Path

MIN_LENGTH = 12
MAX_LENGTH = 128
_TEST_PW = "_TEST_placeholder_pw"
_COMMON_FILE = Path(__file__).parent / "common_passwords.txt"


def _load_common_passwords() -> frozenset[str]:
    """Load common-password blacklist from disk (P1-7 100+ 条内置)."""
    if not _COMMON_FILE.exists():
        return frozenset()
    return frozenset(
        line.strip() for line in _COMMON_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


_COMMON_PASSWORDS: frozenset[str] = _load_common_passwords()

# 100+ 条常见密码 (P1-7 HIBP top 取子集, 简化版内置)
_BUILTIN_COMMON: frozenset[str] = frozenset({
    "password", "password1", "password123", "12345678", "123456789",
    "1234567890", "qwerty", "qwerty123", "abc123", "111111", "123123",
    "admin", "admin123", "letmein", "welcome", "welcome1", "monkey",
    "dragon", "master", "login", "princess", "football", "shadow",
    "sunshine", "trustno1", "iloveyou", "batman", "starwars", "whatever",
    "passw0rd", "passwd", "pass1234", "pass12345", "p@ssw0rd",
    "test1234", "test12345", "testing123", "qweqwe", "qweqwe123",
    "zaq12wsx", "1q2w3e4r", "1qaz2wsx", "qwertyuiop", "asdfghjkl",
    "changeme", "default", "secret", "secret123", "mypassword",
    "newpassword", "temp1234", "root", "toor", "administrator",
    "user", "user123", "guest", "guest123", "demo", "demo123",
    "qwerty1", "abcd1234", "1q2w3e", "zaq1xsw2", "qazwsx",
    "passpass", "password!", "password@", "password#",
    "computer", "internet", "samsung", "apple", "google",
    "microsoft", "facebook", "twitter", "instagram", "snapchat",
    "letmein123", "welcome123", "abc12345", "12345abc",
    "qwerty12345", "1q2w3e4r5t", "asdfasdf", "asdf1234",
    "zxcvbnm", "zxcvbn", "00000000", "000000000", "0987654321",
    "987654321", "1qaz2wsx3edc", "!@#$%^&*", "qwerty123!",
    "helloworld", "hellohello", "foofoofoo", "barbarbar",
    "ncc1701", "starlord", "tardis", "hogwarts",
})

# 合并 (磁盘文件优先, 内置兜底)
_EFFECTIVE_COMMON = _COMMON_PASSWORDS | _BUILTIN_COMMON


def validate_password(pw: str) -> None:
    """Raise ValueError on weak password; return None on pass.

    校验规则 (顺序: 长度 → 黑名单 → 大小写 → 数字):
    1. 长度 12-128
    2. 非常见密码 (大小写不敏感)
    3. 含 a-z + A-Z (混合)
    4. 含 0-9
    """
    if not isinstance(pw, str):
        raise ValueError("Password must be a string")
    if not (MIN_LENGTH <= len(pw) <= MAX_LENGTH):
        raise ValueError(f"Password length must be {MIN_LENGTH}-{MAX_LENGTH}")
    if pw.lower() in _EFFECTIVE_COMMON:
        raise ValueError("Password too common")
    if not re.search(r"[a-z]", pw) or not re.search(r"[A-Z]", pw):
        raise ValueError("Password must contain mixed case")
    if not re.search(r"\d", pw):
        raise ValueError("Password must contain digit")


__all__ = ["validate_password", "MIN_LENGTH", "MAX_LENGTH"]