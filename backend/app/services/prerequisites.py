"""Small course graph interface; direction is prerequisite -> subsequent knowledge point."""

import heapq
from collections import defaultdict, deque

from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.errors import fail
from app.models import Course, KnowledgeEdge, KnowledgePoint


def lock_course(db, course_id):
    # Serialize graph mutations AND recommendation input reads per course on SQLite/PostgreSQL.
    # A no-op update takes a write/row lock without changing course content.
    db.execute(update(Course).where(Course.id == course_id).values(id=Course.id))


def path_between(adjacency, start, target):
    queue, previous = deque([start]), {start: None}
    while queue:
        current = queue.popleft()
        if current == target:
            path = []
            while current is not None:
                path.append(current)
                current = previous[current]
            return list(reversed(path))
        for following in sorted(adjacency[current]):
            if following not in previous:
                previous[following] = current
                queue.append(following)
    return None


def cycle_error(cycle):
    raise HTTPException(
        409,
        detail={
            "code": "PREREQUISITE_CYCLE",
            "message": "先修关系形成环，请调整后重试。",
            "fields": {"cycle": cycle},
        },
    )


def adjacency_for(edges):
    result = defaultdict(set)
    for edge in edges:
        result[edge.from_kp_id].add(edge.to_kp_id)
    return result


def ordered_graph(points, edges):
    by_id = {p.id: p for p in points}
    if any(e.from_kp_id not in by_id or e.to_kp_id not in by_id for e in edges):
        fail(409, "INVALID_PREREQUISITE_GRAPH", "先修关系包含不属于本课程的知识点，请教师检查。")
    adjacency, degree = adjacency_for(edges), {p.id: 0 for p in points}
    for edge in edges:
        degree[edge.to_kp_id] += 1
    ready = [(by_id[key].code, key) for key, value in degree.items() if value == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        _, key = heapq.heappop(ready)
        ordered.append(key)
        for following in sorted(adjacency[key]):
            degree[following] -= 1
            if degree[following] == 0:
                heapq.heappush(ready, (by_id[following].code, following))
    if len(ordered) != len(points):
        # Find a concrete cycle iteratively; large chains must not hit Python recursion limits.
        for edge in edges:
            if degree[edge.from_kp_id] and degree[edge.to_kp_id]:
                path = path_between(adjacency, edge.to_kp_id, edge.from_kp_id)
                if path:
                    cycle_error([edge.from_kp_id, *path])
        fail(409, "INVALID_PREREQUISITE_GRAPH", "先修图无法排序，请教师检查。")
    return ordered


def list_edges(db, course_id):
    return db.scalars(
        select(KnowledgeEdge)
        .where(KnowledgeEdge.course_id == course_id)
        .order_by(KnowledgeEdge.from_kp_id, KnowledgeEdge.to_kp_id)
    ).all()


def add_edge(db, course_id, body):
    lock_course(db, course_id)
    points = [db.get(KnowledgePoint, key) for key in (body.from_kp_id, body.to_kp_id)]
    if any(p is None or p.course_id != course_id for p in points):
        fail(422, "KNOWLEDGE_POINT_MISMATCH", "先修关系两端必须属于本课程。")
    if body.from_kp_id == body.to_kp_id:
        cycle_error([body.from_kp_id, body.from_kp_id])
    edges = list_edges(db, course_id)
    existing = next(
        (e for e in edges if e.from_kp_id == body.from_kp_id and e.to_kp_id == body.to_kp_id), None
    )
    if existing:
        return existing
    path = path_between(adjacency_for(edges), body.to_kp_id, body.from_kp_id)
    if path:
        cycle_error([body.from_kp_id, *path])
    row = KnowledgeEdge(course_id=course_id, **body.model_dump())
    db.add(row)
    db.flush()
    return row
