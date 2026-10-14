#!/usr/bin/env python
"""在**开发集**上标定拒答阈值，并输出阈值扫描表。

    python scripts/calibrate.py

背景
----
课程《验收标准》第 6 章要求"不得在测试集上调参，应区分开发集与测试集"。
因此拒答参数只能在 dev 子集上选定，选定结果写回 `src/se_rag/config.py`，
然后在 test 子集上报告最终指标（`python scripts/eval.py --split test`）。

拒答闸门由两个条件共同构成（见 `se_rag.retrieve.is_supporting`）：
    1. relevance >= min_relevance   —— 实词加权覆盖率（连续阈值，需要标定）
    2. key_hit   >= min_key_hit     —— 关键实词命中（结构性规则，不标定）

本脚本只标定第 1 个；第 2 个固定为 0.5，因为它不是靠调参得到的。
评测集的 dev / test 划分是**确定性**的：ID 中的数字为奇数属 dev，偶数属 test。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag import RagConfig, RagIndex  # noqa: E402
from app.rag.evalutil import case_split, load_cases  # noqa: E402
from app.rag.retrieve import HybridRetriever  # noqa: E402

EVAL_PATH = ROOT / "data" / "eval" / "eval_set.jsonl"
GRID = [round(0.20 + 0.05 * i, 2) for i in range(11)]


def main() -> int:
    cfg = RagConfig.from_env()
    min_key_hit = cfg.answer.min_key_hit
    index = RagIndex.load(cfg)
    retriever = HybridRetriever(index, cfg)

    cases = [c for c in load_cases(EVAL_PATH) if case_split(c) == "dev"]
    in_scope = [c for c in cases if c["category"] == "in_scope"]
    out_scope = [c for c in cases if c["category"] == "out_of_scope"]

    def probe(items: list[dict]) -> list[tuple[float, float, str]]:
        rows: list[tuple[float, float, str]] = []
        for c in items:
            hits = retriever.retrieve(c["question"], top_n=6)
            rel = hits[0].relevance if hits else 0.0
            kh = hits[0].key_hit if hits else 0.0
            rows.append((rel, kh, c["id"]))
        return rows

    in_rows = probe(in_scope)
    out_rows = probe(out_scope)

    # 先应用结构性的 key_hit 闸门，再看连续阈值的标定
    in_eff = [(r if kh >= min_key_hit else 0.0, i) for r, kh, i in in_rows]
    out_eff = [(r if kh >= min_key_hit else 0.0, i) for r, kh, i in out_rows]
    blocked_by_key = [i for (_, kh, i) in out_rows if kh < min_key_hit]

    print(f"开发集规模：in_scope={len(in_rows)}  out_of_scope={len(out_rows)}")
    print(f"key_hit 闸门（min_key_hit={min_key_hit}）直接拦下的超范围问题：{blocked_by_key or '无'}\n")

    print("in_scope 相关性最低 5 个：")
    for r, kh, i in sorted(in_rows)[:5]:
        print(f"   rel={r:.3f} key_hit={kh:.2f}  {i}")
    print("out_of_scope 相关性最高 5 个（这些是最难拒答的）：")
    for r, kh, i in sorted(out_rows, reverse=True)[:5]:
        print(f"   rel={r:.3f} key_hit={kh:.2f}  {i}")

    print(f"\n{'阈值':>6} {'回答率':>10} {'拒答率':>10} {'F1':>8}")
    feasible: list[float] = []
    for thr in GRID:
        ar = sum(1 for r, _ in in_eff if r >= thr) / max(1, len(in_eff))
        ra = sum(1 for r, _ in out_eff if r < thr) / max(1, len(out_eff))
        f1 = (2 * ar * ra / (ar + ra)) if (ar + ra) else 0.0
        flag = ""
        if ar >= 0.90 and ra >= 0.80:
            flag = "  ← 满足 AC-M7-2（拒答率≥0.8）且回答率≥0.90"
            feasible.append(thr)
        print(f"{thr:>6.2f} {ar:>10.3f} {ra:>10.3f} {f1:>8.3f}{flag}")

    if not feasible:
        print("\n❌ 没有任何阈值同时满足 回答率≥0.90 且 拒答率≥0.80；需要改进检索或相关性打分。")
        return 1

    # 选阈值的准则：**最大化两类问题的间隔（margin），而不是最大化 dev 上的 F1**。
    # 在开发集上挑 F1 最高的点等价于在 dev 上过拟合，换一批问题就容易翻车。
    max_out = max(r for r, _ in out_eff)
    min_in = min(r for r, _ in in_eff)
    lo, hi = min(feasible), max(feasible)
    if max_out <= 0.0:
        # key_hit 闸门已经把所有超范围问题拦下了，相关性阈值退化为第二道防线。
        # 此时"间隔中点"没有意义（间隔等于整条可行区间）。改为在范围内最低分
        # 之下留出 30% 的余量：既能挡住漏网的超范围问题，又不会误拒范围内的题。
        recommended = min(max(round(0.7 * min_in, 2), lo), hi)
        print(
            f"\nkey_hit 闸门已完全分离两类问题（超范围最高分={max_out:.3f}），"
            f"相关性阈值作为第二道防线，取范围内最低分 {min_in:.3f} 的 70% 保留余量。"
        )
    elif min_in > max_out:
        mid = (max_out + min_in) / 2
        recommended = min(max(round(mid, 2), lo), hi)
        print(
            f"\n两类问题的相关性间隔：超范围最高={max_out:.3f}，范围内最低={min_in:.3f}，"
            f"间隔={min_in - max_out:.3f}（越大越稳健）"
        )
    else:
        recommended = lo
        print(
            f"\n⚠️  两类问题存在重叠（超范围最高={max_out:.3f} ≥ 范围内最低={min_in:.3f}），"
            "只能取保守阈值。"
        )

    print(f"✅ 建议 min_relevance = {recommended}（可行区间 {lo}~{hi}）")
    print(f"   当前配置值：{cfg.answer.min_relevance}")
    if abs(cfg.answer.min_relevance - recommended) > 0.02:
        print("   ⚠️  与配置不一致，请更新 src/se_rag/config.py 中的 min_relevance")
    else:
        print("   ✓ 与当前配置一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
