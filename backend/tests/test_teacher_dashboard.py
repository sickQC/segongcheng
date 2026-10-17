import sys
from pathlib import Path

from test_foundation import PASSWORD, course_id, foundation, sign_in  # noqa: F401
from app.schemas.diagnosis_report import ReportCreate
from app.services.evidence_diagnosis import collect_snapshot

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.seed_teacher_demo import seed  # noqa: E402


def test_demo_seed_and_teacher_dashboard_keep_sources_separate(foundation):  # noqa: F811
    app, client, _ = foundation
    with app.state.sessions.begin() as db:
        assert seed(db, PASSWORD) == (10, 8, 7)
    with app.state.sessions.begin() as db:
        assert seed(db, PASSWORD) == (0, 0, 0)

    sign_in(client)
    cid = course_id(client)
    base = f"/api/v1/courses/{cid}"
    real = client.get(base + "/dashboard").json()
    assert real["student_count"] == 12
    assert real["quiz_count"] == real["practice_count"] == real["simulated_record_count"] == 0
    assert all(row["accuracy_percent"] is None for row in real["students"])
    demo = client.get(base + "/dashboard?include_demo=true").json()
    assert demo["student_count"] == 12
    assert (demo["active_count"], demo["quiz_count"], demo["practice_count"]) == (8, 8, 7)
    assert demo["simulated_record_count"] == 15
    assert sum(point["question_count"] for point in demo["points"]) == 32
    assert sum(chapter["question_count"] for chapter in demo["chapters"]) == 32
    learner = next(row for row in demo["students"] if row["username"] == "demo_student_01")
    detail = client.get(base + f"/students/{learner['id']}/report?include_demo=true").json()
    assert detail["simulated_record_count"] == 2
    assert {item["kind"] for item in detail["activities"]} == {"quiz", "practice"}
    assert sum(chapter["question_count"] for chapter in detail["chapters"]) == 4
    assert all(item["simulated"] for item in detail["activities"])
    assert any(item["answer"] for item in detail["activities"] if item["kind"] == "practice")
    assert detail["mistakes"] and all(item["simulated"] for item in detail["mistakes"])
    with app.state.sessions() as db:
        snapshot = collect_snapshot(
            db, cid, learner["id"],
            ReportCreate(knowledge_point_ids=[demo["points"][0]["knowledge_point_id"]], days=30),
        )
    assert snapshot["points"][0]["events"] == []
    no_data = next(row for row in demo["students"] if row["username"] == "demo_student_10")
    assert no_data["accuracy_percent"] is None and no_data["question_count"] == 0

    practice = next(row for row in client.get(base + "/practices").json()
                    if row["knowledge_point_id"] == demo["points"][0]["knowledge_point_id"])
    progress = client.get(base + f"/practices/{practice['id']}/progress").json()
    demo_progress = next(row for row in progress["students"] if row["username"] == "demo_student_01")
    assert demo_progress["latest_submission"]["synthetic"] is True

    sign_in(client, "student01")
    assert client.get(base + "/dashboard?include_demo=true").status_code == 403
    assert client.get(base + f"/students/{learner['id']}/report").status_code == 403
    sign_in(client, "otherteacher")
    assert client.get(base + "/dashboard").status_code == 403
