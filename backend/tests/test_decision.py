from app.pipeline.checks import CheckResult, Severity
from app.pipeline.decision import Status, decide


def c(severity: Severity, code: str = "X") -> CheckResult:
    return CheckResult(code=code, stage="S4", severity=severity, reason=f"{code} reason")


def test_all_pass_is_approved():
    d = decide([c(Severity.PASS), c(Severity.PASS)], attempt_no=1, max_attempts=3)
    assert d.status == Status.APPROVED and d.deciding_checks == []


def test_warnings_alone_still_approve():
    assert decide([c(Severity.PASS), c(Severity.WARN)], 1, 3).status == Status.APPROVED


def test_blocking_wins_over_everything():
    checks = [c(Severity.FIXABLE), c(Severity.NEEDS_REVIEW), c(Severity.BLOCKING, "PAN_IN_GSTIN")]
    d = decide(checks, 1, 3)
    assert d.status == Status.REJECTED
    assert [x.code for x in d.deciding_checks] == ["PAN_IN_GSTIN"]


def test_fixable_goes_back_to_vendor():
    d = decide([c(Severity.FIXABLE, "A"), c(Severity.FIXABLE, "B"), c(Severity.NEEDS_REVIEW)], 1, 3)
    assert d.status == Status.PENDING_VENDOR
    assert [x.code for x in d.deciding_checks] == ["A", "B"]


def test_fixable_on_last_attempt_auto_closes():
    assert decide([c(Severity.FIXABLE)], attempt_no=3, max_attempts=3).status == Status.AUTO_CLOSED


def test_needs_review_goes_internal_never_approved():
    assert decide([c(Severity.PASS), c(Severity.NEEDS_REVIEW)], 1, 3).status == Status.PENDING_INTERNAL


def test_empty_check_list_is_approved_only_because_nothing_failed():
    # The pipeline always produces checks; this documents the pure-function behaviour.
    assert decide([], 1, 3).status == Status.APPROVED
