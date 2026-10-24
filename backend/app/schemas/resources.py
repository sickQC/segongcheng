from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.foundation import PatchInput


class ResourcePatch(PatchInput):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    # Empty chapter_id clears an optional chapter; IDs are validated against this course.
    chapter_id: str | None = Field(default=None, max_length=36)
    knowledge_point_ids: list[str] | None = Field(default=None, max_length=100)


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    filename: str
    file_type: str
    size_bytes: int
    status: str
    error: str | None
    created_at: datetime


class ParseJob(BaseModel):
    resource_id: str
    version: int
    status: str
