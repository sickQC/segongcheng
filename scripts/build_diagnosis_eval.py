"""Create reproducible synthetic scenarios and a separate human label-review sheet.

No generated labels are described as human reviewed. No records enter the application DB.
"""

import argparse
import copy
import csv
import hashlib
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.evidence_diagnosis import facts  # noqa: E402

DATASET_VERSION = "learning-diagnosis-v2"
DEFAULT_DIRECTORY = ROOT / "data/eval/learning_diagnosis/v2"
VARIANTS = ("full", "no_dialogue", "no_behavior")


def snapshot_for_variant(snapshot, variant):
    if variant not in VARIANTS:
        raise ValueError("unknown variant")
    result = copy.deepcopy(snapshot)
    excluded = (
        {"dialogue"} if variant == "no_dialogue" else {"behavior"} if variant == "no_behavior" else set()
    )
    for point in result["points"]:
        point["events"] = [e for e in point["events"] if e["source"] not in excluded]
        point["baseline"] = facts(point["events"])
    return result


def snapshot_hash(snapshot):
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


TYPES = (
    "concept_confusion",
    "prerequisite_gap",
    "repeated_error",
    "low_engagement",
    "practice_only",
    "no_obvious_issue",
    "insufficient_evidence",
)
TOPICS = [
    (
        "KP-REQ-01",
        "功能需求与非功能需求",
        "功能需求描述系统做什么，非功能需求约束系统运行质量。",
        "导出报告和响应两秒都是功能需求，不用区分。",
        "功能描述做什么，响应时间属于可测量的质量要求。",
    ),
    (
        "KP-REQ-02",
        "用例与参与者",
        "参与者是系统外部与系统交互的角色，用例描述角色目标。",
        "系统内部的数据库表是它自己的外部参与者。",
        "参与者位于系统边界外，可为人或其他系统。",
    ),
    (
        "KP-VAL-01",
        "验证与确认",
        "验证关注符合规定要求，确认关注满足预期用途和用户需要。",
        "确认检查符合规格，验证检查用户是否满意。",
        "验证核对规格，确认核实预期用途和用户实际需要。",
    ),
    (
        "KP-TEST-01",
        "等价类划分",
        "按预期处理行为划分有效和无效输入类别，分别选择代表值。",
        "年龄十八到六十只测二十、三十、四十就覆盖全部无效类。",
        "应覆盖有效类及低于下限、高于上限的无效类。",
    ),
    (
        "KP-BOUND-01",
        "边界值分析",
        "边界值分析测试边界和紧邻值，注意上下界与内外侧。",
        "只测试范围中间的二十、五十就能发现所有边界错误。",
        "应测试上下边界及紧邻内外侧，分别核对接受或拒绝。",
    ),
]


def scenarios():
    cutoff = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for i in range(100):
        split = "dev" if i < 60 else "test"
        seed = 1700 + i if split == "dev" else 79000 + i
        rng = random.Random(seed)
        code, name, definition, wrong, right = TOPICS[i % len(TOPICS)]
        kind = TYPES[i % len(TYPES)]
        student = f"{split}-learner-{i:03}"
        raw = []
        for j in range(50):
            source = "assessment" if j % 3 == 0 else "dialogue"
            correct, answer = True, right
            if kind == "concept_confusion":
                if source == "dialogue":
                    answer = wrong
                # Correct objective answers conflict with the learner's explanation,
                # not with their own server grade.
                correct = True
            elif kind == "prerequisite_gap":
                answer, correct = "我不能解释题目里基础术语的含义，也说不出判断对象。", False
            elif kind == "repeated_error":
                correct = j < 40
                answer = wrong if source == "assessment" and not correct else right
            elif kind in ("low_engagement", "insufficient_evidence"):
                # Very little usable answer information; behavior only distinguishes one condition.
                source = "assessment" if j == 48 else "dialogue"
                answer, correct = "不知道。", False
                if kind == "insufficient_evidence":
                    source = "assessment" if j == 49 else "dialogue"
            elif kind == "practice_only":
                answer = right
            elif kind == "no_obvious_issue":
                correct = j >= 18
                answer = right if correct else wrong
            event = {
                "event_id": f"{student}-event-{j:02}",
                "source": source,
                "timestamp": (cutoff - timedelta(hours=50 - j)).isoformat(),
                "answer": answer
                + (" 我给出的例子是医院预约。" if split == "test" and len(answer) > 8 else ""),
                "question": "请说明判断依据并举一个新例子。",
                "correct": correct if source == "assessment" else None,
                "prerequisite_check": kind == "prerequisite_gap" and source == "assessment",
            }
            raw.append(event)
        if kind in ("practice_only", "low_engagement"):
            raw[-1] = {
                "event_id": f"{student}-event-49",
                "source": "behavior",
                "timestamp": cutoff.isoformat(),
                "measurement": {
                    "effective_seconds": 0 if kind == "practice_only" else 8,
                    "coverage": 0 if kind == "practice_only" else 0.05,
                    "study_visits": 0 if kind == "practice_only" else 1,
                    "resource_available": True,
                    "observation_complete": True,
                },
            }
        # Alternate chronology/correctness distributions in the held-out split.
        if split == "test":
            for event in raw:
                if event["source"] == "dialogue" and len(event.get("answer", "")) > 8:
                    event["answer"] = "我的判断如下：" + event["answer"]
        rng.shuffle(raw)
        evidence = sorted(raw, key=lambda e: (e["timestamp"], e["event_id"]))[-30:]
        point = {
            "knowledge_point_id": code,
            "code": code,
            "name": name,
            "definition": definition,
            "events": evidence,
            "baseline": facts(evidence),
        }
        expectations = {variant: kind for variant in VARIANTS}
        if kind == "concept_confusion":
            expectations["no_dialogue"] = "no_obvious_issue"
        if kind == "practice_only":
            expectations["no_behavior"] = "no_obvious_issue"
        if kind == "low_engagement":
            expectations["no_behavior"] = "insufficient_evidence"
        yield {
            "id": student,
            "dataset_version": DATASET_VERSION,
            "split": split,
            "scenario_type": kind,
            "data_source": "self_authored_synthetic_scenario",
            "label_review": "pending",
            "expected_type": kind,
            "expected_status": "insufficient" if kind == "insufficient_evidence" else "supported",
            "variant_expectations": expectations,
            "expected_support_needed": kind != "no_obvious_issue",
            "simulated_mastery": 0.85 if kind == "no_obvious_issue" else 0.3,
            "all_events": raw,
            "snapshot": {
                "student_id": student,
                "course_id": "evaluation-only",
                "days": 30,
                "from": (cutoff - timedelta(days=30)).isoformat(),
                "cutoff": cutoff.isoformat(),
                "points": [point],
            },
        }


def write_dataset(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = list(scenarios())
    review_rows = [
        {
            "id": row["id"],
            "variant": variant,
            "snapshot_sha256": snapshot_hash(snapshot_for_variant(row["snapshot"], variant)),
            "expected_type": row["variant_expectations"][variant],
            "expected_status": "insufficient"
            if row["variant_expectations"][variant] == "insufficient_evidence"
            else "supported",
            "review_status": "pending",
            "reviewer": "",
            "notes": "",
        }
        for row in rows
        for variant in VARIANTS
    ]
    review = directory / "label-review.csv"
    # A changed snapshot must never inherit approval of the old evidence.
    if review.exists():
        with review.open(encoding="utf-8-sig", newline="") as stream:
            existing = list(csv.DictReader(stream))
        old_hashes = {(r["id"], r.get("variant")): r.get("snapshot_sha256") for r in existing}
        new_hashes = {(r["id"], r["variant"]): r["snapshot_sha256"] for r in review_rows}
        if old_hashes != new_hashes:
            raise ValueError(
                "Existing review sheet belongs to different evidence; use a new output directory."
            )
    for split in ("dev", "test"):
        path = directory / f"{split}.jsonl"
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows if row["split"] == split),
            encoding="utf-8",
        )
    # Preserve human work if a reviewer has already started.
    if not review.exists():
        with review.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(review_rows[0]),
            )
            writer.writeheader()
            writer.writerows(review_rows)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_version": DATASET_VERSION,
                "files": {
                    name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                    for name in ("dev.jsonl", "test.jsonl")
                },
                "candidate_label_rows": len(review_rows),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "students": len(rows),
                "events": sum(len(r["all_events"]) for r in rows),
                "dialogue_segments": sum(e["source"] == "dialogue" for r in rows for e in r["all_events"]),
                "label_review": "pending; human review required",
                "dataset_version": DATASET_VERSION,
                "directory": str(directory),
            },
            ensure_ascii=False,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIRECTORY)
    write_dataset(parser.parse_args().output_dir)


if __name__ == "__main__":
    main()
