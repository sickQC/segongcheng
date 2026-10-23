"""Immutable server-computed snapshots. A comparison is descriptive, never a learning gain."""

from sqlalchemy import select

from app.core.errors import fail
from app.models import ProfileSnapshot
from app.models.diagnosis_report import DiagnosisReport
from app.models.legacy import now, uid
from app.schemas.profile import LearningProfileOut
from app.services.learning_events import utc


def summary(row):
    report = None
    if row.report_id:
        from sqlalchemy.orm import object_session

        session = object_session(row)
        report = session.get(DiagnosisReport, row.report_id) if session is not None else None
    return dict(id=row.id, reason=row.reason, report_id=row.report_id, days=row.days,
                created_at=utc(row.created_at), rule_version=row.payload["rule_version"],
                origin=row.payload.get("_snapshot_origin", row.reason),
                source_report_created_at=utc(report.created_at) if report else None)


def detail(row):
    return dict(**summary(row), profile=row.payload)


def save_snapshot(db, course, student, request_id, days=30, reason="manual", report_id=None, origin=None):
    from app.services.profile import build_profile, insert_for

    scope = (ProfileSnapshot.course_id == course, ProfileSnapshot.student_id == student,
             ProfileSnapshot.request_id == request_id)
    existing = db.scalar(select(ProfileSnapshot).where(*scope))
    if existing:
        if (existing.days, existing.reason, existing.report_id) != (days, reason, report_id):
            fail(409, "SNAPSHOT_REQUEST_CONFLICT", "同一请求标识不能用于不同快照参数")
        return existing
    profile = LearningProfileOut.model_validate(build_profile(db, course, student, days))
    db.execute(insert_for(db, ProfileSnapshot).values(
        id=uid(), course_id=course, student_id=student, request_id=request_id,
        days=days, reason=reason, report_id=report_id,
        payload={**profile.model_dump(mode="json"), "_snapshot_origin": origin or reason}, created_at=now(),
    ).on_conflict_do_nothing(index_elements=["course_id", "student_id", "request_id"]))
    row = db.scalar(select(ProfileSnapshot).where(*scope))
    if (row.days, row.reason, row.report_id) != (days, reason, report_id):
        fail(409, "SNAPSHOT_REQUEST_CONFLICT", "同一请求标识不能用于不同快照参数")
    return row


def get_snapshot(db, course, student, identifier):
    row = db.scalar(select(ProfileSnapshot).where(
        ProfileSnapshot.id == identifier, ProfileSnapshot.course_id == course,
        ProfileSnapshot.student_id == student,
    ))
    if row is None:
        fail(404, "SNAPSHOT_NOT_FOUND", "本课程学生不存在该画像快照")
    return row


def page(db, course, student, offset, limit):
    rows = db.scalars(select(ProfileSnapshot).where(
        ProfileSnapshot.course_id == course, ProfileSnapshot.student_id == student,
    ).order_by(ProfileSnapshot.created_at.desc(), ProfileSnapshot.id.desc())
      .offset(offset).limit(limit + 1)).all()
    return dict(items=[summary(r) for r in rows[:limit]],
                next_offset=offset + limit if len(rows) > limit else None)


def change(before, after):
    return dict(before=before, after=after, delta=round(after - before, 6)
                if before is not None and after is not None else None)


def compare(before, after):
    if before.id == after.id or utc(before.created_at) > utc(after.created_at):
        fail(422, "SNAPSHOT_ORDER", "请选择两份不同快照，并按较早、较晚的顺序比较")
    if before.days != after.days or before.payload["rule_version"] != after.payload["rule_version"]:
        fail(409, "SNAPSHOT_INCOMPATIBLE", "请选择统计窗口天数和规则版本相同的快照")
    a, b = before.payload, after.payload
    left = {p["knowledge_point_id"]: p for p in a["knowledge"]["points"]}
    right = {p["knowledge_point_id"]: p for p in b["knowledge"]["points"]}
    points = []
    for identifier in sorted(left.keys() | right.keys()):
        old, new = left.get(identifier, {}), right.get(identifier, {})
        points.append(dict(knowledge_point_id=identifier, name=new.get("name", old.get("name")),
                           mastery=change(old.get("mastery_percent"), new.get("mastery_percent")),
                           accuracy=change(old.get("accuracy_percent"), new.get("accuracy_percent"))))
    old_pref = {p["key"]: p["percent"] for p in a["preference"]["items"]}
    new_pref = {p["key"]: p["percent"] for p in b["preference"]["items"]}
    return dict(
        before=summary(before), after=summary(after), points=points,
        engagement={key: change(a["engagement"][key], b["engagement"][key]) for key in (
            "active_days", "event_count", "effective_seconds", "completed_resource_percent")},
        preference={key: change(old_pref.get(key), new_pref.get(key))
                    for key in sorted(old_pref.keys() | new_pref.keys())},
        risk_before=a["risk"]["level"], risk_after=b["risk"]["level"],
        warnings=["快照冻结保存时的四维结果；未知不按零计算，新增或删除的知识点可能无法计算差值。",
                  "滚动窗口位置不同，活跃数、正确率及偏好变化不等于学习增益。",
                  "资源时长是累计观测值之差，不等于两份快照之间的新增学习时间。",
                  "诊断后快照记录保存时的完整画像，不回填或重建旧时刻；不证明因果或教学效果。"],
    )
