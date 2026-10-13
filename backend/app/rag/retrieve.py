"""混合检索：稠密向量 + BM25 + RRF 融合 + 启发式重排 + small-to-big 扩展。

为什么是混合检索
----------------
纯向量检索对"边界值分析"这类**术语精确匹配**的问题容易漂移；
纯 BM25 对"我搞不清什么时候该用等价值划分"这类**口语化提问**召回很差。
两路并行后用 RRF 融合，再叠加词汇覆盖度重排，在课程语料上明显更稳。

RRF（Reciprocal Rank Fusion）
----------------------------
    score(d) = Σ_l  w_l / (k + rank_l(d))
只用排名不用分数，因此不需要对 BM25 与余弦相似度做量纲归一化，
是工程上最省事也最鲁棒的融合方式，k 取 60。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .chunker import Chunk
from .config import RagConfig
from .index import RagIndex
from .textutil import QUESTION_SCAFFOLD, normalize, tokenize

_CJK_TOKEN = re.compile(r"^[\u4e00-\u9fff]+$")
_ASCII_TOKEN = re.compile(r"^[a-z][a-z0-9_.+#/-]*$")

KIND_PRIOR: dict[str, float] = {
    "definition": 1.00,
    "pitfall": 0.95,
    "procedure": 0.90,
    "method": 0.90,
    "example": 0.88,
    "body": 0.70,
    "relation": 0.50,
    "references": 0.0,
}


def _content_weight(token: str, idf: float) -> float:
    """实词权重 = IDF × log(1+词长)。弱词与提问脚手架词权重为 0。

    权重为 0 的词不参与"是否可回答"的判定，也不进入关键实词；
    但它们仍参与 BM25 排序与普通 coverage。
    """
    if token in QUESTION_SCAFFOLD:
        return 0.0
    if _CJK_TOKEN.match(token):
        if len(token) < 2:
            return 0.0
    elif _ASCII_TOKEN.match(token):
        if len(token) < 3:
            return 0.0
    else:
        return 0.0  # 纯数字或混合串
    return idf * math.log(1.0 + len(token))


def is_supporting(hit: "RetrievedChunk", cfg: RagConfig) -> bool:
    """判定一个检索片段是否足以支撑回答（拒答闸门的唯一实现，供全项目复用）。

    两个条件必须同时满足：
      1. relevance ≥ min_relevance   —— 实词加权覆盖率够高
      2. key_hit   ≥ min_key_hit     —— 问题的关键实词至少命中一个
    """
    return (
        hit.relevance >= cfg.answer.min_relevance
        and hit.key_hit >= cfg.answer.min_key_hit
    )


@dataclass
class RetrievedChunk:
    chunk: Chunk
    dense_rank: int | None = None
    dense_score: float = 0.0
    sparse_rank: int | None = None
    sparse_score: float = 0.0
    rrf: float = 0.0
    coverage: float = 0.0
    wcoverage: float = 0.0
    key_hit: float = 0.0
    phrase: float = 0.0
    section_hit: float = 0.0
    final_score: float = 0.0
    relevance: float = 0.0
    evidence_text: str = ""  # 喂给大模型的文本（可能已扩展为父块）
    citation_text: str = ""  # 展示与引用校验用的精确片段

    def trace(self) -> dict:
        return {
            "chunk_id": self.chunk.chunk_id,
            "doc_id": self.chunk.doc_id,
            "section": self.chunk.section,
            "kind": self.chunk.kind,
            "dense_rank": self.dense_rank,
            "sparse_rank": self.sparse_rank,
            "rrf": round(self.rrf, 6),
            "coverage": round(self.coverage, 4),
            "wcoverage": round(self.wcoverage, 4),
            "key_hit": round(self.key_hit, 4),
            "relevance": round(self.relevance, 4),
            "final_score": round(self.final_score, 4),
        }


def _longest_common_run(query_norm: str, text_norm: str) -> int:
    """最长公共子串长度（查询侧），用于奖励"原句命中"。语料小，O(n*m) 可接受。"""
    if not query_norm or not text_norm:
        return 0
    best = 0
    prev = [0] * (len(text_norm) + 1)
    for i in range(1, len(query_norm) + 1):
        cur = [0] * (len(text_norm) + 1)
        for j in range(1, len(text_norm) + 1):
            if query_norm[i - 1] == text_norm[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


class HybridRetriever:
    def __init__(self, index: RagIndex, cfg: RagConfig | None = None) -> None:
        self.index = index
        self.cfg = cfg or index.cfg
        self.history: list[dict] = []  # 最近一次检索的中间结果，用于 trace 与错误分析

    def retrieve(
        self,
        query: str,
        *,
        top_n: int | None = None,
        doc_ids: list[str] | None = None,
        kp_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        rc = self.cfg.retrieval
        self.history = []
        if not rc.use_retrieval:
            return []

        allowed = None
        if rc.use_metadata_filter:
            allowed = self.index.filter_indices(doc_ids=doc_ids, kp_ids=kp_ids)
            if allowed is not None and not allowed:
                return []

        dense = self.index.search_dense(query, rc.top_k_dense, allowed)
        sparse = self.index.search_sparse(query, rc.top_k_sparse, allowed)

        # ---- RRF 融合 ----
        pool: dict[int, RetrievedChunk] = {}
        for rank, (i, s) in enumerate(dense, start=1):
            rc_i = pool.setdefault(i, RetrievedChunk(chunk=self.index.chunks[i]))
            rc_i.dense_rank, rc_i.dense_score = rank, s
            rc_i.rrf += rc.dense_weight / (rc.rrf_k + rank)
        for rank, (i, s) in enumerate(sparse, start=1):
            rc_i = pool.setdefault(i, RetrievedChunk(chunk=self.index.chunks[i]))
            rc_i.sparse_rank, rc_i.sparse_score = rank, s
            rc_i.rrf += rc.sparse_weight / (rc.rrf_k + rank)

        if not pool:
            return []

        # ---- 重排特征 ----
        q_tokens = set(tokenize(query))
        q_norm = normalize(query).lower()
        max_rrf = max(c.rrf for c in pool.values()) or 1.0

        # 实词覆盖率（weighted coverage）：这是超范围拒答的核心判据。
        #
        # 只用 IDF 加权还不够：问"2024 年诺贝尔物理学奖颁给了谁"时，"2024"和"年"
        # 恰好出现在语料里，会贡献大半个权重，导致系统以为"有依据"。真正的实词
        # "诺贝尔物理学奖"却一个都没命中。
        #
        # 因此权重 = IDF × log(1+词长)，并且**排除弱词**：纯数字、单字中文、
        # 两字符以下英文。弱词只在普通 coverage 里起作用，不参与可回答性判定。
        q_weight = {t: _content_weight(t, self.index.token_idf(t)) for t in q_tokens}
        q_weight_sum = sum(q_weight.values())

        # 关键实词：权重最高的两个实词。这是"是否锚定在问题上"的判据。
        #
        # 为什么光有覆盖率不够：问"红烧肉怎么做才好吃？请给详细步骤"时，
        # 真正的实词"红烧肉""好吃"一个都没命中，但泛化的后缀"详细""步骤"
        # 恰好在语料里，能凑出 35% 的加权覆盖率，于是被误判为"有依据"。
        # 加一条结构性规则——**权重最高的两个实词至少命中一个**——
        # 比继续调连续阈值更稳健，因为它不依赖具体分数刻度。
        key_terms = [
            t for t, _ in sorted(q_weight.items(), key=lambda kv: -kv[1]) if q_weight[t] > 0
        ][:2]

        for c in pool.values():
            c_tokens = set(tokenize(c.chunk.text))
            c.coverage = len(q_tokens & c_tokens) / max(1, len(q_tokens))
            matched = q_tokens & c_tokens
            if q_weight_sum > 0:
                c.wcoverage = sum(q_weight[t] for t in matched if q_weight[t] > 0) / q_weight_sum
            else:
                c.wcoverage = c.coverage * 0.5  # 全是弱词时保守降权
            c.key_hit = (
                sum(1 for t in key_terms if t in c_tokens) / len(key_terms) if key_terms else 0.0
            )
            run = _longest_common_run(q_norm, normalize(c.chunk.text).lower())
            c.phrase = min(1.0, run / max(4, len(q_norm)))
            sec_tokens = set(tokenize(c.chunk.section))
            c.section_hit = len(q_tokens & sec_tokens) / max(1, len(q_tokens))

            rrf_norm = c.rrf / max_rrf
            prior = KIND_PRIOR.get(c.chunk.kind, 0.7)
            c.final_score = (
                0.34 * rrf_norm
                + 0.26 * c.wcoverage
                + 0.14 * c.coverage
                + 0.14 * c.phrase
                + 0.12 * prior
            )
            # relevance 是**可解释的**相关性，专门用于拒答阈值判定
            c.relevance = 0.70 * c.wcoverage + 0.15 * c.phrase + 0.15 * rrf_norm

        ranked = sorted(pool.values(), key=lambda x: -x.final_score)
        if not rc.use_rerank:
            ranked = sorted(pool.values(), key=lambda x: -x.rrf)

        # ---- 去重：同一小节只保留得分最高的 chunk（避免上下文被同一节占满）----
        seen_parent: set[str] = set()
        deduped: list[RetrievedChunk] = []
        for c in ranked:
            key = c.chunk.parent_id if rc.use_parent_expansion else c.chunk.chunk_id
            if key in seen_parent:
                continue
            seen_parent.add(key)
            deduped.append(c)
            self.history.append(c.trace())

        # ---- small-to-big：检索用小块，喂给模型用父块 ----
        n = top_n or rc.top_n_context
        out: list[RetrievedChunk] = []
        budget = rc.max_context_chars
        for c in deduped[:n]:
            evidence = c.chunk.text
            if rc.use_parent_expansion:
                parent_text = self.index.get_parent_text(c.chunk)
                if len(parent_text) > len(c.chunk.text):
                    evidence = parent_text
            c.evidence_text = evidence[: self.cfg.answer.max_evidence_chars]
            c.citation_text = c.chunk.text
            if budget - len(c.evidence_text) < 0 and out:
                break
            budget -= len(c.evidence_text)
            out.append(c)
        return out
