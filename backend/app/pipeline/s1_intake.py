"""S1 Intake: a frozen, redacted snapshot of exactly what was submitted."""
from app.pipeline.context import RunContext
from app.redact import redact


async def run(ctx: RunContext) -> dict:
    return {
        "attempt": ctx.submission.attempt_no,
        "fields": redact({k: v for k, v in ctx.form.items() if v}),
        "documents": [
            {"slot": slot, "type": doc.mime, "size_kb": round(doc.size_bytes / 1024),
             "sha256": doc.sha256[:16] + "…", "reused_from_attempt": doc.reused_from_attempt}
            for slot, doc in ctx.documents.items()
        ],
    }
