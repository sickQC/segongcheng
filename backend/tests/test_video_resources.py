"""Video uploads, authenticated ranges and click-only completion without telemetry."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_foundation import foundation, sign_in  # noqa: F401
from test_resources import get_row, setup_course, upload

from app.models import LearningEvent, ResourceVersion, VideoCompletion
from app.services import resource_uploads, resources


def video_bytes(kind="mp4"):
    return (b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42" if kind == "mp4" else b"\x1a\x45\xdf\xa3\x87\x42\x82\x84webm") + b"example-video-payload" * 10


@pytest.mark.parametrize("kind", ["mp4", "webm"])
def test_video_upload_visible_streamable_and_not_automatically_completed(foundation, kind):  # noqa: F811
    app, client, _ = foundation
    cid, chapter, point, headers = setup_course(client)
    data = video_bytes(kind)
    response = upload(client, cid, headers, filename="教学视频." + kind, data=data,
                      chapter_id=chapter["id"], knowledge_point_ids='["' + point["id"] + '"]')
    assert response.status_code == 202 and response.json()["status"] == "ready", response.text
    rid = response.json()["resource_id"]
    student = sign_in(client, "student01")
    row = get_row(client, cid, rid)
    assert row["type"] == "video" and row["format"] is None and row["completed"] is False
    assert row["knowledge_point_ids"] == [point["id"]]
    assert client.get(row["url"]).content == data
    partial = client.get(row["url"], headers={"Range": "bytes=4-11"})
    assert partial.status_code == 206 and partial.content == data[4:12]
    assert partial.headers["content-range"] == f"bytes 4-11/{len(data)}"
    assert client.get(row["download_url"]).content == data
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvent)) == 0
        assert db.scalar(select(func.count()).select_from(VideoCompletion)) == 0
        assert not resources.course_index(db, app.state.settings, cid).chunks
        version = resources.version_for(db, resources.get_resource(db, cid, rid))
        assert version.original == b"" and version.storage_path
    # Opening is a separate authenticated, idempotent action, not a media-range side effect.
    for _ in range(2):
        result = client.post(f"/api/v1/courses/{cid}/resources/{rid}/complete", headers=student)
        assert result.status_code == 200 and result.json()["completed"] is True
    assert get_row(client, cid, rid)["completed"] is True
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(VideoCompletion)) == 1
        assert db.scalar(select(func.count()).select_from(LearningEvent)) == 0
    sign_in(client)
    assert get_row(client, cid, rid)["completed"] is False


def test_completion_is_per_student_per_version_and_survives_refresh(foundation):  # noqa: F811
    app, client, _ = foundation
    cid, _, _, teacher = setup_course(client)
    client.post(f"/api/v1/courses/{cid}/members", headers=teacher, json={"username": "student02"})
    rid = upload(client, cid, teacher, filename="lesson.mp4", data=video_bytes()).json()["resource_id"]
    base = f"/api/v1/courses/{cid}/resources/{rid}"
    first = sign_in(client, "student01")
    assert client.post(base + "/complete", headers=first).json()["completed"] is True
    sign_in(client, "student02")
    assert get_row(client, cid, rid)["completed"] is False
    teacher = sign_in(client)
    assert client.post(base + "/versions", headers=teacher, files={"file": ("new.mp4", video_bytes() + b"new")}).json()["status"] == "ready"
    sign_in(client, "student01")
    assert get_row(client, cid, rid)["completed"] is False
    teacher = sign_in(client)
    assert client.post(base + "/versions/1/activate", headers=teacher).status_code == 200
    sign_in(client, "student01")
    assert get_row(client, cid, rid)["completed"] is True
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(VideoCompletion)) == 1


def test_video_access_completion_and_delete_are_course_scoped(foundation):  # noqa: F811
    app, client, _ = foundation
    cid, _, _, headers = setup_course(client)
    rid = upload(client, cid, headers, filename="lesson.mp4", data=video_bytes()).json()["resource_id"]
    base = f"/api/v1/courses/{cid}/resources/{rid}"
    assert client.post(base + "/complete", headers=headers).status_code == 403
    assert client.post(base + "/complete").status_code == 403
    other = sign_in(client, "student02")
    assert client.get(base + "/file?inline=true").status_code == 403
    assert client.post(base + "/complete", headers=other).status_code == 403
    student = sign_in(client, "student01")
    assert client.post(f"/api/v1/courses/{uuid4()}/resources/{rid}/complete", headers=student).status_code == 404
    headers = sign_in(client)
    assert client.delete(base, headers=headers).status_code == 204
    student = sign_in(client, "student01")
    assert client.get(base + "/file?inline=true").status_code == 404
    assert client.post(base + "/complete", headers=student).status_code == 404
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvent)) == 0


def test_video_validation_and_failed_transaction_clean_staged_files(foundation, monkeypatch):  # noqa: F811
    app, client, _ = foundation
    cid, _, _, headers = setup_course(client)
    for kind in ("mp4", "webm"):
        assert upload(client, cid, headers, filename="fake." + kind, data=b"not video").status_code == 422
    result = upload(client, cid, headers, filename="lesson.mp4", data=video_bytes(), chapter_id=str(uuid4()))
    assert result.status_code == 422
    assert list(app.state.settings.video_upload_dir.glob("*")) == []
    monkeypatch.setattr(resource_uploads, "MAX_VIDEO_BYTES", 50)
    assert upload(client, cid, headers, filename="large.mp4", data=video_bytes()).status_code == 413
    assert list(app.state.settings.video_upload_dir.glob("*")) == []
    with app.state.sessions() as db:
        assert not db.scalar(select(ResourceVersion).where(ResourceVersion.file_type.in_(["mp4", "webm"])))


def test_videos_do_not_enter_document_parsing_or_qa(foundation):  # noqa: F811
    _, client, _ = foundation
    cid, _, _, headers = setup_course(client)
    rid = upload(client, cid, headers, filename="lesson.mp4", data=video_bytes()).json()["resource_id"]
    base = f"/api/v1/courses/{cid}/resources/{rid}"
    assert client.get(base + "/content").status_code == 422
    assert client.post(base + "/retry", headers=headers).status_code == 409
    student = sign_in(client, "student01")
    assert client.post(f"/api/v1/courses/{cid}/chat", headers=student, json={"resource_id": rid, "mode": "rag", "message": "总结视频"}).status_code == 422


def test_document_video_replacement_is_rejected_without_leaking_files(foundation):  # noqa: F811
    app, client, _ = foundation
    cid, _, _, headers = setup_course(client)
    doc = upload(client, cid, headers).json()["resource_id"]
    assert client.post(f"/api/v1/courses/{cid}/resources/{doc}/versions", headers=headers, files={"file": ("wrong.mp4", video_bytes())}).status_code == 422
    assert list(app.state.settings.video_upload_dir.glob("*")) == []
    assert get_row(client, cid, doc)["type"] == "doc"
