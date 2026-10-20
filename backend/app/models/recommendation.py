"""Course prerequisite graph and immutable student recommendation snapshots."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.legacy import now, uid


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        UniqueConstraint("course_id", "from_kp_id", "to_kp_id", name="uq_prerequisite_edge"),
        CheckConstraint("from_kp_id <> to_kp_id", name="ck_prerequisite_not_self"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    from_kp_id: Mapped[str] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    to_kp_id: Mapped[str] = mapped_column(ForeignKey("knowledge_points.id"), index=True)


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", "request_id", name="uq_recommendation_request"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    # Historical targets and steps are frozen IDs/names, retained if a point is later removed.
    target_kp_id: Mapped[str] = mapped_column(String(36))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"
    __table_args__ = (CheckConstraint("choice IN ('accepted', 'declined')", name="ck_feedback_choice"),)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    choice: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
