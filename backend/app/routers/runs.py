import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session as DBSession

from app.db import SessionLocal
from app.deps import get_db
from app.models import Document, Run
from app.security.sessions import Auth, current_auth
from app.audit import audit
from app.storage import storage
from app.views import run_view

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs/{run_id}")
def get_run(run_id: int, auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found.")
    return run_view(db, run)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: int, request: Request, auth: Auth = Depends(current_auth)):
    """Server-Sent Events. Reads stage rows from the database, so it works no matter which
    process/worker is executing the run, and a reconnect simply resumes from the current state."""
    with SessionLocal() as db:
        if not db.get(Run, run_id):
            raise HTTPException(404, "Run not found.")

    async def stream():
        last = None
        idle = 0
        while not await request.is_disconnected():
            with SessionLocal() as db:
                run = db.get(Run, run_id)
                snapshot = run_view(db, run, include_llm=False)
            payload = json.dumps(snapshot, default=str)
            if payload != last:
                last, idle = payload, 0
                yield f"event: run\ndata: {payload}\n\n"
                if snapshot["status"] == "DONE":
                    yield "event: done\ndata: {}\n\n"
                    return
            else:
                idle += 1
                if idle % 30 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.3)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/documents/{document_id}")
def download_document(document_id: int, auth: Auth = Depends(current_auth), db: DBSession = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    data = storage().get(doc.stored_name)
    audit(db, auth.actor, "DOCUMENT_DOWNLOADED", doc.submission.vendor_id, document=doc.id, slot=doc.slot)
    db.commit()
    ext = doc.stored_name.rsplit(".", 1)[-1]
    filename = f"VND-{doc.submission.vendor_id:04d}-attempt{doc.submission.attempt_no}-{doc.slot.lower()}.{ext}"
    return Response(data, media_type=doc.mime, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; sandbox"})
