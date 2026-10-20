"""Baseline acceptance: prerequisite safety, provenance, privacy and durable requests."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from test_evidence_diagnosis import events, mock
from test_foundation import course_id, foundation, sign_in  # noqa: F401

from app.models import KnowledgeEdge, LearningEvent, Recommendation
from app.schemas.recommendation import EdgeCreate, RecommendationCreate
from app.services.prerequisites import add_edge, ordered_graph
from app.services.recommendation import create_recommendation
from app.services.seed import seed_id


@pytest.fixture
def graph(foundation):  # noqa: F811
    app, client, _ = foundation
    headers = sign_in(client)
    course = course_id(client)
    outline = client.get(f"/api/v1/courses/{course}/outline").json()
    points = [p for ch in outline["chapters"] for p in ch["knowledge_points"]]
    return app, client, headers, course, points


def edges(graph, pairs):
    _, client, _, course, points = graph
    headers = sign_in(client)
    rows = []
    for before, after in pairs:
        response = client.post(
            f"/api/v1/courses/{course}/prerequisites",
            headers=headers,
            json={"from_kp_id": points[before]["id"], "to_kp_id": points[after]["id"]},
        )
        assert response.status_code == 201, response.text
        rows.append(response.json())
    return rows


def diagnose(graph, monkeypatch, values):
    app, client, _, course, points = graph
    headers = sign_in(client, "student01")
    for index in values:
        events((app, client, headers, course, points[index], seed_id("student01")))
    by_id = {points[index]["id"]: value for index, value in values.items()}
    mock(
        monkeypatch,
        alter=lambda result: [p.update(mastery=by_id[p["knowledge_point_id"]]) for p in result["points"]],
    )
    response = client.post(
        f"/api/v1/courses/{course}/diagnosis-reports",
        headers=headers,
        json={"knowledge_point_ids": list(by_id)},
    )
    assert response.status_code == 202
    saved = client.get(f"/api/v1/courses/{course}/diagnosis-reports/{response.json()['id']}").json()
    assert saved["status"] == "supported"
    return saved["id"]


def generate(graph, target=2, request_id=None):
    _, client, _, course, points = graph
    headers = sign_in(client, "student01")
    return client.post(
        f"/api/v1/courses/{course}/recommendations",
        headers=headers,
        json={"target_kp_id": points[target]["id"], "request_id": request_id or str(uuid4())},
    )


def test_unknown_diamond_has_complete_order_and_real_actions(graph):
    _, client, _, course, points = graph
    edges(graph, [(0, 1), (0, 3), (1, 2), (3, 2)])
    headers = sign_in(client)
    chapter = client.get(f"/api/v1/courses/{course}/outline").json()["chapters"][0]
    practice = client.post(
        f"/api/v1/courses/{course}/chapters/{chapter['id']}/practices",
        headers=headers,
        json={"knowledge_point_id": points[0]["id"], "question_text": "说明功能需求。"},
    )
    assert practice.status_code == 201
    response = generate(graph)
    assert response.status_code == 201, response.text
    data = response.json()
    order = {s["knowledge_point_id"]: s["order"] for s in data["steps"]}
    a, b, c, d = [p["id"] for p in points]
    assert len(order) == 4 and order[a] < order[b] < order[c] and order[a] < order[d] < order[c]
    assert all(
        s["mastery"] is None and s["diagnosis_id"] is None and s["reason_source"] == "prerequisite_rule"
        for s in data["steps"]
    )
    first = next(s for s in data["steps"] if s["knowledge_point_id"] == a)
    assert [x["kind"] for x in first["actions"]] == ["knowledge", "practice"]
    assert first["actions"][1]["id"] == practice.json()["id"]
    assert all(
        f"/courses/{course}?knowledge_point=" in action["url"]
        for s in data["steps"]
        for action in s["actions"]
    )


@pytest.mark.parametrize("mastery,skipped", [(0.699, False), (0.7, True)])
def test_threshold_uses_valid_diagnosis_and_retains_provenance(graph, monkeypatch, mastery, skipped):
    edges(graph, [(0, 1), (1, 2)])
    report_id = diagnose(graph, monkeypatch, {0: mastery, 1: 0.3})
    data = generate(graph).json()
    a = graph[4][0]["id"]
    assert (a in [p["knowledge_point_id"] for p in data["skipped"]]) is skipped
    assert all(s["knowledge_point_id"] != graph[4][3]["id"] for s in data["steps"])
    item = next(s for s in data["steps"] + data["skipped"] if s["knowledge_point_id"] == a)
    assert item["diagnosis_id"] == report_id and item["evidence_ids"] and item["confidence"] == 0.8
    assert item["reason_source"] == "diagnosis"


def test_skipping_intermediate_preserves_transitive_order(graph, monkeypatch):
    edges(graph, [(2, 1), (1, 0)])
    diagnose(graph, monkeypatch, {1: 0.8})
    data = generate(graph, target=0).json()
    assert [s["knowledge_point_id"] for s in data["steps"]] == [graph[4][2]["id"], graph[4][0]["id"]]


def test_mastered_target_requires_no_new_path(graph, monkeypatch):
    edges(graph, [(0, 1), (1, 2)])
    diagnose(graph, monkeypatch, {2: 0.9})
    data = generate(graph).json()
    assert data["status"] == "target_mastered" and data["steps"] == []
    assert [p["knowledge_point_id"] for p in data["skipped"]] == [graph[4][2]["id"]]


def test_missing_graph_never_invents_prerequisites(graph):
    data = generate(graph).json()
    assert len(data["steps"]) == 1 and data["graph_edges"] == []
    assert "没有已配置的先修关系" in data["notes"][0]


def test_cycle_self_duplicate_and_point_delete_guard(graph):
    _, client, _, course, points = graph
    rows = edges(graph, [(0, 1), (1, 2)])
    headers = sign_in(client)
    base = f"/api/v1/courses/{course}/prerequisites"
    a, b, c = [p["id"] for p in points[:3]]
    cycle = client.post(base, headers=headers, json={"from_kp_id": c, "to_kp_id": a})
    assert cycle.status_code == 409
    assert cycle.json()["detail"]["fields"]["cycle"] == [c, a, b, c]
    assert client.post(base, headers=headers, json={"from_kp_id": a, "to_kp_id": a}).status_code == 409
    duplicate = client.post(base, headers=headers, json={"from_kp_id": a, "to_kp_id": b})
    assert duplicate.json()["id"] == rows[0]["id"] and len(client.get(base).json()) == 2
    assert client.delete(f"/api/v1/knowledge-points/{a}", headers=headers).status_code == 409
    assert (
        client.patch(
            f"/api/v1/knowledge-points/{a}", headers=headers, json={"name": "仍可编辑名称"}
        ).status_code
        == 200
    )
    assert client.delete(base + "/" + rows[0]["id"], headers=headers).status_code == 204
    assert len(client.get(base).json()) == 1


def test_request_id_persists_snapshot_and_one_event(graph):
    app, client, _, course, points = graph
    rows = edges(graph, [(0, 1), (1, 2)])
    request_id = str(uuid4())
    first = generate(graph, request_id=request_id).json()
    teacher_headers = sign_in(client)
    client.delete(f"/api/v1/courses/{course}/prerequisites/{rows[0]['id']}", headers=teacher_headers)
    again = generate(graph, request_id=request_id).json()
    assert again == first
    assert generate(graph, target=0, request_id=request_id).status_code == 409
    base = f"/api/v1/courses/{course}/recommendations"
    assert client.get(base + "/" + first["id"]).json() == first
    assert client.get(base).json() == [first]
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Recommendation)) == 1
        assert (
            db.scalar(
                select(func.count()).select_from(LearningEvent).where(LearningEvent.verb == "recommended")
            )
            == 1
        )
    assert client.get(f"/api/v1/courses/{course}/profile").json()["engagement"]["event_count"] == 0
    refreshed = generate(graph).json()
    assert len(refreshed["steps"]) == 2 and len(first["steps"]) == 3


def test_student_and_teacher_permissions_and_csrf(graph):
    _, client, _, course, points = graph
    saved = generate(graph).json()
    base = f"/api/v1/courses/{course}"
    student_headers = sign_in(client, "student02")
    assert client.get(base + "/recommendations").json() == []
    assert client.get(base + "/recommendations/" + saved["id"]).status_code == 404
    edge = {"from_kp_id": points[0]["id"], "to_kp_id": points[1]["id"]}
    assert client.post(base + "/prerequisites", headers=student_headers, json=edge).status_code == 403
    body = {"target_kp_id": points[2]["id"]}
    assert (
        client.post(base + "/recommendations", headers={"Origin": "http://testserver"}, json=body).status_code
        == 403
    )
    assert (
        client.post(
            base + "/recommendations", headers=student_headers, json={**body, "strategy": "budgeted"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            base + "/recommendations",
            headers=student_headers,
            json={**body, "student_id": seed_id("student01")},
        ).status_code
        == 422
    )
    sign_in(client)
    assert client.get(base + "/recommendations/" + saved["id"]).status_code == 200
    assert len(client.get(base + f"/students/{seed_id('student01')}/recommendations").json()) == 1
    other_headers = sign_in(client, "otherteacher")
    assert client.get(base + "/prerequisites").status_code == 403
    assert client.get(base + "/recommendations/" + saved["id"]).status_code == 403
    assert client.post(base + "/prerequisites", headers=other_headers, json=edge).status_code == 403


def test_cross_course_point_and_target_are_rejected(graph):
    _, client, _, course, points = graph
    headers = sign_in(client, "otherteacher")
    other = client.post(
        "/api/v1/courses", headers=headers, json={"title": "其他课程", "description": ""}
    ).json()
    chapter = client.post(
        f"/api/v1/courses/{other['id']}/chapters",
        headers=headers,
        json={"title": "其他章节", "sort_order": 1},
    ).json()
    point = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=headers,
        json={
            "code": "OTHER",
            "name": "其他知识点",
            "definition": "其他课程的定义",
            "difficulty": 1,
            "bloom_level": "understand",
        },
    ).json()
    headers = sign_in(client)
    assert (
        client.post(
            f"/api/v1/courses/{course}/prerequisites",
            headers=headers,
            json={"from_kp_id": points[0]["id"], "to_kp_id": point["id"]},
        ).status_code
        == 422
    )
    headers = sign_in(client, "student01")
    assert (
        client.post(
            f"/api/v1/courses/{course}/recommendations", headers=headers, json={"target_kp_id": point["id"]}
        ).status_code
        == 422
    )


def test_concurrent_opposite_edges_cannot_create_cycle(graph):
    app, _, _, course, points = graph

    def create(pair):
        try:
            with app.state.sessions.begin() as db:
                add_edge(
                    db, course, EdgeCreate(from_kp_id=points[pair[0]]["id"], to_kp_id=points[pair[1]]["id"])
                )
            return 201
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, [(0, 1), (1, 0)])) == [201, 409]


def test_concurrent_retry_and_rollback_keep_records_and_events_atomic(graph):
    app, _, _, course, points = graph
    body = RecommendationCreate(target_kp_id=points[2]["id"])

    def create(_):
        with app.state.sessions.begin() as db:
            return create_recommendation(db, course, seed_id("student01"), body, 0.7)["id"]

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert len(set(pool.map(create, range(3)))) == 1
    with pytest.raises(RuntimeError):
        with app.state.sessions.begin() as db:
            create_recommendation(
                db, course, seed_id("student01"), RecommendationCreate(target_kp_id=points[0]["id"]), 0.7
            )
            raise RuntimeError("rollback")
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Recommendation)) == 1
        assert (
            db.scalar(
                select(func.count()).select_from(LearningEvent).where(LearningEvent.verb == "recommended")
            )
            == 1
        )


def test_corrupt_cycle_fails_without_saving_path(graph):
    app, _, _, course, points = graph
    with app.state.sessions.begin() as db:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            db.add(KnowledgeEdge(course_id=course, from_kp_id=points[a]["id"], to_kp_id=points[b]["id"]))
    assert generate(graph).status_code == 409
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Recommendation)) == 0


def test_large_chain_orders_without_recursion():
    points = [SimpleNamespace(id=str(i), code=f"KP-{i:04}") for i in range(1200)]
    edges = [SimpleNamespace(from_kp_id=str(i), to_kp_id=str(i + 1)) for i in range(1199)]
    assert ordered_graph(points, edges) == [p.id for p in points]
