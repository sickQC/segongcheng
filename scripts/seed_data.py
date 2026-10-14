"""Run with the project virtual environment; never overwrite existing passwords."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import Settings
from app.core.database import database
from app.services.seed import seed_data


def main():
    settings = Settings()
    engine, sessions = database(settings.database_url)
    try:
        with sessions.begin() as db:
            result = seed_data(db, settings.seed_password.get_secret_value())
        print("Seed ready:", ", ".join(result["accounts"]))
        print("Existing passwords and edited content were not changed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
