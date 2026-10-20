"""Shared read contract for real course events. Clients cannot assert grades or diagnoses."""

from datetime import timezone

from sqlalchemy import select

from app.models import LearningEvent


def utc(value):
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)


def real_events(db, course_id, student_id, start, end):
    return list(iter_real_events(db, course_id, student_id, start, end))


def iter_real_events(db, course_id, student_id, start, end, verb=None, point=None):
    # JSON course scope is filtered in SQL on both SQLite and PostgreSQL.
    statement = (select(LearningEvent)
        .where(
            LearningEvent.actor == student_id,
            LearningEvent.context["course"].as_string() == course_id,
            LearningEvent.timestamp >= start,
            LearningEvent.timestamp <= end,
        )
        .order_by(LearningEvent.timestamp, LearningEvent.event_id))
    if verb is not None:
        statement = statement.where(LearningEvent.verb == verb)
    rows = db.scalars(statement.execution_options(yield_per=100))
    try:
        for row in rows:
            if row.context.get("synthetic") is False and (point is None or point_matches(row, point)):
                yield row
    finally:
        rows.close()


def point_matches(event, point):
    keys = event.object.get("kp", [])
    return isinstance(keys, list) and (point.id in keys or point.code in keys)


def activity_kind(event):
    kind = event.object.get("type")
    if event.verb == "answered" and kind in ("assessment", "practice"):
        return "practice"
    if (event.verb, kind) in (("asked", "question"), ("responded", "learning_5e")):
        return "ask"
    # Resource producers must emit cumulative server measurements; browser claims are excluded.
    if (
        kind == "resource"
        and event.context.get("source") == "resource_tracker"
        and event.context.get("measurement") == "server"
    ):
        return {"video": "video", "doc": "read"}.get(event.object.get("resource_type"))
    return None
