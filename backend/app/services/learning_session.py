"""5E state machine: evidence/quality gates, adjacent transitions and durable turns."""

import json
import time
from copy import deepcopy

import httpx
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.agents.diagnosis_guardrails import contains_prompt_leak, is_instruction_attack
from app.agents.learning_templates import LEARNING_PROMPT, LEARNING_PROMPT_VERSION, STAGES, TEMPLATES
from app.core.errors import fail
from app.models import Diagnosis, KnowledgePoint, LearningEvent, ModelTrace
from app.models.assessment import QuizAttempt
from app.models.learning_session import LearningSession, LearningTurn
from app.models.legacy import now, uid
from app.models.practice import PracticeExercise, PracticeSubmission
from app.schemas.learning_session import LearningFeedback
from app.services.c_model_gateway import ModelCallError, complete_json
from app.services.learning_curriculum import chapter_for, lecture_links, lecture_materials


def source_context(db, student_id, body):
    """Resolve the student's own submitted work; never accept client-authored context."""
    if not body.source_event_id:
        return None
    event = db.get(LearningEvent, body.source_event_id)
    if (
        event is None
        or event.actor != student_id
        or event.context.get("course") != body.course_id
        or event.context.get("synthetic") is not False
    ):
        fail(404, "SOURCE_NOT_FOUND", "本人的原题作答记录不存在")
    kind = event.object.get("type")
    reference = {}
    if kind == "assessment":
        attempt = db.get(QuizAttempt, event.object.get("attempt_id"))
        question = (
            next((q for q in attempt.questions if q["id"] == event.object.get("id")), None)
            if attempt
            else None
        )
        if (
            not attempt
            or attempt.student_id != student_id
            or attempt.course_id != body.course_id
            or attempt.status != "submitted"
            or not question
            or question["knowledge_point_id"] != body.knowledge_point_id
        ):
            fail(422, "SOURCE_MISMATCH", "原题必须是当前知识点的已提交测验")
        reference = {"attempt_id": attempt.id, "options": question["options"]}
    elif kind == "practice":
        submission = db.scalar(
            select(PracticeSubmission).where(PracticeSubmission.event_id == event.event_id)
        )
        exercise = db.get(PracticeExercise, submission.exercise_id) if submission else None
        if (
            not submission
            or submission.student_id != student_id
            or submission.course_id != body.course_id
            or not exercise
            or exercise.knowledge_point_id != body.knowledge_point_id
        ):
            fail(422, "SOURCE_MISMATCH", "原题必须是当前知识点的小练习")
        reference = {"exercise_id": exercise.id}
    else:
        fail(422, "SOURCE_MISMATCH", "请选择测验或小练习的诊断记录")
    diagnosis = db.scalar(
        select(Diagnosis).where(Diagnosis.event_id == event.event_id).order_by(Diagnosis.created_at.desc())
    )
    if not diagnosis or diagnosis.status not in ("supported", "insufficient") or not diagnosis.output:
        fail(409, "DIAGNOSIS_NOT_READY", "请等待原题诊断完成后开始针对性学习")
    return {
        "event_id": event.event_id,
        "type": kind,
        **reference,
        "question": event.object.get("question", ""),
        "original_answer": event.result.get("answer", ""),
        "diagnosis": {
            key: diagnosis.output.get(key, "")
            for key in ("problem_description", "recommendation", "followup_question")
        },
    }


def same_request(previous, body):
    return (
        previous.course_id == body.course_id
        and previous.knowledge_point_id == body.knowledge_point_id
        and (previous.snapshot.get("source") or {}).get("event_id") == body.source_event_id
    )


def session_out(db, session):
    turns = db.scalars(
        select(LearningTurn)
        .where(LearningTurn.session_id == session.id)
        .order_by(LearningTurn.created_at, LearningTurn.id)
    ).all()
    quiz = session.snapshot["template"]["quiz"]
    exercise = db.scalar(
        select(PracticeExercise).where(
            PracticeExercise.course_id == session.course_id,
            PracticeExercise.knowledge_point_id == session.knowledge_point_id,
        )
    )
    return {
        "id": session.id,
        "course_id": session.course_id,
        "student_id": session.student_id,
        "knowledge_point_id": session.knowledge_point_id,
        "knowledge_point_name": session.snapshot["name"],
        "chapter": chapter_for(db, db.get(KnowledgePoint, session.knowledge_point_id)),
        "lectures": lecture_links(session.snapshot.get("course_materials", [])),
        "source": session.snapshot.get("source"),
        "practice_available": exercise is not None,
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


def create_session(sessions, student_id, body, settings=None):
    try:
        with sessions.begin() as db:
            previous = db.scalar(
                select(LearningSession).where(
                    LearningSession.student_id == student_id,
                    LearningSession.request_id == str(body.request_id),
                )
            )
            if previous:
                if not same_request(previous, body):
                    fail(409, "REQUEST_CONFLICT", "同一请求编号已用于另一个学习会话")
                return session_out(db, previous)
            kp = db.get(KnowledgePoint, body.knowledge_point_id)
            if kp is None or kp.course_id != body.course_id:
                fail(422, "KNOWLEDGE_POINT_MISMATCH", "知识点必须属于当前课程")
            if kp.code not in TEMPLATES:
                fail(422, "TEMPLATE_NOT_AVAILABLE", "该知识点尚未配置 5E 教学模板")
            source = source_context(db, student_id, body)
            template = deepcopy(TEMPLATES[kp.code])
            if source:
                template["tasks"][0] = (
                    "回看下方原题和原答案：你当时是怎样判断的？现在最不确定的是哪一步？请说明理由。"
                )
            session = LearningSession(
                course_id=body.course_id,
                student_id=student_id,
                knowledge_point_id=kp.id,
                request_id=str(body.request_id),
                snapshot={
                    "code": kp.code,
                    "name": kp.name,
                    "definition": kp.definition,
                    "chapter": chapter_for(db, kp),
                    "course_materials": lecture_materials(settings, body.course_id, kp.code, db=db),
                    "template": template,
                    "source": source,
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
            if previous and same_request(previous, body):
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
                "question": session.snapshot["template"]["tasks"][STAGES.index(session.stage)],
                "source_event_id": (session.snapshot.get("source") or {}).get("event_id"),
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


def retry_turn(sessions, settings, session_id, student_id, turn_id):
    """Retry the latest failed answer, retaining its event and every model attempt."""
    with sessions.begin() as db:
        session = db.get(LearningSession, session_id)
        if session is None or session.student_id != student_id:
            fail(404, "SESSION_NOT_FOUND", "本人的学习会话不存在")
        turn = db.get(LearningTurn, turn_id)
        if turn is None or turn.session_id != session_id:
            fail(404, "TURN_NOT_FOUND", "本会话的作答不存在")
        latest = db.scalar(
            select(LearningTurn)
            .where(LearningTurn.session_id == session_id)
            .order_by(LearningTurn.created_at.desc(), LearningTurn.id.desc())
            .limit(1)
        )
        if (
            turn.status != "failed"
            or latest.id != turn_id
            or session.status != "active"
            or session.stage != turn.stage_before
        ):
            fail(409, "RETRY_NOT_ALLOWED", "仅当前阶段最后一次失败的作答可重试")
        claimed = db.execute(
            update(LearningSession)
            .where(
                LearningSession.id == session_id,
                LearningSession.pending_turn_id.is_(None),
                LearningSession.status == "active",
                LearningSession.stage == turn.stage_before,
            )
            .values(pending_turn_id=turn_id, updated_at=now())
        )
        if not claimed.rowcount:
            fail(409, "TURN_IN_PROGRESS", "上一轮仍在处理，请等待结果后再重试")
        changed = db.execute(
            update(LearningTurn)
            .where(
                LearningTurn.id == turn_id,
                LearningTurn.status == "failed",
            )
            .values(status="pending", error_code=None, error_message=None)
        )
        if not changed.rowcount:
            fail(409, "RETRY_NOT_ALLOWED", "本轮已经处理，请刷新后查看")
        old_trace = db.get(ModelTrace, turn.trace_id)
        trace = ModelTrace(
            event_id=turn.event_id,
            feature="learning.5e",
            source="live",
            model=settings.c_llm_model or settings.llm_model or "unconfigured",
            prompt_version=LEARNING_PROMPT_VERSION,
            input_summary=dict(old_trace.input_summary),
            details={"backend": settings.c_llm_backend, "retry_of": turn.trace_id},
        )
        db.add(trace)
        db.flush()
        turn.trace_id = trace.trace_id
        return turn_out(turn)


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
            "source_context": session.snapshot.get("source"),
            "chapter": session.snapshot.get("chapter"),
            "course_materials": session.snapshot.get("course_materials", []),
            "evaluation_task": {
                key: session.snapshot["template"]["quiz"][key] for key in ("stem", "options")
            },
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
    call_details = None
    guardrail_action = None
    try:
        if is_instruction_attack(turn.answer):
            raise ModelCallError("UNSAFE_LEARNING_INPUT", "作答包含修改学习规则的指令，已保存但未请求模型。")
        reply = complete_json(settings, LEARNING_PROMPT, data, LearningFeedback.model_json_schema())
        usage = reply.usage
        call_details = reply.details
        output = LearningFeedback.model_validate_json(reply.text)
        if output.evidence_event_ids != [turn.event_id]:
            raise ModelCallError("INVALID_EVIDENCE", "模型使用了不属于本轮作答的证据。")
        if contains_prompt_leak(json.dumps(output.model_dump(), ensure_ascii=False), LEARNING_PROMPT):
            raise ModelCallError("PROMPT_LEAK", "模型返回了系统指令，本轮结果已拒绝。")
        target, completed = checked_transition(turn.stage_before, output, turn.answer, quiz_correct)
        if target == "evaluate" and turn.stage_before != "evaluate":
            output.reply = (
                f"请完成下方小测“{session.snapshot['template']['quiz']['stem']}”，选择选项并说明判断依据。"
            )
            guardrail_action = "evaluation_task_alignment"
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
        call_details = exc.details
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
        if call_details:
            trace.details = {**(trace.details or {}), "model_call": call_details}
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
