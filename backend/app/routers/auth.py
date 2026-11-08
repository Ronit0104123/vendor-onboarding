from datetime import datetime, timedelta, timezone
from app.timeutil import utcnow

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DBSession

from app.audit import audit
from app.config import settings
from app.deps import get_db
from app.models import Session, User
from app.ratelimit import limiter
from app.schemas import LoginIn
from app.security.passwords import verify_password
from app.security.sessions import Auth, clear_cookie, create_session, current_auth, set_cookie

router = APIRouter(prefix="/api/auth", tags=["auth"])
GENERIC = "Email or password is incorrect."


def _now():
    return utcnow()


def me_view(auth: Auth) -> dict:
    u = auth.user
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "csrf_token": auth.session.csrf_token,
            "buyer_name": settings.buyer_name, "four_eyes": settings.four_eyes_overrides}


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, response: Response, body: LoginIn, db: DBSession = Depends(get_db)):
    user = db.scalars(select(User).where(func.lower(User.email) == body.email.lower())).first()
    if user and user.locked_until and (user.locked_until if user.locked_until.tzinfo else
                                       user.locked_until.replace(tzinfo=timezone.utc)) > _now():
        audit(db, f"user:{user.id}", "LOGIN_LOCKED", ip=request.client.host if request.client else None)
        db.commit()
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    if not verify_password(user.password_hash if user else None, body.password):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= settings.login_max_failures:
                user.locked_until = _now() + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_logins = 0
            audit(db, f"user:{user.id}", "LOGIN_FAILED", ip=request.client.host if request.client else None)
        else:
            audit(db, "anonymous", "LOGIN_FAILED_UNKNOWN_EMAIL")
        db.commit()
        raise HTTPException(401, GENERIC)
    user.failed_logins, user.locked_until = 0, None
    raw, s = create_session(db, user)  # always a fresh session id (no fixation)
    audit(db, f"user:{user.id}", "LOGIN", ip=request.client.host if request.client else None)
    db.commit()
    set_cookie(response, raw)
    return me_view(Auth(user, s))


@router.get("/session")
def session(request: Request, db: DBSession = Depends(get_db)):
    """Like /me but answers 200 with user=null when signed out (used on page load)."""
    try:
        return {"user": me_view(current_auth(request, db))}
    except HTTPException:
        return {"user": None}


@router.get("/me")
def me(auth: Auth = Depends(current_auth)):
    return me_view(auth)


@router.post("/logout")
def logout(response: Response, auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db)):
    db.execute(update(Session).where(Session.id == auth.session.id).values(revoked=True))
    audit(db, auth.actor, "LOGOUT")
    db.commit()
    clear_cookie(response)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(response: Response, auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db)):
    db.execute(update(Session).where(Session.user_id == auth.user.id).values(revoked=True))
    audit(db, auth.actor, "LOGOUT_ALL")
    db.commit()
    clear_cookie(response)
    return {"ok": True}
