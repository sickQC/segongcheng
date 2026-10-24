from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")
    database_url: str = f"sqlite:///{(ROOT / 'backend' / 'learning.db').as_posix()}"
    video_upload_dir: Path = ROOT / "data" / "uploads" / "videos"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-flash"
    llm_timeout_seconds: float = Field(default=30, ge=1, le=120)
    # Diagnosis and 5E can use an inference channel separate from course RAG.
    c_llm_backend: Literal["api", "codex"] = "api"
    c_llm_model: str = ""
    c_codex_timeout_seconds: float = Field(default=120, ge=10, le=300)
    c_codex_binary: str = ""
    enable_demo: bool = True

    enable_dev_routes: bool = False
    session_hours: int = Field(default=12, ge=1, le=168)
    cookie_secure: bool = False
    allowed_origins: list[str] = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    seed_password: SecretStr = SecretStr("")
    mastery_threshold: float = Field(default=0.7, gt=0, le=1)
