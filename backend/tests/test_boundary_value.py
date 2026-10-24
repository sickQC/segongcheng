"""Boundary-value content upgrades preserve teaching data and enter the real learning flow."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from test_assessment_learning_c import learning_mock
from test_foundation import foundation, sign_in  # noqa: F401
from test_practice_c import install_mock

from app.agents.learning_templates import STAGES, TEMPLATES
from app.models import KnowledgeEdge, KnowledgePoint, LearningEvent, PracticeExercise
from app.services.seed import seed_boundary_value, seed_id


def test_boundary_practice_diagnosis_lectures_and_five_stages(foundation, monkeypatch):  # noqa: F811
    app, client, _ = foundation
    headers = sign_in(client, "student01")
    cid = seed_id("course")
    base = f"/api/v1/courses/{cid}"
    outline = client.get(base + "/outline").json()
    chapter = next(ch for ch in outline["chapters"] if any(
        p["code"] == "KP-BOUND-01" for p in ch["knowledge_points"]
    ))
    point = next(p for p in chapter["knowledge_points"] if p["code"] == "KP-BOUND-01")
    assert chapter["title"] == "第二章 软件测试"
    assert point["estimated_minutes"] == 10
    topics = client.get(base + "/learning-templates").json()
    assert len(topics) == 5
    topic = next(t for t in topics if t["code"] == "KP-BOUND-01")
    assert topic["lectures"][0]["section"] == "边界值分析"
    exercises = client.get(base + "/practices").json()
    exercise = next(e for e in exercises if e["knowledge_point_id"] == point["id"])
    install_mock(monkeypatch, app)
    answer = "我只测试长度为12的密码，其他长度应该也一样。"
    response = client.post(
        base + f"/practices/{exercise['id']}/submissions", headers=headers, json={"answer": answer}
    )
    assert response.status_code == 202, response.text
    submission = response.json()
    response = client.post("/api/v1/learning-sessions", headers=headers, json={
        "course_id": cid, "knowledge_point_id": point["id"], "source_event_id": submission["event_id"],
    })
    assert response.status_code == 201, response.text
    state = response.json()
    assert state["source"]["original_answer"] == answer
    assert state["practice_available"] is True
    captured = learning_mock(monkeypatch)
    url = f"/api/v1/learning-sessions/{state['id']}"
    for stage in STAGES:
        assert client.get(url).json()["stage"] == stage
        body = {"answer": "7与21应拒绝，8、9、19、20应接受；因为8和20包含在允许范围内，字符数按整数变化。"}
        if stage == "evaluate":
            body["evaluation_choice"] = TEMPLATES["KP-BOUND-01"]["quiz"]["correct"]
        assert client.post(url + "/turns", headers=headers, json=body).status_code == 202
    assert client.get(url).json()["status"] == "completed"
    assert "边界值分析" in str(captured[0]["course_materials"])
    plan = client.post(base + "/recommendations", headers=headers, json={"target_kp_id": point["id"]})
    assert plan.status_code == 201, plan.text
    assert [p["code"] for p in plan.json()["steps"]] == ["KP-TEST-01", "KP-BOUND-01"]
    assert any(a["kind"] == "practice" for a in plan.json()["steps"][-1]["actions"])


def test_boundary_upgrade_is_repeatable_and_does_not_create_learning_events(foundation):  # noqa: F811
    app, _, _ = foundation
    with app.state.sessions.begin() as db:
        point = db.get(KnowledgePoint, seed_id("KP-BOUND-01"))
        db.execute(delete(KnowledgeEdge).where(KnowledgeEdge.to_kp_id == point.id))
        db.execute(delete(PracticeExercise).where(PracticeExercise.knowledge_point_id == point.id))
        db.delete(point)
    with app.state.sessions.begin() as db:
        first = seed_boundary_value(db)
        assert seed_boundary_value(db) == first
        assert db.scalar(select(func.count()).select_from(KnowledgePoint)) == 5
        assert db.scalar(select(func.count()).select_from(PracticeExercise)) == 1
        assert db.scalar(select(func.count()).select_from(KnowledgeEdge)) == 1
        assert db.scalar(select(func.count()).select_from(LearningEvent)) == 0


def test_boundary_upgrade_reuses_manual_code_and_preserves_teacher_edits(foundation):  # noqa: F811
    app, _, _ = foundation
    manual_id = str(uuid4())
    with app.state.sessions.begin() as db:
        point = db.get(KnowledgePoint, seed_id("KP-BOUND-01"))
        chapter_id = point.chapter_id
        db.execute(delete(KnowledgeEdge).where(KnowledgeEdge.to_kp_id == point.id))
        db.execute(delete(PracticeExercise).where(PracticeExercise.knowledge_point_id == point.id))
        db.delete(point)
        db.flush()
        db.add(KnowledgePoint(
            id=manual_id, course_id=seed_id("course"), chapter_id=chapter_id, code="KP-BOUND-01",
            name="教师的边界值课程", definition="教师自编定义", difficulty=3, bloom_level="analyze", estimated_minutes=18,
        ))
        db.flush()
        db.add(PracticeExercise(
            course_id=seed_id("course"), chapter_id=chapter_id, knowledge_point_id=manual_id,
            question_text="教师自己的边界练习",
        ))
    with app.state.sessions.begin() as db:
        result = seed_boundary_value(db)
        assert result["knowledge_point_id"] == manual_id
        assert db.get(KnowledgePoint, manual_id).definition == "教师自编定义"
        assert db.get(KnowledgePoint, manual_id).estimated_minutes == 18
        assert db.get(PracticeExercise, result["exercise_id"]).question_text == "教师自己的边界练习"
        assert db.scalar(select(func.count()).select_from(KnowledgePoint)) == 5


def test_boundary_cycle_rolls_back_new_exercise(foundation):  # noqa: F811
    app, _, _ = foundation
    point_id = seed_id("KP-BOUND-01")
    with app.state.sessions.begin() as db:
        db.execute(delete(KnowledgeEdge))
        db.execute(delete(PracticeExercise))
        db.add(KnowledgeEdge(
            course_id=seed_id("course"), from_kp_id=point_id, to_kp_id=seed_id("KP-TEST-01")
        ))
    with pytest.raises(HTTPException) as error, app.state.sessions.begin() as db:
        seed_boundary_value(db)
    assert error.value.detail["code"] == "PREREQUISITE_CYCLE"
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(PracticeExercise)) == 0
        assert db.scalar(select(func.count()).select_from(KnowledgeEdge)) == 1
