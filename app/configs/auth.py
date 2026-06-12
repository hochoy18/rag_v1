"""Auth settings (M2 Task 1 + P1-2/P1-13/P2-10 追加).

来源: 2026-06-10-rag-m2-auth.md Task 1 GREEN 段
- token_ttl_sliding (default 7d) — V1 spec 决策 #5 滑动过期
- token_ttl_hard (default 30d) — 硬上限
- argon2_* — OWASP 2024 推荐值 (P1-2)
- session_extend_threshold (P2-10) — 触发 BackgroundTasks 续期的阈值
- failed_login_lockout_count / duration (P1-13) — 账号锁

子模型显式 env_prefix="AUTH_" + "ARGON2_" 兼容 (避免 env_nested_delimiter 解析错位)。
"""
from datetime import timedelta

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from app.configs.base import BaseAppSettings


class AuthSettings(BaseAppSettings):
    """M2 鉴权配置块 (AUTH_* env 前缀).

    r2 实操修订: 子模型显式 env_prefix="AUTH_" 让 env 形如
    AUTH_TOKEN_TTL_SLIDING=7d 直接映射到本字段。
    """

    model_config = SettingsConfigDict(env_prefix="AUTH_")

    # ---- Token 过期策略 (V1 spec 决策 #5) ----
    token_ttl_sliding: timedelta = Field(
        default=timedelta(days=7),
        description="token 滑动过期时间 (默认 7d)",
    )
    token_ttl_hard: timedelta = Field(
        default=timedelta(days=30),
        description="token 硬过期时间 (默认 30d)",
    )
    # P2-10: extend_session 触发阈值可配
    session_extend_threshold: timedelta = Field(
        default=timedelta(days=1),
        description="sliding 剩余 < 阈值时 BackgroundTasks 续期",
    )

    # ---- 账号锁 (P1-13) ----
    failed_login_lockout_count: int = Field(
        default=5,
        description="连续 N 次密码错误锁定账号",
    )
    failed_login_lockout_duration: timedelta = Field(
        default=timedelta(minutes=15),
        description="账号锁持续时间",
    )

    # ---- argon2id 参数 (P1-2 OWASP 2024) ----
    # 注意: argon2 参数走独立 env 前缀 ARGON2_*
    argon2_time_cost: int = Field(default=3, alias="ARGON2_TIME_COST")
    argon2_memory_cost: int = Field(default=65536, alias="ARGON2_MEMORY_COST")
    argon2_parallelism: int = Field(default=1, alias="ARGON2_PARALLELISM")


__all__ = ["AuthSettings"]