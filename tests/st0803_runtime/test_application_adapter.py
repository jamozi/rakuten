from __future__ import annotations

from dataclasses import replace
import json
from collections.abc import Callable
from uuid import UUID

import pytest

from raos.adapters.recorded_comparison_validation import (
    RecordedComparisonValidationAdapter,
    RecordedComparisonValidationError,
    load_recorded_comparison_fixture,
)
from raos.application.editorial.comparison_validation import (
    EvaluateComparisonValidationService,
    RecordComparisonValidationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.comparison_validation_v2 import (
    ComparisonValidationStatus,
)
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.shared.persistence import Sha256Digest


def _adapter(payload: bytes) -> RecordedComparisonValidationAdapter:
    return RecordedComparisonValidationAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=4,
        snapshot_bytes=(payload,),
    )


def test_services_evaluate_and_record_idempotently(fixture_bytes: bytes) -> None:
    adapter = _adapter(fixture_bytes)
    envelope = load_recorded_comparison_fixture(fixture_bytes)
    article_version_id = envelope.comparison.article.article_version_id
    evaluator = EvaluateComparisonValidationService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
    )
    recorder = RecordComparisonValidationService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
        appender=adapter,
    )

    report = evaluator.evaluate(article_version_id)
    first = recorder.record(article_version_id, report)
    second = recorder.record(article_version_id, report)

    assert report.status is ComparisonValidationStatus.LOCAL_VALIDATED
    assert first == second
    assert first.sequence == 1
    assert first.report_sha256 == report.report_sha256
    assert not first.publication_authorized
    assert adapter.receipts() == (first,)


def test_missing_or_reader_failure_returns_unevaluable(fixture_bytes: bytes) -> None:
    adapter = _adapter(fixture_bytes)
    unknown = ArticleVersionId(UUID("90909090-9090-4090-8090-909090909090"))
    service = EvaluateComparisonValidationService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
    )

    report = service.evaluate(unknown)

    assert report.status is ComparisonValidationStatus.UNEVALUABLE


def test_nonlocal_environment_is_rejected(fixture_bytes: bytes) -> None:
    adapter = _adapter(fixture_bytes)
    with pytest.raises(ValueError, match="INVALID_COMPARISON_VALIDATION_SERVICE"):
        EvaluateComparisonValidationService(
            environment=RuntimeEnvironment.PRODUCTION,
            reader=adapter,
        )
    with pytest.raises(RecordedComparisonValidationError):
        RecordedComparisonValidationAdapter(
            environment=RuntimeEnvironment.PRODUCTION,
            capacity=1,
            snapshot_bytes=(fixture_bytes,),
        )


def test_forged_report_is_rejected(fixture_bytes: bytes) -> None:
    adapter = _adapter(fixture_bytes)
    envelope = load_recorded_comparison_fixture(fixture_bytes)
    article_version_id = envelope.comparison.article.article_version_id
    evaluator = EvaluateComparisonValidationService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
    )
    recorder = RecordComparisonValidationService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
        appender=adapter,
    )
    report = evaluator.evaluate(article_version_id)
    forged = replace(report, report_sha256=Sha256Digest("f" * 64))

    with pytest.raises(ValueError):
        recorder.record(article_version_id, forged)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.replace(b'"schema_version": 2', b'"schema_version": 1'),
        lambda payload: payload.replace(
            b'"schema_version": 2',
            b'"schema_version": 2, "schema_version": 2',
        ),
        lambda payload: payload.replace(
            b'"contract_id": "RAOS-ST0803-COMPARISON-VALIDATION-RUNTIME-002"',
            b'"contract_id": "wrong"',
        ),
    ],
)
def test_strict_fixture_decoder_rejects_drift(
    fixture_bytes: bytes,
    mutation: Callable[[bytes], bytes],
) -> None:
    with pytest.raises(RecordedComparisonValidationError):
        load_recorded_comparison_fixture(mutation(fixture_bytes))


def test_decoder_rejects_oversized_and_wrong_key_order(fixture_bytes: bytes) -> None:
    with pytest.raises(RecordedComparisonValidationError):
        load_recorded_comparison_fixture(b"{" + b"x" * 2_097_152 + b"}")
    parsed = json.loads(fixture_bytes)
    reordered = {
        "comparison": parsed["comparison"],
        "schema_version": 2,
        "claim_evidence": parsed["claim_evidence"],
    }
    with pytest.raises(RecordedComparisonValidationError):
        load_recorded_comparison_fixture(json.dumps(reordered).encode())


def test_decoder_bounds_every_nested_string(fixture_bytes: bytes) -> None:
    parsed = json.loads(fixture_bytes)
    parsed["comparison"]["axis_catalog"]["axes"][0]["label"] = "x" * 121
    with pytest.raises(RecordedComparisonValidationError):
        load_recorded_comparison_fixture(json.dumps(parsed).encode())
    parsed = json.loads(fixture_bytes)
    parsed["claim_evidence"]["claims"][0]["claim_text_sha256"] = "x" * 4_097
    with pytest.raises(RecordedComparisonValidationError):
        load_recorded_comparison_fixture(json.dumps(parsed).encode())


def test_adapter_owns_source_bytes_and_has_no_mutation_surface(
    fixture_bytes: bytes,
) -> None:
    adapter = _adapter(fixture_bytes)
    envelope = load_recorded_comparison_fixture(fixture_bytes)
    first = adapter.get_snapshot(envelope.comparison.article.article_version_id)
    second = adapter.get_snapshot(envelope.comparison.article.article_version_id)

    assert first == second
    assert first is not second
    assert not hasattr(adapter, "publish")
    assert not hasattr(adapter, "update")
    assert not hasattr(adapter, "delete")
    assert "11111111" not in repr(adapter)
