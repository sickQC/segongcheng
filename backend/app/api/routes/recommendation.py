from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.api.routes.profile import target_student
from app.core.errors import fail
from app.models import KnowledgeEdge, KnowledgePoint, Recommendation, RecommendationFeedback
from app.schemas.foundation import KpOut
from app.schemas.recommendation import (
    EdgeCreate,
    EdgeOut,
    FeedbackCreate,
    FeedbackOut,
    RecommendationCreate,
    RecommendationMetrics,
    RecommendationOut,
    StudyTimeUpdate,
)
from app.services.prerequisites import add_edge, list_edges, lock_course
from app.services.recommendation import create_recommendation, out, record_feedback, strategy_metrics

router = APIRouter(tags=["Prerequisites and recommendation"])


def accessible(db, user, course_id, recommendation_id):
    course_access(db, user, course_id, edit=user.role == "teacher")
    row = db.get(Recommendation, recommendation_id)
    if row is None or row.course_id != course_id or (user.role != "teacher" and row.student_id != user.id):
        fail(404, "RECOMMENDATION_NOT_FOUND", "本人的推荐记录不存在。")
    target_student(db, user, course_id, row.student_id)
    return row


@router.patch("/courses/{course_id}/knowledge-points/{point_id}/study-time", response_model=KpOut)
def set_study_time(course_id: str, point_id: str, body: StudyTimeUpdate, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    lock_course(db, course_id)
    point = db.get(KnowledgePoint, point_id)
    if point is None or point.course_id != course_id:
        fail(422, "KNOWLEDGE_POINT_MISMATCH", "知识点必须属于本课程。")
    point.estimated_minutes = body.estimated_minutes
    db.flush()
    return point


@router.get("/courses/{course_id}/recommendation-metrics", response_model=RecommendationMetrics)
def metrics(course_id: str, db: Db, user: CurrentUser):
    if user.role == "teacher":
        course_access(db, user, course_id, edit=True)
        return strategy_metrics(db, course_id)
    return strategy_metrics(db, course_id, target_student(db, user, course_id))


@router.get(
    "/courses/{course_id}/recommendations/{recommendation_id}/feedback", response_model=FeedbackOut | None
)
def get_feedback(course_id: str, recommendation_id: str, db: Db, user: CurrentUser):
    row = accessible(db, user, course_id, recommendation_id)
    return db.get(RecommendationFeedback, row.id)


@router.post("/courses/{course_id}/recommendations/{recommendation_id}/feedback", response_model=FeedbackOut)
def feedback(course_id: str, recommendation_id: str, body: FeedbackCreate, db: Db, user: CurrentUser):
    row = accessible(db, user, course_id, recommendation_id)
    if user.role != "student":
        fail(403, "STUDENT_REQUIRED", "教师不能代学生接受或拒绝推荐。")
    return record_feedback(db, row, body.choice)


@router.get("/courses/{course_id}/prerequisites", response_model=list[EdgeOut])
def prerequisites(course_id: str, db: Db, user: CurrentUser):
    course_access(db, user, course_id)
    return list_edges(db, course_id)


@router.post("/courses/{course_id}/prerequisites", response_model=EdgeOut, status_code=201)
def create_edge(course_id: str, body: EdgeCreate, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    return add_edge(db, course_id, body)


@router.delete("/courses/{course_id}/prerequisites/{edge_id}", status_code=204)
def delete_edge(course_id: str, edge_id: str, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    lock_course(db, course_id)
    row = db.get(KnowledgeEdge, edge_id)
    if row is None or row.course_id != course_id:
        fail(404, "PREREQUISITE_NOT_FOUND", "本课程的先修关系不存在。")
    db.delete(row)
    return Response(status_code=204)


@router.post("/courses/{course_id}/recommendations", response_model=RecommendationOut, status_code=201)
def recommend(course_id: str, body: RecommendationCreate, db: Db, user: CurrentUser, request: Request):
    sid = target_student(db, user, course_id)
    return create_recommendation(db, course_id, sid, body, request.app.state.settings.mastery_threshold)


@router.get("/courses/{course_id}/recommendations", response_model=list[RecommendationOut])
def history(course_id: str, db: Db, user: CurrentUser, limit: int = Query(20, ge=1, le=100)):
    sid = target_student(db, user, course_id)
    rows = db.scalars(
        select(Recommendation)
        .where(
            Recommendation.course_id == course_id,
            Recommendation.student_id == sid,
        )
        .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
        .limit(limit)
    )
    return [out(row) for row in rows]


@router.get(
    "/courses/{course_id}/students/{student_id}/recommendations", response_model=list[RecommendationOut]
)
def student_history(
    course_id: str, student_id: str, db: Db, user: Teacher, limit: int = Query(20, ge=1, le=100)
):
    sid = target_student(db, user, course_id, student_id)
    return [
        out(row)
        for row in db.scalars(
            select(Recommendation)
            .where(
                Recommendation.course_id == course_id,
                Recommendation.student_id == sid,
            )
            .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
            .limit(limit)
        )
    ]


@router.get("/courses/{course_id}/recommendations/{recommendation_id}", response_model=RecommendationOut)
def get_recommendation(course_id: str, recommendation_id: str, db: Db, user: CurrentUser):
    return out(accessible(db, user, course_id, recommendation_id))
