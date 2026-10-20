"""Idempotently apply existing supported diagnoses after upgrading to migration 0008."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select

from app.core.config import Settings
from app.core.database import database
from app.models.diagnosis_report import DiagnosisReport
from app.services.profile import apply_report


def main():
    engine, sessions = database(Settings().database_url)
    try:
        with sessions.begin() as db:
            count = sum(
                apply_report(db, row)
                for row in db.scalars(
                    select(DiagnosisReport)
                    .where(DiagnosisReport.status == "supported")
                    .order_by(DiagnosisReport.created_at, DiagnosisReport.id)
                )
            )
        print(
            f"Mastery projections updated: {count}; existing answers and diagnoses retained."
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
