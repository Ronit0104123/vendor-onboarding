from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.redact import redact


def audit(db: Session, actor: str, action: str, vendor_id: int | None = None, **details) -> None:
    """Append an audit event. Caller commits."""
    db.add(AuditEvent(actor=actor, action=action, vendor_id=vendor_id, details=redact(details) or None))
