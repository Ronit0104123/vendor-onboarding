"""The shape every check returns. Every reason shown anywhere in the app comes from one of these."""
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"                  # shown, never blocks
    FIXABLE = "FIXABLE"            # vendor can correct it
    BLOCKING = "BLOCKING"          # cannot be fixed by resubmitting; reject
    NEEDS_REVIEW = "NEEDS_REVIEW"  # a human must look (LLM unsure, low confidence, LLM failure)


@dataclass
class CheckResult:
    code: str             # stable id, e.g. "PAN_IN_GSTIN"
    stage: str            # "S3".."S7"
    severity: Severity
    reason: str           # internal, for procurement ("PAN inside GSTIN is AABCX... but submitted PAN is ...")
    field: str | None = None          # form field to highlight on the vendor portal
    vendor_message: str | None = None  # what the vendor is asked to do (only for FIXABLE)
