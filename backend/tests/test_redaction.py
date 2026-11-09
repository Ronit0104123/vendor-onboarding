from app.redact import redact, redact_text


def test_redacts_pan_and_account_but_keeps_gstin():
    text = "PAN AAHCS4821K account 50200041887312 GSTIN 07AAHCS4821K1Z3"
    out = redact_text(text)
    assert "AAHCS4821K account" not in out
    assert "50200041887312" not in out and "•••• 7312" in out
    assert "07AAHCS4821K1Z3" in out


def test_redacts_sensitive_keys():
    out = redact({"pan": "AAHCS4821K", "account_number": "50200041887312", "legal_name": "Sharma Hardware"})
    assert out == {"pan": "•••• 821K", "account_number": "•••• 7312", "legal_name": "Sharma Hardware"}


def test_demo_addresses_are_never_emailed():
    from app.emailer import deliverable
    assert not deliverable("accounts@sharmahardware.example")
    assert not deliverable("x@foo.test")
    assert deliverable("someone@realcompany.in")


def test_redirect_sends_demo_mail_to_one_inbox(monkeypatch):
    from app import emailer
    from app.db import SessionLocal
    sent = []
    monkeypatch.setattr(emailer.settings, "email_redirect_to", "me@inbox.test.in")
    monkeypatch.setattr(emailer.settings, "resend_api_key", "k")
    monkeypatch.setattr(emailer.settings, "smtp_user", "")
    monkeypatch.setattr(emailer.settings, "brevo_api_key", "")
    monkeypatch.setattr(emailer, "_send_resend", lambda to, subject, body: sent.append((to, subject)))
    with SessionLocal() as db:
        msg = emailer.send_message(db, vendor_id=1, kind="INVITE", to="accounts@x.example", subject="Hi", body="b")
        db.rollback()
    assert sent == [("me@inbox.test.in", "[for accounts@x.example] Hi")]
    assert msg.to_address == "accounts@x.example" and msg.sent_via == "RESEND"
