from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.security import hash_password
from app.models import Chapter, Course, CourseMember, KnowledgePoint, PracticeExercise, User
from app.schemas.recommendation import EdgeCreate
from app.services.prerequisites import add_edge, lock_course


def seed_id(name):
    return str(uuid5(NAMESPACE_URL, "se-learning/seed/" + name))


def seed_boundary_value(db):
    """Complete the existing seed course without replacing teacher-authored content."""
    course_id = seed_id("course")
    if db.get(Course, course_id) is None:
        raise ValueError("请先初始化预置课程，再补充边界值分析")
    lock_course(db, course_id)
    prerequisite = db.scalar(select(KnowledgePoint).where(
        KnowledgePoint.course_id == course_id, KnowledgePoint.code == "KP-TEST-01"
    ))
    if prerequisite is None:
        raise ValueError("预置课程缺少等价类划分知识点，未补充边界值分析")
    point = db.scalar(select(KnowledgePoint).where(
        KnowledgePoint.course_id == course_id, KnowledgePoint.code == "KP-BOUND-01"
    ))
    if point is None:
        point = KnowledgePoint(
            id=seed_id("KP-BOUND-01"), course_id=course_id, chapter_id=prerequisite.chapter_id,
            code="KP-BOUND-01", name="边界值分析",
            definition="优先检查允许范围的边界及其邻近值，结合等价类划分设计测试；"
                       "先明确端点是否包含和输入的最小变化单位，再说明各测试值的预期结果。",
            difficulty=2, bloom_level="apply", estimated_minutes=10,
        )
        db.add(point)
        db.flush()
    chapter = db.get(Chapter, point.chapter_id)
    if chapter is None or chapter.course_id != course_id:
        raise ValueError("边界值分析的章节归属无效，未补充配套内容")
    exercise = db.scalar(select(PracticeExercise).where(PracticeExercise.knowledge_point_id == point.id))
    if exercise is None:
        exercise = PracticeExercise(
            id=seed_id("KP-BOUND-01/practice"), course_id=course_id,
            chapter_id=point.chapter_id, knowledge_point_id=point.id,
            question_text="某系统要求密码长度为 8–20 个字符，包含两端；本题只考虑字符数，"
                          "长度按整数计，其他密码规则均已满足。请设计覆盖上下边界及内外紧邻长度的测试用例，"
                          "逐一说明预期接受还是拒绝及判断依据，并解释只测试长度为 12 的密码有什么不足。",
        )
        db.add(exercise)
        db.flush()
    edge = add_edge(db, course_id, EdgeCreate(from_kp_id=prerequisite.id, to_kp_id=point.id))
    return {"knowledge_point_id": point.id, "exercise_id": exercise.id, "prerequisite_id": edge.id}


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
    boundary = seed_boundary_value(db)
    from app.services.resources import import_builtins

    import_builtins(db, course_id)
    return {"accounts": [u.username for u in users], "course_id": course_id, "boundary_value": boundary}
