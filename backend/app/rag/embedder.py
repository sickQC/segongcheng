"""向量嵌入后端（可插拔）。

三种后端，接口一致，便于做消融实验：

1. ``hashing``  —— 纯本地哈希 TF-IDF 向量。零下载、确定性、离线可跑，默认。
2. ``st``       —— sentence-transformers 本地模型（如 BAAI/bge-small-zh-v1.5）。
3. ``openai``   —— 任何 OpenAI 兼容的 /embeddings 接口。

为什么默认用哈希 TF-IDF 而不是神经嵌入？
--------------------------------------
课程验收要求"系统能在新环境 30 分钟内跑起来"，而下载 torch + 中文嵌入模型
通常需要数 GB 流量与若干分钟。哈希 TF-IDF 让整套 RAG 在无网络、无 API Key
的情况下也能端到端跑通并被评测；需要更好的语义召回时，改一个环境变量即可
切换到 bge 或 API 嵌入，评测脚本会给出两者的差异。
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, Sequence

import numpy as np

from .config import EmbedderConfig
from .textutil import char_ngrams, normalize, tokenize


class Embedder(Protocol):
    name: str
    dim: int

    def fit(self, corpus: Sequence[str]) -> None: ...
    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


def _hash_index(feature: str, dim: int) -> int:
    h = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") % dim


class HashingTfidfEmbedder:
    """哈希 TF-IDF 向量：词级 token + 中文 2-gram，双哈希到固定维度。"""

    name = "hashing-tfidf"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.idf: np.ndarray | None = None
        self.n_docs = 0

    @staticmethod
    def _features(text: str) -> list[str]:
        feats = tokenize(text)
        feats.extend(f"g:{g}" for g in char_ngrams(text, 2))
        return feats

    def _counts(self, text: str) -> dict[int, float]:
        counts: dict[int, float] = {}
        for f in self._features(text):
            b = _hash_index(f, self.dim)
            counts[b] = counts.get(b, 0.0) + 1.0
        return counts

    def fit(self, corpus: Sequence[str]) -> None:
        df = np.zeros(self.dim, dtype=np.float64)
        for text in corpus:
            for b in self._counts(text):
                df[b] += 1.0
        self.n_docs = len(corpus)
        self.idf = np.log((1.0 + self.n_docs) / (1.0 + df)) + 1.0

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if self.idf is None:
            raise RuntimeError("HashingTfidfEmbedder 未 fit")
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            counts = self._counts(text)
            if not counts:
                continue
            for b, tf in counts.items():
                out[i, b] = (1.0 + math.log(tf)) * self.idf[b]
            norm = float(np.linalg.norm(out[i]))
            if norm > 0:
                out[i] /= norm
        return out


class SentenceTransformerEmbedder:
    """本地神经嵌入（可选，需要 sentence-transformers）。"""

    name = "sentence-transformers"

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        from sentence_transformers import SentenceTransformer  # 延迟导入

        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.dim = int(self.model.get_sentence_embedding_dimension())

    def fit(self, corpus: Sequence[str]) -> None:  # 神经嵌入无需拟合
        return None

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vecs = self.model.encode(
            [normalize(t) for t in texts], normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vecs, dtype=np.float32)


class OpenAIEmbedder:
    """OpenAI 兼容的 embedding 接口。"""

    name = "openai-embedding"

    def __init__(self, cfg: EmbedderConfig, api_key: str, base_url: str, model: str) -> None:
        import httpx

        self.dim = cfg.dim
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=60.0)

    def fit(self, corpus: Sequence[str]) -> None:
        return None

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        out: list[list[float]] = []
        batch = 32
        for i in range(0, len(texts), batch):
            resp = self._client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": [normalize(t) for t in texts[i : i + batch]]},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        arr = np.asarray(out, dtype=np.float32)
        self.dim = arr.shape[1]
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


def get_embedder(cfg: EmbedderConfig, *, api_key: str = "", base_url: str = "", model: str = "") -> Embedder:
    backend = (cfg.backend or "hashing").lower()
    if backend == "st":
        try:
            return SentenceTransformerEmbedder(cfg.st_model)
        except Exception as exc:  # 缺依赖 / 无网络时自动退回本地后端，保证系统可用
            print(f"[embedder] sentence-transformers 不可用（{exc}），回退到 hashing-tfidf")
            return HashingTfidfEmbedder(cfg.dim)
    if backend == "openai":
        if not api_key:
            print("[embedder] 缺少 OPENAI_API_KEY，回退到 hashing-tfidf")
            return HashingTfidfEmbedder(cfg.dim)
        return OpenAIEmbedder(cfg, api_key=api_key, base_url=base_url, model=model)
    return HashingTfidfEmbedder(cfg.dim)
