"""Mastery projection; source diagnoses remain immutable and independently auditable."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.legacy import now, uid


class ProfileApplication(Base):
    __tablename__ = "profile_applications"
    report_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_reports.id"), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProfileSnapshot(Base):
    __tablename__ = "profile_snapshots"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", "request_id", name="uq_profile_snapshot_request"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(String(20))
    report_id: Mapped[str | None] = mapped_column(ForeignKey("diagnosis_reports.id"), nullable=True)
    days: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MasteryProfile(Base):
    __tablename__ = "mastery_profiles"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", "knowledge_point_id", name="uq_mastery_scope"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    knowledge_point_id: Mapped[str] = mapped_column(ForeignKey("knowledge_points.id"))
    mastery: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_reports.id"))
    evidence_ids: Mapped[list] = mapped_column(JSON)
    input_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_order: Mapped[str] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
