import os
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Base
from app.core.security import hash_password, token_hash
from app.main import create_app
from app.models import Chapter, Course, CourseMember, KnowledgePoint, LearningEvent, User, UserSession
from app.models.legacy import now
from app.services.seed import seed_data

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "test-password-123"


@pytest.fixture(params=["sqlite", "postgresql"] if os.getenv("RUN_POSTGRES_TESTS") == "1" else ["sqlite"])
def foundation(request, tmp_path):
    bootstrap = None
    schema = None
    if request.param == "postgresql":
        original = Settings().database_url
        assert original.startswith("postgresql")
        bootstrap = create_engine(original)
        schema = "test_p1_" + uuid4().hex
        with bootstrap.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(original).update_query_dict({"options": f"-csearch_path={schema}"})
        url = url.render_as_string(hide_password=False)
    else:
        url = f"sqlite:///{(tmp_path / 'foundation.db').as_posix()}"
    settings = Settings(
        _env_file=None,
        database_url=url,
        enable_dev_routes=False,
        allowed_origins=["http://testserver"],
        seed_password=PASSWORD,
        video_upload_dir=tmp_path / "videos",
    )
    app = create_app(settings)
    try:
        Base.metadata.create_all(app.state.engine)
        with app.state.sessions.begin() as db:
            seed_data(db, PASSWORD)
            db.add(
                User(
                    id="other-teacher",
                    username="otherteacher",
                    display_name="Other",
                    role="teacher",
                    password_hash=hash_password(PASSWORD),
                )
            )
        with TestClient(app) as client:
            yield app, client, url
    finally:
        app.state.engine.dispose()
        if bootstrap is not None:
            with bootstrap.begin() as db:
                db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            bootstrap.dispose()


def sign_in(client, username="teacher"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return {**ORIGIN, "X-CSRF-Token": r.json()["csrf_token"]}


def course_id(client):
    return client.get("/api/v1/courses").json()["items"][0]["id"]


def test_login_logout_and_no_secret_leak(foundation):
    app, c, _ = foundation
    assert c.get("/api/v1/auth/me").status_code == 401
    r = c.post("/api/v1/auth/login", json={"username": "teacher", "password": "wrong"}, headers=ORIGIN)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    h = sign_in(c)
    raw = c.cookies.get("se_session")
    r = c.get("/api/v1/auth/me")
    assert r.json()["user"]["role"] == "teacher"
    assert "password_hash" not in r.text and PASSWORD not in r.text
    assert r.headers["cache-control"] == "no-store"
    with app.state.sessions() as db:
        auth = db.scalar(select(UserSession))
        assert auth.token_hash == token_hash(raw) and auth.token_hash != raw
        user = db.scalar(select(User).where(User.username == "teacher"))
        assert user.password_hash.startswith("$argon2id$")
    assert c.post("/api/v1/auth/logout", headers=h).status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401
    c.cookies.set("se_session", raw)
    assert c.get("/api/v1/courses").status_code == 401


def test_origin_csrf_and_validation(foundation):
    _, c, _ = foundation
    assert (
        c.post(
            "/api/v1/auth/login",
            json={"username": "teacher", "password": PASSWORD},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    h = sign_in(c)
    assert c.post("/api/v1/courses", json={"title": "X"}).status_code == 403
    assert c.post("/api/v1/courses", json={"title": "X"}, headers=ORIGIN).status_code == 403
    assert (
        c.post(
            "/api/v1/courses", json={"title": "X"}, headers={**h, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    r = c.post("/api/v1/courses", json={"title": "  ", "teacher_id": "forged"}, headers=h)
    assert r.status_code == 422 and r.json()["request_id"]
    assert c.get("/api/v1/courses?page_size=101").status_code == 422


def test_teacher_student_full_flow(foundation):
    app, c, _ = foundation
    h = sign_in(c)
    course = course_id(c)
    chapter = c.post(
        f"/api/v1/courses/{course}/chapters", json={"title": "New Chapter", "sort_order": 3}, headers=h
    )
    assert chapter.status_code == 201
    chapter_id = chapter.json()["id"]
    body = {
        "code": "KP-NEW",
        "name": "New KP",
        "definition": "A definition",
        "difficulty": 2,
        "bloom_level": "understand",
    }
    r = c.post(f"/api/v1/chapters/{chapter_id}/knowledge-points", json=body, headers=h)
    assert r.status_code == 201
    kp_id = r.json()["id"]
    assert c.post(f"/api/v1/chapters/{chapter_id}/knowledge-points", json=body, headers=h).status_code == 409
    assert (
        c.patch(f"/api/v1/knowledge-points/{kp_id}", json={"name": "Updated KP"}, headers=h).status_code
        == 200
    )
    assert (
        c.patch(f"/api/v1/chapters/{chapter_id}", json={"title": "Updated Chapter"}, headers=h).status_code
        == 200
    )
    student_headers = sign_in(c, "student01")
    data = c.get(f"/api/v1/courses/{course}/outline").json()
    assert data["chapters"][-1]["title"] == "Updated Chapter"
    assert data["chapters"][-1]["knowledge_points"][0]["name"] == "Updated KP"
    assert (
        c.post(
            f"/api/v1/courses/{course}/chapters", json={"title": "forged"}, headers=student_headers
        ).status_code
        == 403
    )
    assert (
        c.patch(
            f"/api/v1/knowledge-points/{kp_id}", json={"name": "forged"}, headers=student_headers
        ).status_code
        == 403
    )
    assert c.delete(f"/api/v1/knowledge-points/{kp_id}", headers=student_headers).status_code == 403
    assert c.get(f"/api/v1/courses/{course}/members").status_code == 403
    with app.state.sessions() as db:
        assert db.get(KnowledgePoint, kp_id).name == "Updated KP"


def test_course_isolation_and_enrollment(foundation):
    _, c, _ = foundation
    h = sign_in(c)
    r = c.post("/api/v1/courses", json={"title": "Private course", "description": "Only members"}, headers=h)
    assert r.status_code == 201
    private = r.json()["id"]
    ch = c.post(f"/api/v1/courses/{private}/chapters", json={"title": "Private"}, headers=h).json()["id"]
    sign_in(c, "student01")
    assert private not in [x["id"] for x in c.get("/api/v1/courses").json()["items"]]
    assert c.get(f"/api/v1/courses/{private}/outline").status_code == 403
    other = sign_in(c, "otherteacher")
    assert c.get("/api/v1/courses").json()["total"] == 0
    assert c.patch(f"/api/v1/chapters/{ch}", json={"title": "Hacked"}, headers=other).status_code == 403
    h = sign_in(c)
    assert (
        c.post(f"/api/v1/courses/{private}/members", json={"username": "student01"}, headers=h).status_code
        == 201
    )
    assert (
        c.post(f"/api/v1/courses/{private}/members", json={"username": "student01"}, headers=h).status_code
        == 409
    )
    sign_in(c, "student01")
    assert c.get(f"/api/v1/courses/{private}/outline").status_code == 200
    sign_in(c, "student02")
    assert c.get(f"/api/v1/courses/{private}/outline").status_code == 403


def test_expiry_rotation_and_independent_sessions(foundation):
    app, c, _ = foundation
    sign_in(c, "student01")
    first = c.cookies.get("se_session")
    sign_in(c, "student02")
    with app.state.sessions.begin() as db:
        assert db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(first))) is None
        current = db.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash(c.cookies.get("se_session")))
        )
        assert db.get(User, current.user_id).username == "student02"
        current.expires_at = now() - timedelta(seconds=1)
    assert c.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("body", [{}, {"name": None}, {"difficulty": 0}, {"bloom_level": "invalid"}])
def test_invalid_updates_do_not_mutate(foundation, body):
    _, c, _ = foundation
    h = sign_in(c)
    course = course_id(c)
    kp = c.get(f"/api/v1/courses/{course}/outline").json()["chapters"][0]["knowledge_points"][0]
    assert c.patch(f"/api/v1/knowledge-points/{kp['id']}", json=body, headers=h).status_code == 422
    assert c.get(f"/api/v1/courses/{course}/outline").json()["chapters"][0]["knowledge_points"][0] == kp


def test_delete_and_unknown_resources(foundation):
    _, c, _ = foundation
    h = sign_in(c)
    course = course_id(c)
    chapter = c.get(f"/api/v1/courses/{course}/outline").json()["chapters"][0]
    kp = c.post(f"/api/v1/chapters/{chapter['id']}/knowledge-points", headers=h, json={
        "code": "KP-DELETE", "name": "待删除知识点", "definition": "尚无资料或学习记录", "difficulty": 1,
        "bloom_level": "remember",
    }).json()
    assert c.delete(f"/api/v1/knowledge-points/{kp['id']}", headers=h).status_code == 204
    assert c.delete(f"/api/v1/knowledge-points/{kp['id']}", headers=h).status_code == 404
    assert c.get("/api/v1/courses/missing/outline").status_code == 404
    assert c.get("/api/dev/question").status_code == 404
    assert c.get("/api/diagnoses").status_code == 404


def test_seed_is_idempotent_and_preserves_changes(foundation):
    app, _, _ = foundation
    with app.state.sessions.begin() as db:
        user = db.scalar(select(User).where(User.username == "teacher"))
        before = user.password_hash
        course = db.scalar(select(Course))
        course.title = "Edited title"
        seed_data(db, "different-password")
        seed_data(db, "different-password")
        assert user.password_hash == before
        assert course.title == "Edited title"
        assert db.scalar(select(func.count()).select_from(Course)) == 1
        assert db.scalar(select(func.count()).select_from(Chapter)) == 2
        assert db.scalar(select(func.count()).select_from(KnowledgePoint)) == 5
        assert db.scalar(select(func.count()).select_from(CourseMember)) == 3


def test_migrations_incremental_preserve_legacy(foundation, monkeypatch):
    from pathlib import Path

    from alembic.config import Config

    from alembic import command
    from app.models import LearningEvent

    app, _, url = foundation
    # Only this fixture's temporary DB/schema; never the application schema.
    Base.metadata.drop_all(app.state.engine)
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0001")
    with app.state.sessions.begin() as db:
        db.add(
            LearningEvent(
                event_id="legacy",
                actor="sim-student",
                verb="answered",
                object={},
                result={"answer": "saved"},
                context={},
            )
        )
    command.upgrade(config, "head")
    assert {"users", "sessions", "courses", "chapters", "knowledge_points"} <= set(
        inspect(app.state.engine).get_table_names()
    )
    with app.state.sessions() as db:
        assert db.get(LearningEvent, "legacy").result["answer"] == "saved"
    command.downgrade(config, "0001")
    assert "users" not in inspect(app.state.engine).get_table_names()
    command.upgrade(config, "head")


def test_workspace_contracts_do_not_fake_success(foundation):
    _, c, _ = foundation
    assert c.get("/api/v1/courses/unknown/resources").status_code == 401
    h = sign_in(c)
    cid = course_id(c)
    base = f"/api/v1/courses/{cid}"
    members = c.get(base + "/members").json()["items"]
    sid = next(m["user"]["id"] for m in members if m["role"] == "student")
    assert c.get(base + "/resources").status_code == 200
    assert c.get(base + "/quizzes").json() == []
    assert c.get(base + "/report").status_code == 403
    dashboard = c.get(base + "/dashboard").json()
    assert dashboard["student_count"] == 2
    assert dashboard["average_quiz_percent"] is None
    assert all(student["accuracy_percent"] is None for student in dashboard["students"])
    detail = c.get(base + f"/students/{sid}/report").json()
    assert detail["student_id"] == sid and detail["question_count"] == 0
    assert c.get(base + "/dashboard?days=0").status_code == 422
    for path, body in [
        ("/report/followup", {"message": "question"}),
        (f"/students/{sid}/diagnoses", None),
    ]:
        assert c.post(base + path, json=body, headers=h).status_code == 501
    assert c.post(base + "/attempts", json={"quiz_id": "q"}, headers=h).status_code == 403
    assert c.post(base + "/attempts/a/submit", json={"answers": []}, headers=h).status_code == 403
    assert (
        c.post(
            base + "/chat", json={"resource_id": "r", "message": "question", "mode": "rag"}, headers=h
        ).status_code
        == 404
    )
    assert c.post(base + "/attempts", json={"quiz_id": "q"}, headers=ORIGIN).status_code == 403
    assert (
        c.post(
            base + "/chat", json={"resource_id": "r", "message": " ", "mode": "rag"}, headers=h
        ).status_code
        == 422
    )
    assert c.get(base + "/report?algorithm=unknown").status_code == 422
    assert c.get(base + "/students/no-such-user/report").status_code == 404
    sign_in(c, "student01")
    assert c.get(base + "/dashboard").status_code == 403
    assert c.get(base + f"/students/{sid}/report").status_code == 403
    assert c.get(base + "/resources").status_code == 200
    assert c.get(base + "/report").json()["history_source"] == "real"
    assert c.get(base + "/report?history=synthetic").json()["history_source"] == "synthetic"
    sign_in(c, "otherteacher")
    assert c.get(base + "/resources").status_code == 403
    assert c.get(base + "/dashboard").status_code == 403


def test_synthetic_history_personalizes_only_related_questions(foundation, monkeypatch):
    from pydantic import SecretStr

    from app.rag.llm import LLMResult
    from app.services import tutor

    app, c, _ = foundation
    app.state.settings.llm_api_key = SecretStr("mock-key")
    app.state.settings.llm_model = "mock-model"
    prompts = []

    class FakeLLM:
        def complete(self, system, user):
            prompts.append((system, user))
            return LLMResult(text="功能需求描述系统行为 [1]。", model="mock-model", provider="openai")

    monkeypatch.setattr(tutor, "get_llm", lambda _cfg: FakeLLM())
    sign_in(c, "student01")
    cid = course_id(c)
    base = f"/api/v1/courses/{cid}"
    first_report = c.get(base + "/report?history=synthetic").json()
    assert first_report["history_source"] == "synthetic"
    assert first_report["chapter_history"][0]["accuracy"] == 48
    assert first_report["chapter_history"][0]["high_error"] is True
    assert len(first_report["chapter_history"][0]["wrong_questions"]) == 2

    question = "功能性需求与非功能性需求有什么区别？"
    first = c.post(
        base + "/chat",
        json={"resource_id": "kb:all", "message": question, "mode": "rag", "history": "synthetic"},
        headers=sign_in(c, "student01"),
    )
    assert first.status_code == 200, first.text
    assert first.json()["citations"]
    assert all(citation["section"] for citation in first.json()["citations"])
    assert first.json()["personalization"]["source"] == "synthetic"
    assert "48%" in prompts[-1][1]
    assert "两者都是系统要实现的功能" in prompts[-1][1]

    sign_in(c, "student02")
    second_report = c.get(base + "/report?history=synthetic").json()
    assert second_report["chapter_history"][0]["accuracy"] == 72
    assert second_report["chapter_history"][1]["high_error"] is True
    second = c.post(
        base + "/report/followup", json={"message": question}, headers=sign_in(c, "student02")
    )
    assert second.status_code == 200, second.text
    assert second.json()["personalization"] is not None
    assert "72%" in prompts[-1][1]
    assert "系统运行要快" in prompts[-1][1]
    assert "两者都是系统要实现的功能" not in prompts[-1][1]

    unrelated = c.post(
        base + "/report/followup",
        json={"message": "软件危机是什么？"}, headers=sign_in(c, "student02"),
    )
    assert unrelated.status_code == 200, unrelated.text
    assert unrelated.json()["personalization"] is None
    assert "演示学习记录" not in prompts[-1][1]

    with app.state.sessions() as db:
        asked = db.scalars(select(LearningEvent).where(LearningEvent.verb == "asked")).all()
        assert len(asked) == 3
        assert len({event.actor for event in asked}) == 2
        assert all(event.context["course"] == cid for event in asked)
