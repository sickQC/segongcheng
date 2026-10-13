from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    answer: str = Field(min_length=1, max_length=4000)
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    mode: Literal["live", "demo"] = "live"


class DiagnosisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["supported", "insufficient"]
    knowledge_point_id: Literal["KP-VAL-01"]
    mastery: float | None = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    problem_type: Literal["concept_confusion", "no_obvious_issue", "insufficient_evidence"]
    problem_description: str = Field(min_length=1, max_length=2000)
    evidence_event_ids: list[str] = Field(min_length=1, max_length=1)
    # Sprint 0 没有导入课程资料，禁止生成貌似真实的出处。
    citations: list[dict] = Field(max_length=0)
    recommendation: str = Field(min_length=1, max_length=2000)
    followup_question: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def check_insufficient(self):
        if self.status == "insufficient":
            if self.mastery is not None or self.problem_type != "insufficient_evidence":
                raise ValueError("证据不足时不能给出掌握度或确定的错误类型")
        elif self.mastery is None or self.problem_type == "insufficient_evidence":
            raise ValueError("supported 输出需要掌握度和明确类型")
        return self
