from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_migration_upgrade_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert {
        "learning_events", "diagnoses", "model_traces", "practice_exercises", "practice_submissions"
    } <= set(inspect(engine).get_table_names())
    command.downgrade(config, "base")
    assert "learning_events" not in inspect(engine).get_table_names()
    engine.dispose()


def test_0003_adds_tutor_trace_columns(tmp_path, monkeypatch):
    """0003 必须让 model_traces 能记录没有诊断的助教调用（M7）。"""
    url = f"sqlite:///{(tmp_path / 'tutor.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    columns = {c["name"]: c for c in inspect(engine).get_columns("model_traces")}
    assert {"feature", "event_id", "details"} <= set(columns)
    assert columns["diagnosis_id"]["nullable"] is True
    engine.dispose()


def test_0003_downgrade_removes_tutor_traces(tmp_path, monkeypatch):
    """降级到 0001 时，无诊断的助教 trace 必须被清除，否则恢复 NOT NULL 会失败。"""
    url = f"sqlite:///{(tmp_path / 'roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO model_traces (trace_id, source, model, prompt_version, status,"
                " input_summary, feature, diagnosis_id, created_at) VALUES"
                " ('t-1', 'demo', 'm', 'v1', 'demo', '{}', 'tutor.ask', NULL, '2026-01-01 00:00:00')"
            )
        )
    command.downgrade(config, "0001")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM model_traces")).scalar() == 0
    command.upgrade(config, "head")
    assert {"feature", "event_id", "details"} <= {
        c["name"] for c in inspect(engine).get_columns("model_traces")
    }
    engine.dispose()


def test_foundation_0002_upgrades_without_losing_accounts(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'p1-upgrade.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0002")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id,username,display_name,role,password_hash,created_at) "
                "VALUES ('preserved','preserved','Preserved','student','hash','2026-01-01')"
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT username FROM users WHERE id='preserved'")).scalar() == "preserved"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0013"
    assert {"mastery_profiles", "profile_applications"} <= set(inspect(engine).get_table_names())
    assert {"knowledge_edges", "recommendations"} <= set(inspect(engine).get_table_names())
    assert "recommendation_feedback" in inspect(engine).get_table_names()
    assert "profile_snapshots" in inspect(engine).get_table_names()
    assert "estimated_minutes" in {c["name"] for c in inspect(engine).get_columns("knowledge_points")}
    engine.dispose()


def test_historical_rag_revision_is_not_silently_accepted(tmp_path, monkeypatch):
    import pytest

    url = f"sqlite:///{(tmp_path / 'old-rag.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0001")
    # Historical partner database claimed 0002 without the foundation tables.
    command.stamp(config, "0002")
    with pytest.raises(RuntimeError, match="historical RAG-only"):
        command.upgrade(config, "head")


def test_local_practice_0004_is_upgraded_without_losing_answers(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'old-practice.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0003")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE practice_exercises (
            id VARCHAR(36) PRIMARY KEY, course_id VARCHAR(36) NOT NULL,
            chapter_id VARCHAR(36) NOT NULL, knowledge_point_id VARCHAR(36) NOT NULL UNIQUE,
            question_text TEXT NOT NULL, created_by VARCHAR(36) NOT NULL,
            created_at DATETIME NOT NULL)"""))
        conn.execute(text("""CREATE TABLE practice_submissions (
            id VARCHAR(36) PRIMARY KEY, exercise_id VARCHAR(36) NOT NULL,
            course_id VARCHAR(36) NOT NULL, student_id VARCHAR(36) NOT NULL,
            original_answer TEXT NOT NULL, event_id VARCHAR(36) NOT NULL UNIQUE,
            diagnosis_id VARCHAR(36) NOT NULL UNIQUE, created_at DATETIME NOT NULL)"""))
        conn.execute(text("""INSERT INTO practice_exercises VALUES
            ('ex-1','course-1','chapter-1','kp-1','What?','teacher-1','2026-01-01')"""))
        conn.execute(text("""INSERT INTO practice_submissions VALUES
            ('sub-1','ex-1','course-1','student-1','Original answer','event-1','diag-1','2026-01-01')"""))
    command.stamp(config, "0004")
    command.upgrade(config, "head")
    columns = {column["name"]: column for column in inspect(engine).get_columns("practice_submissions")}
    assert columns["request_id"]["nullable"] is False
    assert "parent_submission_id" in columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT original_answer, request_id FROM practice_submissions")).one() == (
            "Original answer", "sub-1"
        )
        assert conn.execute(text("SELECT created_by FROM practice_exercises")).scalar() == "teacher-1"
    assert {column["name"]: column for column in inspect(engine).get_columns("practice_exercises")}["created_by"][
        "nullable"
    ] is True
    engine.dispose()
