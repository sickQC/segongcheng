from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.security import hash_password
from app.models import Chapter, Course, CourseMember, KnowledgePoint, User


def seed_id(name):
    return str(uuid5(NAMESPACE_URL, "se-learning/seed/" + name))


def seed_data(db, password):
    if len(password) < 8:
        raise ValueError("SEED_PASSWORD 至少 8 位，请在本机 .env 设置")
    accounts = [
        ("teacher", "演示教师", "teacher"),
        ("student01", "模拟学生 01", "student"),
        ("student02", "模拟学生 02", "student"),
    ]
    users = []
    for username, display_name, role in accounts:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                id=seed_id(username),
                username=username,
                display_name=display_name,
                role=role,
                password_hash=hash_password(password),
            )
            db.add(user)
            db.flush()
        elif user.id != seed_id(username) or user.role != role:
            raise ValueError("演示账号名称与已有账号冲突，未覆盖数据")
        users.append(user)
    course_id = seed_id("course")
    if db.get(Course, course_id) is None:
        db.add(
            Course(
                id=course_id,
                title="软件工程基础",
                teacher_id=users[0].id,
                description="围绕需求分析与软件测试，建立清晰的课程知识结构。当前已开放课程目录浏览。",
            )
        )
        db.flush()
    for user in users:
        if not db.scalar(
            select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user.id)
        ):
            db.add(CourseMember(course_id=course_id, user_id=user.id, role=user.role))
    chapters = [("requirements", "第一章 需求工程", 1), ("testing", "第二章 软件测试", 2)]
    for key, title, order in chapters:
        if db.get(Chapter, seed_id(key)) is None:
            db.add(Chapter(id=seed_id(key), course_id=course_id, title=title, sort_order=order))
    db.flush()
    points = [
        (
            "KP-REQ-01",
            "requirements",
            "功能需求与非功能需求",
            "功能需求描述系统做什么，非功能需求约束系统如何运行。",
            1,
            "understand",
        ),
        (
            "KP-REQ-02",
            "requirements",
            "用例与参与者",
            "通过参与者与系统交互描述用户目标及其实现过程。",
            2,
            "apply",
        ),
        (
            "KP-VAL-01",
            "testing",
            "软件验证与确认",
            "验证关注是否符合规定要求；确认关注是否满足预期用途和用户需要。",
            2,
            "analyze",
        ),
        (
            "KP-TEST-01",
            "testing",
            "等价类划分",
            "将输入域划分为预期具有相似行为的类别，选择代表值进行测试。",
            2,
            "apply",
        ),
    ]
    for code, chapter, name, definition, difficulty, bloom in points:
        if db.get(KnowledgePoint, seed_id(code)) is None:
            db.add(
                KnowledgePoint(
                    id=seed_id(code),
                    course_id=course_id,
                    chapter_id=seed_id(chapter),
                    code=code,
                    name=name,
                    definition=definition,
                    difficulty=difficulty,
                    bloom_level=bloom,
                )
            )
    db.flush()
    return {"accounts": [u.username for u in users], "course_id": course_id}
