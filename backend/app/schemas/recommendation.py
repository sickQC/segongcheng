from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EdgeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_kp_id: str = Field(min_length=1, max_length=36)
    to_kp_id: str = Field(min_length=1, max_length=36)


class EdgeOut(EdgeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    course_id: str


class RecommendationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_kp_id: str = Field(min_length=1, max_length=36)
    strategy: Literal["baseline", "budgeted"] = "baseline"
    time_budget_minutes: int | None = Field(default=None, ge=1, le=240, strict=True)
    request_id: UUID = Field(default_factory=uuid4)

    @model_validator(mode="after")
    def budget_required(self):
        if self.strategy == "budgeted" and self.time_budget_minutes is None:
            raise ValueError("时间预算推荐须填写1–240分钟预算")
        return self


class LearningAction(BaseModel):
    kind: Literal["knowledge", "practice"]
    id: str
    title: str
    url: str


class PathPoint(BaseModel):
    knowledge_point_id: str
    code: str
    name: str
    mastery: float | None = Field(ge=0, le=1)
    confidence: float | None = Field(ge=0, le=1)
    diagnosis_id: str | None
    evidence_ids: list[str]
    input_cutoff: datetime | None
    reason: str
    reason_source: Literal["diagnosis", "prerequisite_rule"]


class PathStep(PathPoint):
    estimated_minutes: int | None = None
    estimate_source: Literal["teacher", "rule_estimate"] | None = None
    priority_score: float | None = None
    deferral_reason: str | None = None
    order: int
    prerequisite_ids: list[str]
    actions: list[LearningAction]
    notes: list[str]


class RecommendationOut(BaseModel):
    id: str
    course_id: str
    student_id: str
    created_at: datetime
    strategy: Literal["baseline", "budgeted"]
    time_budget_minutes: int | None = None
    estimated_minutes: int | None = None
    full_path_estimated_minutes: int | None = None
    remaining_estimated_minutes: int | None = None
    remaining_steps: list[PathStep] = Field(default_factory=list)
    goal_in_plan: bool | None = None
    scheduling_rule: str | None = None
    algorithm_version: str
    mastery_threshold: float
    target_kp_id: str
    target_name: str
    status: Literal["ready", "target_mastered"]
    input_cutoff: datetime
    graph_edges: list[EdgeCreate]
    steps: list[PathStep]
    skipped: list[PathPoint]
    notes: list[str]


class StudyTimeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estimated_minutes: int | None = Field(ge=1, le=240, strict=True)


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: Literal["accepted", "declined"]


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    recommendation_id: str
    student_id: str
    choice: Literal["accepted", "declined"]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(
            timezone.utc
        )


class StrategyMetrics(BaseModel):
    strategy: Literal["baseline", "budgeted"]
    recommendation_count: int
    feedback_count: int
    accepted_count: int
    acceptance_rate: float | None
    estimated_path_count: int
    average_estimated_minutes: float | None
    goal_in_plan_count: int


class RecommendationMetrics(BaseModel):
    scope: Literal["student", "course"]
    strategies: list[StrategyMetrics]
    explanation: str
