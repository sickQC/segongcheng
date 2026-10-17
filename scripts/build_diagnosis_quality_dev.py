"""New development regressions for reviewed diagnosis defects; never human-approved labels."""

import csv
import json
from datetime import datetime, timedelta, timezone

from build_diagnosis_eval import DATASET_VERSION, ROOT, snapshot_hash

DIRECTORY = ROOT / "data/eval/diagnosis_quality_dev"
TOPICS = {
    "KP-REQ-01": ("功能需求与非功能需求", "功能说明系统提供的行为，非功能要求约束质量并应能检查。"),
    "KP-REQ-02": ("用例与参与者", "参与者是边界外与系统交互的角色，用例对应角色的目标。"),
    "KP-VAL-01": ("验证与确认", "验证核对规定要求，确认检查预期用途和用户需要。"),
    "KP-TEST-01": ("等价类划分", "按输入条件与预期处理行为分组，为有效和无效类别选代表值。"),
    "KP-BOUND-01": ("边界值分析", "按取值域、端点包含性和精度检查边界及相邻位置。"),
}


def quality_cases():
    cutoff = datetime(2026, 10, 15, tzinfo=timezone.utc)

    def make(name, code, expected, answers, measurement=None, older_measurement=None):
        events = []
        for i, (source, answer, correct, prerequisite) in enumerate(answers):
            events.append(
                {
                    "event_id": f"quality-{name}-{i}",
                    "source": source,
                    "timestamp": (cutoff - timedelta(minutes=20 - i)).isoformat(),
                    "question": "请结合场景解释你的判断。",
                    "answer": answer,
                    "correct": correct,
                    "prerequisite_check": prerequisite,
                }
            )
        for i, measured in enumerate([m for m in (older_measurement, measurement) if m is not None]):
            events.append(
                {
                    "event_id": f"quality-{name}-observation-{i}",
                    "source": "behavior",
                    "timestamp": (cutoff - timedelta(minutes=2 - i)).isoformat(),
                    "measurement": measured,
                }
            )
        # Facts used by the model are recomputed by the service, not labels.
        from app.services.evidence_diagnosis import facts

        topic, definition = TOPICS[code]
        return {
            "id": f"quality-{name}",
            "split": "dev",
            "dataset_version": DATASET_VERSION,
            "data_source": "new_self_authored_development_regression",
            "label_review": "pending",
            "expected_type": expected,
            "snapshot": {
                "student_id": f"quality-{name}",
                "course_id": "development-only",
                "days": 30,
                "cutoff": cutoff.isoformat(),
                "from": (cutoff - timedelta(days=30)).isoformat(),
                "points": [
                    {
                        "knowledge_point_id": code,
                        "code": code,
                        "name": topic,
                        "definition": definition,
                        "events": events,
                        "baseline": facts(events),
                    }
                ],
            },
        }

    def observed(**changes):
        return {
            "coverage": 0.12,
            "effective_seconds": 53,
            "study_visits": 2,
            "resource_available": True,
            "observation_complete": True,
            **changes,
        }

    unknown = [
        ("dialogue", "还不能说清楚判断过程。", None, False),
        ("assessment", "我暂时无法给出答案。", False, False),
        ("dialogue", "需要再学一下才知道怎么做。", None, False),
    ]
    positive = [
        ("assessment", "导出清单是系统行为，限时响应是质量约束。", True, False),
        ("dialogue", "我会用响应耗时的分位数检查该质量要求。", None, False),
    ]
    yield make("low-two-visits", "KP-REQ-01", "low_engagement", unknown, observed())
    yield make(
        "low-threshold",
        "KP-VAL-01",
        "low_engagement",
        unknown,
        observed(coverage=0.2, effective_seconds=119, study_visits=3),
    )
    yield make(
        "complete-active",
        "KP-REQ-01",
        "no_obvious_issue",
        positive,
        observed(coverage=0.82, effective_seconds=720, study_visits=4),
    )
    yield make(
        "incomplete", "KP-REQ-02", "insufficient_evidence", unknown, observed(observation_complete=False)
    )
    yield make(
        "unavailable", "KP-TEST-01", "insufficient_evidence", unknown, observed(resource_available=False)
    )
    yield make(
        "newer-active",
        "KP-REQ-01",
        "no_obvious_issue",
        positive,
        observed(coverage=0.8, effective_seconds=600),
        observed(),
    )
    yield make(
        "practice",
        "KP-REQ-02",
        "practice_only",
        [("assessment", "边界外的角色通过交互完成目标。", True, False)] * 4
        + [("dialogue", "在停车登记服务中，用户希望登记车牌以进入场馆。", None, False)],
        observed(coverage=0, effective_seconds=0, study_visits=0),
    )
    yield make(
        "recent-conflict",
        "KP-VAL-01",
        "repeated_error",
        [("assessment", "核对规格是验证。", True, False)] * 2
        + [("assessment", "核对规格是确认，用户用途是验证。", False, False)] * 3
        + [("dialogue", "我现在认为核对规格应是验证，检查用户用途应是确认。", None, False)],
    )
    yield make(
        "prerequisite",
        "KP-TEST-01",
        "prerequisite_gap",
        [("assessment", "无法说出输入条件和处理结果。", False, True)] * 2
        + [("dialogue", "还不懂什么是输入的预期处理行为。", None, False)],
    )
    yield make(
        "concept-boundary",
        "KP-BOUND-01",
        "concept_confusion",
        [("assessment", "应按取值域和精度检查边界及附近位置。", True, False)] * 3
        + [("dialogue", "只要测试9到15之间的中间值就能保证边界没有问题。", None, False)],
    )
    yield make(
        "concept-actor",
        "KP-REQ-02",
        "concept_confusion",
        [("assessment", "参与者是系统外部交互角色。", True, False)] * 2
        + [("dialogue", "任何内部缓存键都是这个系统自己的外部参与者。", None, False)],
    )
    yield make(
        "named-scene",
        "KP-REQ-02",
        "no_obvious_issue",
        [
            ("assessment", "参与者是边界外的交互角色。", True, False),
            ("dialogue", "参与者位于边界外。我想到的场景名称是停车缴费。", None, False),
        ],
    )
    yield make("insufficient", "KP-BOUND-01", "insufficient_evidence", unknown)


def main():
    rows = list(quality_cases())
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = DIRECTORY / "dev.jsonl"
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise ValueError("Development data changed; write a new version instead of replacing it")
    path.write_text(text, encoding="utf-8")
    review = DIRECTORY / "label-review.csv"
    if not review.exists():
        with review.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "id",
                    "variant",
                    "snapshot_sha256",
                    "expected_type",
                    "expected_status",
                    "review_status",
                    "reviewer",
                    "notes",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "id": row["id"],
                        "variant": "full",
                        "snapshot_sha256": snapshot_hash(row["snapshot"]),
                        "expected_type": row["expected_type"],
                        "expected_status": "insufficient"
                        if row["expected_type"] == "insufficient_evidence"
                        else "supported",
                        "review_status": "pending",
                        "reviewer": "",
                        "notes": "新编开发回归，未人工审核",
                    }
                )
    print(json.dumps({"cases": len(rows), "directory": str(DIRECTORY), "human_reviewed": False}))


if __name__ == "__main__":
    main()
