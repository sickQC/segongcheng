"""RAG 检索增强层的参数配置。

所有可调参数集中在这里，便于做检索设计的消融实验（课程《实践项目要求》第 6 章）。
配置优先级：显式参数 > 环境变量 > 默认值；接入后端时用 `from_settings` 直接读取应用配置。

路径约定（ROOT 为仓库根目录）：
    data/kb/docs/*.md       课程讲义正文
    data/kb/meta/*.json     知识点元数据
    data/kb/synonyms.json   领域术语与缩写表
    data/index/             构建产物（索引、知识点图谱、统计）
    data/logs/              运行期 JSONL trace
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[3]

PROMPT_VERSION = "tutor-prompt/v1.3"


def _env_str(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v if v not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ[key])
    except (KeyError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ[key])
    except (KeyError, ValueError):
        return default


@dataclass
class ChunkConfig:
    """切分参数（消融维度之一）。"""

    target_size: int = 500
    overlap: int = 80
    min_chunk_chars: int = 80
    max_chunk_chars: int = 900
    definition_markers: tuple[str, ...] = ("是指", "定义为", "指的是", "是一种", "称为", "是由")


@dataclass
class RetrievalConfig:
    """检索参数（消融维度之二）。"""

    top_k_dense: int = 30
    top_k_sparse: int = 30
    rrf_k: int = 60
    top_n_context: int = 6
    max_context_chars: int = 7000
    dense_weight: float = 1.0
    sparse_weight: float = 1.0
    use_synonym_expansion: bool = True
    use_rerank: bool = True
    use_parent_expansion: bool = True
    use_metadata_filter: bool = True
    use_retrieval: bool = True


@dataclass
class AnswerConfig:
    """生成与拒答参数。"""

    # top1 相关性低于该阈值 -> 判定"资料中无依据"，拒答。
    # 由 scripts/calibrate_rag.py 在**开发集**上标定；禁止在测试集上调参。
    # 标定方法：取"超范围问题最高分"与"范围内问题最低分"的中点，最大化间隔。
    min_relevance: float = 0.39
    # 问题的关键实词（权重最高的两个）至少命中一个，才认为锚定在资料上。
    # 结构性规则，不随语料规模失效，因此不参与阈值标定。
    min_key_hit: float = 0.5
    min_supporting_chunks: int = 1
    temperature: float = 0.1
    max_tokens: int = 900
    max_evidence_chars: int = 1200


@dataclass
class GuardrailConfig:
    enabled: bool = True
    block_on_injection: bool = True
    refuse_exam_cheating: bool = True
    validate_citations: bool = True
    citation_accuracy_floor: float = 0.6


@dataclass
class LLMConfig:
    """大模型配置。

    provider="offline"：不调用外部服务，用检索到的证据做抽取式回答。
                        对应接口层的 mode="demo"，输出带显式标注，不作为智能体交付。
    provider="openai"：OpenAI 兼容接口，对应接口层的 mode="live"。
    """

    provider: Literal["offline", "openai"] = "offline"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    timeout_s: float = 60.0
    max_retries: int = 2


@dataclass
class EmbedderConfig:
    """向量嵌入后端（消融维度之三）。

    backend="hashing"：本地哈希 TF-IDF，零下载、确定性、离线可跑（默认）。
    backend="st"     ：sentence-transformers 本地模型。
    backend="openai" ：OpenAI 兼容 /embeddings 接口。
    """

    backend: Literal["hashing", "st", "openai"] = "hashing"
    dim: int = 1024
    st_model: str = "BAAI/bge-small-zh-v1.5"


@dataclass
class RagConfig:
    kb_dir: Path = ROOT / "data" / "kb"
    index_dir: Path = ROOT / "data" / "index"
    log_dir: Path = ROOT / "data" / "logs"
    synonyms_path: Path = ROOT / "data" / "kb" / "synonyms.json"

    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    answer: AnswerConfig = field(default_factory=AnswerConfig)
    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)

    @classmethod
    def from_settings(cls, settings) -> "RagConfig":
        """从后端 Settings 构造配置（应用运行时的唯一入口）。"""
        cfg = cls()
        key = settings.llm_api_key.get_secret_value().strip()
        # 没有配置 Key 时退回离线抽取式，避免启动即失败；接口层用 mode 明确区分两种来源。
        cfg.llm.provider = "openai" if key else "offline"
        cfg.llm.api_key = key
        cfg.llm.base_url = settings.llm_base_url
        cfg.llm.model = settings.llm_model or "gpt-4o-mini"
        cfg.llm.timeout_s = float(settings.llm_timeout_seconds)
        return cfg

    @classmethod
    def from_env(cls) -> "RagConfig":
        """从环境变量构造配置（离线脚本与评测使用）。"""
        cfg = cls()
        provider = _env_str("SE_RAG_LLM_PROVIDER", "offline").lower()
        cfg.llm.provider = "openai" if provider == "openai" else "offline"
        cfg.llm.api_key = _env_str("OPENAI_API_KEY", "")
        cfg.llm.base_url = _env_str("OPENAI_BASE_URL", cfg.llm.base_url)
        cfg.llm.model = _env_str("OPENAI_MODEL", cfg.llm.model)
        cfg.llm.embedding_model = _env_str("OPENAI_EMBED_MODEL", cfg.llm.embedding_model)
        cfg.llm.timeout_s = _env_float("SE_RAG_LLM_TIMEOUT", cfg.llm.timeout_s)

        backend = _env_str("SE_RAG_EMBED_BACKEND", cfg.embedder.backend)
        if backend in ("hashing", "st", "openai"):
            cfg.embedder.backend = backend  # type: ignore[assignment]
        cfg.embedder.dim = _env_int("SE_RAG_EMBED_DIM", cfg.embedder.dim)
        cfg.embedder.st_model = _env_str("SE_RAG_ST_MODEL", cfg.embedder.st_model)

        explicit_provider = os.environ.get("SE_RAG_LLM_PROVIDER") is None
        if cfg.llm.provider == "offline" and cfg.llm.api_key and explicit_provider:
            cfg.llm.provider = "openai"
        return cfg

    def describe(self) -> dict:
        """用于 trace 与成本报表的配置快照。"""
        return {
            "prompt_version": PROMPT_VERSION,
            "llm_provider": self.llm.provider,
            "llm_model": self.llm.model,
            "embedder_backend": self.embedder.backend,
            "chunk": vars(self.chunk),
            "retrieval": vars(self.retrieval),
            "answer": vars(self.answer),
        }
