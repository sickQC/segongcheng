"""Backup/restore safety is checked on disposable files, never the developer database."""

import json
import sqlite3
from contextlib import closing

import pytest
from scripts.database_backup import create_backup, digest, inspect_database, restore_drill, verify_backup


def source(root):
    path = root / "active.db"
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE alembic_version(version_num TEXT);
            INSERT INTO alembic_version VALUES ('0011');
            CREATE TABLE parent(id INTEGER PRIMARY KEY, value TEXT);
            CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));
            INSERT INTO parent VALUES (1, 'private student answer');
            INSERT INTO child VALUES (1, 1);
        """)
    return path


def test_backup_and_restore_preserve_active_and_snapshot(tmp_path):
    original = source(tmp_path)
    before = digest(original)
    backup = create_backup(original, tmp_path)
    manifest = verify_backup(backup, tmp_path)
    assert manifest["alembic_revisions"] == ["0011"]
    assert manifest["table_counts"]["child"] == 1
    assert "private student answer" not in (backup / "manifest.json").read_text()
    drill = restore_drill(backup, tmp_path)
    assert digest(drill / "database.db") == manifest["sha256"]
    assert digest(original) == before
    assert json.loads((drill / "drill.json").read_text())["active_database_replaced"] is False
    with closing(sqlite3.connect(original)) as db:
        db.execute("INSERT INTO parent VALUES (2, 'new data after backup')")
        db.commit()
    assert inspect_database(original)["table_counts"]["parent"] == 2
    assert inspect_database(drill / "database.db")["table_counts"]["parent"] == 1


def test_online_backup_includes_committed_wal_without_committing_pending_writes(tmp_path):
    original = source(tmp_path)
    with closing(sqlite3.connect(original)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("INSERT INTO parent VALUES (2, 'committed WAL')")
        db.commit()
        db.execute("INSERT INTO parent VALUES (3, 'uncommitted')")
        backup = create_backup(original, tmp_path)
        assert verify_backup(backup, tmp_path)["table_counts"]["parent"] == 2
        db.rollback()


def test_repeated_operations_never_overwrite(tmp_path):
    original = source(tmp_path)
    first, second = create_backup(original, tmp_path), create_backup(original, tmp_path)
    assert first != second
    assert restore_drill(first, tmp_path) != restore_drill(first, tmp_path)
    assert first.is_dir() and second.is_dir()


@pytest.mark.parametrize("damage", ["database", "counts", "revision", "version", "missing_manifest"])
def test_damaged_backup_rejected_before_restore_directory(tmp_path, damage):
    backup = create_backup(source(tmp_path), tmp_path)
    manifest_path = backup / "manifest.json"
    if damage == "database":
        with (backup / "database.db").open("ab") as stream:
            stream.write(b"corruption")
    elif damage == "missing_manifest":
        manifest_path.unlink()
    else:
        manifest = json.loads(manifest_path.read_text())
        if damage == "counts":
            manifest["table_counts"]["parent"] = 999
        elif damage == "revision":
            manifest["alembic_revisions"] = ["wrong"]
        else:
            manifest["version"] = "unsupported"
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        restore_drill(backup, tmp_path)
    assert not (tmp_path / ".local/restore-drills").exists()


def test_foreign_key_corruption_does_not_get_valid_manifest(tmp_path):
    original = source(tmp_path)
    with closing(sqlite3.connect(original)) as db:
        db.execute("INSERT INTO child VALUES (2, 999)")
        db.commit()
    with pytest.raises(ValueError, match="Foreign key"):
        create_backup(original, tmp_path)
    assert not list((tmp_path / ".local/backups").glob("*/manifest.json"))


def test_missing_source_is_not_created_and_external_paths_rejected(tmp_path):
    with pytest.raises(ValueError):
        create_backup(tmp_path / "missing.db", tmp_path)
    assert not (tmp_path / "missing.db").exists()
    with pytest.raises(ValueError):
        create_backup(tmp_path.parent / "external.db", tmp_path)
    with pytest.raises(ValueError):
        verify_backup(tmp_path / "outside", tmp_path)


def test_redirected_local_directory_is_rejected(tmp_path):
    from unittest.mock import patch

    original = source(tmp_path)
    real_resolve = type(tmp_path).resolve

    def redirect(path, *args, **kwargs):
        return tmp_path.parent / "outside" if path == tmp_path / ".local" else real_resolve(path, *args, **kwargs)

    with patch.object(type(tmp_path), "resolve", redirect), pytest.raises(ValueError):
        create_backup(original, tmp_path)
