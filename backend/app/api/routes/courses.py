from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, Db, Teacher, course_access
from app.core.errors import fail
from app.models import Chapter, CourseMember, User
from app.schemas.foundation import (
    ChapterCreate,
    ChapterOut,
    CourseCreate,
    CourseOut,
    MemberCreate,
    MemberOut,
    Outline,
    Page,
)
from app.services.courses import create_course, outline, user_courses

router = APIRouter(tags=["Courses"])


@router.get("/courses", response_model=Page[CourseOut])
def courses(
    user: CurrentUser,
    db: Db,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    rows = user_courses(db, user.id)
    start = (page - 1) * page_size
    return Page[CourseOut](
        items=rows[start : start + page_size], total=len(rows), page=page, page_size=page_size
    )


@router.post("/courses", response_model=CourseOut, status_code=201)
def add_course(body: CourseCreate, user: Teacher, db: Db):
    return create_course(db, user, body)


@router.get("/courses/{course_id}/outline", response_model=Outline)
def course_outline(course_id: str, user: CurrentUser, db: Db):
    return outline(db, course_access(db, user, course_id))


@router.post("/courses/{course_id}/chapters", response_model=ChapterOut, status_code=201)
def add_chapter(course_id: str, body: ChapterCreate, user: Teacher, db: Db):
    course_access(db, user, course_id, edit=True)
    row = Chapter(course_id=course_id, **body.model_dump())
    db.add(row)
    db.flush()
    return row


@router.get("/courses/{course_id}/members", response_model=Page[MemberOut])
def members(
    course_id: str,
    user: Teacher,
    db: Db,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    course_access(db, user, course_id, edit=True)
    query = select(User, CourseMember.role).join(CourseMember).where(CourseMember.course_id == course_id)
    total = db.scalar(
        select(func.count()).select_from(CourseMember).where(CourseMember.course_id == course_id)
    )
    rows = db.execute(query.order_by(User.username).offset((page - 1) * page_size).limit(page_size))
    return Page[MemberOut](
        items=[MemberOut(user=u, role=r) for u, r in rows], total=total, page=page, page_size=page_size
    )


@router.post("/courses/{course_id}/members", response_model=MemberOut, status_code=201)
def add_member(course_id: str, body: MemberCreate, user: Teacher, db: Db):
    course_access(db, user, course_id, edit=True)
    student = db.scalar(select(User).where(User.username == body.username))
    if student is None or student.role != "student":
        fail(404, "STUDENT_NOT_FOUND", "学生账号不存在，请先初始化演示账号")
    if db.scalar(
        select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == student.id)
    ):
        fail(409, "MEMBER_EXISTS", "该学生已加入课程")
    db.add(CourseMember(course_id=course_id, user_id=student.id, role="student"))
    db.flush()
    return MemberOut(user=student, role="student")
