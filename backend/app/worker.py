"""Durable job queue on the runs table. Survives restarts: a run is only DONE when the pipeline finished.

Claiming is a single conditional UPDATE, so several workers (or web instances) never run the same job.
Run standalone with `python -m app.worker`, or inside the web process (RUN_WORKER=true).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.audit import audit
from app.db import SessionLocal
from app.models import Check, Run
from app.pipeline.runner import run_pipeline
from app.timeutil import utcnow

log = logging.getLogger(__name__)
LEASE = timedelta(minutes=10)  # a RUNNING job older than this is assumed to belong to a dead worker
MAX_TRIES = 2


def _now():
    return utcnow()


def claim_next() -> int | None:
    with SessionLocal() as db:
        stale = _now() - LEASE
        candidate = db.scalars(
            select(Run.id).where((Run.status == "QUEUED") | ((Run.status == "RUNNING") & (Run.claimed_at < stale)))
            .order_by(Run.created_at).limit(1)).first()
        if candidate is None:
            return None
        claimed = db.execute(
            update(Run).where(Run.id == candidate, (Run.status == "QUEUED") | (Run.claimed_at < stale))
            .values(status="RUNNING", claimed_at=_now(), tries=Run.tries + 1)).rowcount
        db.commit()
        return candidate if claimed == 1 else None


def give_up(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        run.status, run.decision = "DONE", "PENDING_INTERNAL"
        run.decision_summary = "Pipeline failed repeatedly; needs manual review"
        run.finished_at = _now()
        run.submission.vendor.status = "PENDING_INTERNAL"
        db.add(Check(run_id=run_id, stage="S8", code="PIPELINE_ERROR", severity="NEEDS_REVIEW",
                     reason="Automatic processing failed twice. A reviewer must complete this case."))
        audit(db, "system", "RUN_FAILED", run.submission.vendor_id, run_id=run_id)
        db.commit()


async def process(run_id: int) -> None:
    try:
        await run_pipeline(run_id)
    except Exception:
        log.exception("run %s crashed", run_id)
        with SessionLocal() as db:
            run = db.get(Run, run_id)
            if run.tries >= MAX_TRIES:
                db.close()
                give_up(run_id)
            else:
                run.status = "QUEUED"
                db.commit()


async def drain() -> int:
    """Process everything queued (used by tests and the seed script)."""
    n = 0
    while (run_id := claim_next()) is not None:
        await process(run_id)
        n += 1
    return n


async def worker_loop(stop: asyncio.Event, poll_seconds: float = 0.5) -> None:
    log.info("worker started")
    while not stop.is_set():
        try:
            run_id = claim_next()
            if run_id is not None:
                await process(run_id)
                continue
        except Exception:
            log.exception("worker loop error")
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop(asyncio.Event()))
