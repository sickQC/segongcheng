"""Generate explicitly synthetic offline events and separate latent truth; no DB/model access."""

import argparse
import hashlib
import json
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("video", "read", "assessment", "practice", "ask")
FILES = ("students.jsonl", "knowledge_points.jsonl", "events.jsonl", "dialogues.jsonl",
         "truth/students.jsonl", "truth/dialogues.jsonl")


def uid(seed, key):
    return str(uuid5(NAMESPACE_URL, f"se-learning/offline-simulator/{seed}/{key}"))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_config(config):
    if config["version"] != "learning-simulator-v1" or type(config["seed"]) is not int:
        raise ValueError("unsupported simulator version/seed")
    n, e, d = (config[k] for k in ("students_per_type", "events_per_student", "dev_students_per_type"))
    if any(type(v) is not int for v in (n, e, d)) or not 1 <= d < n <= 1000 or not 7 <= e <= 1000:
        raise ValueError("invalid counts; require 1 <= dev < students per type and >=7 events")
    start = datetime.fromisoformat(config["start"])
    if start.tzinfo is None or start.utcoffset() != timedelta(0):
        raise ValueError("start must specify UTC")
    if any(type(config[k]) not in (int, float) or not 0 <= config[k] <= 1 for k in ("slip", "guess")):
        raise ValueError("invalid slip/guess")
    expected = ["strong_active", "weak_active", "low_engagement", "uneven"]
    if [p["key"] for p in config["profiles"]] != expected:
        raise ValueError("four named profiles required")
    for p in config["profiles"]:
        if (len(p["weights"]) != len(KINDS) or any(type(w) is not int or w < 1 for w in p["weights"])
                or not p["mastery_beta"] or any(len(pair) != 2 or any(type(a) is not int or a <= 0 for a in pair)
                                               for pair in p["mastery_beta"])
                or not p["session_days"] or any(type(d) is not int or d < 0 for d in p["session_days"])
                or p["session_days"] != sorted(set(p["session_days"]))
                or len(p["seconds"]) != 2 or not 1 <= p["seconds"][0] <= p["seconds"][1] <= 900):
            raise ValueError("invalid profile parameters")


def generate(config, topics):
    validate_config(config)
    if not topics or len({t["code"] for t in topics}) != len(topics):
        raise ValueError("unique nonempty topics required")
    seed, size = config["seed"], config["events_per_student"]
    course = uid(seed, "course")
    points = [{"id": uid(seed, t["code"]), "code": t["code"], "name": t["name"],
               "course_id": course, "synthetic": True} for t in topics]
    data = {name: [] for name in FILES}
    data["knowledge_points.jsonl"] = points
    for p_index, profile in enumerate(config["profiles"]):
        for number in range(config["students_per_type"]):
            index = p_index * config["students_per_type"] + number
            actor = uid(seed, f"student/{index}")
            split = "dev" if number < config["dev_students_per_type"] else "test"
            latent_rng = random.Random(f"{seed}:latent:{index}")
            rng = random.Random(f"{seed}:observations:{index}")
            mastery = {point["id"]: round(latent_rng.betavariate(
                *profile["mastery_beta"][j % len(profile["mastery_beta"])]), 6)
                for j, point in enumerate(points)}
            student = {"id": actor, "course_id": course, "split": split, "synthetic": True}
            data["students.jsonl"].append(student)
            data["truth/students.jsonl"].append({**student, "student_type": profile["key"],
                                                "true_mastery": mastery})
            topic_index = index % len(topics)
            topic, point = topics[topic_index], points[topic_index]
            misconception = index % 3 == 0
            conversation = uid(seed, f"dialogue/{index}")
            questions = [
                f"我认为{topic['misconception']}，对吗？" if misconception else f"请解释{topic['name']}。",
                topic["followup"],
                f"我的理解是：{topic['correct']}，这个表述合适吗？",
            ]
            dialogue = {"id": conversation, "actor": actor, "course_id": course, "split": split,
                        "synthetic": True, "kp": [point["id"]], "turns": [], "event_ids": []}
            counters = {}
            for i in range(size):
                kind = "ask" if i < 3 else KINDS[i - 3] if i < 7 else rng.choices(KINDS, profile["weights"])[0]
                kp_index = topic_index if i < 3 else rng.randrange(len(points))
                kp, content = points[kp_index], topics[kp_index]
                event_id = uid(seed, f"event/{index}/{i}")
                days = profile["session_days"]
                day_index = min(i * len(days) // size, len(days) - 1)
                first_in_day = math.ceil(day_index * size / len(days))
                timestamp = datetime.fromisoformat(config["start"]) + timedelta(
                    days=days[day_index], seconds=(i - first_in_day) * 300,
                )
                obj = {"id": uid(seed, f"activity/{index}/{i}"), "kp": [kp["id"]]}
                context = {"course": course, "synthetic": True, "source": "learning_simulator",
                           "measurement": "simulated", "generator_version": config["version"]}
                if kind in ("video", "read"):
                    resource = uid(seed, f"resource/{kind}/{kp['id']}")
                    seconds, visits = counters.get(resource, (0, 0))
                    seconds += rng.randint(*profile["seconds"])
                    counters[resource] = (seconds, visits + 1)
                    verb = "viewed"
                    obj.update(id=resource, type="resource", resource_type="video" if kind == "video" else "doc")
                    result = {"effective_seconds": seconds, "coverage": round(min(seconds / 900, 1), 6),
                              "study_visits": visits + 1, "observation_complete": True,
                              "resource_available": False, "simulated_duration_seconds": 900}
                elif kind in ("assessment", "practice"):
                    verb = "answered"
                    probability = mastery[kp["id"]] * (1 - config["slip"]) + (1 - mastery[kp["id"]]) * config["guess"]
                    success = rng.random() < probability
                    obj.update(type=kind, question=f"请判断并说明：{content['correct']}")
                    result = {"answer": content["correct"] if success else content["wrong"],
                              "correct": success if kind == "assessment" else None}
                else:
                    verb = "asked"
                    obj.update(type="question")
                    result = {"question": questions[i] if i < 3 else f"请举例解释{content['name']}。",
                              "assistant_text": content["explanation"]}
                    if i < 3:
                        obj["conversation_id"] = conversation
                        dialogue["event_ids"].append(event_id)
                        dialogue["turns"].extend([
                            {"role": "student", "content": result["question"]},
                            {"role": "assistant", "content": result["assistant_text"]},
                        ])
                data["events.jsonl"].append({"event_id": event_id, "actor": actor, "verb": verb,
                                            "object": obj, "result": result, "context": context,
                                            "timestamp": timestamp.astimezone(UTC).isoformat()})
            data["dialogues.jsonl"].append(dialogue)
            data["truth/dialogues.jsonl"].append({"id": conversation, "actor": actor, "synthetic": True,
                "contains_misconception": misconception,
                "misconception_label": topic["code"] if misconception else None,
                "event_ids": dialogue["event_ids"]})
    return data


def write_pack(output, config, topics):
    data = generate(config, topics)
    output = Path(output)
    # Refuse every existing destination, including partially written previous runs.
    output.mkdir(parents=True, exist_ok=False)
    (output / "truth").mkdir()
    hashes = {}
    for name, rows in data.items():
        raw = ("\n".join(encoded(row) for row in rows) + "\n").encode("utf-8")
        with (output / name).open("xb") as stream:
            stream.write(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    manifest = {
        "version": config["version"], "synthetic": True, "config": config,
        "topics_sha256": hashlib.sha256(encoded(topics).encode()).hexdigest(),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "file_sha256": hashes, "counts": {name: len(rows) for name, rows in data.items()},
        "provenance": "Authored templates and seeded sampling; no observed people, real resources, model calls or DB writes",
        "observation_model": "P(correct)=latent_mastery*(1-slip)+(1-latent_mastery)*guess; fixed latent mastery, no learning gains",
        "truth_boundary": "Only events/dialogues are potential observations; never send truth/, manifest or student types to a model",
        "limitations": "Template dialogue episodes, not distinct human conversations; no actual resource tracking or ground-truth validation on real learners",
    }
    with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "data/simulator/config.json")
    parser.add_argument("--topics", type=Path, default=ROOT / "data/simulator/topics.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/ci/learning-simulator")
    args = parser.parse_args()
    try:
        manifest = write_pack(args.output, json.loads(args.config.read_text(encoding="utf-8")),
                              json.loads(args.topics.read_text(encoding="utf-8")))
    except FileExistsError:
        raise SystemExit("Output already exists; validate it or choose a new output directory. Nothing was overwritten.") from None
    print(json.dumps(manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
