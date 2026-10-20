"""The merged targeted 5E journey remains visible to D's real-data consumers."""

import json
from uuid import uuid4

from test_assessment_learning_c import context, foundation, learning_mock  # noqa: F401
from test_foundation import sign_in
from test_learning_journey import diagnosed_quiz


def test_targeted_learning_flows_into_real_profile_export_snapshot_and_recommendation(context, monkeypatch):  # noqa: F811
    _, client, course, points = context
    headers, attempt, graded, diagnoses = diagnosed_quiz(context, monkeypatch)
    point = points["KP-VAL-01"]["id"]
    prefix = f"/api/v1/courses/{course}"
    learning_mock(monkeypatch)
    started = client.post("/api/v1/learning-sessions", headers=headers, json={
        "course_id": course, "knowledge_point_id": point,
        "source_event_id": diagnoses[0]["event_id"], "request_id": str(uuid4()),
    })
    assert started.status_code == 201, started.text
    session = started.json()["id"]
    turn = client.post(f"/api/v1/learning-sessions/{session}/turns", headers=headers,
                       json={"answer": "I will compare the specification with the actual user need."})
    assert turn.status_code == 202, turn.text
    report = client.get(prefix + "/report").json()
    assert report["history_source"] == "real"
    profile = report["learning_profile"]
    assert next(p for p in profile["preference"]["items"] if p["key"] == "ask")["count"] == 1
    response = client.get(prefix + "/learning-events/export", params={"knowledge_point_id": point, "verb": "responded"})
    assert response.status_code == 200
    rows = [json.loads(line) for line in response.text.splitlines()]
    assert len(rows) == 1 and rows[0]["object"]["id"] == session
    assert rows[0]["context"]["synthetic"] is False
    snapshot = client.post(prefix + "/profile/snapshots", headers=headers,
                           json={"request_id": str(uuid4()), "days": 30})
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["profile"]["engagement"]["event_count"] == profile["engagement"]["event_count"]
    path = client.post(prefix + "/recommendations", headers=headers, json={
        "target_kp_id": point, "strategy": "budgeted", "time_budget_minutes": 30, "request_id": str(uuid4()),
    })
    assert path.status_code == 201, path.text
    assert path.json()["target_kp_id"] == point
    assert client.get(prefix + f"/attempts/{attempt['id']}").json()["result"] == graded
    sign_in(client, "student02")
    assert client.get(prefix + "/learning-events/export", params={"verb": "responded"}).content == b""
