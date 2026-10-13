from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.api.tutor import router as tutor_router
from app.core.config import ROOT, Settings
from app.core.database import database
from app.models import Diagnosis, LearningEvent, ModelTrace
from app.schemas import Submission
from app.services.diagnosis import QUESTION, add_trace, run_diagnosis, traces_for


def row_dict(row):
    values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    for key, value in values.items():
        if hasattr(value, "tzinfo") and value.tzinfo is None:
            values[key] = value.replace(tzinfo=timezone.utc)
    return values


def create_app(settings=None):
    settings = settings or Settings()
    engine, sessions = database(settings.database_url)

    @asynccontextmanager
    async def lifespan(_):
        # 单进程开发版：重启后把中断任务标为失败，允许用户明确重试。
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

    app = FastAPI(title="软件工程学习辅助系统 · Sprint 0", version="0.1.0", lifespan=lifespan)
    app.state.sessions, app.state.engine = sessions, engine
    app.state.settings = settings
    # M7 AI 助教路由；M8 诊断路由保留在本文件，两者共用 model_traces。
    app.include_router(tutor_router)

    @app.get("/health")
    def health():
        try:
            with sessions() as session:
                session.execute(text("SELECT 1"))
                session.execute(select(LearningEvent.event_id).limit(1))
        except SQLAlchemyError:
            raise HTTPException(503, "数据库不可用或尚未迁移") from None
        return {"status": "ok", "database": engine.dialect.name, "sprint": 0}

    @app.get("/api/dev/question")
    def question():
        return {
            **QUESTION,
            "demo_enabled": settings.enable_demo,
            "model_configured": bool(settings.llm_api_key.get_secret_value() and settings.llm_model),
        }

    @app.post("/api/dev/submissions", status_code=202)
    def submit(body: Submission, tasks: BackgroundTasks):
        if body.mode == "demo":
            if not settings.enable_demo:
                raise HTTPException(403, "模拟演示已禁用")
            if body.answer != QUESTION["sample_answer"]:
                raise HTTPException(422, "固定模拟结果仅适用于预置示例答案，请使用示例或切换真实调用")
        with sessions.begin() as session:
            event = LearningEvent(
                actor="sim-student-001",
                verb="answered",
                object={"type": "question", "id": QUESTION["id"], "kp": ["KP-VAL-01"]},
                result={"answer": body.answer, "duration_seconds": body.duration_seconds, "correct": None},
                context={"course": "SE", "source": body.mode, "synthetic": True},
            )
            session.add(event)
            session.flush()
            diagnosis = Diagnosis(event_id=event.event_id, mode=body.mode)
            session.add(diagnosis)
            session.flush()
            trace = add_trace(session, settings, diagnosis, event)
            result = {
                "event_id": event.event_id,
                "diagnosis_id": diagnosis.id,
                "trace_id": trace.trace_id,
                "status": "pending",
                "mode": body.mode,
            }
        tasks.add_task(run_diagnosis, sessions, settings, diagnosis.id, trace.trace_id)
        return result

    @app.get("/api/diagnoses")
    def list_diagnoses():
        with sessions() as session:
            return [
                row_dict(row)
                for row in session.scalars(select(Diagnosis).order_by(Diagnosis.created_at.desc()).limit(50))
            ]

    @app.get("/api/diagnoses/{diagnosis_id}")
    def get_diagnosis(diagnosis_id: str):
        with sessions() as session:
            diagnosis = session.get(Diagnosis, diagnosis_id)
            if diagnosis is None:
                raise HTTPException(404, "诊断记录不存在")
            return {
                **row_dict(diagnosis),
                "event": row_dict(session.get(LearningEvent, diagnosis.event_id)),
                "traces": [row_dict(t) for t in traces_for(session, diagnosis_id)],
            }

    @app.post("/api/diagnoses/{diagnosis_id}/retry", status_code=202)
    def retry(diagnosis_id: str, tasks: BackgroundTasks):
        with sessions.begin() as session:
            claimed = session.execute(
                update(Diagnosis)
                .where(Diagnosis.id == diagnosis_id, Diagnosis.status == "failed")
                .values(status="pending", error_code=None, error_message=None)
            )
            if not claimed.rowcount:
                if session.get(Diagnosis, diagnosis_id) is None:
                    raise HTTPException(404, "诊断记录不存在")
                raise HTTPException(409, "仅失败的诊断可以重试")
            diagnosis = session.get(Diagnosis, diagnosis_id)
            event = session.get(LearningEvent, diagnosis.event_id)
            trace = add_trace(session, settings, diagnosis, event)
            result = {
                "diagnosis_id": diagnosis.id,
                "event_id": event.event_id,
                "trace_id": trace.trace_id,
                "status": "pending",
                "mode": diagnosis.mode,
            }
        tasks.add_task(run_diagnosis, sessions, settings, diagnosis.id, trace.trace_id)
        return result

    dist: Path = ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
