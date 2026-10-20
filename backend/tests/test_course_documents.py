from urllib.parse import quote

import pytest
from test_foundation import course_id, foundation, sign_in  # noqa: F401


@pytest.mark.parametrize("username", ["student01", "teacher"])
def test_indexed_lectures_return_readable_originals(foundation, username):  # noqa: F811
    _, client, _ = foundation
    sign_in(client, username)
    base = f"/api/v1/courses/{course_id(client)}"
    lectures = [item for item in client.get(base + "/resources").json()
                if item.get("format") == "markdown"]
    assert len(lectures) == 6
    for item in lectures:
        response = client.get(base + f"/resources/{quote(item['id'], safe='')}/content")
        assert response.status_code == 200, response.text
        document = response.json()
        assert document["title"] == item["title"]
        assert document["resource_id"] == item["id"]
        assert "## " in document["markdown"]
        assert len(document["markdown"]) > 1000
    requirements = client.get(base + "/resources/kb:SE-02/content").json()["markdown"]
    assert "3000" in requirements and "95" in requirements and "2 秒" in requirements


def test_lecture_originals_require_course_access(foundation):  # noqa: F811
    _, client, _ = foundation
    sign_in(client)
    cid = course_id(client)
    path = f"/api/v1/courses/{cid}/resources/kb:SE-02/content"
    sign_in(client, "otherteacher")
    assert client.get(path).status_code == 403
    client.cookies.clear()
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("resource", ["kb:all", "kb:unknown", "kb:../../.env", "file:.env"])
def test_resource_ids_cannot_read_arbitrary_files(foundation, resource):  # noqa: F811
    _, client, _ = foundation
    sign_in(client, "student01")
    cid = course_id(client)
    response = client.get(f"/api/v1/courses/{cid}/resources/{quote(resource, safe='')}/content")
    assert response.status_code == 404
    assert "LLM_API_KEY" not in response.text
