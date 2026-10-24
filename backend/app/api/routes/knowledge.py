from fastapi import APIRouter, Response
from sqlalchemy import select

from app.api.deps import Db, Teacher, course_access
from app.core.errors import fail
from app.models import (
    Chapter,
    CourseResource,
    KnowledgeEdge,
    KnowledgePoint,
    MasteryProfile,
    PracticeExercise,
)
from app.schemas.foundation import ChapterOut, ChapterPatch, KpCreate, KpOut, KpPatch
from app.services.prerequisites import lock_course

router = APIRouter(tags=["Knowledge"])


def authorized_row(db, user, model, row_id):
    row = db.get(model, row_id)
    if row is None:
        fail(404, "NOT_FOUND", "章节或知识点不存在")
    course_access(db, user, row.course_id, edit=True)
    return row


@router.patch("/chapters/{chapter_id}", response_model=ChapterOut)
def edit_chapter(chapter_id: str, body: ChapterPatch, user: Teacher, db: Db):
    row = authorized_row(db, user, Chapter, chapter_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.flush()
    return row


@router.post("/chapters/{chapter_id}/knowledge-points", response_model=KpOut, status_code=201)
def add_kp(chapter_id: str, body: KpCreate, user: Teacher, db: Db):
    chapter = authorized_row(db, user, Chapter, chapter_id)
    if db.scalar(
        select(KnowledgePoint).where(
            KnowledgePoint.course_id == chapter.course_id, KnowledgePoint.code == body.code
        )
    ):
        fail(409, "KP_CODE_EXISTS", "本课程已存在该知识点编号")
    row = KnowledgePoint(chapter_id=chapter_id, course_id=chapter.course_id, **body.model_dump())
    db.add(row)
    db.flush()
    return row


@router.patch("/knowledge-points/{kp_id}", response_model=KpOut)
def edit_kp(kp_id: str, body: KpPatch, user: Teacher, db: Db):
    row = authorized_row(db, user, KnowledgePoint, kp_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.flush()
    return row


@router.delete("/knowledge-points/{kp_id}", status_code=204)
def delete_kp(kp_id: str, user: Teacher, db: Db):
    row = authorized_row(db, user, KnowledgePoint, kp_id)
    lock_course(db, row.course_id)
    if db.scalar(
        select(KnowledgeEdge).where((KnowledgeEdge.from_kp_id == kp_id) | (KnowledgeEdge.to_kp_id == kp_id))
    ):
        fail(409, "PREREQUISITES_EXIST", "该知识点仍有先修关系，请先移除相关关系。")
    if db.scalar(select(PracticeExercise).where(PracticeExercise.knowledge_point_id == kp_id)):
        fail(409, "PRACTICE_EXISTS", "该知识点已有小练习，暂不可删除")
    if db.scalar(select(MasteryProfile).where(MasteryProfile.knowledge_point_id == kp_id)):
        fail(409, "PROFILE_EXISTS", "该知识点已有学习画像记录，暂不可删除")
    resources = db.scalars(select(CourseResource).where(
        CourseResource.course_id == row.course_id, CourseResource.deleted_at.is_(None)
    ))
    if any(kp_id in resource.knowledge_point_ids for resource in resources):
        fail(409, "RESOURCE_EXISTS", "该知识点关联课程资料，请先在资料管理中解除关联")
    db.delete(row)
    db.flush()
    return Response(status_code=204)
