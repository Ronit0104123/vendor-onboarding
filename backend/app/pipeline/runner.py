"""Runs S1..S9 for one run, persisting each stage as it goes (the live view reads these rows)."""
import asyncio
import logging
import time
from datetime import datetime, timezone
from app.timeutil import utcnow

from app.audit import audit
from app.config import settings
from app.db import SessionLocal
from app.models import Check, Run, StageResult
from app.pipeline import (s1_intake, s2_documents, s3_completeness, s4_format, s5_consistency, s6_names,
                          s7_risk, s8_decision, s9_communication)
from app.pipeline.checks import CheckResult, Severity
from app.pipeline.context import RunContext
from app.pipeline.decision import Status
from app.redact import redact
from app.security.crypto import decrypt

log = logging.getLogger(__name__)

STAGES = [
    ("S1", "Intake", s1_intake),
    ("S2", "Document understanding", s2_documents),
    ("S3", "Completeness", s3_completeness),
    ("S4", "Format validation", s4_format),
    ("S5", "Cross-field consistency", s5_consistency),
    ("S6", "Name matching", s6_names),
    ("S7", "Risk checks", s7_risk),
    ("S8", "Decision", s8_decision),
    ("S9", "Communication", s9_communication),
]
STAGE_INPUTS = {
    "S1": "Submitted form and files", "S2": "Uploaded documents (as images)",
    "S3": "Form fields + detected document types", "S4": "Typed IDs and codes",
    "S5": "GSTIN, PAN, state, extracted vs typed values", "S6": "Legal, GST-certificate, PAN and bank names",
    "S7": "Vendor master, contact email, GST & bank verification", "S8": "All check results",
    "S9": "Decision and the checks behind it",
}
SEVERITY_TO_STATUS = {Severity.BLOCKING: "fail", Severity.FIXABLE: "fail", Severity.NEEDS_REVIEW: "review",
                      Severity.WARN: "warn", Severity.PASS: "pass"}
RANK = ["pass", "warn", "review", "fail"]


def _now():
    return utcnow()


def build_context(db, run: Run) -> RunContext:
    sub = run.submission
    form = {
        "legal_name": sub.legal_name, "trade_name": sub.trade_name, "country": sub.country,
        "address_line": sub.address_line, "city": sub.city, "state": sub.state, "postal_code": sub.postal_code,
        "contact_name": sub.contact_name, "contact_email": sub.contact_email, "contact_phone": sub.contact_phone,
        "pan": decrypt(sub.pan_enc) if sub.pan_enc else "", "gstin": sub.gstin or "", "tax_id": sub.other_tax_id or "",
        "bank_holder_name": sub.bank_holder_name, "account_number": decrypt(sub.account_enc) if sub.account_enc else "",
        "bank_code": sub.bank_code,
    }
    return RunContext(db=db, run=run, submission=sub, vendor=sub.vendor, form=form,
                      documents={d.slot: d for d in sub.documents})


async def run_pipeline(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        # A restarted run starts clean (stage rows are working state; the audit log keeps history).
        db.query(StageResult).filter(StageResult.run_id == run_id).delete()
        db.query(Check).filter(Check.run_id == run_id).delete()
        stage_rows = {code: StageResult(run_id=run_id, stage=code, name=name, status="pending")
                      for code, name, _ in STAGES}
        db.add_all(stage_rows.values())
        run.started_at = _now()
        run.vendor_id = run.submission.vendor_id
        run.submission.vendor.status = "PROCESSING"
        db.commit()

        ctx = build_context(db, run)
        delay = settings.demo_stage_delay_ms / 1000 if settings.llm_mode == "mock" else 0

        for code, name, module in STAGES:
            row = stage_rows[code]
            row.status, row.started_at, row.input_json = "running", _now(), {"summary": STAGE_INPUTS[code]}
            db.commit()
            started = time.monotonic()
            before = len(ctx.checks)
            try:
                output = await module.run(ctx)
            except Exception as exc:  # never crash; never approve after an internal error
                log.exception("stage %s failed run=%s", code, run_id)
                output = {"error": type(exc).__name__}
                ctx.add(CheckResult("PIPELINE_ERROR", code, Severity.NEEDS_REVIEW,
                                    f"{name} hit an internal error ({type(exc).__name__}); a reviewer must complete it."))
                if code == "S8":
                    from app.pipeline.decision import Decision
                    ctx.decision = Decision(Status.PENDING_INTERNAL, "Decision stage failed", ctx.checks[-1:])
                db.rollback()
            if delay:
                await asyncio.sleep(delay)
            new_checks = ctx.checks[before:]
            for c in new_checks:
                db.add(Check(run_id=run_id, stage=c.stage, code=c.code, severity=c.severity.value,
                             reason=c.reason, field=c.field, vendor_message=c.vendor_message))
            statuses = [SEVERITY_TO_STATUS[c.severity] for c in new_checks] or ["pass"]
            if code == "S8":
                statuses = [{"APPROVED": "pass", "PENDING_INTERNAL": "review"}.get(ctx.decision.status.value, "fail")]
            row.status = max(statuses, key=RANK.index)
            row.duration_ms = int((time.monotonic() - started) * 1000)
            row.output_json = redact(output)
            db.commit()

        decision = ctx.decision
        run.status, run.finished_at = "DONE", _now()
        run.decision, run.decision_summary = decision.status.value, decision.summary
        vendor = ctx.vendor
        vendor.status = decision.status.value
        if decision.status in (Status.APPROVED, Status.REJECTED, Status.AUTO_CLOSED):
            vendor.decided_at = _now()
        audit(db, "system", "DECISION", vendor.id, run_id=run_id, attempt=ctx.submission.attempt_no,
              status=decision.status.value, because=[c.code for c in decision.deciding_checks])
        db.commit()
