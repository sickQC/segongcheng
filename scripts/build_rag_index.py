#!/usr/bin/env python
"""构建 RAG 索引。

    python scripts/build_rag_index.py
    SE_RAG_EMBED_BACKEND=st python scripts/build_rag_index.py   # 换嵌入后端重建
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag import RagConfig, build_index


def main() -> int:
    cfg = RagConfig.from_env()
    print(f"知识库目录: {cfg.kb_dir}")
    if not (cfg.kb_dir / "docs").exists():
        print("❌ 未找到 kb/docs，请先放入课程资料（Markdown）。")
        return 1

    idx = build_index(cfg)
    print("\n✅ 索引构建完成")
    print(json.dumps(idx.stats, ensure_ascii=False, indent=2))
    print(f"\n索引文件: {cfg.index_dir / 'index.pkl'}")

    # 顺带做一次知识库体检，早发现问题
    orphans = [k.name for k in idx.kps if not any(k.id in c.kp_ids for c in idx.chunks)]
    if orphans:
        print(f"\n⚠️  {len(orphans)} 个知识点没有被任何 chunk 引用（孤立知识点）：")
        for name in orphans[:10]:
            print(f"   - {name}")
    else:
        print("\n✅ 所有知识点都至少挂接到一个 chunk")
    return 0


if __name__ == "__main__":
    # Windows redirected stdout may default to GBK and fail on report symbols.
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
