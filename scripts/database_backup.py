"""Local SQLite backups and isolated restore drills; never overwrite the active database."""

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def inside(path, parent):
    path, parent = Path(path).resolve(), Path(parent).resolve()
    if not path.is_relative_to(parent) or path == parent:
        raise ValueError("Path must stay inside its designated local directory")
    return path


def local_area(root, name):
    root = Path(root).resolve()
    local = inside(root / ".local", root)
    return inside(local / name, local)


def readonly(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Existing database required")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_database(path):
    with closing(readonly(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("Foreign key check failed")
        tables = sorted(r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        counts = {table: db.execute('SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0]
                  for table in tables}
        revisions = sorted(r[0] for r in db.execute("SELECT version_num FROM alembic_version")) if "alembic_version" in tables else []
        return {"table_counts": counts, "alembic_revisions": revisions}


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def new_directory(root, area):
    parent = local_area(root, area)
    parent.mkdir(parents=True, exist_ok=True)
    target = inside(parent / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex), parent)
    target.mkdir()  # Never reuse or overwrite a previous backup/drill.
    return target


def create_backup(source, root=ROOT):
    source = inside(source, root)
    if not source.is_file():
        raise ValueError("Existing database required")
    target = new_directory(root, "backups")
    database = target / "database.db"
    started = time.monotonic()

    def progress(status, remaining, total):
        if time.monotonic() - started > 30:
            raise TimeoutError("Backup timed out; incomplete directory has no valid manifest")

    # SQLite online backup includes committed WAL data; raw file copying could omit it.
    with closing(readonly(source)) as original, database.open("xb"):
        with closing(sqlite3.connect(database)) as destination:
            original.backup(destination, pages=256, progress=progress, sleep=.05)
    summary = inspect_database(database)
    manifest = {"version": "sqlite-backup-v1", "created_at": datetime.now(UTC).isoformat(),
                "sha256": digest(database), "bytes": database.stat().st_size, **summary,
                "sensitive": True, "contains_env_file": False}
    write_new(target / "manifest.json", manifest)
    verify_backup(target, root)
    return target


def verify_backup(directory, root=ROOT):
    directory = inside(directory, local_area(root, "backups"))
    database = inside(directory / "database.db", directory)
    manifest_path = inside(directory / "manifest.json", directory)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != "sqlite-backup-v1":
        raise ValueError("Unsupported backup manifest")
    if database.stat().st_size != manifest.get("bytes") or digest(database) != manifest.get("sha256"):
        raise ValueError("Backup checksum or size mismatch")
    summary = inspect_database(database)
    if any(summary[key] != manifest.get(key) for key in summary):
        raise ValueError("Backup table counts or migration revision mismatch")
    return manifest


def restore_drill(directory, root=ROOT):
    manifest = verify_backup(directory, root)
    directory = inside(directory, local_area(root, "backups"))
    target = new_directory(root, "restore-drills")
    restored = target / "database.db"
    with (directory / "database.db").open("rb") as source, restored.open("xb") as destination:
        shutil.copyfileobj(source, destination, length=1024 * 1024)
    if digest(restored) != manifest["sha256"]:
        raise ValueError("Restored database checksum mismatch")
    summary = inspect_database(restored)
    if any(summary[key] != manifest[key] for key in summary):
        raise ValueError("Restored database content summary mismatch")
    write_new(target / "drill.json", {"version": "sqlite-restore-drill-v1", "status": "passed",
              "checked_at": datetime.now(UTC).isoformat(), "backup_sha256": manifest["sha256"],
              "tables": len(summary["table_counts"]), "active_database_replaced": False})
    return target


def configured_source(root=ROOT):
    sys.path.insert(0, str(root / "backend"))
    from sqlalchemy.engine import make_url

    from app.core.config import Settings

    url = make_url(Settings().database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("This tool supports an existing local SQLite database only")
    return inside(Path(url.database), root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup")
    for name in ("verify", "restore-drill"):
        sub.add_parser(name).add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            target = create_backup(configured_source())
        elif args.command == "verify":
            verify_backup(args.backup_dir)
            target = args.backup_dir.resolve()
        else:
            target = restore_drill(args.backup_dir)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, TimeoutError):
        # Do not print DB URLs, contents, raw SQLite errors or credentials.
        raise SystemExit("Operation failed. Check local paths, backup integrity and available disk space; active database was not replaced.") from None
    print(json.dumps({"status": "passed", "operation": args.command,
                      "directory": target.relative_to(ROOT).as_posix(), "active_database_replaced": False}))


if __name__ == "__main__":
    main()
