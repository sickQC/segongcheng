"""Fixed synthetic baseline/E7 comparison; never writes learners or calls a model."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from statistics import mean
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.budgeted_recommendation import SCHEDULING_RULE, schedule
from app.services.prerequisites import ordered_graph


def case_plan(case):
    nodes = {n["id"]: n for n in case["nodes"]}
    if len(nodes) != len(case["nodes"]) or case["target"] not in nodes:
        raise ValueError("duplicate/missing case nodes")
    if any(
        type(n["minutes"]) is not int
        or not 1 <= n["minutes"] <= 240
        or (n["mastery"] is not None and not 0 <= n["mastery"] <= 1)
        for n in nodes.values()
    ):
        raise ValueError("invalid case estimates/mastery")
    points = [SimpleNamespace(id=key, code=key) for key in nodes]
    edges = [SimpleNamespace(from_kp_id=a, to_kp_id=b) for a, b in case["edges"]]
    order = ordered_graph(points, edges)
    parents = {key: {a for a, b in case["edges"] if b == key} for key in nodes}
    closure, pending = set(), [case["target"]]
    while pending:
        key = pending.pop()
        if key not in closure:
            closure.add(key)
            pending.extend(parents[key])
    mastered = {
        key
        for key in closure
        if nodes[key]["mastery"] is not None and nodes[key]["mastery"] >= 0.7
    }
    target_mastered = case["target"] in mastered
    steps = [
        {
            "knowledge_point_id": key,
            "code": key,
            "mastery": nodes[key]["mastery"],
            "estimated_minutes": nodes[key]["minutes"],
            "order": i,
        }
        for i, key in enumerate(order, 1)
        if key in closure and key not in mastered and not target_mastered
    ]
    return {
        "target_kp_id": case["target"],
        "status": "target_mastered" if target_mastered else "ready",
        "graph_edges": [
            {"from_kp_id": a, "to_kp_id": b}
            for a, b in case["edges"]
            if a in closure and b in closure
        ],
        "steps": steps,
    }


def violations(case, plan):
    nodes = {n["id"]: n for n in case["nodes"]}
    positions = {s["knowledge_point_id"]: i for i, s in enumerate(plan["steps"])}
    failures = []
    for key, position in positions.items():
        ancestors, pending = set(), [a for a, b in case["edges"] if b == key]
        while pending:
            prior = pending.pop()
            if prior not in ancestors:
                ancestors.add(prior)
                pending.extend(a for a, b in case["edges"] if b == prior)
        for prior in ancestors:
            if (nodes[prior]["mastery"] is None or nodes[prior]["mastery"] < 0.7) and (
                prior not in positions or positions[prior] >= position
            ):
                failures.append([prior, key])
    return failures


def evaluate(dataset):
    results = []
    for case in dataset["cases"]:
        source = case_plan(case)
        for strategy in ("baseline", "budgeted"):
            plan = schedule(source, strategy, case["budget"])
            results.append(
                {
                    "case": case["id"],
                    "split": case["split"],
                    "strategy": strategy,
                    "budget": case["budget"],
                    "selected": [s["knowledge_point_id"] for s in plan["steps"]],
                    "remaining": [
                        s["knowledge_point_id"] for s in plan["remaining_steps"]
                    ],
                    "selected_steps": len(plan["steps"]),
                    "estimated_minutes": plan["estimated_minutes"],
                    "goal_in_plan": plan["goal_in_plan"],
                    "prerequisite_violations": violations(case, plan),
                    "budget_violation": plan["estimated_minutes"] > case["budget"],
                    "selected_weakness_sum": sum(
                        0.5 if s["mastery"] is None else 1 - s["mastery"]
                        for s in plan["steps"]
                    ),
                }
            )
    summary = []
    for split in ("dev", "test"):
        for strategy in ("baseline", "budgeted"):
            rows = [
                r for r in results if r["split"] == split and r["strategy"] == strategy
            ]
            if not rows:
                continue
            summary.append(
                {
                    "split": split,
                    "strategy": strategy,
                    "case_count": len(rows),
                    "mean_selected_steps": mean(r["selected_steps"] for r in rows),
                    "mean_estimated_minutes": mean(
                        r["estimated_minutes"] for r in rows
                    ),
                    "goal_in_plan_rate": mean(r["goal_in_plan"] for r in rows),
                    "mean_budget_utilization": mean(
                        r["estimated_minutes"] / r["budget"] for r in rows
                    ),
                    "prerequisite_violation_count": sum(
                        len(r["prerequisite_violations"]) for r in rows
                    ),
                    "budget_violation_count": sum(r["budget_violation"] for r in rows),
                    "acceptance_rate": None,
                }
            )
    return {
        "dataset_version": dataset["version"],
        "scheduling_rule": SCHEDULING_RULE,
        "limitations": "Authored synthetic cases, deterministic rules and estimated time only. No real learning outcomes or acceptance measurements. No claim of global optimality or superiority on every case.",
        "summary": summary,
        "cases": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "data/eval/recommendation/e7-cases.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local/e7-evaluation.json"
    )
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    report = evaluate(json.loads(raw))
    report["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if any(
        row["prerequisite_violations"] or row["budget_violation"]
        for row in report["cases"]
    ):
        raise SystemExit("Constraint violation found")


if __name__ == "__main__":
    main()
