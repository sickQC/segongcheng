"""Add the boundary-value topic, exercise and prerequisite to an existing seed course."""

import sys
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.core.database import database  # noqa: E402
from app.services.seed import seed_boundary_value  # noqa: E402


def main():
    settings = Settings()
    engine, sessions = database(settings.database_url)
    try:
        inspector = inspect(engine)
        if not {"courses", "knowledge_points", "practice_exercises", "knowledge_edges"} <= set(inspector.get_table_names()):
            raise ValueError("数据库结构尚未升级，请先运行 python -m alembic -c backend/alembic.ini upgrade head")
        if "estimated_minutes" not in {column["name"] for column in inspector.get_columns("knowledge_points")}:
            raise ValueError("数据库结构尚未升级，请先运行 python -m alembic -c backend/alembic.ini upgrade head")
        with sessions.begin() as db:
            result = seed_boundary_value(db)
        print("Boundary-value content ready:", result["knowledge_point_id"])
        print("Existing topic definitions, exercises and learning records were retained.")
    except HTTPException as exc:
        raise SystemExit(exc.detail["message"]) from None
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except SQLAlchemyError:
        raise SystemExit("Database operation failed; transaction rolled back. Check connectivity and migrations.") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
