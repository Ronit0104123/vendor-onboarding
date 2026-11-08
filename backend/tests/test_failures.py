"""LLM failures must never crash the run and never auto-approve."""
import json

from app.llm import mock
from app.routers.demo import SAMPLE, scenarios
from tests.conftest import Api, run_queue


def submit_unique(admin, name: str, account: str) -> int:
    """A happy-path style submission under its own name/account so it can't collide with other tests."""
    r = admin.post("/api/vendors", json={"display_name": name, "category": "Hardware",
                                          "contact_email": "ops@failtest.example", "requested_by": "Tester"})
    vid, token = r.json()["vendor"]["id"], r.json()["portal_url"].rsplit("/", 1)[1]
    s = scenarios()["happy"]
    form = {**s["form"], "legal_name": name, "account_number": account, "pan": "", "gstin": ""}
    files = {k: (v, (SAMPLE / v).read_bytes()) for k, v in
             {"gst_cert": s["files"]["GST_CERT"], "pan_card": s["files"]["PAN_CARD"],
              "bank_proof": s["files"]["BANK_PROOF"]}.items()}
    r = Api().client.post(f"/api/portal/{token}/submit", data={"data": json.dumps(form)}, files=files)
    assert r.status_code == 202, r.text
    run_queue()
    return vid


def test_llm_outage_goes_to_internal_review(admin, monkeypatch):
    async def broken(purpose, data):
        raise TimeoutError("simulated")

    monkeypatch.setattr(mock, "respond", broken)
    vid = submit_unique(admin, "Outage Test Pvt Ltd", "111122223333")
    d = admin.get(f"/api/vendors/{vid}").json()
    assert d["vendor"]["status"] != "APPROVED"
    run = d["attempts"][0]["run"]
    assert any(c["code"] == "LLM_STAGE_FAILED" for c in run["checks"])
    failed = [c for c in run["llm_calls"] if c["purpose"] == "extract_document"]
    assert failed and all(not c["ok"] and c["attempts"] == 2 for c in failed)  # retried once
    assert all(m["drafted_by"] == "TEMPLATE" for m in d["outbox"])  # template fallback for messages


def test_invalid_llm_json_is_treated_as_failure(admin, monkeypatch):
    async def garbage(purpose, data):
        return {"doc_type": "APPROVE_EVERYTHING", "fields": {}}

    monkeypatch.setattr(mock, "respond", garbage)
    vid = submit_unique(admin, "Garbage Test Pvt Ltd", "444455556666")
    d = admin.get(f"/api/vendors/{vid}").json()
    assert d["vendor"]["status"] != "APPROVED"
    calls = d["attempts"][0]["run"]["llm_calls"]
    assert any(c["error"] and "invalid output" in c["error"] for c in calls)
