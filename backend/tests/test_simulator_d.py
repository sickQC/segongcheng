"""Offline data generation, tamper detection and production synthetic-event isolation."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from scripts.simulate_learning import write_pack
from scripts.validate_simulator import validate_pack
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import LearningEvent
from app.services.learning_events import real_events

ROOT = Path(__file__).resolve().parents[2]


def inputs(small=False):
    config = json.loads((ROOT / "data/simulator/config.json").read_text(encoding="utf-8"))
    topics = json.loads((ROOT / "data/simulator/topics.json").read_text(encoding="utf-8"))
    if small:
        config.update(students_per_type=2, dev_students_per_type=1)
    return config, topics


def rewrite(pack, name, change):
    path = pack / name
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    change(rows)
    raw = ("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode()
    path.write_bytes(raw)
    manifest_path = pack / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["file_sha256"][name] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_full_scale_reproducible_pack_and_separate_truth(tmp_path):
    config, topics = inputs()
    a, b = tmp_path / "a", tmp_path / "b"
    first, second = write_pack(a, config, topics), write_pack(b, config, topics)
    assert first == second
    report = validate_pack(a)
    assert report["students"] == 100 and report["events"] == 5000
    assert report["student_types"] == {p["key"]: 25 for p in config["profiles"]}
    assert report["split_students"] == {"dev": 20, "test": 80}
    assert report["dialogues"] == 100 and report["misconception_episodes"] == 34
    for name in ("students.jsonl", "events.jsonl", "dialogues.jsonl"):
        text = (a / name).read_text(encoding="utf-8")
        assert '"student_type"' not in text and '"true_mastery"' not in text


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "preserved.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_pack(output, *inputs(small=True))
    assert marker.read_text(encoding="utf-8") == "keep"
    assert list(output.iterdir()) == [marker]


def test_non_divisible_event_count_keeps_timestamps_ordered(tmp_path):
    config, topics = inputs(small=True)
    config["events_per_student"] = 51
    pack = tmp_path / "uneven-days"
    write_pack(pack, config, topics)
    assert validate_pack(pack, require_scale=False)["events"] == 8 * 51


def test_missing_scale_and_changed_bytes_rejected(tmp_path):
    pack = tmp_path / "small"
    write_pack(pack, *inputs(small=True))
    assert validate_pack(pack, require_scale=False)["students"] == 8
    with pytest.raises(ValueError, match="formal synthetic scale"):
        validate_pack(pack)
    with (pack / "events.jsonl").open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_pack(pack, require_scale=False)


@pytest.mark.parametrize("change,expected", [
    ("synthetic", "simulator isolation"), ("truth", "leaked"),
    ("actor", "unknown student"), ("grade", "correctness"),
    ("time", "UTC"), ("duplicate", "duplicate event_id"),
    ("resource", "fixtures only"), ("transcript", "transcript"),
])
def test_semantic_tampering_detected_even_after_rehash(tmp_path, change, expected):
    pack = tmp_path / change
    write_pack(pack, *inputs(small=True))

    def mutate(rows):
        if change == "synthetic":
            rows[0]["context"]["synthetic"] = False
        elif change == "truth":
            rows[0]["result"]["true_mastery"] = 0.8
        elif change == "actor":
            rows[0]["actor"] = "unknown"
        elif change == "grade":
            next(r for r in rows if r["object"]["type"] == "assessment")["result"]["correct"] = None
        elif change == "time":
            rows[0]["timestamp"] = "2026-09-01T08:00:00"
        elif change == "duplicate":
            rows[1]["event_id"] = rows[0]["event_id"]
        elif change == "resource":
            next(r for r in rows if r["object"]["type"] == "resource")["result"]["resource_available"] = True
        else:
            rows[0]["turns"][0]["content"] = "tampered"

    rewrite(pack, "dialogues.jsonl" if change == "transcript" else "events.jsonl", mutate)
    with pytest.raises(ValueError, match=expected):
        validate_pack(pack, require_scale=False)


def test_generated_events_cannot_pollute_real_event_reader(tmp_path):
    pack = tmp_path / "isolation"
    write_pack(pack, *inputs(small=True))
    rows = [json.loads(line) for line in (pack / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    selected = [r for r in rows if r["actor"] == rows[0]["actor"]]
    engine = create_engine("sqlite:///:memory:")
    try:
        LearningEvent.__table__.create(engine)
        with Session(engine) as db:
            for row in selected:
                row["timestamp"] = datetime.fromisoformat(row["timestamp"])
                db.add(LearningEvent(**row))
            db.commit()
            assert len(list(db.query(LearningEvent))) == 50
            assert real_events(db, selected[0]["context"]["course"], selected[0]["actor"],
                               selected[0]["timestamp"] - timedelta(days=1),
                               selected[-1]["timestamp"] + timedelta(days=1)) == []
    finally:
        engine.dispose()
