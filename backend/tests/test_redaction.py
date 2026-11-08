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
