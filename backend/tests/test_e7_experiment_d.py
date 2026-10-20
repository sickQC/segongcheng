"""Verify reproducibility and honest sample accounting, not algorithm superiority."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from scripts import eval_e7_experiment as experiment
from scripts.eval_recommendation import case_plan, schedule, violations


def config():
    return json.loads((Path(__file__).resolve().parents[2]
                       / "data/eval/recommendation/e7-experiment.json").read_text(encoding="utf-8"))


def test_fixed_generator_is_reproducible_and_split_disjoint():
    source = config()
    dataset = experiment.generate(source)
    assert experiment.digest(dataset) == experiment.digest(experiment.generate(source))
    dev = [c for c in dataset["cases"] if c["split"] == "dev"]
    test = [c for c in dataset["cases"] if c["split"] == "test"]
    assert len(dev) == 20 and len(test) == 80
    assert not {c["seed"] for c in dev} & {c["seed"] for c in test}
    assert {p: sum(c["profile"] == p for c in test) for p in source["profiles"]} == {
        p: 20 for p in source["profiles"]
    }
    for case in dataset["cases"]:
        assert len(case["nodes"]) == 30 and len(case["edges"]) == len({tuple(e) for e in case["edges"]}) == 40
        plan = case_plan(case)
        assert plan["status"] == "ready"
        assert not any(violations(case, schedule(plan, strategy, case["budget"]))
                       for strategy in ("baseline", "budgeted"))


def test_overlapping_dev_test_seeds_are_rejected():
    source = config()
    source["test_seed_start"] = source["dev_seed_start"]
    with pytest.raises(ValueError, match="overlap"):
        experiment.generate(source)


@pytest.mark.parametrize("budgets", [[], [0], [241], [True]])
def test_invalid_budgets_rejected(budgets):
    source = config()
    source["budgets"] = budgets
    with pytest.raises(ValueError, match="budgets"):
        experiment.generate(source)


def test_constant_and_reproducible_bootstrap():
    assert experiment.interval([3] * 4, 100, 1) == {
        "mean": 3, "ci95_percentile": [3, 3], "n_scenarios": 4,
    }
    assert experiment.interval([-1, 0, 2, 3], 100, 1) == experiment.interval([-1, 0, 2, 3], 100, 1)


def test_repeat_timings_are_not_counted_as_independent_samples():
    source = config()
    source.update(dev_cases=4, test_cases=4, node_count=6, edge_count=7, repeats=2, bootstrap_resamples=100)
    original = deepcopy(source)
    dataset, result = experiment.run(source)
    assert source == original and len(dataset["cases"]) == 8
    assert all(len(r["scheduling_ms"]) == 2 for r in result["cases"])
    assert all(s["acceptance_rate"] is None for s in result["summary"])
    row = next(r for r in result["intervals"]
               if r["split"] == "test" and r["profile"] == "all" and r["metric"] == "selected_steps")
    assert row["baseline"]["n_scenarios"] == 4
    assert row["paired_delta_budgeted_minus_baseline"]["n_scenarios"] == 4
    baseline = {r["case"]: r for r in result["cases"] if r["split"] == "test" and r["strategy"] == "baseline"}
    budgeted = {r["case"]: r for r in result["cases"] if r["split"] == "test" and r["strategy"] == "budgeted"}
    expected = sum(budgeted[k]["selected_steps"] - baseline[k]["selected_steps"] for k in baseline) / 4
    assert row["paired_delta_budgeted_minus_baseline"]["mean"] == expected
