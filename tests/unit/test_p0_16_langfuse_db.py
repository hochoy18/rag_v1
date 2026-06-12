"""P0-16 回归测试: langfuse 必须独立 DB (不共用 rag)."""
import pytest


class TestLangfuseIndependentDB:
    """防止 langfuse 共用 rag DB 的 P0 回归."""

    def test_compose_langfuse_uses_langfuse_db(self):
        """compose.yml langfuse.DATABASE_URL 必须 dbname=langfuse."""
        import re
        from pathlib import Path
        dc = Path("/home/hochoy/projects/apps/rag_v1/infra/docker-compose.yml").read_text()
        # 找 langfuse service block
        m = re.search(r"^  langfuse:(.*?)(?=^  \w+:|^networks:|^volumes:|\Z)", dc, re.S | re.M)
        assert m, "langfuse service not found in compose.yml"
        block = m.group(1)
        assert "postgresql://" in block, "langfuse.DATABASE_URL must be postgresql://"
        # dbname must be langfuse, NOT rag
        assert "/langfuse" in block, f"langfuse.DATABASE_URL must end with /langfuse, got: {block[:200]}"
        assert "/rag\"" not in block, f"langfuse must NOT use /rag DB"

    def test_init_sql_creates_langfuse_db(self):
        """init.sql 必须 CREATE DATABASE langfuse 独立 DB."""
        from pathlib import Path
        sql = Path("/home/hochoy/projects/apps/rag_v1/infra/init.sql").read_text()
        assert "CREATE DATABASE langfuse" in sql, "init.sql missing CREATE DATABASE langfuse"
        assert "GRANT ALL PRIVILEGES ON DATABASE langfuse" in sql, "init.sql missing GRANT for langfuse"

    def test_env_file_langfuse_uses_langfuse_db(self):
        """.env.example LANGFUSE_DATABASE_URL 必须 dbname=langfuse."""
        from pathlib import Path
        env = Path("/home/hochoy/projects/apps/rag_v1/.env.example").read_text()
        assert "LANGFUSE_DATABASE_URL=postgresql://rag_app:" in env
        # dbname
        import re
        m = re.search(r"LANGFUSE_DATABASE_URL=postgresql://rag_app:.*?@postgres:5432/(\w+)", env)
        assert m, "LANGFUSE_DATABASE_URL malformed"
        assert m.group(1) == "langfuse", f"LANGFUSE_DATABASE_URL dbname must be langfuse, got {m.group(1)}"
