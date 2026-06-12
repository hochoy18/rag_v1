# RAG V1

> RAG V1 - 10k-1M chunk production-ready retrieval-augmented generation system
> 实施基线: 13 份 plan (M0-M12) 修复完版
> 文档: `~/.hermes/profiles/coder/docs/superpowers/plans/`

## 快速开始 (M0 里程碑)

### 前置条件

- Docker 24+ / Docker Compose v2
- Linux 内核 sysctl (OpenSearch 需要): `vm.max_map_count=262144`
  ```bash
  sudo sysctl -w vm.max_map_count=262144
  ```

### 启动 5 service 基础设施

```bash
cd ~/projects/apps/rag_v1
make up
# 等 60s 让 TEI 冷启加载 bge-m3 (~2GB 模型)
make health
```

期望输出：
```
SERVICE         STATUS
-------         ------
postgres        healthy
opensearch      healthy
tei             healthy
langfuse        healthy
minio           healthy

✅ ALL SERVICES HEALTHY
```

### 5 Service 角色

| Service | 端口 | 角色 |
|---------|------|------|
| postgres | 5432 | 主数据库 (M1 schema / M2 auth / M7 graph state) |
| opensearch | 9200 | 向量库 (M4 k-NN HNSW dim=1024 cosine) |
| tei | 18080 | bge-m3 embedding 服务 |
| langfuse | 3000 | LLM 观测平台 (M10 trace_id) |
| minio | 9000/9001 | S3 兼容备份 (M12 backup) |

### 实施路线图

| Milestone | 估时 | 状态 |
|-----------|------|------|
| M0 infra (本里程碑) | 3d | ✅ 已实操 |
| M1 schema (4 表 DDL) | 3d | 🚧 文档已就绪 |
| M2 auth (register/login) | 8d | 🚧 文档已就绪 |
| M3 llm-embed (make_llm 工厂) | 2d | 🚧 文档已就绪 |
| M4-M6 ingest (file/url/confluence) | 3+3+4d | 🚧 文档已就绪 |
| M7 graph (langgraph 8 节点) | 5d | 🚧 文档已就绪 |
| M8 API (FastAPI chat) | 5d | 🚧 文档已就绪 |
| M9 UI (Gradio 暗色) | 3d | 🚧 文档已就绪 |
| M10 obs (Langfuse 装饰器) | 3d | 🚧 文档已就绪 |
| M11 eval (RAGAS) | 3d | 🚧 文档已就绪 |
| M12 hardening | 5d | 🚧 文档已就绪 |

### 关键技术决策

- **Embedding**: bge-m3 dim=1024 (TEI 自部署)
- **LLM**: minimax-cn / MiniMax-M3 走 `ChatAnthropic` 工厂 + Langfuse callback
- **Memory**: PostgresCheckpointer (M7)
- **向量索引**: OpenSearch k-NN HNSW cosine
- **UI**: FastAPI + Gradio 暗色中文
- **观测**: Langfuse 在线 + RAGAS 离线
- **鉴权**: 随机 token + SHA-256 + 7d 滑/30d 硬
