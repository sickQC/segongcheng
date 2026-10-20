"""Submitted work -> targeted 5E -> durable evidence, with ownership boundaries."""
# ruff: noqa: F811 -- imported pytest fixtures share their injection names

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_assessment_learning_c import (  # noqa: F401
    context,
    foundation,
    learning_mock,
    published,
    start_quiz,
)
from test_foundation import sign_in
from test_practice_c import install_mock

from app.models import Diagnosis, LearningEvent
from app.schemas.diagnosis_report import ReportCreate
from app.services.evidence_diagnosis import collect_snapshot


def diagnosed_quiz(context, monkeypatch):
    app, client, cid, points = context
    quiz = published(context)
    install_mock(monkeypatch, app)
    headers, base, attempt = start_quiz(context, quiz)
    result = client.post(base + f"/attempts/{attempt['id']}/submit", headers=headers, json={"answers": []})
    assert result.status_code == 200, result.text
    rows = client.get(base + f"/attempts/{attempt['id']}/diagnoses").json()
    assert rows[0]["five_e_available"] is True
    return headers, attempt, result.json(), rows


def test_targeted_quiz_keeps_context_and_returns_evidence(context, monkeypatch):
    app, client, cid, points = context
    headers, attempt, result, rows = diagnosed_quiz(context, monkeypatch)
    point = points["KP-VAL-01"]["id"]
    body = {
        "course_id": cid,
        "knowledge_point_id": point,
        "source_event_id": rows[0]["event_id"],
        "request_id": str(uuid4()),
    }
    response = client.post("/api/v1/learning-sessions", headers=headers, json=body)
    assert response.status_code == 201, response.text
    state = response.json()
    assert state["source"]["attempt_id"] == attempt["id"]
    assert state["source"]["question"] == rows[0]["question"]
    assert state["source"]["options"] == attempt["questions"][0]["options"]
    assert "correct_values" not in str(state["source"])
    assert state["source"]["diagnosis"]["problem_description"] == rows[0]["output"]["problem_description"]
    assert "当时" in state["task"]
    assert client.post("/api/v1/learning-sessions", headers=headers, json=body).json()["id"] == state["id"]
    assert (
        client.post(
            "/api/v1/learning-sessions",
            headers=headers,
            json={**body, "source_event_id": rows[1]["event_id"]},
        ).status_code
        == 409
    )
    captured = learning_mock(monkeypatch)
    url = f"/api/v1/learning-sessions/{state['id']}"
    for stage in ("engage", "explore", "explain", "elaborate", "evaluate"):
        answer = {"answer": "我之前混淆了规格与实际需要，现在会先说明判断依据。"}
        if stage == "evaluate":
            answer["evaluation_choice"] = "B"
        assert client.post(url + "/turns", headers=headers, json=answer).status_code == 202
        if stage == "elaborate":
            evaluating = client.get(url).json()
            assert evaluating["evaluation"]["stem"] in evaluating["turns"][-1]["output"]["reply"]
            assert evaluating["turns"][-1]["output"]["guardrail_action"] == "evaluation_task_alignment"
    final = client.get(url).json()
    assert final["status"] == "completed"
    assert all(item["source_context"] == state["source"] for item in captured)
    assert all(
        item["evaluation_task"]["options"] and "correct" not in item["evaluation_task"] for item in captured
    )
    assert client.get(f"/api/v1/courses/{cid}/attempts/{attempt['id']}").json()["result"] == result
    history = client.get(f"/api/v1/courses/{cid}/learning-sessions").json()[0]
    assert history["status"] == "completed" and history["source"] == state["source"]
    assert datetime.fromisoformat(history["updated_at"]).utcoffset() == timedelta(0)
    with app.state.sessions() as db:
        original = db.get(LearningEvent, rows[0]["event_id"])
        snapshot = collect_snapshot(db, cid, original.actor, ReportCreate(knowledge_point_ids=[point]))
        events = snapshot["points"][0]["events"]
        dialogue = [e for e in events if e["source"] == "dialogue"]
        assert len(dialogue) == 5 and all(e["question"] for e in dialogue)
        assert rows[0]["event_id"] in {e["event_id"] for e in events}


@pytest.mark.parametrize(
    "invalid", ["other_student", "wrong_point", "pending", "failed", "synthetic", "unknown"]
)
def test_source_is_owned_matching_real_diagnosed_work(context, monkeypatch, invalid):
    app, client, cid, points = context
    headers, _, _, rows = diagnosed_quiz(context, monkeypatch)
    body = {
        "course_id": cid,
        "knowledge_point_id": points["KP-VAL-01"]["id"],
        "source_event_id": rows[0]["event_id"],
    }
    expected = 422
    if invalid == "other_student":
        headers = sign_in(client, "student02")
        expected = 404
    elif invalid == "wrong_point":
        body["knowledge_point_id"] = points["KP-REQ-01"]["id"]
    elif invalid in ("pending", "failed"):
        with app.state.sessions.begin() as db:
            diagnosis = db.scalar(select(Diagnosis).where(Diagnosis.event_id == body["source_event_id"]))
            diagnosis.status = invalid
        expected = 409
    elif invalid == "synthetic":
        with app.state.sessions.begin() as db:
            event = db.get(LearningEvent, body["source_event_id"])
            event.context = {**event.context, "synthetic": True}
        expected = 404
    else:
        body["source_event_id"] = str(uuid4())
        expected = 404
    response = client.post("/api/v1/learning-sessions", headers=headers, json=body)
    assert response.status_code == expected, response.text


def test_practice_source_preserves_answer_and_offers_more_practice(context, monkeypatch):
    app, client, cid, points = context
    headers = sign_in(client)
    kp = points["KP-REQ-01"]
    outline = client.get(f"/api/v1/courses/{cid}/outline").json()
    chapter = next(
        ch for ch in outline["chapters"] if any(p["id"] == kp["id"] for p in ch["knowledge_points"])
    )
    exercise = client.post(
        f"/api/v1/courses/{cid}/chapters/{chapter['id']}/practices",
        headers=headers,
        json={"knowledge_point_id": kp["id"], "question_text": "举例区分功能和性能要求。"},
    ).json()
    install_mock(monkeypatch, app)
    headers = sign_in(client, "student01")
    submission = client.post(
        f"/api/v1/courses/{cid}/practices/{exercise['id']}/submissions",
        headers=headers,
        json={"answer": "导出报告是一项性能要求，因为它需要运行。"},
    ).json()
    response = client.post(
        "/api/v1/learning-sessions",
        headers=headers,
        json={"course_id": cid, "knowledge_point_id": kp["id"], "source_event_id": submission["event_id"]},
    )
    assert response.status_code == 201, response.text
    state = response.json()
    assert state["practice_available"] is True
    assert state["source"]["exercise_id"] == exercise["id"]
    assert "导出报告" in state["source"]["original_answer"]
    assert "correct_values" not in str(state["source"])
