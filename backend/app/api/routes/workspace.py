"""Course workspace; the small synthetic-profile demo is explicitly scoped."""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Query, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import CourseMember, KnowledgePoint
from app.schemas.foundation import ErrorResponse
from app.schemas.workspace import (
    AttemptOut,
    ChatIn,
    ChatOut,
    CitationOut,
    DashboardOut,
    FollowupIn,
    JobOut,
    PersonalizationOut,
    QuizOut,
    ReportOut,
    ResourceContentOut,
    ResourceOut,
    ResultOut,
    StartAttemptIn,
    SubmitIn,
    TeacherStudentOut,
)
from app.services import assessment, tutor
from app.services.course_documents import markdown_document
from app.services.diagnosis import run_diagnosis
from app.services.learning_curriculum import LECTURE_SECTIONS
from app.services.personalization import DEMO_COURSE_ID, demo_history
from app.services.teacher_dashboard import dashboard as build_dashboard
from app.services.teacher_dashboard import student_report as build_student_report
from app.services.tutor import TutorError

router = APIRouter(
    prefix="/courses/{course_id}",
    tags=["Workspace · 演示与占位"],
    responses={501: {"model": ErrorResponse, "description": "接口占位，业务尚未实现"}},
)


def pending():
    fail(501, "NOT_IMPLEMENTED", "此业务尚未实现；可手动开启界面预览查看布局。")


def learner_demo(user, course_id):
    history = demo_history(user.username, course_id)
    if history is None or user.role != "student":
        pending()
    return history


def demo_answer(request, user, course_id, message, resource_id):
    history = learner_demo(user, course_id)
    settings = request.app.state.settings
    index = tutor.load_index(settings)
    titles = index.doc_titles()
    if resource_id != "kb:all" and not (resource_id.startswith("kb:") and resource_id[3:] in titles):
        fail(404, "RESOURCE_NOT_FOUND", "课程讲义不存在")
    doc_ids = None if resource_id == "kb:all" else [resource_id[3:]]
    try:
        result = tutor.ask(
            request.app.state.sessions,
            settings,
            question=message,
            mode="live",
            actor=user.id,
            course_id=course_id,
            feature="course.chat",
            learner_history=history,
            doc_ids=doc_ids,
        )
    except TutorError as exc:
        fail(503, exc.code, exc.message)
    if result["status"] == "failed":
        fail(503, "MODEL_UNAVAILABLE", "模型问答未完成，本次问题已保存，请稍后重试。")
    matched = result.get("personalization")
    return ChatOut(
        message=result["answer"],
        citations=[
            CitationOut(
                resource_id="kb:" + citation["doc_id"],
                title=citation["doc_title"] + " · " + citation["section"],
                page=None,
                seconds=None,
                section=citation["section"],
            )
            for citation in result["citations"]
        ],
        phase=None,
        personalization=(
            PersonalizationOut(
                source="synthetic",
                matched_knowledge_points=[item["knowledge_point"] for item in matched["items"]],
                similarity=matched["similarity"],
            )
            if matched
            else None
        ),
    )


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


@router.get("/resources", response_model=list[ResourceOut], summary="演示讲义列表")
def resources(course_id: str, db: Db, user: CurrentUser, request: Request):
    course_access(db, user, course_id)
    if course_id != DEMO_COURSE_ID:
        pending()
    titles = tutor.load_index(request.app.state.settings).doc_titles()
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)).all()
    return [
        ResourceOut(
            id="kb:all",
            title="全部内置讲义 · AI 问答",
            type="doc",
            url=None,
            description="浏览下方讲义原文，或让学习助手检索全部内置讲义。",
            knowledge_point_ids=[],
        ),
        *[
            ResourceOut(
                id="kb:" + doc_id,
                title=title,
                type="doc",
                url=None,
                description="可直接阅读讲义原文；学习助手将依据当前讲义回答问题。",
                knowledge_point_ids=[
                    kp.id for kp in points
                    if LECTURE_SECTIONS.get(kp.code, (None,))[0] == "kb:" + doc_id
                ],
                format="markdown",
            )
            for doc_id, title in sorted(titles.items())
        ],
    ]


@router.get("/resources/{resource_id}/content", response_model=ResourceContentOut,
            summary="读取内置讲义原文")
def resource_content(course_id: str, resource_id: str, db: Db, user: CurrentUser, request: Request):
    course_access(db, user, course_id)
    if course_id != DEMO_COURSE_ID:
        pending()
    return markdown_document(request.app.state.settings, resource_id)


@router.post("/chat", response_model=ChatOut, summary="演示课程个性化答疑；5E使用独立会话接口")
def chat(course_id: str, body: ChatIn, db: Db, user: CurrentUser, request: Request):
    course_access(db, user, course_id)
    if body.mode == "5e":
        pending()
    return demo_answer(request, user, course_id, body.message, body.resource_id)


@router.get("/quizzes", response_model=list[QuizOut], summary="可参加测验列表")
def quizzes(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    return assessment.list_quizzes(db, user, course_id)


@router.post("/attempts", response_model=AttemptOut, status_code=201, summary="开始或恢复测验")
def start_attempt(course_id: str, body: StartAttemptIn, db: Db, user: CurrentUser, request: Request):
    course_access(db, user, course_id)
    if user.role != "student":
        fail(403, "STUDENT_REQUIRED", "测验作答仅限学生")
    return assessment.start_attempt(request.app.state.sessions, course_id, user.id, body.quiz_id)


@router.post("/attempts/{attempt_id}/submit", response_model=ResultOut, summary="交卷、判分与自动诊断")
def submit(course_id: str, attempt_id: str, body: SubmitIn, db: Db, user: CurrentUser,
           request: Request, tasks: BackgroundTasks):
    course_access(db, user, course_id)
    if user.role != "student":
        fail(403, "STUDENT_REQUIRED", "测验作答仅限学生")
    result, jobs = assessment.submit_attempt(
        request.app.state.sessions, request.app.state.settings, course_id, user.id, attempt_id, body
    )
    for diagnosis_id, trace_id in jobs:
        tasks.add_task(
            run_diagnosis, request.app.state.sessions, request.app.state.settings, diagnosis_id, trace_id
        )
    return result


@router.get("/report", response_model=ReportOut, summary="演示学生学习历史；正式报告尚未实现")
def report(
    course_id: str, db: Db, user: CurrentUser, algorithm: Literal["baseline", "enhanced"] = "baseline"
):
    course_access(db, user, course_id)
    if algorithm != "baseline":
        pending()
    history = learner_demo(user, course_id)
    return ReportOut(
        history_source="synthetic",
        chapter_history=[
            {
                "title": chapter["title"],
                "accuracy": chapter["accuracy"],
                "high_error": chapter["accuracy"] < 60,
                "wrong_questions": chapter["wrong_questions"],
                "weak_knowledge_points": [
                    {key: weak[key] for key in ("name", "learning_gap", "practice")}
                    for weak in chapter["weak_knowledge_points"]
                ],
            }
            for chapter in history["chapters"]
        ],
        diagnosis=[],
        profile=[],
        recommendations=[],
        records=[],
        mistakes=[],
        timeline=[],
    )


@router.post("/report/followup", response_model=ChatOut, summary="基于演示学习历史的个性化提问")
def followup(course_id: str, body: FollowupIn, db: Db, user: CurrentUser, request: Request):
    course_access(db, user, course_id)
    return demo_answer(request, user, course_id, body.message, "kb:all")


@router.get("/dashboard", response_model=DashboardOut, summary="教师课程学情汇总")
def dashboard(course_id: str, db: Db, user: Teacher, days: int = Query(30, ge=1, le=90),
              include_demo: bool = False):
    course_access(db, user, course_id, edit=True)
    return build_dashboard(db, course_id, days, include_demo)


@router.get("/students/{student_id}/report", response_model=TeacherStudentOut, summary="教师查看学生学习证据")
def student_report(course_id: str, student_id: str, db: Db, user: Teacher,
                   days: int = Query(30, ge=1, le=90), include_demo: bool = False):
    student_access(db, user, course_id, student_id)
    return build_student_report(db, course_id, student_id, days, include_demo)


@router.post(
    "/students/{student_id}/diagnoses", response_model=JobOut, status_code=202, summary="[占位] 手动诊断任务"
)
def diagnose(course_id: str, student_id: str, db: Db, user: Teacher):
    student_access(db, user, course_id, student_id)
    pending()
