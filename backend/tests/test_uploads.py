import io
import json

import pymupdf
import pytest
from PIL import Image

from app.uploads import MAX_BYTES, UploadError, clean_upload
from tests.conftest import Api


def png_with_exif() -> bytes:
    img = Image.new("RGB", (40, 40), "white")
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneMaker"  # Make
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def small_pdf(password: str | None = None) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello")
    if password:
        return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    return doc.tobytes()


def test_accepts_pdf_and_gives_random_name():
    a, b = clean_upload(small_pdf(), "x"), clean_upload(small_pdf(), "x")
    assert a.mime == "application/pdf" and a.stored_name != b.stored_name and a.stored_name.endswith(".pdf")


def test_rejects_html_named_pdf():
    with pytest.raises(UploadError):
        clean_upload(b"<html><script>alert(1)</script></html>", "GST certificate")


def test_rejects_executable():
    with pytest.raises(UploadError):
        clean_upload(b"MZ\x90\x00" + b"\x00" * 100, "PAN card")


def test_rejects_oversize():
    with pytest.raises(UploadError, match="5 MB"):
        clean_upload(b"%PDF-" + b"0" * MAX_BYTES, "x")


def test_rejects_encrypted_pdf():
    with pytest.raises(UploadError, match="password"):
        clean_upload(small_pdf("secret"), "x")


def test_rejects_fake_image_with_valid_magic():
    with pytest.raises(UploadError):
        clean_upload(b"\x89PNG\r\n\x1a\n" + b"garbage" * 20, "x")


def test_strips_exif():
    original = png_with_exif()
    assert b"SecretPhoneMaker" in original
    cleaned = clean_upload(original, "x")
    assert b"SecretPhoneMaker" not in cleaned.data
    assert not Image.open(io.BytesIO(cleaned.data)).getexif()


def test_portal_rejects_spoofed_upload(admin):
    r = admin.post("/api/vendors", json={"display_name": "Upload Test Co", "category": "Hardware",
                                          "contact_email": "u@uploadtest.example", "requested_by": "Tester"})
    token = r.json()["portal_url"].rsplit("/", 1)[1]
    api = Api()
    r = api.client.post(f"/api/portal/{token}/submit", data={"data": json.dumps({"legal_name": "Upload Test Co"})},
                        files={"gst_cert": ("gst.pdf", b"<svg onload=alert(1)>", "application/pdf")})
    assert r.status_code == 422
    assert "PDF, PNG or JPG" in r.json()["detail"]["message"]


def test_portal_rejects_bad_characters(admin):
    r = admin.post("/api/vendors", json={"display_name": "Chars Test Co", "category": "Hardware",
                                          "contact_email": "c@charstest.example", "requested_by": "Tester"})
    token = r.json()["portal_url"].rsplit("/", 1)[1]
    r = Api().client.post(f"/api/portal/{token}/submit",
                          data={"data": json.dumps({"legal_name": "<script>alert(1)</script>"})})
    assert r.status_code == 422
