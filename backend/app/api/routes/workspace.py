"""Reserved learning endpoints: validate access/input, then return explicit HTTP 501.

Implement services behind these contracts; never return fixture data from this router.
"""

from typing import Literal

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import CourseMember
from app.schemas.foundation import ErrorResponse
from app.schemas.workspace import (
    AttemptOut,
    ChatIn,
    ChatOut,
    DashboardOut,
    FollowupIn,
    JobOut,
    QuizOut,
    ReportOut,
    ResourceOut,
    ResultOut,
    StartAttemptIn,
    SubmitIn,
)

router = APIRouter(
    prefix="/courses/{course_id}",
    tags=["Workspace · 尚未实现"],
    responses={501: {"model": ErrorResponse, "description": "接口占位，业务尚未实现"}},
)


def pending():
    fail(501, "NOT_IMPLEMENTED", "此业务尚未实现；可手动开启界面预览查看布局。")


def student_access(db, user, course_id, student_id):
    course_access(db, user, course_id, edit=True)
    member = db.scalar(
        select(CourseMember).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == student_id,
            CourseMember.role == "student",
        )
    )
    if member is None:
        fail(404, "STUDENT_NOT_FOUND", "该课程中不存在此学生")


@router.get("/resources", response_model=list[ResourceOut], summary="[占位] 学习资源列表")
def resources(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    pending()


@router.post("/chat", response_model=ChatOut, summary="[占位] 课程答疑或 5E 对话")
def chat(course_id: str, body: ChatIn, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    pending()


@router.get("/quizzes", response_model=list[QuizOut], summary="[占位] 可参加测验列表")
def quizzes(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    pending()


@router.post("/attempts", response_model=AttemptOut, status_code=201, summary="[占位] 开始测验")
def start_attempt(course_id: str, body: StartAttemptIn, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    pending()


@router.post("/attempts/{attempt_id}/submit", response_model=ResultOut, summary="[占位] 交卷与判分")
def submit(course_id: str, attempt_id: str, body: SubmitIn, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    pending()


@router.get("/report", response_model=ReportOut, summary="[占位] 本人学习报告")
def report(
    course_id: str, db: Db, user: CurrentUser, algorithm: Literal["baseline", "enhanced"] = "baseline"
):
    course_access(db, user, course_id)
    pending()


@router.post("/report/followup", response_model=ChatOut, summary="[占位] 诊断追问")
def followup(course_id: str, body: FollowupIn, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    pending()


@router.get("/dashboard", response_model=DashboardOut, summary="[占位] 教师学情汇总")
def dashboard(course_id: str, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    pending()


@router.get("/students/{student_id}/report", response_model=ReportOut, summary="[占位] 学生报告")
def student_report(course_id: str, student_id: str, db: Db, user: Teacher):
    student_access(db, user, course_id, student_id)
    pending()


@router.post(
    "/students/{student_id}/diagnoses", response_model=JobOut, status_code=202, summary="[占位] 手动诊断任务"
)
def diagnose(course_id: str, student_id: str, db: Db, user: Teacher):
    student_access(db, user, course_id, student_id)
    pending()
