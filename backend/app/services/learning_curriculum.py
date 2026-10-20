"""Explicit course-topic/lecture-section bindings, checked against actual headings."""

import re

from fastapi import HTTPException

from app.models import Chapter
from app.services.course_documents import markdown_document
from app.services.personalization import DEMO_COURSE_ID

LECTURE_SECTIONS = {
    "KP-REQ-01": ("kb:SE-02", "功能性需求与非功能性需求"),
    "KP-REQ-02": ("kb:SE-02", "用例与参与者"),
    "KP-VAL-01": ("kb:SE-06", "软件验证与确认"),
    "KP-TEST-01": ("kb:SE-06", "等价类划分"),
    "KP-BOUND-01": ("kb:SE-06", "边界值分析"),
}


def chapter_for(db, point):
    chapter = db.get(Chapter, point.chapter_id) if point else None
    if not chapter or chapter.course_id != point.course_id:
        return None
    return {"id": chapter.id, "title": chapter.title, "sort_order": chapter.sort_order}


def lecture_materials(settings, course_id, code):
    if settings is None or course_id != DEMO_COURSE_ID or code not in LECTURE_SECTIONS:
        return []
    resource_id, section = LECTURE_SECTIONS[code]
    try:
        document = markdown_document(settings, resource_id)
    except (HTTPException, OSError, RuntimeError):
        return []
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", document["markdown"]))
    for index, heading in enumerate(headings):
        if heading[2] != section:
            continue
        end = next(
            (h.start() for h in headings[index + 1 :] if len(h[1]) <= len(heading[1])),
            len(document["markdown"]),
        )
        excerpt = document["markdown"][heading.end() : end].strip()
        if not excerpt:
            return []
        return [
            {
                "resource_id": resource_id,
                "title": document["title"],
                "section": section,
                "excerpt": excerpt[:6000],
            }
        ]
    return []


def lecture_links(materials):
    return [{key: item[key] for key in ("resource_id", "title", "section")} for item in materials]
