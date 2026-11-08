"""Single source of 'now'. The seed script can pin it (to create realistic history) without ever
rewriting rows afterwards, which matters because the audit table is append-only."""
from contextvars import ContextVar
from datetime import datetime, timezone

_pinned: ContextVar[datetime | None] = ContextVar("pinned_now", default=None)


def utcnow() -> datetime:
    return _pinned.get() or datetime.now(timezone.utc)


def pin(moment: datetime | None) -> None:
    _pinned.set(moment)
