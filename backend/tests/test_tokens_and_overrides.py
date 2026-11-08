from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import PortalToken, Vendor
from app.portal_links import issue_token
from app.timeutil import utcnow
from tests.conftest import Api, run_queue


def new_vendor(admin, name="Token Test Traders"):
    r = admin.post("/api/vendors", json={"display_name": name, "category": "Hardware",
                                          "contact_email": "t@tokentest.example", "requested_by": "Tester"})
    assert r.status_code == 201, r.text
    return r.json()["vendor"]["id"], r.json()["portal_url"].rsplit("/", 1)[1]


def test_token_is_random_hashed_and_scoped(admin):
    vid_a, token_a = new_vendor(admin, "Alpha Test Co")
    vid_b, token_b = new_vendor(admin, "Beta Test Co")
    assert len(token_a) >= 43  # 32 random bytes, base64url
    with SessionLocal() as db:
        stored = db.scalars(select(PortalToken).where(PortalToken.vendor_id == vid_a)).first()
        assert stored.token_hash != token_a and token_a not in stored.token_enc
    public = Api()
    assert public.get(f"/api/portal/{token_a}").json()["company"] == "Alpha Test Co"
    assert public.get(f"/api/portal/{token_b}").json()["company"] == "Beta Test Co"
    assert public.get(f"/api/portal/{token_a[:-2]}xx").status_code == 404
    assert public.get("/api/portal/not-a-real-token").status_code == 404


def test_expired_token_is_refused(admin):
    vid, token = new_vendor(admin, "Expiry Test Co")
    with SessionLocal() as db:
        t = db.scalars(select(PortalToken).where(PortalToken.vendor_id == vid)).first()
        t.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert Api().get(f"/api/portal/{token}").status_code == 404


def test_reissued_token_revokes_old(admin):
    vid, old = new_vendor(admin, "Reissue Test Co")
    with SessionLocal() as db:
        issue_token(db, vid)
        db.commit()
    assert Api().get(f"/api/portal/{old}").status_code == 404


def test_token_invalidated_after_decision(admin):
    r = admin.post("/api/demo/scenarios/e3")
    vid = r.json()["vendor_id"]
    with SessionLocal() as db:
        assert db.scalars(select(PortalToken).where(PortalToken.vendor_id == vid,
                                                    PortalToken.revoked_at.is_(None))).first()
    run_queue()
    with SessionLocal() as db:
        assert not db.scalars(select(PortalToken).where(PortalToken.vendor_id == vid,
                                                        PortalToken.revoked_at.is_(None))).first()


def test_maker_checker_override(admin, checker):
    with SessionLocal() as db:
        vid = db.scalars(select(Vendor).where(Vendor.status == "PENDING_INTERNAL")).first().id
    assert admin.post(f"/api/vendors/{vid}/overrides", json={"decision": "APPROVED", "reason": "short"}).status_code == 422
    r = admin.post(f"/api/vendors/{vid}/overrides",
                   json={"decision": "APPROVED", "reason": "Confirmed name change with GST portal printout on file."})
    assert r.status_code == 201
    oid = r.json()["id"]
    assert admin.get(f"/api/vendors/{vid}").json()["vendor"]["status"] == "PENDING_INTERNAL"  # not applied yet
    assert admin.post(f"/api/overrides/{oid}/review", json={"approve": True}).status_code == 403  # own request
    assert checker.post(f"/api/overrides/{oid}/review", json={"approve": True, "note": "Checked"}).status_code == 200
    d = admin.get(f"/api/vendors/{vid}").json()
    assert d["vendor"]["status"] == "APPROVED" and d["in_vendor_master"]
    actions = [e["action"] for e in d["audit"]]
    assert "OVERRIDE_REQUESTED" in actions and "OVERRIDE_APPLIED" in actions


def test_override_only_for_internal_review(admin):
    vid = admin.get("/api/vendors?status=REJECTED").json()["items"][0]["id"]
    r = admin.post(f"/api/vendors/{vid}/overrides", json={"decision": "APPROVED", "reason": "Trying to bypass a rejection"})
    assert r.status_code == 409


def test_reminder_flag_with_simulated_clock(admin):
    admin.post("/api/clock", json={"offset_days": 0})
    lakshmi = admin.get("/api/vendors?q=Lakshmi").json()["items"][0]
    admin.post("/api/clock", json={"offset_days": 30})
    assert admin.get("/api/vendors?q=Lakshmi").json()["items"][0]["reminder_due"] is True
    assert admin.post(f"/api/vendors/{lakshmi['id']}/remind").status_code == 200
    admin.post("/api/clock", json={"offset_days": 0})
