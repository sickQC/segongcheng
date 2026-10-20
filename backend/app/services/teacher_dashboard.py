"""Small, evidence-based course dashboard; no stored or invented mastery score."""

from collections import defaultdict
from datetime import timedelta, timezone

from sqlalchemy import select

from app.models import (
    Chapter,
    CourseMember,
    Diagnosis,
    KnowledgePoint,
    LearningEvent,
    PracticeExercise,
    PracticeSubmission,
    User,
)
from app.models.assessment import CourseQuiz, QuizAttempt
from app.models.diagnosis_report import DiagnosisReport
from app.models.legacy import now


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _percent(correct, total):
    return round(correct * 100 / total, 1) if total else None


def _point_rows(counts, points, chapters):
    return [
        {
            "knowledge_point_id": kp.id,
            "name": kp.name,
            "chapter": chapters[kp.chapter_id].title,
            "correct_count": counts[kp.id][0],
            "question_count": counts[kp.id][1],
            "accuracy_percent": _percent(*counts[kp.id]),
        }
        for kp in points
    ]


def _chapter_rows(counts, points, chapters):
    totals = defaultdict(lambda: [0, 0])
    for kp in points:
        totals[kp.chapter_id][0] += counts[kp.id][0]
        totals[kp.chapter_id][1] += counts[kp.id][1]
    return [
        {
            "chapter_id": chapter.id, "name": chapter.title,
            "correct_count": totals[chapter.id][0], "question_count": totals[chapter.id][1],
            "accuracy_percent": _percent(*totals[chapter.id]),
        }
        for chapter in sorted(chapters.values(), key=lambda row: (row.sort_order, row.id))
    ]


def _collect(db, course_id, days, include_demo):
    cutoff = now() - timedelta(days=days)
    students = db.scalars(
        select(User)
        .join(CourseMember, CourseMember.user_id == User.id)
        .where(CourseMember.course_id == course_id, CourseMember.role == "student", User.role == "student")
        .order_by(User.username)
    ).all()
    ids = [student.id for student in students]
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.course_id == course_id).order_by(KnowledgePoint.code)
    ).all()
    chapters = {row.id: row for row in db.scalars(select(Chapter).where(Chapter.course_id == course_id))}
    quizzes = {row.id: row for row in db.scalars(select(CourseQuiz).where(CourseQuiz.course_id == course_id))}
    exercises = {row.id: row for row in db.scalars(select(PracticeExercise).where(PracticeExercise.course_id == course_id))}
    if not ids:
        return students, points, chapters, {}, [], [], [], {}, {}

    events = db.scalars(
        select(LearningEvent).where(LearningEvent.actor.in_(ids), LearningEvent.timestamp >= cutoff)
    ).all()
    events = [
        event for event in events
        if event.context.get("course") == course_id
        and (include_demo or not event.context.get("synthetic", False))
    ]
    event_by_id = {event.event_id: event for event in events}
    assessments = [
        event for event in events
        if event.object.get("type") == "assessment" and type(event.result.get("correct")) is bool
    ]
    attempts = db.scalars(
        select(QuizAttempt).where(
            QuizAttempt.course_id == course_id,
            QuizAttempt.student_id.in_(ids),
            QuizAttempt.status == "submitted",
            QuizAttempt.submitted_at >= cutoff,
        )
    ).all()
    attempts = [row for row in attempts if include_demo or not (row.result or {}).get("synthetic", False)]
    submissions = db.scalars(
        select(PracticeSubmission).where(
            PracticeSubmission.course_id == course_id,
            PracticeSubmission.student_id.in_(ids),
            PracticeSubmission.created_at >= cutoff,
        )
    ).all()
    submissions = [row for row in submissions if row.event_id in event_by_id and row.exercise_id in exercises]
    diagnoses = {
        row.id: row for row in db.scalars(
            select(Diagnosis).where(Diagnosis.id.in_([submission.diagnosis_id for submission in submissions]))
        )
    } if submissions else {}
    reports = db.scalars(
        select(DiagnosisReport).where(
            DiagnosisReport.course_id == course_id,
            DiagnosisReport.student_id.in_(ids),
            DiagnosisReport.created_at >= cutoff,
        ).order_by(DiagnosisReport.created_at.desc())
    ).all()
    latest_reports = {}
    for report in reports:
        latest_reports.setdefault(report.student_id, report)
    return students, points, chapters, quizzes, assessments, attempts, submissions, diagnoses, (event_by_id, exercises, latest_reports)


def _student_data(student, points, chapters, quizzes, assessments, attempts, submissions, diagnoses, extra, days):
    event_by_id, exercises, latest_reports = extra
    graded = [event for event in assessments if event.actor == student.id]
    quiz_rows = [row for row in attempts if row.student_id == student.id]
    practice_rows = [row for row in submissions if row.student_id == student.id]
    point_counts = defaultdict(lambda: [0, 0])
    for event in graded:
        point_ids = event.object.get("kp") or []
        if point_ids:
            count = point_counts[point_ids[0]]
            count[0] += int(event.result["correct"])
            count[1] += 1
    point_rows = _point_rows(point_counts, points, chapters)
    correct = sum(event.result["correct"] for event in graded)
    reasons = []
    if not quiz_rows and not practice_rows:
        reasons.append(f"近{days}天无练习或测验提交")
    if any(row["question_count"] >= 2 and row["accuracy_percent"] < 50 for row in point_rows):
        reasons.append("某知识点测验正确率偏低")
    if any(diagnoses[row.diagnosis_id].status in ("failed", "insufficient") for row in practice_rows):
        reasons.append("练习诊断需教师查看")
    activities = []
    mistakes = []
    event_for_question = {
        (event.object.get("attempt_id"), event.object.get("id")): event.event_id for event in graded
    }
    for row in quiz_rows:
        result = row.result or {}
        total = result.get("total") or 0
        activities.append({
            "kind": "quiz", "title": quizzes[row.quiz_id].title if row.quiz_id in quizzes else "课程测验",
            "at": row.submitted_at, "simulated": bool(result.get("synthetic")),
            "score_percent": _percent(result.get("score", 0), total),
            "evidence_id": row.id,
        })
        question_by_id = {question["id"]: question for question in row.questions}
        for answer in result.get("answers", []):
            if answer.get("correct") is not False or answer.get("question_id") not in question_by_id:
                continue
            question_id = answer["question_id"]
            question = question_by_id[question_id]
            mistakes.append({
                "question": question["stem"],
                "original_answer": "；".join((row.submitted_answers or {}).get(question_id, [])) or "未作答",
                "explanation": answer.get("explanation", ""), "at": row.submitted_at,
                "simulated": bool(result.get("synthetic")),
                "evidence_id": event_for_question.get((row.id, question_id)),
            })
    for row in practice_rows:
        event = event_by_id[row.event_id]
        diagnosis = diagnoses[row.diagnosis_id]
        output = diagnosis.output or {}
        activities.append({
            "kind": "practice", "title": exercises[row.exercise_id].question_text,
            "at": row.created_at, "simulated": bool(event.context.get("synthetic")),
            "answer": row.original_answer,
            "diagnosis": output.get("problem_description") or diagnosis.error_message or "诊断中",
            "recommendation": output.get("recommendation"), "evidence_id": row.event_id,
        })
    activities.sort(key=lambda item: _utc(item["at"]), reverse=True)
    mistakes.sort(key=lambda item: _utc(item["at"]), reverse=True)
    report = latest_reports.get(student.id)
    latest_report = None if report is None else {
        "id": report.id, "status": report.status, "created_at": report.created_at,
        "points": (report.output or {}).get("points", []),
    }
    simulated = sum(item["simulated"] for item in activities)
    summary = {
        "id": student.id, "name": student.display_name, "username": student.username,
        "quiz_count": len(quiz_rows), "practice_count": len(practice_rows),
        "correct_count": correct, "question_count": len(graded),
        "accuracy_percent": _percent(correct, len(graded)), "attention_reasons": reasons,
        "last_activity_at": activities[0]["at"] if activities else None,
        "simulated_record_count": simulated,
    }
    detail = {
        "student_id": student.id, "name": student.display_name, "username": student.username,
        "days": days, "correct_count": correct, "question_count": len(graded),
        "accuracy_percent": summary["accuracy_percent"],
        "chapters": _chapter_rows(point_counts, points, chapters), "points": point_rows,
        "activities": activities[:30], "mistakes": mistakes[:30], "attention_reasons": reasons,
        "simulated_record_count": simulated, "latest_report": latest_report,
    }
    return summary, detail


def dashboard(db, course_id, days, include_demo):
    students, points, chapters, quizzes, assessments, attempts, submissions, diagnoses, extra = _collect(
        db, course_id, days, include_demo
    )
    if not students:
        extra = ({}, {}, {})
    rows = [
        _student_data(student, points, chapters, quizzes, assessments, attempts, submissions, diagnoses, extra, days)[0]
        for student in students
    ]
    counts = defaultdict(lambda: [0, 0])
    for event in assessments:
        point_ids = event.object.get("kp") or []
        if point_ids:
            counts[point_ids[0]][0] += int(event.result["correct"])
            counts[point_ids[0]][1] += 1
    scores = [
        _percent((row.result or {}).get("score", 0), (row.result or {}).get("total", 0))
        for row in attempts
    ]
    valid_scores = [score for score in scores if score is not None]
    return {
        "days": days, "include_demo": include_demo, "student_count": len(students),
        "active_count": sum(row["quiz_count"] + row["practice_count"] > 0 for row in rows),
        "quiz_count": len(attempts), "practice_count": len(submissions),
        "average_quiz_percent": round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None,
        "simulated_record_count": sum(row["simulated_record_count"] for row in rows),
        "chapters": _chapter_rows(counts, points, chapters),
        "points": _point_rows(counts, points, chapters), "students": rows,
    }


def student_report(db, course_id, student_id, days, include_demo):
    students, points, chapters, quizzes, assessments, attempts, submissions, diagnoses, extra = _collect(
        db, course_id, days, include_demo
    )
    student = next(row for row in students if row.id == student_id)
    return _student_data(student, points, chapters, quizzes, assessments, attempts, submissions, diagnoses, extra, days)[1]
