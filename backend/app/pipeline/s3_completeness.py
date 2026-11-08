"""S3 Completeness: required fields and required documents, and the right document in each slot."""
from app.config import settings
from app.pipeline.checks import CheckResult, Severity
from app.pipeline.context import DOC_TYPE_LABELS, EXPECTED_DOC_TYPES, SLOT_LABELS, RunContext
from app.validators.tax_ids import is_supported_country, required_documents, tax_id_rules

FIELD_LABELS = {
    "legal_name": "Legal name", "country": "Country", "address_line": "Registered address",
    "city": "City", "state": "State", "postal_code": "PIN / postal code", "contact_name": "Contact name",
    "contact_email": "Contact email", "pan": "PAN", "gstin": "GSTIN", "tax_id": "Tax ID",
    "bank_holder_name": "Bank account holder name", "account_number": "Bank account number",
    "bank_code": "IFSC / bank code",
}
COMMON_REQUIRED = ["legal_name", "country", "address_line", "city", "state", "postal_code",
                   "contact_name", "contact_email", "bank_holder_name", "account_number", "bank_code"]


def required_fields(country: str) -> list[str]:
    if country == "IN":
        return COMMON_REQUIRED + ["pan", "gstin"]
    return COMMON_REQUIRED + ["tax_id"]


async def run(ctx: RunContext) -> dict:
    country = ctx.form.get("country") or ""
    if not is_supported_country(country):
        ctx.add(CheckResult("COUNTRY_UNSUPPORTED", "S3", Severity.FIXABLE,
                            f"Country '{country}' is not supported for onboarding yet.", field="country",
                            vendor_message="Select the country where your business is registered (India, United States or United Kingdom)."))
        return {"country": country}

    missing_fields = [f for f in required_fields(country) if not (ctx.form.get(f) or "").strip()]
    for f in missing_fields:
        label = FIELD_LABELS[f]
        if f == "tax_id":
            label = " / ".join(r["label"] for r in tax_id_rules(country).values())
        ctx.add(CheckResult("REQ_FIELD_MISSING", "S3", Severity.FIXABLE, f"{label} was left blank.",
                            field=f, vendor_message=f"Enter your {label}."))

    needed_docs = required_documents(country)
    missing_docs = [slot for slot in needed_docs if slot not in ctx.documents]
    for slot in missing_docs:
        ctx.add(CheckResult("REQ_DOC_MISSING", "S3", Severity.FIXABLE, f"No {SLOT_LABELS[slot]} was uploaded.",
                            field=f"doc:{slot}", vendor_message=f"Upload your {SLOT_LABELS[slot]}."))

    doc_results = {}
    for slot in needed_docs:
        if slot not in ctx.documents:
            continue
        extraction = ctx.extractions.get(slot)
        if extraction is None:
            doc_results[slot] = "not read (LLM failure)"
            continue  # S2 already raised NEEDS_REVIEW
        detected = extraction.doc_type
        doc_results[slot] = f"{detected} ({extraction.doc_type_confidence:.2f})"
        if detected == "UNREADABLE" or extraction.doc_type_confidence < 0.5:
            ctx.add(CheckResult("DOC_UNREADABLE", "S3", Severity.FIXABLE,
                                f"The {SLOT_LABELS[slot]} could not be read reliably "
                                f"(confidence {extraction.doc_type_confidence:.2f}).", field=f"doc:{slot}",
                                vendor_message=f"Upload a clearer copy of your {SLOT_LABELS[slot]}: "
                                               "the whole page, flat, in good light."))
        elif detected not in EXPECTED_DOC_TYPES[slot]:
            ctx.add(CheckResult("DOC_WRONG_TYPE", "S3", Severity.FIXABLE,
                                f"The file in the {SLOT_LABELS[slot]} slot is {DOC_TYPE_LABELS[detected]}.",
                                field=f"doc:{slot}",
                                vendor_message=f"The file you uploaded as your {SLOT_LABELS[slot]} looks like "
                                               f"{DOC_TYPE_LABELS[detected]}. Upload your {SLOT_LABELS[slot]} instead."))
        elif extraction.doc_type_confidence < settings.confidence_threshold:
            ctx.add(CheckResult("DOC_TYPE_UNCERTAIN", "S3", Severity.NEEDS_REVIEW,
                                f"The {SLOT_LABELS[slot]} was classified with low confidence "
                                f"({extraction.doc_type_confidence:.2f}); a reviewer should confirm it.",
                                field=f"doc:{slot}"))
        else:
            ctx.add(CheckResult("DOC_TYPE_OK", "S3", Severity.PASS,
                                f"{SLOT_LABELS[slot][0].upper()}{SLOT_LABELS[slot][1:]} recognised as {DOC_TYPE_LABELS[detected]}.",
                                field=f"doc:{slot}"))

    if not missing_fields and not missing_docs:
        ctx.add(CheckResult("COMPLETE", "S3", Severity.PASS, "All required fields and documents are present."))
    return {"missing_fields": missing_fields, "missing_documents": missing_docs, "documents": doc_results}
