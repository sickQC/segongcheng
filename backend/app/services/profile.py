"""Explainable four-dimensional profile from scoped evidence, without invented activity."""

import math
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import KnowledgePoint, LearningEvent, MasteryProfile, ProfileApplication
from app.models.legacy import now, uid
from app.schemas.diagnosis_report import PointDiagnosis
from app.services.learning_events import activity_kind, point_matches, real_events, utc

RULE_VERSION = "profile-v1"
LOCAL_TIME = ZoneInfo("Asia/Shanghai")


def insert_for(db, table):
    return (sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert)(table)


def apply_report(db, report):
    """Call inside the diagnosis transaction. Upserts are atomic on SQLite and PostgreSQL.

    A report can be applied once; a later completion with an older input never replaces newer mastery.
    Missing/failed/insufficient evidence leaves previously supported mastery unchanged.
    """
    if report.status != "supported" or not report.output:
        return 0
    snapshot = report.snapshot
    if snapshot.get("student_id") != report.student_id or snapshot.get("course_id") != report.course_id:
        return 0
    try:
        cutoff = utc(datetime.fromisoformat(snapshot["cutoff"]))
        if cutoff > now():
            return 0
    except (KeyError, TypeError, ValueError):
        return 0
    claimed = db.execute(
        insert_for(db, ProfileApplication)
        .values(report_id=report.id, applied_at=now())
        .on_conflict_do_nothing(index_elements=["report_id"])
        .returning(ProfileApplication.report_id)
    ).scalar_one_or_none()
    if claimed is None:
        return 0
    frozen = {p["knowledge_point_id"]: p for p in snapshot.get("points", [])}
    order = "/".join(
        (
            cutoff.isoformat(timespec="microseconds"),
            utc(report.created_at).isoformat(timespec="microseconds"),
            report.id,
        )
    )
    applied = 0
    for raw in report.output.get("points", []):
        try:
            item = PointDiagnosis.model_validate(raw)
        except ValidationError:
            continue
        point = db.get(KnowledgePoint, item.knowledge_point_id)
        if (
            item.status != "supported"
            or item.mastery is None
            or not math.isfinite(item.mastery)
            or point is None
            or point.course_id != report.course_id
            or point.id not in frozen
            or not item.evidence_event_ids
        ):
            continue
        frozen_ids = {e["event_id"] for e in frozen[point.id].get("events", [])}
        if not set(item.evidence_event_ids) <= frozen_ids:
            continue
        evidence = db.scalars(
            select(LearningEvent).where(LearningEvent.event_id.in_(item.evidence_event_ids))
        ).all()
        if len(evidence) != len(item.evidence_event_ids) or any(
            e.actor != report.student_id
            or e.context.get("course") != report.course_id
            or e.context.get("synthetic") is not False
            or not point_matches(e, point)
            or utc(e.timestamp) > cutoff
            for e in evidence
        ):
            continue
        values = dict(
            id=uid(),
            course_id=report.course_id,
            student_id=report.student_id,
            knowledge_point_id=point.id,
            mastery=item.mastery,
            confidence=item.confidence,
            report_id=report.id,
            evidence_ids=item.evidence_event_ids,
            input_cutoff=cutoff,
            input_order=order,
            updated_at=now(),
        )
        statement = insert_for(db, MasteryProfile).values(**values)
        result = db.execute(
            statement.on_conflict_do_update(
                index_elements=["course_id", "student_id", "knowledge_point_id"],
                set_={
                    key: statement.excluded[key]
                    for key in (
                        "mastery",
                        "confidence",
                        "report_id",
                        "evidence_ids",
                        "input_cutoff",
                        "input_order",
                        "updated_at",
                    )
                },
                where=MasteryProfile.input_order < order,
            ).returning(MasteryProfile.id)
        ).scalar_one_or_none()
        applied += result is not None
    if applied:
        from app.services.profile_history import save_snapshot

        save_snapshot(db, report.course_id, report.student_id, f"diagnosis-{report.id}",
                      reason="diagnosis", report_id=report.id)
    return applied


def numeric(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def resource_measurements(events):
    """Latest cumulative snapshot per resource, never sum repeated cumulative heartbeats."""
    latest = {}
    for event in events:
        if activity_kind(event) not in ("video", "read"):
            continue
        result = event.result
        resource_id = event.object.get("id")
        if (
            not isinstance(resource_id, str)
            or not resource_id
            or not numeric(result.get("effective_seconds"), 0, 90 * 86400)
            or not numeric(result.get("coverage"), 0, 1)
            or result.get("observation_complete") is not True
            or result.get("resource_available") is not True
        ):
            continue
        latest[resource_id] = event
    return latest


def build_profile(db, course_id, student_id, days=30):
    end = now()
    start = end - timedelta(days=days)
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.course_id == course_id).order_by(KnowledgePoint.code)
    ).all()
    events = real_events(db, course_id, student_id, start, end)
    activities = [e for e in events if activity_kind(e)]
    graded = [
        e
        for e in activities
        if e.object.get("type") == "assessment" and type(e.result.get("correct")) is bool
    ]
    mastery = {
        p.knowledge_point_id: p
        for p in db.scalars(
            select(MasteryProfile).where(
                MasteryProfile.course_id == course_id, MasteryProfile.student_id == student_id
            )
        )
    }
    rows, risks, risk_ids = [], [], []
    for point in points:
        row = mastery.get(point.id)
        answers = [e for e in graded if point_matches(e, point)]
        accuracy = (
            round(sum(e.result["correct"] for e in answers) / len(answers) * 100, 1) if answers else None
        )
        rows.append(
            dict(
                knowledge_point_id=point.id,
                name=point.name,
                mastery_percent=round(row.mastery * 100, 1) if row else None,
                confidence_percent=round(row.confidence * 100, 1)
                if row and row.confidence is not None
                else None,
                report_id=row.report_id if row else None,
                evidence_ids=row.evidence_ids if row else [],
                input_cutoff=utc(row.input_cutoff) if row else None,
                updated_at=utc(row.updated_at) if row else None,
                accuracy_percent=accuracy,
                question_count=len(answers),
            )
        )
        if len(answers) >= 3 and accuracy < 50:
            risks.append(f"{point.name}：近{days}天至少3次客观作答，正确率低于50%")
            risk_ids.extend(e.event_id for e in answers)
        if len(answers) >= 3 and all(e.result["correct"] is False for e in answers[-3:]):
            risks.append(f"{point.name}：最近3次客观作答连续错误")
            risk_ids.extend(e.event_id for e in answers[-3:])
    if activities and (end - utc(activities[-1].timestamp)).total_seconds() >= 7 * 86400:
        risks.append("最近一次已记录学习活动距今至少7天；未采集的线下活动不在判断范围内")
        risk_ids.append(activities[-1].event_id)
    resources = resource_measurements(activities)
    counts = Counter(activity_kind(e) for e in activities if activity_kind(e) in ("ask", "practice"))
    total = sum(counts.values())
    # Resource counters are cumulative, whereas question/answer events are windowed.
    # Show cumulative visits separately; never mix their denominators into windowed preferences.
    for event in resources.values():
        visits = event.result.get("study_visits")
        if type(visits) is int and visits >= 0:
            counts[activity_kind(event)] += visits
    preferences = []
    for key, label in (
        ("video", "视频"),
        ("read", "阅读"),
        ("ask", "问答与5E互动"),
        ("practice", "练习与测验"),
    ):
        measured = key in ("ask", "practice") or key in counts
        count = counts[key] if measured else None
        preferences.append(
            dict(
                key=key,
                label=label,
                count=count,
                percent=round(count / total * 100, 1) if key in ("ask", "practice") and total else None,
            )
        )
    return dict(
        student_id=student_id,
        course_id=course_id,
        rule_version=RULE_VERSION,
        generated_at=end,
        window_start=start,
        window_end=end,
        knowledge=dict(
            known_points=len(mastery),
            total_points=len(points),
            points=rows,
            explanation="掌握度来自最近有效综合诊断并保留至有更新；正确率单列为近窗客观统计。未知不当作零分。",
        ),
        engagement=dict(
            active_days=len({utc(e.timestamp).astimezone(LOCAL_TIME).date() for e in activities}),
            event_count=len(activities),
            observed_resource_count=len(resources),
            effective_seconds=sum(e.result["effective_seconds"] for e in resources.values())
            if resources
            else None,
            completed_resource_percent=round(
                sum(e.result["coverage"] >= 0.9 for e in resources.values()) / len(resources) * 100, 1
            )
            if resources
            else None,
            explanation="活跃天按北京时间去重。资源显示本窗内最新累计测量，不代表本窗增量；完成比例仅统计已测资源（覆盖≥90%）。未采集则未知。",
        ),
        preference=dict(
            items=preferences,
            explanation="占比仅比较本窗内问答与练习次数，不推断固定学习风格。资源累计访问次数另列，未接入窗口访问采集前不计算四类共同占比。",
        ),
        risk=dict(
            level="attention" if risks else "normal" if len(graded) >= 3 else "unknown",
            reasons=risks,
            evidence_ids=list(dict.fromkeys(risk_ids)),
            explanation="规则：某知识点至少3次客观作答且正确率<50%，或最近3次连续错误，或至少7天无已记录活动。无触发项且不足3次作答时为未知；未采集行为不推断投入不足。",
        ),
    )


def build_report(db, course_id, student_id):
    profile = build_profile(db, course_id, student_id)
    start, end = profile["window_start"], profile["window_end"]
    events = real_events(db, course_id, student_id, start, end)
    # Reuse the existing read-only course aggregation for submitted quiz records and mistakes.
    from app.services.teacher_dashboard import student_report

    detail = student_report(db, course_id, student_id, 30, False)
    return dict(
        history_source="real",
        chapter_history=[],
        diagnosis=[],
        profile=[],
        recommendations=[],
        learning_profile=profile,
        records=[
            dict(title=a["title"], score=a["score_percent"], at=utc(a["at"]).isoformat())
            for a in detail["activities"]
            if a["kind"] == "quiz" and a.get("score_percent") is not None
        ],
        mistakes=[dict(stem=m["question"], explanation=m["explanation"]) for m in detail["mistakes"]],
        timeline=[
            dict(
                at=utc(e.timestamp).isoformat(),
                description={
                    "practice": "练习或测验作答",
                    "ask": "问答或5E互动",
                    "video": "视频学习",
                    "read": "阅读资料",
                }[activity_kind(e)],
            )
            for e in reversed(events)
            if activity_kind(e)
        ][:50],
    )
