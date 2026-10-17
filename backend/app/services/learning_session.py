"""5E state machine: evidence/quality gates, adjacent transitions and durable turns."""

import json
import time

import httpx
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.agents.diagnosis_guardrails import contains_prompt_leak, is_instruction_attack
from app.agents.learning_templates import LEARNING_PROMPT, LEARNING_PROMPT_VERSION, STAGES, TEMPLATES
from app.core.errors import fail
from app.models import KnowledgePoint, LearningEvent, ModelTrace
from app.models.learning_session import LearningSession, LearningTurn
from app.models.legacy import now, uid
from app.schemas.learning_session import LearningFeedback
from app.services.c_model_gateway import ModelCallError, complete_json


def session_out(db, session):
    turns = db.scalars(
        select(LearningTurn)
        .where(LearningTurn.session_id == session.id)
        .order_by(LearningTurn.created_at, LearningTurn.id)
    ).all()
    quiz = session.snapshot["template"]["quiz"]
    return {
        "id": session.id,
        "course_id": session.course_id,
        "student_id": session.student_id,
        "knowledge_point_id": session.knowledge_point_id,
        "knowledge_point_name": session.snapshot["name"],
        "stage": session.stage,
        "status": session.status,
        "pending_turn_id": session.pending_turn_id,
        "task": session.snapshot["template"]["tasks"][STAGES.index(session.stage)],
        "evaluation": {"stem": quiz["stem"], "options": quiz["options"]}
        if session.stage == "evaluate"
        else None,
        "turns": [turn_out(turn) for turn in turns],
        "updated_at": session.updated_at,
    }


def turn_out(turn):
    return {
        key: getattr(turn, key)
        for key in (
            "id",
            "session_id",
            "answer",
            "evaluation_choice",
            "stage_before",
            "stage_after",
            "status",
            "output",
            "error_code",
            "error_message",
            "event_id",
            "trace_id",
            "created_at",
        )
    }


def create_session(sessions, student_id, body):
    try:
        with sessions.begin() as db:
            previous = db.scalar(
                select(LearningSession).where(
                    LearningSession.student_id == student_id,
                    LearningSession.request_id == str(body.request_id),
                )
            )
            if previous:
                if (
                    previous.course_id != body.course_id
                    or previous.knowledge_point_id != body.knowledge_point_id
                ):
                    fail(409, "REQUEST_CONFLICT", "同一请求编号已用于另一个学习会话")
                return session_out(db, previous)
            kp = db.get(KnowledgePoint, body.knowledge_point_id)
            if kp is None or kp.course_id != body.course_id:
                fail(422, "KNOWLEDGE_POINT_MISMATCH", "知识点必须属于当前课程")
            if kp.code not in TEMPLATES:
                fail(422, "TEMPLATE_NOT_AVAILABLE", "该知识点尚未配置 5E 教学模板")
            session = LearningSession(
                course_id=body.course_id,
                student_id=student_id,
                knowledge_point_id=kp.id,
                request_id=str(body.request_id),
                snapshot={
                    "code": kp.code,
                    "name": kp.name,
                    "definition": kp.definition,
                    "template": TEMPLATES[kp.code],
                },
            )
            db.add(session)
            db.flush()
            result = session_out(db, session)
        return result
    except IntegrityError:
        with sessions() as db:
            previous = db.scalar(
                select(LearningSession).where(
                    LearningSession.student_id == student_id,
                    LearningSession.request_id == str(body.request_id),
                )
            )
            if (
                previous
                and previous.course_id == body.course_id
                and previous.knowledge_point_id == body.knowledge_point_id
            ):
                return session_out(db, previous)
        raise


def save_turn(sessions, settings, session_id, student_id, body):
    with sessions.begin() as db:
        session = db.get(LearningSession, session_id)
        if session is None or session.student_id != student_id:
            fail(404, "SESSION_NOT_FOUND", "本人的学习会话不存在")
        previous = db.scalar(
            select(LearningTurn).where(
                LearningTurn.session_id == session_id, LearningTurn.request_id == str(body.request_id)
            )
        )
        if previous:
            if previous.answer != body.answer or previous.evaluation_choice != body.evaluation_choice:
                fail(409, "REQUEST_CONFLICT", "同一请求编号已用于不同作答")
            return turn_out(previous), False
        if session.status != "active":
            fail(409, "SESSION_COMPLETED", "学习会话已完成，请开始新会话")
        if session.stage == "evaluate":
            if body.evaluation_choice not in session.snapshot["template"]["quiz"]["options"]:
                fail(422, "EVALUATION_REQUIRED", "评价阶段必须完成本阶段小测")
        elif body.evaluation_choice is not None:
            fail(422, "UNEXPECTED_EVALUATION", "当前阶段尚未进入评价小测")
        turn_id = uid()
        claimed = db.execute(
            update(LearningSession)
            .where(
                LearningSession.id == session_id,
                LearningSession.pending_turn_id.is_(None),
                LearningSession.status == "active",
                LearningSession.stage == session.stage,
            )
            .values(pending_turn_id=turn_id, updated_at=now())
        )
        if not claimed.rowcount:
            previous = db.scalar(
                select(LearningTurn).where(
                    LearningTurn.session_id == session_id, LearningTurn.request_id == str(body.request_id)
                )
            )
            if (
                previous
                and previous.answer == body.answer
                and previous.evaluation_choice == body.evaluation_choice
            ):
                return turn_out(previous), False
            fail(409, "TURN_IN_PROGRESS", "上一轮仍在处理，请等待结果后再回复")
        event = LearningEvent(
            actor=student_id,
            verb="responded",
            object={
                "type": "learning_5e",
                "id": session_id,
                "kp": [session.knowledge_point_id],
                "stage": session.stage,
            },
            result={"answer": body.answer, "evaluation_choice": body.evaluation_choice},
            context={"course": session.course_id, "source": "learning_5e", "synthetic": False},
        )
        db.add(event)
        db.flush()
        trace = ModelTrace(
            event_id=event.event_id,
            feature="learning.5e",
            source="live",
            model=settings.c_llm_model or settings.llm_model or "unconfigured",
            prompt_version=LEARNING_PROMPT_VERSION,
            input_summary={
                "session_id": session_id,
                "stage": session.stage,
                "answer_length": len(body.answer),
            },
            details={"backend": settings.c_llm_backend},
        )
        db.add(trace)
        db.flush()
        turn = LearningTurn(
            id=turn_id,
            session_id=session_id,
            request_id=str(body.request_id),
            answer=body.answer,
            evaluation_choice=body.evaluation_choice,
            stage_before=session.stage,
            event_id=event.event_id,
            trace_id=trace.trace_id,
        )
        db.add(turn)
        db.flush()
        result = turn_out(turn)
    return result, True


def checked_transition(stage, output, answer, quiz_correct):
    before, after = STAGES.index(stage), STAGES.index(output.next_stage)
    if abs(after - before) > 1:
        raise ModelCallError("INVALID_TRANSITION", "模型建议跨越多个学习阶段，本轮推进已拒绝。")
    ready = output.status == "supported" and output.quality >= 0.7 and len(answer.strip()) >= 8
    target = output.next_stage if after <= before or ready else stage
    if output.status == "insufficient":
        target = stage
    completed = stage == "evaluate" and target == "evaluate" and ready and quiz_correct
    return target, completed


def run_turn(sessions, settings, turn_id):
    started = time.perf_counter()
    with sessions() as db:
        turn = db.get(LearningTurn, turn_id)
        session = db.get(LearningSession, turn.session_id)
        if turn.status != "pending" or session.pending_turn_id != turn_id:
            return
        history = db.scalars(
            select(LearningTurn)
            .where(LearningTurn.session_id == session.id, LearningTurn.status == "succeeded")
            .order_by(LearningTurn.created_at.desc())
            .limit(10)
        ).all()
        data = {
            "event_id": turn.event_id,
            "stage": turn.stage_before,
            "answer": turn.answer,
            "knowledge_point": {key: session.snapshot[key] for key in ("code", "name", "definition")},
            "stage_tasks": dict(zip(STAGES, session.snapshot["template"]["tasks"], strict=True)),
            "history": [
                {"stage": row.stage_before, "answer": row.answer, "feedback": row.output}
                for row in reversed(history)
            ],
        }
        quiz_correct = turn.evaluation_choice == session.snapshot["template"]["quiz"]["correct"]
        if turn.stage_before == "evaluate":
            data["quiz"] = {
                "stem": session.snapshot["template"]["quiz"]["stem"],
                "choice": turn.evaluation_choice,
                "correct": quiz_correct,
            }
    output, usage, failure, target, completed = None, None, None, None, False
    guardrail_action = None
    try:
        if is_instruction_attack(turn.answer):
            raise ModelCallError("UNSAFE_LEARNING_INPUT", "作答包含修改学习规则的指令，已保存但未请求模型。")
        reply = complete_json(settings, LEARNING_PROMPT, data, LearningFeedback.model_json_schema())
        usage = reply.usage
        output = LearningFeedback.model_validate_json(reply.text)
        if output.evidence_event_ids != [turn.event_id]:
            raise ModelCallError("INVALID_EVIDENCE", "模型使用了不属于本轮作答的证据。")
        if contains_prompt_leak(json.dumps(output.model_dump(), ensure_ascii=False), LEARNING_PROMPT):
            raise ModelCallError("PROMPT_LEAK", "模型返回了系统指令，本轮结果已拒绝。")
        target, completed = checked_transition(turn.stage_before, output, turn.answer, quiz_correct)
        if turn.stage_before == "explore" or target == "explore":
            definition = session.snapshot["definition"].strip()
            if (len(definition) >= 12 and definition in output.reply) or not any(
                mark in output.reply for mark in ("?", "？")
            ):
                output.reply = (
                    session.snapshot["template"]["tasks"][STAGES.index(target)]
                    + " 你会用什么具体例子支持自己的判断？"
                )
                guardrail_action = "template_hint_replacement"
    except ModelCallError as exc:
        failure = (exc.code, exc.message)
    except httpx.TimeoutException:
        failure = ("MODEL_TIMEOUT", "模型请求超时；本轮答案已保存。")
    except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError, IndexError):
        failure = ("INVALID_MODEL_RESPONSE", "模型响应未通过调用或结构校验；本轮答案已保存。")
    except Exception:
        failure = ("INTERNAL_LEARNING_ERROR", "学习反馈处理失败，请凭 trace 编号排查。")
    with sessions.begin() as db:
        turn = db.get(LearningTurn, turn_id)
        session = db.get(LearningSession, turn.session_id)
        if turn.status != "pending" or session.pending_turn_id != turn_id:
            return
        trace = db.get(ModelTrace, turn.trace_id)
        trace.usage, trace.latency_ms = usage, round((time.perf_counter() - started) * 1000)
        if failure:
            turn.status, trace.status = "failed", "failed"
            turn.error_code, turn.error_message = failure
            trace.error_code = failure[0]
        else:
            turn.status, trace.status = "succeeded", "succeeded"
            turn.output = {
                **output.model_dump(),
                "actual_stage": target,
                "completed": completed,
                "guardrail_action": guardrail_action,
                "evaluation_correct": quiz_correct if turn.stage_before == "evaluate" else None,
            }
            turn.stage_after, session.stage = target, target
            if guardrail_action:
                trace.details = {**(trace.details or {}), "guardrail_action": guardrail_action}
            if completed:
                session.status = "completed"
        session.pending_turn_id, session.updated_at = None, now()


def recover_interrupted(db):
    sessions = db.scalars(select(LearningSession).where(LearningSession.pending_turn_id.is_not(None))).all()
    for session in sessions:
        turn = db.get(LearningTurn, session.pending_turn_id)
        if turn and turn.status == "pending":
            turn.status, turn.error_code = "failed", "PROCESS_INTERRUPTED"
            turn.error_message = "上一轮在进程退出时中断；答案已保存，可以重新提交本轮。"
            trace = db.get(ModelTrace, turn.trace_id)
            trace.status, trace.error_code = "failed", "PROCESS_INTERRUPTED"
        session.pending_turn_id = None
