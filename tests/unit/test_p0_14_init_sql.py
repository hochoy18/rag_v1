"""P0-14 回归测试: init.sql 必须用 IF NOT EXISTS 包裹 CREATE ROLE / CREATE DATABASE.

防止 P0-14 (init.sql 重启 compose 时 'database already exists' 失败) 回归.
"""
import re
from pathlib import Path


class TestInitSqlIdempotent:
    """init.sql 必须幂等 (重启 compose 不会失败)."""

    INIT_SQL = Path("/home/hochoy/projects/apps/rag_v1/infra/init.sql").read_text()

    def test_create_role_has_if_not_exists_wrapper(self):
        """CREATE ROLE 必须 IF NOT EXISTS 包裹 (Postgres 不支持原生语法, 需 DO 块)."""
        m = re.search(r"CREATE ROLE rag_app", self.INIT_SQL)
        assert m, "CREATE ROLE rag_app not found"
        before = self.INIT_SQL[:m.start()]
        assert "IF NOT EXISTS" in before[-200:], "CREATE ROLE must be wrapped in IF NOT EXISTS DO block"

    def test_create_database_rag_has_if_not_exists(self):
        """CREATE DATABASE rag 必须 IF NOT EXISTS 包裹."""
        assert "CREATE DATABASE rag" in self.INIT_SQL
        m = re.search(r"CREATE DATABASE rag", self.INIT_SQL)
        before = self.INIT_SQL[:m.start()]
        assert "IF NOT EXISTS" in before[-200:], "CREATE DATABASE rag must be in IF NOT EXISTS DO block"

    def test_create_database_langfuse_has_if_not_exists(self):
        """CREATE DATABASE langfuse (P0-16 独立) 必须 IF NOT EXISTS 包裹."""
        m = re.search(r"CREATE DATABASE langfuse", self.INIT_SQL)
        assert m, "CREATE DATABASE langfuse not found"
        before = self.INIT_SQL[:m.start()]
        assert "IF NOT EXISTS" in before[-200:], "CREATE DATABASE langfuse must be in IF NOT EXISTS DO block"

    def test_do_blocks_balanced(self):
        """DO $$ 块必须平衡 (3 开 3 闭)."""
        do_open = self.INIT_SQL.count("DO $$")
        do_close = self.INIT_SQL.count("END $$;")
        assert do_open == do_close, f"DO blocks unbalanced: {do_open} open vs {do_close} close"

    def test_password_not_env_variable(self):
        """Password 禁止 ${...} 变量插值 (initdb 阶段 env 不可用, r1 P1-2 决议)."""
        # 找 PASSWORD '${...}' 模式
        m = re.search(r"PASSWORD\s+['\"]?\$\{", self.INIT_SQL)
        assert m is None, "PASSWORD must not use env variable interpolation in init.sql"
