"""One authoritative, course-scoped store for documents, originals and parsed text."""

import hashlib
import json
import re
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, update

from app.core.config import ROOT
from app.core.errors import fail
from app.models import (
    Chapter,
    CourseResource,
    KnowledgePoint,
    LearningEvent,
    ResourceChunk,
    ResourceVersion,
    VideoCompletion,
)
from app.rag.chunker import Chunk, ParentBlock
from app.rag.config import RagConfig
from app.rag.index import RagIndex
from app.services.document_parser import MIME_TYPES, ParseError, extract_document, validate_file
from app.services.prerequisites import lock_course
from app.services.resource_uploads import VIDEO_TYPES


def public_id(resource):
    return "kb:" + resource.builtin_key if resource.builtin_key else resource.id


def get_resource(db, course_id, resource_id):
    query = select(CourseResource).where(CourseResource.course_id == course_id, CourseResource.deleted_at.is_(None))
    if resource_id.startswith("kb:"):
        query = query.where(CourseResource.builtin_key == resource_id[3:])
    else:
        query = query.where(CourseResource.id == resource_id)
    row = db.scalar(query)
    if row is None:
        fail(404, "RESOURCE_NOT_FOUND", "本课程的资料不存在或已删除")
    return row


def version_for(db, resource, number=None):
    row = db.scalar(select(ResourceVersion).where(
        ResourceVersion.resource_id == resource.id,
        ResourceVersion.version == (number if number is not None else resource.current_version),
    ))
    if row is None:
        fail(404, "VERSION_NOT_FOUND", "资料版本不存在")
    return row


def metadata_scope(db, course_id, chapter_id, point_ids):
    if chapter_id:
        chapter = db.get(Chapter, chapter_id)
        if chapter is None or chapter.course_id != course_id:
            fail(422, "CHAPTER_MISMATCH", "章节必须属于当前课程")
    if len(set(point_ids)) != len(point_ids):
        fail(422, "DUPLICATE_KNOWLEDGE_POINT", "关联知识点不能重复")
    for key in point_ids:
        point = db.get(KnowledgePoint, key)
        if point is None or point.course_id != course_id or (chapter_id and point.chapter_id != chapter_id):
            fail(422, "KNOWLEDGE_POINT_MISMATCH", "关联知识点必须属于当前课程及所选章节")


def describe(db, resource, student_id=None):
    version = version_for(db, resource)
    key = public_id(resource)
    base = f"/api/v1/courses/{quote(resource.course_id, safe='')}/resources/{quote(key, safe='')}"
    video = version.file_type in VIDEO_TYPES
    return dict(
        id=key, title=resource.title, type="video" if video else "doc", description=resource.description,
        knowledge_point_ids=resource.knowledge_point_ids, format=None if video else "markdown",
        chapter_id=resource.chapter_id, origin=resource.origin, uploaded_by=resource.uploaded_by,
        status=version.status, error=version.error, version=version.version, filename=version.filename,
        file_type=version.file_type, size_bytes=version.size_bytes, created_at=resource.created_at,
        url=base + f"/file?inline=true&version={version.version}" if video or version.file_type == "pdf" else None,
        download_url=base + "/file",
        completed=bool(video and student_id and db.get(VideoCompletion, (student_id, version.id))),
    )


def list_resources(db, course_id, student_id=None):
    rows = db.scalars(select(CourseResource).where(
        CourseResource.course_id == course_id, CourseResource.deleted_at.is_(None)
    ).order_by(CourseResource.created_at, CourseResource.id)).all()
    return [dict(id="kb:all", title="全部课程资料 · AI 问答", type="doc", url=None,
                 description="只检索本课程解析成功的当前版本资料。", knowledge_point_ids=[]),
            *[describe(db, r, student_id) for r in rows]]


def document_content(db, course_id, resource_id):
    resource = get_resource(db, course_id, resource_id)
    version = version_for(db, resource)
    if version.file_type in VIDEO_TYPES:
        fail(422, "VIDEO_HAS_NO_TEXT", "视频可直接播放，当前未提供讲稿文字")
    if version.status != "ready":
        fail(409, "RESOURCE_NOT_READY", version.error or "资料正在解析，请稍后刷新")
    return {"resource_id": public_id(resource), "title": resource.title, "markdown": version.markdown}


def add_version(db, resource, user_id, filename, data):
    name, kind = validate_file(filename, data)
    numbers = db.scalars(select(ResourceVersion.version).where(ResourceVersion.resource_id == resource.id)).all()
    number = max(numbers, default=0) + 1
    version = ResourceVersion(
        resource_id=resource.id, version=number, filename=name, file_type=kind, media_type=MIME_TYPES[kind],
        size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), original=data,
        uploaded_by=user_id, status="pending", markdown="",
    )
    db.add(version)
    resource.current_version = number
    db.flush()
    return version


def add_uploaded_version(db, resource, user_id, upload):
    previous = db.scalar(select(ResourceVersion).where(
        ResourceVersion.resource_id == resource.id, ResourceVersion.version == resource.current_version
    ))
    video = upload.kind in VIDEO_TYPES
    if previous is not None and (previous.file_type in VIDEO_TYPES) != video:
        fail(422, "RESOURCE_TYPE_MISMATCH", "文档和视频请分别新建资源，不能互相替换版本")
    if not video:
        return add_version(db, resource, user_id, upload.filename, upload.data)
    numbers = db.scalars(select(ResourceVersion.version).where(ResourceVersion.resource_id == resource.id)).all()
    number = max(numbers, default=0) + 1
    version = ResourceVersion(
        resource_id=resource.id, version=number, filename=upload.filename, file_type=upload.kind,
        media_type=VIDEO_TYPES[upload.kind], size_bytes=upload.size, sha256=upload.sha256,
        original=b"", storage_path=upload.storage_path, uploaded_by=user_id, status="ready", markdown="",
    )
    resource.current_version = number
    db.add(version)
    db.flush()
    return version


def parse_version(sessions, version_id):
    # A persisted pending version survives upload/parse failures and can be retried.
    with sessions.begin() as db:
        version = db.get(ResourceVersion, version_id)
        if version is None or version.status != "pending":
            return
        claimed = db.execute(update(ResourceVersion).where(
            ResourceVersion.id == version_id, ResourceVersion.status == "pending"
        ).values(status="parsing"))
        if claimed.rowcount != 1:
            return
        data, kind = version.original, version.file_type
    try:
        markdown, parts = extract_document(data, kind)
        error = None
    except ParseError as exc:
        markdown, parts, error = "", [], str(exc)
    except Exception:
        markdown, parts, error = "", [], "资料解析失败，请重新导出文档或稍后重试。"
    with sessions.begin() as db:
        version = db.get(ResourceVersion, version_id)
        if version is None or version.status != "parsing":
            return
        version.markdown, version.error = markdown, error
        for i, (page, section, text) in enumerate(parts):
            db.add(ResourceChunk(version_id=version.id, ordinal=i, section=section[:400], page=page, text=text))
        version.status = "failed" if error else "ready"


def recover_parsing(db):
    db.execute(update(ResourceVersion).where(ResourceVersion.status.in_(["pending", "parsing"])).values(
        status="failed", error="解析任务被服务重启中断，请教师点击重新解析。"
    ))


def record_access(db, actor, resource, version, action):
    db.add(LearningEvent(
        actor=actor, verb="downloaded" if action == "download" else "viewed",
        object={"type": "resource", "id": public_id(resource), "resource_type": "doc",
                "kp": resource.knowledge_point_ids, "version": version.version, "title": resource.title},
        result={"action": action},
        context={"course": resource.course_id, "source": "resource_access", "synthetic": False},
    ))


def import_builtins(db, course_id):
    """Import snapshots exactly once; preserve teacher edits, versions and deletions."""
    from app.services.learning_curriculum import LECTURE_SECTIONS

    lock_course(db, course_id)
    points = db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)).all()
    imported = 0
    for path in sorted((ROOT / "data/kb/docs").glob("*.md")):
        match = re.match(r"^([A-Za-z]+-\d+)", path.stem)
        key = match[1] if match else path.stem
        if db.scalar(select(CourseResource).where(CourseResource.course_id == course_id, CourseResource.builtin_key == key)):
            continue
        meta_path = ROOT / "data/kb/meta" / (path.name + ".json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        linked = [p for p in points if LECTURE_SECTIONS.get(p.code, (None,))[0] == "kb:" + key]
        chapter_ids = {p.chapter_id for p in linked}
        resource = CourseResource(
            id=str(uuid5(NAMESPACE_URL, f"se-learning/resource/{course_id}/{key}")), course_id=course_id,
            chapter_id=next(iter(chapter_ids)) if len(chapter_ids) == 1 else None,
            origin="builtin", uploaded_by=None, builtin_key=key, title=meta.get("title", path.stem),
            description="系统导入的项目自编讲义，可由课程教师维护。", knowledge_point_ids=[p.id for p in linked],
        )
        db.add(resource)
        db.flush()
        data = path.read_bytes()
        version = add_version(db, resource, None, path.name, data)
        markdown, parts = extract_document(data, "md")
        version.markdown, version.status = markdown, "ready"
        db.add_all([ResourceChunk(version_id=version.id, ordinal=i, page=page, section=section[:400], text=text)
                    for i, (page, section, text) in enumerate(parts)])
        imported += 1
    db.flush()
    return imported


def course_index(db, settings, course_id):
    """Build only from this course's current ready versions; no shared-KB fallback."""
    from app.services.learning_curriculum import LECTURE_SECTIONS

    cfg = RagConfig.from_settings(settings)
    rows = db.execute(select(CourseResource, ResourceVersion, ResourceChunk).join(
        ResourceVersion, (ResourceVersion.resource_id == CourseResource.id)
        & (ResourceVersion.version == CourseResource.current_version)
    ).join(ResourceChunk, ResourceChunk.version_id == ResourceVersion.id).where(
        CourseResource.course_id == course_id, CourseResource.deleted_at.is_(None), ResourceVersion.status == "ready"
    ).order_by(CourseResource.id, ResourceChunk.ordinal)).all()
    points = {p.id: p for p in db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id))}
    chunks, parents, raw_kps = [], [], []
    seen = set()
    for resource, version, block in rows:
        doc_id = resource.builtin_key or resource.id
        linked = [points[k] for k in resource.knowledge_point_ids if k in points]
        if resource.builtin_key and version.uploaded_by is None:
            linked = [p for p in linked if p.code not in LECTURE_SECTIONS
                      or LECTURE_SECTIONS[p.code][1] in block.section]
        kp_ids = [p.id for p in linked]
        for p in linked:
            if p.id not in seen:
                raw_kps.append(dict(id=p.id, name=p.name, definition=p.definition, difficulty=p.difficulty,
                                    bloom=p.bloom_level, doc_id=doc_id, doc_title=resource.title))
                seen.add(p.id)
        parents.append(ParentBlock(block.id, doc_id, resource.title, block.section, block.text, kp_ids))
        chunks.append(Chunk(block.id, doc_id, resource.title, block.section, [block.section], block.id,
                            block.text, "body", kp_ids, block.ordinal))
    return RagIndex(cfg).build_materials(chunks, parents, raw_kps)
