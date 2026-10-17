"""Replay saved v7 drafts through v8 rules. Offline regression, not a model benchmark."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.evidence_diagnosis import PROMPT_VERSION  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.services.c_model_gateway import ModelReply  # noqa: E402
from app.services.evidence_diagnosis import infer_snapshot  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evaluation/evidence-v8-v7-replay.json")
    args = parser.parse_args()
    source = ROOT / "docs/evaluation/evidence-v7-test-full-reviewed.json"
    dataset = ROOT / "data/eval/learning_diagnosis/v2/test.jsonl"
    original = json.loads(source.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in map(json.loads, dataset.read_text(encoding="utf-8").splitlines())}
    results = []
    settings = Settings()
    for row in original["records"]:
        draft = {"points": row["output"]["points"]}
        with patch(
            "app.services.evidence_diagnosis.complete_json",
            return_value=ModelReply(
                json.dumps(draft, ensure_ascii=False), None, "recorded-v7-offline-replay"
            ),
        ):
            output, _, _ = infer_snapshot(settings, cases[row["id"]]["snapshot"])
        results.append(
            {
                "id": row["id"],
                "expected_type": row["expected_type"],
                "before_type": row["predicted_type"],
                "output": output,
            }
        )
    by_id = {r["id"]: r["output"]["points"][0] for r in results}
    for number in (73, 87):
        point = by_id[f"test-learner-{number:03}"]
        assert point["problem_type"] == "low_engagement" and point["mastery"] is None
    assert "正确7次，错误3次" in by_id["test-learner-093"]["explanation"]
    assert "前八次" not in by_id["test-learner-093"]["explanation"]
    assert (
        "支付平台"
        not in by_id["test-learner-091"]["recommendation"] + by_id["test-learner-091"]["followup_question"]
    )
    for number in (65, 72, 79, 86, 93):
        text = by_id[f"test-learner-{number:03}"]["explanation"]
        assert f"test-learner-{number:03}-event-49" in text and "晚于最近客观答题" in text
    for number in (64, 69, 74, 79, 84, 89, 94):
        question = by_id[f"test-learner-{number:03}"]["followup_question"]
        assert all(term in question for term in ("整数", "包含两端", "步长为1"))
    assert "行为数据未采集" in by_id["test-learner-096"]["explanation"]
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_recorded_output_replay",
        "real_model_calls": 0,
        "prompt_version": PROMPT_VERSION,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "note": "原测试集已用于发现缺陷；本文件仅验证修复回归，不是新模型的独立测试准确率。",
        "source_type_matches": sum(r["before_type"] == r["expected_type"] for r in results),
        "assembled_type_matches": sum(
            r["output"]["points"][0]["problem_type"] == r["expected_type"] for r in results
        ),
        "rule_adjustments": sum(
            any(a["action"] == "apply_verified_behavior_rule" for a in r["output"]["guardrail_actions"])
            for r in results
        ),
        "reviewed_defect_checks_passed": True,
        "records": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("records", "note")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
