import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select

from app.api.deps import Auth, CurrentUser, Db, trusted_origin
from app.core.errors import fail
from app.core.security import DUMMY_HASH, hash_password, hasher, token_hash, verify_password
from app.models import User, UserSession
from app.models.legacy import now
from app.schemas.foundation import AuthOut, Login
from app.services.courses import user_courses

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=AuthOut, dependencies=[Depends(trusted_origin)])
def login(body: Login, request: Request, response: Response, db: Db):
    user = db.scalar(select(User).where(User.username == body.username.strip()))
    valid = verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if not valid or user is None:
        fail(401, "INVALID_CREDENTIALS", "用户名或密码不正确")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    # Rotate existing browser session on account switch; remove expired sessions.
    previous = token_hash(request.cookies.get("se_session", ""))
    db.execute(delete(UserSession).where(UserSession.token_hash == previous))
    db.execute(delete(UserSession).where(UserSession.expires_at <= now()))
    raw = secrets.token_urlsafe(32)
    auth = UserSession(
        user_id=user.id,
        token_hash=token_hash(raw),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=now() + timedelta(hours=request.app.state.settings.session_hours),
    )
    db.add(auth)
    db.flush()
    response.set_cookie(
        "se_session",
        raw,
        httponly=True,
        samesite="lax",
        path="/",
        secure=request.app.state.settings.cookie_secure,
        max_age=request.app.state.settings.session_hours * 3600,
    )
    return AuthOut(
        user=user, csrf_token=auth.csrf_token, expires_at=auth.expires_at, courses=user_courses(db, user.id)
    )


@router.get("/me", response_model=AuthOut)
def me(user: CurrentUser, auth: Auth, db: Db):
    return AuthOut(
        user=user, csrf_token=auth.csrf_token, expires_at=auth.expires_at, courses=user_courses(db, user.id)
    )


@router.post("/logout", status_code=204)
def logout(auth: Auth, db: Db, response: Response):
    db.delete(auth)
    response.delete_cookie("se_session", path="/")
