"""Upload validation. We trust the bytes, not the filename or the browser's Content-Type."""
import io
import secrets
from dataclasses import dataclass

import pymupdf
from PIL import Image

MAX_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 5
MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard

SIGNATURES = {
    b"%PDF-": "application/pdf",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}
EXTENSIONS = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}


class UploadError(ValueError):
    pass


@dataclass
class CleanFile:
    data: bytes
    mime: str
    stored_name: str


def sniff_mime(data: bytes) -> str | None:
    for signature, mime in SIGNATURES.items():
        if data.startswith(signature):
            return mime
    return None


def clean_upload(data: bytes, label: str) -> CleanFile:
    if not data:
        raise UploadError(f"{label}: the file is empty.")
    if len(data) > MAX_BYTES:
        raise UploadError(f"{label}: the file is larger than 5 MB.")
    mime = sniff_mime(data)
    if mime is None:
        raise UploadError(f"{label}: only PDF, PNG or JPG files are accepted.")

    if mime == "application/pdf":
        data = _clean_pdf(data, label)
    else:
        data = _clean_image(data, mime, label)
    return CleanFile(data=data, mime=mime, stored_name=f"{secrets.token_hex(16)}.{EXTENSIONS[mime]}")


def _clean_pdf(data: bytes, label: str) -> bytes:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise UploadError(f"{label}: the PDF could not be opened.")
    if doc.needs_pass or doc.is_encrypted:
        raise UploadError(f"{label}: password-protected PDFs are not accepted.")
    if doc.page_count == 0 or doc.page_count > MAX_PDF_PAGES:
        raise UploadError(f"{label}: the PDF must have between 1 and {MAX_PDF_PAGES} pages.")
    # Rewrite the file: drops metadata, embedded JavaScript and attachments.
    doc.set_metadata({})
    for name in doc.embfile_names():
        doc.embfile_del(name)
    out = doc.tobytes(garbage=4, deflate=True, clean=True)
    doc.close()
    return out


def _clean_image(data: bytes, mime: str, label: str) -> bytes:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        image = Image.open(io.BytesIO(data))  # verify() leaves the object unusable
        image.load()
    except Exception:
        raise UploadError(f"{label}: the image could not be read.")
    # Re-encode from pixels only: strips EXIF (GPS, device) and anything appended to the file.
    out = io.BytesIO()
    if mime == "image/png":
        image.save(out, format="PNG")
    else:
        image.convert("RGB").save(out, format="JPEG", quality=90)
    return out.getvalue()
