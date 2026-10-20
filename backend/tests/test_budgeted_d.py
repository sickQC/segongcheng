"""E7 constraints, teacher estimates, request identity and non-learning feedback."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from test_foundation import foundation, sign_in  # noqa: F401
from test_recommendation_d import diagnose, edges, graph  # noqa: F401

from app.models import LearningEvent, MasteryProfile, Recommendation, RecommendationFeedback
from app.services.budgeted_recommendation import schedule
from app.services.recommendation import record_feedback


def estimates(context, values):
    _, client, _, course, points = context
    headers = sign_in(client)
    for index, minutes in values.items():
        response = client.patch(
            f"/api/v1/courses/{course}/knowledge-points/{points[index]['id']}/study-time",
            headers=headers,
            json={"estimated_minutes": minutes},
        )
        assert response.status_code == 200, response.text


def create(context, strategy="budgeted", budget=20, target=2, request_id=None):
    _, client, _, course, points = context
    headers = sign_in(client, "student01")
    response = client.post(
        f"/api/v1/courses/{course}/recommendations",
        headers=headers,
        json={
            "target_kp_id": points[target]["id"],
            "strategy": strategy,
            "time_budget_minutes": budget,
            "request_id": request_id or str(uuid4()),
        },
    )
    return response


def test_budget_strategy_can_progress_when_baseline_first_step_does_not_fit(graph):  # noqa: F811
    edges(graph, [(0, 2), (1, 2)])
    estimates(graph, {0: 20, 1: 5, 2: 5})
    baseline = create(graph, "baseline", 10).json()
    enhanced = create(graph, budget=10).json()
    assert baseline["steps"] == [] and len(baseline["remaining_steps"]) == 3
    assert [s["knowledge_point_id"] for s in enhanced["steps"]] == [graph[4][1]["id"]]
    assert enhanced["estimated_minutes"] == 5 and enhanced["remaining_estimated_minutes"] == 25
    assert enhanced["goal_in_plan"] is False
    assert enhanced["full_path_estimated_minutes"] == baseline["full_path_estimated_minutes"] == 30
    assert all(s["deferral_reason"] for s in enhanced["remaining_steps"])


def test_budget_preserves_prerequisites_across_mastered_bridge(graph, monkeypatch):  # noqa: F811
    edges(graph, [(0, 1), (1, 2)])
    estimates(graph, {0: 20, 1: 5, 2: 5})
    diagnose(graph, monkeypatch, {1: 0.9})
    small = create(graph, budget=10).json()
    assert small["steps"] == [] and len(small["remaining_steps"]) == 2
    assert small["goal_in_plan"] is False
    exact = create(graph, budget=25).json()
    assert [s["knowledge_point_id"] for s in exact["steps"]] == [graph[4][0]["id"], graph[4][2]["id"]]
    assert exact["estimated_minutes"] == 25 and exact["goal_in_plan"] is True


def test_priority_prefers_weaker_ready_nodes_and_unknown_is_explicit(graph, monkeypatch):  # noqa: F811
    edges(graph, [(0, 2), (1, 2)])
    estimates(graph, {0: 5, 1: 5, 2: 5})
    diagnose(graph, monkeypatch, {0: 0.65, 1: 0.1})
    plan = create(graph, budget=5).json()
    assert plan["steps"][0]["knowledge_point_id"] == graph[4][1]["id"]
    assert plan["steps"][0]["reason_source"] == "diagnosis"
    assert (
        next(s for s in plan["remaining_steps"] if s["knowledge_point_id"] == graph[4][2]["id"])["mastery"]
        is None
    )


def test_teacher_estimate_reset_and_rule_source_are_distinguished(graph):  # noqa: F811
    _, client, _, course, points = graph
    estimates(graph, {2: 7})
    teacher = create(graph, budget=7).json()
    assert teacher["steps"][0]["estimated_minutes"] == 7
    assert teacher["steps"][0]["estimate_source"] == "teacher"
    estimates(graph, {2: None})
    rule = create(graph, budget=240).json()
    assert rule["steps"][0]["estimate_source"] == "rule_estimate"
    assert rule["steps"][0]["estimated_minutes"] == 5 + 3 * points[2]["difficulty"]
    headers = sign_in(client, "student01")
    url = f"/api/v1/courses/{course}/knowledge-points/{points[2]['id']}/study-time"
    assert client.patch(url, headers=headers, json={"estimated_minutes": 1}).status_code == 403
    headers = sign_in(client)
    for bad in (0, 241, True, 2.5, "10"):
        assert client.patch(url, headers=headers, json={"estimated_minutes": bad}).status_code == 422
    assert (
        client.patch(
            url.replace(points[2]["id"], "missing"), headers=headers, json={"estimated_minutes": 10}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("budget", [None, 0, 241, True, 2.5, "10"])
def test_budget_input_bounds(graph, budget):  # noqa: F811
    assert create(graph, budget=budget).status_code == 422


def test_request_identity_includes_strategy_and_budget(graph):  # noqa: F811
    request = str(uuid4())
    first = create(graph, budget=20, request_id=request)
    assert first.status_code == 201
    assert create(graph, budget=20, request_id=request).json() == first.json()
    assert create(graph, budget=21, request_id=request).status_code == 409
    assert create(graph, "baseline", 20, request_id=request).status_code == 409


def test_feedback_is_once_private_and_never_changes_mastery(graph):  # noqa: F811
    app, client, _, course, _ = graph
    saved = create(graph).json()
    url = f"/api/v1/courses/{course}/recommendations/{saved['id']}/feedback"
    metrics_url = f"/api/v1/courses/{course}/recommendation-metrics"
    assert client.get(url).json() is None
    before = client.get(metrics_url).json()["strategies"][1]
    assert before["feedback_count"] == 0 and before["acceptance_rate"] is None
    h = sign_in(client, "student01")
    first = client.post(url, headers=h, json={"choice": "accepted"})
    assert first.status_code == 200
    assert client.post(url, headers=h, json={"choice": "accepted"}).json() == first.json()
    assert client.post(url, headers=h, json={"choice": "declined"}).status_code == 409
    metrics = client.get(metrics_url).json()["strategies"][1]
    assert (metrics["feedback_count"], metrics["accepted_count"], metrics["acceptance_rate"]) == (1, 1, 1)
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecommendationFeedback)) == 1
        assert db.scalar(select(func.count()).select_from(MasteryProfile)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(LearningEvent.verb == "recommendation_feedback")
            )
            == 1
        )
    assert client.get(f"/api/v1/courses/{course}/profile").json()["engagement"]["event_count"] == 0
    h = sign_in(client, "student02")
    assert client.get(url).status_code == 404
    assert client.post(url, headers=h, json={"choice": "accepted"}).status_code == 404
    assert client.get(metrics_url).json()["strategies"][1]["recommendation_count"] == 0
    h = sign_in(client)
    assert client.get(url).status_code == 200
    assert client.post(url, headers=h, json={"choice": "accepted"}).status_code == 403
    assert client.get(metrics_url).json()["scope"] == "course"
    sign_in(client, "otherteacher")
    assert client.get(metrics_url).status_code == 403


def test_concurrent_feedback_does_not_duplicate_events(graph):  # noqa: F811
    app, _, _, _, _ = graph
    saved = create(graph).json()

    def record(choice):
        try:
            with app.state.sessions.begin() as db:
                return record_feedback(db, db.get(Recommendation, saved["id"]), choice).choice
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(record, ["accepted", "declined"]))
    assert values.count(409) == 1
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecommendationFeedback)) == 1


def test_legacy_baseline_snapshot_remains_readable(graph):  # noqa: F811
    app, client, _, course, _ = graph
    saved = create(graph, "baseline", None).json()
    with app.state.sessions.begin() as db:
        row = db.get(Recommendation, saved["id"])
        old = dict(row.snapshot)
        for key in (
            "time_budget_minutes",
            "estimated_minutes",
            "remaining_steps",
            "goal_in_plan",
            "remaining_estimated_minutes",
            "full_path_estimated_minutes",
            "scheduling_rule",
        ):
            old.pop(key, None)
        old["steps"] = [
            {
                k: v
                for k, v in s.items()
                if k not in ("estimated_minutes", "estimate_source", "priority_score")
            }
            for s in old["steps"]
        ]
        row.snapshot = old
    response = client.get(f"/api/v1/courses/{course}/recommendations/{saved['id']}")
    assert response.status_code == 200 and response.json()["estimated_minutes"] is None


def test_pure_scheduler_does_not_mutate_shared_comparison_input():
    plan = {
        "target_kp_id": "T",
        "status": "ready",
        "graph_edges": [],
        "steps": [
            {"knowledge_point_id": "T", "code": "T", "mastery": None, "estimated_minutes": 10, "order": 1}
        ],
    }
    result = schedule(plan, "budgeted", 1)
    assert result["steps"] == [] and len(result["remaining_steps"]) == 1
    assert "priority_score" not in plan["steps"][0]


def test_frozen_offline_comparison_is_reproducible_and_constraint_safe():
    import json
    from copy import deepcopy
    from pathlib import Path

    from scripts.eval_recommendation import evaluate

    path = Path(__file__).resolve().parents[2] / "data/eval/recommendation/e7-cases.json"
    dataset = json.loads(path.read_text(encoding="utf-8"))
    original = deepcopy(dataset)
    first = evaluate(dataset)
    assert first == evaluate(dataset) and dataset == original
    assert len(first["cases"]) == 24
    assert all(not r["budget_violation"] and not r["prerequisite_violations"] for r in first["cases"])
    assert all(r["acceptance_rate"] is None for r in first["summary"])


def test_priority_considers_distance_to_target(graph):  # noqa: F811
    edges(graph, [(0, 1), (1, 2), (3, 2)])
    estimates(graph, {0: 5, 1: 5, 2: 5, 3: 5})
    plan = create(graph, budget=5).json()
    assert [s["knowledge_point_id"] for s in plan["steps"]] == [graph[4][3]["id"]]


def test_acceptance_denominator_excludes_unanswered_recommendations(graph):  # noqa: F811
    _, client, _, course, _ = graph
    plans = [create(graph).json() for _ in range(3)]
    headers = sign_in(client, "student01")
    for plan, choice in zip(plans[:2], ("accepted", "declined")):
        assert (
            client.post(
                f"/api/v1/courses/{course}/recommendations/{plan['id']}/feedback",
                headers=headers,
                json={"choice": choice},
            ).status_code
            == 200
        )
    metrics = client.get(f"/api/v1/courses/{course}/recommendation-metrics").json()["strategies"][1]
    assert (metrics["recommendation_count"], metrics["feedback_count"], metrics["acceptance_rate"]) == (
        3,
        2,
        0.5,
    )


def test_seeded_dags_preserve_budget_and_ancestor_constraints():
    import random

    from scripts.eval_recommendation import case_plan, violations

    rng = random.Random(731)
    for _ in range(20):
        case = {
            "target": "29",
            "budget": rng.randint(1, 80),
            "nodes": [
                {"id": str(i), "minutes": rng.randint(1, 20), "mastery": rng.choice([None, 0.2, 0.6, 0.8])}
                for i in range(30)
            ],
            "edges": [[str(a), str(b)] for a in range(30) for b in range(a + 1, 30) if rng.random() < 0.12],
        }
        source = case_plan(case)
        for strategy in ("baseline", "budgeted"):
            plan = schedule(source, strategy, case["budget"])
            assert plan["estimated_minutes"] <= case["budget"]
            assert not violations(case, plan)
            assert len(plan["steps"]) + len(plan["remaining_steps"]) == len(source["steps"])
