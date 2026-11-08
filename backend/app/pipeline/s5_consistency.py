"""S5 Cross-field consistency. Fields that are each valid can still contradict each other."""
from app.config import settings
from app.pipeline.checks import CheckResult, Severity
from app.pipeline.context import SLOT_LABELS, RunContext
from app.validators import india
from app.validators.rules import state_codes

# (document slot, extracted field, form field, label, is_sensitive)
DOC_FORM_PAIRS = [
    ("GST_CERT", "gstin", "gstin", "GSTIN", False),
    ("PAN_CARD", "pan", "pan", "PAN", True),
    ("BANK_PROOF", "account_number", "account_number", "bank account number", True),
    ("BANK_PROOF", "ifsc", "bank_code", "IFSC", False),
]


def _clean(value: str | None) -> str:
    return (value or "").replace(" ", "").replace("-", "").upper()


def _show(value: str, sensitive: bool) -> str:
    return f"ending {value[-4:]}" if sensitive else value


async def run(ctx: RunContext) -> dict:
    f = ctx.form
    out = {}
    gstin, pan, state = f.get("gstin") or "", f.get("pan") or "", f.get("state") or ""

    if f.get("country") == "IN" and india.is_valid_gstin_format(gstin):
        if india.is_valid_pan(pan):
            embedded = india.pan_inside_gstin(gstin)
            if embedded == pan:
                ctx.add(CheckResult("PAN_IN_GSTIN", "S5", Severity.PASS,
                                    "The PAN inside the GSTIN (characters 3–12) matches the PAN submitted.", field="pan"))
            else:
                ctx.add(CheckResult("PAN_IN_GSTIN", "S5", Severity.BLOCKING,
                                    f"The GSTIN is registered to PAN ending {embedded[-4:]}, but the PAN submitted "
                                    f"ends {pan[-4:]}. The GST registration belongs to a different taxpayer.",
                                    field="gstin"))
            out["pan_in_gstin"] = embedded == pan
        expected = india.state_code_for(state)
        if expected:
            actual = india.state_code_of_gstin(gstin)
            names = {v: k.title() for k, v in state_codes().items()}
            if actual == expected:
                ctx.add(CheckResult("GSTIN_STATE", "S5", Severity.PASS,
                                    f"GSTIN state code {actual} matches the address state ({state}).", field="state"))
            else:
                ctx.add(CheckResult("GSTIN_STATE", "S5", Severity.BLOCKING,
                                    f"GSTIN state code is {actual} ({names.get(actual, 'unknown')}), but the "
                                    f"registered address is in {state} (code {expected}). A GSTIN is issued per "
                                    "state, so this registration is not for this address.", field="state"))
            out["gstin_state"] = {"gstin": actual, "address": expected}

    comparisons = []
    for slot, ext_key, form_key, label, sensitive in DOC_FORM_PAIRS:
        extraction = ctx.usable_extraction(slot)
        typed = _clean(f.get(form_key))
        if not extraction or not typed:
            continue
        item = getattr(extraction.fields, ext_key)
        read = _clean(item.value)
        if not read:
            continue
        comparisons.append({"field": form_key, "document": slot, "match": read == typed,
                            "confidence": item.confidence})
        if item.confidence < settings.confidence_threshold:
            ctx.add(CheckResult("DOC_VS_FORM", "S5", Severity.NEEDS_REVIEW,
                                f"The {label} on the {SLOT_LABELS[slot]} was read with low confidence "
                                f"({item.confidence:.2f}); a reviewer should compare it by eye.", field=form_key))
        elif read != typed:
            ctx.add(CheckResult("DOC_VS_FORM", "S5", Severity.FIXABLE,
                                f"The {label} on the {SLOT_LABELS[slot]} ({_show(read, sensitive)}) doesn't match "
                                f"the {label} entered in the form ({_show(typed, sensitive)}).", field=form_key,
                                vendor_message=f"The {label} you entered doesn't match your {SLOT_LABELS[slot]}. "
                                               f"Correct the {label}, or upload the right document."))
        else:
            ctx.add(CheckResult("DOC_VS_FORM", "S5", Severity.PASS,
                                f"{label[0].upper() + label[1:]} on the {SLOT_LABELS[slot]} matches the form.",
                                field=form_key))
    out["document_vs_form"] = comparisons
    return out
