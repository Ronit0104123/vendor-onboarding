"""Every outgoing message is written to the outbox (the audit trail). Delivery via Resend is optional."""
import logging

import httpx
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.models import OutboxMessage

log = logging.getLogger(__name__)


def send_message(db: Session, *, vendor_id: int, kind: str, to: str, subject: str, body: str,
                 drafted_by: str = "TEMPLATE", run_id: int | None = None) -> OutboxMessage:
    msg = OutboxMessage(vendor_id=vendor_id, run_id=run_id, kind=kind, to_address=to,
                        subject=subject, body=body, drafted_by=drafted_by, sent_via="LOG")
    if settings.resend_api_key:
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={"from": settings.email_from, "to": [to], "subject": subject, "text": body},
                timeout=10,
            )
            response.raise_for_status()
            msg.sent_via = "RESEND"
        except Exception as exc:  # delivery failure must never break the pipeline
            log.warning("email delivery failed kind=%s vendor=%s error=%s", kind, vendor_id, type(exc).__name__)
    db.add(msg)
    audit(db, "system", "MESSAGE_SENT", vendor_id, kind=kind, to=to, via=msg.sent_via, drafted_by=drafted_by)
    return msg
