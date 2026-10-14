from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

Title = Annotated[str, Field(min_length=1, max_length=200)]
Name = Annotated[str, Field(min_length=1, max_length=100)]
Bloom = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Login(Input):
    username: Name
    password: str = Field(min_length=1, max_length=256)
    # Password whitespace is significant.
    model_config = ConfigDict(extra="forbid")


class UserOut(Output):
    id: str
    username: str
    display_name: str
    role: Literal["student", "teacher"]


class CourseCreate(Input):
    title: Title
    description: str = Field(default="", max_length=4000)


class CourseOut(Output):
    id: str
    title: str
    description: str
    teacher_id: str


class AuthOut(Output):
    user: UserOut
    csrf_token: str
    expires_at: datetime
    courses: list[CourseOut]


class ChapterCreate(Input):
    title: Title
    sort_order: int = Field(default=0, ge=0, le=10000)


class ChapterOut(Output):
    id: str
    course_id: str
    title: str
    sort_order: int


class KpCreate(Input):
    code: Name
    name: Name
    definition: str = Field(min_length=1, max_length=8000)
    difficulty: int = Field(ge=1, le=5)
    bloom_level: Bloom


class KpOut(Output):
    id: str
    code: str
    chapter_id: str
    name: str
    definition: str
    difficulty: int
    bloom_level: Bloom
    resource_ids: list[str] = Field(default_factory=list)
    question_ids: list[str] = Field(default_factory=list)


class ChapterOutline(ChapterOut):
    knowledge_points: list[KpOut]


class Outline(Output):
    course: CourseOut
    chapters: list[ChapterOutline]


class PatchInput(Input):
    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or any(getattr(self, x) is None for x in self.model_fields_set):
            raise ValueError("请至少提供一个非空修改字段")
        return self


class ChapterPatch(PatchInput):
    title: Title | None = None
    sort_order: Annotated[int, Field(ge=0, le=10000)] | None = None


class KpPatch(PatchInput):
    name: Name | None = None
    definition: Annotated[str, Field(min_length=1, max_length=8000)] | None = None
    difficulty: Annotated[int, Field(ge=1, le=5)] | None = None
    bloom_level: Bloom | None = None


class MemberCreate(Input):
    username: Name


class MemberOut(Output):
    user: UserOut
    role: Literal["student", "teacher"]


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[dict] | None = None


class ErrorResponse(BaseModel):
    detail: ErrorDetail
    request_id: str
