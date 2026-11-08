"""S6 Name matching. Code normalises first; only unresolved pairs go to the LLM for a judgment.
The LLM's verdict maps to a severity in code; UNSURE always means a human looks."""
import asyncio

from app.config import settings
from app.llm.client import call_llm, prompt
from app.llm.schemas import NameJudgement
from app.pipeline.checks import CheckResult, Severity
from app.pipeline.context import RunContext
from app.validators.names import looks_like_company, names_match, normalise_name


def name_pairs(ctx: RunContext) -> list[tuple[str, str, str, str, float]]:
    """(code, label, name_a, name_b, confidence_of_b)"""
    f = ctx.form
    pairs = []
    if f.get("legal_name") and f.get("bank_holder_name"):
        pairs.append(("NAME_LEGAL_BANK", "bank account holder name", f["legal_name"], f["bank_holder_name"], 1.0))
    gst = ctx.usable_extraction("GST_CERT")
    if gst and gst.fields.legal_name.value and f.get("legal_name"):
        pairs.append(("NAME_LEGAL_GST", "legal name on the GST certificate", f["legal_name"],
                      gst.fields.legal_name.value, gst.fields.legal_name.confidence))
    pan = ctx.usable_extraction("PAN_CARD")
    if pan and pan.fields.legal_name.value and f.get("legal_name"):
        pairs.append(("NAME_LEGAL_PAN", "name on the PAN card", f["legal_name"],
                      pan.fields.legal_name.value, pan.fields.legal_name.confidence))
    bank = ctx.usable_extraction("BANK_PROOF")
    if bank and bank.fields.account_holder_name.value and f.get("bank_holder_name"):
        pairs.append(("NAME_BANK_DOC", "account holder on the cheque / bank letter", f["bank_holder_name"],
                      bank.fields.account_holder_name.value, bank.fields.account_holder_name.confidence))
    return pairs


async def judge(ctx: RunContext, code, label, a, b, confidence) -> tuple[CheckResult, dict]:
    trace = {"a": a, "b": b, "normalised_a": normalise_name(a), "normalised_b": normalise_name(b)}
    if names_match(a, b):
        trace["method"] = "normalised match"
        note = "" if a.strip().upper() == b.strip().upper() else f" (\"{a}\" = \"{b}\" after normalisation)"
        return CheckResult(code, "S6", Severity.PASS, f"Legal name matches the {label}{note}.", field="legal_name"), trace

    if confidence < settings.confidence_threshold:
        trace["method"] = "low confidence"
        return CheckResult(code, "S6", Severity.NEEDS_REVIEW,
                           f"The {label} (\"{b}\") was read with low confidence ({confidence:.2f}); compare by eye.",
                           field="legal_name"), trace

    result = await call_llm(
        purpose="name_match", model=settings.openai_model_text, schema=NameJudgement,
        messages=[{"role": "system", "content": prompt("name_match")},
                  {"role": "user", "content": f"Name A: {a!r}\nName B: {b!r}"}],
        prompt_summary=f"name_match {code}", mock_input={"name_a": a, "name_b": b}, run_id=ctx.run.id,
    )
    trace["method"] = "llm"
    if not result.ok:
        trace["llm"] = {"error": result.error}
        return CheckResult(code, "S6", Severity.NEEDS_REVIEW,
                           f"Could not compare \"{a}\" with the {label} \"{b}\" automatically ({result.error}).",
                           field="legal_name"), trace
    verdict: NameJudgement = result.data
    trace["llm"] = verdict.model_dump()
    if verdict.verdict == "SAME_ENTITY":
        return CheckResult(code, "S6", Severity.PASS,
                           f"\"{a}\" and \"{b}\" judged the same entity: {verdict.reason}", field="legal_name"), trace
    if verdict.verdict == "UNSURE":
        return CheckResult(code, "S6", Severity.NEEDS_REVIEW,
                           f"\"{a}\" vs the {label} \"{b}\": {verdict.reason} A reviewer should confirm.",
                           field="legal_name"), trace

    if code == "NAME_LEGAL_BANK" and looks_like_company(a) and not looks_like_company(b):
        reason = (f"Bank account holder \"{b}\" appears to be an individual, not {a}. Paying a company's invoices "
                  "into a personal account is a third-party payment risk.")
    else:
        reason = f"Legal name \"{a}\" doesn't match the {label} \"{b}\". {verdict.reason}"
    return CheckResult(code, "S6", Severity.BLOCKING, reason, field="bank_holder_name" if "BANK" in code else "legal_name"), trace


async def run(ctx: RunContext) -> dict:
    pairs = name_pairs(ctx)
    results = await asyncio.gather(*(judge(ctx, *p) for p in pairs))
    out = {}
    for check, trace in results:
        ctx.add(check)
        out[check.code] = trace
    return out
