#!/usr/bin/env python
"""评测脚本：端到端指标 + 检索消融。

    python scripts/eval.py                  # 跑全部
    python scripts/eval.py --mode retrieve  # 只跑检索指标与消融（不需要大模型）
    python scripts/eval.py --mode answer    # 只跑端到端（需要大模型或离线兜底）

输出：data/eval/report.json + 终端 Markdown 表。

指标定义
--------
doc_hit@k     期望文档出现在 top-k 检索结果中的比例
term_hit@k    top-k 证据文本中包含期望关键词的比例（比 doc_hit 更严格）
MRR           第一个命中期望文档的排名的倒数均值
abstain_acc   超范围问题被正确拒答（检索相关性低于阈值）的比例
citation_acc  回答中 [n] 指向真实证据片段的比例
injection_block / cheat_refuse  护栏拦截率
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag import RagConfig, RagIndex, TutorRAG  # noqa: E402
from app.rag.evalutil import case_split, describe, filter_split, load_cases  # noqa: E402
from app.rag.retrieve import HybridRetriever, is_supporting  # noqa: E402
from app.rag.textutil import normalize  # noqa: E402

EVAL_PATH = ROOT / "data" / "eval" / "eval_set.jsonl"


def _set_dotted(obj, dotted: str, value) -> None:
    parts = dotted.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    setattr(obj, parts[-1], value)


def build_index_with(base_cfg: RagConfig, overrides: dict) -> RagIndex:
    cfg = copy.deepcopy(base_cfg)
    for k, v in overrides.items():
        _set_dotted(cfg, k, v)
    return RagIndex(cfg).build()


# ------------------------------------------------------------- 检索层评测
def evaluate_retrieval(index: RagIndex, cases: list[dict], top_n: int = 6) -> dict:
    retr = HybridRetriever(index, index.cfg)

    hit3 = hit6 = term6 = 0
    rr_sum = 0.0
    n_in = 0
    abstain_ok = 0
    n_out = 0
    per_case: list[dict] = []

    for c in cases:
        cat = c["category"]
        if cat == "in_scope":
            n_in += 1
            hits = retr.retrieve(c["question"], top_n=max(top_n, 10))
            docs = [h.chunk.doc_id for h in hits]
            expected = set(c.get("expected_docs", []))
            rank = next((i for i, d in enumerate(docs, start=1) if d in expected), None)
            text = "\n".join(h.evidence_text for h in hits[:top_n])
            terms = c.get("expected_terms", [])
            term_ok = bool(terms) and all(t.lower() in normalize(text).lower() for t in terms)
            hit3 += 1 if rank and rank <= 3 else 0
            hit6 += 1 if rank and rank <= top_n else 0
            term6 += 1 if term_ok else 0
            rr_sum += (1.0 / rank) if rank else 0.0
            per_case.append(
                {
                    "id": c["id"],
                    "rank": rank,
                    "term_hit": term_ok,
                    "top_docs": docs[:top_n],
                }
            )
        elif cat == "out_of_scope":
            n_out += 1
            hits = retr.retrieve(c["question"], top_n=top_n)
            supporting = [h for h in hits if is_supporting(h, index.cfg)]
            if len(supporting) < index.cfg.answer.min_supporting_chunks:
                abstain_ok += 1
            per_case.append(
                {
                    "id": c["id"],
                    "abstained": len(supporting) < index.cfg.answer.min_supporting_chunks,
                    "top_relevance": round(hits[0].relevance, 4) if hits else 0.0,
                    "top_key_hit": round(hits[0].key_hit, 4) if hits else 0.0,
                }
            )

    return {
        "n_in_scope": n_in,
        "n_out_of_scope": n_out,
        "doc_hit@3": round(hit3 / n_in, 4) if n_in else 0.0,
        f"doc_hit@{top_n}": round(hit6 / n_in, 4) if n_in else 0.0,
        f"term_hit@{top_n}": round(term6 / n_in, 4) if n_in else 0.0,
        "MRR": round(rr_sum / n_in, 4) if n_in else 0.0,
        "abstain_acc": round(abstain_ok / n_out, 4) if n_out else 0.0,
        "per_case": per_case,
    }


# --------------------------------------------------------------- 端到端评测
def evaluate_answers(rag: TutorRAG, cases: list[dict], top_n: int = 6) -> dict:
    n_in = n_out = n_inj = n_cheat = 0
    answered = cited = 0
    cite_acc: list[float] = []
    abstain_ok = 0
    blocked = refused = 0
    latencies: list[float] = []
    costs = 0.0
    per_case: list[dict] = []

    for c in cases:
        t0 = time.perf_counter()
        res = rag.answer(c["question"], top_n=top_n)
        latencies.append((time.perf_counter() - t0) * 1000)
        costs += float(res.llm.get("cost_usd", 0.0) or 0.0)
        action = res.guardrail.get("action", "allow")
        row = {"id": c["id"], "category": c["category"], "action": action, "abstained": res.abstained}

        if c["category"] == "in_scope":
            n_in += 1
            answered += 1 if not res.abstained else 0
            cited += 1 if res.citation_report.get("has_citation") else 0
            cite_acc.append(res.citation_report.get("accuracy", 0.0))
            row["citation_accuracy"] = res.citation_report.get("accuracy")
        elif c["category"] == "out_of_scope":
            n_out += 1
            abstain_ok += 1 if res.abstained else 0
        elif c["category"] == "injection":
            n_inj += 1
            blocked += 1 if action == "block" else 0
        elif c["category"] == "cheating":
            n_cheat += 1
            refused += 1 if action == "refuse_cheat" else 0
        per_case.append(row)

    lat_sorted = sorted(latencies)
    p50 = lat_sorted[len(lat_sorted) // 2] if lat_sorted else 0.0
    p95 = lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * 0.95))] if lat_sorted else 0.0

    return {
        "provider": rag.cfg.llm.provider,
        "model": rag.cfg.llm.model if rag.cfg.llm.provider == "openai" else "offline-extractive",
        "n_in_scope": n_in,
        "answer_rate": round(answered / n_in, 4) if n_in else 0.0,
        "citation_rate": round(cited / n_in, 4) if n_in else 0.0,
        "citation_accuracy_mean": round(statistics.mean(cite_acc), 4) if cite_acc else 0.0,
        "n_out_of_scope": n_out,
        "refusal_accuracy": round(abstain_ok / n_out, 4) if n_out else 0.0,
        "n_injection": n_inj,
        "injection_block_rate": round(blocked / n_inj, 4) if n_inj else 0.0,
        "n_cheating": n_cheat,
        "cheat_refuse_rate": round(refused / n_cheat, 4) if n_cheat else 0.0,
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "total_cost_usd": round(costs, 6),
        "per_case": per_case,
    }


# ------------------------------------------------------------------ 消融实验
ABLATIONS: list[tuple[str, dict]] = [
    ("baseline（混合检索+重排）", {}),
    ("仅稠密向量", {"retrieval.top_k_sparse": 0}),
    ("仅BM25稀疏", {"retrieval.top_k_dense": 0}),
    ("关闭重排（只用RRF）", {"retrieval.use_rerank": False}),
    ("关闭同义词扩展", {"retrieval.use_synonym_expansion": False}),
    ("chunk=300字符", {"chunk.target_size": 300}),
    ("chunk=800字符", {"chunk.target_size": 800}),
    ("关闭 small-to-big 父块扩展", {"retrieval.use_parent_expansion": False}),
]


def run_ablations(base_cfg: RagConfig, cases: list[dict], top_n: int = 6) -> list[dict]:
    in_scope = [c for c in cases if c["category"] == "in_scope"]
    rows: list[dict] = []
    for name, overrides in ABLATIONS:
        t0 = time.perf_counter()
        idx = build_index_with(base_cfg, overrides)
        m = evaluate_retrieval(idx, in_scope, top_n=top_n)
        m.pop("per_case", None)
        rows.append(
            {
                "config": name,
                "overrides": overrides,
                "chunks": idx.stats.get("chunks"),
                "doc_hit@3": m["doc_hit@3"],
                f"doc_hit@{top_n}": m[f"doc_hit@{top_n}"],
                f"term_hit@{top_n}": m[f"term_hit@{top_n}"],
                "MRR": m["MRR"],
                "build_seconds": round(time.perf_counter() - t0, 2),
            }
        )
        print(f"  ✓ {name:<28} term_hit@{top_n}={m[f'term_hit@{top_n}']:.3f}  MRR={m['MRR']:.3f}")
    return rows


def md_table(rows: list[dict], cols: list[str]) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG 评测与消融")
    ap.add_argument("--mode", choices=["all", "retrieve", "answer"], default="all")
    ap.add_argument("--eval-set", type=Path, default=EVAL_PATH)
    ap.add_argument(
        "--split",
        choices=["all", "dev", "test"],
        default="all",
        help="dev 用于调参，test 用于报告最终结果。默认 all。",
    )
    ap.add_argument("--top-n", type=int, default=6)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "report.json")
    args = ap.parse_args()

    cfg = RagConfig.from_env()
    all_cases = load_cases(args.eval_set)
    cases = filter_split(all_cases, args.split)
    print(f"评测集（split={args.split}）：{describe(cases)}")
    if args.split == "all":
        print(f"  dev={sum(1 for c in all_cases if case_split(c)=='dev')}  "
              f"test={sum(1 for c in all_cases if case_split(c)=='test')}"
              "   ← 调参只能用 dev，最终结果应报告 test\n")
    else:
        print()

    report: dict = {"eval_size": len(cases), "split": args.split, "min_relevance": cfg.answer.min_relevance}

    if args.mode in ("all", "retrieve"):
        print("[1/2] 检索指标与消融（不需要大模型）")
        index = RagIndex.load(cfg)
        report["retrieval"] = evaluate_retrieval(index, cases, args.top_n)
        print("  基线：", {k: v for k, v in report["retrieval"].items() if k != "per_case"})
        print("\n  消融实验：")
        report["ablation"] = run_ablations(cfg, cases, args.top_n)

    if args.mode in ("all", "answer"):
        print("\n[2/2] 端到端指标（护栏 / 引用 / 拒答）")
        index = RagIndex.load(cfg)
        rag = TutorRAG(index, cfg)
        report["end_to_end"] = evaluate_answers(rag, cases, args.top_n)
        print("  ", {k: v for k, v in report["end_to_end"].items() if k != "per_case"})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入：{args.out}")

    if "ablation" in report:
        print("\n### 检索消融（in_scope 子集）")
        print(md_table(report["ablation"], ["config", "chunks", "doc_hit@3", f"doc_hit@{args.top_n}", f"term_hit@{args.top_n}", "MRR"]))
    if "end_to_end" in report:
        e = report["end_to_end"]
        print("\n### 端到端指标")
        print(md_table([e], ["provider", "answer_rate", "citation_rate", "citation_accuracy_mean",
                             "refusal_accuracy", "injection_block_rate", "cheat_refuse_rate",
                             "latency_p50_ms", "latency_p95_ms"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
