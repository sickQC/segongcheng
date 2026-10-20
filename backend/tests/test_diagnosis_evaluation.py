"""Regression checks for evaluation evidence, review binding and model failures."""

import csv
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import c_model_gateway as gateway
from app.services import evidence_diagnosis as diagnosis

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import eval_evidence_diagnosis as evaluation  # noqa: E402
from build_diagnosis_eval import (  # noqa: E402
    TOPICS,
    scenarios,
    snapshot_for_variant,
    write_dataset,
)
from eval_evidence_diagnosis import checked_reviews, summary  # noqa: E402


def test_objective_grades_agree_with_answer_text_and_pattern_evidence():
    for case in scenarios():
        wrong = next(t[3] for t in TOPICS if t[0] == case["snapshot"]["points"][0]["code"])
        for event in case["all_events"]:
            if event["source"] != "assessment":
                continue
            if event["answer"].startswith(wrong):
                assert event["correct"] is False
            elif event["answer"].startswith(("不知道", "我不能解释")):
                assert event["correct"] is False
            else:
                assert event["correct"] is True
        baseline = case["snapshot"]["points"][0]["baseline"]
        if case["expected_type"] == "concept_confusion":
            assert baseline["accuracy"] == 1
            assert any(
                e["answer"].startswith((wrong, "我的判断如下：" + wrong))
                for e in case["all_events"]
                if e["source"] == "dialogue"
            )
        if case["expected_type"] == "repeated_error":
            assert baseline["wrong_count"] >= 3 and baseline["latest_correct"] is False
        if case["expected_type"] == "low_engagement":
            assert baseline["graded_count"] == 1 and baseline["behavior_available"]


def test_ablation_removes_all_features_of_excluded_sources_without_mutation():
    cases = {c["expected_type"]: c for c in scenarios()}
    concept = cases["concept_confusion"]
    original = json.dumps(concept["snapshot"], sort_keys=True)
    reduced = snapshot_for_variant(concept["snapshot"], "no_dialogue")
    assert reduced["points"][0]["baseline"]["dialogue_count"] == 0
    assert reduced["points"][0]["baseline"]["accuracy"] == 1
    assert concept["variant_expectations"]["no_dialogue"] == "no_obvious_issue"
    assert json.dumps(concept["snapshot"], sort_keys=True) == original
    for kind in ("low_engagement", "practice_only"):
        case = cases[kind]
        point = snapshot_for_variant(case["snapshot"], "no_behavior")["points"][0]
        assert not point["baseline"]["behavior_available"]
        assert point["baseline"]["behavior_observations"] == []
    assert cases["low_engagement"]["variant_expectations"]["no_behavior"] == "insufficient_evidence"
    assert cases["practice_only"]["variant_expectations"]["no_behavior"] == "no_obvious_issue"


def test_reviews_bind_to_each_variant_and_cannot_survive_evidence_changes(tmp_path):
    write_dataset(tmp_path)
    cases = list(scenarios())
    reviews = checked_reviews(tmp_path, cases, ["full", "no_dialogue", "no_behavior"])
    assert len(reviews) == 300 and all(r["review_status"] == "pending" for r in reviews.values())
    path = tmp_path / "label-review.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0].update(review_status="approved", reviewer="test-only-reviewer")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    before = path.read_bytes()
    write_dataset(tmp_path)
    assert path.read_bytes() == before
    cases[0]["snapshot"]["points"][0]["events"][0]["answer"] = "changed"
    with pytest.raises(ValueError, match="不匹配"):
        checked_reviews(tmp_path, cases, ["full"])
    rows[0]["snapshot_sha256"] = "old-evidence"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    dataset_before = (tmp_path / "dev.jsonl").read_bytes()
    with pytest.raises(ValueError, match="different evidence"):
        write_dataset(tmp_path)
    assert (tmp_path / "dev.jsonl").read_bytes() == dataset_before


def test_ablation_accuracy_and_original_label_retention_are_separate():
    result = summary(
        [
            {
                "expected_type": "no_obvious_issue",
                "full_expected_type": "concept_confusion",
                "predicted_type": "no_obvious_issue",
                "repeat": 1,
                "latency_ms": 1,
                "model_succeeded": True,
            }
        ]
    )
    assert result["type_accuracy_including_failures"] == 1
    assert result["full_label_retention_rate"] == 0
    behavior = summary(
        [
            {
                "expected_type": "practice_only",
                "predicted_type": "practice_only",
                "repeat": 1,
                "latency_ms": 1,
                "model_succeeded": True,
                "baseline_support_needed": False,
                "predicted_mastery": 0.95,
                "expected_support_needed": True,
            }
        ]
    )
    assert behavior["knowledge_binary_eligible_samples"] == 0
    assert behavior["baseline_binary_accuracy"] is None and behavior["model_binary_accuracy"] is None


@pytest.mark.parametrize(
    "text,code,retryable",
    [
        ("401 unauthorized", "CODEX_AUTH_REQUIRED", False),
        ("429 usage limit exceeded", "MODEL_RATE_LIMITED", False),
        ("model is not supported", "MODEL_NOT_AVAILABLE", False),
        ("unexpected argument --ignore-user-config", "CODEX_CONFIGURATION_ERROR", False),
        ("stream disconnected: connection reset", "MODEL_CONNECTION_ERROR", True),
        ("unclassified failure", "CODEX_UNAVAILABLE", False),
    ],
)
def test_failure_classification_never_exposes_raw_output(text, code, retryable):
    error = gateway.codex_failure(text + " SECRET_TOKEN private/student/answer", 1)
    assert error.code == code and error.details["retryable"] is retryable
    assert "SECRET_TOKEN" not in str(error) + error.message + json.dumps(error.details)
    assert error.details["exit_code"] == 1


@pytest.mark.parametrize(
    "returncode,stdout,stderr,expected",
    [
        (1, "", "401 unauthorized SECRET_TOKEN", "CODEX_AUTH_REQUIRED"),
        (0, '{"type":"turn.failed","error":{"message":"429 quota exceeded"}}', "", "MODEL_RATE_LIMITED"),
    ],
)
def test_codex_adapter_uses_both_error_channels_and_releases_slot(
    tmp_path, monkeypatch, returncode, stdout, stderr, expected
):
    settings = SimpleNamespace(c_codex_timeout_seconds=1, c_llm_model="test-model")
    monkeypatch.setattr(gateway, "ROOT", tmp_path)
    monkeypatch.setattr(gateway, "codex_arguments", lambda *a: ["test"])
    process = SimpleNamespace(returncode=returncode, communicate=lambda *a, **kw: (stdout, stderr))
    monkeypatch.setattr(gateway.subprocess, "Popen", lambda *a, **kw: process)
    with pytest.raises(gateway.ModelCallError) as failure:
        gateway.call_codex(settings, "prompt", {}, {})
    assert failure.value.code == expected
    assert "SECRET_TOKEN" not in failure.value.message
    assert gateway._CODEX_SLOT.acquire(blocking=False)
    gateway._CODEX_SLOT.release()


def test_cli_discovery_tracks_app_updates_but_never_silently_ignores_explicit_path(tmp_path, monkeypatch):
    settings = SimpleNamespace(c_codex_binary="", c_llm_model="test-model")
    monkeypatch.delenv("CODEX_CLI_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    binaries = []
    for name, modified in (("old", 100), ("new", 200)):
        path = tmp_path / "OpenAI/Codex/bin" / name / "codex.exe"
        path.parent.mkdir(parents=True)
        path.touch()
        os.utime(path, (modified, modified))
        binaries.append(path)
    assert gateway.codex_arguments(settings, tmp_path / "schema.json")[0] == str(binaries[1])
    settings.c_codex_binary = str(tmp_path / "removed-by-update.exe")
    with pytest.raises(gateway.ModelCallError, match="CODEX_NOT_INSTALLED"):
        gateway.codex_arguments(settings, tmp_path / "schema.json")


def test_eval_stops_on_unavailable_model_and_rejects_unreviewed_formal_run(tmp_path, monkeypatch):
    write_dataset(tmp_path)
    output = tmp_path / "result.json"
    argv = [
        "eval",
        "--live",
        "--split",
        "dev",
        "--limit",
        "7",
        "--repeat",
        "2",
        "--data-dir",
        str(tmp_path),
        "--output",
        str(output),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    calls = []

    def unavailable(*args):
        calls.append(args)
        raise gateway.ModelCallError("MODEL_NOT_AVAILABLE", "test-only failure")

    monkeypatch.setattr(evaluation, "infer_snapshot", unavailable)
    monkeypatch.setattr(
        evaluation,
        "Settings",
        lambda: SimpleNamespace(c_llm_model="test-model", llm_model="test-model", c_llm_backend="codex"),
    )
    with pytest.raises(SystemExit) as rejected:
        evaluation.main()
    assert rejected.value.code == 2 and calls == [] and not output.exists()
    monkeypatch.setattr(sys, "argv", argv + ["--provisional"])
    assert evaluation.main() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(calls) == len(report["records"]) == 1
    assert report["planned_records"] == 42 and report["run_complete"] is False
    assert report["aborted_due_to"] == "MODEL_NOT_AVAILABLE"


@pytest.mark.parametrize(
    "text,phase",
    [
        ('{"points":', "json_decode"),
        ('{"points":[{"private_answer_SECRET": "secret"}]}', "schema_validation"),
    ],
)
def test_invalid_model_structure_has_safe_actionable_error_details(monkeypatch, text, phase):
    monkeypatch.setattr(diagnosis, "complete_json", lambda *a: gateway.ModelReply(text, None, "test-model"))
    case = next(scenarios())
    settings = SimpleNamespace(c_llm_model="test-model", llm_model="test-model")
    with pytest.raises(gateway.ModelCallError) as failure:
        diagnosis.infer_snapshot(settings, case["snapshot"])
    assert failure.value.code == "INVALID_MODEL_RESPONSE"
    assert failure.value.details["phase"] == phase
    assert "SECRET" not in json.dumps(failure.value.details)
