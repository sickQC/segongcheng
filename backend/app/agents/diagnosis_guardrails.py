"""Diagnosis-specific input and output checks."""

import re

INJECTION_PATTERNS = (
    r"(?:忽略|无视|忘记).{0,12}(?:之前|以上|系统|所有).{0,12}(?:指令|规则|提示)",
    r"(?:^|[，。！？\n]|请|帮我|给我|直接|立刻)\s*(?:输出|泄露|展示|告诉我|打印)"
    r".{0,12}(?:系统提示词|system\s*prompt|API\s*key|密钥)",
    r"ignore\s+(?:all\s+)?(?:previous|system|above)\s+(?:instructions|rules)",
    r"(?:给|将|把).{0,8}(?:掌握度|mastery).{0,8}(?:设为|改为|设置为).{0,4}(?:1(?:\.0)?|100)",
)


def is_instruction_attack(answer: str) -> bool:
    return any(re.search(pattern, answer, re.IGNORECASE | re.DOTALL) for pattern in INJECTION_PATTERNS)


def contains_prompt_leak(output_text: str, system_prompt: str) -> bool:
    # Match long source lines rather than ordinary teaching words such as "知识点".
    return any(line.strip() in output_text for line in system_prompt.splitlines() if len(line.strip()) >= 28)
