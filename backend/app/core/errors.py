from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException


def fail(status: int, code: str, message: str):
    raise HTTPException(status, detail={"code": code, "message": message})


def install_errors(app):
    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/v1"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def error(request, status, detail):
        return JSONResponse(
            status_code=status,
            content={"detail": detail, "request_id": getattr(request.state, "request_id", str(uuid4()))},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc):
        if not request.url.path.startswith("/api/v1"):
            return await http_exception_handler(request, exc)
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}
        )
        return error(request, exc.status_code, detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        if not request.url.path.startswith("/api/v1"):
            return await request_validation_exception_handler(request, exc)
        # Never echo request input: it can contain a password.
        fields = [{"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return error(
            request, 422, {"code": "VALIDATION_ERROR", "message": "请求参数不正确", "fields": fields}
        )

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc):
        return error(request, 409, {"code": "DATA_CONFLICT", "message": "编号或成员已存在，请刷新后重试"})
