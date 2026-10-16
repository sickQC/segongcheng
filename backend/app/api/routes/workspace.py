"""课程级业务接口。

/courses/{id}/chat 已接入 M7 检索增强（app/services/tutor.py）；
其余仍是占位：先校验访问权限与入参，再明确返回 HTTP 501，绝不返回固定样例数据。
"""

from typing import Literal

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import CourseMember
from app.schemas.foundation import ErrorResponse
from app.schemas.workspace import (
    AttemptOut,
    ChatIn,
    ChatOut,
    CitationOut,
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
from app.services import tutor as tutor_service

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


@router.post("/chat", response_model=ChatOut, summary="课程答疑（M7 检索增强）")
def chat(course_id: str, body: ChatIn, db: Db, user: CurrentUser, request: Request):
    """基于课程知识库回答，并给出可核查的出处。

    证据不足时明确拒答；提问注入与作弊诱导由检索层护栏拦截。
    提问者取当前登录用户，写入 asked 学习事件与一条 trace。
    """
    course_access(db, user, course_id)
    if body.mode == "5e":
        # E1 5E 智能体尚未实现。不做静默降级，避免把普通答疑当成 5E 引导交付。
        fail(501, "NOT_IMPLEMENTED", "5E 引导智能体尚未实现；请使用课程答疑。")

    try:
        result = tutor_service.course_chat(
            db,
            request.app.state.sessions,
            request.app.state.settings,
            course_id=course_id,
            actor=user.username,
            message=body.message,
            resource_id=body.resource_id,
        )
    except tutor_service.TutorError as exc:
        status = 503 if exc.code in ("MISSING_API_KEY", "MISSING_MODEL") else 500
        fail(status, exc.code, exc.message)

    return ChatOut(
        message=result["answer"],
        citations=[CitationOut(**citation) for citation in result["citations"]],
        phase=None,
    )


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
