"""S4 Format validation. Deterministic code only."""
import re

from app.pipeline.checks import CheckResult, Severity
from app.pipeline.context import RunContext
from app.validators import india
from app.validators.rules import countries
from app.validators.tax_ids import (is_supported_country, is_valid_bank_code, is_valid_postal_code,
                                    is_valid_tax_id, tax_id_rules, which_country_matches)


def _ok(code: str, reason: str, field: str) -> CheckResult:
    return CheckResult(code, "S4", Severity.PASS, reason, field=field)


def _fix(code: str, reason: str, field: str, ask: str) -> CheckResult:
    return CheckResult(code, "S4", Severity.FIXABLE, reason, field=field, vendor_message=ask)


async def run(ctx: RunContext) -> dict:
    f, country = ctx.form, ctx.form.get("country")
    if not is_supported_country(country or ""):
        return {"skipped": "unsupported country"}
    rules = countries()[country]
    results = {}

    def check(code, field, value, valid, reason_bad, ask, reason_ok=None):
        if not value:
            return  # S3 already reported it missing
        result = _ok(code, reason_ok or f"{field} format is valid.", field) if valid else _fix(code, reason_bad, field, ask)
        results[code] = result.severity.value
        ctx.add(result)

    if country == "IN":
        pan, gstin = f.get("pan"), f.get("gstin")
        check("PAN_FORMAT", "pan", pan, india.is_valid_pan(pan or ""),
              "PAN is not in the format AAAAA9999A.", "Check your PAN: it should be 10 characters, like AABCS1234Q.",
              "PAN format is valid.")
        gst_ok = india.is_valid_gstin_format(gstin or "")
        check("GSTIN_FORMAT", "gstin", gstin, gst_ok,
              "GSTIN is not in the 15-character GSTIN format.",
              "Check your GSTIN: it should be 15 characters, like 07AABCS1234Q1Z5.", "GSTIN format is valid.")
        if gstin and gst_ok:
            valid = india.has_valid_gstin_checksum(gstin)
            result = (_ok("GSTIN_CHECKSUM", "GSTIN check digit is correct.", "gstin") if valid else
                      CheckResult("GSTIN_CHECKSUM", "S4", Severity.BLOCKING,
                                  f"GSTIN {gstin} has the right format but an invalid check digit "
                                  f"(expected '{india.gstin_check_char(gstin[:14])}'). This is not a GSTIN the "
                                  "GST network would have issued.", field="gstin"))
            results["GSTIN_CHECKSUM"] = result.severity.value
            ctx.add(result)
        state = f.get("state")
        if state:
            known = india.state_code_for(state) is not None
            check("STATE_KNOWN", "state", state, known, f"'{state}' is not a recognised Indian state or UT.",
                  "Select your state from the list.", "State recognised.")
    else:
        tax_id = f.get("tax_id")
        if tax_id:
            id_type, rule = next(iter(tax_id_rules(country).items()))
            valid = is_valid_tax_id(country, id_type, tax_id)
            hint = ""
            if not valid:
                elsewhere = which_country_matches(tax_id)
                if elsewhere:
                    hint = f" It matches the format of a {elsewhere[0]}, but the country selected is {rules['name']}."
            check("TAX_ID_COUNTRY", "tax_id", tax_id, valid,
                  f"{rule['label']} '{tax_id}' is not valid for {rules['name']}.{hint}",
                  f"Enter a valid {rules['name']} {rule['label']} (for example {rule['example']}), "
                  "or correct the country if you are registered elsewhere.",
                  f"{rule['label']} format is valid for {rules['name']}.")
        if f.get("pan") or f.get("gstin"):
            ctx.add(CheckResult("TAX_ID_COUNTRY", "S4", Severity.FIXABLE,
                                f"Indian PAN/GSTIN entered, but the country selected is {rules['name']}.",
                                field="country", vendor_message="Check the country you selected: you entered an Indian PAN or GSTIN."))

    postal = f.get("postal_code")
    check("POSTAL_FORMAT", "postal_code", postal, is_valid_postal_code(country, postal or ""),
          f"{rules['postal_code']['label']} '{postal}' is not valid for {rules['name']}.",
          f"Enter a valid {rules['postal_code']['label']} (for example {rules['postal_code']['example']}).")
    bank_code = f.get("bank_code")
    check("BANK_CODE_FORMAT", "bank_code", bank_code, is_valid_bank_code(country, bank_code or ""),
          f"{rules['bank_code']['label']} '{bank_code}' is not in the expected format.",
          f"Enter a valid {rules['bank_code']['label']} (for example {rules['bank_code']['example']}).")
    account = f.get("account_number")
    check("ACCOUNT_FORMAT", "account_number", account, bool(re.fullmatch(r"[0-9]{6,18}", account or "")),
          "Bank account number should be 6 to 18 digits.", "Check your bank account number: digits only.")
    return results
