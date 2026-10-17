"""Evidence-derived explanations and authored transfer tasks for diagnosis reports."""

from app.schemas.diagnosis_report import PointDiagnosis

PRESENTATION_VERSION = "diagnosis-presentation-v1"

# Tasks name facts to reason about, never the classification or the test-value answer.
TASKS = {
    "KP-REQ-01": (
        "功能、质量约束和可验收条件",
        "校园失物平台有两条要求：‘用户能够登记遗失物品’和‘95%的检索请求在800毫秒内返回’。"
        "请分别分类并说明判断依据，再自拟一条不同的需求。",
    ),
    "KP-REQ-02": (
        "系统边界、交互角色和角色目标",
        "某软件只负责场馆预约登记，门禁由独立系统控制，两者交换预约资格结果。"
        "门禁系统是否可能是预约软件的参与者？请说明边界、交互及其目标。",
    ),
    "KP-VAL-01": (
        "规定要求、预期用途和用户需要",
        "为一个食堂订餐功能分别设计一项验证活动和一项确认活动，"
        "说明各自需要什么证据，以及两项活动为何不能互相替代。",
    ),
    "KP-TEST-01": (
        "输入条件、预期处理行为和类别代表值",
        "某接口只接受2到7的整数，包含两端；本题仅考虑整数输入，范围外输入统一拒绝。"
        "请自行划分输入类别、选择代表值，并说明类别依据与各代表值的预期处理结果。",
    ),
    "KP-BOUND-01": (
        "输入参数、合法取值范围、端点和最小步长",
        "某表单只接受6到14的整数，包含两端，整数最小步长为1；范围外整数一律拒绝。"
        "请自行选择检查上下边界及紧邻位置的测试值，并说明每个值的预期结果。",
    ),
}


def verified_behavior(events, stats):
    """Use the latest trusted observation, not a favorable older window."""
    observed = [e for e in events if e["source"] == "behavior"]
    if not observed:
        return None
    event = observed[-1]
    m = event["measurement"]
    if not (m["resource_available"] and m["observation_complete"]):
        return None
    if stats["graded_count"] >= 3 and m["study_visits"] == 0:
        kind = "practice_only"
    elif m["coverage"] <= 0.2 and m["effective_seconds"] < 120:
        kind = "low_engagement"
    else:
        return None
    return {"problem_type": kind, "evidence_event_id": event["event_id"], "measurement": m}


def render_point(point, original, stats):
    """Keep model diagnosis/score, render factual claims and tasks deterministically."""
    events = original["events"]
    graded = [e for e in events if e["source"] == "assessment" and type(e.get("correct")) is bool]
    dialogue = [e for e in events if e["source"] in ("dialogue", "practice")]
    behavior = verified_behavior(events, stats)
    cited = set(point.evidence_event_ids)
    pieces = []
    if graded:
        pieces.append(
            f"本次选取记录中有{len(graded)}次客观答题，正确{len(graded) - stats['wrong_count']}次，"
            f"错误{stats['wrong_count']}次，客观正确率为{stats['accuracy']:.0%}。"
        )
        last = graded[-1]
        pieces.append(f"最近客观答题（{last['event_id']}）判为{'正确' if last['correct'] else '错误'}。")
        cited.add(last["event_id"])
    else:
        pieces.append("本次窗口没有可客观判分的答题，客观正确率未知。")
    if dialogue:
        last = dialogue[-1]
        pieces.append(f"最近自主回答（{last['event_id']}，节选）为：“{last.get('answer', '')[:160]}”。")
        cited.add(last["event_id"])
        if graded and events.index(last) > events.index(graded[-1]):
            pieces.append("这条自主回答晚于最近客观答题，已与该答题一起保留供核对。")
            if point.problem_type == "repeated_error":
                pieces.append("是否已稳定纠正，需要新的应用任务核实。")
    if stats["behavior_available"]:
        observations = [e for e in events if e["source"] == "behavior"]
        latest = observations[-1]
        m = latest["measurement"]
        pieces.append(
            f"最近服务端行为汇总（{latest['event_id']}）："
            f"资源{'可用' if m['resource_available'] else '不可用'}，"
            f"窗口{'完整' if m['observation_complete'] else '不完整'}，覆盖率{m['coverage']:.0%}，"
            f"有效时长{m['effective_seconds']:g}秒，学习访问{m['study_visits']}次。"
        )
        cited.add(latest["event_id"])
    else:
        pieces.append("行为数据未采集，暂不评价学习投入或资源访问模式。")

    kind = point.problem_type
    if kind == "repeated_error":
        wrong = [e for e in graded if e["correct"] is False]
        cited.update(e["event_id"] for e in wrong)
        pieces.append(
            "至少三次客观错答且最新客观答题仍错，支持反复客观错误观察；对话与答题是否一致需进一步检查。"
        )
    elif kind == "prerequisite_gap":
        cited.update(stats["prerequisite_errors"])
        pieces.append(
            f"其中{len(stats['prerequisite_errors'])}次错误被教师标记为前置检查，支持存在前置知识缺口的假设；"
            "尚不能仅凭这些记录确定缺失的是哪项具体基础技能。"
        )
    elif kind == "concept_confusion":
        pieces.append(
            f"模型暂判存在概念混淆，请将所引回答与定义“{original.get('definition', '')[:300]}”对照。"
            "答题判分与学生自己的概念说明分别作为证据，正确率不直接等于语义掌握度。"
        )
    elif kind in ("low_engagement", "practice_only"):
        if behavior:
            cited.add(behavior["evidence_event_id"])
        pieces.append(
            "完整行为汇总满足资源访问为零且至少三次答题的学习方式条件。"
            if kind == "practice_only"
            else "完整行为汇总满足低覆盖率、短有效学习时长的观察条件，学习访问不要求为零。"
        )
        pieces.append("行为观察与知识掌握度分开判断，不能据此直接推断知识不会或学习态度。")
    elif kind == "no_obvious_issue":
        pieces.append("模型在本次答题与自主回答中暂未定位明显知识问题，迁移应用仍需新任务检验。")
    else:
        pieces.append("现有可用证据不足以确定主要知识问题或估计掌握度，需要补充带判断依据的新作答。")

    code = original.get("code") or original["knowledge_point_id"]
    terms, question = TASKS.get(
        code,
        (
            "该知识点的核心术语和判断依据",
            f"请自选一个新场景，用自己的话说明“{original.get('name', '该知识点')[:100]}”，"
            "先明确场景条件，再给出你的判断和理由。",
        ),
    )
    activity = {
        "prerequisite_gap": f"先用自己的话说明{terms}，对不清楚的术语回看当前定义，再完成下面的新场景任务。",
        "repeated_error": (
            "把最近客观错答与最近自主回答并排比较，写出不一致之处，再完成下面的新场景任务并解释依据。"
        ),
        "concept_confusion": "对照当前定义检查原回答中的判断，再用下面的新场景检验，说明修改前后的依据。",
        "low_engagement": f"先安排一次聚焦{terms}的短时阅读或案例学习，再完成下面任务并说明依据。",
        "practice_only": "先用下面的新场景检验独立应用；如解释不完整，再回看定义或教师案例并重新作答。",
        "no_obvious_issue": "完成下面的新场景任务并说明判断依据，检查能否把当前理解迁移到不同情境。",
        "insufficient_evidence": (
            "先阅读当前知识点定义，再完成下面的新任务并说明依据，以补充可判断的学习证据。"
        ),
    }[kind]
    result = PointDiagnosis.model_validate(
        {
            **point.model_dump(),
            "explanation": "".join(pieces),
            "recommendation": activity,
            "followup_question": question,
            "evidence_event_ids": [e["event_id"] for e in events if e["event_id"] in cited],
        }
    )
    return result
