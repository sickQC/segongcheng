from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select

from app.agents.learning_templates import TEMPLATES
from app.api.deps import CurrentUser, Db, course_access
from app.core.errors import fail
from app.models import KnowledgePoint
from app.models.learning_session import LearningSession, LearningTurn
from app.schemas.learning_session import LearningAnswer, SessionCreate
from app.services.learning_session import create_session, run_turn, save_turn, session_out, turn_out

router = APIRouter(tags=["Member C · 5E learning"])


def accessible_session(db, user, session_id, write=False):
    session = db.get(LearningSession, session_id)
    if session is None:
        fail(404, "SESSION_NOT_FOUND", "学习会话不存在")
    course_access(db, user, session.course_id, edit=user.role == "teacher")
    if session.student_id != user.id and (write or user.role != "teacher"):
        fail(404, "SESSION_NOT_FOUND", "本人的学习会话不存在")
    return session


@router.get("/courses/{course_id}/learning-templates")
def templates(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id))
    return [
        {"knowledge_point_id": kp.id, "code": kp.code, "name": kp.name}
        for kp in points
        if kp.code in TEMPLATES
    ]


@router.get("/courses/{course_id}/learning-sessions")
def list_sessions(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    rows = db.scalars(
        select(LearningSession)
        .where(LearningSession.course_id == course_id, LearningSession.student_id == user.id)
        .order_by(LearningSession.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": row.id,
            "knowledge_point_name": row.snapshot["name"],
            "stage": row.stage,
            "status": row.status,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/learning-sessions", status_code=201)
def start_session(body: SessionCreate, db: Db, user: CurrentUser, request: Request):
    course_access(db, user, body.course_id)
    if user.role != "student":
        fail(403, "STUDENT_REQUIRED", "学习会话由学生开始")
    return create_session(request.app.state.sessions, user.id, body)


@router.get("/learning-sessions/{session_id}")
def get_session(session_id: str, db: Db, user: CurrentUser):
    return session_out(db, accessible_session(db, user, session_id))


@router.post("/learning-sessions/{session_id}/turns", status_code=202)
def answer_turn(
    session_id: str,
    body: LearningAnswer,
    db: Db,
    user: CurrentUser,
    request: Request,
    tasks: BackgroundTasks,
):
    accessible_session(db, user, session_id, write=True)
    turn, created = save_turn(
        request.app.state.sessions, request.app.state.settings, session_id, user.id, body
    )
    if created:
        tasks.add_task(run_turn, request.app.state.sessions, request.app.state.settings, turn["id"])
    return turn


@router.get("/learning-sessions/{session_id}/turns/{turn_id}")
def get_turn(session_id: str, turn_id: str, db: Db, user: CurrentUser):
    accessible_session(db, user, session_id)
    turn = db.get(LearningTurn, turn_id)
    if turn is None or turn.session_id != session_id:
        fail(404, "TURN_NOT_FOUND", "本会话的作答不存在")
    return turn_out(turn)
