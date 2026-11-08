"""Simulated clock for demoing reminders without waiting days."""
from datetime import datetime, timedelta, timezone
from app.timeutil import utcnow

from sqlalchemy.orm import Session

from app.models import AppState


def offset_days(db: Session) -> int:
    row = db.get(AppState, "clock_offset_days")
    return int(row.value) if row else 0


def set_offset_days(db: Session, days: int) -> None:
    row = db.get(AppState, "clock_offset_days") or AppState(key="clock_offset_days", value="0")
    row.value = str(days)
    db.merge(row)


def now(db: Session) -> datetime:
    return utcnow() + timedelta(days=offset_days(db))
