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
    assert {"learning_events", "diagnoses", "model_traces"} <= set(inspect(engine).get_table_names())
    command.downgrade(config, "base")
    assert "learning_events" not in inspect(engine).get_table_names()
    engine.dispose()


def test_0002_adds_tutor_trace_columns(tmp_path, monkeypatch):
    """0002 必须让 model_traces 能记录没有诊断的助教调用（M7）。"""
    url = f"sqlite:///{(tmp_path / 'tutor.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    columns = {c["name"]: c for c in inspect(engine).get_columns("model_traces")}
    assert {"feature", "event_id", "details"} <= set(columns)
    assert columns["diagnosis_id"]["nullable"] is True
    engine.dispose()


def test_0002_downgrade_removes_tutor_traces(tmp_path, monkeypatch):
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
