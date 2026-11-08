"""S7 Risk: duplicates against the vendor master, free-mail domains, live GST + penny-drop verification."""
from sqlalchemy import select

from app.models import Submission, Vendor, VendorMaster
from app.pipeline.checks import CheckResult, Severity
from app.pipeline.context import RunContext
from app.validators.names import names_match
from app.verification.providers import lookup_gstin, penny_drop

FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com", "rediffmail.com",
                      "icloud.com", "proton.me", "protonmail.com", "aol.com", "live.com"}
COMPANY_FORMS = ("PRIVATE LIMITED", "PVT", "LIMITED", "LTD", "LLP")


def vendor_ref(v: Vendor) -> str:
    return f"{v.display_name} (VND-{v.id:04d})"


async def run(ctx: RunContext) -> dict:
    db, sub, f = ctx.db, ctx.submission, ctx.form
    out = {}

    # Duplicate bank account against APPROVED vendors -> blocking (possible fraud ring / impersonation).
    hit = db.scalars(select(VendorMaster).where(VendorMaster.account_hash == sub.account_hash,
                                                VendorMaster.vendor_id != ctx.vendor.id)).first()
    if hit:
        other = db.get(Vendor, hit.vendor_id)
        ctx.add(CheckResult("DUP_BANK_ACCOUNT", "S7", Severity.BLOCKING,
                            f"Bank account ending {sub.account_last4} is already registered to approved vendor "
                            f"{vendor_ref(other)}. Two vendors cannot share a payout account.",
                            field="account_number"))
        out["duplicate_account_of"] = other.id
    else:
        # Same account on another vendor that is still in flight: not proof, but a human should look.
        in_flight = db.scalars(select(Submission).join(Vendor).where(
            Submission.account_hash == sub.account_hash, Submission.vendor_id != ctx.vendor.id,
            Vendor.status.in_(["PROCESSING", "PENDING_VENDOR", "PENDING_INTERNAL", "SUBMITTED"]))).first()
        if in_flight:
            ctx.add(CheckResult("DUP_BANK_IN_FLIGHT", "S7", Severity.NEEDS_REVIEW,
                                f"Bank account ending {sub.account_last4} was also submitted by "
                                f"{vendor_ref(in_flight.vendor)}, which is still being onboarded.", field="account_number"))
        else:
            ctx.add(CheckResult("DUP_BANK_ACCOUNT", "S7", Severity.PASS,
                                "Bank account is not used by any other vendor.", field="account_number"))

    if sub.pan_hash:
        pan_hit = db.scalars(select(VendorMaster).where(VendorMaster.pan_hash == sub.pan_hash,
                                                        VendorMaster.vendor_id != ctx.vendor.id)).first()
        if pan_hit:
            other = db.get(Vendor, pan_hit.vendor_id)
            ctx.add(CheckResult("DUP_PAN", "S7", Severity.BLOCKING,
                                f"PAN ending {sub.pan_last4} already belongs to approved vendor {vendor_ref(other)}. "
                                "Use the existing vendor record instead of creating a duplicate.", field="pan"))
            out["duplicate_pan_of"] = other.id
        else:
            ctx.add(CheckResult("DUP_PAN", "S7", Severity.PASS, "PAN is not used by any other vendor.", field="pan"))

    domain = (f.get("contact_email") or "").rsplit("@", 1)[-1].lower()
    is_company = any(form in (f.get("legal_name") or "").upper() for form in COMPANY_FORMS)
    if domain in FREE_EMAIL_DOMAINS and is_company:
        ctx.add(CheckResult("FREE_EMAIL_DOMAIN", "S7", Severity.WARN,
                            f"A registered company is using a free email address (@{domain}). Not blocking, "
                            "but confirm the contact by phone before the first payment.", field="contact_email"))

    if f.get("country") == "IN" and f.get("gstin"):
        gst = lookup_gstin(f["gstin"])
        out["gst_lookup"] = gst.__dict__
        if gst.status == "ACTIVE":
            if gst.legal_name and not names_match(gst.legal_name, f.get("legal_name", "")):
                ctx.add(CheckResult("GST_LIVE_STATUS", "S7", Severity.NEEDS_REVIEW,
                                    f"GSTIN is active, but the GST network lists the legal name as \"{gst.legal_name}\".",
                                    field="gstin"))
            else:
                ctx.add(CheckResult("GST_LIVE_STATUS", "S7", Severity.PASS,
                                    f"GSTIN is active on the GST network ({gst.provider}).", field="gstin"))
        elif gst.status in ("CANCELLED", "NOT_FOUND"):
            ctx.add(CheckResult("GST_LIVE_STATUS", "S7", Severity.BLOCKING,
                                f"GST network reports this GSTIN as {gst.status.replace('_', ' ').lower()}.", field="gstin"))
        else:
            ctx.add(CheckResult("GST_LIVE_STATUS", "S7", Severity.WARN,
                                "Live GST verification was not available; only format, checksum and document "
                                "consistency were verified.", field="gstin"))

    if f.get("country") == "IN" and f.get("account_number") and f.get("bank_code"):
        bank = penny_drop(f["account_number"], f["bank_code"])
        out["penny_drop"] = {"status": bank.status, "provider": bank.provider, "name_at_bank": bank.name_at_bank}
        if bank.status == "VERIFIED":
            if bank.name_at_bank and not names_match(bank.name_at_bank, f.get("bank_holder_name", "")):
                ctx.add(CheckResult("PENNY_DROP", "S7", Severity.BLOCKING,
                                    f"The bank reports the account holder as \"{bank.name_at_bank}\", not "
                                    f"\"{f.get('bank_holder_name')}\" as entered.", field="bank_holder_name"))
            else:
                ctx.add(CheckResult("PENNY_DROP", "S7", Severity.PASS,
                                    "Penny-drop verification: the account exists and the holder name matches.",
                                    field="account_number"))
        elif bank.status == "ACCOUNT_INVALID":
            ctx.add(CheckResult("PENNY_DROP", "S7", Severity.FIXABLE,
                                "The bank could not credit a test deposit to this account.", field="account_number",
                                vendor_message="We couldn't verify your bank account. Check the account number and IFSC."))
        else:
            ctx.add(CheckResult("PENNY_DROP", "S7", Severity.WARN,
                                "Penny-drop verification was not available; bank details were checked against the "
                                "uploaded document only.", field="account_number"))
    return out
