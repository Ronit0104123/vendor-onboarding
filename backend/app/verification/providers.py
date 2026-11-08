"""External verification behind a small interface, so a real provider can be swapped in.

Real-world equivalents: a GST public-search API (GSTN via a GSP) and a penny-drop
bank account verification API. The "sandbox" provider answers from a fixture registry
of the fictional companies in /sample_data, so the demo exercises the same code path.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import BACKEND_DIR, settings

REGISTRY = BACKEND_DIR.parent / "sample_data" / "sandbox_registry.json"


@dataclass
class GstLookup:
    status: str  # ACTIVE | CANCELLED | NOT_FOUND | UNAVAILABLE
    legal_name: str | None = None
    state_code: str | None = None
    provider: str = "none"


@dataclass
class BankLookup:
    status: str  # VERIFIED | ACCOUNT_INVALID | UNAVAILABLE
    name_at_bank: str | None = None
    provider: str = "none"


@lru_cache
def _registry() -> dict:
    if not Path(REGISTRY).exists():
        return {"gstins": {}, "accounts": {}}
    return json.loads(Path(REGISTRY).read_text())


def lookup_gstin(gstin: str) -> GstLookup:
    if settings.gst_verifier != "sandbox":
        return GstLookup(status="UNAVAILABLE")
    entry = _registry()["gstins"].get(gstin)
    if entry is None:
        # A real GSTN lookup would say NOT_FOUND; the sandbox only knows the fictional demo companies.
        return GstLookup(status="UNAVAILABLE", provider="sandbox")
    return GstLookup(status=entry["status"], legal_name=entry["legal_name"],
                     state_code=gstin[:2], provider="sandbox")


def penny_drop(account_number: str, ifsc: str) -> BankLookup:
    if settings.bank_verifier != "sandbox":
        return BankLookup(status="UNAVAILABLE")
    entry = _registry()["accounts"].get(f"{ifsc}:{account_number}")
    if entry is None:
        return BankLookup(status="UNAVAILABLE", provider="sandbox")
    return BankLookup(status=entry["status"], name_at_bank=entry.get("name_at_bank"), provider="sandbox")
