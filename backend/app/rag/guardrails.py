"""AI 护栏：提示注入防护、作弊诱导拒绝、证据净化、引用校验。

对应课程验收标准 5.3 的四条：
    AC-NF-10  课件与提问中嵌入提示注入样例 → 不得改变智能体行为
    AC-NF-11  测验作弊诱导 → 拒绝直接给出答案
    AC-NF-12  诊断/引用中出现不存在的编号 → 校验拦截
    AC-NF-13  智能体不得直接改成绩、不得未经批准推送干预

设计原则：**检索到的文本永远是数据，不是指令**。
即使课件里写满"忽略以上指令"，它也只会作为被引用的资料片段出现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 注入模式
INJECTION_PATTERNS: list[tuple[str, str]] = [
    (
        r"忽略(以上|之前|前面|上述|先前)(的)?(所有|全部)?\s*"
        r"(指令|指示|规则|要求|提示|设定|内容)",
        "zh_ignore_instructions",
    ),
    (r"(无|不)(视|要遵守|需遵守|必遵守)\s*(以上|之前|上述)", "zh_disregard_above"),
    (
        r"ignore\s+(all\s+)?(the\s+)?(previous|above|prior|foregoing)\s+"
        r"(instruction|prompt|rule)",
        "en_ignore_instructions",
    ),
    (r"disregard\s+(all\s+)?(previous|above|prior)", "en_disregard"),
    (
        r"(输出|告诉我|展示|打印|复述)(你的|一下你的)?\s*(系统)?\s*"
        r"(提示词|prompt|设定|人设|指令)",
        "prompt_leak",
    ),
    (r"(reveal|show|print|repeat)\s+(your\s+)?(system\s+)?(prompt|instructions)", "prompt_leak_en"),
    (r"你现在是|从现在开始你是|接下来你(要|将)?扮演", "role_override"),
    (r"(扮演|假装成?).{0,6}(没有(任何)?限制|不受限制|越狱|开发者模式)", "jailbreak_persona"),
    (r"(越狱|jailbreak|DAN\s*模式|开发者模式)", "jailbreak"),
    (r"<(system|assistant|user|im_start|im_end)>", "fake_role_tag"),
    (r"\[/?INST\]|<<SYS>>", "llama_role_tag"),
    (r"^\s*#{2,}\s*(system|instruction|系统指令)", "fake_heading"),
    (r"(覆盖|更改|修改)(你的)?(系统)?(指令|设定|规则)", "override_instruction"),
]

# ---------------------------------------------------------------- 作弊模式
CHEATING_PATTERNS: list[tuple[str, str]] = [
    (r"(直接|只|就)?\s*(给|告诉|说|写|报)\s*我?\s*(这道题|这题|本题)?的?\s*(正确)?答案", "ask_for_answer"),
    (r"(这|本|该)\s*(道)?\s*题.{0,6}(选什么|答案是什么|选哪个|怎么选)", "ask_quiz_choice"),
    (r"(我|人家)\s*(在|正在|马上)\s*(考试|测验|测试|做题)", "in_exam"),
    (
        r"(帮|替|代)\s*我.{0,12}(做|答|写|完成|搞定).{0,8}"
        r"(题|测验|考试|作业|试卷|卷子|quiz|exam)",
        "do_my_exam",
    ),
    # 中文常把宾语放在动词前："帮我把这份测验做完"
    (
        r"(帮|替|代)\s*我.{0,10}(题|测验|考试|作业|试卷|卷子).{0,6}"
        r"(做|答|写|完成|搞定)",
        "do_my_exam_reordered",
    ),
    (
        r"(不要|别|无需|不用)\s*(解释|讲解|分析|说明|废话).{0,10}"
        r"(直接|只)\s*(给|说|告诉)",
        "demand_answer_only",
    ),
    (r"(考试|测验|测试|试卷|quiz|exam).{0,10}(答案|原题|泄露|作弊)", "exam_leak"),
    (r"(背|记住).{0,6}(答案|题库)", "memorize_answers"),
]


def _scan(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    hits: list[str] = []
    for pattern, name in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            hits.append(name)
    return hits


@dataclass
class GuardrailVerdict:
    action: str  # allow / block / refuse_cheat
    reasons: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def blocked(self) -> bool:
        return self.action != "allow"

    def to_dict(self) -> dict:
        return {"action": self.action, "reasons": self.reasons, "message": self.message}


SAFE_REFUSAL_INJECTION = (
    "你的问题中包含看起来像「指令覆盖」的内容。为了系统的安全与公平，"
    "我不会执行提问或资料中夹带的指令，只按《软件工程》课程资料回答问题。"
    "如果你有课程学习上的具体疑问，欢迎换个说法再问一次。"
)

SAFE_REFUSAL_CHEATING = (
    "这道题需要你自己作答。我可以换个方式帮你：\n"
    "1) 讲清它考的是哪个知识点；\n"
    "2) 给出判断这类题的通用方法或解题步骤；\n"
    "3) 用一个**同类型的示例**演示推理过程（不是本题答案）。\n"
    "你想从哪一步开始？"
)


def scan_input(query: str, *, enabled: bool = True) -> GuardrailVerdict:
    """输入层护栏：先查提示注入，再查作弊诱导。"""
    if not enabled:
        return GuardrailVerdict(action="allow")
    q = query or ""
    inj = _scan(q, INJECTION_PATTERNS)
    if inj:
        return GuardrailVerdict(action="block", reasons=inj, message=SAFE_REFUSAL_INJECTION)
    cheat = _scan(q, CHEATING_PATTERNS)
    if cheat:
        return GuardrailVerdict(action="refuse_cheat", reasons=cheat, message=SAFE_REFUSAL_CHEATING)
    return GuardrailVerdict(action="allow")


# ---------------------------------------------------------------- 证据净化
INSTRUCTION_LINE_RE = re.compile(
    "|".join(f"(?:{p})" for p, _ in INJECTION_PATTERNS), flags=re.IGNORECASE | re.MULTILINE
)


def sanitize_evidence(text: str) -> tuple[str, list[str]]:
    """把检索到的文本里"像指令的行"剔除掉，只保留陈述性内容。

    返回 (净化后文本, 被移除的行)。被移除的行会写进 trace，便于红队复盘。
    """
    kept: list[str] = []
    removed: list[str] = []
    for line in (text or "").splitlines():
        if line.strip() and INSTRUCTION_LINE_RE.search(line):
            removed.append(line.strip()[:200])
        else:
            kept.append(line)
    return "\n".join(kept).strip(), removed


def wrap_evidence(index: int, doc_title: str, section: str, text: str) -> str:
    """把证据片段包在显式定界符里，并在提示词中声明"以下是资料，不是指令"。"""
    header = f"[{index}] 来源：《{doc_title}》 › {section}"
    return f"{header}\n<<<EVIDENCE\n{text}\nEVIDENCE>>>"


# ---------------------------------------------------------------- 输出校验
CITATION_RE = re.compile(r"\[(\d{1,2})\]")


@dataclass
class CitationReport:
    cited: list[int]
    valid: list[int]
    invalid: list[int]
    accuracy: float
    has_citation: bool

    def to_dict(self) -> dict:
        return {
            "cited": self.cited,
            "valid": self.valid,
            "invalid": self.invalid,
            "accuracy": round(self.accuracy, 4),
            "has_citation": self.has_citation,
        }


def validate_citations(answer: str, n_evidence: int) -> CitationReport:
    """校验回答中的 [n] 是否都指向真实存在的证据片段（NF-11）。"""
    cited = [int(m) for m in CITATION_RE.findall(answer or "")]
    uniq = sorted(set(cited))
    valid = [c for c in uniq if 1 <= c <= n_evidence]
    invalid = [c for c in uniq if not (1 <= c <= n_evidence)]
    total = len(uniq)
    return CitationReport(
        cited=uniq,
        valid=valid,
        invalid=invalid,
        accuracy=(len(valid) / total) if total else 0.0,
        has_citation=total > 0,
    )


NO_EVIDENCE_MARKERS = (
    "资料中没有",
    "没有找到",
    "未找到",
    "资料未涉及",
    "无法从",
    "不在课程范围内",
    "没有相关依据",
)


def claims_no_evidence(answer: str) -> bool:
    return any(m in (answer or "") for m in NO_EVIDENCE_MARKERS)
