"""Remove only the course created by browser-foundation.cjs; retain screenshots."""

import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import ROOT, Settings
from app.core.database import database
from app.models import Chapter, Course, CourseMember, KnowledgePoint
from app.services.seed import seed_id
from sqlalchemy import delete

marker = ROOT / ".local" / "e2e-created-course.json"
if marker.exists():
    course_id = str(UUID(json.loads(marker.read_text(encoding="utf-8"))["id"]))
    engine, sessions = database(Settings().database_url)
    try:
        with sessions.begin() as db:
            course = db.get(Course, course_id)
            if course is not None:
                if course.title != "P1 浏览器验收课程" or course.teacher_id != seed_id(
                    "teacher"
                ):
                    raise RuntimeError("Fixture identity mismatch; no data removed")
                for model in (KnowledgePoint, Chapter, CourseMember):
                    db.execute(delete(model).where(model.course_id == course_id))
                db.delete(course)
        marker.unlink()
        print("Browser test course cleaned; original course and users retained.")
    finally:
        engine.dispose()
