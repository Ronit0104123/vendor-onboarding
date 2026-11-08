"""One-click demo scenarios. They go through exactly the same code path as a real vendor
(create request -> invite -> submit via the portal service -> queued run)."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.config import BACKEND_DIR
from app.deps import get_db
from app.models import Vendor
from app.schemas import SubmissionIn, VendorRequestIn
from app.security.sessions import Auth, current_auth, require_admin
from app.services.vendors import create_vendor_request, submit

router = APIRouter(prefix="/api/demo", tags=["demo"])
SAMPLE = BACKEND_DIR.parent / "sample_data" / "docs"


def scenarios() -> dict:
    return json.loads((SAMPLE.parent / "scenarios.json").read_text())


def files_for(spec: dict) -> dict:
    return {slot: ((SAMPLE / name).read_bytes(), Path(name).name) for slot, name in spec.items()}


def run_scenario(db, key: str, actor: str):
    s = scenarios().get(key)
    if not s:
        raise HTTPException(404, "Unknown scenario.")
    vendor, _ = create_vendor_request(db, VendorRequestIn(**s["request"]), actor)
    db.flush()
    run = submit(db, vendor, SubmissionIn(**s["form"]), files_for(s["files"]), actor=f"vendor:{vendor.id}")
    return vendor, run


@router.get("/scenarios")
def list_scenarios(auth: Auth = Depends(current_auth)):
    return [{"key": k, "title": s["title"], "description": s["description"], "expected": s["expected"],
             "has_fix": "fix" in s} for k, s in scenarios().items() if not s.get("seed_only")]


@router.post("/scenarios/{key}")
def start_scenario(key: str, auth: Auth = Depends(require_admin), db: DBSession = Depends(get_db)):
    vendor, run = run_scenario(db, key, auth.actor)
    return {"vendor_id": vendor.id, "run_id": run.id}


@router.post("/scenarios/{key}/resubmit/{vendor_id}")
def resubmit_scenario(key: str, vendor_id: int, auth: Auth = Depends(require_admin), db: DBSession = Depends(get_db)):
    s = scenarios().get(key)
    vendor = db.get(Vendor, vendor_id)
    if not s or "fix" not in s or not vendor:
        raise HTTPException(404, "Nothing to resubmit for this scenario.")
    form = SubmissionIn(**{**s["form"], **s["fix"].get("form", {})})
    run = submit(db, vendor, form, files_for(s["fix"].get("files", {})), actor=f"vendor:{vendor.id}")
    return {"vendor_id": vendor.id, "run_id": run.id}
