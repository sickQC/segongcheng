"""RAG 主流程：护栏 → 检索 → 拒答判定 → 接地生成 → 引用校验 → trace。

这条链路的每一步都在 trace 里留痕，便于做误差分析与消融实验。
提示词不写在本文件，见 `app/agents/tutor.py`。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Iterator

from app.agents.tutor import ABSTAIN_TEMPLATE, SYSTEM_PROMPT, USER_TEMPLATE

from .config import PROMPT_VERSION, RagConfig
from .guardrails import (
    GuardrailVerdict,
    sanitize_evidence,
    scan_input,
    validate_citations,
    wrap_evidence,
)
from .index import RagIndex
from .llm import BaseLLM, LLMResult, get_llm
from .retrieve import HybridRetriever, RetrievedChunk, is_supporting
from .textutil import strip_markdown
from .trace import Tracer

# 引用校验失败时的兜底清洗
INVALID_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def _union_kp_ids(hits: list[RetrievedChunk]) -> list[str]:
    """把本次引用片段挂接的知识点合并去重，供学习事件与诊断复用。"""
    ids: list[str] = []
    for hit in hits:
        for kp_id in hit.chunk.kp_ids:
            if kp_id not in ids:
                ids.append(kp_id)
    return ids


@dataclass
class Citation:
    index: int
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    kind: str
    score: float
    snippet: str

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "section": self.section,
            "kind": self.kind,
            "score": round(self.score, 4),
            "snippet": self.snippet,
        }


@dataclass
class AnswerResult:
    trace_id: str
    question: str
    answer: str
    abstained: bool
    citations: list[Citation] = field(default_factory=list)
    guardrail: dict = field(default_factory=dict)
    citation_report: dict = field(default_factory=dict)
    llm: dict = field(default_factory=dict)
    retrieved: list[dict] = field(default_factory=list)
    timings_ms: dict = field(default_factory=dict)
    config_snapshot: dict = field(default_factory=dict)
    prompt_version: str = PROMPT_VERSION
    removed_instruction_lines: list[str] = field(default_factory=list)
    # 本次回答实际引用到的知识点，供 M6 事件与 M8 诊断复用。
    kp_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "question": self.question,
            "answer": self.answer,
            "abstained": self.abstained,
            "citations": [c.to_dict() for c in self.citations],
            "guardrail": self.guardrail,
            "citation_report": self.citation_report,
            "llm": self.llm,
            "retrieved": self.retrieved,
            "timings_ms": self.timings_ms,
            "prompt_version": self.prompt_version,
        }


class TutorRAG:
    def __init__(self, index: RagIndex, cfg: RagConfig | None = None, llm: BaseLLM | None = None) -> None:
        self.cfg = cfg or index.cfg
        self.index = index
        self.retriever = HybridRetriever(index, self.cfg)
        self.llm = llm or get_llm(self.cfg.llm)
        self.tracer = Tracer(self.cfg.log_dir)

    # ------------------------------------------------------------- helpers
    def _suggestions(self) -> str:
        kps = self.index.kps[:3]
        return "\n".join(f"- {kp.name}（{kp.doc_title}）" for kp in kps) if kps else "- 请先导入课程资料"

    def _build_evidence(self, hits: list[RetrievedChunk]) -> tuple[str, list[str]]:
        blocks: list[str] = []
        removed_all: list[str] = []
        for i, h in enumerate(hits, start=1):
            clean, removed = sanitize_evidence(h.evidence_text)
            removed_all.extend(removed)
            blocks.append(wrap_evidence(i, h.chunk.doc_title, h.chunk.section, clean))
        return "\n\n".join(blocks), removed_all

    def _make_citations(self, hits: list[RetrievedChunk]) -> list[Citation]:
        out: list[Citation] = []
        for i, h in enumerate(hits, start=1):
            snippet = strip_markdown(h.citation_text).replace("\n", " ")
            out.append(
                Citation(
                    index=i,
                    chunk_id=h.chunk.chunk_id,
                    doc_id=h.chunk.doc_id,
                    doc_title=h.chunk.doc_title,
                    section=h.chunk.section,
                    kind=h.chunk.kind,
                    score=h.final_score,
                    snippet=snippet[:220],
                )
            )
        return out

    def _should_abstain(self, hits: list[RetrievedChunk]) -> bool:
        if not hits:
            return True
        supporting = [h for h in hits if is_supporting(h, self.cfg)]
        return len(supporting) < self.cfg.answer.min_supporting_chunks

    def _finalize(
        self,
        *,
        trace_id: str,
        question: str,
        answer: str,
        abstained: bool,
        hits: list[RetrievedChunk],
        verdict: GuardrailVerdict,
        llm_res: LLMResult | None,
        timings: dict,
        removed: list[str],
        retrieval_history: list[dict],
    ) -> AnswerResult:
        citations = self._make_citations(hits) if not abstained else []
        report = validate_citations(answer, len(hits)).to_dict()
        result = AnswerResult(
            trace_id=trace_id,
            question=question,
            answer=answer,
            abstained=abstained,
            citations=citations,
            guardrail=verdict.to_dict(),
            citation_report=report,
            llm=llm_res.to_dict() if llm_res else {},
            retrieved=retrieval_history,
            timings_ms={k: round(v, 1) for k, v in timings.items()},
            config_snapshot=self.cfg.describe(),
            removed_instruction_lines=removed,
            kp_ids=_union_kp_ids(hits) if not abstained else [],
        )
        self.tracer.log(
            {
                "trace_id": trace_id,
                "feature": "tutor.ask",
                "prompt_version": PROMPT_VERSION,
                "question": question[:500],
                "answer_chars": len(answer),
                "abstained": abstained,
                "guardrail": verdict.to_dict(),
                "citation_report": report,
                "llm": result.llm,
                "retrieved": retrieval_history,
                "timings_ms": result.timings_ms,
                "removed_instruction_lines": removed[:5],
                "config": self.cfg.describe(),
            }
        )
        return result

    # ---------------------------------------------------------------- public
    def answer(
        self,
        question: str,
        *,
        top_n: int | None = None,
        doc_ids: list[str] | None = None,
        kp_ids: list[str] | None = None,
    ) -> AnswerResult:
        t_start = time.perf_counter()
        timings: dict[str, float] = {}
        trace_id = Tracer.new_trace_id()

        # 1) 输入护栏
        t = time.perf_counter()
        verdict = scan_input(question, enabled=self.cfg.guardrails.enabled)
        timings["guardrail_input"] = (time.perf_counter() - t) * 1000

        if verdict.action == "block":
            timings["total"] = (time.perf_counter() - t_start) * 1000
            return self._finalize(
                trace_id=trace_id,
                question=question,
                answer=verdict.message,
                abstained=True,
                hits=[],
                verdict=verdict,
                llm_res=None,
                timings=timings,
                removed=[],
                retrieval_history=[],
            )

        if verdict.action == "refuse_cheat":
            timings["total"] = (time.perf_counter() - t_start) * 1000
            return self._finalize(
                trace_id=trace_id,
                question=question,
                answer=verdict.message,
                abstained=True,
                hits=[],
                verdict=verdict,
                llm_res=None,
                timings=timings,
                removed=[],
                retrieval_history=[],
            )

        # 2) 检索
        t = time.perf_counter()
        hits = self.retriever.retrieve(question, top_n=top_n, doc_ids=doc_ids, kp_ids=kp_ids)
        timings["retrieve"] = (time.perf_counter() - t) * 1000
        history = list(self.retriever.history)

        # 3) 拒答判定（资料不足以支撑回答）
        if self._should_abstain(hits):
            answer = ABSTAIN_TEMPLATE.format(question=question, suggestions=self._suggestions())
            timings["total"] = (time.perf_counter() - t_start) * 1000
            return self._finalize(
                trace_id=trace_id,
                question=question,
                answer=answer,
                abstained=True,
                hits=[],
                verdict=verdict,
                llm_res=None,
                timings=timings,
                removed=[],
                retrieval_history=history,
            )

        # 4) 组装接地提示词
        t = time.perf_counter()
        evidence, removed = self._build_evidence(hits)
        user_prompt = USER_TEMPLATE.format(question=question, evidence=evidence)
        timings["prompt_build"] = (time.perf_counter() - t) * 1000

        # 5) 生成
        t = time.perf_counter()
        llm_res = self.llm.complete(SYSTEM_PROMPT, user_prompt)
        timings["generate"] = (time.perf_counter() - t) * 1000

        answer = llm_res.text
        if llm_res.degraded and not answer:
            answer = (
                "⚠️ 大模型调用失败，已降级。请稍后重试或切换到离线模式。\n"
                f"错误信息：{llm_res.error}"
            )

        # 6) 输出护栏：引用校验（NF-11）
        t = time.perf_counter()
        if self.cfg.guardrails.validate_citations and answer:
            rep = validate_citations(answer, len(hits))
            if rep.invalid:
                keep = set(rep.valid)
                answer = INVALID_CITATION_RE.sub(
                    lambda m: m.group(0) if int(m.group(1)) in keep else "", answer
                )
        timings["output_guardrail"] = (time.perf_counter() - t) * 1000
        timings["total"] = (time.perf_counter() - t_start) * 1000

        return self._finalize(
            trace_id=trace_id,
            question=question,
            answer=answer,
            abstained=False,
            hits=hits,
            verdict=verdict,
            llm_res=llm_res,
            timings=timings,
            removed=removed,
            retrieval_history=history,
        )

    # ------------------------------------------------------------- streaming
    def answer_stream(
        self, question: str, *, top_n: int | None = None, doc_ids: list[str] | None = None
    ) -> Iterator[dict]:
        """SSE 事件流：meta → delta… → done。满足 NF-2 首字符 < 5 秒。"""
        t_start = time.perf_counter()
        trace_id = Tracer.new_trace_id()
        verdict = scan_input(question, enabled=self.cfg.guardrails.enabled)

        if verdict.action != "allow":
            yield {"event": "meta", "trace_id": trace_id, "guardrail": verdict.to_dict(), "citations": []}
            yield {"event": "delta", "text": verdict.message}
            yield {
                "event": "done",
                "trace_id": trace_id,
                "abstained": True,
                "guardrail": verdict.to_dict(),
                "citation_report": validate_citations(verdict.message, 0).to_dict(),
                "kp_ids": [],
            }
            return

        hits = self.retriever.retrieve(question, top_n=top_n, doc_ids=doc_ids)
        if self._should_abstain(hits):
            text = ABSTAIN_TEMPLATE.format(question=question, suggestions=self._suggestions())
            yield {"event": "meta", "trace_id": trace_id, "guardrail": verdict.to_dict(), "citations": []}
            yield {"event": "delta", "text": text}
            yield {
                "event": "done",
                "trace_id": trace_id,
                "abstained": True,
                "guardrail": verdict.to_dict(),
                "citation_report": validate_citations(text, 0).to_dict(),
                "kp_ids": [],
            }
            return

        evidence, removed = self._build_evidence(hits)
        user_prompt = USER_TEMPLATE.format(question=question, evidence=evidence)
        citations = [c.to_dict() for c in self._make_citations(hits)]
        yield {
            "event": "meta",
            "trace_id": trace_id,
            "guardrail": verdict.to_dict(),
            "citations": citations,
            "first_token_ms": round((time.perf_counter() - t_start) * 1000, 1),
        }

        buf: list[str] = []
        for piece in self.llm.stream(SYSTEM_PROMPT, user_prompt):
            buf.append(piece)
            yield {"event": "delta", "text": piece}

        answer = "".join(buf)
        rep = validate_citations(answer, len(hits))
        yield {
            "event": "done",
            "trace_id": trace_id,
            "abstained": False,
            "guardrail": verdict.to_dict(),
            "citation_report": rep.to_dict(),
            "kp_ids": _union_kp_ids(hits),
            "total_ms": round((time.perf_counter() - t_start) * 1000, 1),
        }
        self.tracer.log(
            {
                "trace_id": trace_id,
                "feature": "tutor.ask.stream",
                "prompt_version": PROMPT_VERSION,
                "question": question[:500],
                "answer_chars": len(answer),
                "abstained": False,
                "guardrail": verdict.to_dict(),
                "citation_report": rep.to_dict(),
                "llm": {"model": getattr(self.llm, "cfg", self.cfg.llm).model, "provider": self.llm.provider},
                "retrieved": list(self.retriever.history),
                "removed_instruction_lines": removed[:5],
            }
        )
