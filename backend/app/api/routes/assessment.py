from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select, update

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import Diagnosis, LearningEvent
from app.models.assessment import CourseQuiz, QuizAttempt
from app.schemas.assessment import QuizCreate
from app.services.assessment import public_attempt, publish_quiz
from app.services.diagnosis import add_trace, run_diagnosis

router = APIRouter(tags=["Member C · assessment bridge"])


@router.post("/courses/{course_id}/quizzes", status_code=201)
def create_quiz(course_id: str, body: QuizCreate, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    return publish_quiz(db, course_id, body)


def attempt_access(db, user, course_id, attempt_id):
    course_access(db, user, course_id, edit=user.role == "teacher")
    attempt = db.get(QuizAttempt, attempt_id)
    if attempt is None or attempt.course_id != course_id:
        fail(404, "ATTEMPT_NOT_FOUND", "测验记录不存在")
    if user.role != "teacher" and attempt.student_id != user.id:
        fail(404, "ATTEMPT_NOT_FOUND", "本人的测验记录不存在")
    return attempt


@router.get("/courses/{course_id}/attempts/me")
def my_attempts(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    attempts = db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.course_id == course_id, QuizAttempt.student_id == user.id)
        .order_by(QuizAttempt.started_at.desc())
        .limit(50)
    )
    return [
        {
            "id": item.id,
            "title": db.get(CourseQuiz, item.quiz_id).title,
            "status": item.status,
            "started_at": item.started_at,
        }
        for item in attempts
    ]


@router.get("/courses/{course_id}/attempts/{attempt_id}")
def get_attempt(course_id: str, attempt_id: str, db: Db, user: CurrentUser):
    item = attempt_access(db, user, course_id, attempt_id)
    return {"attempt": public_attempt(item), "status": item.status, "result": item.result}


@router.get("/courses/{course_id}/attempts/{attempt_id}/diagnoses")
def attempt_diagnoses(course_id: str, attempt_id: str, db: Db, user: CurrentUser):
    attempt = attempt_access(db, user, course_id, attempt_id)
    if attempt.status != "submitted":
        fail(409, "NOT_SUBMITTED", "提交答卷后才能查看诊断")
    rows = []
    for diagnosis_id in attempt.result["diagnosis_ids"]:
        diagnosis = db.get(Diagnosis, diagnosis_id)
        event = db.get(LearningEvent, diagnosis.event_id)
        rows.append(
            {
                "id": diagnosis.id,
                "status": diagnosis.status,
                "output": diagnosis.output,
                "error_message": diagnosis.error_message,
                "question": event.object["question"],
                "original_answer": event.result["answer"],
                "event_id": event.event_id,
            }
        )
    return rows


@router.post("/courses/{course_id}/attempts/{attempt_id}/diagnoses/{diagnosis_id}/retry", status_code=202)
def retry_diagnosis(
    course_id: str,
    attempt_id: str,
    diagnosis_id: str,
    db: Db,
    user: CurrentUser,
    request: Request,
    tasks: BackgroundTasks,
):
    attempt = attempt_access(db, user, course_id, attempt_id)
    if not attempt.result or diagnosis_id not in attempt.result["diagnosis_ids"]:
        fail(404, "DIAGNOSIS_NOT_FOUND", "本次答卷的诊断不存在")
    with request.app.state.sessions.begin() as write_db:
        claimed = write_db.execute(
            update(Diagnosis)
            .where(Diagnosis.id == diagnosis_id, Diagnosis.status == "failed")
            .values(status="pending", output=None, error_code=None, error_message=None)
        )
        if not claimed.rowcount:
            fail(409, "RETRY_NOT_ALLOWED", "仅失败的诊断可以重试")
        diagnosis = write_db.get(Diagnosis, diagnosis_id)
        trace = add_trace(
            write_db, request.app.state.settings, diagnosis, write_db.get(LearningEvent, diagnosis.event_id)
        )
        trace_id = trace.trace_id
    tasks.add_task(
        run_diagnosis, request.app.state.sessions, request.app.state.settings, diagnosis_id, trace_id
    )
    return {"diagnosis_id": diagnosis_id, "trace_id": trace_id, "status": "pending"}
