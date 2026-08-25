"""One-shot caller-bytes adapter for the ST-1908 synthetic recording."""

from __future__ import annotations

import json
from threading import RLock
from typing import Final, NoReturn, SupportsIndex, cast, final

from raos.domain.ai.fine_tuning_evaluation import (
    FINE_TUNING_CONTRACT_VERSION,
    FINE_TUNING_FIXTURE_PROFILE,
    FINE_TUNING_METHOD_VERSION,
    FINE_TUNING_PARSER_VERSION,
    MAX_SOURCE_BYTES,
    AggregateModelEvaluation,
    CostEvidence,
    DataGovernanceStatus,
    DatasetRightsEvidence,
    DatasetRightsStatus,
    DatasetSourceCount,
    EvaluationRole,
    EvidenceStatus,
    FineTuningEvaluationCommand,
    FineTuningFailure,
    FineTuningFailureCode,
    FineTuningScope,
    OptimizationEvidence,
    RecordedFineTuningBundle,
    SourceKind,
    canonical_json_bytes,
    fail_fine_tuning,
    sha256_bytes,
)


_REDACTED: Final = "<redacted-recorded-fine-tuning-source>"
_ROOT_KEYS = frozenset(
    {"baseline", "candidate", "cost", "dataset", "document", "optimization"}
)
_DOCUMENT_KEYS = frozenset(
    {
        "actual_training_executed",
        "candidate_id",
        "fixture_profile",
        "method_version",
        "parser_version",
        "recording_id",
        "schema_version",
        "scope",
        "synthetic",
        "task_code",
    }
)
_DATASET_KEYS = frozenset(
    {
        "case_count",
        "data_inventory_sha256",
        "dataset_id",
        "dataset_sha256",
        "deletion_policy_sha256",
        "governance_status",
        "holdout_compromised",
        "holdout_locked",
        "holdout_sha256",
        "license_review_sha256",
        "personal_data_present",
        "rakuten_review_body_present",
        "release_eligible",
        "representative",
        "retention_policy_sha256",
        "rights_status",
        "secret_present",
        "source_counts",
        "source_inventory_sha256",
        "unlicensed_content_present",
    }
)
_SOURCE_COUNT_KEYS = frozenset({"count", "kind"})
_OPTIMIZATION_KEYS = frozenset(
    {
        "evidence_sha256",
        "prompt_optimization_exhausted",
        "repeated_error_code",
        "repeated_error_count",
        "route_optimization_exhausted",
        "status",
    }
)
_EVALUATION_KEYS = frozenset(
    {
        "actual_execution",
        "critical_claim_support_rate_micros",
        "dataset_sha256",
        "evaluation_sha256",
        "holdout_sha256",
        "human_acceptance_rate_micros",
        "model_binding_sha256",
        "role",
        "sample_size",
        "schema_valid_rate_micros",
        "status",
        "zero_tolerance_failures",
    }
)
_COST_KEYS = frozenset(
    {
        "actual_cost",
        "baseline_inference_jpy_micros_per_request",
        "candidate_inference_jpy_micros_per_request",
        "curation_jpy_micros",
        "evaluation_jpy_micros",
        "evidence_sha256",
        "forecast_sha256",
        "human_labor_jpy_micros",
        "status",
        "training_jpy_micros",
        "workload_requests",
    }
)


class RecordedFineTuningSourceError(ValueError):
    """Sanitized adapter construction failure."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(FineTuningFailureCode.SOURCE_DOCUMENT_INVALID.value)

    def __repr__(self) -> str:
        return f"RecordedFineTuningSourceError({_REDACTED})"

    def __str__(self) -> str:
        return FineTuningFailureCode.SOURCE_DOCUMENT_INVALID.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded source errors cannot be serialized")


def _invalid() -> NoReturn:
    fail_fine_tuning(FineTuningFailureCode.SOURCE_DOCUMENT_INVALID)


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _reject_float(value: str) -> NoReturn:
    del value
    _invalid()


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    mapping = cast(dict[object, object], value)
    if frozenset(mapping) != keys:
        _invalid()
    return cast(dict[str, object], mapping)


def _list(value: object, length: int) -> list[object]:
    if type(value) is not list:
        _invalid()
    items = cast(list[object], value)
    if len(items) != length:
        _invalid()
    return items


def _string(value: object, maximum: int = 160) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(character in value for character in "\x00\r\n")
    ):
        _invalid()
    return value


def _optional_string(value: object, maximum: int = 160) -> str | None:
    if value is None:
        return None
    return _string(value, maximum)


def _integer(value: object, maximum: int = 10**15) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _invalid()
    return value


def _optional_integer(value: object, maximum: int = 10**15) -> int | None:
    if value is None:
        return None
    return _integer(value, maximum)


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _enum[EnumT: str](enum_type: type[EnumT], value: object) -> EnumT:
    try:
        return enum_type(_string(value))
    except ValueError:
        _invalid()


def _dataset(value: object) -> DatasetRightsEvidence:
    row = _mapping(value, _DATASET_KEYS)
    source_rows = _list(row["source_counts"], len(SourceKind))
    source_counts = tuple(
        DatasetSourceCount(
            kind=_enum(SourceKind, source_row["kind"]),
            count=_integer(source_row["count"], 100_000),
        )
        for source_row in (
            _mapping(source_row, _SOURCE_COUNT_KEYS) for source_row in source_rows
        )
    )
    try:
        return DatasetRightsEvidence(
            dataset_id=_string(row["dataset_id"]),
            dataset_sha256=_string(row["dataset_sha256"], 64),
            source_inventory_sha256=_string(row["source_inventory_sha256"], 64),
            holdout_sha256=_string(row["holdout_sha256"], 64),
            case_count=_integer(row["case_count"], 100_000),
            source_counts=source_counts,
            rights_status=_enum(DatasetRightsStatus, row["rights_status"]),
            license_review_sha256=_optional_string(row["license_review_sha256"], 64),
            governance_status=_enum(DataGovernanceStatus, row["governance_status"]),
            data_inventory_sha256=_optional_string(row["data_inventory_sha256"], 64),
            retention_policy_sha256=_optional_string(
                row["retention_policy_sha256"], 64
            ),
            deletion_policy_sha256=_optional_string(row["deletion_policy_sha256"], 64),
            representative=_boolean(row["representative"]),
            holdout_locked=_boolean(row["holdout_locked"]),
            holdout_compromised=_boolean(row["holdout_compromised"]),
            personal_data_present=_boolean(row["personal_data_present"]),
            rakuten_review_body_present=_boolean(row["rakuten_review_body_present"]),
            unlicensed_content_present=_boolean(row["unlicensed_content_present"]),
            secret_present=_boolean(row["secret_present"]),
            release_eligible=_boolean(row["release_eligible"]),
        )
    except FineTuningFailure:
        raise
    except Exception:
        _invalid()


def _optimization(value: object) -> OptimizationEvidence:
    row = _mapping(value, _OPTIMIZATION_KEYS)
    try:
        return OptimizationEvidence(
            status=_enum(EvidenceStatus, row["status"]),
            evidence_sha256=_optional_string(row["evidence_sha256"], 64),
            prompt_optimization_exhausted=_boolean(
                row["prompt_optimization_exhausted"]
            ),
            route_optimization_exhausted=_boolean(row["route_optimization_exhausted"]),
            repeated_error_code=_optional_string(row["repeated_error_code"]),
            repeated_error_count=_optional_integer(
                row["repeated_error_count"], 100_000
            ),
        )
    except FineTuningFailure:
        raise
    except Exception:
        _invalid()


def _evaluation(value: object) -> AggregateModelEvaluation:
    row = _mapping(value, _EVALUATION_KEYS)
    try:
        return AggregateModelEvaluation(
            role=_enum(EvaluationRole, row["role"]),
            status=_enum(EvidenceStatus, row["status"]),
            evaluation_sha256=_optional_string(row["evaluation_sha256"], 64),
            model_binding_sha256=_optional_string(row["model_binding_sha256"], 64),
            dataset_sha256=_string(row["dataset_sha256"], 64),
            holdout_sha256=_string(row["holdout_sha256"], 64),
            sample_size=_optional_integer(row["sample_size"], 100_000),
            schema_valid_rate_micros=_optional_integer(
                row["schema_valid_rate_micros"], 1_000_000
            ),
            critical_claim_support_rate_micros=_optional_integer(
                row["critical_claim_support_rate_micros"], 1_000_000
            ),
            human_acceptance_rate_micros=_optional_integer(
                row["human_acceptance_rate_micros"], 1_000_000
            ),
            zero_tolerance_failures=_optional_integer(
                row["zero_tolerance_failures"], 100_000
            ),
            actual_execution=_boolean(row["actual_execution"]),
        )
    except FineTuningFailure:
        raise
    except Exception:
        _invalid()


def _cost(value: object) -> CostEvidence:
    row = _mapping(value, _COST_KEYS)
    try:
        return CostEvidence(
            status=_enum(EvidenceStatus, row["status"]),
            evidence_sha256=_optional_string(row["evidence_sha256"], 64),
            forecast_sha256=_optional_string(row["forecast_sha256"], 64),
            workload_requests=_optional_integer(
                row["workload_requests"], 1_000_000_000
            ),
            baseline_inference_jpy_micros_per_request=_optional_integer(
                row["baseline_inference_jpy_micros_per_request"]
            ),
            candidate_inference_jpy_micros_per_request=_optional_integer(
                row["candidate_inference_jpy_micros_per_request"]
            ),
            training_jpy_micros=_optional_integer(row["training_jpy_micros"]),
            curation_jpy_micros=_optional_integer(row["curation_jpy_micros"]),
            evaluation_jpy_micros=_optional_integer(row["evaluation_jpy_micros"]),
            human_labor_jpy_micros=_optional_integer(row["human_labor_jpy_micros"]),
            actual_cost=_boolean(row["actual_cost"]),
        )
    except FineTuningFailure:
        raise
    except Exception:
        _invalid()


def load_recorded_fine_tuning_bundle(
    source_bytes: bytes,
) -> RecordedFineTuningBundle:
    """Parse one bounded canonical JSON document without repair or coercion."""

    if (
        type(source_bytes) is not bytes
        or not 1 <= len(source_bytes) <= MAX_SOURCE_BYTES
    ):
        _invalid()
    try:
        parsed = json.loads(
            source_bytes.decode("ascii", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except FineTuningFailure:
        raise
    except Exception:
        _invalid()
    root = _mapping(parsed, _ROOT_KEYS)
    if canonical_json_bytes(root) + b"\n" != source_bytes:
        _invalid()
    document = _mapping(root["document"], _DOCUMENT_KEYS)
    if (
        _string(document["schema_version"]) != FINE_TUNING_CONTRACT_VERSION
        or _string(document["fixture_profile"]) != FINE_TUNING_FIXTURE_PROFILE
        or _string(document["method_version"]) != FINE_TUNING_METHOD_VERSION
        or _string(document["parser_version"]) != FINE_TUNING_PARSER_VERSION
        or _enum(FineTuningScope, document["scope"])
        is not FineTuningScope.RECORDED_SYNTHETIC_EVALUATION_ONLY
    ):
        _invalid()
    try:
        return RecordedFineTuningBundle(
            recording_id=_string(document["recording_id"], 64),
            fixture_profile=_string(document["fixture_profile"]),
            task_code=_string(document["task_code"]),
            candidate_id=_string(document["candidate_id"]),
            synthetic=_boolean(document["synthetic"]),
            actual_training_executed=_boolean(document["actual_training_executed"]),
            dataset=_dataset(root["dataset"]),
            optimization=_optimization(root["optimization"]),
            baseline=_evaluation(root["baseline"]),
            candidate=_evaluation(root["candidate"]),
            cost=_cost(root["cost"]),
        )
    except FineTuningFailure:
        raise
    except Exception:
        _invalid()


@final
class RecordedFineTuningEvidenceSource:
    """Hold one sanitized caller recording and consume it exactly once."""

    __slots__ = ("_consumed", "_lock", "_source_bytes", "_source_sha256")

    def __init__(self, source_bytes: bytes) -> None:
        if (
            type(source_bytes) is not bytes
            or not 1 <= len(source_bytes) <= MAX_SOURCE_BYTES
        ):
            raise RecordedFineTuningSourceError() from None
        self._source_bytes = bytes(source_bytes)
        self._source_sha256 = sha256_bytes(self._source_bytes)
        self._consumed = False
        self._lock = RLock()

    def read(self, command: FineTuningEvaluationCommand) -> RecordedFineTuningBundle:
        if type(command) is not FineTuningEvaluationCommand:
            fail_fine_tuning()
        with self._lock:
            if self._consumed:
                fail_fine_tuning(FineTuningFailureCode.SOURCE_EXHAUSTED)
            if (
                command.source_sha256 != self._source_sha256
                or command.source_bytes != self._source_bytes
            ):
                fail_fine_tuning(FineTuningFailureCode.SOURCE_BYTES_MISMATCH)
            self._consumed = True
            bundle = load_recorded_fine_tuning_bundle(self._source_bytes)
            if bundle.recording_id != command.recording_id:
                fail_fine_tuning(FineTuningFailureCode.SOURCE_DOCUMENT_INVALID)
            return bundle


__all__ = (
    "RecordedFineTuningEvidenceSource",
    "RecordedFineTuningSourceError",
    "load_recorded_fine_tuning_bundle",
)
