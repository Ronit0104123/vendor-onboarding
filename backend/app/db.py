from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    is_sqlite = url.startswith("sqlite")
    if is_sqlite and ":memory:" not in url:
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        (settings.storage_dir.parent / "data").mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# The audit trail is append-only at the database level, not just by convention.
APPEND_ONLY_SQLITE = [
    "CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
]
APPEND_ONLY_POSTGRES = [
    "CREATE OR REPLACE FUNCTION audit_block() RETURNS trigger AS $$ "
    "BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS audit_append_only ON audit_events",
    "CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_events "
    "FOR EACH ROW EXECUTE FUNCTION audit_block()",
]


def init_db(bind=None):
    from app import models  # noqa: F401  (registers tables)
    bind = bind or engine
    Base.metadata.create_all(bind)
    statements = APPEND_ONLY_SQLITE if bind.dialect.name == "sqlite" else APPEND_ONLY_POSTGRES
    with bind.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))
