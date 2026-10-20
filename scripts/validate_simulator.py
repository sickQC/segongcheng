"""Independent structural checks for a synthetic event pack; never imports a pack into the app."""

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

try:
    from scripts.simulate_learning import FILES, validate_config
except ModuleNotFoundError:
    from simulate_learning import FILES, validate_config

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {"true_mastery", "student_type", "contains_misconception", "misconception_label"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def no_truth(value):
    if isinstance(value, dict):
        require(not FORBIDDEN.intersection(value), "truth label leaked into observations")
        for item in value.values():
            no_truth(item)
    elif isinstance(value, list):
        for item in value:
            no_truth(item)


def unique(rows, key):
    ids = [r[key] for r in rows]
    require(len(ids) == len(set(ids)), f"duplicate {key}")
    for identifier in ids:
        UUID(identifier)
    return dict(zip(ids, rows))


def validate_pack(directory, require_scale=True):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["synthetic"] is True, "manifest must be synthetic")
    config = manifest["config"]
    validate_config(config)
    require(manifest["version"] == config["version"], "version mismatch")
    require(set(manifest["file_sha256"]) == set(FILES), "unexpected pack file list")
    data = {}
    for name in FILES:
        path = directory / name
        require(path.resolve().is_relative_to(directory) and not path.is_symlink(), "pack path escapes directory")
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == manifest["file_sha256"][name], f"hash mismatch: {name}")
        data[name] = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        require(len(data[name]) == manifest["counts"][name], f"manifest count mismatch: {name}")
    students = unique(data["students.jsonl"], "id")
    points = unique(data["knowledge_points.jsonl"], "id")
    truth = unique(data["truth/students.jsonl"], "id")
    events = unique(data["events.jsonl"], "event_id")
    dialogues = unique(data["dialogues.jsonl"], "id")
    labels = unique(data["truth/dialogues.jsonl"], "id")
    require(set(truth) == set(students), "student truth coverage mismatch")
    require(set(labels) == set(dialogues), "dialogue truth coverage mismatch")
    require(len({p["code"] for p in points.values()}) == len(points), "duplicate knowledge code")
    course_ids = {p["course_id"] for p in points.values()}
    require(len(course_ids) == 1, "single synthetic course required")
    course = next(iter(course_ids))
    UUID(course)
    for name in ("students.jsonl", "knowledge_points.jsonl", "events.jsonl", "dialogues.jsonl"):
        no_truth(data[name])
    type_counts, split_counts = Counter(), Counter()
    for identifier, student in students.items():
        require(student["synthetic"] is True and student["course_id"] == course, "invalid synthetic student")
        label = truth[identifier]
        require(label["synthetic"] is True and label["course_id"] == course, "invalid student truth provenance")
        require(student["split"] == label["split"] and student["split"] in ("dev", "test"), "split mismatch")
        values = label["true_mastery"]
        require(set(values) == set(points), "missing point truth")
        require(all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in values.values()), "invalid mastery truth")
        type_counts[label["student_type"]] += 1
        split_counts[label["student_type"], label["split"]] += 1
    require(type_counts == Counter({p["key"]: config["students_per_type"] for p in config["profiles"]}), "unbalanced student types")
    for key in type_counts:
        require(split_counts[key, "dev"] == config["dev_students_per_type"], "invalid dev allocation")
    for point in points.values():
        require(point["synthetic"] is True, "knowledge fixtures must be synthetic")
    per_actor, kinds = Counter(), Counter()
    last_time, snapshots = {}, {}
    actor_kinds = defaultdict(set)
    for event in events.values():
        actor, obj, result, context = (event[k] for k in ("actor", "object", "result", "context"))
        require(actor in students, "event references unknown student")
        require(context["synthetic"] is True and context["source"] == "learning_simulator"
                and context["measurement"] == "simulated" and context["course"] == course,
                "event must retain simulator isolation")
        require(context["generator_version"] == config["version"], "event generator mismatch")
        require(isinstance(obj["kp"], list) and len(obj["kp"]) == 1 and obj["kp"][0] in points, "invalid event point")
        timestamp = datetime.fromisoformat(event["timestamp"])
        require(timestamp.tzinfo is not None and timestamp.utcoffset() == timedelta(0), "event time must be UTC")
        require(actor not in last_time or timestamp > last_time[actor], "events must be strictly chronological per student")
        last_time[actor] = timestamp
        kind = obj["type"]
        if kind == "resource":
            require(obj["resource_type"] in ("video", "doc") and event["verb"] == "viewed", "invalid resource event")
            kind = "video" if obj["resource_type"] == "video" else "read"
            key = (actor, obj["id"])
            seconds, visits = snapshots.get(key, (0, 0))
            require(type(result["effective_seconds"]) is int and result["effective_seconds"] > seconds,
                    "cumulative resource seconds must increase")
            require(type(result["study_visits"]) is int and result["study_visits"] == visits + 1, "invalid cumulative visits")
            require(result["resource_available"] is False and result["observation_complete"] is True, "resources are fixtures only")
            require(result["coverage"] == round(min(result["effective_seconds"] / 900, 1), 6), "invalid resource coverage")
            snapshots[key] = (result["effective_seconds"], result["study_visits"])
        elif kind in ("assessment", "practice"):
            require(event["verb"] == "answered" and isinstance(result["answer"], str), "invalid answer")
            require(type(result["correct"]) is bool if kind == "assessment" else result["correct"] is None,
                    "objective correctness must be bool, practice must remain ungraded")
        else:
            require(kind == "question" and event["verb"] == "asked" and bool(result["question"]), "invalid dialogue event")
            kind = "ask"
        per_actor[actor] += 1
        kinds[kind] += 1
        actor_kinds[actor].add(kind)
    require(per_actor == Counter({s: config["events_per_student"] for s in students}), "events per student mismatch")
    require(all(k == {"ask", "video", "read", "assessment", "practice"} for k in actor_kinds.values()), "missing activity categories")
    dialogue_actors = Counter()
    misconceptions = 0
    for identifier, dialogue in dialogues.items():
        actor = dialogue["actor"]
        label = labels[identifier]
        require(actor in students and dialogue["synthetic"] is True and dialogue["course_id"] == course, "invalid dialogue actor/provenance")
        require(dialogue["split"] == students[actor]["split"] and set(dialogue["kp"]) <= set(points), "invalid dialogue split/point")
        require(len(dialogue["event_ids"]) == len(set(dialogue["event_ids"])) == 3, "dialogue needs 3 distinct observed events")
        turns = []
        for event_id in dialogue["event_ids"]:
            event = events[event_id]
            require(event["actor"] == actor and event["verb"] == "asked"
                    and event["object"]["conversation_id"] == identifier
                    and event["object"]["kp"] == dialogue["kp"], "dialogue/event mismatch")
            turns.extend([{"role": "student", "content": event["result"]["question"]},
                          {"role": "assistant", "content": event["result"]["assistant_text"]}])
        require(dialogue["turns"] == turns, "transcript does not match observed events")
        require(label["synthetic"] is True and label["actor"] == actor and label["event_ids"] == dialogue["event_ids"], "dialogue label mismatch")
        require(type(label["contains_misconception"]) is bool, "invalid misconception flag")
        if label["contains_misconception"]:
            require(label["misconception_label"] in {p["code"] for p in points.values()}, "invalid misconception label")
            misconceptions += 1
        else:
            require(label["misconception_label"] is None, "unexpected misconception label")
        dialogue_actors[actor] += 1
    require(dialogue_actors == Counter({s: 1 for s in students}), "one complete dialogue per student required")
    if require_scale:
        require(len(students) >= 100 and min(per_actor.values()) >= 50 and misconceptions >= 30,
                "formal synthetic scale requires >=100 students, >=50 events each, >=30 misconception episodes")
    return {"version": manifest["version"], "synthetic": True, "status": "passed",
            "seed": config["seed"], "generator_sha256": manifest["generator_sha256"],
            "manifest_sha256": hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest(),
            "students": len(students), "student_types": dict(type_counts),
            "events": len(events), "events_per_student": config["events_per_student"],
            "split_students": dict(Counter(s["split"] for s in students.values())),
            "event_kinds": dict(kinds), "dialogues": len(dialogues), "misconception_episodes": misconceptions,
            "knowledge_fixtures": len(points), "formal_synthetic_scale_checked": require_scale,
            "truth_labels_excluded_from_observations": True, "file_sha256": manifest["file_sha256"],
            "limitations": "Structural checks only; not human annotation review, real learner data or actual playback/learning validation"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--report", type=Path, default=ROOT / ".local/ci/simulator-validation.json")
    args = parser.parse_args()
    report = validate_pack(args.directory)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "file_sha256"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
