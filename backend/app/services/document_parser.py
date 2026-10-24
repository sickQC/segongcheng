"""Bounded, non-executing text extraction; PDF pages are real, Office sections aren't pages."""

import io
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from app.rag.chunker import chunk_markdown
from app.rag.config import ChunkConfig

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT = 500_000
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}


class ParseError(ValueError):
    pass


def validate_file(filename, data):
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    if not name or len(name) > 255 or any(ord(c) < 32 for c in name):
        raise ParseError("文件名无效或过长")
    kind = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if kind not in MIME_TYPES:
        raise ParseError("支持 PDF、DOCX、PPTX、Markdown 和 TXT；旧版 DOC/PPT 请先另存为 DOCX/PPTX 或 PDF。")
    if not data:
        raise ParseError("文件不能为空")
    if len(data) > MAX_FILE_BYTES:
        raise ParseError("文件大小不能超过 20 MiB")
    if kind == "pdf" and not data.startswith(b"%PDF-"):
        raise ParseError("文件内容与 PDF 类型不符")
    if kind in ("docx", "pptx") and not data.startswith(b"PK"):
        raise ParseError("文件内容与 Office 文档类型不符")
    if kind in ("md", "txt"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            raise ParseError("文本文件请使用 UTF-8 编码") from None
        if "\x00" in text:
            raise ParseError("文件含有二进制数据，不是有效的文本文件")
    return name, kind


def office_parts(data, kind):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        with archive:
            entries = archive.infolist()
            if len(entries) > 3000 or sum(e.file_size for e in entries) > 50 * 1024 * 1024:
                raise ParseError("Office 文档解压后过大，请拆分后上传")
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or any("vbaproject" in n.lower() for n in names):
                raise ParseError("不支持该 Office 文件结构或宏文档")
            if kind == "docx":
                root = ET.fromstring(archive.read("word/document.xml"))
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paragraphs = ["".join(t.text or "" for t in p.findall(".//w:t", ns)).strip()
                              for p in root.findall(".//w:p", ns)]
                # Paragraph position is a section anchor, never a fabricated Word page number.
                return [(None, f"段落 {n}", text) for n, text in enumerate(paragraphs, 1) if text]
            slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                            key=lambda n: int(re.search(r"slide(\d+)", n)[1]))
            ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            return [(None, f"幻灯片 {i}", "\n".join(t.text or "" for t in ET.fromstring(archive.read(name)).findall(".//a:t", ns)))
                    for i, name in enumerate(slides, 1)]
    except ParseError:
        raise
    except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError, OSError):
        raise ParseError("Office 文档损坏或格式不符，请重新导出后上传") from None


def extract_document(data, kind):
    """Return readable Markdown plus (page, section, chunk text) tuples."""
    if kind in ("md", "txt"):
        text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if kind == "txt":
            # Plain text must not become executable/raw HTML when rendered.
            import html
            text = html.escape(text)
        if len(text) > MAX_TEXT:
            raise ParseError("文档文字过多，请拆分后上传")
        chunks, _ = chunk_markdown(doc_id="document", doc_title="正文", markdown=text, kps=[], cfg=ChunkConfig())
        parts = [(None, " > ".join(c.section_path) if c.section_path else "正文", c.text) for c in chunks]
        markdown = text
    else:
        if kind == "pdf":
            try:
                reader = PdfReader(io.BytesIO(data), strict=True)
                if reader.is_encrypted:
                    raise ParseError("暂不支持加密 PDF，请解除密码后重新上传")
                if len(reader.pages) > 300:
                    raise ParseError("PDF 超过 300 页，请拆分后上传")
                parts = []
                for n, page in enumerate(reader.pages, 1):
                    contents = page.get_contents()
                    if contents is not None and len(contents.get_data()) > 8 * 1024 * 1024:
                        raise ParseError("PDF 单页内容过大，请简化后上传")
                    parts.append((n, f"第 {n} 页", page.extract_text() or ""))
            except ParseError:
                raise
            except Exception:
                raise ParseError("PDF 解析失败，请检查文件是否损坏或重新导出") from None
        else:
            parts = office_parts(data, kind)
        import html
        parts = [(page, section, html.escape(text.replace("\x00", ""))) for page, section, text in parts]
        if sum(len(t) for _, _, t in parts) > MAX_TEXT:
            raise ParseError("文档文字过多，请拆分后上传")
        markdown = "\n\n".join(f"## {section}\n\n{text}" for _, section, text in parts if text.strip())
        # Keep page/slide/paragraph anchors while breaking long sections into bounded chunks.
        parts = [(page, section, text[start:start + 1400]) for page, section, text in parts
                 for start in range(0, len(text), 1200) if text[start:start + 1400].strip()]
    if not parts or not markdown.strip():
        raise ParseError("未提取到可检索文字；扫描 PDF 请先进行 OCR，再重新上传。原文件仍可预览或下载。")
    return markdown, parts
