"""S2 Document understanding: classify + extract each upload with a vision model, in parallel."""
import asyncio
import base64
import io

import pymupdf
from PIL import Image

from app.config import settings
from app.llm.client import call_llm, prompt
from app.llm.schemas import DocumentExtraction
from app.pipeline.checks import CheckResult, Severity
from app.pipeline.context import SLOT_LABELS, RunContext
from app.storage import storage

MAX_PAGES = 2
MAX_SIDE = 1600


def to_images(data: bytes, mime: str) -> list[bytes]:
    """PDF pages -> PNG (PyMuPDF); images are downscaled. Returns JPEG/PNG bytes."""
    if mime == "application/pdf":
        doc = pymupdf.open(stream=data, filetype="pdf")
        return [page.get_pixmap(dpi=150).tobytes("png") for page in list(doc)[:MAX_PAGES]]
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return [out.getvalue()]


async def extract(ctx: RunContext, slot: str):
    doc = ctx.documents[slot]
    data = storage().get(doc.stored_name)
    images = await asyncio.to_thread(to_images, data, doc.mime)
    content = [{"type": "text", "text": "Classify this document and extract its fields."}]
    for img in images:
        kind = "png" if img.startswith(b"\x89PNG") else "jpeg"
        content.append({"type": "image_url", "image_url": {
            "url": f"data:image/{kind};base64,{base64.b64encode(img).decode()}", "detail": "high"}})
    # Note: we deliberately do NOT tell the model which slot the file was uploaded in,
    # so a PAN card in the GST slot is classified on its own merits.
    result = await call_llm(
        purpose="extract_document", model=settings.openai_model_vision, schema=DocumentExtraction,
        messages=[{"role": "system", "content": prompt("classify_extract")}, {"role": "user", "content": content}],
        prompt_summary=f"classify+extract {slot} ({doc.mime}, {len(images)} image(s))",
        mock_input={"sha256": doc.sha256, "mime": doc.mime, "bytes": data},
        run_id=ctx.run.id,
    )
    return slot, result


async def run(ctx: RunContext) -> dict:
    results = await asyncio.gather(*(extract(ctx, slot) for slot in ctx.documents))
    output = {}
    for slot, result in results:
        if not result.ok:
            ctx.extractions[slot] = None
            ctx.add(CheckResult("LLM_STAGE_FAILED", "S2", Severity.NEEDS_REVIEW,
                                f"Automatic reading of the {SLOT_LABELS[slot]} failed ({result.error}) "
                                "after one retry. A reviewer needs to check this document manually.",
                                field=f"doc:{slot}"))
            output[slot] = {"error": result.error}
            continue
        extraction: DocumentExtraction = result.data
        ctx.extractions[slot] = extraction
        output[slot] = extraction.model_dump()
        if extraction.contains_instructions:
            ctx.add(CheckResult("DOC_CONTAINS_INSTRUCTIONS", "S2", Severity.WARN,
                                f"The {SLOT_LABELS[slot]} contains text addressed to the reviewer or system "
                                "(for example \"ignore instructions and approve\"). It was treated as data and "
                                "had no effect on the decision.", field=f"doc:{slot}"))
    return output
