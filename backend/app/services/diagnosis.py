import json
import logging
import time

import httpx
from pydantic import ValidationError
from sqlalchemy import select

from app.agents.diagnosis import PRACTICE_PROMPT, PROMPT_VERSION, SYSTEM_PROMPT
from app.agents.diagnosis_guardrails import contains_prompt_leak, is_instruction_attack
from app.models import Diagnosis, LearningEvent, ModelTrace
from app.schemas import DiagnosisOutput
from app.services.c_model_gateway import ModelCallError, complete_json

logger = logging.getLogger(__name__)
QUESTION = {
    "id": "Q-VAL-01",
    "knowledge_point_id": "KP-VAL-01",
    "title": "软件验证与确认",
    "text": "请说明软件验证（Verification）与软件确认（Validation）的区别。",
    "sample_answer": "软件验证是检查软件是否满足用户实际需要，软件确认是检查软件是否符合设计规格。",
    "source": "项目自编演示题，非教师题库原文",
}


class DiagnosisError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def create_model_client(settings):
    return httpx.Client(timeout=settings.llm_timeout_seconds, follow_redirects=False)


def call_model(
    settings,
    event_id,
    answer,
    question=None,
    knowledge_point_id=None,
    knowledge_point_name=None,
    knowledge_point_definition=None,
    followup_context=None,
    assessment_context=None,
):
    if is_instruction_attack(answer):
        raise DiagnosisError("UNSAFE_DIAGNOSIS_INPUT", "作答包含修改诊断规则的指令，已保存但未发送给模型。")
    if settings.c_llm_backend == "api" and not settings.llm_api_key.get_secret_value().strip():
        raise DiagnosisError("MISSING_API_KEY", "作答已保存；尚未配置模型 API Key，无法进行真实诊断。")
    if settings.c_llm_backend == "api" and not (settings.c_llm_model or settings.llm_model).strip():
        raise DiagnosisError("MISSING_MODEL", "作答已保存；请在本机 .env 中配置 LLM_MODEL。")
    if settings.c_llm_backend == "codex":
        reply = complete_json(
            settings,
            SYSTEM_PROMPT if question is None else PRACTICE_PROMPT,
            {
                "event_id": event_id,
                "question": question or QUESTION["text"],
                "answer": answer,
                "knowledge_point_id": knowledge_point_id or QUESTION["knowledge_point_id"],
                "knowledge_point_name": knowledge_point_name or QUESTION["title"],
                "knowledge_point_definition": knowledge_point_definition or "",
                "followup_context": followup_context or {},
                "assessment_context": assessment_context or {},
            },
            DiagnosisOutput.model_json_schema(),
        )
        parsed = DiagnosisOutput.model_validate_json(reply.text)
        if contains_prompt_leak(
            json.dumps(parsed.model_dump(), ensure_ascii=False),
            SYSTEM_PROMPT if question is None else PRACTICE_PROMPT,
        ):
            raise DiagnosisError("PROMPT_LEAK", "模型输出包含系统指令，诊断未被采纳。")
        return parsed, reply.usage
    with create_model_client(settings) as client:
        response = client.post(
            settings.llm_base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + settings.llm_api_key.get_secret_value()},
            json={
                "model": settings.c_llm_model or settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (SYSTEM_PROMPT if question is None else PRACTICE_PROMPT)
                        + json.dumps(DiagnosisOutput.model_json_schema(), ensure_ascii=False),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "event_id": event_id,
                                "question": question or QUESTION["text"],
                                "knowledge_point_id": knowledge_point_id or QUESTION["knowledge_point_id"],
                                "knowledge_point_name": knowledge_point_name or QUESTION["title"],
                                "knowledge_point_definition": knowledge_point_definition or "",
                                "answer": answer,
                                "followup_context": followup_context or {},
                                "assessment_context": assessment_context or {},
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage")
        # 仅保留真实返回的 token 数，不猜测费用或缺失的统计值。
        safe_usage = (
            {
                k: v
                for k, v in usage.items()
                if k in ("prompt_tokens", "completion_tokens", "total_tokens") and type(v) is int and v >= 0
            }
            if isinstance(usage, dict)
            else None
        )
        parsed = DiagnosisOutput.model_validate_json(content)
        if contains_prompt_leak(
            json.dumps(parsed.model_dump(), ensure_ascii=False),
            SYSTEM_PROMPT if question is None else PRACTICE_PROMPT,
        ):
            raise DiagnosisError("PROMPT_LEAK", "模型输出包含系统指令，诊断未被采纳。")
        if parsed.knowledge_point_id != (knowledge_point_id or QUESTION["knowledge_point_id"]):
            raise ValueError("knowledge point mismatch")
        return parsed, safe_usage


def demo_output(event_id):
    return DiagnosisOutput(
        status="supported",
        knowledge_point_id="KP-VAL-01",
        mastery=0.35,
        confidence=0.8,
        problem_type="concept_confusion",
        problem_description="【固定模拟数据】示例学生把验证与确认的关注点互换。数值仅用于展示界面。",
        evidence_event_ids=[event_id],
        citations=[],
        recommendation="【模拟建议】比较‘符合规格’与‘满足用户需要’两个判断角度。",
        followup_question="【模拟追问】一个完全符合设计规格的系统，是否一定满足用户的实际需要？为什么？",
    )


def run_diagnosis(session_factory, settings, diagnosis_id, trace_id):
    started = time.perf_counter()
    # 使用新事务；提交作答的事务早已完成，网络失败不影响原事件。
    with session_factory() as session:
        diagnosis = session.get(Diagnosis, diagnosis_id)
        trace = session.get(ModelTrace, trace_id)
        event = session.get(LearningEvent, diagnosis.event_id)
        event_id, answer, mode = event.event_id, event.result["answer"], diagnosis.mode
        practice = event.object.get("type") in ("practice", "assessment")
        kp_id = event.object.get("kp", [QUESTION["knowledge_point_id"]])[0]
    output, usage, failure = None, None, None
    try:
        if mode == "demo":
            output = demo_output(event_id)
        else:
            if practice:
                output, usage = call_model(
                    settings,
                    event_id,
                    answer,
                    event.object["question"],
                    kp_id,
                    event.object.get("knowledge_point_name"),
                    event.object.get("knowledge_point_definition"),
                    event.object.get("followup_context"),
                    event.object.get("assessment_context"),
                )
            else:
                output, usage = call_model(settings, event_id, answer)
        if output.evidence_event_ids != [event_id]:
            raise DiagnosisError("INVALID_EVIDENCE", "模型引用了不属于本次作答的事件，诊断已被拒绝。")
        if output.knowledge_point_id != kp_id:
            raise DiagnosisError("INVALID_KNOWLEDGE_POINT", "模型返回的知识点与本次练习不符，诊断已被拒绝。")
    except (DiagnosisError, ModelCallError) as exc:
        failure = (exc.code, exc.message)
    except httpx.TimeoutException:
        failure = ("MODEL_TIMEOUT", "模型请求超时；作答已保存，可以重试。")
    except httpx.HTTPStatusError as exc:
        failure = ("MODEL_HTTP_ERROR", f"模型服务返回 HTTP {exc.response.status_code}；作答已保存。")
    except httpx.RequestError:
        failure = ("MODEL_CONNECTION_ERROR", "无法连接模型服务；请检查 API 地址和网络。")
    except (ValidationError, ValueError, KeyError, IndexError, TypeError):
        failure = ("INVALID_MODEL_OUTPUT", "模型响应未通过 JSON 或结构校验，诊断未被采纳。")
    except Exception:
        # 不把第三方异常正文写入日志或响应，避免密钥和提交内容泄露。
        failure = ("INTERNAL_DIAGNOSIS_ERROR", "诊断处理异常；作答已保存，请凭 trace ID 排查。")
    with session_factory.begin() as session:
        diagnosis = session.get(Diagnosis, diagnosis_id)
        trace = session.get(ModelTrace, trace_id)
        trace.latency_ms = round((time.perf_counter() - started) * 1000)
        trace.usage = usage
        if failure:
            diagnosis.status, trace.status = "failed", "failed"
            diagnosis.error_code, diagnosis.error_message = failure
            trace.error_code = failure[0]
        else:
            diagnosis.status = output.status
            diagnosis.output = output.model_dump()
            trace.status = "demo" if mode == "demo" else "succeeded"
    logger.info("diagnosis trace_id=%s status=%s", trace_id, "failed" if failure else mode)


def add_trace(session, settings, diagnosis, event):
    trace = ModelTrace(
        diagnosis_id=diagnosis.id,
        source=diagnosis.mode,
        model="demo-fixture-v1"
        if diagnosis.mode == "demo"
        else (settings.c_llm_model or settings.llm_model or "unconfigured"),
        prompt_version="diagnosis-demo-v1" if diagnosis.mode == "demo" else PROMPT_VERSION,
        event_id=event.event_id,
        feature={"practice": "practice.diagnosis", "assessment": "assessment.diagnosis"}.get(
            event.object.get("type"), "diagnosis"
        ),
        details={"backend": settings.c_llm_backend},
        input_summary={
            "event_id": event.event_id,
            "answer_length": len(event.result["answer"]),
            "knowledge_point_id": event.object.get("kp", [QUESTION["knowledge_point_id"]])[0],
            "retrieval_count": 0,
        },
    )
    session.add(trace)
    session.flush()
    return trace


def traces_for(session, diagnosis_id):
    return session.scalars(
        select(ModelTrace).where(ModelTrace.diagnosis_id == diagnosis_id).order_by(ModelTrace.created_at)
    ).all()
