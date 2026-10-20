"""Deterministic budget scheduling, shared by runtime and offline comparison."""

from collections import defaultdict, deque
from copy import deepcopy

SCHEDULING_RULE = "(0.6 * weakness + 0.4 / (1 + distance_to_target)) / estimated_minutes"


def schedule(plan, strategy="baseline", budget=None):
    if strategy not in ("baseline", "budgeted"):
        raise ValueError("unknown recommendation strategy")
    if budget is not None and (type(budget) is not int or not 1 <= budget <= 240):
        raise ValueError("budget must be an integer between 1 and 240")
    result = deepcopy(plan)
    steps = result["steps"]
    if any(type(s.get("estimated_minutes")) is not int or s["estimated_minutes"] <= 0 for s in steps):
        raise ValueError("each scheduled step needs a positive integer time estimate")
    parents = defaultdict(set)
    for edge in result["graph_edges"]:
        parents[edge["to_kp_id"]].add(edge["from_kp_id"])
    distance, queue = {result["target_kp_id"]: 0}, deque([result["target_kp_id"]])
    while queue:
        current = queue.popleft()
        for prior in parents[current]:
            if prior not in distance or distance[prior] > distance[current] + 1:
                distance[prior] = distance[current] + 1
                queue.append(prior)
    required = {s["knowledge_point_id"] for s in steps}
    dependencies = {}
    for step in steps:
        key = step["knowledge_point_id"]
        ancestors, pending = set(), list(parents[key])
        while pending:
            prior = pending.pop()
            if prior not in ancestors:
                ancestors.add(prior)
                pending.extend(parents[prior])
        # Traverse even mastered intermediate nodes to preserve transitive dependencies.
        dependencies[key] = ancestors & required
        weakness = 0.5 if step["mastery"] is None else 1 - step["mastery"]
        relevance = 1 / (1 + distance.get(key, len(steps)))
        step["priority_score"] = round((0.6 * weakness + 0.4 * relevance) / step["estimated_minutes"], 8)
    selected, selected_ids, used = [], set(), 0
    if strategy == "baseline":
        for step in steps:
            if budget is not None and used + step["estimated_minutes"] > budget:
                break
            selected.append(step)
            selected_ids.add(step["knowledge_point_id"])
            used += step["estimated_minutes"]
    else:
        if budget is None:
            raise ValueError("budgeted scheduling requires a budget")
        while True:
            ready = [
                s
                for s in steps
                if s["knowledge_point_id"] not in selected_ids
                and dependencies[s["knowledge_point_id"]] <= selected_ids
                and used + s["estimated_minutes"] <= budget
            ]
            if not ready:
                break
            step = min(ready, key=lambda s: (-s["priority_score"], s["code"], s["knowledge_point_id"]))
            selected.append(step)
            selected_ids.add(step["knowledge_point_id"])
            used += step["estimated_minutes"]
    remaining = [s for s in steps if s["knowledge_point_id"] not in selected_ids]
    for i, step in enumerate(selected, 1):
        step["order"] = i
    for i, step in enumerate(remaining, 1):
        step["order"] = i
        if dependencies[step["knowledge_point_id"]] - selected_ids:
            step["deferral_reason"] = "尚有先修步骤未安排；完成这些步骤后才能继续。"
        elif budget is not None and step["estimated_minutes"] > budget - used:
            step["deferral_reason"] = (
                f"剩余预算{budget - used}分钟，不足本步估计的{step['estimated_minutes']}分钟。"
            )
        else:
            step["deferral_reason"] = "基础策略保留原拓扑顺序的前缀，本次不跳过前序未安排步骤。"
    result.update(
        strategy=strategy,
        algorithm_version="ready-priority-budget-v1"
        if strategy == "budgeted"
        else "prerequisite-baseline-v2",
        time_budget_minutes=budget,
        estimated_minutes=used,
        full_path_estimated_minutes=used + sum(s["estimated_minutes"] for s in remaining),
        remaining_estimated_minutes=sum(s["estimated_minutes"] for s in remaining),
        steps=selected,
        remaining_steps=remaining,
        goal_in_plan=result["status"] == "target_mastered" or result["target_kp_id"] in selected_ids,
        scheduling_rule=SCHEDULING_RULE if strategy == "budgeted" else "topological_prefix",
    )
    return result
