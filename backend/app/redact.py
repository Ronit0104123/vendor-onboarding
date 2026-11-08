"""Redaction applied to everything we log or store as LLM/stage traces. PII never reaches logs."""
import re
from typing import Any

SENSITIVE_KEYS = {"pan", "account_number", "password", "token", "api_key", "account", "pan_number"}

PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
ACCOUNT_RE = re.compile(r"\b[0-9]{9,18}\b")


def redact_text(text: str) -> str:
    # GSTINs are public (printed on every tax invoice) and are left as-is; a bare PAN is masked.
    text = PAN_RE.sub(lambda m: "•••• " + m.group()[-4:], text)
    text = ACCOUNT_RE.sub(lambda m: "•••• " + m.group()[-4:], text)
    return text


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k.lower() in SENSITIVE_KEYS and isinstance(v, str) and v:
                out[k] = "•••• " + v[-4:]
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
