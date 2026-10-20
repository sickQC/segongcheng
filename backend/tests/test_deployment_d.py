"""Deployment initialization must preserve existing credentials and course edits."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app.core.database import database
from app.models import Course, User

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("deploy_bootstrap", ROOT / "deploy/bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def test_container_database_password_is_encoded():
    password = "test-only:@/percent%$ ?#"
    url = make_url(bootstrap.database_url({"DEPLOY_DB_PASSWORD": password}))
    assert url.password == password
    assert url.host == "postgres" and url.database == "se_learning"


@pytest.mark.parametrize("password", ["", "short", "CHANGE_ME_DATABASE_PASSWORD"])
def test_deploy_rejects_missing_or_template_password(password):
    with pytest.raises(ValueError, match="DEPLOY_DB_PASSWORD"):
        bootstrap.database_url({"DEPLOY_DB_PASSWORD": password})


def test_repeated_initialization_preserves_existing_data(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'deployment.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SEED_PASSWORD", "deployment-test-only-password")
    bootstrap.initialize()
    engine, sessions = database(url)
    try:
        with sessions.begin() as db:
            original_hash = db.scalar(select(User).where(User.username == "teacher")).password_hash
            course = db.scalar(select(Course))
            course.title = "Teacher-edited course retained"
            original_course = course.id
        monkeypatch.setenv("SEED_PASSWORD", "changed-test-only-password")
        bootstrap.initialize()
        with sessions() as db:
            assert db.scalar(select(User).where(User.username == "teacher")).password_hash == original_hash
            assert db.get(Course, original_course).title == "Teacher-edited course retained"
            assert len(list(db.scalars(select(User)))) == 3
            assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0011"
    finally:
        engine.dispose()
