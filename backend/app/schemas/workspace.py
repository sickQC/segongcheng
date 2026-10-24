"""Course workspace contracts; unimplemented routes still return HTTP 501."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profile import LearningProfileOut


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResourceOut(BaseModel):
    id: str
    title: str
    type: Literal["video", "doc"]
    url: str | None
    description: str
    knowledge_point_ids: list[str]
    format: Literal["markdown"] | None = None
    chapter_id: str | None = None
    origin: Literal["builtin", "upload"] | None = None
    uploaded_by: str | None = None
    status: str = "ready"
    error: str | None = None
    version: int = 1
    filename: str | None = None
    file_type: str | None = None
    size_bytes: int = 0
    download_url: str | None = None
    created_at: datetime | None = None
    completed: bool = False


class ResourceContentOut(BaseModel):
    resource_id: str
    title: str
    markdown: str


class CitationOut(BaseModel):
    resource_id: str
    title: str
    page: int | None = Field(ge=1)
    seconds: float | None = Field(ge=0)
    section: str | None = None


class PersonalizationOut(BaseModel):
    source: Literal["synthetic"]
    matched_knowledge_points: list[str]
    similarity: float = Field(ge=0, le=1)


class ChatIn(Input):
    resource_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    mode: Literal["rag", "5e"]
    history: Literal["real", "synthetic"] = "real"


class FollowupIn(Input):
    message: str = Field(min_length=1, max_length=2000)


class ChatOut(BaseModel):
    message: str
    citations: list[CitationOut]
    phase: str | None
    personalization: PersonalizationOut | None = None


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
    attempt_id: str | None = None
    diagnosis_ids: list[str] = Field(default_factory=list)
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


class WrongQuestionOut(BaseModel):
    stem: str
    answer: str
    knowledge_point: str


class WeakKnowledgePointOut(BaseModel):
    name: str
    learning_gap: str
    practice: str


class ChapterHistoryOut(BaseModel):
    title: str
    accuracy: float = Field(ge=0, le=100)
    high_error: bool
    wrong_questions: list[WrongQuestionOut]
    weak_knowledge_points: list[WeakKnowledgePointOut]


class ReportOut(BaseModel):
    learning_profile: LearningProfileOut | None = None
    history_source: Literal["synthetic", "real"] | None = None
    chapter_history: list[ChapterHistoryOut] = []
    diagnosis: list[DiagnosisItem]
    profile: list[ProfileItem]
    recommendations: list[RecommendationItem]
    records: list[RecordItem]
    mistakes: list[MistakeItem]
    timeline: list[TimelineItem]


class PointStatOut(BaseModel):
    knowledge_point_id: str
    name: str
    chapter: str
    correct_count: int
    question_count: int
    accuracy_percent: float | None


class ChapterStatOut(BaseModel):
    chapter_id: str
    name: str
    correct_count: int
    question_count: int
    accuracy_percent: float | None


class TeacherStudentSummary(BaseModel):
    id: str
    name: str
    username: str
    quiz_count: int
    practice_count: int
    correct_count: int
    question_count: int
    accuracy_percent: float | None
    attention_reasons: list[str]
    last_activity_at: datetime | None
    simulated_record_count: int


class TeacherActivityOut(BaseModel):
    kind: Literal["quiz", "practice"]
    title: str
    at: datetime
    simulated: bool
    score_percent: float | None = None
    answer: str | None = None
    diagnosis: str | None = None
    recommendation: str | None = None
    evidence_id: str | None = None


class TeacherMistakeOut(BaseModel):
    question: str
    original_answer: str
    explanation: str
    at: datetime
    simulated: bool
    evidence_id: str | None


class TeacherStudentOut(BaseModel):
    student_id: str
    name: str
    username: str
    days: int
    correct_count: int
    question_count: int
    accuracy_percent: float | None
    chapters: list[ChapterStatOut]
    points: list[PointStatOut]
    activities: list[TeacherActivityOut]
    mistakes: list[TeacherMistakeOut]
    attention_reasons: list[str]
    simulated_record_count: int
    latest_report: dict | None


class DashboardOut(BaseModel):
    days: int
    include_demo: bool
    student_count: int
    active_count: int
    quiz_count: int
    practice_count: int
    average_quiz_percent: float | None
    simulated_record_count: int
    chapters: list[ChapterStatOut]
    points: list[PointStatOut]
    students: list[TeacherStudentSummary]


class JobOut(BaseModel):
    job_id: str
