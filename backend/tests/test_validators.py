import pytest

from app.validators import india, names, tax_ids


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    body = f"{state}{pan}{entity}Z"
    return body + india.gstin_check_char(body)


# ---------- PAN ----------
@pytest.mark.parametrize("pan", ["AABCS1234Q", "ZZZPK9999A"])
def test_pan_valid(pan):
    assert india.is_valid_pan(pan)


@pytest.mark.parametrize("pan", ["", "AABCS1234", "AABC51234Q", "aabcs1234q", "AABCS1234QQ", "12345ABCDE"])
def test_pan_invalid(pan):
    assert not india.is_valid_pan(pan)


# ---------- GSTIN ----------
def test_gstin_checksum_independent_reference():
    """Re-implement the published algorithm a second way and compare on many inputs."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def reference(first14):
        s = 0
        for i, ch in enumerate(first14):
            q, r = divmod(alphabet.index(ch) * (2 if i % 2 else 1), 36)
            s += q + r
        return alphabet[-s % 36]

    for state in ["07", "27", "29", "33"]:
        for pan in ["AABCS1234Q", "AAFCR5678M", "BQXPK0001Z"]:
            first14 = f"{state}{pan}1Z"
            assert india.gstin_check_char(first14) == reference(first14)


def test_gstin_valid_with_checksum():
    gstin = make_gstin("07", "AABCS1234Q")
    assert india.is_valid_gstin_format(gstin)
    assert india.has_valid_gstin_checksum(gstin)


def test_gstin_single_char_change_breaks_checksum():
    gstin = make_gstin("07", "AABCS1234Q")
    wrong_last = gstin[:14] + ("0" if gstin[14] != "0" else "1")
    assert india.is_valid_gstin_format(wrong_last)  # still looks right...
    assert not india.has_valid_gstin_checksum(wrong_last)  # ...but is not a real GSTIN


@pytest.mark.parametrize("gstin", ["", "07AABCS1234Q1Z", "07AABCS1234Q1X5", "7AABCS1234Q1Z55", "07aabcs1234q1z5"])
def test_gstin_bad_format(gstin):
    assert not india.is_valid_gstin_format(gstin)
    assert not india.has_valid_gstin_checksum(gstin)


def test_pan_and_state_inside_gstin():
    gstin = make_gstin("27", "AABCS1234Q")
    assert india.pan_inside_gstin(gstin) == "AABCS1234Q"
    assert india.state_code_of_gstin(gstin) == "27"


@pytest.mark.parametrize("state,code", [("Delhi", "07"), ("maharashtra", "27"), (" Karnataka ", "29"), ("Tamil Nadu", "33")])
def test_state_codes(state, code):
    assert india.state_code_for(state) == code


def test_unknown_state():
    assert india.state_code_for("Atlantis") is None


# ---------- IFSC / PIN ----------
@pytest.mark.parametrize("ifsc,ok", [("NCBA0001234", True), ("NCBA0ABC123", True), ("NCBA1001234", False),
                                     ("NCB00001234", False), ("NCBA000123", False), ("ncba0001234", False)])
def test_ifsc(ifsc, ok):
    assert india.is_valid_ifsc(ifsc) is ok


@pytest.mark.parametrize("pin,ok", [("110020", True), ("400001", True), ("010020", False), ("11002", False), ("11002A", False)])
def test_pin(pin, ok):
    assert india.is_valid_pin(pin) is ok


# ---------- Country rules ----------
def test_country_tax_ids():
    assert tax_ids.is_valid_tax_id("US", "EIN", "12-3456789")
    assert not tax_ids.is_valid_tax_id("US", "EIN", "123456789")
    assert tax_ids.is_valid_tax_id("GB", "VAT", "GB123456789")
    assert not tax_ids.is_valid_tax_id("GB", "VAT", "123456789")
    assert not tax_ids.is_valid_tax_id("GB", "EIN", "12-3456789")  # wrong id type for country


def test_wrong_country_hint():
    gstin = make_gstin("07", "AABCS1234Q")
    assert not tax_ids.is_valid_tax_id("GB", "VAT", gstin)
    assert tax_ids.which_country_matches(gstin) == ["GSTIN (India)"]


def test_postal_and_bank_codes_by_country():
    assert tax_ids.is_valid_postal_code("US", "94107")
    assert tax_ids.is_valid_postal_code("GB", "EC1A 1BB")
    assert not tax_ids.is_valid_postal_code("IN", "94107")
    assert tax_ids.is_valid_bank_code("GB", "20-00-00")
    assert not tax_ids.is_valid_bank_code("US", "20-00-00")


def test_supported_countries():
    assert all(tax_ids.is_supported_country(c) for c in ["IN", "US", "GB"])
    assert not tax_ids.is_supported_country("FR")


# ---------- Name normalisation ----------
@pytest.mark.parametrize("a,b", [
    ("Sharma Hardware Pvt Ltd", "SHARMA HARDWARE PRIVATE LIMITED"),
    ("Sharma Hardware Pvt. Ltd.", "Sharma Hardware Private Ltd"),
    ("M/s. Sharma Hardware Pvt Ltd", "Sharma Hardware Private Limited"),
    ("Gupta & Sons Traders", "GUPTA AND SONS TRADERS"),
    ("Mehta  Logistics   LLP", "mehta logistics llp"),
    ("Rao Steel Co.", "Rao Steel Company"),
])
def test_names_match_after_normalisation(a, b):
    assert names.names_match(a, b)


@pytest.mark.parametrize("a,b", [
    ("Sharma Hardware Pvt Ltd", "Rakesh Kumar"),
    ("Sharma Hardware Pvt Ltd", "Sharma Hardwares Pvt Ltd"),  # close, but left for the LLM / human
    ("Sharma Hardware Pvt Ltd", "Sharma Hardware LLP"),       # different legal form
    ("", ""),
])
def test_names_do_not_match(a, b):
    assert not names.names_match(a, b)


def test_looks_like_company():
    assert names.looks_like_company("Sharma Hardware Pvt Ltd")
    assert not names.looks_like_company("Rakesh Kumar")
