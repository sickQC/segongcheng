from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuizQuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    knowledge_point_id: str = Field(min_length=1, max_length=36)
    prerequisite_for: str | None = Field(default=None, min_length=1, max_length=36)
    type: Literal["single", "multiple", "boolean", "fill"]
    stem: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=20)
    correct_values: list[str] = Field(min_length=1, max_length=20)
    explanation: str = Field(min_length=1, max_length=2000)
    points: float = Field(default=10, gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_question(self):
        self.options = [value.strip() for value in self.options]
        self.correct_values = [value.strip() for value in self.correct_values]
        if any(not value or len(value) > 2000 for value in self.options + self.correct_values):
            raise ValueError("选项和标准答案必须非空且不超过 2000 字符")
        if len(set(self.options)) != len(self.options) or len(set(self.correct_values)) != len(
            self.correct_values
        ):
            raise ValueError("选项或标准答案不能重复")
        if self.type == "fill":
            if self.options:
                raise ValueError("填空题不使用选项；多个标准答案表示可接受的同义答案")
        else:
            if len(self.options) < 2 or not set(self.correct_values) <= set(self.options):
                raise ValueError("标准答案必须来自至少两个选项")
            if self.type in ("single", "boolean") and len(self.correct_values) != 1:
                raise ValueError("单选和判断题必须只有一个标准答案")
            if self.type == "boolean" and set(self.options) != {"正确", "错误"}:
                raise ValueError("判断题选项为正确和错误")
        return self


class QuizCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(default=20, ge=1, le=180)
    max_attempts: int = Field(default=1, ge=1, le=10)
    questions: list[QuizQuestionCreate] = Field(min_length=1, max_length=100)
