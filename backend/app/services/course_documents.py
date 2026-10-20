"""Read original Markdown for indexed, course-authorized built-in lectures."""

import re

from app.core.errors import fail
from app.rag.config import RagConfig
from app.services.tutor import load_index


def markdown_document(settings, resource_id: str) -> dict:
    titles = load_index(settings).doc_titles()
    doc_id = resource_id.removeprefix("kb:")
    if not resource_id.startswith("kb:") or doc_id not in titles:
        fail(404, "RESOURCE_NOT_FOUND", "课程讲义不存在")

    # Resource identifiers are never used as user-supplied filesystem paths.
    docs_dir = (RagConfig.from_settings(settings).kb_dir / "docs").resolve()
    for candidate in sorted(docs_dir.glob("*.md")):
        match = re.match(r"^([A-Za-z]+-\d+)", candidate.stem)
        candidate_id = match.group(1) if match else candidate.stem
        if candidate_id != doc_id:
            continue
        resolved = candidate.resolve()
        if not resolved.is_relative_to(docs_dir):
            break
        try:
            markdown = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            fail(404, "RESOURCE_UNAVAILABLE", "讲义原文暂时无法读取，请稍后重试")
        return {"resource_id": resource_id, "title": titles[doc_id], "markdown": markdown}
    fail(404, "RESOURCE_UNAVAILABLE", "讲义原文暂时无法读取，请稍后重试")
