"""评测集加载与 dev / test 划分（供 eval.py 与 calibrate.py 共用）。

为什么要划分
------------
课程《验收标准》第 6 章明确要求："不得在测试集上调参，应区分开发集与测试集"。
本项目把拒答阈值（min_relevance）等**超参数**只在 dev 子集上标定，
最终指标一律在 test 子集上报告。

划分规则是确定性的、可复现的：评测 ID 中的数字为奇数 → dev，偶数 → test。
不随机、不人工挑选，避免"挑选性报告"（否决项 X3）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVAL_PATH = ROOT / "data" / "eval" / "eval_set.jsonl"

CATEGORIES = ("in_scope", "out_of_scope", "injection", "cheating")


def load_cases(path: str | Path) -> list[dict]:
    cases: list[dict] = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def case_split(case: dict) -> str:
    """确定性划分：ID 数字为奇数 → dev，偶数 → test。"""
    digits = re.sub(r"\D", "", str(case.get("id", "")))
    return "dev" if (int(digits) if digits else 0) % 2 == 1 else "test"


def filter_split(cases: list[dict], split: str) -> list[dict]:
    if split == "all":
        return list(cases)
    return [c for c in cases if case_split(c) == split]


def describe(cases: list[dict]) -> str:
    parts = []
    for cat in CATEGORIES:
        n = sum(1 for c in cases if c.get("category") == cat)
        if n:
            parts.append(f"{cat}={n}")
    return f"共 {len(cases)} 题 (" + ", ".join(parts) + ")"
