"""Import the six repository lectures into an existing course without replacing edits."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings  # noqa: E402
from app.core.database import database  # noqa: E402
from app.models import Course  # noqa: E402
from app.services.resources import import_builtins  # noqa: E402
from app.services.seed import seed_id  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", default=seed_id("course"))
    args = parser.parse_args()
    engine, sessions = database(Settings().database_url)
    try:
        with sessions.begin() as db:
            if db.get(Course, args.course_id) is None:
                raise SystemExit("Course not found; initialize the course first.")
            count = import_builtins(db, args.course_id)
        print(f"Imported {count} documents; existing content and deletions retained.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
