from sqlalchemy import select

from app.models import Chapter, Course, CourseMember, CourseResource, KnowledgePoint
from app.schemas.foundation import ChapterOutline, CourseOut, KpOut, Outline


def user_courses(db, user_id):
    return list(
        db.scalars(
            select(Course)
            .join(CourseMember)
            .where(CourseMember.user_id == user_id)
            .order_by(Course.created_at, Course.id)
        )
    )


def create_course(db, teacher, body):
    course = Course(**body.model_dump(), teacher_id=teacher.id)
    db.add(course)
    db.flush()
    db.add(CourseMember(course_id=course.id, user_id=teacher.id, role="teacher"))
    db.flush()
    return course


def outline(db, course):
    chapters = db.scalars(
        select(Chapter).where(Chapter.course_id == course.id).order_by(Chapter.sort_order, Chapter.id)
    ).all()
    points = db.scalars(
        select(KnowledgePoint).where(KnowledgePoint.course_id == course.id).order_by(KnowledgePoint.code)
    ).all()
    resources = db.scalars(select(CourseResource).where(
        CourseResource.course_id == course.id, CourseResource.deleted_at.is_(None)
    )).all()
    return Outline(
        course=CourseOut.model_validate(course),
        chapters=[
            ChapterOutline(
                **{k: getattr(ch, k) for k in ("id", "course_id", "title", "sort_order")},
                knowledge_points=[KpOut.model_validate(kp).model_copy(update={
                    "resource_ids": ["kb:" + r.builtin_key if r.builtin_key else r.id
                                     for r in resources if kp.id in r.knowledge_point_ids]
                }) for kp in points if kp.chapter_id == ch.id],
            )
            for ch in chapters
        ],
    )
