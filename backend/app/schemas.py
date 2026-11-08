"""Request schemas. Everything the client sends is re-validated here: types, lengths, allowed characters."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

NAME = r"^[A-Za-z0-9 .,&'()/\-]*$"
ID = r"^[A-Z0-9\-]*$"
EMAIL = r"^[^@\s]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class VendorRequestIn(Strict):
    display_name: str = Field(min_length=2, max_length=200, pattern=NAME)
    category: Literal["Hardware", "Raw materials", "Logistics", "Packaging", "Services", "IT", "Other"]
    contact_email: str = Field(max_length=254, pattern=EMAIL)
    requested_by: str = Field(min_length=2, max_length=120, pattern=NAME)


class SubmissionIn(Strict):
    """Most fields are optional here on purpose: an incomplete form is still accepted and the
    Completeness stage tells the vendor exactly what is missing."""
    legal_name: str = Field("", max_length=200, pattern=NAME)
    trade_name: str = Field("", max_length=200, pattern=NAME)
    country: Literal["IN", "US", "GB"] = "IN"
    address_line: str = Field("", max_length=300, pattern=r"^[A-Za-z0-9 .,&'()/#:\-\n]*$")
    city: str = Field("", max_length=100, pattern=NAME)
    state: str = Field("", max_length=100, pattern=NAME)
    postal_code: str = Field("", max_length=12, pattern=r"^[A-Za-z0-9 \-]*$")
    contact_name: str = Field("", max_length=120, pattern=NAME)
    contact_email: str = Field("", max_length=254)
    contact_phone: str = Field("", max_length=20, pattern=r"^[0-9+ ()\-]*$")
    pan: str = Field("", max_length=10, pattern=ID)
    gstin: str = Field("", max_length=15, pattern=ID)
    tax_id: str = Field("", max_length=20, pattern=ID)
    bank_holder_name: str = Field("", max_length=200, pattern=NAME)
    account_number: str = Field("", max_length=18, pattern=r"^[0-9]*$")
    bank_code: str = Field("", max_length=11, pattern=ID)

    @field_validator("pan", "gstin", "tax_id", "bank_code", "postal_code", mode="before")
    @classmethod
    def upper(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("contact_email")
    @classmethod
    def email(cls, v):
        import re
        if v and not re.fullmatch(EMAIL, v):
            raise ValueError("Enter a valid email address.")
        return v.lower()


class OverrideIn(Strict):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=15, max_length=1000)


class OverrideReviewIn(Strict):
    approve: bool
    note: str = Field("", max_length=1000)


class RevealIn(Strict):
    field: Literal["pan", "account_number"]


class ClockIn(Strict):
    offset_days: int = Field(ge=0, le=60)
