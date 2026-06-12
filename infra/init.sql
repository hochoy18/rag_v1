-- RAG V1 init.sql —— Postgres 初始化（M0 P1-2 修复版）
-- dev only —— 生产环境走 secret manager / Vault
-- 文件名 01-init.sql，挂载到 /docker-entrypoint-initdb.d/

-- r1 修复 P1-2：dev-only 占位（不依赖 ${POSTGRES_PASSWORD} 变量插值——initdb 阶段 env 不可用）
-- r1 修复 P1-2：IF NOT EXISTS 包裹（防止重启 compose 失败）
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_app') THEN
    CREATE ROLE rag_app WITH LOGIN PASSWORD 'rag_app_password';
  END IF;
END
$$;

-- r1 修复 P1-2：CREATE DATABASE IF NOT EXISTS（PostgreSQL 9.5+ 不支持 IF NOT EXISTS for CREATE DATABASE，
-- 改用 pg_database 系统表检查）
SELECT 'CREATE DATABASE rag OWNER rag_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'rag')\gexec

-- 授权
GRANT ALL PRIVILEGES ON DATABASE rag TO rag_app;
ALTER USER rag_app CREATEDB;  -- M11 eval test 需要建临时 DB
