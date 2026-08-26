"""Golden behavior and pre-parser duplicate denial for ST-1301."""

from __future__ import annotations

import pytest

from dataclasses import FrozenInstanceError, replace
from datetime import date
import pickle

from .support import (
    ROW_CONFIRMED,
    ROW_GENERATED,
    SYNTHETIC_CSV,
    intake_result,
    parse_command,
    service_for,
)
from raos.adapters.recorded_revenue_import import (
    RecordedRevenueFixture,
    RecordedRevenueParserAdapter,
)
from raos.application.finance.revenue_import import RevenueImportService
from raos.domain.finance.revenue_import import (
    RevenueDecision,
    RevenueExecutionStatus,
    RevenueImportFailure,
    RevenueImportFailureCode,
    RevenueMappingStatus,
    RevenueObservedSum,
    RevenueRowCode,
    RevenueRowParseStatus,
    SyntheticRevenueParseCommand,
    SyntheticRevenueProfile,
)
from raos.domain.ops.object_intake import DuplicateStatus, Sha256Digest


def test_synthetic_dry_run_is_redacted_nonpersistent_and_not_ready() -> None:
    intake = intake_result()
    result = service_for(intake, SYNTHETIC_CSV).dry_run(intake)

    assert result.row_count == 4
    assert result.accepted_count == 2
    assert result.rejected_count == 1
    assert result.duplicate_count == 1
    assert result.ignored_count == 0
    assert tuple(value.status for value in result.previews) == (
        RevenueRowParseStatus.ACCEPTED,
        RevenueRowParseStatus.ACCEPTED,
        RevenueRowParseStatus.DUPLICATE,
        RevenueRowParseStatus.REJECTED,
    )
    assert result.execution is RevenueExecutionStatus.SYNTHETIC_FIXTURE_ONLY
    assert result.persistence is RevenueExecutionStatus.NOT_EXECUTED
    assert result.mapping is RevenueMappingStatus.UNVERIFIED
    assert result.decision is RevenueDecision.NOT_READY
    assert result.provider_total_jpy is None
    assert result.revenue_import_id is None
    assert result.source_artifact_id is None
    assert result.approval_id is None
    assert result.facts.value == "NOT_CREATED"
    assert result.reconciliation is RevenueExecutionStatus.NOT_EXECUTED
    assert result.audit is RevenueExecutionStatus.NOT_EXECUTED
    assert result.outbox is RevenueExecutionStatus.NOT_EXECUTED
    assert result.events is RevenueExecutionStatus.NOT_EXECUTED
    assert result.tst026 is RevenueExecutionStatus.NOT_EXECUTED
    assert result.tst030 is RevenueExecutionStatus.NOT_EXECUTED


def test_observed_sums_are_fixed_order_and_missing_confirmed_is_not_zero() -> None:
    intake = intake_result()
    result = service_for(intake).dry_run(intake)
    generated, confirmed, cancelled, adjusted = result.observed_sums

    assert generated.row_count == 1
    assert generated.generated_commission_jpy == 100
    assert generated.confirmed_commission_jpy is None
    assert generated.confirmed_missing_count == 1
    assert confirmed.row_count == 1
    assert confirmed.generated_commission_jpy == 100
    assert confirmed.confirmed_commission_jpy == 80
    assert confirmed.confirmed_missing_count == 0
    assert cancelled == RevenueObservedSum(
        event_type=cancelled.event_type,
        row_count=0,
        generated_commission_jpy=0,
        confirmed_commission_jpy=None,
        confirmed_missing_count=0,
    )
    assert adjusted.row_count == 0


def test_synthetic_period_is_observed_only_and_labeled() -> None:
    intake = intake_result()
    period = service_for(intake).dry_run(intake).period
    assert period.label.value == "SYNTHETIC_OBSERVED_RANGE"
    assert period.period_from == date(2026, 8, 1)
    assert period.period_to == date(2026, 8, 2)


def test_row_preview_never_contains_provider_event_key_or_raw_text() -> None:
    intake = intake_result()
    result = service_for(intake).dry_run(intake)
    annotations = result.previews[0].__annotations__
    assert "provider_event_key" not in annotations
    assert "raw" not in annotations
    assert "text" not in annotations
    assert "synthetic-event" not in repr(result)
    assert "synthetic-event" not in str(result)


def test_command_fingerprint_is_deterministic_and_binds_every_field() -> None:
    command = parse_command(intake_result())
    assert (
        command.canonical_fingerprint
        == parse_command(intake_result()).canonical_fingerprint
    )
    changed = replace(
        command, expected_max_cell_bytes=command.expected_max_cell_bytes + 1
    )
    assert changed.canonical_fingerprint != command.canonical_fingerprint


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_size", True),
        ("expected_row_count", True),
        ("expected_column_count", 7),
        ("expected_max_cell_bytes", 0),
        ("profile", "RAOS_ST1301_SYNTHETIC_V1"),
        ("source_sha256", "0" * 64),
    ],
)
def test_command_rejects_type_and_shape_bypass(field: str, value: object) -> None:
    values = {
        "intake_id": parse_command(intake_result()).intake_id,
        "site_id": parse_command(intake_result()).site_id,
        "source_sha256": parse_command(intake_result()).source_sha256,
        "source_size": parse_command(intake_result()).source_size,
        "profile": SyntheticRevenueProfile.RAOS_ST1301_SYNTHETIC_V1,
        "expected_row_count": parse_command(intake_result()).expected_row_count,
        "expected_column_count": 8,
        "expected_max_cell_bytes": parse_command(
            intake_result()
        ).expected_max_cell_bytes,
    }
    values[field] = value
    with pytest.raises(RevenueImportFailure):
        SyntheticRevenueParseCommand(**values)  # type: ignore[arg-type]


def test_values_are_frozen_redacted_and_nonpickle() -> None:
    command = parse_command(intake_result())
    with pytest.raises(FrozenInstanceError):
        command.source_size = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        pickle.dumps(command)
    assert repr(command) == "SyntheticRevenueParseCommand(<redacted-revenue-import>)"
    assert str(command) == "<redacted-revenue-import>"


def test_adapter_is_exactly_one_shot() -> None:
    intake = intake_result()
    command = parse_command(intake)
    adapter = RecordedRevenueParserAdapter(
        RecordedRevenueFixture(command=command, payload=SYNTHETIC_CSV)
    )
    adapter.parse(command)
    with pytest.raises(RevenueImportFailure) as caught:
        adapter.parse(command)
    assert caught.value.code is RevenueImportFailureCode.PARSER_REJECTED


def test_row_hash_is_exact_source_row_bytes_excluding_lf() -> None:
    import hashlib

    intake = intake_result()
    result = service_for(intake).dry_run(intake)
    assert result.previews[0].row_sha256 == Sha256Digest(
        hashlib.sha256(ROW_GENERATED).hexdigest()
    )
    assert result.previews[1].row_sha256 == Sha256Digest(
        hashlib.sha256(ROW_CONFIRMED).hexdigest()
    )
    assert result.previews[2].code is RevenueRowCode.EXACT_ROW_DUPLICATE
    assert result.previews[3].code is RevenueRowCode.EVENT_KEY_CONFLICT


class _CountingParser:
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, command: object) -> object:
        del command
        self.calls += 1
        raise AssertionError("must not be called")


def test_exact_source_duplicate_is_rejected_before_parser_io() -> None:
    parser = _CountingParser()
    service = RevenueImportService(parser=parser)  # type: ignore[arg-type]
    duplicate = intake_result(duplicate_status=DuplicateStatus.EXACT_DUPLICATE)

    with pytest.raises(RevenueImportFailure) as caught:
        service.dry_run(duplicate)

    assert caught.value.code is RevenueImportFailureCode.SOURCE_DUPLICATE_REJECTED
    assert parser.calls == 0
