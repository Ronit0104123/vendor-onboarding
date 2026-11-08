"""Server-side sessions in an httpOnly cookie, plus a per-session CSRF token sent in a header."""
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from app.timeutil import utcnow

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.deps import get_db
from app.models import Session, User
from app.security.crypto import new_token, sha256_hex

COOKIE = "__Host-vo_session" if settings.is_prod else "vo_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _now():
    return utcnow()


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_session(db: DBSession, user: User) -> tuple[str, Session]:
    raw = new_token()
    s = Session(token_hash=sha256_hex(raw), user_id=user.id, csrf_token=secrets.token_urlsafe(32),
                expires_at=_now() + timedelta(hours=settings.session_hours))
    db.add(s)
    return raw, s


def set_cookie(response, raw: str) -> None:
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings.is_prod, samesite="strict",
                        path="/", max_age=settings.session_hours * 3600)


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE, path="/", secure=settings.is_prod, samesite="strict", httponly=True)


class Auth:
    def __init__(self, user: User, session: Session):
        self.user, self.session = user, session

    @property
    def actor(self) -> str:
        return f"user:{self.user.id}"


def current_auth(request: Request, db: DBSession = Depends(get_db)) -> Auth:
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401, "Sign in to continue.")
    s = db.scalars(select(Session).where(Session.token_hash == sha256_hex(raw))).first()
    now = _now()
    if (s is None or s.revoked or _aware(s.expires_at) <= now
            or now - _aware(s.last_seen_at) > timedelta(minutes=settings.session_idle_minutes)):
        raise HTTPException(401, "Your session has expired. Sign in again.")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(sent, s.csrf_token):
            raise HTTPException(403, "Security check failed. Refresh the page and try again.")
    if now - _aware(s.last_seen_at) > timedelta(seconds=30):  # avoid a write on every request
        s.last_seen_at = now
        db.commit()
    user = db.get(User, s.user_id)
    return Auth(user, s)


def require_admin(auth: Auth = Depends(current_auth)) -> Auth:
    if auth.user.role != "ADMIN":
        raise HTTPException(403, "You need the Admin role to do this.")
    return auth
