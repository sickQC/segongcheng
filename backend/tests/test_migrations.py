from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

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
