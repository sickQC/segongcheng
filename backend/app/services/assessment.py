"""Persist deterministic grades and evidence, then schedule AI diagnosis separately."""

from datetime import timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import fail
from app.models import Diagnosis, KnowledgePoint, LearningEvent
from app.models.assessment import CourseQuiz, QuizAttempt
from app.models.legacy import now
from app.services.diagnosis import add_trace


def utc(value):
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)


def quiz_in_course(db, course_id, quiz_id):
    quiz = db.get(CourseQuiz, quiz_id)
    if quiz is None or quiz.course_id != course_id:
        fail(404, "QUIZ_NOT_FOUND", "本课程的测验不存在")
    return quiz


def publish_quiz(db, course_id, body):
    questions = []
    for question in body.questions:
        kp = db.get(KnowledgePoint, question.knowledge_point_id)
        if kp is None or kp.course_id != course_id:
            fail(422, "KNOWLEDGE_POINT_MISMATCH", "测验知识点必须属于本课程")
        if question.prerequisite_for:
            target = db.get(KnowledgePoint, question.prerequisite_for)
            if target is None or target.course_id != course_id:
                fail(422, "KNOWLEDGE_POINT_MISMATCH", "前置检查目标必须属于本课程")
        questions.append(
            {
                **question.model_dump(),
                "id": str(uuid4()),
                "knowledge_point_name": kp.name,
                "knowledge_point_definition": kp.definition,
            }
        )
    quiz = CourseQuiz(
        course_id=course_id,
        title=body.title,
        duration_minutes=body.duration_minutes,
        max_attempts=body.max_attempts,
        questions=questions,
    )
    db.add(quiz)
    db.flush()
    return {"id": quiz.id, "title": quiz.title, "question_count": len(questions)}


def list_quizzes(db, user, course_id):
    rows = db.scalars(
        select(CourseQuiz).where(CourseQuiz.course_id == course_id).order_by(CourseQuiz.created_at)
    )
    result = []
    for quiz in rows:
        used = db.scalar(
            select(func.count())
            .select_from(QuizAttempt)
            .where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.student_id == user.id)
        )
        active = db.scalar(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id == quiz.id,
                QuizAttempt.student_id == user.id,
                QuizAttempt.status == "in_progress",
                QuizAttempt.expires_at > now(),
            )
        )
        result.append(
            {
                "id": quiz.id,
                "title": quiz.title,
                "duration_minutes": quiz.duration_minutes,
                "attempts_remaining": max(0, quiz.max_attempts - used) + int(active is not None),
            }
        )
    return result


def public_attempt(attempt):
    return {
        "id": attempt.id,
        "quiz_id": attempt.quiz_id,
        "expires_at": utc(attempt.expires_at).isoformat(),
        "questions": [
            {key: question[key] for key in ("id", "type", "stem", "options", "points")}
            for question in attempt.questions
        ],
    }


def owned_attempt(db, course_id, student_id, attempt_id):
    attempt = db.get(QuizAttempt, attempt_id)
    if attempt is None or attempt.course_id != course_id or attempt.student_id != student_id:
        fail(404, "ATTEMPT_NOT_FOUND", "本人的测验记录不存在")
    return attempt


def start_attempt(sessions, course_id, student_id, quiz_id):
    try:
        with sessions.begin() as db:
            quiz = quiz_in_course(db, course_id, quiz_id)
            current = now()
            attempts = db.scalars(
                select(QuizAttempt)
                .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.student_id == student_id)
                .order_by(QuizAttempt.ordinal.desc())
            ).all()
            for attempt in attempts:
                if attempt.status == "in_progress" and utc(attempt.expires_at) > current:
                    return public_attempt(attempt)
                if attempt.status == "in_progress":
                    attempt.status = "expired"
            if len(attempts) >= quiz.max_attempts:
                fail(409, "ATTEMPTS_EXHAUSTED", "测验次数已用完")
            attempt = QuizAttempt(
                quiz_id=quiz.id,
                course_id=course_id,
                student_id=student_id,
                ordinal=len(attempts) + 1,
                questions=quiz.questions,
                expires_at=current + timedelta(minutes=quiz.duration_minutes),
            )
            db.add(attempt)
            db.flush()
            result = public_attempt(attempt)
        return result
    except IntegrityError:
        with sessions() as db:
            attempt = db.scalar(
                select(QuizAttempt)
                .where(
                    QuizAttempt.quiz_id == quiz_id,
                    QuizAttempt.student_id == student_id,
                    QuizAttempt.status == "in_progress",
                    QuizAttempt.expires_at > now(),
                )
                .order_by(QuizAttempt.ordinal.desc())
            )
            if attempt:
                return public_attempt(attempt)
        raise


def normalized_answers(questions, body):
    known = {question["id"]: question for question in questions}
    values = {}
    for answer in body.answers:
        if answer.question_id not in known or answer.question_id in values:
            fail(422, "INVALID_QUESTION", "答卷包含未知或重复题目")
        question = known[answer.question_id]
        selected = [value.strip() for value in answer.value]
        if any(len(value) > 2000 for value in selected) or len(set(selected)) != len(selected):
            fail(422, "INVALID_ANSWER", "作答超长或重复")
        if question["type"] != "multiple" and len(selected) > 1:
            fail(422, "INVALID_ANSWER", "该题只能提交一个答案")
        if question["type"] != "fill" and not set(selected) <= set(question["options"]):
            fail(422, "INVALID_ANSWER", "答案必须来自题目选项")
        values[answer.question_id] = sorted(selected)
    return {question_id: values.get(question_id, []) for question_id in known}


def submit_attempt(sessions, settings, course_id, student_id, attempt_id, body):
    with sessions.begin() as db:
        attempt = owned_attempt(db, course_id, student_id, attempt_id)
        submitted = normalized_answers(attempt.questions, body)
        if attempt.status == "submitted":
            if submitted != attempt.submitted_answers:
                fail(409, "ALREADY_SUBMITTED", "答卷已提交，不能修改原答案")
            return attempt.result, []
        current = now()
        if attempt.status != "in_progress" or current > utc(attempt.expires_at):
            fail(409, "ATTEMPT_EXPIRED", "服务端作答时间已结束，不能提交")
        claimed = db.execute(
            update(QuizAttempt)
            .where(QuizAttempt.id == attempt_id, QuizAttempt.status == "in_progress")
            .values(status="submitted")
        )
        if not claimed.rowcount:
            db.expire_all()
            attempt = db.get(QuizAttempt, attempt_id)
            if attempt.submitted_answers == submitted:
                return attempt.result, []
            fail(409, "ALREADY_SUBMITTED", "答卷已提交，不能修改原答案")
        score, total, results, jobs, diagnosis_ids = 0, 0, [], [], []
        for question in attempt.questions:
            selected = submitted[question["id"]]
            expected = question["correct_values"]
            correct = (
                bool(selected) and selected[0].casefold() in {value.casefold() for value in expected}
                if question["type"] == "fill"
                else set(selected) == set(expected)
            )
            total += question["points"]
            score += question["points"] if correct else 0
            results.append(
                {"question_id": question["id"], "correct": correct, "explanation": question["explanation"]}
            )
            event = LearningEvent(
                actor=student_id,
                verb="answered",
                object={
                    "type": "assessment",
                    "id": question["id"],
                    "attempt_id": attempt.id,
                    "kp": list(
                        dict.fromkeys(
                            filter(None, [question["knowledge_point_id"], question.get("prerequisite_for")])
                        )
                    ),
                    "question": question["stem"],
                    "knowledge_point_name": question["knowledge_point_name"],
                    "knowledge_point_definition": question["knowledge_point_definition"],
                    "assessment_context": {
                        "correct_values": expected,
                        "explanation": question["explanation"],
                        "correct": correct,
                        "prerequisite_for": question.get("prerequisite_for"),
                    },
                },
                result={
                    "answer": "；".join(selected),
                    "selected_values": selected,
                    "correct": correct,
                    "points": question["points"] if correct else 0,
                },
                context={"course": course_id, "source": "assessment", "synthetic": False},
            )
            db.add(event)
            db.flush()
            if not correct:
                diagnosis = Diagnosis(event_id=event.event_id, mode="live")
                db.add(diagnosis)
                db.flush()
                trace = add_trace(db, settings, diagnosis, event)
                jobs.append((diagnosis.id, trace.trace_id))
                diagnosis_ids.append(diagnosis.id)
        result = {
            "attempt_id": attempt.id,
            "score": score,
            "total": total,
            "answers": results,
            "diagnosis_ids": diagnosis_ids,
        }
        attempt.submitted_answers, attempt.result, attempt.submitted_at = submitted, result, current
    # Scores and every original answer have committed before AI jobs start.
    return result, jobs
