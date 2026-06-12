# RAG V1 Makefile (M0 P1-8 新增 + r1 修订)
# 主体命令：up / down / logs / health / test / clean

.PHONY: up down logs health test clean help

help:
	@echo "RAG V1 Makefile"
	@echo "  make up        - 启动 5 service (PG / OS / TEI / Langfuse / MinIO)"
	@echo "  make down      - 停止所有 service"
	@echo "  make logs      - 查看所有 service 日志 (tail -f)"
	@echo "  make health    - 5 service 健康检查"
	@echo "  make test      - 跑 pytest tests/unit"
	@echo "  make clean     - 清理 volumes + 容器 (危险：会丢数据)"

up:
	cd infra && docker compose up -d
	@echo "5 service 启动完成；等 60s 让 TEI 冷启 bge-m3"

down:
	cd infra && docker compose down

logs:
	cd infra && docker compose logs -f

health:
	./infra/check_health.sh

test:
	python -m pytest tests/unit/ -v

clean:
	cd infra && docker compose down -v
	@echo "volumes 已清，下次 up 会重新建表"
