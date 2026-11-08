"""Creates demo users and realistic history by pushing the seed cases through the REAL pipeline
(with the offline mock LLM, so seeding is free and deterministic), at backdated times.

    python -m app.seed            # idempotent: skips what already exists
    python -m app.seed --reset    # wipe and recreate (SQLite file or all Postgres tables)
"""
import asyncio
import sys
from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.migrate import upgrade
from app.models import User, Vendor
from app.routers.demo import files_for, scenarios
from app.schemas import SubmissionIn, VendorRequestIn
from app.security.passwords import hash_password
from app.services.vendors import create_vendor_request, submit
from app.timeutil import pin, utcnow
from app.worker import drain


def seed_users(db) -> None:
    people = [
        (settings.demo_admin_email, settings.demo_admin_password, "Priya Nair", "ADMIN"),
        (settings.demo_checker_email, settings.demo_checker_password, "Arjun Mehta", "ADMIN"),
        (settings.demo_viewer_email, settings.demo_viewer_password, "Kavita Rao", "VIEWER"),
    ]
    for email, password, name, role in people:
        if not email or not password:
            print(f"skipping {name}: set DEMO_*_EMAIL / DEMO_*_PASSWORD in .env")
            continue
        if db.scalars(select(User).where(User.email == email.lower())).first():
            continue
        db.add(User(email=email.lower(), name=name, role=role, password_hash=hash_password(password)))
        print(f"created {role.lower()} {email}")
    db.commit()


async def seed_history() -> None:
    real_mode, real_delay = settings.llm_mode, settings.demo_stage_delay_ms
    settings.llm_mode, settings.demo_stage_delay_ms = "mock", 0
    try:
        with SessionLocal() as db:
            if db.scalars(select(Vendor).where(Vendor.is_seed)).first():
                print("history already seeded")
                return
        cases = sorted(((k, s) for k, s in scenarios().items() if s.get("seed_only")),
                       key=lambda kv: -kv[1]["seed"]["days_ago"])
        start = utcnow()
        for key, s in cases:
            t = start - timedelta(days=s["seed"]["days_ago"], hours=3)
            pin(t)
            with SessionLocal() as db:
                vendor, _ = create_vendor_request(db, VendorRequestIn(**s["request"]), "user:1", is_seed=True)
                db.commit()
                vendor_id = vendor.id
            steps = [{"form": {}, "files": s["files"]}] + s["seed"]["resubmits"]
            for i, step in enumerate(steps):
                pin(t + timedelta(hours=5 + 52 * i))
                with SessionLocal() as db:
                    vendor = db.get(Vendor, vendor_id)
                    if vendor.status not in ("INVITED", "PENDING_VENDOR"):
                        break
                    form = SubmissionIn(**{**s["form"], **step.get("form", {})})
                    submit(db, vendor, form, files_for(step["files"]), actor=f"vendor:{vendor_id}")
                pin(t + timedelta(hours=5 + 52 * i, minutes=1))
                await drain()
            with SessionLocal() as db:
                print(f"  {s['title']:<38} {db.get(Vendor, vendor_id).status}")
        # One request that hasn't been opened yet.
        pin(start - timedelta(days=1, hours=4))
        with SessionLocal() as db:
            create_vendor_request(db, VendorRequestIn(display_name="Coastal Marine Logistics Pvt Ltd", category="Logistics",
                                                      contact_email="accounts@coastalmarine.example",
                                                      requested_by="Kavita Rao"), "user:1", is_seed=True)
            db.commit()
    finally:
        pin(None)
        settings.llm_mode, settings.demo_stage_delay_ms = real_mode, real_delay


def reset() -> None:
    if settings.database_url.startswith("sqlite"):
        from pathlib import Path
        path = Path(settings.database_url.removeprefix("sqlite:///"))
        engine.dispose()
        for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
            p.unlink(missing_ok=True)
    else:
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))


def main() -> None:
    if "--reset" in sys.argv:
        reset()
    upgrade()
    with SessionLocal() as db:
        seed_users(db)
    asyncio.run(seed_history())


if __name__ == "__main__":
    main()
