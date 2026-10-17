"""C evaluation: default is local input guards; --live explicitly calls the configured model.

No simulated answer is substituted when a real model is missing or fails.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.diagnosis import PROMPT_VERSION  # noqa: E402
from app.agents.diagnosis_guardrails import is_instruction_attack  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.services.diagnosis import call_model  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local" / "c-ai-eval.json"
    )
    args = parser.parse_args()
    settings = Settings()
    if args.live and not (
        settings.llm_api_key.get_secret_value().strip() and settings.llm_model.strip()
    ):
        parser.error("真实评测需要配置 LLM_API_KEY 和 LLM_MODEL；未执行任何模型请求。")
    records = []
    cases = (
        (ROOT / "data" / "eval" / "diagnosis_c.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    for line in cases:
        case = json.loads(line)
        blocked = is_instruction_attack(case["answer"])
        record = {
            "id": case["id"],
            "guard_correct": blocked == case["attack"],
            "blocked": blocked,
        }
        if args.live and not blocked:
            try:
                event_id = str(uuid4())
                output, usage = call_model(
                    settings,
                    event_id,
                    case["answer"],
                    case["question"],
                    "C-EVAL-KP",
                    "评测知识点",
                    case["definition"],
                )
                # Same evidence restriction as the production task runner.
                record["evidence_valid"] = output.evidence_event_ids == [event_id]
                record["status_match"] = output.status == case["expected_status"]
                record["type_match"] = (
                    output.problem_type == case["expected_problem_type"]
                    if case["expected_problem_type"] is not None
                    else None
                )
                record["output"], record["usage"] = output.model_dump(), usage
            except Exception:
                # Third-party exception bodies can contain credentials. Do not persist them.
                record["model_failed"] = True
        records.append(record)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if args.live else "input_guard_only",
        "prompt_version": PROMPT_VERSION,
        "diagnosis_labels_source": "ai_draft_needs_human_review",
        "model": settings.llm_model if args.live else None,
        "case_count": len(records),
        "guard_correct": sum(row["guard_correct"] for row in records),
        "live_successes": sum("output" in row for row in records),
        "live_failures": sum(row.get("model_failed", False) for row in records),
        "requires_human_review": [
            "错误解释是否准确",
            "建议是否可执行",
            "追问是否有针对性且未直接泄露答案",
        ],
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "records"},
            ensure_ascii=False,
        )
    )
    return int(
        any(
            not row["guard_correct"]
            or row.get("model_failed", False)
            or row.get("evidence_valid") is False
            or row.get("status_match") is False
            or row.get("type_match") is False
            for row in records
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
