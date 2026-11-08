"""Vendor portal. The token in the URL is the only credential, and every query is scoped to the
vendor that token belongs to: there is no vendor id anywhere in these routes."""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.deps import get_db
from app.portal_links import resolve_token
from app.ratelimit import limiter
from app.schemas import SubmissionIn
from app.services.vendors import OPEN_FOR_SUBMISSION, SubmissionRejected, latest_submission, submit
from app.uploads import MAX_BYTES, UploadError
from app.views import iso

router = APIRouter(prefix="/api/portal", tags=["portal"])
INVALID = "This link is invalid or has expired. Contact your buyer for a new link."
VENDOR_STATUS = {
    "INVITED": "Not submitted yet", "SUBMITTED": "Received, checking now", "PROCESSING": "Received, checking now",
    "PENDING_VENDOR": "Action needed from you", "PENDING_INTERNAL": "Under review by our team",
}


def vendor_for(db, token: str):
    vendor = resolve_token(db, token)
    if vendor is None:
        raise HTTPException(404, INVALID)
    return vendor


@router.get("/{token}")
@limiter.limit("60/minute")
def portal_state(request: Request, token: str, db: DBSession = Depends(get_db)):
    vendor = vendor_for(db, token)
    last = latest_submission(db, vendor.id)
    flags, prefill, documents = [], {}, []
    if last:
        prefill = {k: getattr(last, k) or "" for k in
                   ["legal_name", "trade_name", "country", "address_line", "city", "state", "postal_code",
                    "contact_name", "contact_email", "contact_phone", "bank_holder_name", "bank_code"]}
        prefill["gstin"] = last.gstin or ""
        prefill["tax_id"] = last.other_tax_id or ""
        prefill["pan_on_file"] = f"ending {last.pan_last4}" if last.pan_last4 else ""
        prefill["account_on_file"] = f"ending {last.account_last4}" if last.account_last4 else ""
        documents = [{"slot": d.slot, "name": d.original_name} for d in last.documents]
        if vendor.status == "PENDING_VENDOR" and last.run:
            flags = [{"field": c.field, "message": c.vendor_message} for c in last.run.checks
                     if c.severity == "FIXABLE" and c.vendor_message]
    return {
        "company": vendor.display_name, "buyer_name": settings.buyer_name, "contact_email": vendor.contact_email,
        "status": vendor.status, "status_label": VENDOR_STATUS.get(vendor.status, vendor.status),
        "can_submit": vendor.status in OPEN_FOR_SUBMISSION and vendor.attempt_count < settings.max_attempts,
        "attempt_no": vendor.attempt_count + 1, "max_attempts": settings.max_attempts,
        "last_submitted_at": iso(last.created_at) if last else None,
        "prefill": prefill, "documents_on_file": documents, "flags": flags,
        "max_file_mb": MAX_BYTES // (1024 * 1024),
    }


@router.post("/{token}/submit", status_code=202)
@limiter.limit("10/hour")
async def portal_submit(request: Request, token: str, data: str = Form(..., max_length=20000),
                        gst_cert: UploadFile | None = File(None), pan_card: UploadFile | None = File(None),
                        bank_proof: UploadFile | None = File(None), db: DBSession = Depends(get_db)):
    vendor = vendor_for(db, token)
    try:
        form = SubmissionIn.model_validate(json.loads(data))
    except (ValidationError, json.JSONDecodeError) as exc:
        errors = exc.errors() if isinstance(exc, ValidationError) else []
        raise HTTPException(422, {"message": "Some fields are invalid.",
                                  "fields": {".".join(map(str, e["loc"])): e["msg"] for e in errors}})
    files = {}
    for slot, upload in (("GST_CERT", gst_cert), ("PAN_CARD", pan_card), ("BANK_PROOF", bank_proof)):
        if upload is None or not upload.filename:
            continue
        content = await upload.read(MAX_BYTES + 1)
        files[slot] = (content, upload.filename)
    try:
        run = submit(db, vendor, form, files, actor=f"vendor:{vendor.id}")
    except UploadError as exc:
        db.rollback()
        raise HTTPException(422, {"message": str(exc)})
    except SubmissionRejected as exc:
        db.rollback()
        raise HTTPException(409, {"message": str(exc)})
    return {"received": True, "attempt_no": run.submission.attempt_no}
