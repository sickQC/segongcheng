"""RAG 检索增强层（M7 AI 助教的检索内核）。

对外主要入口：
    from app.rag import RagConfig, RagIndex, TutorRAG

模块划分：
    config    参数与路径约定（消融开关集中在此）
    textutil  归一化、分词、领域词典、同义词扩展、提问脚手架词
    chunker   结构感知切分（定义句单独成块 + 父块）
    embedder  可插拔向量后端：hashing / sentence-transformers / OpenAI
    index     稠密 + BM25 双索引、知识点图谱
    retrieve  混合检索、RRF、重排、可回答性判定
    guardrails 提示注入、作弊诱导、资料净化、引用校验
    llm       OpenAI 兼容客户端 + 离线兜底 + 成本核算
    tutor     主流程编排（护栏 → 检索 → 拒答 → 生成 → 校验）
    trace     JSONL 明细 trace 与成本报表
"""

from .config import (
    PROMPT_VERSION,
    AnswerConfig,
    ChunkConfig,
    EmbedderConfig,
    GuardrailConfig,
    LLMConfig,
    RagConfig,
    RetrievalConfig,
)
from .index import KnowledgePoint, RagIndex, build_index
from .retrieve import HybridRetriever, RetrievedChunk, is_supporting
from .tutor import AnswerResult, Citation, TutorRAG

__all__ = [
    "PROMPT_VERSION",
    "AnswerConfig",
    "ChunkConfig",
    "EmbedderConfig",
    "GuardrailConfig",
    "LLMConfig",
    "RagConfig",
    "RetrievalConfig",
    "KnowledgePoint",
    "RagIndex",
    "build_index",
    "HybridRetriever",
    "RetrievedChunk",
    "is_supporting",
    "AnswerResult",
    "Citation",
    "TutorRAG",
]
