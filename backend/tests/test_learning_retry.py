"""Retries preserve answers/evidence and reject stale or unauthorized work."""

# ruff: noqa: F811
from sqlalchemy import select
from test_assessment_learning_c import context, foundation, learning_mock, start_learning  # noqa: F401
from test_foundation import sign_in

from app.models import LearningEvent, ModelTrace
from app.services import learning_session as learning
from app.services.c_model_gateway import ModelCallError


def fail_turn(context, monkeypatch):
    app, client, _, _ = context
    headers, session = start_learning(context)
    url = f"/api/v1/learning-sessions/{session['id']}"

    def timeout(*args):
        raise ModelCallError("MODEL_TIMEOUT", "模型超时")

    monkeypatch.setattr(learning, "complete_json", timeout)
    response = client.post(
        url + "/turns", headers=headers, json={"answer": "我会用响应时间约束来判断非功能需求。"}
    )
    assert response.status_code == 202
    failed = client.get(url).json()["turns"][-1]
    return app, client, headers, url, failed


def test_retry_preserves_answer_event_and_failed_attempt(context, monkeypatch):
    app, client, headers, url, failed = fail_turn(context, monkeypatch)
    learning_mock(monkeypatch)
    endpoint = url + f"/turns/{failed['id']}/retry"
    response = client.post(endpoint, headers=headers)
    assert response.status_code == 202, response.text
    state = client.get(url).json()
    assert len(state["turns"]) == 1
    turn = state["turns"][0]
    assert turn["status"] == "succeeded" and state["pending_turn_id"] is None
    assert turn["answer"] == failed["answer"] and turn["event_id"] == failed["event_id"]
    assert turn["trace_id"] != failed["trace_id"]
    assert client.post(endpoint, headers=headers).status_code == 409
    with app.state.sessions() as db:
        assert db.get(ModelTrace, failed["trace_id"]).error_code == "MODEL_TIMEOUT"
        assert db.get(ModelTrace, turn["trace_id"]).details["retry_of"] == failed["trace_id"]
        assert (
            len(list(db.scalars(select(LearningEvent).where(LearningEvent.event_id == failed["event_id"]))))
            == 1
        )


def test_retry_rejects_other_student_teacher_and_stale_turn(context, monkeypatch):
    _, client, _, url, failed = fail_turn(context, monkeypatch)
    endpoint = url + f"/turns/{failed['id']}/retry"
    other = sign_in(client, "student02")
    assert client.post(endpoint, headers=other).status_code == 404
    teacher = sign_in(client)
    assert client.post(endpoint, headers=teacher).status_code == 404
    owner = sign_in(client, "student01")
    client.post(url + "/turns", headers=owner, json={"answer": "这是后续一次新的尝试。"})
    assert client.post(endpoint, headers=owner).status_code == 409
