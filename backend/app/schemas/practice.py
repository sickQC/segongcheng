"""Member C API schemas; existing member A contracts remain compatible."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import DiagnosisOutput


class PracticeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    knowledge_point_id: str = Field(min_length=1, max_length=36)
    question_text: str = Field(min_length=1, max_length=4000)


class PracticeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    answer: str = Field(min_length=1, max_length=4000)
    request_id: UUID = Field(default_factory=uuid4)


class PracticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    course_id: str
    chapter_id: str
    knowledge_point_id: str
    question_text: str
    created_at: datetime


class SubmissionOut(BaseModel):
    id: str
    exercise_id: str
    course_id: str
    student_id: str
    original_answer: str
    event_id: str
    diagnosis_id: str
    created_at: datetime
    parent_submission_id: str | None
    status: Literal["pending", "supported", "insufficient", "failed"]
    diagnosis: DiagnosisOutput | None
    error_message: str | None
    needs_attention: bool


class StudentProgress(BaseModel):
    student_id: str
    username: str
    display_name: str
    latest_submission: SubmissionOut | None
    needs_attention: bool


class PracticeProgress(BaseModel):
    exercise_id: str
    student_count: int
    submitted_count: int
    attention_count: int
    students: list[StudentProgress]
