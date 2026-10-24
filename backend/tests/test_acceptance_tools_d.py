"""Read-only acceptance infrastructure: no fake readiness or unbounded remote traffic."""

from uuid import uuid4

import pytest
from scripts.audit_course_data import audit
from scripts.benchmark_read_api import benchmark, local_origin, metrics
from sqlalchemy import select
from test_evidence_diagnosis import scope  # noqa: F401
from test_foundation import foundation  # noqa: F401

from app.models import CourseQuiz, KnowledgeEdge, KnowledgePoint


def test_percentiles_and_errors_are_not_hidden():
    report = metrics([{"ok": i != 1, "ms": i} for i in range(1, 21)])
    assert report == {"requests": 20, "errors": 1, "mean_ms": 10.5, "p50_ms": 10, "p95_ms": 19, "max_ms": 20}
    with pytest.raises(ValueError):
        metrics([])


@pytest.mark.parametrize("origin", ["https://example.com", "http://user:password@localhost", "http://localhost/path", "http://localhost?token=x"])
def test_benchmark_never_sends_credentials_to_remote_or_embedded_urls(origin):
    with pytest.raises(ValueError):
        local_origin(origin)


def test_load_bounds_checked_before_login():
    for concurrency, per_endpoint in ((0, 30), (21, 30), (10, 101)):
        with pytest.raises(ValueError):
            benchmark("http://127.0.0.1:8000", "not-used", concurrency, per_endpoint)


def test_inventory_is_read_only_and_resources_remain_unknown(scope):  # noqa: F811
    app, _, _, course, _, _ = scope
    with app.state.sessions() as db:
        before = [(p.id, p.name) for p in db.scalars(select(KnowledgePoint))]
        report = audit(db, course)
        assert report["counts"]["chapters"] == 2 and report["counts"]["knowledge_points"] == 5
        assert report["checks"]["knowledge_points"]["status"] == "shortfall"
        assert report["checks"]["videos"]["status"] == "shortfall" and report["counts"]["videos"] == 0 and not report["ready"]
        assert [(p.id, p.name) for p in db.scalars(select(KnowledgePoint))] == before


def test_inventory_deduplicates_quiz_copies_without_exporting_answers(scope):  # noqa: F811
    app, _, _, course, point, _ = scope
    with app.state.sessions.begin() as db:
        question = {"id": str(uuid4()), "knowledge_point_id": point["id"], "type": "boolean",
                    "stem": "Unique stem", "options": ["yes", "no"], "correct_values": ["private answer"]}
        for _ in range(2):
            db.add(CourseQuiz(course_id=course, title="Copy", duration_minutes=10, max_attempts=1,
                              questions=[{**question, "id": str(uuid4())}]))
    with app.state.sessions() as db:
        report = audit(db, course)
        assert report["counts"]["published_question_instances"] == 2
        assert report["counts"]["unique_objective_questions"] == 1
        assert "private answer" not in str(report)


def test_inventory_reports_invalid_graph_instead_of_acceptance(scope):  # noqa: F811
    app, _, _, course, point, _ = scope
    with app.state.sessions.begin() as db:
        other = next(p for p in db.scalars(select(KnowledgePoint)) if p.id != point["id"])
        db.add_all([KnowledgeEdge(course_id=course, from_kp_id=point["id"], to_kp_id=other.id),
                    KnowledgeEdge(course_id=course, from_kp_id=other.id, to_kp_id=point["id"])])
    with app.state.sessions() as db:
        report = audit(db, course)
        assert "invalid_prerequisite_graph" in report["issues"] and not report["ready"]
