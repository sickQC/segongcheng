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
    knowledge_point_id: str = Field(min_length=1, max_length=100)
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


class TutorAskRequest(BaseModel):
    """M7 AI 助教的提问请求。

    `mode` 与诊断接口保持同一语义：live 走真实大模型，demo 使用检索证据的演示回答。
    提问者身份由服务端固定（Sprint 0 无登录鉴权），不接受客户端传入，避免越权写入他人事件。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["live", "demo"] = "live"
    top_n: int | None = Field(default=None, ge=1, le=20, description="进入上下文的片段数")

