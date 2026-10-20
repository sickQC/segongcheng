"""Offline multi-seed comparison; never connects to a database or model."""

import argparse
import hashlib
import json
import platform
import random
import sys
from pathlib import Path
from statistics import mean
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.eval_recommendation import case_plan, evaluate, schedule

METRICS = ("selected_steps", "estimated_minutes", "goal_in_plan", "budget_utilization", "mean_scheduling_ms")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def generate(config):
    """Each scenario has its own RNG, graph, observed mastery and estimated costs."""
    if config["generator_version"] != "random-dag-v1":
        raise ValueError("unsupported generator")
    n, e = config["node_count"], config["edge_count"]
    if type(n) is not int or type(e) is not int or not 2 <= n <= 100 or not n - 1 <= e <= n * (n - 1) // 2:
        raise ValueError("invalid graph size")
    if not config["budgets"] or any(type(b) is not int or not 1 <= b <= 240 for b in config["budgets"]):
        raise ValueError("budgets must be integers between 1 and 240")
    if config["profiles"] != ["mostly_unknown", "weak", "mixed", "mostly_mastered"]:
        raise ValueError("unsupported profile definitions")
    cases, used_seeds = [], set()
    for split in ("dev", "test"):
        count = config[f"{split}_cases"]
        if type(count) is not int or count < 1:
            raise ValueError("case count must be positive")
        for i in range(count):
            seed = config[f"{split}_seed_start"] + i
            if seed in used_seeds:
                raise ValueError("dev/test seed overlap")
            used_seeds.add(seed)
            rng = random.Random(seed)
            profile = config["profiles"][i % 4]
            # Random forward spanning tree makes every node an ancestor of the last target.
            edges = {(a, rng.randrange(a + 1, n)) for a in range(n - 1)}
            candidates = [(a, b) for a in range(n) for b in range(a + 1, n) if (a, b) not in edges]
            edges.update(rng.sample(candidates, e - len(edges)))
            nodes = []
            for node in range(n):
                roll = rng.random()
                if profile == "mostly_unknown":
                    mastery = None if roll < 0.75 else round(rng.uniform(0.1, 0.9), 2)
                elif profile == "weak":
                    mastery = None if roll < 0.1 else round(rng.uniform(0.05, 0.5), 2)
                elif profile == "mostly_mastered":
                    mastery = None if roll < 0.1 else round(rng.uniform(0.65, 0.95), 2)
                else:
                    mastery = rng.choice([None, 0.2, 0.5, 0.69, 0.7, 0.85])
                nodes.append({"id": f"N{node:03d}", "minutes": rng.randint(3, 25), "mastery": mastery})
            # Target is pending in all cases to compare useful scheduling, not mastered-target exits.
            nodes[-1]["mastery"] = None
            cases.append({
                "id": f"{split}-{seed}", "seed": seed, "split": split, "profile": profile,
                "target": nodes[-1]["id"], "budget": config["budgets"][(i // 4) % len(config["budgets"])],
                "nodes": nodes, "edges": [[f"N{a:03d}", f"N{b:03d}"] for a, b in sorted(edges)],
            })
    return {"version": config["version"], "source": config["source"], "cases": cases}


def interval(values, resamples, seed):
    """Percentile bootstrap over independent scenarios, never repeated timings."""
    if not values or type(resamples) is not int or not 100 <= resamples <= 100000:
        raise ValueError("nonempty values and >=100 bootstrap resamples required")
    rng = random.Random(seed)
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(resamples))
    return {"mean": mean(values), "ci95_percentile": [
        samples[int(0.025 * (resamples - 1))], samples[int(0.975 * (resamples - 1))],
    ], "n_scenarios": len(values)}


def run(config):
    if type(config["repeats"]) is not int or not 2 <= config["repeats"] <= 100:
        raise ValueError("repeats must be an integer between 2 and 100")
    dataset = generate(config)
    report = evaluate(dataset)
    rows = {(r["case"], r["strategy"]): r for r in report["cases"]}
    for case in dataset["cases"]:
        source = case_plan(case)
        reference = {}
        timings = {"baseline": [], "budgeted": []}
        # Warm up both; alternate measured order to reduce consistent first-run bias.
        for strategy in timings:
            reference[strategy] = schedule(source, strategy, case["budget"])
        for repeat in range(config["repeats"]):
            order = ("baseline", "budgeted") if repeat % 2 == 0 else ("budgeted", "baseline")
            for strategy in order:
                start = perf_counter_ns()
                result = schedule(source, strategy, case["budget"])
                timings[strategy].append((perf_counter_ns() - start) / 1_000_000)
                if result != reference[strategy]:
                    raise ValueError("deterministic scheduler changed across repeats")
        for strategy, samples in timings.items():
            row = rows[case["id"], strategy]
            row.update(profile=case["profile"], seed=case["seed"],
                       budget_utilization=row["estimated_minutes"] / row["budget"],
                       scheduling_ms=samples, mean_scheduling_ms=mean(samples))
    if any(r["prerequisite_violations"] or r["budget_violation"] for r in rows.values()):
        raise ValueError("constraint violations found")
    report["intervals"] = []
    for split in ("dev", "test"):
        cases = [c for c in dataset["cases"] if c["split"] == split]
        groups = [("all", cases)] + [
            (profile, [c for c in cases if c["profile"] == profile]) for profile in config["profiles"]
        ]
        for group, selected in groups:
            if not selected:
                continue
            for metric in METRICS:
                data = {
                    strategy: [rows[c["id"], strategy][metric] for c in selected]
                    for strategy in ("baseline", "budgeted")
                }
                stats = {strategy: interval(values, config["bootstrap_resamples"], config["bootstrap_seed"])
                         for strategy, values in data.items()}
                stats["paired_delta_budgeted_minus_baseline"] = interval(
                    [b - a for a, b in zip(data["baseline"], data["budgeted"])],
                    config["bootstrap_resamples"], config["bootstrap_seed"],
                )
                report["intervals"].append({"split": split, "profile": group, "metric": metric, **stats})
    report.update(
        config=config, dataset_sha256=digest(dataset),
        code_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in [
            "scripts/eval_e7_experiment.py", "scripts/eval_recommendation.py",
            "backend/app/services/budgeted_recommendation.py",
            "backend/app/services/prerequisites.py", "backend/requirements-lock.txt",
        ]},
        environment={"python": platform.python_version(), "os": platform.system(), "architecture": platform.machine()},
        repeats=config["repeats"],
        interval_method="95% percentile bootstrap over scenarios; paired strategy deltas; synthetic generator only",
        timing_scope="pure scheduling only; excludes graph preparation, DB, HTTP and actual learning",
        limitations="Synthetic observed mastery, random DAGs and estimated costs only. Not real students, real teaching prerequisites, latent truth, acceptance or learning outcomes. Deterministic repetitions are not independent samples. No real-student or API-latency inference.",
    )
    return dataset, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "data/eval/recommendation/e7-experiment.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/ci/e7-experiment.json")
    parser.add_argument("--dataset-output", type=Path, default=ROOT / ".local/ci/e7-experiment-input.json")
    args = parser.parse_args()
    dataset, report = run(json.loads(args.config.read_text(encoding="utf-8")))
    for path, value in ((args.dataset_output, dataset), (args.output, report)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("Saved synthetic inputs, per-case outputs, paired intervals and measured scheduling timings.")


if __name__ == "__main__":
    main()
