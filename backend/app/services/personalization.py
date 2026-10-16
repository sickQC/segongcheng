"""明确标记的演示学习历史，不作为正式测验或诊断结果。"""

from copy import deepcopy

from app.services.seed import seed_id

DEMO_COURSE_ID = seed_id("course")

# 两名演示学生对同一知识点有不同的错误原因，便于检验个性化是否生效。
_HISTORIES = {
    "student01": {
        "chapters": [
            {
                "title": "第一章 需求工程",
                "accuracy": 48,
                "wrong_questions": [
                    {
                        "stem": "功能需求与非功能需求有什么区别？",
                        "answer": "两者都是系统要实现的功能。",
                        "knowledge_point": "功能需求与非功能需求",
                    },
                    {
                        "stem": "响应时间小于两秒属于哪类需求？",
                        "answer": "功能需求。",
                        "knowledge_point": "功能需求与非功能需求",
                    },
                ],
                "weak_knowledge_points": [
                    {
                        "name": "功能需求与非功能需求",
                        "rag_topic": "功能性需求与非功能性需求",
                        "learning_gap": "容易把系统行为与质量约束混为一谈",
                        "practice": "分别写出一个功能需求和一个可度量的性能要求",
                    }
                ],
            },
            {
                "title": "第二章 软件测试",
                "accuracy": 84,
                "wrong_questions": [
                    {
                        "stem": "软件验证与软件确认分别关注什么？",
                        "answer": "验证关注用户需要。",
                        "knowledge_point": "软件验证与确认",
                    }
                ],
                "weak_knowledge_points": [
                    {
                        "name": "软件验证与确认",
                        "rag_topic": "软件验证与确认",
                        "learning_gap": "验证与确认的关注对象偶尔混淆",
                        "practice": "用一个项目例子分别说明符合规格与满足用户需要",
                    }
                ],
            },
        ]
    },
    "student02": {
        "chapters": [
            {
                "title": "第一章 需求工程",
                "accuracy": 72,
                "wrong_questions": [
                    {
                        "stem": "如何把非功能需求写成可验收的要求？",
                        "answer": "系统运行要快。",
                        "knowledge_point": "功能需求与非功能需求",
                    }
                ],
                "weak_knowledge_points": [
                    {
                        "name": "功能需求与非功能需求",
                        "rag_topic": "功能性需求与非功能性需求",
                        "learning_gap": "能分辨需求类型，但质量要求缺少可测量的指标",
                        "practice": "把“系统要快”改写成带场景和时间阈值的验收标准",
                    }
                ],
            },
            {
                "title": "第二章 软件测试",
                "accuracy": 41,
                "wrong_questions": [
                    {
                        "stem": "等价类划分如何选择代表值？",
                        "answer": "只挑正常输入即可。",
                        "knowledge_point": "等价类划分",
                    },
                    {
                        "stem": "边界值分析需要测哪些位置？",
                        "answer": "只测边界本身。",
                        "knowledge_point": "等价类划分",
                    },
                ],
                "weak_knowledge_points": [
                    {
                        "name": "等价类划分",
                        "rag_topic": "等价类划分",
                        "learning_gap": "遗漏无效等价类和边界附近的输入",
                        "practice": "为一个输入范围同时列出有效与无效等价类",
                    }
                ],
            },
        ]
    },
}


def demo_history(username: str, course_id: str) -> dict | None:
    """仅演示课程内的预置学生有模拟历史；返回副本避免请求间串改。"""
    if course_id != DEMO_COURSE_ID or username not in _HISTORIES:
        return None
    return {"source": "synthetic", "chapters": deepcopy(_HISTORIES[username]["chapters"])}
