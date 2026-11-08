"""S9 Communication + side effects. The LLM drafts only the wording around the list; code inserts the
exact items and the link, so a message can never ask for more (or less) than the checks found."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.audit import audit
from app.config import settings
from app.emailer import send_message
from app.llm.client import call_llm, prompt
from app.llm.schemas import MessageDraft
from app.models import PortalToken, VendorMaster
from app.pipeline.context import RunContext
from app.pipeline.decision import Status
from app.portal_links import active_link, revoke_tokens

SIGNATURE = "\n\nRegards,\nProcurement team\n{buyer}"


async def draft(ctx: RunContext, kind: str, items: list[str]) -> tuple[MessageDraft | None, str]:
    result = await call_llm(
        purpose="draft_message", model=settings.openai_model_text, schema=MessageDraft,
        messages=[{"role": "system", "content": prompt("draft_message").replace("{buyer_name}", settings.buyer_name)},
                  {"role": "user", "content": f"Message type: {kind}\nVendor: {ctx.vendor.display_name}\n"
                                              f"Number of items: {len(items)}\nItems (for context only):\n- "
                                              + "\n- ".join(items)}],
        prompt_summary=f"draft {kind} ({len(items)} items)",
        mock_input={"kind": kind, "vendor_name": ctx.vendor.display_name}, run_id=ctx.run.id,
    )
    return (result.data, "LLM") if result.ok else (None, "TEMPLATE")


def compose(d: MessageDraft, items: list[str] | None, link: str | None) -> str:
    parts = [d.opening]
    if items:
        parts.append("\n".join(f"{i}. {text}" for i, text in enumerate(items, 1)))
    if link:
        parts.append(f"Update your registration here: {link}")
    parts.append(d.closing)
    return "\n\n".join(parts) + SIGNATURE.format(buyer=settings.buyer_name)


TEMPLATES = {
    "FIX_REQUEST": MessageDraft(subject="Action needed: items to complete your vendor registration",
                                opening="Dear {v} team, thank you for your submission. Before we can complete your "
                                        "registration, please fix the following:",
                                closing="Everything else you submitted has been saved; you only need to update the items above."),
    "REJECTION": MessageDraft(subject="Update on your vendor registration",
                              opening="Dear {v} team, thank you for your interest in working with us.",
                              closing="After review, we are unable to proceed with this registration. If you believe "
                                      "this is an error, please reply to this email."),
    "WELCOME": MessageDraft(subject="Your vendor registration is approved",
                            opening="Dear {v} team, your registration is complete and you are now an approved vendor.",
                            closing="Our accounts payable team will be in touch about purchase orders and invoicing."),
}


def template(kind: str, vendor: str) -> MessageDraft:
    t = TEMPLATES[kind]
    return MessageDraft(subject=t.subject, opening=t.opening.replace("{v}", vendor), closing=t.closing)


async def run(ctx: RunContext) -> dict:
    db, vendor, decision = ctx.db, ctx.vendor, ctx.decision
    status = decision.status
    sent = []

    def send(kind, to, subject, body, drafted_by):
        send_message(db, vendor_id=vendor.id, run_id=ctx.run.id, kind=kind, to=to, subject=subject,
                     body=body, drafted_by=drafted_by)
        sent.append({"kind": kind, "to": to, "subject": subject, "drafted_by": drafted_by})

    reasons = [f"- [{c.code}] {c.reason}" for c in decision.deciding_checks]
    console_link = f"{settings.public_app_url}/vendors/{vendor.id}"

    if status == Status.PENDING_VENDOR:
        items = []
        for c in decision.deciding_checks:  # one line per item, de-duplicated
            if c.vendor_message and c.vendor_message not in items:
                items.append(c.vendor_message)
        d, by = await draft(ctx, "FIX_REQUEST", items)
        d = d or template("FIX_REQUEST", vendor.display_name)
        attempts_left = settings.max_attempts - ctx.submission.attempt_no
        body = compose(d, items, active_link(db, vendor.id))
        body += f"\n\n(You have {attempts_left} more attempt{'s' if attempts_left != 1 else ''} to resubmit.)"
        send("FIX_REQUEST", vendor.contact_email, d.subject, body, by)

    elif status == Status.REJECTED:
        d, by = await draft(ctx, "REJECTION", [])
        d = d or template("REJECTION", vendor.display_name)
        # The vendor is told politely, without detail on fraud checks; procurement gets the reasons.
        send("REJECTION", vendor.contact_email, d.subject, compose(d, None, None), by)
        send("INTERNAL_ALERT", settings.internal_alert_email, f"Rejected: {vendor.display_name}",
             f"Vendor {vendor.display_name} (VND-{vendor.id:04d}) was rejected on attempt "
             f"{ctx.submission.attempt_no}.\n\nReasons:\n" + "\n".join(reasons) + f"\n\nView: {console_link}", "TEMPLATE")
        revoke_tokens(db, vendor.id)

    elif status == Status.PENDING_INTERNAL:
        send("ACKNOWLEDGEMENT", vendor.contact_email, "We've received your vendor registration",
             f"Dear {vendor.display_name} team, thank you. Your registration is with our procurement team for a "
             "final review. You don't need to do anything right now; we'll write to you once it's complete."
             + SIGNATURE.format(buyer=settings.buyer_name), "TEMPLATE")
        send("INTERNAL_ALERT", settings.internal_alert_email, f"Review needed: {vendor.display_name}",
             f"{vendor.display_name} (VND-{vendor.id:04d}) needs a manual review:\n" + "\n".join(reasons)
             + f"\n\nReview: {console_link}", "TEMPLATE")

    elif status == Status.AUTO_CLOSED:
        send("CLOSED", vendor.contact_email, "Your vendor registration has been closed",
             f"Dear {vendor.display_name} team, we haven't been able to complete your registration after "
             f"{ctx.submission.attempt_no} attempts, so it has been closed. Please contact your {settings.buyer_name} "
             "buyer if you'd like to start again." + SIGNATURE.format(buyer=settings.buyer_name), "TEMPLATE")
        revoke_tokens(db, vendor.id)

    elif status == Status.APPROVED:
        d, by = await draft(ctx, "WELCOME", [])
        d = d or template("WELCOME", vendor.display_name)
        send("WELCOME", vendor.contact_email, d.subject, compose(d, None, None), by)
        add_to_vendor_master(ctx)
        revoke_tokens(db, vendor.id)

    return {"messages": sent, "vendor_master": status == Status.APPROVED}


def add_to_vendor_master(ctx: RunContext) -> None:
    db = ctx.db
    if db.scalars(select(VendorMaster).where(VendorMaster.vendor_id == ctx.vendor.id)).first():
        return
    db.add(VendorMaster(vendor_id=ctx.vendor.id, legal_name=ctx.submission.legal_name,
                        account_hash=ctx.submission.account_hash, pan_hash=ctx.submission.pan_hash))
    audit(db, "system", "VENDOR_MASTER_ADDED", ctx.vendor.id, legal_name=ctx.submission.legal_name)
