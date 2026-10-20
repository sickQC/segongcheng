from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import CourseMember, KnowledgePoint
from app.models.legacy import now
from app.schemas.profile import (
    EventPage,
    LearningProfileOut,
    SnapshotComparison,
    SnapshotCreate,
    SnapshotOut,
    SnapshotPage,
)
from app.services import event_export, profile_history
from app.services.learning_events import point_matches, real_events, utc
from app.services.profile import build_profile

router = APIRouter(tags=["Learning profile and events"])


def event_window(db, course_id, start, end, knowledge_point_id):
    until = now()
    if any(value is not None and value.tzinfo is None for value in (start, end)):
        fail(422, "TIMEZONE_REQUIRED", "时间须包含时区，例如 2026-10-20T00:00:00+08:00")
    end = min(utc(end), until) if end else until
    start = utc(start) if start else end - timedelta(days=30)
    if start > end or end - start > timedelta(days=90):
        fail(422, "INVALID_TIME_WINDOW", "起止顺序须正确，查询范围最多90天")
    point = db.get(KnowledgePoint, knowledge_point_id) if knowledge_point_id else None
    if knowledge_point_id and (point is None or point.course_id != course_id):
        fail(422, "KNOWLEDGE_POINT_MISMATCH", "知识点必须属于本课程")
    return start, end, point


def target_student(db, user, course_id, student_id=None):
    course_access(db, user, course_id, edit=user.role == "teacher")
    if user.role == "student":
        if student_id is not None and student_id != user.id:
            fail(403, "STUDENT_FORBIDDEN", "仅可查询自己的学习记录")
        student_id = user.id
    if student_id is None:
        fail(422, "STUDENT_REQUIRED", "教师查询时须指定课程学生")
    member = db.scalar(
        select(CourseMember).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == student_id,
            CourseMember.role == "student",
        )
    )
    if member is None:
        fail(404, "STUDENT_NOT_FOUND", "本课程不存在该学生")
    return student_id


@router.get("/courses/{course_id}/profile", response_model=LearningProfileOut)
def my_profile(course_id: str, db: Db, user: CurrentUser, days: int = Query(30, ge=1, le=90)):
    sid = target_student(db, user, course_id)
    return build_profile(db, course_id, sid, days)


@router.get("/courses/{course_id}/students/{student_id}/profile", response_model=LearningProfileOut)
def student_profile(
    course_id: str, student_id: str, db: Db, user: Teacher, days: int = Query(30, ge=1, le=90)
):
    sid = target_student(db, user, course_id, student_id)
    return build_profile(db, course_id, sid, days)


@router.post("/courses/{course_id}/profile/snapshots", response_model=SnapshotOut)
def save_profile_snapshot(course_id: str, body: SnapshotCreate, db: Db, user: CurrentUser,
                          student_id: str | None = None):
    sid = target_student(db, user, course_id, student_id)
    row = profile_history.save_snapshot(db, course_id, sid, f"manual-{body.request_id}", body.days)
    db.commit()
    return profile_history.detail(row)


@router.get("/courses/{course_id}/profile/snapshots", response_model=SnapshotPage)
def profile_snapshots(course_id: str, db: Db, user: CurrentUser, student_id: str | None = None,
                      offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    sid = target_student(db, user, course_id, student_id)
    return profile_history.page(db, course_id, sid, offset, limit)


@router.get("/courses/{course_id}/profile/snapshots/compare", response_model=SnapshotComparison)
def compare_profile_snapshots(course_id: str, before_id: str, after_id: str, db: Db,
                              user: CurrentUser, student_id: str | None = None):
    sid = target_student(db, user, course_id, student_id)
    return profile_history.compare(
        profile_history.get_snapshot(db, course_id, sid, before_id),
        profile_history.get_snapshot(db, course_id, sid, after_id),
    )


@router.get("/courses/{course_id}/profile/snapshots/{snapshot_id}", response_model=SnapshotOut)
def profile_snapshot(course_id: str, snapshot_id: str, db: Db, user: CurrentUser,
                     student_id: str | None = None):
    sid = target_student(db, user, course_id, student_id)
    return profile_history.detail(profile_history.get_snapshot(db, course_id, sid, snapshot_id))


@router.get("/courses/{course_id}/learning-events", response_model=EventPage)
def learning_events(
    course_id: str,
    db: Db,
    user: CurrentUser,
    student_id: str | None = None,
    knowledge_point_id: str | None = None,
    verb: str | None = Query(None, max_length=40),
    start: datetime | None = None,
    end: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    sid = target_student(db, user, course_id, student_id)
    start, end, point = event_window(db, course_id, start, end, knowledge_point_id)
    rows = [
        e
        for e in reversed(real_events(db, course_id, sid, start, end))
        if (verb is None or e.verb == verb) and (point is None or point_matches(e, point))
    ]
    page = rows[offset : offset + limit]
    return dict(
        items=[
            dict(
                event_id=e.event_id,
                actor=e.actor,
                verb=e.verb,
                object=e.object,
                result=e.result,
                context=e.context,
                timestamp=utc(e.timestamp),
            )
            for e in page
        ],
        next_offset=offset + limit if len(rows) > offset + limit else None,
        window_start=start,
        window_end=end,
    )


@router.get("/courses/{course_id}/learning-events/export", response_class=Response,
            responses={200: {"content": {"text/csv": {}, "application/x-ndjson": {}}}})
def export_learning_events(course_id: str, db: Db, user: CurrentUser,
                           format: Literal["csv", "jsonl"] = "jsonl", student_id: str | None = None,
                           knowledge_point_id: str | None = None, verb: str | None = Query(None, max_length=40),
                           start: datetime | None = None, end: datetime | None = None):
    sid = target_student(db, user, course_id, student_id)
    start, end, point = event_window(db, course_id, start, end, knowledge_point_id)
    body, count = event_export.build_export(db, course_id, sid, start, end, format, verb, point)
    return Response(body, media_type="text/csv; charset=utf-8" if format == "csv" else "application/x-ndjson",
                    headers={"Content-Disposition": f'attachment; filename="learning-events.{format}"',
                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                             "X-Export-Event-Count": str(count), "X-Export-Window-Start": start.isoformat(),
                             "X-Export-Window-End": end.isoformat()})
