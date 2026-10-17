"""Member C endpoints mounted by the existing main.py entry point."""

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select, update

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import (
    Chapter,
    CourseMember,
    Diagnosis,
    KnowledgePoint,
    LearningEvent,
    PracticeExercise,
    PracticeSubmission,
    User,
)
from app.schemas.practice import (
    PracticeAnswer,
    PracticeCreate,
    PracticeOut,
    PracticeProgress,
    StudentProgress,
    SubmissionOut,
)
from app.services.diagnosis import add_trace, run_diagnosis
from app.services.practice import save_answer, submission_out

router = APIRouter(tags=["Course practice"])


def exercise_access(db, user, course_id, exercise_id):
    course_access(db, user, course_id)
    exercise = db.get(PracticeExercise, exercise_id)
    if exercise is None or exercise.course_id != course_id:
        fail(404, "PRACTICE_NOT_FOUND", "本课程的小练习不存在")
    return exercise


def student_only(user):
    if user.role != "student":
        fail(403, "STUDENT_REQUIRED", "此操作仅限学生")


@router.post(
    "/courses/{course_id}/chapters/{chapter_id}/practices", status_code=201, response_model=PracticeOut
)
def create_practice(course_id: str, chapter_id: str, body: PracticeCreate, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    chapter = db.get(Chapter, chapter_id)
    kp = db.get(KnowledgePoint, body.knowledge_point_id)
    if chapter is None or chapter.course_id != course_id:
        fail(404, "CHAPTER_NOT_FOUND", "本课程的章节不存在")
    if kp is None or kp.course_id != course_id or kp.chapter_id != chapter_id:
        fail(422, "KNOWLEDGE_POINT_MISMATCH", "知识点必须属于当前课程和章节")
    if db.scalar(select(PracticeExercise).where(PracticeExercise.knowledge_point_id == kp.id)):
        fail(409, "PRACTICE_EXISTS", "每个知识点目前只能创建一道小练习")
    exercise = PracticeExercise(
        course_id=course_id, chapter_id=chapter_id, knowledge_point_id=kp.id, question_text=body.question_text
    )
    db.add(exercise)
    db.flush()
    return PracticeOut.model_validate(exercise)


@router.get("/courses/{course_id}/practices", response_model=list[PracticeOut])
def list_practices(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    return db.scalars(
        select(PracticeExercise).where(PracticeExercise.course_id == course_id).order_by(PracticeExercise.id)
    ).all()


def schedule_answer(request, tasks, exercise_id, user, body, parent_id=None):
    result, trace_id = save_answer(
        request.app.state.sessions, request.app.state.settings, exercise_id, user.id, body, parent_id
    )
    if trace_id:
        tasks.add_task(
            run_diagnosis,
            request.app.state.sessions,
            request.app.state.settings,
            result.diagnosis_id,
            trace_id,
        )
    return result


@router.post(
    "/courses/{course_id}/practices/{exercise_id}/submissions", status_code=202, response_model=SubmissionOut
)
def submit_practice(
    course_id: str,
    exercise_id: str,
    body: PracticeAnswer,
    db: Db,
    user: CurrentUser,
    request: Request,
    tasks: BackgroundTasks,
):
    exercise_access(db, user, course_id, exercise_id)
    student_only(user)
    return schedule_answer(request, tasks, exercise_id, user, body)


@router.get("/courses/{course_id}/practices/{exercise_id}/submissions/me", response_model=list[SubmissionOut])
def my_submissions(course_id: str, exercise_id: str, db: Db, user: CurrentUser):
    exercise_access(db, user, course_id, exercise_id)
    student_only(user)
    rows = db.scalars(
        select(PracticeSubmission)
        .where(PracticeSubmission.exercise_id == exercise_id, PracticeSubmission.student_id == user.id)
        .order_by(PracticeSubmission.created_at.desc(), PracticeSubmission.id)
        .limit(50)
    ).all()
    return [submission_out(db, row) for row in rows]


@router.post(
    "/courses/{course_id}/practices/{exercise_id}/submissions/{submission_id}/followups",
    status_code=202,
    response_model=SubmissionOut,
)
def answer_followup(
    course_id: str,
    exercise_id: str,
    submission_id: str,
    body: PracticeAnswer,
    db: Db,
    user: CurrentUser,
    request: Request,
    tasks: BackgroundTasks,
):
    exercise_access(db, user, course_id, exercise_id)
    student_only(user)
    return schedule_answer(request, tasks, exercise_id, user, body, submission_id)


@router.post(
    "/courses/{course_id}/practices/{exercise_id}/submissions/{submission_id}/retry",
    status_code=202,
    response_model=SubmissionOut,
)
def retry_practice(
    course_id: str,
    exercise_id: str,
    submission_id: str,
    db: Db,
    user: CurrentUser,
    request: Request,
    tasks: BackgroundTasks,
):
    exercise_access(db, user, course_id, exercise_id)
    submission = db.get(PracticeSubmission, submission_id)
    if submission is None or submission.exercise_id != exercise_id:
        fail(404, "SUBMISSION_NOT_FOUND", "作答记录不存在")
    if submission.student_id != user.id:
        course_access(db, user, course_id, edit=True)
    with request.app.state.sessions.begin() as write_db:
        claimed = write_db.execute(
            update(Diagnosis)
            .where(Diagnosis.id == submission.diagnosis_id, Diagnosis.status == "failed")
            .values(status="pending", output=None, error_code=None, error_message=None)
        )
        if not claimed.rowcount:
            fail(409, "RETRY_NOT_ALLOWED", "仅失败的诊断可以重试")
        diagnosis = write_db.get(Diagnosis, submission.diagnosis_id)
        event = write_db.get(LearningEvent, submission.event_id)
        trace = add_trace(write_db, request.app.state.settings, diagnosis, event)
        result = submission_out(write_db, write_db.get(PracticeSubmission, submission_id))
        trace_id = trace.trace_id
    tasks.add_task(
        run_diagnosis,
        request.app.state.sessions,
        request.app.state.settings,
        submission.diagnosis_id,
        trace_id,
    )
    return result


@router.get("/courses/{course_id}/practices/{exercise_id}/progress", response_model=PracticeProgress)
def practice_progress(course_id: str, exercise_id: str, db: Db, user: Teacher):
    exercise_access(db, user, course_id, exercise_id)
    course_access(db, user, course_id, edit=True)
    students = db.scalars(
        select(User)
        .join(CourseMember, CourseMember.user_id == User.id)
        .where(CourseMember.course_id == course_id, CourseMember.role == "student", User.role == "student")
        .order_by(User.username)
    ).all()
    submissions = db.scalars(
        select(PracticeSubmission)
        .where(PracticeSubmission.exercise_id == exercise_id)
        .order_by(PracticeSubmission.created_at.desc(), PracticeSubmission.id)
    ).all()
    latest = {}
    for submission in submissions:
        latest.setdefault(submission.student_id, submission)
    rows = []
    for student in students:
        item = submission_out(db, latest[student.id]) if student.id in latest else None
        rows.append(
            StudentProgress(
                student_id=student.id,
                username=student.username,
                display_name=student.display_name,
                latest_submission=item,
                needs_attention=bool(item and item.needs_attention),
            )
        )
    return PracticeProgress(
        exercise_id=exercise_id,
        student_count=len(rows),
        submitted_count=sum(row.latest_submission is not None for row in rows),
        attention_count=sum(row.needs_attention for row in rows),
        students=rows,
    )
