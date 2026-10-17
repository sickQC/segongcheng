"""Member C: persist answers before model work; retries never replace answers."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import fail
from app.models import Diagnosis, KnowledgePoint, LearningEvent, PracticeExercise, PracticeSubmission
from app.schemas.practice import SubmissionOut
from app.services.diagnosis import add_trace


def submission_out(db, submission):
    diagnosis = db.get(Diagnosis, submission.diagnosis_id)
    output = diagnosis.output
    attention = diagnosis.status in ("failed", "insufficient") or (
        diagnosis.status == "supported" and output is not None and output.get("mastery", 1) < 0.6
    )
    return SubmissionOut(
        **{key: getattr(submission, key) for key in SubmissionOut.model_fields if hasattr(submission, key)},
        status=diagnosis.status,
        diagnosis=output,
        error_message=diagnosis.error_message,
        needs_attention=attention,
    )


def matching_request(db, exercise_id, student_id, body, parent_id):
    previous = db.scalar(
        select(PracticeSubmission).where(
            PracticeSubmission.exercise_id == exercise_id,
            PracticeSubmission.student_id == student_id,
            PracticeSubmission.request_id == str(body.request_id),
        )
    )
    if previous is not None:
        if previous.original_answer != body.answer or previous.parent_submission_id != parent_id:
            fail(409, "REQUEST_CONFLICT", "同一请求编号已用于不同作答，请刷新后重试")
        return submission_out(db, previous)
    return None


def save_answer(sessions, settings, exercise_id, student_id, body, parent_id=None):
    """Return (saved response, new trace id or None for an idempotent repeat)."""
    try:
        with sessions.begin() as db:
            previous = matching_request(db, exercise_id, student_id, body, parent_id)
            if previous is not None:
                return previous, None
            exercise = db.get(PracticeExercise, exercise_id)
            kp = db.get(KnowledgePoint, exercise.knowledge_point_id)
            question, context = exercise.question_text, {}
            if parent_id:
                parent = db.get(PracticeSubmission, parent_id)
                if parent is None or parent.exercise_id != exercise_id or parent.student_id != student_id:
                    fail(404, "SUBMISSION_NOT_FOUND", "本人的作答记录不存在")
                diagnosis = db.get(Diagnosis, parent.diagnosis_id)
                if diagnosis.status not in ("supported", "insufficient") or not diagnosis.output:
                    fail(409, "FOLLOWUP_NOT_READY", "请等待诊断完成，失败时先重试诊断")
                question = diagnosis.output["followup_question"]
                parent_event = db.get(LearningEvent, parent.event_id)
                context = {
                    "parent_submission_id": parent.id,
                    "parent_diagnosis_id": diagnosis.id,
                    "previous_question": parent_event.object["question"],
                    "previous_answer": parent.original_answer,
                    "previous_feedback": diagnosis.output["problem_description"],
                }
                # Freeze the teaching reference that the previous diagnosis actually used.
                kp_name = parent_event.object["knowledge_point_name"]
                kp_definition = parent_event.object["knowledge_point_definition"]
            else:
                kp_name, kp_definition = kp.name, kp.definition
            event = LearningEvent(
                actor=student_id,
                verb="answered",
                object={
                    "type": "practice",
                    "id": exercise.id,
                    "kp": [kp.id],
                    "question": question,
                    "knowledge_point_name": kp_name,
                    "knowledge_point_definition": kp_definition,
                    "followup_context": context,
                },
                result={"answer": body.answer, "correct": None},
                context={"course": exercise.course_id, "source": "practice", "synthetic": False},
            )
            db.add(event)
            db.flush()
            diagnosis = Diagnosis(event_id=event.event_id, mode="live")
            db.add(diagnosis)
            db.flush()
            submission = PracticeSubmission(
                exercise_id=exercise.id,
                course_id=exercise.course_id,
                student_id=student_id,
                original_answer=body.answer,
                event_id=event.event_id,
                diagnosis_id=diagnosis.id,
                request_id=str(body.request_id),
                parent_submission_id=parent_id,
            )
            db.add(submission)
            db.flush()
            trace = add_trace(db, settings, diagnosis, event)
            result = submission_out(db, submission)
            trace_id = trace.trace_id
        # This transaction has committed before the caller schedules a model request.
        return result, trace_id
    except IntegrityError:
        # Concurrent clicks with the same request id converge on the unique DB key.
        with sessions() as db:
            previous = matching_request(db, exercise_id, student_id, body, parent_id)
            if previous is not None:
                return previous, None
        raise
