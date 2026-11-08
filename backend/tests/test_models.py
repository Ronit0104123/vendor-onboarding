import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from app.db import init_db
from app.models import AuditEvent


def test_tables_create_and_audit_is_append_only():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as s:
        s.add(AuditEvent(actor="system", action="TEST", details={"k": "v"}))
        s.commit()
        with pytest.raises(DatabaseError):
            s.execute(text("UPDATE audit_events SET action='TAMPERED'"))
        s.rollback()
        with pytest.raises(DatabaseError):
            s.execute(text("DELETE FROM audit_events"))
        s.rollback()
        assert s.query(AuditEvent).one().action == "TEST"
