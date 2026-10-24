"""Teacher document management and member-only previews/downloads."""

import json
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import CourseResource, ResourceVersion, VideoCompletion
from app.models.legacy import now
from app.schemas.resources import ParseJob, ResourcePatch, VersionOut
from app.schemas.workspace import ResourceOut
from app.services import resources as service
from app.services.prerequisites import lock_course
from app.services.resource_uploads import VIDEO_TYPES, prepare_upload, video_path

router = APIRouter(prefix="/courses/{course_id}/resources", tags=["Course resources"])


@router.post("", response_model=ParseJob, status_code=202)
async def upload(
    course_id: str, request: Request, tasks: BackgroundTasks, db: Db, user: Teacher,
    file: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=200),
    description: str = Form("", max_length=4000), chapter_id: str = Form("", max_length=36),
    knowledge_point_ids: str = Form("[]", max_length=5000),
):
    course_access(db, user, course_id, edit=True)
    try:
        points = json.loads(knowledge_point_ids)
        if not isinstance(points, list) or len(points) > 100 or any(not isinstance(p, str) or not 1 <= len(p) <= 36 for p in points):
            raise ValueError()
    except (ValueError, TypeError):
        fail(422, "INVALID_KNOWLEDGE_POINTS", "关联知识点格式不正确")
    if not title.strip():
        fail(422, "INVALID_TITLE", "请填写资料标题")
    prepared = await prepare_upload(file, request.app.state.settings)
    try:
        with request.app.state.sessions.begin() as session:
            lock_course(session, course_id)
            service.metadata_scope(session, course_id, chapter_id or None, points)
            resource = CourseResource(
                course_id=course_id, chapter_id=chapter_id or None, uploaded_by=user.id, origin="upload",
                title=title.strip(), description=description.strip(), knowledge_point_ids=points,
            )
            session.add(resource)
            session.flush()
            version = service.add_uploaded_version(session, resource, user.id, prepared)
            result = ParseJob(resource_id=resource.id, version=version.version, status=version.status)
            version_id = version.id
    except BaseException:
        prepared.cleanup(request.app.state.settings)
        raise
    if result.status == "pending":
        tasks.add_task(service.parse_version, request.app.state.sessions, version_id)
    return result


@router.post("/import-builtin")
def import_builtin(course_id: str, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    return {"imported": service.import_builtins(db, course_id)}


@router.patch("/{resource_id}", response_model=ResourceOut)
def edit(course_id: str, resource_id: str, body: ResourcePatch, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    lock_course(db, course_id)
    resource = service.get_resource(db, course_id, resource_id)
    values = body.model_dump(exclude_unset=True)
    chapter = values.get("chapter_id", resource.chapter_id) or None
    points = values.get("knowledge_point_ids", resource.knowledge_point_ids)
    service.metadata_scope(db, course_id, chapter, points)
    for name, value in values.items():
        setattr(resource, name, value or None if name == "chapter_id" else value)
    db.flush()
    return service.describe(db, resource)


@router.delete("/{resource_id}", status_code=204)
def remove(course_id: str, resource_id: str, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    lock_course(db, course_id)
    service.get_resource(db, course_id, resource_id).deleted_at = now()


@router.get("/{resource_id}/versions", response_model=list[VersionOut])
def versions(course_id: str, resource_id: str, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    resource = service.get_resource(db, course_id, resource_id)
    return db.scalars(select(ResourceVersion).where(ResourceVersion.resource_id == resource.id)
                      .order_by(ResourceVersion.version.desc())).all()


@router.post("/{resource_id}/versions", response_model=ParseJob, status_code=202)
async def replace(
    course_id: str, resource_id: str, db: Db, user: Teacher, request: Request,
    tasks: BackgroundTasks, file: UploadFile = File(...),
):
    course_access(db, user, course_id, edit=True)
    service.get_resource(db, course_id, resource_id)
    prepared = await prepare_upload(file, request.app.state.settings)
    try:
        with request.app.state.sessions.begin() as session:
            lock_course(session, course_id)
            resource = service.get_resource(session, course_id, resource_id)
            latest = service.version_for(session, resource)
            if latest.status in ("pending", "parsing"):
                fail(409, "PARSE_IN_PROGRESS", "请等待当前文件解析完成后再更新")
            version = service.add_uploaded_version(session, resource, user.id, prepared)
            result = ParseJob(resource_id=service.public_id(resource), version=version.version, status=version.status)
            version_id = version.id
    except BaseException:
        prepared.cleanup(request.app.state.settings)
        raise
    if result.status == "pending":
        tasks.add_task(service.parse_version, request.app.state.sessions, version_id)
    return result


@router.post("/{resource_id}/retry", response_model=ParseJob, status_code=202)
def retry(course_id: str, resource_id: str, db: Db, user: Teacher, request: Request, tasks: BackgroundTasks):
    course_access(db, user, course_id, edit=True)
    with request.app.state.sessions.begin() as session:
        lock_course(session, course_id)
        resource = service.get_resource(session, course_id, resource_id)
        version = service.version_for(session, resource)
        if version.status != "failed":
            fail(409, "RETRY_NOT_AVAILABLE", "仅解析失败的资料可以重试")
        version.status, version.error = "pending", None
        version_id = version.id
        result = ParseJob(resource_id=service.public_id(resource), version=version.version, status="pending")
    tasks.add_task(service.parse_version, request.app.state.sessions, version_id)
    return result


@router.post("/{resource_id}/versions/{version_number}/activate", response_model=ResourceOut)
def activate(course_id: str, resource_id: str, version_number: int, db: Db, user: Teacher):
    course_access(db, user, course_id, edit=True)
    lock_course(db, course_id)
    resource = service.get_resource(db, course_id, resource_id)
    version = service.version_for(db, resource, version_number)
    if version.status != "ready":
        fail(409, "RESOURCE_NOT_READY", "只能使用解析成功的版本")
    resource.current_version = version.version
    db.flush()
    return service.describe(db, resource)


@router.get("/{resource_id}/file")
def file(
    course_id: str, resource_id: str, db: Db, user: CurrentUser, request: Request,
    inline: bool = False, version: int | None = Query(default=None, ge=1),
):
    course_access(db, user, course_id)
    resource = service.get_resource(db, course_id, resource_id)
    if version is not None and version != resource.current_version and user.role != "teacher":
        fail(403, "TEACHER_REQUIRED", "历史文件仅供课程教师管理")
    original = service.version_for(db, resource, version)
    if original.file_type in VIDEO_TYPES:
        return FileResponse(
            video_path(request.app.state.settings, original), media_type=original.media_type,
            filename=original.filename, content_disposition_type="inline" if inline else "attachment",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    disposition = "inline" if inline and original.file_type == "pdf" else "attachment"
    # Downloads and explicit PDF preview requests are real events, not invented reading duration.
    if user.role == "student":
        service.record_access(db, user.id, resource, original, "preview_pdf" if disposition == "inline" else "download")
    return Response(original.original, media_type=original.media_type, headers={
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(original.filename, safe='')}",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
        "Content-Security-Policy": "sandbox",
    })


@router.post("/{resource_id}/complete", response_model=ResourceOut)
def complete_video(course_id: str, resource_id: str, db: Db, user: CurrentUser, request: Request):
    course_access(db, user, course_id)
    if user.role != "student":
        fail(403, "STUDENT_REQUIRED", "仅学生可以完成视频学习")
    resource = service.get_resource(db, course_id, resource_id)
    version = service.version_for(db, resource)
    if version.file_type not in VIDEO_TYPES or version.status != "ready":
        fail(422, "VIDEO_REQUIRED", "该资源不是可播放的视频")
    video_path(request.app.state.settings, version)
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    db.execute(insert(VideoCompletion).values(student_id=user.id, version_id=version.id).on_conflict_do_nothing())
    return service.describe(db, resource, student_id=user.id)
