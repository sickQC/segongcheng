"""UI handoff contracts. No persistence or model execution is implemented here."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResourceOut(BaseModel):
    id: str
    title: str
    type: Literal["video", "doc"]
    url: str | None
    description: str
    knowledge_point_ids: list[str]


class CitationOut(BaseModel):
    resource_id: str
    title: str
    page: int | None = Field(ge=1)
    seconds: float | None = Field(ge=0)


class ChatIn(Input):
    resource_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    mode: Literal["rag", "5e"]


class FollowupIn(Input):
    message: str = Field(min_length=1, max_length=2000)


class ChatOut(BaseModel):
    message: str
    citations: list[CitationOut]
    phase: str | None


class QuizOut(BaseModel):
    id: str
    title: str
    duration_minutes: int = Field(ge=1)
    attempts_remaining: int = Field(ge=0)


class QuestionOut(BaseModel):
    id: str
    type: Literal["single", "multiple", "boolean", "fill"]
    stem: str
    options: list[str]
    points: float = Field(ge=0)


class StartAttemptIn(Input):
    quiz_id: str = Field(min_length=1, max_length=100)


class AttemptOut(BaseModel):
    id: str
    quiz_id: str
    expires_at: str
    questions: list[QuestionOut]


class AnswerIn(Input):
    question_id: str = Field(min_length=1, max_length=100)
    value: list[str] = Field(max_length=100)


class SubmitIn(Input):
    answers: list[AnswerIn] = Field(max_length=500)


class AnswerResultOut(BaseModel):
    question_id: str
    correct: bool
    explanation: str


class ResultOut(BaseModel):
    score: float
    total: float
    answers: list[AnswerResultOut]


class DiagnosisItem(BaseModel):
    knowledge_point: str
    mastery: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=100)
    issue: str
    evidence_ids: list[str]


class ProfileItem(BaseModel):
    label: str
    value: float = Field(ge=0, le=100)


class RecommendationItem(BaseModel):
    title: str
    reason: str
    minutes: int = Field(ge=0)
    resource_id: str | None


class RecordItem(BaseModel):
    title: str
    score: float
    at: str


class MistakeItem(BaseModel):
    stem: str
    explanation: str


class TimelineItem(BaseModel):
    at: str
    description: str


class ReportOut(BaseModel):
    diagnosis: list[DiagnosisItem]
    profile: list[ProfileItem]
    recommendations: list[RecommendationItem]
    records: list[RecordItem]
    mistakes: list[MistakeItem]
    timeline: list[TimelineItem]


class StudentMetric(BaseModel):
    id: str
    name: str
    mastery: list[float]
    risk: str


class QuestionMetric(BaseModel):
    stem: str
    correct_rate: float = Field(ge=0, le=100)
    average_seconds: float = Field(ge=0)
    option_counts: dict[str, int]


class ScoreBucket(BaseModel):
    label: str
    count: int = Field(ge=0)


class DashboardOut(BaseModel):
    student_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    completion: float = Field(ge=0, le=100)
    average_score: float
    knowledge_points: list[str]
    students: list[StudentMetric]
    questions: list[QuestionMetric]
    score_distribution: list[ScoreBucket]


class JobOut(BaseModel):
    job_id: str
