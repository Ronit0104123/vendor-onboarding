from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.llm.schemas import DocumentExtraction
from app.models import Document, Run, Submission, Vendor
from app.pipeline.checks import CheckResult
from app.pipeline.decision import Decision

SLOT_LABELS = {
    "GST_CERT": "GST registration certificate",
    "PAN_CARD": "PAN card",
    "BANK_PROOF": "cancelled cheque or bank letter",
}
EXPECTED_DOC_TYPES = {
    "GST_CERT": {"GST_CERTIFICATE"},
    "PAN_CARD": {"PAN_CARD"},
    "BANK_PROOF": {"CANCELLED_CHEQUE", "BANK_LETTER"},
}
DOC_TYPE_LABELS = {
    "GST_CERTIFICATE": "a GST registration certificate", "PAN_CARD": "a PAN card",
    "CANCELLED_CHEQUE": "a cancelled cheque", "BANK_LETTER": "a bank letter",
    "OTHER": "a different document", "UNREADABLE": "unreadable",
}


@dataclass
class RunContext:
    db: Session
    run: Run
    submission: Submission
    vendor: Vendor
    form: dict                     # typed values, PAN/account decrypted (in memory only)
    documents: dict[str, Document]  # slot -> document
    extractions: dict[str, DocumentExtraction | None] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)
    decision: Decision | None = None

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)

    def usable_extraction(self, slot: str) -> DocumentExtraction | None:
        """Only use extracted values from a document that is the right type."""
        extraction = self.extractions.get(slot)
        if extraction and extraction.doc_type in EXPECTED_DOC_TYPES[slot]:
            return extraction
        return None
