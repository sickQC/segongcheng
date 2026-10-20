"""Use the actual course hierarchy and existing lecture headings, not a flat template list."""

from sqlalchemy import select
from test_assessment_learning_c import context, foundation, learning_mock  # noqa: F401
from test_foundation import sign_in

from app.models import Chapter
from app.models.learning_session import LearningSession
from app.services.learning_curriculum import LECTURE_SECTIONS, lecture_materials


def test_available_topics_follow_course_chapters_and_actual_lecture_sections(context):  # noqa: F811
    app, client, cid, _ = context
    sign_in(client, "student01")
    outline = client.get(f"/api/v1/courses/{cid}/outline").json()["chapters"]
    topics = client.get(f"/api/v1/courses/{cid}/learning-templates").json()
    expected = [p["id"] for ch in outline for p in ch["knowledge_points"] if p["code"] in LECTURE_SECTIONS]
    assert [p["knowledge_point_id"] for p in topics] == expected
    for topic in topics:
        chapter = next(ch for ch in outline if ch["id"] == topic["chapter_id"])
        assert topic["chapter_title"] == chapter["title"]
        assert topic["lectures"], topic
        for lecture in topic["lectures"]:
            doc = client.get(f"/api/v1/courses/{cid}/resources/{lecture['resource_id']}/content").json()
            assert f" {lecture['section']}\n" in doc["markdown"]
            resources = client.get(f"/api/v1/courses/{cid}/resources").json()
            resource = next(r for r in resources if r["id"] == lecture["resource_id"])
            assert topic["knowledge_point_id"] in resource["knowledge_point_ids"]
    assert not lecture_materials(app.state.settings, "unrelated-course", "KP-REQ-01")


def test_new_and_existing_sessions_resolve_the_course_chapter(context, monkeypatch):  # noqa: F811
    app, client, cid, points = context
    headers = sign_in(client, "student01")
    point = points["KP-TEST-01"]
    response = client.post(
        "/api/v1/learning-sessions",
        headers=headers,
        json={"course_id": cid, "knowledge_point_id": point["id"]},
    )
    assert response.status_code == 201, response.text
    current = response.json()
    assert current["chapter"]["title"] == "第二章 软件测试"
    assert current["lectures"][0]["section"] == "等价类划分"
    captured = learning_mock(monkeypatch)
    url = f"/api/v1/learning-sessions/{current['id']}"
    client.post(
        url + "/turns", headers=headers, json={"answer": "我会分别检查有效范围和范围两侧的无效输入。"}
    )
    assert captured[0]["chapter"]["id"] == current["chapter"]["id"]
    assert "0、50、101" in captured[0]["course_materials"][0]["excerpt"]
    with app.state.sessions.begin() as db:
        row = db.get(LearningSession, current["id"])
        row.snapshot = {
            key: value for key, value in row.snapshot.items() if key not in ("chapter", "course_materials")
        }
    assert client.get(url).json()["chapter"]["title"] == "第二章 软件测试"


def test_topic_chapters_follow_teacher_sort_order(context):  # noqa: F811
    app, client, cid, _ = context
    with app.state.sessions.begin() as db:
        rows = db.scalars(select(Chapter).where(Chapter.course_id == cid)).all()
        for row in rows:
            row.sort_order = 10 if "需求" in row.title else 1
    sign_in(client, "student01")
    topics = client.get(f"/api/v1/courses/{cid}/learning-templates").json()
    assert topics[0]["chapter_title"] == "第二章 软件测试"
