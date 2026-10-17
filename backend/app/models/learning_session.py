"""Member C: persistent 5E state and immutable model-evaluated turns."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.legacy import now, uid


class LearningSession(Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (UniqueConstraint("student_id", "request_id", name="uq_learning_session_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    knowledge_point_id: Mapped[str] = mapped_column(ForeignKey("knowledge_points.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    stage: Mapped[str] = mapped_column(String(20), default="engage")
    status: Mapped[str] = mapped_column(String(20), default="active")
    pending_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LearningTurn(Base):
    __tablename__ = "learning_turns"
    __table_args__ = (UniqueConstraint("session_id", "request_id", name="uq_learning_turn_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("learning_sessions.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    answer: Mapped[str] = mapped_column(Text)
    evaluation_choice: Mapped[str | None] = mapped_column(String(20), nullable=True)
    stage_before: Mapped[str] = mapped_column(String(20))
    stage_after: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("learning_events.event_id"), unique=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("model_traces.trace_id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
