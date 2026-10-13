"""可观测性：每次智能体调用的 trace 与成本汇总。

对应验收标准：
    AC-NF-14  随机选一次 AI 请求，按 trace ID 可看到输入摘要、检索结果、提示版本、模型、输出、耗时
    AC-NF-4   能按功能汇总调用次数、token 与费用
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path


class Tracer:
    def __init__(self, log_dir: Path, *, enabled: bool = True) -> None:
        self.log_dir = Path(log_dir)
        self.enabled = enabled
        self._lock = threading.Lock()
        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self.log_dir / "trace.jsonl"

    @staticmethod
    def new_trace_id() -> str:
        return f"tr-{uuid.uuid4().hex[:12]}"

    def log(self, record: dict) -> None:
        if not self.enabled:
            return
        record = {**record, "logged_at": time.time()}
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get(self, trace_id: str) -> dict | None:
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("trace_id") == trace_id:
                    return rec
        return None

    def recent(self, limit: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        rows: list[dict] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:]

    def cost_report(self) -> dict:
        """按功能（feature）汇总调用次数、token 与估算费用。"""
        agg: dict[str, dict] = {}
        if not self.path.exists():
            return {"features": {}, "total": {}}
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                feat = rec.get("feature", "unknown")
                row = agg.setdefault(
                    feat,
                    {
                        "calls": 0,
                        "degraded_calls": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "cost_usd": 0.0,
                        "latency_ms_sum": 0.0,
                        "abstained": 0,
                        "blocked_by_guardrail": 0,
                    },
                )
                usage = rec.get("llm", {}) or {}
                row["calls"] += 1
                row["degraded_calls"] += 1 if usage.get("degraded") else 0
                row["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
                row["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
                row["cost_usd"] += float(usage.get("cost_usd", 0.0) or 0)
                row["latency_ms_sum"] += float(usage.get("latency_ms", 0.0) or 0)
                row["abstained"] += 1 if rec.get("abstained") else 0
                gr = rec.get("guardrail", {}) or {}
                row["blocked_by_guardrail"] += 1 if gr.get("action", "allow") != "allow" else 0

        for row in agg.values():
            calls = max(1, row["calls"])
            row["avg_latency_ms"] = round(row["latency_ms_sum"] / calls, 1)
            row["avg_cost_usd"] = round(row["cost_usd"] / calls, 6)
            row["latency_ms_sum"] = round(row["latency_ms_sum"], 1)
            row["cost_usd"] = round(row["cost_usd"], 6)

        total = {
            "calls": sum(r["calls"] for r in agg.values()),
            "prompt_tokens": sum(r["prompt_tokens"] for r in agg.values()),
            "completion_tokens": sum(r["completion_tokens"] for r in agg.values()),
            "cost_usd": round(sum(r["cost_usd"] for r in agg.values()), 6),
        }
        return {"features": agg, "total": total}
