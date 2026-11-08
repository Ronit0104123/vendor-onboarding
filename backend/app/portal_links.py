"""Vendor portal tokens: 32 random bytes, stored as a SHA-256 hash (for lookup) and encrypted (to re-send
the same link). Scoped to one vendor, expire after N days, revoked once the case is closed."""
from datetime import datetime, timedelta, timezone
from app.timeutil import utcnow

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PortalToken, Vendor
from app.security.crypto import decrypt, encrypt, new_token, sha256_hex


def _now():
    return utcnow()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def portal_url(raw_token: str) -> str:
    return f"{settings.public_app_url}/portal/{raw_token}"


def issue_token(db: Session, vendor_id: int) -> str:
    revoke_tokens(db, vendor_id)
    raw = new_token()
    db.add(PortalToken(vendor_id=vendor_id, token_hash=sha256_hex(raw), token_enc=encrypt(raw),
                       expires_at=_now() + timedelta(days=settings.token_ttl_days)))
    return raw


def revoke_tokens(db: Session, vendor_id: int) -> None:
    for t in db.scalars(select(PortalToken).where(PortalToken.vendor_id == vendor_id, PortalToken.revoked_at.is_(None))):
        t.revoked_at = _now()


def active_token(db: Session, vendor_id: int) -> PortalToken | None:
    t = db.scalars(select(PortalToken).where(PortalToken.vendor_id == vendor_id, PortalToken.revoked_at.is_(None))
                   .order_by(PortalToken.id.desc())).first()
    if t and _aware(t.expires_at) > _now():
        return t
    return None


def active_link(db: Session, vendor_id: int) -> str | None:
    t = active_token(db, vendor_id)
    return portal_url(decrypt(t.token_enc)) if t else None


def resolve_token(db: Session, raw: str) -> Vendor | None:
    """Returns the vendor for a valid, unexpired, unrevoked token; None otherwise (no detail leaked)."""
    if not raw or len(raw) > 100:
        return None
    t = db.scalars(select(PortalToken).where(PortalToken.token_hash == sha256_hex(raw))).first()
    if t is None or t.revoked_at is not None or _aware(t.expires_at) <= _now():
        return None
    return db.get(Vendor, t.vendor_id)
