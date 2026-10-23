"""D profile acceptance with real scoped DB events and mocked diagnosis responses."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_evidence_diagnosis import create, events, mock, scope  # noqa: F401
from test_foundation import foundation, sign_in  # noqa: F401

from app.models import MasteryProfile, ProfileApplication
from app.models.diagnosis_report import DiagnosisReport
from app.models.legacy import now
from app.services import profile as service
from app.services.c_model_gateway import ModelCallError


def clone_report(app, original_id, *, cutoff=None, mastery=0.9):
    with app.state.sessions.begin() as db:
        original = db.get(DiagnosisReport, original_id)
        snapshot, output = deepcopy(original.snapshot), deepcopy(original.output)
        if cutoff:
            snapshot["cutoff"] = cutoff.isoformat()
        output["points"][0]["mastery"] = mastery
        row = DiagnosisReport(
            course_id=original.course_id,
            student_id=original.student_id,
            request_id=str(uuid4()),
            trace_id=original.trace_id,
            snapshot=snapshot,
            output=output,
            status="supported",
        )
        db.add(row)
        db.flush()
        return row.id


def test_empty_profile_is_real_and_does_not_invent_measurements(scope):  # noqa: F811
    _, client, _, course, _, sid = scope
    base = f"/api/v1/courses/{course}"
    response = client.get(base + "/report")
    assert response.status_code == 200
    report = response.json()
    assert report["history_source"] == "real" and report["chapter_history"] == []
    p = report["learning_profile"]
    assert p["student_id"] == sid
    assert p["knowledge"]["known_points"] == 0
    assert all(
        x["mastery_percent"] is None and x["accuracy_percent"] is None for x in p["knowledge"]["points"]
    )
    assert p["engagement"]["active_days"] == 0 and p["engagement"]["effective_seconds"] is None
    assert p["risk"]["level"] == "unknown"
    assert all(x["percent"] is None for x in p["preference"]["items"])
    assert client.get(base + "/report?history=synthetic").json()["history_source"] == "synthetic"
    assert client.get(base + "/report?algorithm=enhanced").status_code == 501


def test_real_quiz_submission_updates_report_and_events_without_model(scope):  # noqa: F811
    _, client, _, course, point, _ = scope
    base = f"/api/v1/courses/{course}"
    teacher_headers = sign_in(client)
    quiz = client.post(
        base + "/quizzes",
        headers=teacher_headers,
        json={
            "title": "D闭环验收",
            "duration_minutes": 20,
            "max_attempts": 1,
            "questions": [
                {
                    "knowledge_point_id": point["id"],
                    "type": "boolean",
                    "stem": f"第{i}题：功能需求描述系统做什么",
                    "options": ["正确", "错误"],
                    "correct_values": ["正确"],
                    "explanation": "功能需求描述系统行为。",
                    "points": 10,
                }
                for i in range(3)
            ],
        },
    )
    assert quiz.status_code == 201
    headers = sign_in(client, "student01")
    attempt = client.post(base + "/attempts", headers=headers, json={"quiz_id": quiz.json()["id"]}).json()
    answers = {"answers": [{"question_id": q["id"], "value": ["错误"]} for q in attempt["questions"]]}
    submit = base + f"/attempts/{attempt['id']}/submit"
    first = client.post(submit, headers=headers, json=answers)
    assert first.status_code == 200 and first.json()["score"] == 0
    assert client.post(submit, headers=headers, json=answers).status_code == 200
    report = client.get(base + "/report").json()
    assert report["records"][0]["score"] == 0 and len(report["mistakes"]) == 3
    assert report["learning_profile"]["knowledge"]["known_points"] == 0
    assert report["learning_profile"]["risk"]["level"] == "attention"
    assert len(client.get(base + "/learning-events").json()["items"]) == 3


def test_event_scope_filters_time_point_and_pagination(scope):  # noqa: F811
    _, client, _, course, point, sid = scope
    keep = events(scope)
    for change in (
        {"actor": "other"},
        {"context": {"course": course, "synthetic": True}},
        {"context": {"course": "other", "synthetic": False}},
        {"context": {"course": course}},
        {"timestamp": now() + timedelta(days=1)},
        {"timestamp": now() - timedelta(days=31)},
    ):
        events(scope, count=1, **change)
    base = f"/api/v1/courses/{course}"
    query = {"limit": 2, "knowledge_point_id": point["id"], "verb": "answered"}
    page = client.get(base + "/learning-events", params=query).json()
    assert [x["event_id"] for x in page["items"]] == list(reversed(keep))[:2]
    assert page["next_offset"] == 2
    query.update(offset=2, start=page["window_start"], end=page["window_end"])
    last = client.get(base + "/learning-events", params=query).json()
    assert [x["event_id"] for x in last["items"]] == [keep[0]] and last["next_offset"] is None
    profile = client.get(base + "/profile").json()
    row = next(x for x in profile["knowledge"]["points"] if x["knowledge_point_id"] == point["id"])
    assert row["accuracy_percent"] == 0 and row["mastery_percent"] is None and row["question_count"] == 3
    assert profile["engagement"]["event_count"] == 3
    assert profile["risk"]["level"] == "attention"
    assert set(profile["risk"]["evidence_ids"]) == set(keep)
    assert client.get(base + "/learning-events", params={"knowledge_point_id": "unknown"}).status_code == 422
    assert client.get(base + "/learning-events?limit=101").status_code == 422
    assert client.get(base + "/learning-events?start=2026-01-01T00:00:00").status_code == 422
    assert client.get(base + "/learning-events?start=2020-01-01T00:00:00Z").status_code == 422
    assert client.get(base + "/learning-events", params={"student_id": "other"}).status_code == 403
    sign_in(client, "student02")
    assert client.get(base + "/learning-events").json()["items"] == []
    assert client.get(base + f"/students/{sid}/profile").status_code == 403
    sign_in(client)
    assert client.get(base + f"/students/{sid}/profile").status_code == 200
    assert len(client.get(base + "/learning-events", params={"student_id": sid}).json()["items"]) == 3
    assert client.get(base + "/learning-events").status_code == 422
    assert client.get(base + "/learning-events?student_id=missing").status_code == 404
    sign_in(client, "otherteacher")
    assert client.get(base + f"/students/{sid}/profile").status_code == 403
    assert client.get(base + "/learning-events", params={"student_id": sid}).status_code == 403


def test_success_updates_mastery_once_failure_and_insufficient_preserve_it(scope, monkeypatch):  # noqa: F811
    app, client, _, course, point, _ = scope
    ids = events(scope)
    mock(monkeypatch)
    _, report = create(scope)
    assert report["status"] == "supported"
    base = f"/api/v1/courses/{course}"
    p = client.get(base + "/profile").json()
    row = next(x for x in p["knowledge"]["points"] if x["knowledge_point_id"] == point["id"])
    assert row["mastery_percent"] == 30 and row["confidence_percent"] == 80
    assert set(row["evidence_ids"]) == set(ids) and row["report_id"] == report["id"]
    with app.state.sessions.begin() as db:
        assert service.apply_report(db, db.get(DiagnosisReport, report["id"])) == 0
        assert db.scalar(select(func.count()).select_from(ProfileApplication)) == 1

    def broken(*args):
        raise ModelCallError("MODEL_UNAVAILABLE", "offline")

    # A changed model configuration must bypass same-evidence result reuse.
    app.state.settings.c_llm_model = "offline-test-model"
    monkeypatch.setattr("app.services.evidence_diagnosis.complete_json", broken)
    _, failed = create(scope)
    assert failed["status"] == "failed"
    with app.state.sessions.begin() as db:
        assert service.apply_report(db, db.get(DiagnosisReport, failed["id"])) == 0
    after = client.get(base + "/profile").json()["knowledge"]["points"]
    assert next(x for x in after if x["knowledge_point_id"] == point["id"]) == row
    with app.state.sessions.begin() as db:
        insufficient = db.get(DiagnosisReport, failed["id"])
        insufficient.status = "insufficient"
        assert service.apply_report(db, insufficient) == 0


def test_old_completion_cannot_overwrite_newer_inputs(scope, monkeypatch):  # noqa: F811
    app, _, _, _, _, _ = scope
    events(scope)
    mock(monkeypatch)
    _, report = create(scope)
    old = clone_report(app, report["id"], cutoff=now() - timedelta(seconds=30))
    with app.state.sessions.begin() as db:
        assert service.apply_report(db, db.get(DiagnosisReport, old)) == 0
        mastery = db.scalar(select(MasteryProfile))
        assert mastery.report_id == report["id"] and mastery.mastery == 0.3


def test_concurrent_duplicate_application_and_transaction_rollback(scope, monkeypatch):  # noqa: F811
    app, _, _, _, _, _ = scope
    events(scope)
    mock(monkeypatch)
    _, report = create(scope)
    pending = clone_report(app, report["id"])

    def apply():
        with app.state.sessions.begin() as db:
            return service.apply_report(db, db.get(DiagnosisReport, pending))

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert sorted(pool.map(lambda _: apply(), range(3))) == [0, 0, 1]
    rolled_back = clone_report(app, report["id"], mastery=0.6)
    with pytest.raises(RuntimeError):
        with app.state.sessions.begin() as db:
            assert service.apply_report(db, db.get(DiagnosisReport, rolled_back)) == 1
            raise RuntimeError("roll back the whole diagnosis projection")
    with app.state.sessions() as db:
        assert db.get(ProfileApplication, rolled_back) is None
        assert db.scalar(select(MasteryProfile)).report_id == pending


@pytest.mark.parametrize("change", ["synthetic", "actor", "course", "point", "future"])
def test_invalid_diagnosis_evidence_never_enters_mastery(scope, monkeypatch, change):  # noqa: F811
    app, _, _, course, point, sid = scope
    events(scope)
    mock(monkeypatch)
    _, report = create(scope)
    pending = clone_report(app, report["id"])
    from app.models import LearningEvent

    with app.state.sessions.begin() as db:
        candidate = db.get(DiagnosisReport, pending)
        evidence_id = candidate.output["points"][0]["evidence_event_ids"][0]
        event = db.get(LearningEvent, evidence_id)
        if change == "synthetic":
            event.context = {"course": course, "synthetic": True}
        elif change == "actor":
            event.actor = sid + "-other"
        elif change == "course":
            event.context = {"course": course + "-other", "synthetic": False}
        elif change == "point":
            event.object = {**event.object, "kp": [point["id"] + "-other"]}
        else:
            event.timestamp = now() + timedelta(days=1)
        db.flush()
        assert service.apply_report(db, candidate) == 0
        assert db.scalar(select(MasteryProfile)).report_id == report["id"]


def test_active_days_use_china_time_and_resource_snapshots_are_not_summed(scope, monkeypatch):  # noqa: F811
    app, client, _, course, _, _ = scope
    instant = datetime(2026, 10, 19, 18, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "now", lambda: instant)
    for minute in (59, 61):
        events(scope, count=1, timestamp=instant.replace(hour=15, minute=0) + timedelta(minutes=minute))
    profile = client.get(f"/api/v1/courses/{course}/profile").json()
    assert profile["engagement"]["active_days"] == 2
    for seconds, coverage in ((60, 0.5), (120, 0.95)):
        events(
            scope,
            count=1,
            verb="viewed",
            timestamp=instant - timedelta(minutes=2) + timedelta(seconds=seconds),
            object={"type": "resource", "id": "video1", "resource_type": "video", "kp": []},
            context={
                "course": course,
                "synthetic": False,
                "source": "resource_tracker",
                "measurement": "server",
            },
            result={
                "effective_seconds": seconds,
                "coverage": coverage,
                "study_visits": 1,
                "resource_available": True,
                "observation_complete": True,
            },
        )
    profile = client.get(f"/api/v1/courses/{course}/profile").json()
    assert profile["engagement"]["effective_seconds"] == 120
    assert profile["engagement"]["completed_resource_percent"] == 100
    assert profile["engagement"]["observed_resource_count"] == 1
    items = {x["key"]: x for x in profile["preference"]["items"]}
    assert items["video"]["count"] == 1 and items["read"]["count"] is None
    assert items["video"]["percent"] is None and items["practice"]["percent"] == 100
    assert service.numeric(float("nan"), 0, 1) is False
    assert service.numeric(True, 0, 1) is False
