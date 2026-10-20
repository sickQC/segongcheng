"""Single-container initialization; never resets a database or existing accounts."""

import os
import sys
from pathlib import Path

from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def require_password(value, name):
    if len(value) < 8 or value.startswith("CHANGE_ME"):
        raise ValueError(f"Set {name} to a new password of at least 8 characters")
    return value


def database_url(environ):
    # URL.create safely encodes @, /, %, : and other password characters.
    password = require_password(environ.get("DEPLOY_DB_PASSWORD", ""), "DEPLOY_DB_PASSWORD")
    return URL.create(
        "postgresql+psycopg",
        username="se_learning",
        password=password,
        host=environ.get("DEPLOY_DB_HOST", "postgres"),
        port=5432,
        database="se_learning",
    ).render_as_string(hide_password=False)


def initialize():
    from alembic.config import Config
    from sqlalchemy import select

    from alembic import command
    from app.core.config import Settings
    from app.core.database import database
    from app.models.diagnosis_report import DiagnosisReport
    from app.services.profile import apply_report
    from app.services.seed import seed_data

    settings = Settings()
    password = require_password(settings.seed_password.get_secret_value(), "DEPLOY_SEED_PASSWORD")
    command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    engine, sessions = database(settings.database_url)
    try:
        with sessions.begin() as db:
            seed_data(db, password)
            for report in db.scalars(
                select(DiagnosisReport)
                .where(DiagnosisReport.status == "supported")
                .order_by(DiagnosisReport.created_at, DiagnosisReport.id)
            ):
                apply_report(db, report)
    finally:
        engine.dispose()
    print("Database initialized; existing accounts and learning data retained.", flush=True)


def main():
    os.environ["DATABASE_URL"] = database_url(os.environ)
    initialize()
    # Replace this process so Docker stop signals reach the one Uvicorn worker.
    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "backend"),
        "--host", "0.0.0.0", "--port", "8000", "--workers", "1",
    ])


if __name__ == "__main__":
    main()
