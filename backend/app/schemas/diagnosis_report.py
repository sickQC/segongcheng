from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProblemType = Literal[
    "concept_confusion",
    "prerequisite_gap",
    "repeated_error",
    "low_engagement",
    "practice_only",
    "no_obvious_issue",
    "insufficient_evidence",
]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_point_ids: list[Annotated[str, Field(min_length=1, max_length=36)]] = Field(
        min_length=1, max_length=20
    )
    days: int = Field(default=30, ge=1, le=90)
    request_id: UUID = Field(default_factory=uuid4)

    @model_validator(mode="after")
    def unique_points(self):
        if len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError("知识点不能重复")
        return self


class PointDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    knowledge_point_id: str
    status: Literal["supported", "insufficient"]
    mastery: float | None = Field(ge=0, le=1)
    confidence: float | None = Field(ge=0, le=1)
    problem_type: ProblemType
    explanation: str = Field(min_length=1, max_length=2000)
    recommendation: str = Field(min_length=1, max_length=2000)
    followup_question: str = Field(min_length=1, max_length=1000)
    evidence_event_ids: list[str] = Field(max_length=30)
    citations: list[dict] = Field(max_length=0)

    @model_validator(mode="after")
    def enough_evidence(self):
        if self.status == "insufficient":
            if self.mastery is not None or self.problem_type != "insufficient_evidence":
                raise ValueError("证据不足时掌握度为空、问题类型为证据不足")
        elif (
            self.mastery is None and self.problem_type not in ("low_engagement", "practice_only")
        ) or self.problem_type == "insufficient_evidence":
            raise ValueError("有效诊断需要掌握度和明确问题类型")
        if len(set(self.evidence_event_ids)) != len(self.evidence_event_ids):
            raise ValueError("证据编号不能重复")
        return self


class ReportFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[PointDiagnosis] = Field(min_length=1, max_length=20)


class ReportOut(BaseModel):
    id: str
    course_id: str
    student_id: str
    status: str
    snapshot: dict
    output: dict | None
    trace_id: str
    error_code: str | None
    error_message: str | None
    created_at: datetime
