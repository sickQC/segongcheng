"""Bounded document reads and streamed, private video storage."""

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import uuid4

from app.core.errors import fail
from app.services.document_parser import MAX_FILE_BYTES, ParseError, validate_file

VIDEO_TYPES = {"mp4": "video/mp4", "webm": "video/webm"}
MAX_VIDEO_BYTES = 200 * 1024 * 1024


@dataclass
class PreparedUpload:
    filename: str
    kind: str
    data: bytes
    size: int
    sha256: str
    storage_path: str | None = None

    def cleanup(self, settings):
        if self.storage_path:
            (settings.video_upload_dir / self.storage_path).unlink(missing_ok=True)


async def prepare_upload(file, settings):
    name = PurePosixPath((file.filename or "").replace("\\", "/")).name
    kind = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    try:
        if kind not in VIDEO_TYPES:
            data = await file.read(MAX_FILE_BYTES + 1)
            try:
                name, kind = validate_file(name, data)
            except ParseError as exc:
                fail(413 if len(data) > MAX_FILE_BYTES else 422, "INVALID_FILE", str(exc))
            return PreparedUpload(name, kind, data, len(data), hashlib.sha256(data).hexdigest())
        if not name or len(name) > 255 or any(ord(c) < 32 for c in name):
            fail(422, "INVALID_FILE", "视频文件名无效或过长")
        first = await file.read(64)
        valid = (len(first) >= 12 and first[4:8] == b"ftyp") if kind == "mp4" else (
            first.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in first.lower()
        )
        if not valid:
            fail(422, "INVALID_FILE", "视频内容与格式不符，请上传有效的 MP4 或 WebM 文件")
        settings.video_upload_dir.mkdir(parents=True, exist_ok=True)
        relative = uuid4().hex + "." + kind
        target = settings.video_upload_dir / relative
        total, digest = 0, hashlib.sha256()
        try:
            with target.open("xb") as output:
                data = first
                while data:
                    total += len(data)
                    if total > MAX_VIDEO_BYTES:
                        fail(413, "VIDEO_TOO_LARGE", "视频大小不能超过 200 MiB")
                    output.write(data)
                    digest.update(data)
                    data = await file.read(1024 * 1024)
            return PreparedUpload(name, kind, b"", total, digest.hexdigest(), relative)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    finally:
        await file.close()


def video_path(settings, version):
    if not version.storage_path:
        fail(404, "VIDEO_UNAVAILABLE", "视频文件暂不可用，请教师重新上传")
    root = settings.video_upload_dir.resolve()
    target = (root / version.storage_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        fail(404, "VIDEO_UNAVAILABLE", "视频文件暂不可用，请教师重新上传")
    return target
