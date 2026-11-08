"""Deterministic stand-in for the LLM so tests and the offline demo run without an API key.

Documents: answers from sample_data/manifest.json (keyed by the file's SHA-256), which records
what is actually printed on each generated sample. Unknown PDFs fall back to reading the text
layer with regexes; unknown images are reported as unreadable (so a human reviews them).
"""
import asyncio
import json
import re
from functools import lru_cache
from pathlib import Path

import pymupdf

from app.config import BACKEND_DIR
from app.validators.names import looks_like_company, normalise_name

MANIFEST = BACKEND_DIR.parent / "sample_data" / "manifest.json"
FAIL_MARKER = "__FORCE_LLM_FAILURE__"  # lets tests simulate an outage


@lru_cache
def _by_sha() -> dict:
    if not MANIFEST.exists():
        return {}
    files = json.loads(MANIFEST.read_text())["files"]
    return {f["sha256"]: f["extraction"] for f in files.values()}


def reload_manifest():
    _by_sha.cache_clear()


def _empty_fields():
    return {k: {"value": None, "confidence": 0.0}
            for k in ["legal_name", "pan", "gstin", "account_holder_name", "account_number", "ifsc"]}


def _from_text_layer(pdf_bytes: bytes) -> dict:
    text = "\n".join(page.get_text() for page in pymupdf.open(stream=pdf_bytes, filetype="pdf"))
    fields = _empty_fields()
    patterns = {"gstin": r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", "ifsc": r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
                "account_number": r"\b\d{9,18}\b"}
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            fields[key] = {"value": m.group(), "confidence": 0.7}
    pan = re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", text)
    if pan:
        fields["pan"] = {"value": pan.group(), "confidence": 0.7}
    upper = text.upper()
    doc_type = ("GST_CERTIFICATE" if "GST REG" in upper or "GSTIN" in upper else
                "PAN_CARD" if "PERMANENT ACCOUNT NUMBER" in upper else
                "CANCELLED_CHEQUE" if "CANCELLED" in upper else "OTHER")
    return {"doc_type": doc_type, "doc_type_confidence": 0.7, "fields": fields,
            "contains_instructions": "IGNORE" in upper and "INSTRUCTION" in upper}


async def respond(purpose: str, data: dict) -> dict:
    await asyncio.sleep(0.05)
    if FAIL_MARKER in json.dumps(data, default=str):
        raise TimeoutError("simulated LLM outage")

    if purpose == "extract_document":
        known = _by_sha().get(data["sha256"])
        if known:
            return known
        if data["mime"] == "application/pdf":
            return _from_text_layer(data["bytes"])
        return {"doc_type": "UNREADABLE", "doc_type_confidence": 0.2, "fields": _empty_fields(),
                "contains_instructions": False}

    if purpose == "name_match":
        a, b = data["name_a"], data["name_b"]
        if looks_like_company(a) != looks_like_company(b):
            return {"verdict": "DIFFERENT_ENTITY",
                    "reason": "One name is an individual and the other is a company."}
        words_a, words_b = set(normalise_name(a).split()), set(normalise_name(b).split())
        if words_a and words_a <= words_b or words_b and words_b <= words_a:
            return {"verdict": "UNSURE", "reason": "One name contains the other; the legal form or extra words differ."}
        overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
        if overlap < 0.3:
            return {"verdict": "DIFFERENT_ENTITY", "reason": "The names share almost no words."}
        return {"verdict": "UNSURE", "reason": "The names are similar but not clearly the same entity."}

    if purpose == "draft_message":
        kind, vendor = data["kind"], data["vendor_name"]
        drafts = {
            "FIX_REQUEST": ("Action needed: a few items in your vendor registration",
                            f"Dear {vendor} team, thank you for submitting your registration. "
                            "We need the following before we can complete it:",
                            "Please use the same link to update only these items. Everything else you sent is saved."),
            "REJECTION": ("Update on your vendor registration",
                          f"Dear {vendor} team, thank you for your interest in working with us.",
                          "We are unable to proceed with this registration. If you believe this is an error, "
                          "please reply to this email."),
            "WELCOME": ("Your vendor registration is approved",
                        f"Dear {vendor} team, your registration is complete and you are now set up as an approved vendor.",
                        "Our accounts payable team will be in touch about purchase orders and invoicing."),
        }
        subject, opening, closing = drafts.get(kind, ("Update on your vendor registration", f"Dear {vendor} team,", "Regards."))
        return {"subject": subject, "opening": opening, "closing": closing}

    raise ValueError(f"no mock for {purpose}")
