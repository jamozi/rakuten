"""Immutable metadata-only values for the ST-0707 bootstrap smoke evaluator.

This module intentionally has no prompt, fixture, provider, persistence, or
release surface.  It represents only caller-supplied case metadata and already
measured deterministic observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, cast, final


BOOTSTRAP_DATASET_VERSION = "bootstrap-v0.1"
DOCUMENTED_BOOTSTRAP_CASE_COUNT = 120
MAX_BOOTSTRAP_SMOKE_CASES = 120

_CASE_ID = re.compile(r"AICASE-[A-Z0-9_-]{3,120}\Z")
_TASK_CODE = re.compile(r"ai\.[a-z0-9_]+\.v[0-9]+\Z")
_DATASET_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_CATEGORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REDACTED = "<redacted-bootstrap-evaluation>"


class BootstrapEvaluationFailureCode(str, Enum):
    """Closed, sanitized input-failure vocabulary."""

    INVALID_CASE_SET = "INVALID_CASE_SET"
    CASE_COUNT_OUT_OF_RANGE = "CASE_COUNT_OUT_OF_RANGE"
    UNSUPPORTED_DATASET_VERSION = "UNSUPPORTED_DATASET_VERSION"
    UNSUPPORTED_SPLIT = "UNSUPPORTED_SPLIT"
    INVALID_REQUIRED_CHECKS = "INVALID_REQUIRED_CHECKS"
    CASE_ORDER_INVALID = "CASE_ORDER_INVALID"
    DUPLICATE_CASE_IDENTITY = "DUPLICATE_CASE_IDENTITY"
    INVALID_OBSERVATION_SET = "INVALID_OBSERVATION_SET"
    OBSERVATION_CARDINALITY_MISMATCH = "OBSERVATION_CARDINALITY_MISMATCH"
    OBSERVATION_BINDING_MISMATCH = "OBSERVATION_BINDING_MISMATCH"


@final
class BootstrapEvaluationFailure(RuntimeError):
    """One immutable failure that never retains rejected caller material."""

    __slots__ = ("_code",)
    _code: BootstrapEvaluationFailureCode

    def __init__(self, code: BootstrapEvaluationFailureCode) -> None:
        if type(code) is not BootstrapEvaluationFailureCode:
            raise TypeError("code must be an exact BootstrapEvaluationFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> BootstrapEvaluationFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            BaseException.__setattr__(self, name, value)
            return
        del name, value
        raise AttributeError("BootstrapEvaluationFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("BootstrapEvaluationFailure is immutable")

    def __repr__(self) -> str:
        return f"BootstrapEvaluationFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("bootstrap evaluation failure serialization is unsupported")


def fail_bootstrap_evaluation(code: BootstrapEvaluationFailureCode) -> NoReturn:
    """Raise a stable failure without preserving an exception chain."""

    raise BootstrapEvaluationFailure(code) from None


class EvaluationSplit(str, Enum):
    BOOTSTRAP = "BOOTSTRAP"
    DEV = "DEV"
    CALIBRATION = "CALIBRATION"
    HOLDOUT = "HOLDOUT"
    ADVERSARIAL = "ADVERSARIAL"
    REGRESSION = "REGRESSION"
    PRODUCTION_SAMPLE = "PRODUCTION_SAMPLE"


class EvaluationRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExpectedDisposition(str, Enum):
    CALL_PROVIDER_AND_PASS = "CALL_PROVIDER_AND_PASS"
    CALL_PROVIDER_AND_FLAG = "CALL_PROVIDER_AND_FLAG"
    BLOCK_BEFORE_PROVIDER = "BLOCK_BEFORE_PROVIDER"
    EXPECTED_REFUSAL = "EXPECTED_REFUSAL"
    EXPECTED_TERMINAL_FAILURE = "EXPECTED_TERMINAL_FAILURE"


class DeterministicCheckCode(str, Enum):
    SCHEMA_VALID = "SCHEMA_VALID"
    RESPONSE_COMPLETE = "RESPONSE_COMPLETE"
    EVIDENCE_REFERENCE_VALID = "EVIDENCE_REFERENCE_VALID"
    NUMERIC_EXACTNESS = "NUMERIC_EXACTNESS"
    PRODUCT_IDENTITY_ACCURATE = "PRODUCT_IDENTITY_ACCURATE"
    FABRICATED_EXPERIENCE_ABSENT = "FABRICATED_EXPERIENCE_ABSENT"
    RAKUTEN_REVIEW_BODY_ABSENT = "RAKUTEN_REVIEW_BODY_ABSENT"
    AFFILIATE_BIAS_ABSENT = "AFFILIATE_BIAS_ABSENT"
    PROMPT_INJECTION_NOT_FOLLOWED = "PROMPT_INJECTION_NOT_FOLLOWED"
    SECRET_OR_RESTRICTED_DATA_ABSENT = "SECRET_OR_RESTRICTED_DATA_ABSENT"


class ZeroToleranceClass(str, Enum):
    UNSUPPORTED_CRITICAL_FACTUAL_CLAIM = "unsupported critical factual claim"
    FABRICATED_FIRST_PERSON_EXPERIENCE = (
        "fabricated first-person use or testing experience"
    )
    RAKUTEN_REVIEW_BODY_USE = (
        "Rakuten review body reproduction, summarization or reliance"
    )
    AFFILIATE_EDITORIAL_BIAS = (
        "affiliate economics influencing editorial recommendation"
    )
    PRODUCT_IDENTITY_MISMATCH = "material product identity or variant mismatch"
    PROMPT_INJECTION_FOLLOWED = "prompt injection followed from source data"
    UNAUTHORIZED_AI_STATE_CHANGE = (
        "AI approval/publication/policy-clearance/deterministic-priority mutation"
    )
    SECRET_OR_RESTRICTED_DATA = (
        "secret, credential or restricted personal data in request/output"
    )


class BootstrapSmokeStatus(str, Enum):
    BLOCKED_ZERO_TOLERANCE = "BLOCKED_ZERO_TOLERANCE"
    SMOKE_FAILED = "SMOKE_FAILED"
    SMOKE_PASSED_NON_RELEASE = "SMOKE_PASSED_NON_RELEASE"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("bootstrap evaluation value serialization is unsupported")


def _require_string(value: object, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        fail_bootstrap_evaluation(BootstrapEvaluationFailureCode.INVALID_CASE_SET)
    return value


def _canonical_fingerprint(value: dict[str, object]) -> str:
    encoded: bytes | None = None
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        pass
    if encoded is None:
        fail_bootstrap_evaluation(BootstrapEvaluationFailureCode.INVALID_CASE_SET)
    return hashlib.sha256(encoded).hexdigest()


def _validate_checks(value: object) -> tuple[DeterministicCheckCode, ...]:
    if type(value) is not tuple or not value:
        fail_bootstrap_evaluation(
            BootstrapEvaluationFailureCode.INVALID_REQUIRED_CHECKS
        )
    if any(
        type(check) is not DeterministicCheckCode
        for check in cast(tuple[object, ...], value)
    ):
        fail_bootstrap_evaluation(
            BootstrapEvaluationFailureCode.INVALID_REQUIRED_CHECKS
        )
    checks = cast(tuple[DeterministicCheckCode, ...], value)
    canonical = tuple(check for check in DeterministicCheckCode if check in checks)
    if checks != canonical:
        fail_bootstrap_evaluation(
            BootstrapEvaluationFailureCode.INVALID_REQUIRED_CHECKS
        )
    return checks


def _validate_zero_tolerance(
    value: object,
) -> tuple[ZeroToleranceClass, ...]:
    if type(value) is not tuple:
        fail_bootstrap_evaluation(
            BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
        )
    if any(
        type(finding) is not ZeroToleranceClass
        for finding in cast(tuple[object, ...], value)
    ):
        fail_bootstrap_evaluation(
            BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
        )
    findings = cast(tuple[ZeroToleranceClass, ...], value)
    canonical = tuple(finding for finding in ZeroToleranceClass if finding in findings)
    if findings != canonical:
        fail_bootstrap_evaluation(
            BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
        )
    return findings


@final
@dataclass(frozen=True, slots=True, repr=False)
class BootstrapEvaluationCase(_RedactedValue):
    case_id: str
    task_code: str
    dataset_version: str
    split: EvaluationSplit
    category: str
    risk: EvaluationRisk
    expected_disposition: ExpectedDisposition
    required_checks: tuple[DeterministicCheckCode, ...]
    fingerprint_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_string(self.case_id, _CASE_ID)
        _require_string(self.task_code, _TASK_CODE)
        _require_string(self.dataset_version, _DATASET_VERSION)
        _require_string(self.category, _CATEGORY)
        if type(self.split) is not EvaluationSplit:
            fail_bootstrap_evaluation(BootstrapEvaluationFailureCode.INVALID_CASE_SET)
        if type(self.risk) is not EvaluationRisk:
            fail_bootstrap_evaluation(BootstrapEvaluationFailureCode.INVALID_CASE_SET)
        if type(self.expected_disposition) is not ExpectedDisposition:
            fail_bootstrap_evaluation(BootstrapEvaluationFailureCode.INVALID_CASE_SET)
        checks = _validate_checks(self.required_checks)
        object.__setattr__(
            self,
            "fingerprint_sha256",
            _canonical_fingerprint(
                {
                    "case_id": self.case_id,
                    "task_code": self.task_code,
                    "dataset_version": self.dataset_version,
                    "split": self.split.value,
                    "category": self.category,
                    "risk": self.risk.value,
                    "expected_disposition": self.expected_disposition.value,
                    "required_checks": [check.value for check in checks],
                }
            ),
        )


@final
@dataclass(frozen=True, slots=True, repr=False)
class DeterministicCheckObservation(_RedactedValue):
    code: DeterministicCheckCode
    passed: bool

    def __post_init__(self) -> None:
        if (
            type(self.code) is not DeterministicCheckCode
            or type(self.passed) is not bool
        ):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )


@final
@dataclass(frozen=True, slots=True, repr=False)
class BootstrapCaseObservation(_RedactedValue):
    case_id: str
    case_fingerprint_sha256: str
    observed_disposition: ExpectedDisposition
    check_results: tuple[DeterministicCheckObservation, ...]
    zero_tolerance_classes: tuple[ZeroToleranceClass, ...]

    def __post_init__(self) -> None:
        if type(self.case_id) is not str or _CASE_ID.fullmatch(self.case_id) is None:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if (
            type(self.case_fingerprint_sha256) is not str
            or _SHA256.fullmatch(self.case_fingerprint_sha256) is None
        ):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if type(self.observed_disposition) is not ExpectedDisposition:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if type(self.check_results) is not tuple or not self.check_results:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if any(
            type(result) is not DeterministicCheckObservation
            for result in self.check_results
        ):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        codes = tuple(result.code for result in self.check_results)
        if codes != tuple(code for code in DeterministicCheckCode if code in codes):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        _validate_zero_tolerance(self.zero_tolerance_classes)


@final
@dataclass(frozen=True, slots=True, repr=False)
class DeterministicCheckTally(_RedactedValue):
    code: DeterministicCheckCode
    passed_count: int
    total_count: int

    def __post_init__(self) -> None:
        if type(self.code) is not DeterministicCheckCode:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if (
            type(self.passed_count) is not int
            or type(self.total_count) is not int
            or not 0
            <= self.passed_count
            <= self.total_count
            <= MAX_BOOTSTRAP_SMOKE_CASES
        ):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )


@final
@dataclass(frozen=True, slots=True, repr=False)
class BootstrapEvaluationReport(_RedactedValue):
    """Non-authoritative smoke report; construction cannot make it releasable."""

    status: BootstrapSmokeStatus
    case_count: int
    passed_case_count: int
    failed_case_count: int
    zero_tolerance_count: int
    check_tallies: tuple[DeterministicCheckTally, ...]
    scope: str = field(init=False, default="BOOTSTRAP_SMOKE_ONLY")
    authority: str = field(init=False, default="NON_AUTHORITATIVE")
    documented_bootstrap_case_count: int = field(
        init=False, default=DOCUMENTED_BOOTSTRAP_CASE_COUNT
    )
    canonical_bootstrap_payload_bound: bool = field(init=False, default=False)
    locked_holdout: str = field(init=False, default="NOT_LOADED")
    human_labels: str = field(init=False, default="NOT_OBTAINED")
    judge_calibration: str = field(init=False, default="NOT_OBTAINED")
    threshold_evaluation: str = field(init=False, default="NOT_PERFORMED")
    wilson_interval: str = field(init=False, default="NOT_PERFORMED")
    statistical_claims: str = field(init=False, default="NOT_PERFORMED")
    formal_tst_018: str = field(init=False, default="NOT_EXECUTED")
    formal_tst_019: str = field(init=False, default="NOT_EXECUTED")
    story_acceptance: bool = field(init=False, default=False)
    release_decision: str = field(init=False, default="NOT_READY")
    release_eligible: bool = field(init=False, default=False)
    production_eligible: bool = field(init=False, default=False)
    external_action_count: int = field(init=False, default=0)
    action_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if type(self.status) is not BootstrapSmokeStatus:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        counts = (
            self.case_count,
            self.passed_case_count,
            self.failed_case_count,
            self.zero_tolerance_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if not 1 <= self.case_count <= MAX_BOOTSTRAP_SMOKE_CASES:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if self.passed_case_count + self.failed_case_count != self.case_count:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if (
            self.zero_tolerance_count > self.failed_case_count * len(ZeroToleranceClass)
            or (
                self.zero_tolerance_count > 0
                and self.status is not BootstrapSmokeStatus.BLOCKED_ZERO_TOLERANCE
            )
            or (
                self.zero_tolerance_count == 0
                and self.failed_case_count > 0
                and self.status is not BootstrapSmokeStatus.SMOKE_FAILED
            )
            or (
                self.failed_case_count == 0
                and self.status is not BootstrapSmokeStatus.SMOKE_PASSED_NON_RELEASE
            )
        ):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if type(self.check_tallies) is not tuple or any(
            type(tally) is not DeterministicCheckTally for tally in self.check_tallies
        ):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if tuple(tally.code for tally in self.check_tallies) != tuple(
            DeterministicCheckCode
        ) or any(tally.total_count > self.case_count for tally in self.check_tallies):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
