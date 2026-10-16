from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import auth, courses, knowledge, practice, workspace
from app.api.routes.dev import create_dev_router
from app.core.config import ROOT, Settings
from app.core.database import database
from app.core.errors import install_errors
from app.models import Diagnosis, LearningEvent, ModelTrace, User
from app.schemas.foundation import ErrorResponse


def create_app(settings=None):
    settings = settings or Settings()
    engine, sessions = database(settings.database_url)

    @asynccontextmanager
    async def lifespan(_):
        # Single-worker development tasks cannot survive a process restart.
        if inspect(engine).has_table("diagnoses"):
            with sessions.begin() as session:
                session.execute(
                    update(Diagnosis)
                    .where(Diagnosis.status == "pending")
                    .values(
                        status="failed",
                        error_code="PROCESS_INTERRUPTED",
                        error_message="上次运行在诊断完成前中断；作答已保存，可以重试。",
                    )
                )
                session.execute(
                    update(ModelTrace)
                    .where(ModelTrace.status == "pending")
                    .values(status="failed", error_code="PROCESS_INTERRUPTED")
                )
        yield
        engine.dispose()

    app = FastAPI(title="知序 · 软件工程学习平台", version="0.2.0", lifespan=lifespan)
    app.state.sessions, app.state.engine, app.state.settings = sessions, engine, settings
    install_errors(app)
    api = APIRouter(
        prefix="/api/v1", responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422)}
    )
    api.include_router(auth.router)
    api.include_router(courses.router)
    api.include_router(knowledge.router)
    api.include_router(practice.router)
    api.include_router(workspace.router)
    app.include_router(api)
    if settings.enable_dev_routes:
        app.include_router(create_dev_router(sessions, settings))
        # Fixed simulated actor and shared local KB: not a course-scoped production API.
        from app.api.tutor import router as tutor_router

        app.include_router(tutor_router)

    @app.get("/health", tags=["System"])
    def health():
        try:
            with sessions() as session:
                session.execute(text("SELECT 1"))
                session.execute(select(LearningEvent.event_id).limit(1))
                session.execute(select(User.id).limit(1))
        except SQLAlchemyError:
            raise HTTPException(503, "数据库不可用或尚未迁移") from None
        return {"status": "ok", "database": engine.dialect.name, "sprint": 1}

    @app.get("/api/config", tags=["System"])
    def public_config():
        return {"dev_routes_enabled": settings.enable_dev_routes}

    dist = ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
