import secrets
from datetime import timezone
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import fail
from app.core.security import token_hash
from app.models import Course, CourseMember, User, UserSession
from app.models.legacy import now


def get_db(request: Request):
    with request.app.state.sessions.begin() as session:
        yield session


Db = Annotated[Session, Depends(get_db)]


def trusted_origin(request: Request):
    origin = request.headers.get("origin")
    if origin not in request.app.state.settings.allowed_origins:
        fail(403, "UNTRUSTED_ORIGIN", "请求来源不受信任，请从本应用页面操作")


def current_session(request: Request, db: Db):
    raw = request.cookies.get("se_session", "")
    if not raw or len(raw) > 200:
        fail(401, "NOT_AUTHENTICATED", "请先登录")
    auth = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw)))
    if auth is None:
        fail(401, "SESSION_EXPIRED", "登录已失效，请重新登录")
    expiry = auth.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= now():
        fail(401, "SESSION_EXPIRED", "登录已过期，请重新登录")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        trusted_origin(request)
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), auth.csrf_token):
            fail(403, "CSRF_INVALID", "请求校验失败，请刷新页面后重试")
    return auth


Auth = Annotated[UserSession, Depends(current_session)]


def current_user(auth: Auth, db: Db):
    user = db.get(User, auth.user_id)
    if user is None:
        fail(401, "NOT_AUTHENTICATED", "请重新登录")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def teacher(user: CurrentUser):
    if user.role != "teacher":
        fail(403, "TEACHER_REQUIRED", "此操作仅限教师")
    return user


Teacher = Annotated[User, Depends(teacher)]


def course_access(db, user, course_id, *, edit=False):
    course = db.get(Course, course_id)
    if course is None:
        fail(404, "COURSE_NOT_FOUND", "课程不存在")
    member = db.scalar(
        select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user.id)
    )
    if member is None or (edit and (user.role != "teacher" or member.role != "teacher")):
        fail(403, "COURSE_FORBIDDEN", "无权访问或编辑该课程")
    return course
