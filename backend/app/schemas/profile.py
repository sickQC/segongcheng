from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MasteryPointOut(BaseModel):
    knowledge_point_id: str
    name: str
    mastery_percent: float | None = Field(ge=0, le=100)
    confidence_percent: float | None = Field(ge=0, le=100)
    report_id: str | None
    evidence_ids: list[str]
    input_cutoff: datetime | None
    updated_at: datetime | None
    accuracy_percent: float | None = Field(ge=0, le=100)
    question_count: int


class KnowledgeDimension(BaseModel):
    known_points: int
    total_points: int
    points: list[MasteryPointOut]
    explanation: str


class EngagementDimension(BaseModel):
    active_days: int
    event_count: int
    effective_seconds: float | None
    observed_resource_count: int
    completed_resource_percent: float | None
    explanation: str


class PreferenceItem(BaseModel):
    key: Literal["video", "read", "ask", "practice"]
    label: str
    count: int | None
    percent: float | None


class PreferenceDimension(BaseModel):
    items: list[PreferenceItem]
    explanation: str


class RiskDimension(BaseModel):
    level: Literal["unknown", "attention", "normal"]
    reasons: list[str]
    evidence_ids: list[str]
    explanation: str


class LearningProfileOut(BaseModel):
    student_id: str
    course_id: str
    rule_version: str
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    knowledge: KnowledgeDimension
    engagement: EngagementDimension
    preference: PreferenceDimension
    risk: RiskDimension


class EventOut(BaseModel):
    event_id: str
    actor: str
    verb: str
    object: dict
    result: dict
    context: dict
    timestamp: datetime


class EventPage(BaseModel):
    items: list[EventOut]
    next_offset: int | None
    window_start: datetime
    window_end: datetime


class SnapshotCreate(BaseModel):
    model_config = {"extra": "forbid"}
    request_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    days: int = Field(default=30, ge=1, le=90, strict=True)


class SnapshotSummary(BaseModel):
    id: str
    reason: Literal["manual", "diagnosis"]
    report_id: str | None
    days: int
    created_at: datetime
    rule_version: str
    origin: Literal["manual", "diagnosis", "backfill"] = "diagnosis"
    source_report_created_at: datetime | None = None

    @field_validator("created_at")
    @classmethod
    def as_utc(cls, value):
        from app.services.learning_events import utc

        return utc(value)


class SnapshotOut(SnapshotSummary):
    profile: LearningProfileOut


class SnapshotPage(BaseModel):
    items: list[SnapshotSummary]
    next_offset: int | None


class MetricChange(BaseModel):
    before: float | None
    after: float | None
    delta: float | None


class PointChange(BaseModel):
    knowledge_point_id: str
    name: str
    mastery: MetricChange
    accuracy: MetricChange


class SnapshotComparison(BaseModel):
    before: SnapshotSummary
    after: SnapshotSummary
    points: list[PointChange]
    engagement: dict[str, MetricChange]
    preference: dict[str, MetricChange]
    risk_before: Literal["unknown", "attention", "normal"]
    risk_after: Literal["unknown", "attention", "normal"]
    warnings: list[str]
