from datetime import datetime, timezone
from app.timeutil import utcnow

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app import clock
from app.audit import audit
from app.config import settings
from app.deps import get_db
from app.emailer import send_message
from app.models import AuditEvent, OutboxMessage, OverrideRequest, Run, Submission, Vendor, VendorMaster
from app.pipeline.s9_communication import SIGNATURE
from app.portal_links import active_link, issue_token, portal_url, revoke_tokens
from app.schemas import ClockIn, OverrideIn, OverrideReviewIn, RevealIn, VendorRequestIn
from app.security.crypto import decrypt
from app.security.sessions import Auth, current_auth, require_admin
from app.services.vendors import create_vendor_request
from app.views import aware, message_view, vendor_detail, vendor_row

router = APIRouter(prefix="/api", tags=["console"])
STATUSES = ["INVITED", "SUBMITTED", "PROCESSING", "PENDING_VENDOR", "PENDING_INTERNAL", "APPROVED", "REJECTED",
            "AUTO_CLOSED"]


def _now():
    return utcnow()


def get_vendor(db, vendor_id: int) -> Vendor:
    v = db.get(Vendor, vendor_id)
    if not v:
        raise HTTPException(404, "Vendor not found.")
    return v


@router.get("/stats")
def stats(auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db)):
    counts = dict(db.execute(select(Vendor.status, func.count()).group_by(Vendor.status)).all())
    decided = db.scalars(select(Vendor).where(Vendor.decided_at.is_not(None))).all()
    hours = []
    for v in decided:
        first = v.submissions[0].created_at if v.submissions else v.created_at
        hours.append((aware(v.decided_at) - aware(first)).total_seconds() / 3600)
    pending_vendor = db.scalars(select(Vendor).where(Vendor.status == "PENDING_VENDOR")).all()
    from app.views import reminder_due
    return {
        "total": sum(counts.values()),
        "by_status": {s: counts.get(s, 0) for s in STATUSES},
        "avg_hours_to_decision": round(sum(hours) / len(hours), 1) if hours else None,
        "decided": len(hours),
        "reminders_due": sum(1 for v in pending_vendor if reminder_due(db, v)[0]),
        "overrides_waiting": db.scalar(select(func.count()).select_from(OverrideRequest)
                                       .where(OverrideRequest.status == "PENDING")),
        "clock_offset_days": clock.offset_days(db),
    }


@router.get("/vendors")
def list_vendors(auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db),
                 status: str | None = Query(None, max_length=40), q: str | None = Query(None, max_length=100),
                 page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=5, le=100),
                 reminder: bool = False):
    stmt = select(Vendor)
    if status:
        wanted = [s for s in status.split(",") if s in STATUSES]
        stmt = stmt.where(Vendor.status.in_(wanted))
    if q:
        like = f"%{q.strip()}%"
        filters = [Vendor.display_name.ilike(like), Vendor.contact_email.ilike(like), Vendor.category.ilike(like)]
        ref = q.strip().upper().removeprefix("VND-")
        if ref.isdigit():
            filters.append(Vendor.id == int(ref))
        stmt = stmt.where(or_(*filters))
    rows = db.scalars(stmt.order_by(Vendor.updated_at.desc())).all()
    items = [vendor_row(db, v) for v in rows]
    if reminder:
        items = [i for i in items if i["reminder_due"]]
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size}


@router.post("/vendors", status_code=201)
def create_vendor(body: VendorRequestIn, auth: Auth = Depends(require_admin), db: DBSession = Depends(get_db)):
    vendor, link = create_vendor_request(db, body, auth.actor)
    db.commit()
    return {"vendor": vendor_row(db, vendor), "portal_url": link}


@router.get("/vendors/{vendor_id}")
def get_vendor_detail(vendor_id: int, auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db)):
    return vendor_detail(db, get_vendor(db, vendor_id), auth.user)


@router.post("/vendors/{vendor_id}/portal-link")
def portal_link(vendor_id: int, auth: Auth = Depends(require_admin), db: DBSession = Depends(get_db)):
    """Shows the active link (or issues a new one if expired). Audit-logged: the link grants access."""
    v = get_vendor(db, vendor_id)
    if v.status not in ("INVITED", "PENDING_VENDOR"):
        raise HTTPException(409, "This registration is closed; the portal link is no longer valid.")
    link = active_link(db, v.id)
    if link is None:
        link = portal_url(issue_token(db, v.id))
        audit(db, auth.actor, "PORTAL_LINK_REISSUED", v.id)
    else:
        audit(db, auth.actor, "PORTAL_LINK_VIEWED", v.id)
    db.commit()
    return {"portal_url": link}


@router.post("/vendors/{vendor_id}/remind")
def send_reminder(vendor_id: int, auth: Auth = Depends(require_admin), db: DBSession = Depends(get_db)):
    v = get_vendor(db, vendor_id)
    if v.status != "PENDING_VENDOR":
        raise HTTPException(409, "Reminders can only be sent while waiting on the vendor.")
    link = active_link(db, v.id) or portal_url(issue_token(db, v.id))
    last_fix = db.scalars(select(OutboxMessage).where(OutboxMessage.vendor_id == v.id,
                                                      OutboxMessage.kind == "FIX_REQUEST")
                          .order_by(OutboxMessage.id.desc())).first()
    body = (f"Dear {v.display_name} team,\n\nThis is a reminder that your vendor registration with "
            f"{settings.buyer_name} is waiting on a few items from you. You can update them here:\n\n{link}")
    if last_fix:
        body += f"\n\nFor reference, our last message (\"{last_fix.subject}\") listed what's needed."
    msg = send_message(db, vendor_id=v.id, kind="REMINDER", to=v.contact_email,
                       subject="Reminder: your vendor registration is incomplete",
                       body=body + SIGNATURE.format(buyer=settings.buyer_name))
    v.updated_at = clock.now(db)
    audit(db, auth.actor, "REMINDER_SENT", v.id)
    db.commit()
    return message_view(msg)


@router.post("/submissions/{submission_id}/reveal")
def reveal(submission_id: int, body: RevealIn, auth: Auth = Depends(require_admin), db: DBSession = Depends(get_db)):
    s = db.get(Submission, submission_id)
    if not s:
        raise HTTPException(404, "Submission not found.")
    enc = s.pan_enc if body.field == "pan" else s.account_enc
    if not enc:
        raise HTTPException(404, "No value on file.")
    audit(db, auth.actor, "PII_REVEALED", s.vendor_id, field=body.field, submission=s.id)
    db.commit()
    return {"value": decrypt(enc)}


@router.post("/vendors/{vendor_id}/overrides", status_code=201)
def request_override(vendor_id: int, body: OverrideIn, auth: Auth = Depends(require_admin),
                     db: DBSession = Depends(get_db)):
    v = get_vendor(db, vendor_id)
    if v.status != "PENDING_INTERNAL":
        raise HTTPException(409, "Only cases waiting on internal review can be overridden.")
    if db.scalars(select(OverrideRequest).where(OverrideRequest.vendor_id == v.id,
                                                OverrideRequest.status == "PENDING")).first():
        raise HTTPException(409, "An override is already waiting for approval.")
    run = v.submissions[-1].run
    o = OverrideRequest(vendor_id=v.id, run_id=run.id, decision=body.decision, reason=body.reason,
                        requested_by=auth.user.id)
    db.add(o)
    audit(db, auth.actor, "OVERRIDE_REQUESTED", v.id, decision=body.decision, reason=body.reason)
    db.flush()
    if not settings.four_eyes_overrides:
        apply_override(db, o, auth, note="Four-eyes disabled; applied directly.")
    db.commit()
    return {"id": o.id, "status": o.status}


@router.post("/overrides/{override_id}/review")
def review_override(override_id: int, body: OverrideReviewIn, auth: Auth = Depends(require_admin),
                    db: DBSession = Depends(get_db)):
    o = db.get(OverrideRequest, override_id)
    if not o or o.status != "PENDING":
        raise HTTPException(404, "No pending override with that id.")
    if o.requested_by == auth.user.id:
        raise HTTPException(403, "A different admin must approve this override (four-eyes rule).")
    if body.approve:
        apply_override(db, o, auth, body.note)
    else:
        o.status, o.reviewed_by, o.review_note, o.reviewed_at = "DECLINED", auth.user.id, body.note, _now()
        audit(db, auth.actor, "OVERRIDE_DECLINED", o.vendor_id, override=o.id, note=body.note)
    db.commit()
    return {"id": o.id, "status": o.status}


def apply_override(db, o: OverrideRequest, auth: Auth, note: str) -> None:
    v = db.get(Vendor, o.vendor_id)
    sub = v.submissions[-1]
    if o.decision == "APPROVED":
        clash = db.scalars(select(VendorMaster).where(VendorMaster.account_hash == sub.account_hash,
                                                      VendorMaster.vendor_id != v.id)).first()
        if clash:
            raise HTTPException(409, "This bank account belongs to another approved vendor; it cannot be approved.")
        db.add(VendorMaster(vendor_id=v.id, legal_name=sub.legal_name, account_hash=sub.account_hash,
                            pan_hash=sub.pan_hash))
        send_message(db, vendor_id=v.id, run_id=o.run_id, kind="WELCOME", to=v.contact_email,
                     subject="Your vendor registration is approved",
                     body=f"Dear {v.display_name} team,\n\nYour registration is complete and you are now an approved "
                          "vendor. Our accounts payable team will be in touch." + SIGNATURE.format(buyer=settings.buyer_name))
    else:
        send_message(db, vendor_id=v.id, run_id=o.run_id, kind="REJECTION", to=v.contact_email,
                     subject="Update on your vendor registration",
                     body=f"Dear {v.display_name} team,\n\nThank you for your interest. After review, we are unable "
                          "to proceed with this registration." + SIGNATURE.format(buyer=settings.buyer_name))
    v.status, v.decided_at = o.decision, _now()
    revoke_tokens(db, v.id)
    o.status, o.reviewed_by, o.review_note, o.reviewed_at = "APPLIED", auth.user.id, note, _now()
    audit(db, auth.actor, "OVERRIDE_APPLIED", v.id, override=o.id, decision=o.decision, reason=o.reason, note=note)


@router.get("/overrides")
def pending_overrides(auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db)):
    rows = db.scalars(select(OverrideRequest).where(OverrideRequest.status == "PENDING")).all()
    return [{"id": o.id, "vendor_id": o.vendor_id, "vendor_name": db.get(Vendor, o.vendor_id).display_name,
             "decision": o.decision, "reason": o.reason, "requested_by_id": o.requested_by} for o in rows]


@router.get("/outbox")
def outbox(auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db),
           page: int = Query(1, ge=1, le=1000), page_size: int = Query(25, ge=5, le=100)):
    total = db.scalar(select(func.count()).select_from(OutboxMessage))
    rows = db.scalars(select(OutboxMessage).order_by(OutboxMessage.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    names = {v.id: v.display_name for v in db.scalars(select(Vendor)).all()}
    return {"items": [{**message_view(m), "vendor_name": names.get(m.vendor_id)} for m in rows],
            "total": total, "page": page, "page_size": page_size}


@router.get("/runs")
def recent_runs(auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db), limit: int = Query(15, le=50)):
    rows = db.scalars(select(Run).order_by(Run.created_at.desc()).limit(limit)).all()
    return [{"id": r.id, "vendor_id": r.vendor_id, "vendor_name": r.submission.vendor.display_name,
             "attempt_no": r.submission.attempt_no, "status": r.status, "decision": r.decision,
             "created_at": aware(r.created_at).isoformat()} for r in rows]


@router.get("/clock")
def get_clock(auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db)):
    return {"offset_days": clock.offset_days(db), "now": clock.now(db).isoformat()}


@router.post("/clock")
def set_clock(body: ClockIn, auth: Auth = Depends(require_admin), db: DBSession = Depends(get_db)):
    clock.set_offset_days(db, body.offset_days)
    audit(db, auth.actor, "CLOCK_SET", offset_days=body.offset_days)
    db.commit()
    return {"offset_days": body.offset_days}
