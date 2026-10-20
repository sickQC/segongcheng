"""Add ten clearly marked demo learners to the existing seed course.

Run from the repository root: .venv/Scripts/python.exe scripts/seed_teacher_demo.py
The script is idempotent and never modifies an existing user or submission.
"""

import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Course,
    CourseMember,
    Diagnosis,
    KnowledgePoint,
    LearningEvent,
    PracticeExercise,
    PracticeSubmission,
    User,
)
from app.models.assessment import CourseQuiz, QuizAttempt  # noqa: E402
from app.models.legacy import now  # noqa: E402
from app.services.seed import seed_id  # noqa: E402

SEED_TAG = "teacher_dashboard_demo"
QUESTIONS = [
    ("KP-REQ-01", "功能需求描述什么？", "系统提供的行为", "系统运行速度"),
    ("KP-REQ-02", "用例的参与者是谁？", "与系统交互的外部角色", "数据库表"),
    ("KP-VAL-01", "验证主要检查什么？", "是否符合规定要求", "是否满足预期用途"),
    ("KP-TEST-01", "等价类划分还需考虑什么？", "无效输入类别", "只看正常输入"),
]


def seed(db, password):
    if len(password) < 8:
        raise ValueError("请先在 .env 设置至少 8 位的 SEED_PASSWORD")
    course_id = seed_id("course")
    if db.get(Course, course_id) is None:
        raise ValueError("请先运行项目初始化，创建预置课程")
    points = {
        row.code: row for row in db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id))
    }
    if any(code not in points for code, *_ in QUESTIONS):
        raise ValueError("预置课程缺少演示知识点，未写入任何数据")

    quiz_id = seed_id(SEED_TAG + "/quiz")
    quiz = db.get(CourseQuiz, quiz_id)
    if quiz is None:
        quiz = CourseQuiz(
            id=quiz_id, course_id=course_id, title="演示：软件工程四知识点自测",
            duration_minutes=20, max_attempts=1,
            questions=[{
                "id": seed_id(f"{SEED_TAG}/question/{code}"), "type": "single", "stem": stem,
                "options": [correct, wrong], "correct_values": [correct], "points": 25,
                "explanation": points[code].definition, "knowledge_point_id": points[code].id,
                "knowledge_point_name": points[code].name,
                "knowledge_point_definition": points[code].definition,
                "prerequisite_for": None,
            } for code, stem, correct, wrong in QUESTIONS],
        )
        db.add(quiz)
        db.flush()

    kp = points["KP-REQ-01"]
    exercise = db.scalar(select(PracticeExercise).where(PracticeExercise.knowledge_point_id == kp.id))
    if exercise is None:
        exercise = PracticeExercise(
            id=seed_id(SEED_TAG + "/practice"), course_id=course_id,
            chapter_id=kp.chapter_id, knowledge_point_id=kp.id,
            question_text="请用自己的话区分功能需求与非功能需求，并各举一例。",
        )
        db.add(exercise)
        db.flush()

    created_users = created_attempts = created_practices = 0
    for number in range(1, 11):
        username = f"demo_student_{number:02d}"
        user_id = seed_id(f"{SEED_TAG}/user/{number}")
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                id=user_id, username=username, display_name=f"演示学生 {number + 2:02d}",
                role="student", password_hash=hash_password(password),
            )
            db.add(user)
            db.flush()
            created_users += 1
        elif user.id != user_id or user.role != "student":
            raise ValueError(f"账号 {username} 已被其他用户占用，未覆盖数据")
        if db.scalar(select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user.id)) is None:
            db.add(CourseMember(course_id=course_id, user_id=user.id, role="student"))

        # Two learners have no submission so the dashboard can show missing evidence.
        if number > 8:
            continue
        submitted_at = now() - timedelta(days=number)
        attempt_id = seed_id(f"{SEED_TAG}/attempt/{number}")
        if db.get(QuizAttempt, attempt_id) is None:
            answers, results, score = {}, [], 0
            for index, (code, stem, correct, wrong) in enumerate(QUESTIONS):
                question = quiz.questions[index]
                is_correct = (number + index) % 4 < (3 if number % 3 else 2)
                selected = correct if is_correct else wrong
                answers[question["id"]] = [selected]
                score += 25 if is_correct else 0
                results.append({"question_id": question["id"], "correct": is_correct, "explanation": points[code].definition})
                event_id = seed_id(f"{SEED_TAG}/assessment/{number}/{index}")
                if db.get(LearningEvent, event_id) is None:
                    db.add(LearningEvent(
                        event_id=event_id, actor=user.id, verb="answered",
                        object={"type": "assessment", "id": question["id"], "attempt_id": attempt_id,
                                "kp": [points[code].id], "question": stem,
                                "knowledge_point_name": points[code].name,
                                "knowledge_point_definition": points[code].definition},
                        result={"answer": selected, "selected_values": [selected], "correct": is_correct,
                                "points": 25 if is_correct else 0},
                        context={"course": course_id, "source": "assessment", "synthetic": True,
                                 "seed": SEED_TAG}, timestamp=submitted_at,
                    ))
            db.add(QuizAttempt(
                id=attempt_id, quiz_id=quiz_id, course_id=course_id, student_id=user.id,
                ordinal=1, status="submitted", questions=quiz.questions, submitted_answers=answers,
                result={"attempt_id": attempt_id, "score": score, "total": 100,
                        "answers": results, "diagnosis_ids": [], "synthetic": True},
                started_at=submitted_at - timedelta(minutes=12),
                expires_at=submitted_at + timedelta(minutes=8), submitted_at=submitted_at,
            ))
            created_attempts += 1

        if number <= 7:
            submission_id = seed_id(f"{SEED_TAG}/submission/{number}")
            if db.get(PracticeSubmission, submission_id) is None:
                event_id = seed_id(f"{SEED_TAG}/practice-event/{number}")
                diagnosis_id = seed_id(f"{SEED_TAG}/diagnosis/{number}")
                answer = (
                    "功能需求是系统提供的操作，例如导出报告；非功能需求描述性能，例如两秒内响应。"
                    if number % 3 else "两者都描述系统需要实现的功能。"
                )
                db.add(LearningEvent(
                    event_id=event_id, actor=user.id, verb="answered",
                    object={"type": "practice", "id": exercise.id, "kp": [kp.id],
                            "question": exercise.question_text, "knowledge_point_name": kp.name,
                            "knowledge_point_definition": kp.definition},
                    result={"answer": answer, "correct": None},
                    context={"course": course_id, "source": "practice", "synthetic": True,
                             "seed": SEED_TAG}, timestamp=submitted_at,
                ))
                db.flush()
                weak = number % 3 == 0
                db.add(Diagnosis(
                    id=diagnosis_id, event_id=event_id, mode="demo", status="supported",
                    output={"status": "supported", "knowledge_point_id": kp.id,
                            "mastery": 0.4 if weak else 0.8, "confidence": 0.7,
                            "problem_type": "concept_confusion" if weak else "no_obvious_issue",
                            "problem_description": "混淆系统行为与质量约束。" if weak else "能够举例区分两类需求。",
                            "evidence_event_ids": [event_id], "citations": [],
                            "recommendation": "分别写一个功能需求和一个可测量的性能要求。",
                            "followup_question": "响应时间小于两秒属于哪类需求？"},
                    created_at=submitted_at,
                ))
                db.flush()
                db.add(PracticeSubmission(
                    id=submission_id, exercise_id=exercise.id, course_id=course_id,
                    student_id=user.id, original_answer=answer, event_id=event_id,
                    diagnosis_id=diagnosis_id, request_id=seed_id(f"{SEED_TAG}/request/{number}"),
                    created_at=submitted_at,
                ))
                created_practices += 1
    return created_users, created_attempts, created_practices


def main():
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        required = {"users", "course_members", "course_quizzes", "quiz_attempts", "practice_submissions"}
        if not required <= set(inspect(engine).get_table_names()):
            raise RuntimeError("数据库尚未迁移到最新版本，请先运行 alembic upgrade head")
        with Session(engine) as db, db.begin():
            counts = seed(db, settings.seed_password.get_secret_value())
        print(f"Demo seed complete: students={counts[0]}, quiz_attempts={counts[1]}, practice_submissions={counts[2]}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
