"""Member C: course exercises and immutable answer/follow-up records."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.legacy import now, uid


class PracticeExercise(Base):
    __tablename__ = "practice_exercises"
    __table_args__ = (UniqueConstraint("knowledge_point_id", name="uq_practice_kp"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"))
    knowledge_point_id: Mapped[str] = mapped_column(ForeignKey("knowledge_points.id"))
    question_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PracticeSubmission(Base):
    __tablename__ = "practice_submissions"
    __table_args__ = (
        UniqueConstraint("exercise_id", "student_id", "request_id", name="uq_practice_request"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("practice_exercises.id"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    original_answer: Mapped[str] = mapped_column(Text)
    event_id: Mapped[str] = mapped_column(ForeignKey("learning_events.event_id"), unique=True)
    diagnosis_id: Mapped[str] = mapped_column(ForeignKey("diagnoses.id"), unique=True)
    request_id: Mapped[str] = mapped_column(String(36))
    parent_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("practice_submissions.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
