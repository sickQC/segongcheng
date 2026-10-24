"""Course-owned documents with immutable originals, versions and extracted chunks."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.legacy import now, uid


class CourseResource(Base):
    __tablename__ = "course_resources"
    __table_args__ = (UniqueConstraint("course_id", "builtin_key", name="uq_resource_builtin"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    origin: Mapped[str] = mapped_column(String(20))
    builtin_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    knowledge_point_ids: Mapped[list] = mapped_column(JSON, default=list)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResourceVersion(Base):
    __tablename__ = "resource_versions"
    __table_args__ = (UniqueConstraint("resource_id", "version", name="uq_resource_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    resource_id: Mapped[str] = mapped_column(ForeignKey("course_resources.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    original: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    storage_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    markdown: Mapped[str] = mapped_column(Text, default="", deferred=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResourceChunk(Base):
    __tablename__ = "resource_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    version_id: Mapped[str] = mapped_column(ForeignKey("resource_versions.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(400))
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)


class VideoCompletion(Base):
    """One opened/completed flag per student and version; no watching telemetry."""

    __tablename__ = "video_completions"
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("resource_versions.id"), primary_key=True)
