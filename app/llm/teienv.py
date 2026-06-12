"""TEI (Text Embeddings Inference) 客户端 (M3 Task 2).

r3 实施层: 自实现 HTTP 客户端 (避免 langchain_community TEI 类的版本兼容问题)
- TEI API: POST /embed { inputs: ["text1", "text2"] } -> [[0.1, 0.2, ...]]
- batch_size 默认 32 (M3 plan)
- dim 硬约束 1024 (bge-m3)
- 容器内端口 80 (M0 compose host port 18080)
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterable, List


class TEIEmbeddings:
    """TEI HTTP embedding client for bge-m3 (dim=1024)."""

    def __init__(
        self,
        base_url: str,
        batch_size: int = 32,
        dim: int = 1024,
        timeout_seconds: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.dim = dim
        self.timeout_seconds = timeout_seconds

    def _post(self, texts: List[str]) -> List[List[float]]:
        """POST /embed with batch."""
        url = f"{self.base_url}/embed"
        payload = json.dumps({"inputs": texts}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"TEI request failed: {e}") from e
        return data

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        """Embed list of documents, batched."""
        all_embeddings: List[List[float]] = []
        batch: List[str] = []
        for t in texts:
            batch.append(t)
            if len(batch) >= self.batch_size:
                all_embeddings.extend(self._post(batch))
                batch = []
        if batch:
            all_embeddings.extend(self._post(batch))
        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """Embed single query text (TEI 不区分 query/passage, bge-m3 走 prefix 'Represent this sentence')."""
        embeddings = self._post([text])
        return embeddings[0] if embeddings else []

    def health_check(self) -> bool:
        """Check TEI service health (GET /health)."""
        url = f"{self.base_url}/health"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status == 200
        except Exception:
            return False
