"""Trust-boundary and mutation-negative tests for ST-1908."""

from __future__ import annotations

import json
import pickle

import pytest

from raos.adapters.recorded_fine_tuning_evaluation import (
    RecordedFineTuningEvidenceSource,
    load_recorded_fine_tuning_bundle,
)
from raos.application.ai.fine_tuning_evaluation import (
    evaluate_recorded_fine_tuning,
)
from raos.domain.ai.fine_tuning_evaluation import (
    FineTuningEvaluationCommand,
    FineTuningFailure,
    FineTuningFailureCode,
    FineTuningScope,
    sha256_bytes,
)
from tests.st1908.support import fixture_bytes, recorded_bundle


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data + b" ",
        lambda data: data.replace(b'"synthetic":true', b'"synthetic":1.0', 1),
        lambda data: data.replace(b'{"baseline":', b'{"baseline":{},"baseline":', 1),
        lambda data: b"x" * (1_048_576 + 1),
    ),
)
def test_noncanonical_duplicate_float_and_oversize_sources_fail_closed(
    mutation: object,
) -> None:
    assert callable(mutation)
    content = mutation(fixture_bytes())
    with pytest.raises(FineTuningFailure) as caught:
        load_recorded_fine_tuning_bundle(content)
    assert caught.value.code is FineTuningFailureCode.SOURCE_DOCUMENT_INVALID


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("dataset", "personal_data_present", True),
        ("dataset", "rakuten_review_body_present", True),
        ("dataset", "unlicensed_content_present", True),
        ("dataset", "secret_present", True),
        ("dataset", "release_eligible", True),
        ("document", "actual_training_executed", True),
        ("baseline", "actual_execution", True),
        ("cost", "actual_cost", True),
    ),
)
def test_prohibited_data_or_actual_execution_claims_fail_closed(
    section: str,
    field: str,
    value: bool,
) -> None:
    parsed = json.loads(fixture_bytes())
    parsed[section][field] = value
    with pytest.raises(FineTuningFailure):
        load_recorded_fine_tuning_bundle(_canonical(parsed))


def test_unknown_provider_credential_and_mutation_fields_fail_closed() -> None:
    for field in (
        "provider",
        "model_id",
        "api_key",
        "endpoint",
        "training_examples",
        "release_decision",
        "recommendation_order",
    ):
        parsed = json.loads(fixture_bytes())
        parsed["document"][field] = "forbidden"
        with pytest.raises(FineTuningFailure):
            load_recorded_fine_tuning_bundle(_canonical(parsed))


def test_command_hash_and_dependency_drift_fail_closed() -> None:
    content = fixture_bytes()
    with pytest.raises(FineTuningFailure) as caught_hash:
        FineTuningEvaluationCommand(
            recording_id="st1908_recorded_evaluation_v1",
            source_sha256="f" * 64,
            source_bytes=content,
            scope=FineTuningScope.RECORDED_SYNTHETIC_EVALUATION_ONLY,
        )
    assert caught_hash.value.code is FineTuningFailureCode.SOURCE_BYTES_MISMATCH
    with pytest.raises(FineTuningFailure) as caught_dependency:
        FineTuningEvaluationCommand(
            recording_id="st1908_recorded_evaluation_v1",
            source_sha256=sha256_bytes(content),
            source_bytes=content,
            scope=FineTuningScope.RECORDED_SYNTHETIC_EVALUATION_ONLY,
            st0707_contract_sha256="f" * 64,
        )
    assert caught_dependency.value.code is (
        FineTuningFailureCode.DEPENDENCY_CONTRACT_DRIFT
    )


def test_post_load_mutation_and_source_binding_are_detected() -> None:
    bundle = recorded_bundle()
    object.__setattr__(bundle.dataset, "dataset_sha256", "f" * 64)
    with pytest.raises(FineTuningFailure):
        evaluate_recorded_fine_tuning(bundle)
    source = RecordedFineTuningEvidenceSource(fixture_bytes())
    altered = fixture_bytes().replace(b"ST1908-CANDIDATE-001", b"ST1908-CANDIDATE-002")
    with pytest.raises(FineTuningFailure):
        source.read(
            FineTuningEvaluationCommand(
                recording_id="st1908_recorded_evaluation_v1",
                source_sha256=sha256_bytes(altered),
                source_bytes=altered,
                scope=FineTuningScope.RECORDED_SYNTHETIC_EVALUATION_ONLY,
            )
        )


def test_errors_and_values_are_redacted_and_nonserializable() -> None:
    canary = "secret-canary-st1908"
    parsed = json.loads(fixture_bytes())
    parsed["document"]["api_key"] = canary
    with pytest.raises(FineTuningFailure) as caught:
        load_recorded_fine_tuning_bundle(_canonical(parsed))
    assert canary not in f"{caught.value!s} {caught.value!r}"
    with pytest.raises(TypeError):
        pickle.dumps(caught.value)
    report = evaluate_recorded_fine_tuning(recorded_bundle())
    assert canary not in f"{report!s} {report!r}"
    with pytest.raises(TypeError):
        pickle.dumps(report)
