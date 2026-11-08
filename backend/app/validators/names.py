"""Name normalisation, so 'Sharma Hardware Pvt. Ltd.' == 'SHARMA HARDWARE PRIVATE LIMITED'.

Only when two names still differ after this do we ask the LLM for a judgment.
"""
import re

# Applied after upper-casing and punctuation removal. Order matters: longest first.
SUFFIX_EQUIVALENTS = [
    (r"\bPVT\s+LTD\b", "PRIVATE LIMITED"),
    (r"\bPRIVATE\s+LTD\b", "PRIVATE LIMITED"),
    (r"\bPVT\s+LIMITED\b", "PRIVATE LIMITED"),
    (r"\bPVT\b", "PRIVATE"),
    (r"\bLTD\b", "LIMITED"),
    (r"\bCO\b", "COMPANY"),
    (r"\bCORP\b", "CORPORATION"),
    (r"\bMFG\b", "MANUFACTURING"),
    (r"\bINTL\b", "INTERNATIONAL"),
]

COMPANY_WORDS = {"PRIVATE", "LIMITED", "LLP", "COMPANY", "CORPORATION", "INDUSTRIES",
                 "ENTERPRISES", "TRADERS", "LOGISTICS", "HARDWARE", "INC", "LLC", "PLC"}


def normalise_name(name: str) -> str:
    text = (name or "").upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"^\s*M\s*/\s*S\.?\s+", "", text)  # "M/s. Sharma Hardware" -> "Sharma Hardware"
    text = re.sub(r"[^A-Z0-9 ]", " ", text)           # drop punctuation
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, replacement in SUFFIX_EQUIVALENTS:
        text = re.sub(pattern, replacement, text)
    return text


def names_match(a: str, b: str) -> bool:
    return normalise_name(a) != "" and normalise_name(a) == normalise_name(b)


def looks_like_company(name: str) -> bool:
    """Cheap hint only, never a decision on its own."""
    return bool(set(normalise_name(name).split()) & COMPANY_WORDS)
