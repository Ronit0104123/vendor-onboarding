"""S8 Decision: wraps the pure decision engine."""
from app.config import settings
from app.pipeline.context import RunContext
from app.pipeline.decision import decide


async def run(ctx: RunContext) -> dict:
    ctx.decision = decide(ctx.checks, ctx.submission.attempt_no, settings.max_attempts)
    counts = {}
    for c in ctx.checks:
        counts[c.severity.value] = counts.get(c.severity.value, 0) + 1
    return {
        "status": ctx.decision.status.value,
        "summary": ctx.decision.summary,
        "because": [f"{c.code}: {c.reason}" for c in ctx.decision.deciding_checks],
        "check_counts": counts,
        "rule": "BLOCKING → REJECTED; else FIXABLE → PENDING (vendor); else NEEDS_REVIEW → PENDING (internal); else APPROVED",
    }
