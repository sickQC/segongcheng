"""中文文本处理：归一化、分词、领域词典、同义词扩展。

设计要点
--------
1. 中文课程语料的检索质量高度依赖分词质量。jieba 的通用词典会把
   "边界值分析" 切成 "边界/值/分析"，导致 BM25 命中率下降。
   因此我们把同义词表里的领域术语全部注册为 jieba 用户词。
2. 归一化统一全角/半角、大小写，保证 "ISO/IEC 25010" 与全角写法等价。
3. 同义词扩展是**双向**的：键命中加值，值命中加键。
   这样学生说 "SRS" 也能召回写 "软件需求规格说明" 的段落。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import jieba

jieba.setLogLevel(60)  # 关闭 jieba 的构建日志

CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.+#/]*")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
ANY_TOKEN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z][A-Za-z0-9_.+#/]*|\d+(?:\.\d+)?")

# 停用词：中文功能词 + 疑问词。疑问词必须去掉，否则 "什么是X" 会大量命中 "什么"
STOPWORDS: frozenset[str] = frozenset(
    """
    的 了 是 在 和 与 及 或 也 都 就 而 有 对 从 到 为 以 被 把 让 使 于 中 上 下 个 之 其 此 该
    这 那 一个 一种 一些 一样 什么 怎么 怎样 如何 为何 为什么 哪些 哪个 哪里 谁 何时 是否
    请 我 你 您 他 她 它 我们 你们 他们 可以 能够 需要 应该 会 要 不 没 没有 如果 那么
    因为 所以 但是 然而 以及 等等 例如 比如 就是 还是 只是 已经 正在 通过 进行 用来 用于
    的话 吗 呢 吧 啊 呀 一下 一点 有关 关于 对于 根据 按照 关于 区别 不同 相同 主要 一般
    """.split()
)

# 提问脚手架词：在问题里出现频率极高，但几乎不含主题信息。
#
# 它们**只**在"是否可回答"的判定中被忽略（见 retrieve._content_weight），
# 既不参与实词加权覆盖率，也不能成为"关键实词"。
# 它们**仍然保留**在 BM25 与普通覆盖率里——因为它们在课程语料的小节标题中
# 是有意义的（如"常见误解与易混淆概念"），从索引里删掉反而会伤害检索。
#
# 实测效果：把"哪几个""步骤""详细"这类词排除后，
# 超范围问题"红烧肉怎么做才好吃？请给详细步骤"被正确拒答，
# 而"SWEBOK 一共有多少个知识域"不再被误拒。
QUESTION_SCAFFOLD: frozenset[str] = frozenset(
    """
    哪些方面 哪几个 哪一个 哪几 哪些 哪种 一共 总共 多少 几级 几类 几种 几个 几步
    分成 分为 包含 包括 组成 构成 属于 常见 常用 主要 最大 特点 特征 含义 意思
    举例 例子 作用 用处 内容 具体 详细 步骤 方面 部分 怎么样 什么样 介绍 讲解
    解释 说明 描述 阐述 论述 关系 联系 影响 优缺点 好处 坏处 价值 意义 定义
    """.split()
)

_domain_dict_loaded = False
_synonyms_cache: dict[str, dict[str, list[str]]] = {}

# 只把"全角字母与数字"折叠成半角，**保留中文全角标点**。
#
# 为什么不用 unicodedata.normalize("NFKC")：NFKC 会把中文标点一并折叠
# （"：" → ":"、"。" 保持、"（" → "("），于是引用片段展示给学生时
# 变成西文标点，读起来很别扭。
# 我们需要的其实只是让 "ＩＳＯ ２５０１０" 与 "ISO 25010" 等价。
_FULLWIDTH_FOLD = {
    **{chr(0xFF10 + i): chr(0x30 + i) for i in range(10)},  # ０-９
    **{chr(0xFF21 + i): chr(0x41 + i) for i in range(26)},  # Ａ-Ｚ
    **{chr(0xFF41 + i): chr(0x61 + i) for i in range(26)},  # ａ-ｚ
    "\uFF0B": "+",  # ＋
    "\uFF0D": "-",  # －
    "\uFF0F": "/",  # ／
    "\uFF1D": "=",  # ＝
    "\uFF05": "%",  # ％
    "\uFF03": "#",  # ＃
}


def normalize(text: str) -> str:
    """全角字母数字转半角、压缩空白；中文标点保持原样。"""
    if not text:
        return ""
    text = text.translate(_FULLWIDTH_FOLD)
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text.strip()


def load_synonyms(path: str | Path) -> dict[str, list[str]]:
    """读取同义词表，并把它注册进 jieba 用户词典（只做一次）。"""
    global _domain_dict_loaded
    path = Path(path)
    key = str(path.resolve())
    if key in _synonyms_cache:
        return _synonyms_cache[key]

    table: dict[str, list[str]] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            table[k] = [x for x in v if x]

    if not _domain_dict_loaded:
        # 键是"规范术语"，给最高词频，保证它们永远被切成一个整词。
        # 值只是用于查询扩展的近义表达，词频必须给低：否则像 "代码坏味" 这种
        # 近似写法会把 "代码/坏味道" 这条正确路径挤掉，反而降低召回（实测踩过）。
        for k, vals in table.items():
            jieba.add_word(k, freq=2_000_000)
            for v in vals:
                jieba.add_word(v, freq=10_000)
        _domain_dict_loaded = True

    _synonyms_cache[key] = table
    return table


@lru_cache(maxsize=200_000)
def _cut(text: str) -> tuple[str, ...]:
    return tuple(jieba.lcut(text, cut_all=False))


def tokenize(text: str, *, keep_stopwords: bool = False) -> list[str]:
    """分词并过滤停用词与标点。返回小写化的 token 列表。"""
    if not text:
        return []
    out: list[str] = []
    for w in _cut(normalize(text)):
        w = w.strip()
        if not w:
            continue
        if CJK_RUN.fullmatch(w):
            if keep_stopwords or w not in STOPWORDS:
                out.append(w)
        elif ASCII_WORD.fullmatch(w) or NUMBER.fullmatch(w):
            lw = w.lower()
            if keep_stopwords or lw not in STOPWORDS:
                out.append(lw)
        else:
            # 混合串：拆出其中的中文/英文/数字片段
            for m in ANY_TOKEN.findall(w):
                lw = m.lower()
                if keep_stopwords or lw not in STOPWORDS:
                    out.append(lw)
    return out


def char_ngrams(text: str, n: int = 2) -> list[str]:
    """中文按 n-gram 切分，用于哈希向量嵌入（对 OOV 术语更鲁棒）。"""
    out: list[str] = []
    for run in CJK_RUN.findall(normalize(text)):
        if len(run) < n:
            out.append(run)
        else:
            out.extend(run[i : i + n] for i in range(len(run) - n + 1))
    return out


def expand_query(query: str, synonyms: dict[str, list[str]], max_extra: int = 24) -> list[str]:
    """同义词/缩写双向扩展。返回**追加**到查询中的词（不含原查询词）。

    只在整词子串命中时扩展，避免 "需求" 命中 "需求工程" 后重复扩展。
    """
    if not synonyms:
        return []
    q = normalize(query).lower()
    extra: list[str] = []
    seen: set[str] = set()
    for key, values in synonyms.items():
        hit = key.lower() in q or any(v.lower() in q for v in values)
        if not hit:
            continue
        for term in (key, *values):
            tl = term.lower()
            if tl in q or tl in seen:
                continue
            seen.add(tl)
            extra.extend(tokenize(term))
            if len(extra) >= max_extra:
                return extra[:max_extra]
    return extra


def split_sentences(paragraph: str) -> list[str]:
    """按中文/英文句末标点切句，保留标点。"""
    parts = re.split(r"(?<=[。！？；!?;])\s*", paragraph.strip())
    return [p.strip() for p in parts if p.strip()]


DEFINITION_PATTERNS = (
    re.compile(r"^(【)?[\u4e00-\u9fffA-Za-z0-9（）()\-—·\s]{2,40}(是指|指的是|定义为|是一种|称为|是由|是.{0,6}中)"),
)


def is_definition_sentence(sentence: str) -> bool:
    """判断一句话是否为"概念定义句"。

    语料约定：定义句独立成段。命中定义句的片段会被额外提升为独立 chunk，
    因为它是学生提问 "X 是什么" 时最精确的答案来源。
    """
    s = normalize(sentence)
    if not (8 <= len(s) <= 220):
        return False
    return any(p.search(s) for p in DEFINITION_PATTERNS)


def truncate(text: str, limit: int, ellipsis: str = "…") -> str:
    text = text or ""
    return text if len(text) <= limit else text[: max(0, limit - 1)] + ellipsis


_MD_MARKUP_RE = re.compile(r"\*\*|__|`|~~")
_MD_LIST_PREFIX_RE = re.compile(r"^[\s\-*+>#\d.)（(、]+")


def strip_markdown(sentence: str) -> str:
    """去掉 Markdown 强调标记与列表符号，用于把检索片段展示给人看。"""
    s = _MD_MARKUP_RE.sub("", sentence or "").strip()
    return _MD_LIST_PREFIX_RE.sub("", s).strip()
