from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Stage = Literal["engage", "explore", "explain", "elaborate", "evaluate"]


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    course_id: str = Field(min_length=1, max_length=36)
    knowledge_point_id: str = Field(min_length=1, max_length=36)
    request_id: UUID = Field(default_factory=uuid4)


class LearningAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    answer: str = Field(min_length=1, max_length=4000)
    request_id: UUID = Field(default_factory=uuid4)
    evaluation_choice: str | None = Field(default=None, max_length=20)


class LearningFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["supported", "insufficient"]
    quality: float = Field(ge=0, le=1)
    next_stage: Stage
    transition_reason: str = Field(min_length=1, max_length=1000)
    reply: str = Field(min_length=1, max_length=2000)
    evidence_event_ids: list[str] = Field(min_length=1, max_length=1)
    citations: list[dict] = Field(default_factory=list, max_length=0)
