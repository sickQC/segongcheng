"""Baseline target prerequisite closure, topological order and auditable saved plans."""

from collections import defaultdict

from sqlalchemy import select

from app.core.errors import fail
from app.models import (
    KnowledgePoint,
    LearningEvent,
    MasteryProfile,
    PracticeExercise,
    Recommendation,
    RecommendationFeedback,
)
from app.models.legacy import now
from app.services.budgeted_recommendation import schedule
from app.services.learning_events import utc
from app.services.prerequisites import list_edges, lock_course, ordered_graph

ALGORITHM_VERSION = "prerequisite-baseline-v1"


def out(row):
    return {
        "id": row.id,
        "course_id": row.course_id,
        "student_id": row.student_id,
        "created_at": utc(row.created_at),
        **row.snapshot,
    }


def build_plan(db, course_id, student_id, target_id, threshold):
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)).all()
    by_id = {p.id: p for p in points}
    if target_id not in by_id:
        fail(422, "KNOWLEDGE_POINT_MISMATCH", "目标知识点必须属于本课程。")
    edges = list_edges(db, course_id)
    ordered = ordered_graph(points, edges)
    parents = defaultdict(set)
    for edge in edges:
        parents[edge.to_kp_id].add(edge.from_kp_id)
    closure, todo = set(), [target_id]
    while todo:
        key = todo.pop()
        if key not in closure:
            closure.add(key)
            todo.extend(parents[key])
    profiles = {
        p.knowledge_point_id: p
        for p in db.scalars(
            select(MasteryProfile).where(
                MasteryProfile.course_id == course_id, MasteryProfile.student_id == student_id
            )
        )
    }
    exercises = {
        p.knowledge_point_id: p
        for p in db.scalars(select(PracticeExercise).where(PracticeExercise.course_id == course_id))
    }
    target_mastered = target_id in profiles and profiles[target_id].mastery >= threshold
    steps, skipped, notes = [], [], []
    for key in ordered:
        if key not in closure or (target_mastered and key != target_id):
            continue
        point, profile = by_id[key], profiles.get(key)
        mastered = profile is not None and profile.mastery >= threshold
        if mastered:
            reason = f"有效综合诊断掌握度{profile.mastery:.0%}达到阈值{threshold:.0%}，本次跳过。"
        else:
            position = "目标知识点" if key == target_id else f"目标“{by_id[target_id].name}”的先修知识"
            reason = (
                f"{position}；尚无有效掌握度诊断，安排待测或待复习。"
                if profile is None
                else f"{position}；有效综合诊断掌握度{profile.mastery:.0%}低于阈值{threshold:.0%}。"
            )
        item = dict(
            knowledge_point_id=key,
            code=point.code,
            name=point.name,
            mastery=profile.mastery if profile else None,
            confidence=profile.confidence if profile else None,
            diagnosis_id=profile.report_id if profile else None,
            evidence_ids=profile.evidence_ids if profile else [],
            input_cutoff=utc(profile.input_cutoff).isoformat() if profile else None,
            reason=reason,
            reason_source="diagnosis" if profile else "prerequisite_rule",
        )
        if mastered:
            skipped.append(item)
            continue
        url = f"/courses/{course_id}?knowledge_point={key}"
        actions = [dict(kind="knowledge", id=key, title="阅读知识点定义", url=url)]
        step_notes = []
        if key in exercises:
            exercise = exercises[key]
            actions.append(dict(kind="practice", id=exercise.id, title="查看配套小练习", url=url))
        else:
            step_notes.append("教师尚未配置配套小练习；可先阅读定义，或请教师补充。")
        steps.append(
            {
                **item,
                "estimated_minutes": point.estimated_minutes
                if point.estimated_minutes is not None
                else 5 + 3 * point.difficulty + (5 if key in exercises else 0),
                "estimate_source": "teacher" if point.estimated_minutes is not None else "rule_estimate",
                "order": len(steps) + 1,
                "prerequisite_ids": sorted(parents[key]),
                "actions": actions,
                "notes": step_notes,
            }
        )
    if target_mastered:
        notes.append("目标已达到掌握阈值，本次无需安排路径；如需复习先修知识，可将其单独选为目标。")
    elif not parents[target_id]:
        notes.append("目标没有已配置的先修关系，本次仅安排目标本身；先修关系完整性需由教师确认。")
    notes.append("这是生成时的画像与先修关系快照；学习或关系更新后请重新生成，历史路径保持原样。")
    notes.append("历史入口对应的知识点若已被移除，可能无法定位；重新生成可获取当前有效内容。")
    notes.append("分钟数为教师或规则估时，并非实测耗时；未配置时按5+3×难度+配套练习5分钟估算。")
    notes.append("计划中的先修按步骤完成后才视为可继续，不会仅因推荐或接受计划就更新掌握度。")
    return dict(
        strategy="baseline",
        algorithm_version=ALGORITHM_VERSION,
        mastery_threshold=threshold,
        target_kp_id=target_id,
        target_name=by_id[target_id].name,
        status="target_mastered" if target_mastered else "ready",
        input_cutoff=now().isoformat(),
        graph_edges=[
            dict(from_kp_id=e.from_kp_id, to_kp_id=e.to_kp_id)
            for e in edges
            if e.from_kp_id in closure and e.to_kp_id in closure
        ],
        steps=steps,
        skipped=skipped,
        notes=notes,
    )


def create_recommendation(db, course_id, student_id, body, threshold):
    lock_course(db, course_id)
    existing = db.scalar(
        select(Recommendation).where(
            Recommendation.course_id == course_id,
            Recommendation.student_id == student_id,
            Recommendation.request_id == str(body.request_id),
        )
    )
    if existing:
        if (
            existing.target_kp_id != body.target_kp_id
            or existing.snapshot.get("strategy", "baseline") != body.strategy
            or existing.snapshot.get("time_budget_minutes") != body.time_budget_minutes
        ):
            fail(409, "REQUEST_CONFLICT", "请求编号已用于其他目标、策略或预算。")
        return out(existing)
    snapshot = schedule(
        build_plan(db, course_id, student_id, body.target_kp_id, threshold),
        body.strategy,
        body.time_budget_minutes,
    )
    row = Recommendation(
        course_id=course_id,
        student_id=student_id,
        request_id=str(body.request_id),
        target_kp_id=body.target_kp_id,
        snapshot=snapshot,
    )
    db.add(row)
    db.flush()
    db.add(
        LearningEvent(
            actor=student_id,
            verb="recommended",
            object={
                "type": "learning_path",
                "id": row.id,
                "kp": list(
                    dict.fromkeys([s["knowledge_point_id"] for s in snapshot["steps"]] + [body.target_kp_id])
                ),
            },
            result={
                "strategy": snapshot["strategy"],
                "step_count": len(snapshot["steps"]),
                "skipped_count": len(snapshot["skipped"]),
                "algorithm_version": snapshot["algorithm_version"],
                "estimated_minutes": snapshot["estimated_minutes"],
                "time_budget_minutes": body.time_budget_minutes,
            },
            context={"course": course_id, "source": "recommendation", "synthetic": False},
        )
    )
    db.flush()
    return out(row)


def record_feedback(db, row, choice):
    lock_course(db, row.course_id)
    existing = db.get(RecommendationFeedback, row.id)
    if existing:
        if existing.choice != choice:
            fail(409, "FEEDBACK_EXISTS", "此份推荐已记录反馈；可对新生成的计划再次反馈。")
        return existing
    feedback = RecommendationFeedback(recommendation_id=row.id, student_id=row.student_id, choice=choice)
    db.add(feedback)
    db.add(
        LearningEvent(
            actor=row.student_id,
            verb="recommendation_feedback",
            object={"type": "learning_path", "id": row.id, "kp": [row.target_kp_id]},
            result={"choice": choice, "strategy": row.snapshot["strategy"]},
            context={"course": row.course_id, "source": "recommendation_feedback", "synthetic": False},
        )
    )
    db.flush()
    return feedback


def strategy_metrics(db, course_id, student_id=None):
    query = select(Recommendation).where(Recommendation.course_id == course_id)
    if student_id is not None:
        query = query.where(Recommendation.student_id == student_id)
    rows = db.scalars(query).all()
    feedbacks = {
        f.recommendation_id: f
        for f in db.scalars(
            select(RecommendationFeedback)
            .join(Recommendation, Recommendation.id == RecommendationFeedback.recommendation_id)
            .where(
                Recommendation.course_id == course_id,
                *([Recommendation.student_id == student_id] if student_id is not None else []),
            )
        )
    }
    result = []
    for strategy in ("baseline", "budgeted"):
        plans = [r for r in rows if r.snapshot["strategy"] == strategy]
        feedback = [feedbacks[r.id] for r in plans if r.id in feedbacks]
        estimates = [
            r.snapshot["estimated_minutes"] for r in plans if r.snapshot.get("estimated_minutes") is not None
        ]
        accepted = sum(f.choice == "accepted" for f in feedback)
        result.append(
            dict(
                strategy=strategy,
                recommendation_count=len(plans),
                feedback_count=len(feedback),
                accepted_count=accepted,
                acceptance_rate=accepted / len(feedback) if feedback else None,
                estimated_path_count=len(estimates),
                average_estimated_minutes=round(sum(estimates) / len(estimates), 2) if estimates else None,
                goal_in_plan_count=sum(r.snapshot.get("goal_in_plan") is True for r in plans),
            )
        )
    return dict(
        scope="student" if student_id else "course",
        strategies=result,
        explanation="接受率=愿意采用数/已反馈数，未反馈不当拒绝；分钟数是估计值。计划包含目标不代表实际掌握；不同目标和预算的在线统计不能证明算法优劣。",
    )
