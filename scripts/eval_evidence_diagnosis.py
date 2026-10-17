"""Evaluate held-out diagnosis scenarios, baselines and dialogue/behavior ablations.

Default: offline baseline only. --live makes real model requests, never mock substitutes.
Unreviewed labels require explicit --provisional; such results are not formal acceptance.
"""

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.evidence_diagnosis import PROMPT, PROMPT_VERSION  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.schemas.diagnosis_report import ProblemType  # noqa: E402
from app.services.evidence_diagnosis import infer_snapshot  # noqa: E402
from build_diagnosis_eval import (  # noqa: E402
    DATASET_VERSION,
    DEFAULT_DIRECTORY,
    snapshot_for_variant,
    snapshot_hash,
)

STOP_ERRORS = {
    "CODEX_NOT_INSTALLED",
    "CODEX_START_FAILED",
    "CODEX_AUTH_REQUIRED",
    "CODEX_CONFIGURATION_ERROR",
    "MODEL_NOT_AVAILABLE",
    "MODEL_RATE_LIMITED",
    "MISSING_API_KEY",
    "MISSING_MODEL",
}
KNOWLEDGE_BINARY_TYPES = {"concept_confusion", "prerequisite_gap", "repeated_error", "no_obvious_issue"}


def checked_reviews(directory, cases, variants):
    with (directory / "label-review.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    reviews = {(r["id"], r.get("variant")): r for r in rows}
    if len(reviews) != len(rows):
        raise ValueError("复核表中存在重复样本/变体")
    for case in cases:
        if case.get("dataset_version") != DATASET_VERSION:
            raise ValueError("数据版本不匹配，请使用新版目录；旧结果保留作历史记录")
        for variant in variants:
            review = reviews.get((case["id"], variant))
            if not review or review["expected_type"] not in get_args(ProblemType):
                raise ValueError("复核表缺少样本/变体或存在无效问题类型")
            digest = snapshot_hash(snapshot_for_variant(case["snapshot"], variant))
            if review.get("snapshot_sha256") != digest:
                raise ValueError("复核表与当前证据不匹配；修改数据后需要重新复核")
            expected = "insufficient" if review["expected_type"] == "insufficient_evidence" else "supported"
            if review["expected_status"] != expected:
                raise ValueError("复核表中的状态与问题类型不一致")
    return reviews


def macro_f1(rows):
    labels = sorted({r["expected_type"] for r in rows})
    scores = []
    for label in labels:
        tp = sum(r.get("predicted_type") == label and r["expected_type"] == label for r in rows)
        fp = sum(r.get("predicted_type") == label and r["expected_type"] != label for r in rows)
        fn = sum(r.get("predicted_type") != label and r["expected_type"] == label for r in rows)
        scores.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    return statistics.mean(scores) if scores else None


def baseline_summary(rows):
    eligible = [r for r in rows if r["expected_type"] in KNOWLEDGE_BINARY_TYPES]
    measured = [r for r in eligible if r.get("baseline_support_needed") is not None]
    return {
        "samples": len(rows),
        "knowledge_binary_eligible_samples": len(eligible),
        "binary_target_note": "knowledge support only; behavior and insufficient labels are unscored",
        "measured": len(measured),
        "unknown": len(rows) - len(measured),
        "binary_accuracy": sum(r["baseline_support_needed"] == r["expected_support_needed"] for r in measured)
        / len(measured)
        if measured
        else None,
        "coverage": len(measured) / len(rows) if rows else None,
    }


def summary(rows):
    valid = [r for r in rows if r.get("model_succeeded")]
    called = [r for r in rows if r.get("model_called", (r.get("output") or {}).get("model_called", True))]
    called_valid = [r for r in called if r.get("model_succeeded")]
    binary_eligible = [r for r in rows if r["expected_type"] in KNOWLEDGE_BINARY_TYPES]
    measured = [r for r in binary_eligible if r.get("baseline_support_needed") is not None]
    model_measured = [r for r in binary_eligible if r.get("predicted_mastery") is not None]
    repeats = {}
    for row in rows:
        repeats.setdefault(row["repeat"], []).append(row)
    accuracies = [
        sum(r.get("predicted_type") == r["expected_type"] for r in group) / len(group)
        for group in repeats.values()
    ]
    mean = statistics.mean(accuracies) if accuracies else None
    se = statistics.stdev(accuracies) / math.sqrt(len(accuracies)) if len(accuracies) > 1 else None
    return {
        "samples": len(rows),
        "pipeline_successes": len(valid),
        "model_calls": len(called),
        "local_insufficient_results": len(valid) - len(called_valid),
        "model_successes": len(called_valid),
        "model_failures": len(called) - len(called_valid),
        "guardrail_downgrades": sum(bool(r.get("guardrail_downgraded")) for r in rows),
        "rule_adjustments": sum(bool(r.get("rule_adjusted")) for r in rows),
        "presentation_rendered_results": sum(bool(r.get("presentation_rendered")) for r in rows),
        "raw_model_type_accuracy": sum(
            r.get("raw_predicted_type") == r["expected_type"] for r in rows if r.get("model_called", True)
        )
        / len(called)
        if called and any("raw_predicted_type" in r for r in rows)
        else None,
        "raw_model_metric_note": "original draft labels, before server rules; failures count as incorrect",
        "model_first_pass_valid_rate": sum(
            r.get("model_succeeded", False)
            and not r.get("guardrail_downgraded", False)
            and not r.get("rule_adjusted", False)
            for r in called
        )
        / len(called)
        if called
        else None,
        "type_accuracy_including_failures": sum(r.get("predicted_type") == r["expected_type"] for r in rows)
        / len(rows)
        if rows
        else None,
        "problem_type_macro_f1_including_failures": macro_f1(rows),
        "full_label_retention_rate": sum(
            r.get("predicted_type") == r.get("full_expected_type", r["expected_type"]) for r in rows
        )
        / len(rows)
        if rows
        else None,
        "label_basis": "variant-specific candidate/reviewed labels; full label retention is not accuracy",
        "evidence_valid_rate_including_failures": sum(r.get("evidence_valid", False) for r in rows)
        / len(rows)
        if rows
        else None,
        "baseline_binary_accuracy": sum(
            r["baseline_support_needed"] == r["expected_support_needed"] for r in measured
        )
        / len(measured)
        if measured
        else None,
        "knowledge_binary_eligible_samples": len(binary_eligible),
        "binary_target_note": "knowledge support only; behavior and insufficient labels are unscored",
        "baseline_coverage": len(measured) / len(rows) if rows else None,
        "model_binary_accuracy": sum(
            (r["predicted_mastery"] < 0.7) == r["expected_support_needed"] for r in model_measured
        )
        / len(model_measured)
        if model_measured
        else None,
        "model_binary_coverage": len(model_measured) / len(rows) if rows else None,
        "mean_type_accuracy_across_repeats": mean,
        "accuracy_run_range": [min(accuracies), max(accuracies)] if accuracies else None,
        "accuracy_approx_95_interval": [max(0, mean - 1.96 * se), min(1, mean + 1.96 * se)]
        if se is not None
        else None,
        "interval_note": "normal approximation over run means; few repeats give unreliable intervals",
        "mean_latency_ms": statistics.mean(r["latency_ms"] for r in rows) if rows else None,
        "total_tokens_known": sum((r.get("usage") or {}).get("total_tokens", 0) for r in rows),
        "token_usage_coverage": sum("total_tokens" in (r.get("usage") or {}) for r in called) / len(called)
        if called
        else None,
        "cost": "unknown: no verified unit price configured",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--provisional", action="store_true")
    parser.add_argument("--split", choices=["dev", "test"], default="test")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="0 uses every case; positive limit uses a fixed stratified subset",
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--offset", type=int, default=0, help="skip fixed interleaved cases before applying limit"
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=["full", "no_dialogue", "no_behavior"],
        default=["full", "no_dialogue", "no_behavior"],
    )
    parser.add_argument("--output", type=Path, default=ROOT / ".local/evidence-eval.json")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    if args.repeat < 1 or args.limit < 0 or args.offset < 0:
        parser.error("repeat must be positive and limit must not be negative")
    directory = args.data_dir
    cases = [
        json.loads(line)
        for line in (directory / f"{args.split}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    # Interleave labels for small smoke runs; do not choose cases based on model output.
    groups = {}
    for case in cases:
        groups.setdefault(case["expected_type"], []).append(case)
    cases = [r for i in range(max(map(len, groups.values()))) for g in groups.values() for r in g[i : i + 1]]
    cases = cases[args.offset :]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        parser.error("所选范围没有评测样本")
    selected_variants = args.variants if args.live else ["full"]
    try:
        reviews = checked_reviews(directory, cases, set(selected_variants) | {"full"})
    except ValueError as exc:
        parser.error(str(exc))
    approved = all(
        reviews[c["id"], v]["review_status"] == "approved" and reviews[c["id"], v]["reviewer"].strip()
        for c in cases
        for v in selected_variants
    )
    if args.live and not approved and not args.provisional:
        parser.error("标签尚未人工复核；先填写 label-review.csv，或使用 --provisional 明确运行待审标签冒烟。")
    settings = Settings()
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if args.live else "baseline_only",
        "dataset_split": args.split,
        "dataset_version": DATASET_VERSION,
        "sample_count": len(cases),
        "repeat": args.repeat,
        "labels_human_reviewed": approved,
        "acceptance_status": "reviewed_run" if approved else "provisional_not_formal_acceptance",
        "model": settings.c_llm_model or settings.llm_model,
        "backend": settings.c_llm_backend,
        "prompt_version": PROMPT_VERSION,
        "dataset_sha256": hashlib.sha256((directory / f"{args.split}.jsonl").read_bytes()).hexdigest(),
        "label_review_sha256": hashlib.sha256((directory / "label-review.csv").read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "records": [],
        "summaries": {},
        "planned_records": len(cases) * len(selected_variants) * (args.repeat if args.live else 1),
        "run_complete": False,
    }

    def save():
        report["baseline_summary"] = baseline_summary(report["records"])
        report["summaries"] = {
            v: summary([r for r in report["records"] if r["variant"] == v])
            for v in args.variants
            if args.live
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for run in range(args.repeat if args.live else 1):
        order = list(cases)
        random.Random(92000 + run).shuffle(order)
        for case in order:
            for variant in args.variants if args.live else ["full"]:
                review = reviews[case["id"], variant]
                snapshot = snapshot_for_variant(case["snapshot"], variant)
                baseline = snapshot["points"][0]["baseline"]["accuracy"]
                record = {
                    "id": case["id"],
                    "variant": variant,
                    "repeat": run + 1,
                    "expected_type": review["expected_type"],
                    "full_expected_type": reviews[case["id"], "full"]["expected_type"],
                    "snapshot_sha256": snapshot_hash(snapshot),
                    "expected_status": review["expected_status"],
                    "expected_support_needed": review["expected_type"] != "no_obvious_issue",
                    "baseline_support_needed": baseline < 0.7 if baseline is not None else None,
                    "baseline_accuracy": baseline,
                    "latency_ms": 0,
                }
                if args.live:
                    start = time.perf_counter()
                    try:
                        output, usage, model = infer_snapshot(settings, snapshot)
                        item = output["points"][0]
                        draft = next(
                            (
                                p
                                for p in output.get("model_drafts", [])
                                if p.get("knowledge_point_id") == item["knowledge_point_id"]
                            ),
                            {},
                        )
                        record.update(
                            model_succeeded=True,
                            model_called=output.get("model_called", True),
                            output=output,
                            usage=usage,
                            model=model,
                            predicted_type=item["problem_type"],
                            predicted_status=item["status"],
                            predicted_mastery=item["mastery"],
                            guardrail_downgraded=any(
                                a["action"] in ("downgrade_to_insufficient", "normalize_to_insufficient")
                                for a in output.get("guardrail_actions", [])
                            ),
                            rule_adjusted=any(
                                a["action"] == "apply_verified_behavior_rule"
                                for a in output.get("guardrail_actions", [])
                            ),
                            raw_predicted_type=draft.get("problem_type"),
                            presentation_rendered=bool(output.get("presentation_actions")),
                            evidence_valid=set(item["evidence_event_ids"])
                            <= {e["event_id"] for e in snapshot["points"][0]["events"]},
                        )
                    except Exception as exc:
                        record.update(
                            model_succeeded=False,
                            model_called=True,
                            error_code=getattr(exc, "code", "INVALID_MODEL_RESPONSE"),
                            failure_details=getattr(exc, "details", None),
                        )
                    record["latency_ms"] = round((time.perf_counter() - start) * 1000)
                report["records"].append(record)
                save()
                print(
                    json.dumps(
                        {
                            k: record.get(k)
                            for k in (
                                "id",
                                "variant",
                                "repeat",
                                "model_succeeded",
                                "predicted_type",
                                "error_code",
                            )
                        }
                    ),
                    flush=True,
                )
                if record.get("error_code") in STOP_ERRORS:
                    report["aborted_due_to"] = record["error_code"]
                    save()
                    print("评测停止：当前配置/权限/额度不允许继续调用；失败已记录。", flush=True)
                    return 1
    report["run_complete"] = True
    save()
    print(
        json.dumps(
            {"samples": len(cases), "labels_human_reviewed": approved, "summaries": report["summaries"]},
            ensure_ascii=False,
        )
    )
    return int(args.live and any(not r.get("model_succeeded") for r in report["records"]))


if __name__ == "__main__":
    raise SystemExit(main())
