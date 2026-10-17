"""Regressions for factual rendering, behavior rules and cross-field answer leakage."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.schemas.diagnosis_report import ReportFeedback
from app.services import evidence_diagnosis as service
from app.services.c_model_gateway import ModelCallError, ModelReply
from app.services.diagnosis_presentation import TASKS, verified_behavior

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from build_diagnosis_quality_dev import quality_cases  # noqa: E402

SETTINGS = SimpleNamespace(c_llm_model="test-model", llm_model="test-model")


def case(name):
    return next(c for c in quality_cases() if c["id"] == "quality-" + name)


def infer(monkeypatch, source, kind=None, mutate=None):
    def complete(settings, prompt, data, schema):
        point = data["points"][0]
        chosen = kind or source["expected_type"]
        item = {
            "knowledge_point_id": point["knowledge_point_id"],
            "status": "insufficient" if chosen == "insufficient_evidence" else "supported",
            "mastery": None
            if chosen in ("insufficient_evidence", "low_engagement", "practice_only")
            else 0.4,
            "confidence": 0.8,
            "problem_type": chosen,
            "explanation": "前八次答题均正确，最新对话没有新证据。",
            "recommendation": "支付平台在边界外，因此已经能确定它的分类。",
            "followup_question": "支付平台是不是参与者？",
            "evidence_event_ids": [e["event_id"] for e in point["events"]],
            "citations": [],
        }
        if mutate:
            mutate(item)
        return ModelReply(
            json.dumps({"points": [item]}, ensure_ascii=False), {"total_tokens": 30}, "test-model"
        )

    monkeypatch.setattr(service, "complete_json", complete)
    return service.infer_snapshot(SETTINGS, source["snapshot"])[0]


@pytest.mark.parametrize("name", ["low-two-visits", "low-threshold"])
def test_verified_behavior_survives_unknown_mastery_and_preserves_draft(monkeypatch, name):
    source = case(name)
    before = copy.deepcopy(source)
    output = infer(monkeypatch, source, "insufficient_evidence")
    point = output["points"][0]
    assert point["status"] == "supported" and point["problem_type"] == "low_engagement"
    assert point["mastery"] is None and point["confidence"] is None
    assert output["model_drafts"][0]["problem_type"] == "insufficient_evidence"
    assert output["guardrail_actions"][0]["action"] == "apply_verified_behavior_rule"
    assert output["observed_behaviors"][0]["source"] == "server_rule"
    assert source == before


@pytest.mark.parametrize("name", ["complete-active", "incomplete", "unavailable", "newer-active"])
def test_no_false_behavior_promotion_and_latest_observation_wins(monkeypatch, name):
    source = case(name)
    output = infer(monkeypatch, source, "insufficient_evidence")
    assert output["points"][0]["problem_type"] == "insufficient_evidence"
    assert output["observed_behaviors"] == []
    assert not any(a["action"] == "apply_verified_behavior_rule" for a in output["guardrail_actions"])


def test_old_low_observation_cannot_be_cited_over_a_new_active_window(monkeypatch):
    output = infer(monkeypatch, case("newer-active"), "low_engagement")
    assert output["points"][0]["status"] == "insufficient"
    assert output["guardrail_actions"][0]["code"] == "UNSUPPORTED_BEHAVIOR"


def test_fact_counts_and_latest_dialogue_are_rendered_from_evidence(monkeypatch):
    source = case("recent-conflict")
    output = infer(monkeypatch, source)
    text = output["points"][0]["explanation"]
    assert "正确2次，错误3次" in text and "前八次" not in text
    assert "quality-recent-conflict-5" in text
    assert "我现在认为核对规格应是验证" in text
    assert "晚于最近客观答题" in text
    assert "前八次" in output["model_drafts"][0]["explanation"]
    assert "quality-recent-conflict-5" in output["points"][0]["evidence_event_ids"]


def test_authored_tasks_remove_suggestion_answer_leak_and_define_boundaries(monkeypatch):
    actor = infer(monkeypatch, case("concept-actor"))["points"][0]
    assert "支付平台" not in actor["recommendation"] + actor["followup_question"]
    assert "门禁" in actor["followup_question"]
    assert "是否可能" in actor["followup_question"]
    boundary = infer(monkeypatch, case("concept-boundary"))["points"][0]
    assert all(term in boundary["followup_question"] for term in ("整数", "包含两端", "步长为1", "范围外"))
    assert "5、6、7、13、14、15" not in boundary["followup_question"]
    equivalence = infer(monkeypatch, case("prerequisite"))["points"][0]
    assert "自行划分" in equivalence["followup_question"]
    assert "下限外" not in equivalence["followup_question"]


def test_named_scenario_does_not_become_application_evidence_and_behavior_is_unknown(monkeypatch):
    output = infer(monkeypatch, case("named-scene"))
    text = output["points"][0]["explanation"]
    assert "停车缴费" in text
    assert "已会应用" not in text and "举出" not in text
    assert "行为数据未采集" in text and "未见行为问题" not in text
    assert "迁移应用仍需新任务检验" in text
    assert "纠正" not in text


def test_rule_cannot_repair_foreign_evidence_or_knowledge_scope(monkeypatch):
    source = case("low-two-visits")
    with pytest.raises(ModelCallError, match="INVALID_EVIDENCE"):
        infer(
            monkeypatch,
            source,
            "insufficient_evidence",
            mutate=lambda p: p.update(evidence_event_ids=["someone-elses-event"]),
        )
    with pytest.raises(ModelCallError, match="INVALID_KNOWLEDGE_POINT"):
        infer(
            monkeypatch,
            source,
            "insufficient_evidence",
            mutate=lambda p: p.update(knowledge_point_id="other-course-point"),
        )


def test_raw_prompt_leak_is_rejected_before_normalization(monkeypatch):
    from app.agents.evidence_diagnosis import PROMPT

    with pytest.raises(ModelCallError, match="PROMPT_LEAK"):
        infer(
            monkeypatch,
            case("low-two-visits"),
            "insufficient_evidence",
            mutate=lambda p: p.update(explanation=PROMPT, mastery=0),
        )


@pytest.mark.parametrize("source", list(quality_cases()), ids=lambda c: c["id"])
def test_all_new_development_cases_keep_valid_output_and_input_immutable(monkeypatch, source):
    before = json.dumps(source, sort_keys=True)
    output = infer(monkeypatch, source)
    ReportFeedback.model_validate({"points": output["points"]})
    point = source["snapshot"]["points"][0]
    allowed = {e["event_id"] for e in point["events"]}
    assert set(output["points"][0]["evidence_event_ids"]) <= allowed
    assert json.dumps(source, sort_keys=True) == before
    assert output["presentation_version"] == "diagnosis-presentation-v1"


def test_authored_fallback_supports_new_teacher_topics(monkeypatch):
    source = case("named-scene")
    point = source["snapshot"]["points"][0]
    point.update(code="KP-NEW", knowledge_point_id="new", name="日志完整性")
    result = infer(monkeypatch, source)["points"][0]
    assert "日志完整性" in result["followup_question"]
    assert "先明确场景条件" in result["followup_question"]
    assert len(TASKS) == 5


def test_practice_only_has_priority_for_zero_visits_without_lowering_mastery(monkeypatch):
    source = case("practice")
    output = infer(monkeypatch, source, "no_obvious_issue")
    assert output["points"][0]["problem_type"] == "practice_only"
    assert output["points"][0]["mastery"] == 0.4
    point = source["snapshot"]["points"][0]
    assert verified_behavior(point["events"], point["baseline"])["problem_type"] == "practice_only"


def test_evaluation_keeps_raw_model_and_rule_adjusted_results_separate(monkeypatch):
    from eval_evidence_diagnosis import summary

    output = infer(monkeypatch, case("low-two-visits"), "insufficient_evidence")
    stats = summary(
        [
            {
                "expected_type": "low_engagement",
                "predicted_type": output["points"][0]["problem_type"],
                "raw_predicted_type": output["model_drafts"][0]["problem_type"],
                "model_succeeded": True,
                "model_called": True,
                "rule_adjusted": True,
                "guardrail_downgraded": False,
                "presentation_rendered": True,
                "repeat": 1,
                "latency_ms": 1,
            }
        ]
    )
    assert stats["type_accuracy_including_failures"] == 1
    assert stats["raw_model_type_accuracy"] == 0
    assert stats["rule_adjustments"] == 1 and stats["guardrail_downgrades"] == 0
    assert stats["model_first_pass_valid_rate"] == 0 and stats["presentation_rendered_results"] == 1
