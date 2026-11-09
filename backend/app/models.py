"""Database tables. Sensitive values (PAN, bank account) are stored encrypted plus a keyed hash for lookups."""
from datetime import datetime, timezone
from app.timeutil import utcnow

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def now() -> datetime:
    return utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(10))  # VIEWER | ADMIN
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(60))
    contact_email: Mapped[str] = mapped_column(String(254))
    requested_by: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="INVITED", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submissions: Mapped[list["Submission"]] = relationship(back_populates="vendor", order_by="Submission.attempt_no")


class PortalToken(Base):
    __tablename__ = "portal_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Encrypted copy so the *same* link can be re-sent in follow-up emails. Lookups only use the hash.
    token_enc: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2))
    address_line: Mapped[str] = mapped_column(String(300))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(100))
    postal_code: Mapped[str] = mapped_column(String(12))
    contact_name: Mapped[str] = mapped_column(String(120))
    contact_email: Mapped[str] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    # Tax ids: {"PAN": "...", "GSTIN": "..."}; PAN additionally stored encrypted below.
    gstin: Mapped[str | None] = mapped_column(String(15))
    other_tax_id: Mapped[str | None] = mapped_column(String(20))  # EIN / VAT for non-IN
    pan_enc: Mapped[str | None] = mapped_column(Text)
    pan_last4: Mapped[str | None] = mapped_column(String(4))
    pan_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    bank_holder_name: Mapped[str] = mapped_column(String(200))
    account_enc: Mapped[str] = mapped_column(Text)
    account_last4: Mapped[str] = mapped_column(String(4))
    account_hash: Mapped[str] = mapped_column(String(64), index=True)
    bank_code: Mapped[str] = mapped_column(String(20))  # IFSC / routing / sort code
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    vendor: Mapped[Vendor] = relationship(back_populates="submissions")
    documents: Mapped[list["Document"]] = relationship(back_populates="submission")
    run: Mapped["Run | None"] = relationship(back_populates="submission", uselist=False)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), index=True)
    slot: Mapped[str] = mapped_column(String(20))  # GST_CERT | PAN_CARD | BANK_PROOF
    original_name: Mapped[str] = mapped_column(String(200))
    stored_name: Mapped[str] = mapped_column(String(80))  # shared when a resubmission keeps a file
    sha256: Mapped[str] = mapped_column(String(64))  # of the bytes the vendor uploaded
    mime: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    reused_from_attempt: Mapped[int | None] = mapped_column(Integer)

    submission: Mapped[Submission] = relationship(back_populates="documents")


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), unique=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    # Durable job queue: QUEUED -> RUNNING -> DONE. A worker claims QUEUED rows atomically.
    status: Mapped[str] = mapped_column(String(10), default="QUEUED", index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tries: Mapped[int] = mapped_column(Integer, default=0)
    decision: Mapped[str | None] = mapped_column(String(20))
    decision_summary: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="run")
    stages: Mapped[list["StageResult"]] = relationship(order_by="StageResult.id")
    checks: Mapped[list["Check"]] = relationship(order_by="Check.id")


class StageResult(Base):
    __tablename__ = "stage_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(4))  # S1..S9
    name: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(10))  # pending | running | pass | warn | fail | review
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_json: Mapped[dict | None] = mapped_column(JSON)   # redacted
    output_json: Mapped[dict | None] = mapped_column(JSON)  # redacted


class Check(Base):
    __tablename__ = "checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(4))
    code: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(14))
    reason: Mapped[str] = mapped_column(Text)
    field: Mapped[str | None] = mapped_column(String(40))
    vendor_message: Mapped[str | None] = mapped_column(Text)


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(60))
    prompt_summary: Mapped[str] = mapped_column(Text)
    output_json: Mapped[dict | None] = mapped_column(JSON)  # redacted
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(String(300))
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OutboxMessage(Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"))
    kind: Mapped[str] = mapped_column(String(20))  # INVITE | FIX_REQUEST | REJECTION | INTERNAL_ALERT | WELCOME | REMINDER
    to_address: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    drafted_by: Mapped[str] = mapped_column(String(10))  # LLM | TEMPLATE
    sent_via: Mapped[str] = mapped_column(String(10), default="LOG")  # LOG | RESEND
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VendorMaster(Base):
    """Approved vendors only. Payments can only go to vendors in this table."""
    __tablename__ = "vendor_master"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), unique=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    account_hash: Mapped[str] = mapped_column(String(64), index=True)
    pan_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    """Append-only (DB trigger rejects UPDATE/DELETE)."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    actor: Mapped[str] = mapped_column(String(120))  # "user:3", "vendor:12", "system"
    action: Mapped[str] = mapped_column(String(40))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    details: Mapped[dict | None] = mapped_column(JSON)


class OverrideRequest(Base):
    """Maker-checker: one admin proposes, a *different* admin approves before it takes effect."""
    __tablename__ = "override_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    decision: Mapped[str] = mapped_column(String(10))  # APPROVED | REJECTED
    reason: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(10), default="PENDING")  # PENDING | APPLIED | DECLINED
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppState(Base):
    """Tiny key/value store, e.g. the simulated clock offset used for reminder demos."""
    __tablename__ = "app_state"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
