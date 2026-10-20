"""Bounded read-only export; JSONL is lossless, CSV is intended for human viewing."""

import csv
import io
import json
from contextlib import closing

from app.core.errors import fail
from app.services.learning_events import iter_real_events, utc

MAX_EVENTS = 5000
MAX_BYTES = 10 * 1024 * 1024
FIELDS = ("event_id", "actor", "verb", "object", "result", "context", "timestamp")


def csv_cell(value):
    value = str(value)
    # Quote fields as CSV and neutralize common spreadsheet formula prefixes.
    if value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def build_export(db, course, student, start, end, format="jsonl", verb=None, point=None):
    if format not in ("csv", "jsonl"):
        fail(422, "EXPORT_FORMAT", "导出格式仅支持csv或jsonl")
    parts, size, count = [], 0, 0

    def append(raw):
        nonlocal size
        size += len(raw)
        if size > MAX_BYTES:
            fail(422, "EXPORT_LIMIT", "导出超过10MiB，请缩小时间或知识点范围；未返回部分文件")
        parts.append(raw)

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    if format == "csv":
        writer.writerow(FIELDS)
        append(b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8"))
    with closing(iter_real_events(db, course, student, start, end, verb, point)) as rows:
        for event in rows:
            count += 1
            if count > MAX_EVENTS:
                fail(422, "EXPORT_LIMIT", "导出超过5000条，请缩小筛选范围；未返回部分文件")
            record = dict(event_id=event.event_id, actor=event.actor, verb=event.verb,
                          object=event.object, result=event.result, context=event.context,
                          timestamp=utc(event.timestamp).isoformat())
            if format == "jsonl":
                append((json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
            else:
                buffer.seek(0)
                buffer.truncate()
                writer.writerow([csv_cell(json.dumps(record[key], ensure_ascii=False, allow_nan=False)
                                          if isinstance(record[key], (dict, list)) else record[key]) for key in FIELDS])
                append(buffer.getvalue().encode("utf-8"))
    return b"".join(parts), count
