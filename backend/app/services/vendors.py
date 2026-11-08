"""Business operations shared by the API, the demo panel and the seed script."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.emailer import send_message
from app.models import Document, Run, Submission, Vendor
from app.portal_links import issue_token, portal_url
from app.schemas import SubmissionIn, VendorRequestIn
from app.security.crypto import decrypt, encrypt, last4, lookup_hash, sha256_hex
from app.storage import storage
from app.uploads import clean_upload

SLOTS = ("GST_CERT", "PAN_CARD", "BANK_PROOF")
SLOT_LABELS = {"GST_CERT": "GST certificate", "PAN_CARD": "PAN card", "BANK_PROOF": "Bank proof"}
OPEN_FOR_SUBMISSION = {"INVITED", "PENDING_VENDOR"}


class SubmissionRejected(ValueError):
    pass


def create_vendor_request(db: Session, data: VendorRequestIn, actor: str, is_seed: bool = False) -> tuple[Vendor, str]:
    vendor = Vendor(display_name=data.display_name, category=data.category, contact_email=data.contact_email,
                    requested_by=data.requested_by, status="INVITED", is_seed=is_seed)
    db.add(vendor)
    db.flush()
    raw = issue_token(db, vendor.id)
    link = portal_url(raw)
    send_message(db, vendor_id=vendor.id, kind="INVITE", to=vendor.contact_email,
                 subject=f"Vendor registration with {settings.buyer_name}",
                 body=f"Dear {vendor.display_name} team,\n\n{settings.buyer_name} has invited you to register as a "
                      f"vendor. Please complete the form and upload your GST certificate, PAN card and a cancelled "
                      f"cheque (or bank letter) here:\n\n{link}\n\nThe link is personal to your company and expires in "
                      f"{settings.token_ttl_days} days.\n\nRegards,\nProcurement team\n{settings.buyer_name}")
    audit(db, actor, "VENDOR_REQUESTED", vendor.id, display_name=vendor.display_name, category=vendor.category)
    return vendor, link


def latest_submission(db: Session, vendor_id: int) -> Submission | None:
    return db.scalars(select(Submission).where(Submission.vendor_id == vendor_id)
                      .order_by(Submission.attempt_no.desc())).first()


def submit(db: Session, vendor: Vendor, form: SubmissionIn, files: dict[str, tuple[bytes, str]],
           actor: str) -> Run:
    """Create attempt N+1 and queue its run. Blank PAN/account and missing files on a resubmission
    keep the previous values (the vendor only changes what was flagged)."""
    if vendor.status not in OPEN_FOR_SUBMISSION:
        raise SubmissionRejected("This registration is not open for changes.")
    if vendor.attempt_count >= settings.max_attempts:
        raise SubmissionRejected("The maximum number of attempts has been reached.")

    previous = latest_submission(db, vendor.id)
    cleaned = {slot: clean_upload(data, SLOT_LABELS[slot]) for slot, (data, _) in files.items()}  # may raise UploadError

    pan = form.pan or (decrypt(previous.pan_enc) if previous and previous.pan_enc else "")
    account = form.account_number or (decrypt(previous.account_enc) if previous and previous.account_enc else "")
    vendor.attempt_count += 1
    sub = Submission(
        vendor_id=vendor.id, attempt_no=vendor.attempt_count, legal_name=form.legal_name, trade_name=form.trade_name,
        country=form.country, address_line=form.address_line, city=form.city, state=form.state,
        postal_code=form.postal_code, contact_name=form.contact_name, contact_email=form.contact_email,
        contact_phone=form.contact_phone, gstin=form.gstin or None, other_tax_id=form.tax_id or None,
        pan_enc=encrypt(pan) if pan else None, pan_last4=last4(pan) or None, pan_hash=lookup_hash(pan) if pan else None,
        bank_holder_name=form.bank_holder_name, account_enc=encrypt(account) if account else "",
        account_last4=last4(account), account_hash=lookup_hash(account) if account else "",
        bank_code=form.bank_code,
    )
    db.add(sub)
    db.flush()

    for slot, (original, filename) in files.items():
        clean = cleaned[slot]
        storage().put(clean.stored_name, clean.data, clean.mime)
        db.add(Document(submission_id=sub.id, slot=slot, original_name=filename[:200] or slot,
                        stored_name=clean.stored_name, mime=clean.mime, size_bytes=len(clean.data),
                        sha256=sha256_hex(original)))
    if previous:
        for old in previous.documents:
            if old.slot not in files:
                db.add(Document(submission_id=sub.id, slot=old.slot, original_name=old.original_name,
                                stored_name=old.stored_name, mime=old.mime, size_bytes=old.size_bytes,
                                sha256=old.sha256, reused_from_attempt=previous.attempt_no))

    run = Run(submission_id=sub.id, vendor_id=vendor.id, status="QUEUED")
    db.add(run)
    vendor.status = "SUBMITTED"
    audit(db, actor, "SUBMITTED", vendor.id, attempt=sub.attempt_no, files=sorted(files),
          kept_files=sorted({d.slot for d in (previous.documents if previous else [])} - set(files)))
    db.commit()
    return run
