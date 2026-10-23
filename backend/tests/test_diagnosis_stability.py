"""Unchanged evidence cannot acquire a different score by refreshing or racing."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Lock
from uuid import uuid4

from test_evidence_diagnosis import create, events, mock, scope  # noqa: F401
from test_foundation import foundation  # noqa: F401

from app.schemas.diagnosis_report import ReportCreate
from app.services import evidence_diagnosis as service


def test_repeat_reuses_result_but_new_evidence_or_configuration_recomputes(scope, monkeypatch):  # noqa: F811
    app, client, _, course, point, _ = scope
    events(scope)
    calls = mock(monkeypatch)
    _, first = create(scope)
    _, repeated = create(scope)
    assert len(calls) == 1
    assert repeated["id"] != first["id"]
    assert repeated["output"]["points"] == first["output"]["points"]
    assert repeated["output"]["reuse"]["report_id"] == first["id"]
    assert repeated["output"]["model_called"] is False
    profile = client.get(f"/api/v1/courses/{course}/profile").json()
    assert next(p for p in profile["knowledge"]["points"] if p["knowledge_point_id"] == point["id"])["mastery_percent"] == 30

    events(scope, count=1)
    _, changed = create(scope)
    assert len(calls) == 2 and "reuse" not in changed["output"]
    app.state.settings.c_llm_model = "another-test-model"
    _, configured = create(scope)
    assert len(calls) == 3 and "reuse" not in configured["output"]


def test_concurrent_identical_inputs_persist_one_consistent_result(scope, monkeypatch):  # noqa: F811
    app, client, _, course, point, student = scope
    events(scope)
    mock(monkeypatch)
    rows = [service.create_report(app.state.sessions, app.state.settings, course, student,
                                 ReportCreate(knowledge_point_ids=[point["id"]], request_id=uuid4()))[0]
            for _ in range(2)]
    template, _, _ = service.infer_snapshot(app.state.settings, rows[0]["snapshot"])
    barrier, lock, calls = Barrier(2), Lock(), []

    def inference(*args):
        with lock:
            score = .2 if not calls else .8
            calls.append(score)
        output = deepcopy(template)
        output["points"][0]["mastery"] = score
        barrier.wait(timeout=10)
        return output, None, "test-model"

    monkeypatch.setattr(service, "infer_snapshot", inference)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.run_report, app.state.sessions, app.state.settings,
                               row["id"], row["trace_id"]) for row in rows]
        for future in futures:
            future.result(timeout=20)
    prefix = f"/api/v1/courses/{course}/diagnosis-reports/"
    results = [client.get(prefix + row["id"]).json() for row in rows]
    assert all(r["status"] == "supported" for r in results)
    assert results[0]["output"]["points"] == results[1]["output"]["points"]
    assert sum(bool(r["output"].get("reuse")) for r in results) == 1
