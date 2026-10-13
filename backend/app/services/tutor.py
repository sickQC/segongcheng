"""M7 AI 助教服务：调用 RAG 检索内核，并把结果写成学习事件与模型调用记录。

与 `services/diagnosis.py` 保持同一套约定：

* 先完成模型调用，再用**一个**事务写入学习事件与 trace；
  模型调用期间不持有数据库写事务。
* `mode="live"` 走真实大模型；缺少配置时返回明确错误码，不返回伪造结果。
* `mode="demo"` 使用检索证据抽取拼接的演示回答，输出带显式标注，事件标记 `synthetic=true`。
* 不在服务端猜测费用：只记录接口真实返回的 token 数，费用在价格表命中时才给出估算。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace

from sqlalchemy import select

from app.models import LearningEvent, ModelTrace
from app.rag import PROMPT_VERSION, RagConfig, RagIndex, TutorRAG, build_index
from app.rag.llm import BaseLLM, estimate_cost, get_llm

logger = logging.getLogger(__name__)

FEATURE = "tutor.ask"
FEATURE_STREAM = "tutor.ask.stream"

# 每 100 万 token 的参考价（美元）。仅用于成本报表的估算；表里没有的模型返回 null，
# 不做线性外推，避免出现看似精确的虚构费用。
PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "deepseek-chat": (0.27, 1.10),
    "qwen-plus": (0.40, 1.20),
    "qwen-turbo": (0.05, 0.20),
}


class TutorError(Exception):
    def __init__(self, code, message, event_id=None, trace_id=None):
        self.code, self.message = code, message
        self.event_id, self.trace_id = event_id, trace_id


# 索引只构建/加载一次，进程内复用；构建耗时 <1 秒。
_index_lock = threading.Lock()
_index_cache: dict[str, RagIndex] = {}


def load_index(settings) -> RagIndex:
    cfg = RagConfig.from_settings(settings)
    key = str(cfg.index_dir)
    with _index_lock:
        if key not in _index_cache:
            try:
                _index_cache[key] = RagIndex.load(cfg)
            except FileNotFoundError:
                logger.info("RAG 索引缺失，正在构建：%s", cfg.index_dir)
                _index_cache[key] = build_index(cfg)
        return _index_cache[key]


def reset_cache() -> None:
    """测试与重建索引后清空进程内缓存。"""
    with _index_lock:
        _index_cache.clear()


def build_rag(settings, mode: str) -> TutorRAG:
    cfg = RagConfig.from_settings(settings)
    if mode == "live":
        if not cfg.llm.api_key:
            raise TutorError("MISSING_API_KEY", "尚未配置 LLM_API_KEY，无法进行真实模型问答。")
        if not settings.llm_model.strip():
            raise TutorError("MISSING_MODEL", "请在本机 .env 中配置 LLM_MODEL。")
        llm: BaseLLM = get_llm(replace(cfg.llm, provider="openai"))
    else:
        llm = get_llm(replace(cfg.llm, provider="offline"))
    return TutorRAG(load_index(settings), cfg, llm=llm)


def _status_of(result, mode: str) -> tuple[str, str | None]:
    """把一次问答映射为 trace 状态；模型失败与业务性拒答区分开。"""
    if result.llm.get("error"):
        return "failed", "MODEL_ERROR"
    action = result.guardrail.get("action", "allow")
    if action == "block":
        return "blocked", None
    if action == "refuse_cheat":
        return "refused", None
    if result.abstained:
        return "abstained", None
    return ("demo" if mode == "demo" else "succeeded"), None


def ask(
    sessions,
    settings,
    *,
    question: str,
    mode: str = "live",
    actor: str = "sim-student-001",
    top_n: int | None = None,
) -> dict:
    """回答一个学生问题，并把问题、回答、引用与知识点写入学习事件（M6-2）。"""
    started = time.perf_counter()

    try:
        rag = build_rag(settings, mode)
    except TutorError as exc:
        # 与诊断接口一致：模型暂时不可用时也要先把学生的问题存下来，不能丢数据。
        # 这里写入的是失败记录，不写入任何伪造的回答。
        persisted = _persist(
            sessions,
            actor=actor,
            feature=FEATURE,
            question=question,
            mode=mode,
            answer="",
            citations=[],
            abstained=False,
            guardrail={"action": "allow", "reasons": [], "message": ""},
            citation_report={},
            kp_ids=[],
            status="failed",
            error_code=exc.code,
            model_name=settings.llm_model or "unconfigured",
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage=None,
            input_summary={"question_length": len(question), "top_n": top_n, "retrieval_count": 0},
            details={"error": exc.message},
        )
        raise TutorError(exc.code, exc.message, persisted["event_id"], persisted["trace_id"]) from None

    try:
        result = rag.answer(question, top_n=top_n)
    except Exception:  # noqa: BLE001 —— 不把第三方异常正文写入响应，避免泄露密钥
        logger.exception("tutor ask failed")
        raise TutorError("INTERNAL_TUTOR_ERROR", "助教处理异常，请凭日志排查。") from None

    latency_ms = round((time.perf_counter() - started) * 1000)
    status, error_code = _status_of(result, mode)
    usage = {
        k: result.llm[k]
        for k in ("prompt_tokens", "completion_tokens")
        if isinstance(result.llm.get(k), int)
    }
    usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    model_name = result.llm.get("model") or settings.llm_model or "unconfigured"

    payload = {
        "question": question,
        "answer": result.answer,
        "abstained": result.abstained,
        "citations": [c.to_dict() for c in result.citations],
        "guardrail": result.guardrail,
        "citation_report": result.citation_report,
        "timings_ms": result.timings_ms,
    }

    return _persist(
        sessions,
        actor=actor,
        feature=FEATURE,
        question=question,
        mode=mode,
        answer=result.answer,
        citations=payload["citations"],
        abstained=result.abstained,
        guardrail=result.guardrail,
        citation_report=result.citation_report,
        kp_ids=result.kp_ids,
        status=status,
        error_code=error_code,
        model_name=model_name,
        latency_ms=latency_ms,
        usage=usage,
        input_summary={
            "question_length": len(question),
            "top_n": top_n,
            "retrieval_count": len(result.retrieved),
            "guardrail_action": result.guardrail.get("action", "allow"),
        },
        details={
            "rag_trace_id": result.trace_id,
            "retrieved": result.retrieved,
            "citation_report": result.citation_report,
            "removed_instruction_lines": result.removed_instruction_lines,
        },
    )


def record_stream_result(
    sessions,
    settings,
    *,
    question: str,
    mode: str,
    answer: str,
    citations: list[dict],
    abstained: bool,
    done: dict,
    actor: str = "sim-student-001",
    top_n: int | None = None,
) -> dict:
    """流式问答结束后落库，与 `ask` 写入同样结构的事件与 trace。"""
    guardrail = done.get("guardrail") or {"action": "allow", "reasons": [], "message": ""}
    citation_report = done.get("citation_report") or {}
    kp_ids = list(done.get("kp_ids") or [])
    status, error_code = _status_of_stream(guardrail, abstained, mode)
    return _persist(
        sessions,
        actor=actor,
        feature=FEATURE_STREAM,
        question=question,
        mode=mode,
        answer=answer,
        citations=citations,
        abstained=abstained,
        guardrail=guardrail,
        citation_report=citation_report,
        kp_ids=kp_ids,
        status=status,
        error_code=error_code,
        model_name=settings.llm_model or "unconfigured",
        latency_ms=int(done.get("total_ms") or 0),
        usage={},
        input_summary={
            "question_length": len(question),
            "top_n": top_n,
            "stream": True,
            "guardrail_action": guardrail.get("action", "allow"),
        },
        details={"citation_report": citation_report},
    )


def _status_of_stream(guardrail: dict, abstained: bool, mode: str) -> tuple[str, str | None]:
    action = guardrail.get("action", "allow")
    if action == "block":
        return "blocked", None
    if action == "refuse_cheat":
        return "refused", None
    if abstained:
        return "abstained", None
    return ("demo" if mode == "demo" else "succeeded"), None


def _persist(
    sessions,
    *,
    actor: str,
    feature: str,
    question: str,
    mode: str,
    answer: str,
    citations: list[dict],
    abstained: bool,
    guardrail: dict,
    citation_report: dict,
    kp_ids: list[str],
    status: str,
    error_code: str | None,
    model_name: str,
    latency_ms: int,
    usage: dict | None,
    input_summary: dict,
    details: dict,
) -> dict:
    """在**一个**事务中写入 asked 学习事件（M6-2）与模型调用记录（NF-14）。"""
    with sessions.begin() as session:
        event = LearningEvent(
            actor=actor,
            verb="asked",
            object={"type": "question", "id": None, "kp": kp_ids, "source": mode},
            result={
                "question": question,
                "answer": answer,
                "citations": citations,
                "abstained": abstained,
                "guardrail": guardrail,
                "citation_report": citation_report,
            },
            context={
                "course": "SE",
                "feature": feature,
                "mode": mode,
                "synthetic": mode == "demo",
            },
        )
        session.add(event)
        session.flush()

        trace = ModelTrace(
            diagnosis_id=None,
            event_id=event.event_id,
            feature=feature,
            source=mode,
            model=model_name,
            prompt_version=PROMPT_VERSION,
            status=status,
            input_summary=input_summary,
            details=details,
            latency_ms=latency_ms,
            usage=usage,
            error_code=error_code,
        )
        session.add(trace)
        session.flush()

        return {
            "event_id": event.event_id,
            "trace_id": trace.trace_id,
            "feature": feature,
            "status": status,
            "mode": mode,
            "answer": answer,
            "abstained": abstained,
            "citations": citations,
            "guardrail": guardrail,
            "citation_report": citation_report,
            "knowledge_point_ids": kp_ids,
            "latency_ms": latency_ms,
            "usage": usage,
        }


def kb_overview(settings) -> dict:
    index = load_index(settings)
    return {"stats": index.stats, "documents": index.doc_titles()}


def knowledge_points(settings, *, doc_id: str | None = None, keyword: str | None = None) -> dict:
    index = load_index(settings)
    kps = index.kps
    if doc_id:
        kps = [k for k in kps if k.doc_id == doc_id]
    if keyword:
        kps = [k for k in kps if keyword in k.name or keyword in k.definition]
    return {
        "count": len(kps),
        "items": [
            {
                "id": k.id,
                "name": k.name,
                "definition": k.definition,
                "difficulty": k.difficulty,
                "bloom": k.bloom,
                "doc_id": k.doc_id,
                "doc_title": k.doc_title,
                "prerequisite_ids": k.prereq_ids,
            }
            for k in kps
        ],
    }


def knowledge_graph(settings) -> dict:
    """知识点先修图，供 M4 可视化与 M9 路径规划直接消费。"""
    index = load_index(settings)
    nodes = [
        {
            "id": k.id,
            "name": k.name,
            "doc_id": k.doc_id,
            "doc_title": k.doc_title,
            "difficulty": k.difficulty,
            "bloom": k.bloom,
            "definition": k.definition,
        }
        for k in index.kps
    ]
    edges = [
        {"source": k.id, "target": pid, "type": "prerequisite"}
        for k in index.kps
        for pid in k.prereq_ids
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "document_count": len({k.doc_id for k in index.kps}),
        },
    }


def retrieve_debug(settings, question: str, top_n: int = 6) -> dict:
    """返回检索中间结果，用于误差分析与消融实验。"""
    rag = build_rag(settings, "demo")
    hits = rag.retriever.retrieve(question, top_n=top_n)
    return {
        "query": question,
        "ranking": rag.retriever.history,
        "hits": [
            {
                **h.trace(),
                "section": h.chunk.section,
                "snippet": h.citation_text[:300],
            }
            for h in hits
        ],
    }


def trace_detail(sessions, trace_id: str) -> dict | None:
    with sessions() as session:
        trace = session.get(ModelTrace, trace_id)
        if trace is None:
            return None
        row = {c.name: getattr(trace, c.name) for c in trace.__table__.columns}
        row["event"] = None
        if trace.event_id:
            event = session.get(LearningEvent, trace.event_id)
            if event is not None:
                row["event"] = {c.name: getattr(event, c.name) for c in event.__table__.columns}
        return row


def cost_report(sessions, settings) -> dict:
    """按功能汇总调用次数、token 与耗时；费用仅在价格表命中时给出估算。"""
    with sessions() as session:
        traces = session.scalars(select(ModelTrace).order_by(ModelTrace.created_at.desc()).limit(2000)).all()

    features: dict[str, dict] = {}
    for t in traces:
        row = features.setdefault(
            t.feature or "diagnosis",
            {
                "calls": 0,
                "succeeded": 0,
                "failed": 0,
                "abstained": 0,
                "blocked": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms_sum": 0,
                "estimated_cost_usd": 0.0,
                "priced_models": [],
                "unpriced_models": [],
            },
        )
        row["calls"] += 1
        if t.status in ("succeeded", "demo"):
            row["succeeded"] += 1
        elif t.status == "failed":
            row["failed"] += 1
        elif t.status == "abstained":
            row["abstained"] += 1
        elif t.status == "blocked":
            row["blocked"] += 1
        usage = t.usage or {}
        pt = usage.get("prompt_tokens") or 0
        ct = usage.get("completion_tokens") or 0
        row["prompt_tokens"] += pt
        row["completion_tokens"] += ct
        row["latency_ms_sum"] += t.latency_ms or 0
        price = PRICE_PER_MTOK.get((t.model or "").lower())
        if price:
            row["estimated_cost_usd"] += estimate_cost(t.model, pt, ct)
            if t.model not in row["priced_models"]:
                row["priced_models"].append(t.model)
        elif t.model:
            if t.model not in row["unpriced_models"]:
                row["unpriced_models"].append(t.model)

    for row in features.values():
        calls = max(1, row["calls"])
        row["avg_latency_ms"] = round(row["latency_ms_sum"] / calls, 1)
        row["latency_ms_sum"] = round(row["latency_ms_sum"], 1)
        row["estimated_cost_usd"] = round(row["estimated_cost_usd"], 6)

    return {
        "features": features,
        "total_calls": sum(r["calls"] for r in features.values()),
        "pricing_note": "费用仅在价格表命中时估算；未命中的模型记为 unpriced，不做外推。",
    }
