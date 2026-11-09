"""Turns database rows into API responses. PAN and account numbers are always masked here."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.config import settings
from app.models import (AuditEvent, LLMCall, OutboxMessage, OverrideRequest, Run, Submission, User, Vendor,
                        VendorMaster)
from app.portal_links import active_token
from app.security.crypto import mask

FIELD_LABELS = {"legal_name": "Legal name", "pan": "PAN", "gstin": "GSTIN", "bank_holder_name": "Account holder",
                "account_number": "Account number", "bank_code": "IFSC"}
# typed field -> (document slot, extracted key, check code that judged it)
COMPARISONS = [
    ("legal_name", "GST_CERT", "legal_name", "NAME_LEGAL_GST"),
    ("gstin", "GST_CERT", "gstin", "DOC_VS_FORM"),
    ("pan", "PAN_CARD", "pan", "DOC_VS_FORM"),
    ("bank_holder_name", "BANK_PROOF", "account_holder_name", "NAME_BANK_DOC"),
    ("account_number", "BANK_PROOF", "account_number", "DOC_VS_FORM"),
    ("bank_code", "BANK_PROOF", "ifsc", "DOC_VS_FORM"),
]


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def last_run(vendor: Vendor) -> Run | None:
    subs = vendor.submissions
    return subs[-1].run if subs else None


REMINDER_COOLDOWN = timedelta(hours=24)


def reminder_due(db: Session, vendor: Vendor) -> tuple[bool, int]:
    """Due when the vendor has been silent for REMINDER_DAYS since our last contact
    (the last decision email or the last reminder, whichever is later)."""
    if vendor.status != "PENDING_VENDOR":
        return False, 0
    run = last_run(vendor)
    since = aware(run.finished_at if run and run.finished_at else vendor.updated_at)
    if vendor.last_reminder_at:
        since = max(since, aware(vendor.last_reminder_at))
    days = (clock.now(db) - since).days
    return days >= settings.reminder_days, days


def reminder_available_at(db: Session, vendor: Vendor):
    """When the next reminder may be sent, or None if one can be sent now."""
    if not vendor.last_reminder_at:
        return None
    available = aware(vendor.last_reminder_at) + REMINDER_COOLDOWN
    return available if available > clock.now(db) else None


def vendor_row(db: Session, v: Vendor) -> dict:
    due, days = reminder_due(db, v)
    return {"id": v.id, "ref": f"VND-{v.id:04d}", "display_name": v.display_name, "category": v.category,
            "contact_email": v.contact_email, "requested_by": v.requested_by, "status": v.status,
            "attempt_count": v.attempt_count, "max_attempts": settings.max_attempts,
            "created_at": iso(v.created_at), "updated_at": iso(v.updated_at), "decided_at": iso(v.decided_at),
            "reminder_due": due, "days_waiting": days, "last_reminder_at": iso(v.last_reminder_at),
            "reminder_available_at": iso(reminder_available_at(db, v))}


def stage_view(s) -> dict:
    return {"stage": s.stage, "name": s.name, "status": s.status, "started_at": iso(s.started_at),
            "duration_ms": s.duration_ms, "input": s.input_json, "output": s.output_json}


def check_view(c) -> dict:
    return {"stage": c.stage, "code": c.code, "severity": c.severity, "reason": c.reason, "field": c.field,
            "vendor_message": c.vendor_message}


def run_view(db: Session, run: Run, include_llm: bool = True) -> dict:
    out = {"id": run.id, "vendor_id": run.vendor_id, "attempt_no": run.submission.attempt_no,
           "vendor_name": run.submission.vendor.display_name, "status": run.status, "decision": run.decision,
           "summary": run.decision_summary, "created_at": iso(run.created_at), "started_at": iso(run.started_at),
           "finished_at": iso(run.finished_at), "stages": [stage_view(s) for s in run.stages],
           "checks": [check_view(c) for c in run.checks]}
    if include_llm:
        calls = db.scalars(select(LLMCall).where(LLMCall.run_id == run.id).order_by(LLMCall.id)).all()
        out["llm_calls"] = [{"purpose": c.purpose, "model": c.model, "prompt_summary": c.prompt_summary,
                             "ok": c.ok, "error": c.error, "attempts": c.attempts, "latency_ms": c.latency_ms,
                             "tokens_in": c.tokens_in, "tokens_out": c.tokens_out, "output": c.output_json,
                             "at": iso(c.created_at)} for c in calls]
    return out


def submission_fields(s: Submission) -> dict:
    return {"legal_name": s.legal_name, "trade_name": s.trade_name, "country": s.country,
            "address_line": s.address_line, "city": s.city, "state": s.state, "postal_code": s.postal_code,
            "contact_name": s.contact_name, "contact_email": s.contact_email, "contact_phone": s.contact_phone,
            "pan": mask(s.pan_last4) if s.pan_last4 else "", "gstin": s.gstin or "", "tax_id": s.other_tax_id or "",
            "bank_holder_name": s.bank_holder_name, "account_number": mask(s.account_last4) if s.account_last4 else "",
            "bank_code": s.bank_code}


def comparison(s: Submission, run: Run | None) -> list[dict]:
    if not run:
        return []
    s2 = next((st.output_json for st in run.stages if st.stage == "S2"), None) or {}
    typed = submission_fields(s)
    rows = []
    for field, slot, key, code in COMPARISONS:
        doc = s2.get(slot) or {}
        if not doc.get("fields"):
            continue
        item = doc["fields"].get(key) or {}
        check = next((c for c in run.checks if c.code == code and (code != "DOC_VS_FORM" or c.field == field)), None)
        if code == "DOC_VS_FORM":
            check = next((c for c in run.checks if c.code == code and c.field == field), None)
        rows.append({"field": field, "label": FIELD_LABELS[field], "document": slot, "typed": typed.get(field),
                     "extracted": item.get("value"), "confidence": item.get("confidence"),
                     "result": check.severity if check else None, "reason": check.reason if check else None})
    return rows


def vendor_detail(db: Session, v: Vendor, viewer: User) -> dict:
    attempts = []
    for s in v.submissions:
        attempts.append({
            "submission_id": s.id, "attempt_no": s.attempt_no, "submitted_at": iso(s.created_at),
            "fields": submission_fields(s),
            "documents": [{"id": d.id, "slot": d.slot, "name": d.original_name, "mime": d.mime,
                           "size_bytes": d.size_bytes, "reused_from_attempt": d.reused_from_attempt}
                          for d in s.documents],
            "run": run_view(db, s.run) if s.run else None,
            "comparison": comparison(s, s.run),
        })
    outbox = db.scalars(select(OutboxMessage).where(OutboxMessage.vendor_id == v.id).order_by(OutboxMessage.id)).all()
    events = db.scalars(select(AuditEvent).where(AuditEvent.vendor_id == v.id).order_by(AuditEvent.id)).all()
    overrides = db.scalars(select(OverrideRequest).where(OverrideRequest.vendor_id == v.id)
                           .order_by(OverrideRequest.id)).all()
    users = {u.id: u.name for u in db.scalars(select(User)).all()}
    master = db.scalars(select(VendorMaster).where(VendorMaster.vendor_id == v.id)).first()
    token = active_token(db, v.id)
    return {
        "vendor": vendor_row(db, v),
        "attempts": attempts,
        "outbox": [message_view(m) for m in outbox],
        "audit": [{"id": e.id, "at": iso(e.at), "actor": actor_name(e.actor, users, v), "action": e.action,
                   "details": e.details} for e in events],
        "overrides": [{"id": o.id, "decision": o.decision, "reason": o.reason, "status": o.status,
                       "requested_by": users.get(o.requested_by), "requested_by_id": o.requested_by,
                       "reviewed_by": users.get(o.reviewed_by), "review_note": o.review_note,
                       "created_at": iso(o.created_at), "reviewed_at": iso(o.reviewed_at)} for o in overrides],
        "in_vendor_master": master is not None,
        "portal": {"active": token is not None, "expires_at": iso(token.expires_at) if token else None},
        "can_admin": viewer.role == "ADMIN",
        "four_eyes": settings.four_eyes_overrides,
    }


def actor_name(actor: str, users: dict, v: Vendor) -> str:
    if actor.startswith("user:"):
        return users.get(int(actor.split(":")[1]), actor)
    if actor.startswith("vendor:"):
        return f"{v.display_name} (vendor portal)"
    return "System"


def message_view(m: OutboxMessage) -> dict:
    return {"id": m.id, "vendor_id": m.vendor_id, "run_id": m.run_id, "kind": m.kind, "to": m.to_address,
            "subject": m.subject, "body": m.body, "drafted_by": m.drafted_by, "sent_via": m.sent_via,
            "created_at": iso(m.created_at)}
