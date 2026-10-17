from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import CourseMember
from app.models.diagnosis_report import DiagnosisReport
from app.schemas.diagnosis_report import ReportCreate, ReportOut
from app.services.evidence_diagnosis import create_report, out, retry_report, run_report

router = APIRouter(tags=["Learning diagnosis"])


def accessible(db, user, course_id, report_id):
    course_access(db, user, course_id, edit=user.role == "teacher")
    row = db.get(DiagnosisReport, report_id)
    if row is None or row.course_id != course_id or (user.role != "teacher" and row.student_id != user.id):
        fail(404, "REPORT_NOT_FOUND", "本人的诊断记录不存在")
    return row


def schedule(request, tasks, course_id, student_id, body):
    row, created = create_report(
        request.app.state.sessions, request.app.state.settings, course_id, student_id, body
    )
    if created:
        tasks.add_task(
            run_report, request.app.state.sessions, request.app.state.settings, row["id"], row["trace_id"]
        )
    return row


@router.post("/courses/{course_id}/diagnosis-reports", status_code=202, response_model=ReportOut)
def diagnose(
    course_id: str, body: ReportCreate, db: Db, user: CurrentUser, request: Request, tasks: BackgroundTasks
):
    course_access(db, user, course_id)
    if user.role != "student":
        fail(403, "STUDENT_REQUIRED", "请为指定课程学生发起诊断")
    return schedule(request, tasks, course_id, user.id, body)


@router.post(
    "/courses/{course_id}/students/{student_id}/diagnosis-reports", status_code=202, response_model=ReportOut
)
def diagnose_student(
    course_id: str,
    student_id: str,
    body: ReportCreate,
    db: Db,
    user: Teacher,
    request: Request,
    tasks: BackgroundTasks,
):
    course_access(db, user, course_id, edit=True)
    if (
        db.scalar(
            select(CourseMember).where(
                CourseMember.course_id == course_id,
                CourseMember.user_id == student_id,
                CourseMember.role == "student",
            )
        )
        is None
    ):
        fail(404, "STUDENT_NOT_FOUND", "本课程不存在该学生")
    return schedule(request, tasks, course_id, student_id, body)


@router.get("/courses/{course_id}/diagnosis-reports", response_model=list[ReportOut])
def history(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id, edit=user.role == "teacher")
    query = select(DiagnosisReport).where(DiagnosisReport.course_id == course_id)
    if user.role != "teacher":
        query = query.where(DiagnosisReport.student_id == user.id)
    return [out(row) for row in db.scalars(query.order_by(DiagnosisReport.created_at.desc()).limit(20))]


@router.get("/courses/{course_id}/diagnosis-reports/{report_id}", response_model=ReportOut)
def get_report(course_id: str, report_id: str, db: Db, user: CurrentUser):
    return out(accessible(db, user, course_id, report_id))


@router.post("/courses/{course_id}/diagnosis-reports/{report_id}/retry", status_code=202)
def retry(
    course_id: str, report_id: str, db: Db, user: CurrentUser, request: Request, tasks: BackgroundTasks
):
    accessible(db, user, course_id, report_id)
    trace_id = retry_report(request.app.state.sessions, request.app.state.settings, report_id)
    tasks.add_task(run_report, request.app.state.sessions, request.app.state.settings, report_id, trace_id)
    return {"id": report_id, "trace_id": trace_id, "status": "pending"}
