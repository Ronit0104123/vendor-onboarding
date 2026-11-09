"""Every outgoing message is written to the outbox (the audit trail). Real delivery is optional:

- Brevo HTTP API when BREVO_API_KEY is set (works on hosts that block SMTP ports, e.g. Railway;
  the sender only needs to be a verified address, no domain required)
- SMTP (e.g. a Gmail account with an app password) when SMTP_USER / SMTP_PASSWORD are set
- Resend when RESEND_API_KEY is set
- otherwise the message is only logged to the in-app outbox

Addresses on reserved test domains (.example, .test, .invalid) are never actually sent to,
so the fictional demo vendors don't bounce mail back to the sender.
"""
import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr

import httpx
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.models import OutboxMessage

log = logging.getLogger(__name__)
TEST_DOMAINS = (".example", ".test", ".invalid", ".localhost")


def deliverable(address: str) -> bool:
    domain = address.rsplit("@", 1)[-1].lower()
    return not domain.endswith(TEST_DOMAINS)


def _send_smtp(to: str, subject: str, body: str) -> None:
    mail = EmailMessage()
    mail["From"] = settings.email_from
    mail["To"] = to
    mail["Subject"] = subject
    mail.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as server:
        server.starttls()  # encrypt before sending credentials
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(mail)


def _send_brevo(to: str, subject: str, body: str) -> None:
    name, address = parseaddr(settings.email_from)
    response = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
        json={"sender": {"name": name or address, "email": address}, "to": [{"email": to}],
              "subject": subject, "textContent": body},
        timeout=10,
    )
    response.raise_for_status()


def _send_resend(to: str, subject: str, body: str) -> None:
    response = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json={"from": settings.email_from, "to": [to], "subject": subject, "text": body},
        timeout=10,
    )
    response.raise_for_status()


def send_message(db: Session, *, vendor_id: int, kind: str, to: str, subject: str, body: str,
                 drafted_by: str = "TEMPLATE", run_id: int | None = None) -> OutboxMessage:
    msg = OutboxMessage(vendor_id=vendor_id, run_id=run_id, kind=kind, to_address=to,
                        subject=subject, body=body, drafted_by=drafted_by, sent_via="LOG")
    if deliverable(to):
        try:
            if settings.brevo_api_key:
                _send_brevo(to, subject, body)
                msg.sent_via = "BREVO"
            elif settings.smtp_user and settings.smtp_password:
                _send_smtp(to, subject, body)
                msg.sent_via = "SMTP"
            elif settings.resend_api_key:
                _send_resend(to, subject, body)
                msg.sent_via = "RESEND"
        except Exception as exc:  # delivery failure must never break the pipeline
            msg.sent_via = "FAILED"
            log.warning("email delivery failed kind=%s vendor=%s error=%s", kind, vendor_id, type(exc).__name__)
    db.add(msg)
    audit(db, "system", "MESSAGE_SENT", vendor_id, kind=kind, to=to, via=msg.sent_via, drafted_by=drafted_by)
    return msg
