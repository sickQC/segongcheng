"""索引：稠密向量索引 + BM25 稀疏索引 + 知识点图谱。

索引产物落到 ``data/index/``，可复现、可版本化：
    index.pkl   —— chunks / parents / kps / bm25 / dense matrix / 配置快照
"""

from __future__ import annotations

import json
import math
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .chunker import Chunk, ParentBlock, load_kb
from .config import RagConfig
from .embedder import Embedder, get_embedder
from .textutil import expand_query, load_synonyms, tokenize

INDEX_FORMAT = 1


@dataclass
class KnowledgePoint:
    id: str
    name: str
    definition: str
    difficulty: int
    bloom: str
    doc_id: str
    doc_title: str
    prereq_names: list[str]
    prereq_ids: list[str]


class RagIndex:
    def __init__(self, cfg: RagConfig) -> None:
        self.cfg = cfg
        self.chunks: list[Chunk] = []
        self.parents: dict[str, ParentBlock] = {}
        self.kps: list[KnowledgePoint] = []
        self.embedder: Embedder | None = None
        self.dense: np.ndarray | None = None
        self.bm25: BM25Okapi | None = None
        self.tokenized: list[list[str]] = []
        self.synonyms: dict[str, list[str]] = {}
        self.built_at: float = 0.0
        self.stats: dict = {}
        self.linked_orphans: int = 0
        self.token_df: dict[str, int] = {}

    # ------------------------------------------------------------------ build
    def build(self) -> "RagIndex":
        t0 = time.perf_counter()
        cfg = self.cfg
        chunks, parents, raw_kps = load_kb(cfg.kb_dir, cfg.chunk)

        self.synonyms = load_synonyms(cfg.synonyms_path)
        self.chunks = chunks
        self.parents = {p.parent_id: p for p in parents}
        self.kps = self._build_kps(raw_kps)

        # 稀疏索引：BM25 over jieba 分词
        self.tokenized = [tokenize(c.text) for c in chunks]
        self.bm25 = BM25Okapi(self.tokenized) if self.tokenized else None
        self.token_df = self._compute_token_df()

        # 稠密索引
        self.embedder = get_embedder(
            cfg.embedder,
            api_key=cfg.llm.api_key,
            base_url=cfg.llm.base_url,
            model=cfg.llm.embedding_model,
        )
        corpus_texts = [c.text for c in chunks]
        self.embedder.fit(corpus_texts)
        self.dense = self.embedder.encode(corpus_texts) if corpus_texts else np.zeros((0, 1), np.float32)

        # 知识点 → 教学资源的兜底挂接（AC-M4-5：每个知识点至少关联 1 个资源）
        self.linked_orphans = self._link_orphan_kps()

        self.built_at = time.time()
        self.stats = {
            "docs": len({c.doc_id for c in chunks}),
            "chunks": len(chunks),
            "parents": len(parents),
            "knowledge_points": len(self.kps),
            "relations": sum(len(k.prereq_ids) for k in self.kps),
            "linked_orphan_kps": self.linked_orphans,
            "embedder": self.embedder.name,
            "dim": int(self.dense.shape[1]) if self.dense is not None and self.dense.size else 0,
            "avg_chunk_chars": round(sum(len(c.text) for c in chunks) / max(1, len(chunks)), 1),
            "build_seconds": round(time.perf_counter() - t0, 3),
        }
        return self

    def _link_orphan_kps(self, per_kp: int = 2) -> int:
        """把没挂到任何 chunk 上的知识点，按向量相似度兜底挂到最相关的 chunk。

        只用名称字面匹配会漏掉大量知识点（小节标题写法与知识点命名往往不一致），
        因此这里用 KP 名称+定义的向量表示做一次语义兜底。
        """
        if self.embedder is None or self.dense is None or self.dense.size == 0 or not self.kps:
            return 0
        linked = 0
        for kp in self.kps:
            if any(kp.id in c.kp_ids for c in self.chunks):
                continue
            q = self.embedder.encode([f"{kp.name}。{kp.definition}"])[0]
            sims = self.dense @ q
            for i in np.argsort(-sims)[:per_kp]:
                c = self.chunks[int(i)]
                if kp.id not in c.kp_ids:
                    c.kp_ids.append(kp.id)
            linked += 1
        return linked

    def _build_kps(self, raw_kps: list[dict]) -> list[KnowledgePoint]:
        by_name: dict[str, str] = {}
        kps: list[KnowledgePoint] = []
        for r in raw_kps:
            kps.append(
                KnowledgePoint(
                    id=r["id"],
                    name=r.get("name", ""),
                    definition=r.get("definition", ""),
                    difficulty=int(r.get("difficulty", 3)),
                    bloom=r.get("bloom", "理解"),
                    doc_id=r.get("doc_id", ""),
                    doc_title=r.get("doc_title", ""),
                    prereq_names=list(r.get("prereq_names", [])),
                    prereq_ids=[],
                )
            )
            by_name[r.get("name", "")] = r["id"]
        # 解析先修关系：先精确匹配，再子串匹配
        for kp in kps:
            for name in kp.prereq_names:
                target = by_name.get(name)
                if target is None:
                    for other_name, other_id in by_name.items():
                        if other_id != kp.id and name and (name in other_name or other_name in name):
                            target = other_id
                            break
                if target and target != kp.id and target not in kp.prereq_ids:
                    kp.prereq_ids.append(target)
        return kps

    # -------------------------------------------------------------- persist
    def save(self, index_dir: Path | None = None) -> Path:
        index_dir = Path(index_dir or self.cfg.index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)
        path = index_dir / "index.pkl"
        payload = {
            "format": INDEX_FORMAT,
            "chunks": self.chunks,
            "parents": self.parents,
            "kps": self.kps,
            "tokenized": self.tokenized,
            "dense": self.dense,
            "embedder": self.embedder,
            "built_at": self.built_at,
            "stats": self.stats,
        }
        with path.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        (index_dir / "index_stats.json").write_text(
            json.dumps(self.stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 导出知识点图谱（供 M4 知识图谱 / M9 路径推荐直接消费）
        (index_dir / "knowledge_graph.json").write_text(
            json.dumps(
                {
                    "nodes": [
                        {
                            "id": k.id,
                            "name": k.name,
                            "definition": k.definition,
                            "difficulty": k.difficulty,
                            "bloom": k.bloom,
                            "doc_id": k.doc_id,
                            "doc_title": k.doc_title,
                            "resource_chunk_ids": [c.chunk_id for c in self.chunks if k.id in c.kp_ids],
                        }
                        for k in self.kps
                    ],
                    "edges": [
                        {"source": k.id, "target": pid, "type": "prerequisite"}
                        for k in self.kps
                        for pid in k.prereq_ids
                    ],
                    "meta": self.stats,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, cfg: RagConfig, index_dir: Path | None = None) -> "RagIndex":
        index_dir = Path(index_dir or cfg.index_dir)
        path = index_dir / "index.pkl"
        if not path.exists():
            raise FileNotFoundError(
                f"索引不存在：{path}\n请先运行：python scripts/build_index.py"
            )
        with path.open("rb") as f:
            payload = pickle.load(f)
        if payload.get("format") != INDEX_FORMAT:
            raise RuntimeError("索引格式不匹配，请重新构建：python scripts/build_index.py")

        idx = cls(cfg)
        idx.chunks = payload["chunks"]
        idx.parents = payload["parents"]
        idx.kps = payload["kps"]
        idx.tokenized = payload["tokenized"]
        idx.dense = payload["dense"]
        idx.embedder = payload["embedder"]
        idx.built_at = payload.get("built_at", 0.0)
        idx.stats = payload.get("stats", {})
        idx.bm25 = BM25Okapi(idx.tokenized) if idx.tokenized else None
        idx.token_df = idx._compute_token_df()
        idx.synonyms = load_synonyms(cfg.synonyms_path)
        return idx

    def _compute_token_df(self) -> dict[str, int]:
        """token -> 出现该 token 的 chunk 数。用于 IDF 加权的相关性判定。"""
        df: dict[str, int] = {}
        for tokens in self.tokenized:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1
        return df

    def token_idf(self, token: str) -> float:
        """IDF：语料中没出现过的词得到最高权重。

        这正是"超范围拒答"的关键——问"红烧肉怎么做"时，"红烧肉"在语料里
        df=0，IDF 极高却匹配不上任何 chunk，IDF 加权覆盖率会立刻塌下来，
        从而被正确判定为"资料中没有依据"。
        """
        n = max(1, len(self.tokenized))
        return math.log((1.0 + n) / (1.0 + self.token_df.get(token, 0))) + 1.0

    # ---------------------------------------------------------------- search
    def expand(self, query: str) -> list[str]:
        if not self.cfg.retrieval.use_synonym_expansion:
            return []
        return expand_query(query, self.synonyms)

    def _allowed_mask(self, allowed: set[int] | None) -> np.ndarray | None:
        if allowed is None:
            return None
        mask = np.zeros(len(self.chunks), dtype=bool)
        for i in allowed:
            if 0 <= i < len(self.chunks):
                mask[i] = True
        return mask

    def search_sparse(
        self, query: str, k: int, allowed: set[int] | None = None
    ) -> list[tuple[int, float]]:
        if self.bm25 is None:
            return []
        tokens = tokenize(query) + self.expand(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        mask = self._allowed_mask(allowed)
        if mask is not None:
            scores = np.where(mask, scores, -np.inf)
        order = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in order if np.isfinite(scores[i]) and scores[i] > 0]

    def search_dense(
        self, query: str, k: int, allowed: set[int] | None = None
    ) -> list[tuple[int, float]]:
        if self.dense is None or self.embedder is None or self.dense.size == 0:
            return []
        q = self.embedder.encode([query])[0]
        sims = self.dense @ q
        mask = self._allowed_mask(allowed)
        if mask is not None:
            sims = np.where(mask, sims, -np.inf)
        order = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in order if np.isfinite(sims[i])]

    def filter_indices(
        self, *, doc_ids: list[str] | None = None, kp_ids: list[str] | None = None
    ) -> set[int] | None:
        """元数据预过滤：按文档 / 知识点缩小检索范围（对应"在某知识点下提问"）。"""
        if not doc_ids and not kp_ids:
            return None
        out: set[int] = set()
        for i, c in enumerate(self.chunks):
            if doc_ids and c.doc_id not in doc_ids:
                continue
            if kp_ids and not (set(kp_ids) & set(c.kp_ids)):
                continue
            out.add(i)
        return out

    def get_parent_text(self, chunk: Chunk) -> str:
        parent = self.parents.get(chunk.parent_id)
        return parent.text if parent else chunk.text

    def kp_by_id(self, kp_id: str) -> KnowledgePoint | None:
        for kp in self.kps:
            if kp.id == kp_id:
                return kp
        return None

    def doc_titles(self) -> dict[str, str]:
        return {c.doc_id: c.doc_title for c in self.chunks}


def build_index(cfg: RagConfig | None = None) -> RagIndex:
    cfg = cfg or RagConfig.from_env()
    idx = RagIndex(cfg).build()
    idx.save()
    return idx
