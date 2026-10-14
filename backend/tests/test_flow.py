import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.database import Base
from app.main import create_app
from app.models import Diagnosis, LearningEvent, ModelTrace
from app.services import diagnosis as service


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        _env_file=None,
        enable_dev_routes=True,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        llm_api_key="",
        llm_model="test-model",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    app.state.test_settings = settings
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def submit(client, **kwargs):
    response = client.post(
        "/api/dev/submissions", json={"answer": service.QUESTION["sample_answer"], **kwargs}
    )
    assert response.status_code == 202
    ids = response.json()
    detail = client.get(f"/api/diagnoses/{ids['diagnosis_id']}")
    assert detail.status_code == 200
    return ids, detail.json()


def install_model_mock(monkeypatch, app, handler):
    app.state.test_settings.llm_api_key = SecretStr("test-key-never-real")
    monkeypatch.setattr(
        service, "create_model_client", lambda _: httpx.Client(transport=httpx.MockTransport(handler))
    )


def valid_response(request):
    user = json.loads(json.loads(request.content)["messages"][1]["content"])
    output = service.demo_output(user["event_id"]).model_dump()
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(output)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
        },
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "sqlite", "sprint": 1}


def test_missing_key_retains_submission(client, app, monkeypatch):
    def forbidden(_):
        pytest.fail("缺失密钥时不得发送任何模型请求")

    monkeypatch.setattr(service, "create_model_client", forbidden)
    ids, detail = submit(client)
    assert detail["status"] == "failed"
    assert detail["error_code"] == "MISSING_API_KEY"
    assert detail["output"] is None
    assert detail["event"]["event_id"] == ids["event_id"]
    assert detail["event"]["result"]["answer"] == service.QUESTION["sample_answer"]
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(LearningEvent)) == 1


def test_success_and_commit_before_model_call(client, app, monkeypatch):
    def handler(request):
        # 独立连接在模型请求发生前就能读取作答，证明提交事务已经完成。
        with app.state.sessions() as session:
            assert session.scalar(select(func.count()).select_from(LearningEvent)) == 1
        assert request.headers["authorization"] == "Bearer test-key-never-real"
        return valid_response(request)

    install_model_mock(monkeypatch, app, handler)
    ids, detail = submit(client)
    assert detail["status"] == "supported"
    assert detail["output"]["evidence_event_ids"] == [ids["event_id"]]
    assert detail["traces"][0]["trace_id"] == ids["trace_id"]
    assert detail["traces"][0]["usage"]["total_tokens"] == 50
    assert detail["traces"][0]["status"] == "succeeded"
    assert "test-key-never-real" not in json.dumps(detail)


@pytest.mark.parametrize(
    "case,code",
    [
        ("http", "MODEL_HTTP_ERROR"),
        ("timeout", "MODEL_TIMEOUT"),
        ("connection", "MODEL_CONNECTION_ERROR"),
        ("bad_json", "INVALID_MODEL_OUTPUT"),
        ("bad_envelope", "INVALID_MODEL_OUTPUT"),
        ("bad_schema", "INVALID_MODEL_OUTPUT"),
        ("fake_event", "INVALID_EVIDENCE"),
        ("fake_citation", "INVALID_MODEL_OUTPUT"),
        ("wrong_kp", "INVALID_MODEL_OUTPUT"),
    ],
)
def test_model_failures_preserve_event(client, app, monkeypatch, case, code):
    def handler(request):
        if case == "http":
            return httpx.Response(401, text="secret-upstream-body")
        if case == "timeout":
            raise httpx.ReadTimeout("secret-upstream-body", request=request)
        if case == "connection":
            raise httpx.ConnectError("secret-upstream-body", request=request)
        if case == "bad_envelope":
            return httpx.Response(200, json={"choices": []})
        if case == "bad_json":
            return httpx.Response(200, json={"choices": [{"message": {"content": "not JSON"}}]})
        envelope = valid_response(request).json()
        output = json.loads(envelope["choices"][0]["message"]["content"])
        if case == "bad_schema":
            output["confidence"] = 9
        if case == "fake_event":
            output["evidence_event_ids"] = ["invented-event"]
        if case == "fake_citation":
            output["citations"] = [{"page": 123}]
        if case == "wrong_kp":
            output["knowledge_point_id"] = "FAKE-KP"
        envelope["choices"][0]["message"]["content"] = json.dumps(output)
        return httpx.Response(200, json=envelope)

    install_model_mock(monkeypatch, app, handler)
    ids, detail = submit(client)
    assert detail["status"] == "failed"
    assert detail["error_code"] == code
    assert detail["output"] is None
    assert detail["event"]["event_id"] == ids["event_id"]
    assert "secret-upstream-body" not in json.dumps(detail)


def test_insufficient_evidence(client, app, monkeypatch):
    def handler(request):
        envelope = valid_response(request).json()
        output = json.loads(envelope["choices"][0]["message"]["content"])
        output.update(status="insufficient", mastery=None, problem_type="insufficient_evidence")
        envelope["choices"][0]["message"]["content"] = json.dumps(output)
        return httpx.Response(200, json=envelope)

    install_model_mock(monkeypatch, app, handler)
    _, detail = submit(client, answer="不会")
    assert detail["status"] == "insufficient"
    assert detail["output"]["mastery"] is None


def test_retry_preserves_event_and_trace_history(client, app, monkeypatch):
    ids, failed = submit(client)
    install_model_mock(monkeypatch, app, valid_response)
    response = client.post(f"/api/diagnoses/{ids['diagnosis_id']}/retry")
    assert response.status_code == 202
    detail = client.get(f"/api/diagnoses/{ids['diagnosis_id']}").json()
    assert detail["event_id"] == failed["event_id"]
    assert detail["status"] == "supported"
    assert detail["error_code"] is None
    assert [trace["status"] for trace in detail["traces"]] == ["failed", "succeeded"]
    assert client.post(f"/api/diagnoses/{ids['diagnosis_id']}/retry").status_code == 409
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(LearningEvent)) == 1


def test_demo_is_explicit_and_restricted(client, monkeypatch):
    monkeypatch.setattr(service, "call_model", lambda *_: pytest.fail("演示不得调用模型"))
    _, detail = submit(client, mode="demo")
    assert detail["mode"] == "demo"
    assert detail["event"]["context"]["source"] == "demo"
    assert detail["traces"][0]["status"] == "demo"
    assert detail["traces"][0]["usage"] is None
    assert "固定模拟数据" in detail["output"]["problem_description"]
    assert client.post("/api/dev/submissions", json={"answer": "其他答案", "mode": "demo"}).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"answer": "  "},
        {"answer": "x" * 4001},
        {"answer": "x", "duration_seconds": -1},
        {"answer": "x", "mode": "unknown"},
        {"answer": "x", "actor": "real-student"},
    ],
)
def test_invalid_input_not_saved(client, app, body):
    assert client.post("/api/dev/submissions", json=body).status_code == 422
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(LearningEvent)) == 0


def test_not_found_and_list(client):
    assert client.get("/api/diagnoses/does-not-exist").status_code == 404
    assert client.post("/api/diagnoses/does-not-exist/retry").status_code == 404
    assert client.get("/api/diagnoses").json() == []
    submit(client)
    assert len(client.get("/api/diagnoses").json()) == 1


def test_restart_recovers_interrupted_task(app):
    with app.state.sessions.begin() as session:
        event = LearningEvent(actor="sim-001", verb="answered", object={}, result={"answer": "x"}, context={})
        session.add(event)
        session.flush()
        diagnosis = Diagnosis(event_id=event.event_id, mode="live")
        session.add(diagnosis)
        session.flush()
        trace = service.add_trace(session, app.state.test_settings, diagnosis, event)
        diagnosis_id, trace_id = diagnosis.id, trace.trace_id
    with TestClient(app) as client:
        assert client.get(f"/api/diagnoses/{diagnosis_id}").json()["error_code"] == "PROCESS_INTERRUPTED"
    with app.state.sessions() as session:
        assert session.get(ModelTrace, trace_id).error_code == "PROCESS_INTERRUPTED"


def test_demo_can_be_disabled(client, app):
    app.state.test_settings.enable_demo = False
    assert (
        client.post(
            "/api/dev/submissions", json={"answer": service.QUESTION["sample_answer"], "mode": "demo"}
        ).status_code
        == 403
    )
