-- RAG V1 init.sql -- Postgres initialization
-- Source: M0 plan 2026-06-10-rag-m0-infra.md Task 2 (P1-2 + r3 implementation P0 fix)
-- dev only -- production uses secret manager / Vault
-- Filename 01-init.sql, mounted to /docker-entrypoint-initdb.d/

-- r1 fix P1-2: dev-only plaintext password (no env variable interpolation --
--   env is not available at initdb stage; P1-2 r1 explicitly chose this).
-- r1 fix P1-2: role IF NOT EXISTS wrapper (prevent restart failure)
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_app') THEN
    CREATE ROLE rag_app WITH LOGIN PASSWORD 'rag_app_password';
  END IF;
END $$;

-- r3 implementation P0: CREATE DATABASE IF NOT EXISTS wrapper
-- PostgreSQL does not support CREATE DATABASE IF NOT EXISTS syntax.
-- Use DO block with EXECUTE dynamic SQL.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'rag') THEN
    EXECUTE 'CREATE DATABASE rag OWNER rag_app';
  END IF;
END $$;

-- r3 implementation P0: independent langfuse database (avoid sharing with rag)
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse') THEN
    EXECUTE 'CREATE DATABASE langfuse OWNER rag_app';
  END IF;
END $$;

-- Authorization
GRANT ALL PRIVILEGES ON DATABASE rag TO rag_app;
GRANT ALL PRIVILEGES ON DATABASE langfuse TO rag_app;

ALTER USER rag_app CREATEDB;  -- M11 eval test needs to create temp DB
