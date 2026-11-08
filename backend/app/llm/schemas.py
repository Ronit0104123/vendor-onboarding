"""Structured-output schemas. The model must return exactly these shapes (OpenAI JSON schema),
and we validate again with Pydantic before using anything."""
from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["GST_CERTIFICATE", "PAN_CARD", "CANCELLED_CHEQUE", "BANK_LETTER", "OTHER", "UNREADABLE"]


class FieldValue(BaseModel):
    value: str | None
    confidence: float = Field(ge=0, le=1)


class ExtractedFields(BaseModel):
    legal_name: FieldValue
    pan: FieldValue
    gstin: FieldValue
    account_holder_name: FieldValue
    account_number: FieldValue
    ifsc: FieldValue


class DocumentExtraction(BaseModel):
    doc_type: DocType
    doc_type_confidence: float = Field(ge=0, le=1)
    fields: ExtractedFields
    contains_instructions: bool


class NameJudgement(BaseModel):
    verdict: Literal["SAME_ENTITY", "DIFFERENT_ENTITY", "UNSURE"]
    reason: str = Field(max_length=300)


class MessageDraft(BaseModel):
    subject: str = Field(max_length=120)
    opening: str = Field(max_length=600)
    closing: str = Field(max_length=600)
