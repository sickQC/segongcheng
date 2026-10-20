"""Operator-only read-only inventory; never creates content or prints questions/answers."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def audit(db, course_id):
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.models import Chapter, Course, CourseQuiz, KnowledgeEdge, KnowledgePoint, PracticeExercise
    from app.services.prerequisites import ordered_graph

    if db.get(Course, course_id) is None:
        raise ValueError("Course not found")
    chapters = db.scalars(select(Chapter).where(Chapter.course_id == course_id)).all()
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)).all()
    edges = db.scalars(select(KnowledgeEdge).where(KnowledgeEdge.course_id == course_id)).all()
    quizzes = db.scalars(select(CourseQuiz).where(CourseQuiz.course_id == course_id)).all()
    practices = db.scalars(select(PracticeExercise).where(PracticeExercise.course_id == course_id)).all()
    issues = []
    chapter_ids, point_ids = {p.id for p in chapters}, {p.id for p in points}
    if any(p.chapter_id not in chapter_ids for p in points):
        issues.append("knowledge_point_chapter_scope")
    connected = {key for e in edges for key in (e.from_kp_id, e.to_kp_id)}
    try:
        ordered_graph(points, edges)
    except (HTTPException, ValueError):
        issues.append("invalid_prerequisite_graph")
    content = set()
    types = set()
    raw_questions = 0
    for quiz in quizzes:
        for question in quiz.questions:
            raw_questions += 1
            types.add(question.get("type"))
            if question.get("knowledge_point_id") not in point_ids:
                issues.append("question_knowledge_scope")
            # Canonical content hash avoids counting copies across published quizzes twice.
            material = {k: question.get(k) for k in ("type", "stem", "options")}
            material["stem"] = " ".join(str(material["stem"]).split())
            content.add(hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
    for practice in practices:
        if practice.knowledge_point_id not in point_ids or practice.chapter_id not in chapter_ids:
            issues.append("practice_scope")
    counts = {"chapters": len(chapters), "knowledge_points": len(points), "prerequisites": len(edges),
              "unique_objective_questions": len(content), "published_question_instances": raw_questions,
              "practice_exercises": len(practices), "videos": None, "documents": None}
    targets = {"chapters": 2, "knowledge_points": 30, "prerequisites": 40,
               "unique_objective_questions": 100, "videos": 10, "documents": 10}
    checks = {key: {"count": counts[key], "minimum": minimum,
                    "status": "unknown" if counts[key] is None else "passed" if counts[key] >= minimum else "shortfall"}
              for key, minimum in targets.items()}
    return {"version": "course-inventory-v1", "course_id": course_id, "counts": counts, "checks": checks,
            "isolated_point_ids": sorted(point_ids - connected), "covered_objective_types": sorted(t for t in types if t),
            "missing_objective_types": sorted({"single", "multiple", "boolean", "fill"} - types),
            "issues": sorted(set(issues)), "ready": not issues and all(c["status"] == "passed" for c in checks.values())
            and {"single", "multiple", "boolean", "fill"} <= types,
            "limitations": "Counts only; no question answers or content quality claim. Resource tables are not implemented, so video/document counts remain unknown. Practice questions reported separately; unique objective stems/types/options deduplicated across quizzes. Operator tool, not a student-facing export."}


def main():
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    from app.core.config import Settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/ci/course-inventory.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    url = make_url(Settings().database_url)
    if url.get_backend_name() == "sqlite":
        path = Path(url.database).resolve()
        if not path.is_file():
            raise SystemExit("Existing database required; no database was created")
        url = url.set(database=f"file:{path.as_posix()}", query={"mode": "ro", "uri": "true"})
    engine = create_engine(url)
    try:
        with engine.connect() as connection, connection.begin():
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            with Session(bind=connection) as db:
                report = audit(db, args.course_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ready": report["ready"], "counts": report["counts"]}, ensure_ascii=False))
    finally:
        engine.dispose()
    raise SystemExit(1 if args.strict and not report["ready"] else 0)


if __name__ == "__main__":
    main()
