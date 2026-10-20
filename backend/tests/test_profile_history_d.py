"""Profile history: frozen evidence, atomic diagnosis snapshots and scoped comparison."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_evidence_diagnosis import create, events, mock, scope  # noqa: F401
from test_foundation import foundation, sign_in  # noqa: F401

from app.models import (
    Course,
    CourseMember,
    DiagnosisReport,
    KnowledgePoint,
    ProfileApplication,
    ProfileSnapshot,
)
from app.services import profile_history
from app.services.profile import apply_report


def base(context):
    return f"/api/v1/courses/{context[3]}/profile/snapshots"


def save(context, request=None, days=30):
    response = context[1].post(base(context), headers=context[2],
                             json={"request_id": request or str(uuid4()), "days": days})
    assert response.status_code == 200, response.text
    return response.json()


def test_frozen_unknown_snapshot_and_idempotence(scope):  # noqa: F811
    app, client, headers, _, _, _ = scope
    request = str(uuid4())
    a = save(scope, request)
    assert a["reason"] == "manual" and a["profile"]["knowledge"]["known_points"] == 0
    assert all(p["mastery_percent"] is None for p in a["profile"]["knowledge"]["points"])
    events(scope)
    assert save(scope, request) == a
    assert client.get(base(scope) + "/" + a["id"]).json() == a
    conflict = client.post(base(scope), headers=headers, json={"request_id": request, "days": 7})
    assert conflict.status_code == 409
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ProfileSnapshot)) == 1


def test_comparison_never_turns_unknown_into_zero(scope):  # noqa: F811
    _, client, _, _, _, _ = scope
    a = save(scope)
    events(scope)
    b = save(scope)
    result = client.get(base(scope) + "/compare", params={"before_id": a["id"], "after_id": b["id"]})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["engagement"]["event_count"] == {"before": 0, "after": 3, "delta": 3}
    assert data["engagement"]["effective_seconds"]["delta"] is None
    assert all(p["mastery"]["delta"] is None for p in data["points"])
    assert any("不等于学习增益" in w for w in data["warnings"])
    for before, after in ((a, a), (b, a)):
        response = client.get(base(scope) + "/compare",
                              params={"before_id": before["id"], "after_id": after["id"]})
        assert response.status_code == 422
    different = save(scope, days=7)
    response = client.get(base(scope) + "/compare",
                          params={"before_id": b["id"], "after_id": different["id"]})
    assert response.status_code == 409


def test_auto_snapshot_only_when_supported_mastery_updates(scope, monkeypatch):  # noqa: F811
    app, client, _, _, _, _ = scope
    events(scope)
    mock(monkeypatch)
    _, report = create(scope)
    assert report["status"] == "supported"
    page = client.get(base(scope)).json()
    assert len(page["items"]) == 1 and page["items"][0]["reason"] == "diagnosis"
    assert page["items"][0]["report_id"] == report["id"]
    snap = client.get(base(scope) + "/" + page["items"][0]["id"]).json()
    assert snap["profile"]["knowledge"]["known_points"] == 1
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ProfileApplication)) == 1
    with app.state.sessions.begin() as db:
        assert apply_report(db, db.get(DiagnosisReport, report["id"])) == 0
        assert db.scalar(select(func.count()).select_from(ProfileSnapshot)) == 1


def test_failed_diagnosis_does_not_save_snapshot(scope):  # noqa: F811
    _, client, _, _, _, _ = scope
    _, report = create(scope)
    assert report["status"] == "insufficient"
    assert client.get(base(scope)).json()["items"] == []


def test_snapshot_failure_rolls_back_mastery_and_diagnosis_application(scope, monkeypatch):  # noqa: F811
    app, _, _, _, _, _ = scope
    events(scope)
    mock(monkeypatch)

    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("test snapshot failure")

    monkeypatch.setattr(profile_history, "save_snapshot", fail_snapshot)
    # Background task may propagate or be converted into a failed diagnosis; neither may commit mastery.
    try:
        create(scope)
    except RuntimeError:
        pass
    with app.state.sessions() as db:
        from app.models import MasteryProfile

        assert db.scalar(select(func.count()).select_from(MasteryProfile)) == 0
        assert db.scalar(select(func.count()).select_from(ProfileApplication)) == 0
        assert db.scalar(select(func.count()).select_from(ProfileSnapshot)) == 0


def test_history_permissions_pagination_and_teacher_query(scope):  # noqa: F811
    app, client, _, _, _, sid = scope
    a, b = save(scope), save(scope)
    first = client.get(base(scope), params={"limit": 1}).json()
    second = client.get(base(scope), params={"limit": 1, "offset": first["next_offset"]}).json()
    assert first["items"][0]["id"] == b["id"] and second["items"][0]["id"] == a["id"]
    assert second["next_offset"] is None
    sign_in(client, "student02")
    assert client.get(base(scope) + "/" + a["id"]).status_code == 404
    assert client.get(base(scope), params={"student_id": sid}).status_code == 403
    teacher_headers = sign_in(client, "teacher")
    assert client.get(base(scope), params={"student_id": sid}).status_code == 200
    assert client.post(base(scope), params={"student_id": sid}, headers=teacher_headers,
                       json={"request_id": str(uuid4())}).status_code == 200
    sign_in(client, "otherteacher")
    assert client.get(base(scope), params={"student_id": sid}).status_code in (403, 404)
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ProfileSnapshot)) == 3


@pytest.mark.parametrize("body", [
    {"request_id": "x", "days": True}, {"request_id": "x", "days": 0},
    {"request_id": "x", "days": 91}, {"request_id": "x", "profile": {"mastery": 1}},
])
def test_client_cannot_submit_profile_or_invalid_window(scope, body):  # noqa: F811
    assert scope[1].post(base(scope), headers=scope[2], json=body).status_code == 422


def test_concurrent_same_request_creates_one_snapshot(scope):  # noqa: F811
    app, _, _, course, _, sid = scope
    request = "manual-" + str(uuid4())

    def save_one(_):
        with app.state.sessions.begin() as db:
            return profile_history.save_snapshot(db, course, sid, request).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        identifiers = list(pool.map(save_one, range(2)))
    assert identifiers[0] == identifiers[1]


def test_history_stays_frozen_after_knowledge_rename(scope):  # noqa: F811
    app, client, _, _, point, _ = scope
    original = save(scope)
    with app.state.sessions.begin() as db:
        db.get(KnowledgePoint, point["id"]).name = "Changed after snapshot"
    assert client.get(base(scope) + "/" + original["id"]).json() == original
    newer = save(scope)
    assert any(p["name"] == "Changed after snapshot" for p in newer["profile"]["knowledge"]["points"])


def test_snapshot_id_cannot_be_reused_in_another_enrolled_course(scope):  # noqa: F811
    app, client, _, course, _, sid = scope
    saved = save(scope)
    other = str(uuid4())
    with app.state.sessions.begin() as db:
        db.add(Course(id=other, title="Other", teacher_id=db.get(Course, course).teacher_id))
        db.flush()
        db.add(CourseMember(course_id=other, user_id=sid, role="student"))
    assert client.get(f"/api/v1/courses/{other}/profile/snapshots/{saved['id']}").status_code == 404


def test_different_rule_versions_are_not_mixed(scope):  # noqa: F811
    app, client, _, _, _, _ = scope
    a, b = save(scope), save(scope)
    with app.state.sessions.begin() as db:
        row = db.get(ProfileSnapshot, b["id"])
        row.payload = {**row.payload, "rule_version": "future-rule-version"}
    result = client.get(base(scope) + "/compare", params={"before_id": a["id"], "after_id": b["id"]})
    assert result.status_code == 409
