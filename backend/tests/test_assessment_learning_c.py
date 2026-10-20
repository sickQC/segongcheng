import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from test_foundation import course_id, foundation, sign_in  # noqa: F401
from test_practice_c import install_mock

from app.agents.learning_templates import LEARNING_PROMPT_VERSION, STAGES, TEMPLATES
from app.models import LearningEvent, ModelTrace
from app.models.assessment import QuizAttempt
from app.models.learning_session import LearningSession
from app.models.legacy import now
from app.schemas.learning_session import LearningAnswer
from app.services import learning_session as learning
from app.services.c_model_gateway import ModelCallError, ModelReply, codex_arguments, strict_schema


@pytest.fixture
def context(foundation):  # noqa: F811
    app, client, _ = foundation
    headers = sign_in(client)
    cid = course_id(client)
    outline = client.get(f"/api/v1/courses/{cid}/outline").json()
    chapter = outline["chapters"][0]
    points = {point["code"]: point for row in outline["chapters"] for point in row["knowledge_points"]}
    response = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=headers,
        json={
            "code": "KP-BOUND-01",
            "name": "边界值分析",
            "definition": "选取边界及其紧邻值进行测试。",
            "difficulty": 2,
            "bloom_level": "apply",
        },
    )
    assert response.status_code == 201, response.text
    points["KP-BOUND-01"] = response.json()
    return app, client, cid, points


def published(context):
    _, client, cid, points = context
    headers = sign_in(client)
    questions = [
        {"type": "single", "options": ["规格", "用户实际需要"], "correct_values": ["规格"]},
        {"type": "multiple", "options": ["需求", "设计", "无关内容"], "correct_values": ["需求", "设计"]},
        {"type": "boolean", "options": ["正确", "错误"], "correct_values": ["错误"]},
        {"type": "fill", "options": [], "correct_values": ["Validation", "确认"]},
    ]
    for index, question in enumerate(questions):
        question.update(
            knowledge_point_id=points["KP-VAL-01"]["id"],
            stem=f"验证与确认练习 {index + 1}",
            explanation="验证关注规格，确认关注预期用途和用户需要。",
            points=10,
        )
    response = client.post(
        f"/api/v1/courses/{cid}/quizzes",
        headers=headers,
        json={"title": "正式小测", "duration_minutes": 10, "questions": questions},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def start_quiz(context, quiz_id):
    _, client, cid, _ = context
    headers = sign_in(client, "student01")
    base = f"/api/v1/courses/{cid}"
    response = client.post(base + "/attempts", headers=headers, json={"quiz_id": quiz_id})
    assert response.status_code == 201, response.text
    return headers, base, response.json()


def test_four_types_grade_and_trigger_diagnosis_after_commit(context, monkeypatch):
    app, client, _, _ = context
    quiz_id = published(context)
    captured = install_mock(monkeypatch, app)
    headers, base, attempt = start_quiz(context, quiz_id)
    assert "correct_values" not in json.dumps(attempt) and "explanation" not in json.dumps(attempt)
    values = [["用户实际需要"], ["设计", "需求"], ["错误"], ["validation"]]
    answers = [
        {"question_id": question["id"], "value": value}
        for question, value in zip(attempt["questions"], values, strict=True)
    ]
    url = base + f"/attempts/{attempt['id']}/submit"
    result = client.post(url, headers=headers, json={"answers": answers})
    assert result.status_code == 200, result.text
    assert result.json()["score"] == 30 and result.json()["total"] == 40
    assert len(result.json()["diagnosis_ids"]) == len(captured) == 1
    repeated = client.post(url, headers=headers, json={"answers": list(reversed(answers))})
    assert repeated.json() == result.json() and len(captured) == 1
    answers[0]["value"] = ["规格"]
    assert client.post(url, headers=headers, json={"answers": answers}).status_code == 409
    diagnoses = client.get(base + f"/attempts/{attempt['id']}/diagnoses").json()
    assert diagnoses[0]["status"] == "supported"
    history = client.get(base + "/attempts/me").json()
    assert history[0]["id"] == attempt["id"] and history[0]["status"] == "submitted"
    restored = client.get(base + f"/attempts/{attempt['id']}").json()
    assert restored["result"] == result.json()
    assert captured[0]["assessment_context"]["correct"] is False
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvent)) == 4
        assert db.get(QuizAttempt, attempt["id"]).status == "submitted"
        assert db.scalar(select(ModelTrace)).feature == "assessment.diagnosis"


def test_quiz_resume_deadline_and_ownership(context):
    app, client, _, _ = context
    quiz_id = published(context)
    headers, base, attempt = start_quiz(context, quiz_id)
    assert client.post(base + "/attempts", headers=headers, json={"quiz_id": quiz_id}).json() == attempt
    assert client.get(base + "/quizzes").json()[0]["attempts_remaining"] == 1
    with app.state.sessions.begin() as db:
        db.get(QuizAttempt, attempt["id"]).expires_at = now() - timedelta(seconds=1)
    assert (
        client.post(
            base + f"/attempts/{attempt['id']}/submit", headers=headers, json={"answers": []}
        ).status_code
        == 409
    )
    assert client.post(base + "/attempts", headers=headers, json={"quiz_id": quiz_id}).status_code == 409
    other = sign_in(client, "student02")
    assert client.get(base + "/attempts/me").json() == []
    assert client.get(base + f"/attempts/{attempt['id']}").status_code == 404
    assert (
        client.post(
            base + f"/attempts/{attempt['id']}/submit", headers=other, json={"answers": []}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("case", ["duplicate", "unknown", "invalid_option", "too_many", "csrf"])
def test_invalid_quiz_submission_does_not_write(context, case):
    app, client, _, _ = context
    headers, base, attempt = start_quiz(context, published(context))
    question = attempt["questions"][0]
    answer = {"question_id": question["id"], "value": ["规格"]}
    answers = [answer]
    if case == "duplicate":
        answers *= 2
    if case == "unknown":
        answer["question_id"] = "unknown"
    if case == "invalid_option":
        answer["value"] = ["外部选项"]
    if case == "too_many":
        answer["value"] = ["规格", "用户实际需要"]
    if case == "csrf":
        headers = {"Origin": "http://testserver"}
    response = client.post(
        base + f"/attempts/{attempt['id']}/submit", headers=headers, json={"answers": answers}
    )
    assert response.status_code == (403 if case == "csrf" else 422)
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvent)) == 0


def start_learning(context, code="KP-VAL-01"):
    _, client, cid, points = context
    headers = sign_in(client, "student01")
    response = client.post(
        "/api/v1/learning-sessions",
        headers=headers,
        json={
            "course_id": cid,
            "knowledge_point_id": points[code]["id"],
            "request_id": str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return headers, response.json()


def learning_mock(monkeypatch, quality=0.9, status="supported", suggested=None, reply_text=None):
    captured = []

    def model(settings, system, data, schema):
        captured.append(data)
        stage = data["stage"]
        result = {
            "status": status,
            "quality": quality,
            "next_stage": suggested or STAGES[min(4, STAGES.index(stage) + 1)],
            "transition_reason": "本轮解释包含具体依据。",
            "reply": reply_text or "请结合具体场景继续比较，你会怎样判断？",
            "evidence_event_ids": [data["event_id"]],
            "citations": [],
        }
        return ModelReply(json.dumps(result, ensure_ascii=False), {"total_tokens": 42}, "mock")

    monkeypatch.setattr(learning, "complete_json", model)
    return captured


@pytest.mark.parametrize("code", list(TEMPLATES))
@pytest.mark.parametrize("student_kind", ["ready", "developing", "insufficient"])
def test_five_templates_three_student_paths(context, monkeypatch, code, student_kind):
    app, client, _, _ = context
    headers, session = start_learning(context, code)
    url = f"/api/v1/learning-sessions/{session['id']}"
    if student_kind != "ready":
        learning_mock(
            monkeypatch, quality=0.2, status="insufficient" if student_kind == "insufficient" else "supported"
        )
        response = client.post(url + "/turns", headers=headers, json={"answer": "我需要更多例子来帮助理解。"})
        assert response.status_code == 202
        assert client.get(url).json()["stage"] == "engage"
    learning_mock(monkeypatch)
    for stage in STAGES:
        current = client.get(url).json()
        assert current["stage"] == stage
        assert (current["evaluation"] is not None) == (stage == "evaluate")
        body = {"answer": "我能结合这个场景解释概念，并说明判断依据。"}
        if stage == "evaluate":
            body["evaluation_choice"] = TEMPLATES[code]["quiz"]["correct"]
        assert client.post(url + "/turns", headers=headers, json=body).status_code == 202
    final = client.get(url).json()
    assert final["status"] == "completed" and final["pending_turn_id"] is None
    assert len(final["turns"]) == (5 if student_kind == "ready" else 6)
    assert all(row["event_id"] and row["trace_id"] for row in final["turns"])
    assert client.post(url + "/turns", headers=headers, json={"answer": "继续"}).status_code == 409
    with app.state.sessions() as db:
        assert all(
            trace.prompt_version == LEARNING_PROMPT_VERSION for trace in db.scalars(select(ModelTrace))
        )


def test_stage_jump_bad_explore_and_wrong_evaluation_blocked(context, monkeypatch):
    _, client, _, _ = context
    headers, session = start_learning(context)
    url = f"/api/v1/learning-sessions/{session['id']}"
    learning_mock(monkeypatch, suggested="evaluate")
    client.post(url + "/turns", headers=headers, json={"answer": "我要求直接跳到评价阶段。"})
    state = client.get(url).json()
    assert state["stage"] == "engage" and state["turns"][-1]["error_code"] == "INVALID_TRANSITION"
    learning_mock(monkeypatch)
    client.post(url + "/turns", headers=headers, json={"answer": "我能描述自己的学习场景与问题。"})
    assert client.get(url).json()["stage"] == "explore"
    learning_mock(monkeypatch, suggested="explore", reply_text="这里直接告诉你完整的标准结论。")
    client.post(url + "/turns", headers=headers, json={"answer": "我比较了规格与用户需要的两个角度。"})
    state = client.get(url).json()
    assert state["stage"] == "explore"
    assert state["turns"][-1]["output"]["guardrail_action"] == "template_hint_replacement"
    assert "完整的标准结论" not in state["turns"][-1]["output"]["reply"]
    learning_mock(monkeypatch)
    for _ in range(3):
        client.post(url + "/turns", headers=headers, json={"answer": "我可以举出具体例子并解释概念依据。"})
    assert client.get(url).json()["stage"] == "evaluate"
    assert client.post(url + "/turns", headers=headers, json={"answer": "只解释不做小测"}).status_code == 422
    client.post(
        url + "/turns",
        headers=headers,
        json={"answer": "我尝试解释自己的小测判断依据。", "evaluation_choice": "A"},
    )
    assert client.get(url).json()["status"] == "active"


def test_learning_idempotency_permissions_failure_and_recovery(context, monkeypatch):
    app, client, cid, _ = context
    headers, session = start_learning(context)
    url = f"/api/v1/learning-sessions/{session['id']}"

    def failure(*args):
        raise ModelCallError("MODEL_TIMEOUT", "模型超时")

    monkeypatch.setattr(learning, "complete_json", failure)
    body = {"answer": "这是保存后模型处理失败的原答案。", "request_id": str(uuid4())}
    first = client.post(url + "/turns", headers=headers, json=body)
    second = client.post(url + "/turns", headers=headers, json=body)
    assert first.json()["id"] == second.json()["id"]
    state = client.get(url).json()
    assert len(state["turns"]) == 1 and state["turns"][0]["answer"] == body["answer"]
    assert state["pending_turn_id"] is None
    assert client.post(url + "/turns", headers=headers, json={**body, "answer": "换答案"}).status_code == 409
    other = sign_in(client, "student02")
    assert client.get(url).status_code == 404
    assert client.post(url + "/turns", headers=other, json=body).status_code == 404
    sign_in(client)
    assert client.get(url).status_code == 200
    headers = sign_in(client, "student01")
    with app.state.sessions() as db:
        student_id = db.get(LearningSession, session["id"]).student_id
    turn, _ = learning.save_turn(
        app.state.sessions,
        app.state.settings,
        session["id"],
        student_id,
        LearningAnswer(answer="这轮将在后台进程退出前保存。"),
    )
    with pytest.raises(HTTPException) as error:
        learning.save_turn(
            app.state.sessions,
            app.state.settings,
            session["id"],
            student_id,
            LearningAnswer(answer="并发的另一轮作答不应进入。"),
        )
    assert error.value.status_code == 409
    with app.state.sessions.begin() as db:
        learning.recover_interrupted(db)
    state = client.get(url).json()
    assert state["pending_turn_id"] is None
    assert state["turns"][-1]["error_code"] == "PROCESS_INTERRUPTED"
    assert state["turns"][-1]["id"] == turn["id"]


def test_codex_adapter_prefers_explicit_new_binary_and_disables_tools(context, tmp_path):
    app, _, _, _ = context
    binary = tmp_path / "codex.exe"
    binary.write_text("test placeholder, never executed", encoding="utf-8")
    app.state.settings.c_codex_binary = str(binary)
    app.state.settings.c_llm_model = "gpt-6-luna"
    args = codex_arguments(app.state.settings, tmp_path / "schema.json")
    assert args[0] == str(binary)
    assert args[args.index("--model") + 1] == "gpt-6-luna"
    assert "shell_tool" in args and "apps" in args and "plugins" in args
    assert "--ignore-user-config" in args and "--ephemeral" in args and "read-only" in args
    schema = strict_schema({"type": "object", "properties": {"x": {"type": "string", "default": ""}}})
    assert schema["additionalProperties"] is False and schema["required"] == ["x"]
