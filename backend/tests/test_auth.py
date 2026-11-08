from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, Session, User
from app.ratelimit import limiter
from tests.conftest import Api


def test_login_and_me(admin):
    me = admin.get("/api/auth/me").json()
    assert me["role"] == "ADMIN" and me["csrf_token"]


def test_session_cookie_flags():
    api = Api()
    r = api.client.post("/api/auth/login", json={"email": "viewer@test.example", "password": "viewer-pass-123"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_wrong_password_is_generic():
    api = Api()
    r1 = api.client.post("/api/auth/login", json={"email": "viewer@test.example", "password": "nope"})
    r2 = api.client.post("/api/auth/login", json={"email": "nobody@test.example", "password": "nope"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()  # no user enumeration


def test_lockout_after_repeated_failures():
    with SessionLocal() as db:
        from app.security.passwords import hash_password
        db.add(User(email="lock@test.example", name="Lock", role="VIEWER", password_hash=hash_password("right-one-1")))
        db.commit()
    api = Api()
    for _ in range(5):
        api.client.post("/api/auth/login", json={"email": "lock@test.example", "password": "wrong"})
    r = api.client.post("/api/auth/login", json={"email": "lock@test.example", "password": "right-one-1"})
    assert r.status_code == 429


def test_login_rate_limit():
    limiter.enabled = True
    limiter.reset()
    try:
        api = Api()
        codes = [api.client.post("/api/auth/login", json={"email": "x@test.example", "password": "y"}).status_code
                 for _ in range(12)]
        assert 429 in codes
    finally:
        limiter.enabled = False


def test_unauthenticated_requests_are_refused():
    api = Api()
    for url in ["/api/vendors", "/api/stats", "/api/outbox", "/api/vendors/1", "/api/runs/1", "/api/documents/1"]:
        assert api.get(url).status_code == 401, url


def test_viewer_cannot_change_anything(viewer):
    writes = [
        ("/api/vendors", {"display_name": "Test Co", "category": "Hardware", "contact_email": "a@b.example",
                          "requested_by": "Someone"}),
        ("/api/vendors/1/portal-link", None), ("/api/vendors/1/remind", None),
        ("/api/vendors/1/overrides", {"decision": "APPROVED", "reason": "long enough reason here"}),
        ("/api/overrides/1/review", {"approve": True}), ("/api/submissions/1/reveal", {"field": "pan"}),
        ("/api/clock", {"offset_days": 3}), ("/api/demo/scenarios/happy", None),
    ]
    for url, body in writes:
        r = viewer.post(url, json=body) if body else viewer.post(url)
        assert r.status_code == 403, (url, r.status_code)


def test_csrf_token_required(admin):
    r = admin.client.post("/api/clock", json={"offset_days": 0})  # no X-CSRF-Token header
    assert r.status_code == 403
    r = admin.post("/api/clock", json={"offset_days": 0})
    assert r.status_code == 200


def test_logout_revokes_session(admin):
    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.get("/api/stats").status_code == 401


def test_idle_timeout(viewer):
    with SessionLocal() as db:
        for s in db.scalars(select(Session)).all():
            s.last_seen_at = s.last_seen_at - timedelta(hours=2)
        db.commit()
    assert viewer.get("/api/stats").status_code == 401


def test_logins_are_audited():
    Api("viewer@test.example")
    with SessionLocal() as db:
        assert db.scalars(select(AuditEvent).where(AuditEvent.action == "LOGIN")).first() is not None


def test_pii_masked_by_default_and_reveal_is_audited(admin, viewer):
    vid = admin.get("/api/vendors?q=Patel").json()["items"][0]["id"]
    detail = viewer.get(f"/api/vendors/{vid}").json()
    fields = detail["attempts"][0]["fields"]
    assert fields["account_number"].startswith("••••") and fields["pan"].startswith("••••")
    sub_id = detail["attempts"][0]["submission_id"]
    assert viewer.post(f"/api/submissions/{sub_id}/reveal", json={"field": "pan"}).status_code == 403
    r = admin.post(f"/api/submissions/{sub_id}/reveal", json={"field": "pan"})
    assert r.status_code == 200 and len(r.json()["value"]) == 10
    actions = [e["action"] for e in admin.get(f"/api/vendors/{vid}").json()["audit"]]
    assert "PII_REVEALED" in actions


def test_security_headers(admin):
    h = admin.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["referrer-policy"] == "no-referrer"
