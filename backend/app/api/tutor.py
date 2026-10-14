"""M7 AI 助教的路由。

与 `app/main.py` 中诊断相关路由分开成文件，便于 M7 独立演进与评审。
服务实例（数据库会话工厂与配置）通过 `request.app.state` 获取，不在此处重复构造。
"""

from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import TutorAskRequest
from app.services import tutor as service
from app.services.tutor import TutorError

router = APIRouter(tags=["M7 AI 助教"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sessions(request: Request):
    return request.app.state.sessions


def _settings(request: Request):
    return request.app.state.settings


def _raise(exc: TutorError) -> None:
    status = 503 if exc.code in ("MISSING_API_KEY", "MISSING_MODEL") else 500
    detail = {"code": exc.code, "message": exc.message}
    # 失败时事件与 trace 已经写入，把 ID 一并返回，便于前端提示"问题已保存"。
    if exc.event_id:
        detail["event_id"] = exc.event_id
        detail["trace_id"] = exc.trace_id
    raise HTTPException(status, detail)


@router.get("/api/tutor/kb")
def kb_overview(request: Request):
    """知识库规模与文档清单。"""
    return service.kb_overview(_settings(request))


@router.get("/api/tutor/knowledge-points")
def knowledge_points(
    request: Request,
    doc_id: str | None = Query(default=None, description="按文档过滤，如 SE-01"),
    keyword: str | None = Query(default=None, description="按名称或定义过滤"),
):
    return service.knowledge_points(_settings(request), doc_id=doc_id, keyword=keyword)


@router.get("/api/tutor/graph")
def knowledge_graph(request: Request):
    """知识点先修图（M4 可视化与 M9 路径规划的数据源）。"""
    return service.knowledge_graph(_settings(request))


@router.get("/api/tutor/retrieve-debug")
def retrieve_debug(
    request: Request,
    q: str = Query(..., min_length=1, max_length=2000),
    top_n: int = Query(default=6, ge=1, le=20),
):
    """检索中间结果：稠密/稀疏排名、RRF、覆盖率、可回答性特征。"""
    return service.retrieve_debug(_settings(request), q, top_n=top_n)


@router.post("/api/tutor/ask")
def tutor_ask(request: Request, body: TutorAskRequest) -> dict:
    """回答学生问题，并把问题、回答、引用与知识点写入 asked 学习事件（M6-2）。"""
    try:
        return service.ask(
            _sessions(request),
            _settings(request),
            question=body.question,
            mode=body.mode,
            top_n=body.top_n,
        )
    except TutorError as exc:
        _raise(exc)


@router.get("/api/tutor/ask/stream")
def tutor_ask_stream(
    request: Request,
    q: str = Query(..., min_length=1, max_length=2000),
    mode: str = Query(default="live", pattern="^(live|demo)$"),
    top_n: int | None = Query(default=None, ge=1, le=20),
) -> StreamingResponse:
    """SSE 流式回答，满足 NF-2「首字符 < 5 秒」。结束后落库的事件与 trace 与同步接口一致。"""
    settings = _settings(request)
    sessions = _sessions(request)

    def event_stream() -> Iterator[str]:
        def emit(payload: dict) -> str:
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            rag = service.build_rag(settings, mode)
        except TutorError as exc:
            yield emit({"event": "error", "code": exc.code, "message": exc.message})
            return

        collected: list[str] = []
        citations: list[dict] = []
        abstained = False
        done: dict = {}
        try:
            for event in rag.answer_stream(q, top_n=top_n):
                if event.get("event") == "delta":
                    collected.append(event.get("text", ""))
                elif event.get("event") == "meta":
                    citations = event.get("citations", [])
                elif event.get("event") == "done":
                    abstained = bool(event.get("abstained"))
                    done = event
                yield emit(event)
        except Exception:  # noqa: BLE001 —— 流式过程中不向客户端暴露异常正文
            yield emit({"event": "error", "code": "STREAM_ERROR", "message": "流式输出中断。"})
            return

        # 流结束后落库：与同步接口写入同样的事件与 trace，保证两条路径口径一致。
        service.record_stream_result(
            sessions,
            settings,
            question=q,
            mode=mode,
            answer="".join(collected),
            citations=citations,
            abstained=abstained,
            done=done,
            top_n=top_n,
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/api/traces/{trace_id}")
def trace_detail(request: Request, trace_id: str):
    """按 trace ID 回放一次模型调用（NF-14）。"""
    detail = service.trace_detail(_sessions(request), trace_id)
    if detail is None:
        raise HTTPException(404, "trace 不存在")
    return detail


@router.get("/api/cost-report")
def cost_report(request: Request):
    """按功能汇总调用次数、token 与耗时（NF-4）。"""
    return service.cost_report(_sessions(request), _settings(request))
