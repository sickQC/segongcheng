"""Explicit course-topic/lecture-section bindings, checked against actual headings."""

import re

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Chapter, CourseResource, KnowledgePoint
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


def lecture_materials(settings, course_id, code, db=None):
    if db is not None:
        from app.services.resources import document_content

        point = db.scalar(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id, KnowledgePoint.code == code))
        if point is None:
            return []
        resources = db.scalars(select(CourseResource).where(
            CourseResource.course_id == course_id, CourseResource.deleted_at.is_(None)
        ).order_by(CourseResource.created_at, CourseResource.id)).all()
        materials = []
        for resource in resources:
            if point.id not in resource.knowledge_point_ids:
                continue
            resource_id = "kb:" + resource.builtin_key if resource.builtin_key else resource.id
            try:
                document = document_content(db, course_id, resource_id)
            except HTTPException:
                continue
            section = LECTURE_SECTIONS.get(code, (None, "正文"))[1]
            excerpt = section_excerpt(document["markdown"], section)
            if not excerpt:
                section, excerpt = "正文", document["markdown"]
            materials.append({"resource_id": resource_id, "title": resource.title,
                              "section": section, "excerpt": excerpt[:6000]})
        return materials
    if settings is None or course_id != DEMO_COURSE_ID or code not in LECTURE_SECTIONS:
        return []
    resource_id, section = LECTURE_SECTIONS[code]
    try:
        document = markdown_document(settings, resource_id)
    except (HTTPException, OSError, RuntimeError):
        return []
    excerpt = section_excerpt(document["markdown"], section)
    return [{"resource_id": resource_id, "title": document["title"], "section": section, "excerpt": excerpt[:6000]}] if excerpt else []


def section_excerpt(markdown, section):
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", markdown))
    for index, heading in enumerate(headings):
        if heading[2] != section:
            continue
        end = next(
            (h.start() for h in headings[index + 1 :] if len(h[1]) <= len(heading[1])),
            len(markdown),
        )
        return markdown[heading.end() : end].strip()
    return ""


def lecture_links(materials):
    return [{key: item[key] for key in ("resource_id", "title", "section")} for item in materials]
