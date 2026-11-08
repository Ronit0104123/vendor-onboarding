"""S8: the decision engine. Pure code, no LLM. Every outcome is traceable to the checks that caused it."""
from dataclasses import dataclass, field
from enum import Enum

from app.pipeline.checks import CheckResult, Severity


class Status(str, Enum):
    APPROVED = "APPROVED"
    PENDING_VENDOR = "PENDING_VENDOR"      # waiting on the vendor to fix something
    PENDING_INTERNAL = "PENDING_INTERNAL"  # waiting on a procurement admin
    REJECTED = "REJECTED"
    AUTO_CLOSED = "AUTO_CLOSED"            # ran out of attempts


@dataclass
class Decision:
    status: Status
    summary: str
    deciding_checks: list[CheckResult] = field(default_factory=list)


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def decide(checks: list[CheckResult], attempt_no: int, max_attempts: int) -> Decision:
    def having(severity: Severity) -> list[CheckResult]:
        return [c for c in checks if c.severity == severity]

    blocking = having(Severity.BLOCKING)
    if blocking:
        return Decision(Status.REJECTED, f"{_n(len(blocking), 'blocking issue')} found", blocking)

    fixable = having(Severity.FIXABLE)
    if fixable:
        if attempt_no >= max_attempts:
            return Decision(Status.AUTO_CLOSED,
                            f"Still {_n(len(fixable), 'item')} to fix after {attempt_no} attempts", fixable)
        return Decision(Status.PENDING_VENDOR, f"{_n(len(fixable), 'item')} for the vendor to fix", fixable)

    review = having(Severity.NEEDS_REVIEW)
    if review:
        return Decision(Status.PENDING_INTERNAL, f"{_n(len(review), 'item')} for internal review", review)

    return Decision(Status.APPROVED, "All checks passed", [])
