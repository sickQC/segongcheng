"""Authenticated exports are complete, bounded, private and safe for spreadsheet viewing."""

import csv
import io
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from test_evidence_diagnosis import events, scope  # noqa: F401
from test_foundation import foundation, sign_in  # noqa: F401

from app.models import LearningEvent
from app.models.legacy import now
from app.services import event_export


def url(context):
    return f"/api/v1/courses/{context[3]}/learning-events/export"


def test_jsonl_export_strictly_real_scoped_and_read_only(scope):  # noqa: F811
    app, client, _, course, point, sid = scope
    keep = events(scope)
    for changes in ({"actor": "other"}, {"context": {"course": course, "synthetic": True}},
                    {"context": {"course": course, "synthetic": 0}},
                    {"context": {"course": "other", "synthetic": False}},
                    {"timestamp": now() - timedelta(days=31)}):
        events(scope, count=1, **changes)
    with app.state.sessions() as db:
        count = db.scalar(select(func.count()).select_from(LearningEvent))
    response = client.get(url(scope), params={"knowledge_point_id": point["id"], "verb": "answered"})
    assert response.status_code == 200, response.text
    rows = [json.loads(line) for line in response.text.splitlines()]
    assert [r["event_id"] for r in rows] == keep
    assert all(r["actor"] == sid and r["context"]["synthetic"] is False for r in rows)
    assert response.headers["x-export-event-count"] == "3"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].endswith('"learning-events.jsonl"')
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvent)) == count


def test_csv_unicode_nested_json_and_empty_exports(scope):  # noqa: F811
    _, client, _, _, _, _ = scope
    empty = client.get(url(scope), params={"format": "csv"})
    assert empty.content.startswith(b"\xef\xbb\xbf") and empty.headers["x-export-event-count"] == "0"
    assert client.get(url(scope)).content == b""
    answer = '=1+2,"换行\n测试"'
    events(scope, count=1, result={"answer": answer, "correct": False})
    response = client.get(url(scope), params={"format": "csv"})
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 1 and json.loads(rows[0]["result"])["answer"] == answer
    assert list(rows[0]) == list(event_export.FIELDS)


@pytest.mark.parametrize("value", ["=1+2", "+cmd", "-cmd", "@cmd", "\tvalue", " \r=cmd", "＝1+2", "＠cmd"])
def test_formula_prefixes_are_text(value):
    assert event_export.csv_cell(value).startswith("'")


@pytest.mark.parametrize("limit", ["MAX_EVENTS", "MAX_BYTES"])
def test_limits_fail_before_partial_attachment(scope, monkeypatch, limit):  # noqa: F811
    events(scope)
    monkeypatch.setattr(event_export, limit, 2 if limit == "MAX_EVENTS" else 100)
    response = scope[1].get(url(scope))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "EXPORT_LIMIT"
    assert "content-disposition" not in response.headers


def test_export_permission_and_validation(scope):  # noqa: F811
    _, client, _, _, _, sid = scope
    events(scope)
    for query in ({"format": "xlsx"}, {"start": "2026-01-01T00:00:00"},
                  {"start": "2020-01-01T00:00:00Z"}, {"knowledge_point_id": "not-in-course"}):
        assert client.get(url(scope), params=query).status_code == 422
    assert client.get(url(scope), params={"student_id": "other"}).status_code == 403
    sign_in(client, "student02")
    assert client.get(url(scope)).headers["x-export-event-count"] == "0"
    sign_in(client, "teacher")
    assert client.get(url(scope)).status_code == 422
    assert client.get(url(scope), params={"student_id": sid}).headers["x-export-event-count"] == "3"
    sign_in(client, "otherteacher")
    assert client.get(url(scope), params={"student_id": sid}).status_code == 403
    client.cookies.clear()
    assert client.get(url(scope)).status_code == 401
