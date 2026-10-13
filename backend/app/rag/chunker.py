"""结构感知的 Markdown 切分器。

RAG 策略中的切分原则
--------------------
1. **先按标题结构切，再按长度切**。课程讲义天然有层级（## 章节 / ### 小节），
   按标题切能保证每个 chunk 语义完整；纯粹按固定字数切会把定义和例子割裂。
2. **定义句单独成块**。语料里每个概念的定义独立成段，单独抽出后
   "X 是什么" 类问题的检索精度显著提高。
3. **带重叠的滑动窗口**。同一小节内相邻 chunk 重叠 overlap 个字符，
   避免答案正好横跨切分点。
4. **保留上级上下文（small-to-big）**。检索用小块保证精度，
   喂给大模型时把同小节的相邻块一起展开，保证完整性。
5. **参考来源不入库**。URL 列表会污染检索结果，直接排除。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import ChunkConfig
from .textutil import is_definition_sentence, normalize, split_sentences

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^\s*```")

# 按小标题关键字给 chunk 打上"内容类型"标签，重排时作为先验特征使用
KIND_RULES: list[tuple[str, str]] = [
    ("常见误解", "pitfall"),
    ("易混淆", "pitfall"),
    ("与其他知识域", "relation"),
    ("参考来源", "references"),
    ("例子", "example"),
    ("示例", "example"),
    ("步骤", "procedure"),
    ("方法", "method"),
]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str  # 面包屑，如 "SE-01 软件工程概述与软件过程 > 软件过程模型 > 瀑布模型"
    section_path: list[str]
    parent_id: str  # small-to-big 的父块（= 同一小节）
    text: str
    kind: str  # definition / body / example / procedure / method / pitfall / relation / references
    kp_ids: list[str] = field(default_factory=list)
    ordinal: int = 0
    source_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParentBlock:
    """small-to-big 的父块：同一小节聚合后的完整文本。"""

    parent_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str
    kp_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _mint(*parts: str, n: int = 10) -> str:
    return hashlib.blake2b("||".join(parts).encode("utf-8"), digest_size=n).hexdigest()


def _extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\)\]]+", text or "")


def _classify(section_path: list[str], text: str) -> str:
    joined = " ".join(section_path)
    for kw, kind in KIND_RULES:
        if kw in joined:
            return kind
    if is_definition_sentence(text):
        return "definition"
    return "body"


def _split_paragraphs(body: str) -> list[str]:
    """按空行切段，同时保护 ``` 代码块 不被拆开。"""
    paragraphs: list[str] = []
    buf: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            buf.append(line)
            continue
        if in_fence:
            buf.append(line)
            continue
        if line.strip() == "":
            if buf:
                paragraphs.append("\n".join(buf).strip())
                buf = []
        else:
            buf.append(line)
    if buf:
        paragraphs.append("\n".join(buf).strip())
    return [p for p in paragraphs if p]


def _pack(
    paragraphs: list[str], target: int, overlap: int, max_chars: int, min_chars: int
) -> list[str]:
    """把段落贪心打包成不超过 target 的块；相邻块之间保留 overlap 字符的尾巴。"""
    blocks: list[str] = []
    cur: list[str] = []
    cur_len = 0

    def flush() -> None:
        nonlocal cur, cur_len
        if cur:
            blocks.append("\n\n".join(cur))
            cur, cur_len = [], 0

    for p in paragraphs:
        # 超长段落先按句子切
        if len(p) > max_chars:
            flush()
            sentences = split_sentences(p)
            sub: list[str] = []
            sub_len = 0
            for s in sentences:
                if sub_len + len(s) > target and sub:
                    blocks.append("".join(sub))
                    sub, sub_len = [], 0
                sub.append(s)
                sub_len += len(s)
            if sub:
                blocks.append("".join(sub))
            continue

        if cur_len + len(p) > target and cur:
            flush()
        cur.append(p)
        cur_len += len(p) + 2

    flush()

    # 合并过短的块，并加上重叠尾巴
    merged: list[str] = []
    for b in blocks:
        if merged and len(b) < min_chars:
            merged[-1] = merged[-1] + "\n\n" + b
        else:
            merged.append(b)

    if overlap > 0 and len(merged) > 1:
        with_overlap = [merged[0]]
        for prev, cur_block in zip(merged, merged[1:]):
            tail = prev[-overlap:] if len(prev) > overlap else prev
            with_overlap.append(tail + "\n\n" + cur_block)
        merged = with_overlap

    out: list[str] = []
    for b in merged:
        if len(b) <= max_chars * 2:
            out.append(b)
            continue
        for i in range(0, len(b), max_chars):
            out.append(b[i : i + max_chars])
    return out


def chunk_markdown(
    *,
    doc_id: str,
    doc_title: str,
    markdown: str,
    kps: list[dict],
    cfg: ChunkConfig,
) -> tuple[list[Chunk], list[ParentBlock]]:
    """把一个 Markdown 文档切成 chunks + parent blocks。"""
    lines = markdown.splitlines()

    # ---- 1. 解析成 (标题路径, 正文) 的小节 ----
    sections: list[tuple[list[str], list[str]]] = []
    path: list[str] = []
    buf: list[str] = []
    in_fence = False

    def flush_section() -> None:
        if buf and any(x.strip() for x in buf):
            sections.append((list(path), list(buf)))
        buf.clear()

    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            buf.append(line)
            continue
        m = None if in_fence else HEADING_RE.match(line)
        if m:
            flush_section()
            level = len(m.group(1))
            title = m.group(2).strip()
            path = path[: level - 1]
            while len(path) < level - 1:
                path.append("")
            path.append(title)
            continue
        buf.append(line)
    flush_section()

    # ---- 2. 逐小节生成 chunk ----
    chunks: list[Chunk] = []
    parents: list[ParentBlock] = []
    kp_names = [(k.get("id", ""), k.get("name", "")) for k in kps]

    for section_path, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        clean_path = [p for p in section_path if p]
        # 文档标题已作为前缀，避免面包屑里重复出现
        if clean_path and normalize(clean_path[0]) == normalize(doc_title):
            clean_path = clean_path[1:]
        section_str = f"{doc_title} > " + " > ".join(clean_path) if clean_path else doc_title
        parent_id = _mint(doc_id, section_str)

        # 跳过纯参考链接小节：不参与检索
        kind_hint = _classify(clean_path, body)
        if kind_hint == "references":
            continue

        # 2a. 定义句单独成块
        definition_texts: list[str] = []
        for para in _split_paragraphs(body):
            for sent in split_sentences(para):
                if is_definition_sentence(sent):
                    definition_texts.append(sent)

        # 2b. 主体打包
        blocks = _pack(
            _split_paragraphs(body),
            target=cfg.target_size,
            overlap=cfg.overlap,
            max_chars=cfg.max_chunk_chars,
            min_chars=cfg.min_chunk_chars,
        )

        pieces: list[tuple[str, str]] = [(t, "definition") for t in definition_texts]
        pieces += [(b, kind_hint) for b in blocks]

        section_chunks: list[Chunk] = []
        for text, kind in pieces:
            text = normalize(text)
            if not text:
                continue
            hit_kps = [kid for kid, name in kp_names if kid and name and name in text]
            if not hit_kps and kp_names:
                # 退一步：用小节标题匹配知识点
                joined = " ".join(clean_path)
                hit_kps = [kid for kid, name in kp_names if kid and name and name in joined]
            cid = _mint(doc_id, section_str, text)
            section_chunks.append(
                Chunk(
                    chunk_id=cid,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    section=section_str,
                    section_path=clean_path,
                    parent_id=parent_id,
                    text=text,
                    kind=kind,
                    kp_ids=hit_kps,
                    ordinal=len(section_chunks),
                    source_urls=_extract_urls(body),
                )
            )
        chunks.extend(section_chunks)

        if section_chunks:
            ptext = normalize(body)
            kp_union: list[str] = []
            for c in section_chunks:
                for k in c.kp_ids:
                    if k not in kp_union:
                        kp_union.append(k)
            parents.append(
                ParentBlock(
                    parent_id=parent_id,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    section=section_str,
                    text=ptext,
                    kp_ids=kp_union,
                )
            )

    # 重新编号，保证 chunk_id 全局唯一（不同小节可能文本相同）
    seen: dict[str, int] = {}
    for i, c in enumerate(chunks):
        c.ordinal = i
        n = seen.get(c.chunk_id, 0)
        seen[c.chunk_id] = n + 1
        if n:
            c.chunk_id = f"{c.chunk_id}-{n}"
    return chunks, parents


def load_kb(
    kb_dir: Path, chunk_cfg: ChunkConfig | None = None
) -> tuple[list[Chunk], list[ParentBlock], list[dict]]:
    """读取 kb/docs/*.md + kb/meta/*.json，返回 chunks / parents / 知识点清单。

    chunk_cfg 可注入，用于做"分块大小"的消融实验。
    """
    docs_dir = kb_dir / "docs"
    meta_dir = kb_dir / "meta"
    cfg = chunk_cfg or ChunkConfig()

    all_chunks: list[Chunk] = []
    all_parents: list[ParentBlock] = []
    all_kps: list[dict] = []

    import json

    for md_path in sorted(docs_dir.glob("*.md")):
        m = re.match(r"^([A-Za-z]+-\d+)", md_path.stem)
        doc_id = m.group(1) if m else md_path.stem
        meta_path = meta_dir / f"{md_path.name}.json"
        meta: dict = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        doc_title = meta.get("title") or md_path.stem
        raw_kps = meta.get("kps", [])

        kps: list[dict] = []
        for i, kp in enumerate(raw_kps, start=1):
            kp_id = f"KP-{doc_id.replace('-', '')}-{i:02d}"
            kps.append({**kp, "id": kp_id, "doc_id": doc_id, "doc_title": doc_title})
        all_kps.extend(kps)

        chunks, parents = chunk_markdown(
            doc_id=doc_id,
            doc_title=doc_title,
            markdown=md_path.read_text(encoding="utf-8"),
            kps=kps,
            cfg=cfg,
        )
        all_chunks.extend(chunks)
        all_parents.extend(parents)

    return all_chunks, all_parents, all_kps
