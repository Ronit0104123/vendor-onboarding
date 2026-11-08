"""One end-to-end test per demo scenario: the same path as clicking it in the UI."""
import pytest

from tests.conftest import run_queue


def start(admin, key):
    r = admin.post(f"/api/demo/scenarios/{key}")
    assert r.status_code == 200, r.text
    run_queue()
    vendor_id = r.json()["vendor_id"]
    return vendor_id, admin.get(f"/api/vendors/{vendor_id}").json()


def codes(detail, severity, attempt=-1):
    return {c["code"] for c in detail["attempts"][attempt]["run"]["checks"] if c["severity"] == severity}


def test_happy_path_approved(admin):
    vid, d = start(admin, "happy")
    assert d["vendor"]["status"] == "APPROVED"
    assert d["in_vendor_master"]
    assert not codes(d, "BLOCKING") and not codes(d, "FIXABLE") and not codes(d, "NEEDS_REVIEW")
    name_check = next(c for c in d["attempts"][0]["run"]["checks"] if c["code"] == "NAME_LEGAL_BANK")
    assert name_check["severity"] == "PASS" and "normalisation" in name_check["reason"]
    assert [s["status"] for s in d["attempts"][0]["run"]["stages"]].count("fail") == 0
    assert any(m["kind"] == "WELCOME" for m in d["outbox"])
    assert d["portal"]["active"] is False  # link invalidated once approved


def test_e1_silent_inconsistency_rejected_with_both_reasons(admin):
    _, d = start(admin, "e1")
    assert d["vendor"]["status"] == "REJECTED"
    assert {"PAN_IN_GSTIN", "GSTIN_STATE"} <= codes(d, "BLOCKING")
    assert any(m["kind"] == "INTERNAL_ALERT" and "PAN_IN_GSTIN" in m["body"] for m in d["outbox"])
    rejection = next(m for m in d["outbox"] if m["kind"] == "REJECTION")
    assert "PAN" not in rejection["body"]  # vendor isn't told which fraud check fired


def test_e2_wrong_doc_and_missing_then_fixed(admin):
    vid, d = start(admin, "e2")
    assert d["vendor"]["status"] == "PENDING_VENDOR"
    assert codes(d, "FIXABLE") == {"DOC_WRONG_TYPE", "REQ_DOC_MISSING"}
    fix = [m for m in d["outbox"] if m["kind"] == "FIX_REQUEST"][-1]
    numbered = [line for line in fix["body"].splitlines() if line[:2] in ("1.", "2.", "3.")]
    assert len(numbered) == 2  # exactly the two items, nothing else
    assert "/portal/" in fix["body"]

    r = admin.post(f"/api/demo/scenarios/e2/resubmit/{vid}")
    assert r.status_code == 200, r.text
    run_queue()
    d = admin.get(f"/api/vendors/{vid}").json()
    assert d["vendor"]["attempt_count"] == 2
    assert d["vendor"]["status"] == "APPROVED"
    kept = {doc["slot"] for doc in d["attempts"][1]["documents"] if doc["reused_from_attempt"] == 1}
    assert kept == {"PAN_CARD"}


def test_e3_personal_bank_account_rejected(admin):
    _, d = start(admin, "e3")
    assert d["vendor"]["status"] == "REJECTED"
    assert "NAME_LEGAL_BANK" in codes(d, "BLOCKING")
    reason = next(c["reason"] for c in d["attempts"][0]["run"]["checks"] if c["code"] == "NAME_LEGAL_BANK")
    assert "individual" in reason


def test_e4_duplicate_bank_account_rejected_and_linked(admin):
    _, d = start(admin, "e4")
    assert d["vendor"]["status"] == "REJECTED"
    blocking = codes(d, "BLOCKING")
    assert "DUP_BANK_ACCOUNT" in blocking
    reason = next(c["reason"] for c in d["attempts"][0]["run"]["checks"] if c["code"] == "DUP_BANK_ACCOUNT")
    assert "Patel Industrial Supplies" in reason and "VND-" in reason


def test_e5_prompt_injection_has_no_effect(admin):
    _, d = start(admin, "e5")
    assert d["vendor"]["status"] == "REJECTED"
    assert "DOC_CONTAINS_INSTRUCTIONS" in codes(d, "WARN")
    assert "GSTIN_CHECKSUM" in codes(d, "BLOCKING")


def test_e6_wrong_tax_id_for_country(admin):
    _, d = start(admin, "e6")
    assert d["vendor"]["status"] == "PENDING_VENDOR"
    check = next(c for c in d["attempts"][0]["run"]["checks"] if c["code"] == "TAX_ID_COUNTRY")
    assert check["severity"] == "FIXABLE" and "GSTIN (India)" in check["reason"]


def test_seed_history_covers_every_status(admin):
    stats = admin.get("/api/stats").json()["by_status"]
    for status in ["APPROVED", "PENDING_VENDOR", "PENDING_INTERNAL", "REJECTED", "AUTO_CLOSED", "INVITED"]:
        assert stats[status] >= 1, status
