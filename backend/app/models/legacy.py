from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class LearningEvent(Base):
    __tablename__ = "learning_events"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(100), index=True)
    verb: Mapped[str] = mapped_column(String(40))
    object: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    context: Mapped[dict] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey("learning_events.event_id"), index=True)
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelTrace(Base):
    __tablename__ = "model_traces"
    trace_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    diagnosis_id: Mapped[str | None] = mapped_column(ForeignKey("diagnoses.id"), index=True, nullable=True)
    # Match the existing RAG migration: event identifier, without a foreign key.
    event_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    feature: Mapped[str] = mapped_column(
        String(40), default="diagnosis", server_default="diagnosis", index=True
    )
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(40), default="diagnosis-v1")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    input_summary: Mapped[dict] = mapped_column(JSON)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
