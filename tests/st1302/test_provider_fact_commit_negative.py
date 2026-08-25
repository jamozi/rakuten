"""Adversarial fail-closed checks for the executable-local ST-1302 seam."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

import pytest

from raos.adapters.recorded_provider_fact_commit import (
    RecordedCommitMode,
    RecordedProviderFactCommitAdapter,
    load_recorded_provider_fact_commit_fixture,
)
from raos.application.finance.provider_fact_commit import ProviderFactCommitService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.provider_fact_commit import (
    CanonicalCommissionEventType,
    JpyAmount,
    LocalIdempotencyKey,
    ProviderFactCommitFailure,
    ProviderFactCommitFailureCode,
    ProviderFactCommitReason,
    ProviderFactStatusSummary,
    RecordedCommissionEvent,
    RecordedRevenueDryRunBundle,
    build_provider_fact_commit_result,
)
from raos.domain.finance.revenue_import import RevenueRowCode
from raos.domain.ops.object_intake import Sha256Digest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPOSITORY_ROOT
    / "changes/st-1302/fixtures/provider-fact-commit-recorded.synthetic.v1.json"
)


def _scenario():  # type: ignore[no-untyped-def]
    return load_recorded_provider_fact_commit_fixture(FIXTURE_PATH.resolve())


def _failure_code(call: Callable[[], object]) -> ProviderFactCommitFailureCode:
    with pytest.raises(ProviderFactCommitFailure) as caught:
        call()
    assert str(caught.value) == caught.value.code.value
    return caught.value.code


@pytest.mark.parametrize(
    ("replacement", "expected"),
    [
        (
            {"expected_source_sha256": Sha256Digest("0" * 64)},
            ProviderFactCommitFailureCode.SOURCE_HASH_MISMATCH,
        ),
        (
            {"expected_local_preview_binding_sha256": Sha256Digest("1" * 64)},
            ProviderFactCommitFailureCode.PREVIEW_BINDING_MISMATCH,
        ),
        (
            {"expected_accepted_count": 3, "expected_confirmed_missing_count": 1},
            ProviderFactCommitFailureCode.COUNT_MISMATCH,
        ),
        (
            {"expected_generated_commission_jpy": JpyAmount(Decimal("201"))},
            ProviderFactCommitFailureCode.AMOUNT_MISMATCH,
        ),
        (
            {"expected_period_to": date(2026, 8, 3)},
            ProviderFactCommitFailureCode.PERIOD_MISMATCH,
        ),
    ],
)
def test_request_hash_count_amount_and_period_mismatch_fail_closed(
    replacement: dict[str, object],
    expected: ProviderFactCommitFailureCode,
) -> None:
    scenario = _scenario()
    request = replace(scenario.request, **replacement)
    authorization = replace(
        scenario.authorization,
        request_sha256=request.request_sha256,
    )
    assert (
        _failure_code(
            lambda: build_provider_fact_commit_result(
                request=request,
                bundle=scenario.bundle,
                authorization=authorization,
            )
        )
        is expected
    )


def test_status_summary_mismatch_is_not_hidden_by_aggregate_totals() -> None:
    scenario = _scenario()
    first = scenario.request.expected_status_summaries[0]
    changed = ProviderFactStatusSummary(
        event_type=first.event_type,
        row_count=first.row_count,
        generated_commission_jpy=JpyAmount(Decimal("101")),
        confirmed_commission_jpy=first.confirmed_commission_jpy,
        confirmed_missing_count=first.confirmed_missing_count,
    )
    request = replace(
        scenario.request,
        expected_status_summaries=(
            changed,
            *scenario.request.expected_status_summaries[1:],
        ),
    )
    authorization = replace(
        scenario.authorization,
        request_sha256=request.request_sha256,
    )
    assert (
        _failure_code(
            lambda: build_provider_fact_commit_result(
                request=request,
                bundle=scenario.bundle,
                authorization=authorization,
            )
        )
        is ProviderFactCommitFailureCode.STATUS_SUMMARY_MISMATCH
    )


def test_accepted_row_coverage_or_identity_drift_is_rejected() -> None:
    scenario = _scenario()
    changed_row = replace(
        scenario.bundle.accepted_rows[0],
        provider_event_key=scenario.bundle.accepted_rows[1].provider_event_key,
    )
    assert (
        _failure_code(
            lambda: RecordedRevenueDryRunBundle(
                dry_run=scenario.bundle.dry_run,
                accepted_rows=(changed_row, scenario.bundle.accepted_rows[1]),
                prepared_by_principal_id=scenario.bundle.prepared_by_principal_id,
            )
        )
        is ProviderFactCommitFailureCode.ACCEPTED_ROW_BINDING_INVALID
    )


def test_recorded_adapter_requires_the_exact_full_st1301_dry_run() -> None:
    scenario = _scenario()
    previews = list(scenario.bundle.dry_run.previews)
    previews[-1] = replace(previews[-1], code=RevenueRowCode.INVALID_ROW)
    changed_dry_run = replace(
        scenario.bundle.dry_run,
        previews=tuple(previews),
    )
    changed_bundle = RecordedRevenueDryRunBundle(
        dry_run=changed_dry_run,
        accepted_rows=scenario.bundle.accepted_rows,
        prepared_by_principal_id=scenario.bundle.prepared_by_principal_id,
    )
    assert changed_bundle.local_preview_binding_sha256 == (
        scenario.bundle.local_preview_binding_sha256
    )
    adapter = RecordedProviderFactCommitAdapter(
        environment=RuntimeEnvironment.CI,
        scenario=scenario,
    )
    assert (
        _failure_code(lambda: adapter.authorize(scenario.request, changed_bundle))
        is ProviderFactCommitFailureCode.AUTHORIZATION_INVALID
    )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (
            lambda scenario: replace(
                scenario.authorization,
                step_up_authenticated_at=(
                    scenario.request.requested_at - timedelta(seconds=301)
                ),
            ),
            ProviderFactCommitFailureCode.STEP_UP_STALE,
        ),
        (
            lambda scenario: replace(
                scenario.authorization,
                principal_id=scenario.bundle.prepared_by_principal_id,
            ),
            ProviderFactCommitFailureCode.ROLE_SEPARATION_REQUIRED,
        ),
        (
            lambda scenario: replace(
                scenario.authorization,
                site_id=UUID("018f3e90-7b00-7000-8000-000000009999"),
            ),
            ProviderFactCommitFailureCode.SITE_SCOPE_MISMATCH,
        ),
        (
            lambda scenario: replace(
                scenario.authorization,
                request_sha256=Sha256Digest("9" * 64),
            ),
            ProviderFactCommitFailureCode.AUTHORIZATION_INVALID,
        ),
    ],
)
def test_authorization_step_up_scope_and_role_separation_are_enforced(
    change: Callable[[Any], object],
    expected: ProviderFactCommitFailureCode,
) -> None:
    scenario = _scenario()
    authorization = change(scenario)
    assert (
        _failure_code(
            lambda: build_provider_fact_commit_result(
                request=scenario.request,
                bundle=scenario.bundle,
                authorization=authorization,  # type: ignore[arg-type]
            )
        )
        is expected
    )


def test_same_key_changed_request_is_conflict_and_source_recommit_is_rejected() -> None:
    scenario = _scenario()
    adapter = RecordedProviderFactCommitAdapter(
        environment=RuntimeEnvironment.CI,
        scenario=scenario,
    )
    adapter.commit(scenario.request, scenario.bundle, scenario.authorization)
    changed_request = replace(
        scenario.request,
        reason=ProviderFactCommitReason("A different exact local replay reason."),
    )
    assert (
        _failure_code(
            lambda: adapter.commit(
                changed_request,
                scenario.bundle,
                scenario.authorization,
            )
        )
        is ProviderFactCommitFailureCode.IDEMPOTENCY_CONFLICT
    )
    new_key_request = replace(
        scenario.request,
        idempotency_key=LocalIdempotencyKey("st1302-recorded-synthetic-9999"),
    )
    assert (
        _failure_code(
            lambda: adapter.commit(
                new_key_request,
                scenario.bundle,
                scenario.authorization,
            )
        )
        is ProviderFactCommitFailureCode.SOURCE_ALREADY_COMMITTED
    )


def test_atomic_failure_publishes_no_partial_result() -> None:
    scenario = _scenario()
    adapter = RecordedProviderFactCommitAdapter(
        environment=RuntimeEnvironment.CI,
        scenario=scenario,
        mode=RecordedCommitMode.FAIL_BEFORE_ATOMIC_SWAP,
    )
    service = ProviderFactCommitService(
        environment=RuntimeEnvironment.CI,
        authorization_source=adapter,
        store=adapter,
    )
    assert (
        _failure_code(
            lambda: service.execute(
                request=scenario.request,
                bundle=scenario.bundle,
            )
        )
        is ProviderFactCommitFailureCode.ATOMIC_COMMIT_UNAVAILABLE
    )
    snapshot = adapter.snapshot()
    assert (
        snapshot.replay_count,
        snapshot.source_count,
        snapshot.fact_count,
        snapshot.commission_event_count,
        snapshot.audit_count,
        snapshot.outbox_count,
    ) == (0, 0, 0, 0, 0, 0)


def test_service_rejects_semantically_tampered_result_even_when_hash_list_matches() -> (
    None
):
    scenario = _scenario()
    expected = build_provider_fact_commit_result(
        request=scenario.request,
        bundle=scenario.bundle,
        authorization=scenario.authorization,
    )
    changed_fact = replace(
        expected.facts[0],
        generated_commission_jpy=JpyAmount(Decimal("999")),
    )
    changed_result = replace(
        expected,
        facts=(changed_fact, *expected.facts[1:]),
    )
    assert changed_result.canonical_bytes() == expected.canonical_bytes()

    class TamperedStore:
        def commit(self, request, bundle, authorization):  # type: ignore[no-untyped-def]
            del request, bundle, authorization
            return changed_result

    adapter = RecordedProviderFactCommitAdapter(
        environment=RuntimeEnvironment.CI,
        scenario=scenario,
    )
    service = ProviderFactCommitService(
        environment=RuntimeEnvironment.CI,
        authorization_source=adapter,
        store=TamperedStore(),
    )
    assert (
        _failure_code(
            lambda: service.execute(
                request=scenario.request,
                bundle=scenario.bundle,
            )
        )
        is ProviderFactCommitFailureCode.OUTCOME_MISMATCH
    )


@pytest.mark.parametrize(
    "environment",
    [
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ],
)
def test_nonlocal_environments_are_rejected(environment: RuntimeEnvironment) -> None:
    scenario = _scenario()
    assert (
        _failure_code(
            lambda: RecordedProviderFactCommitAdapter(
                environment=environment,
                scenario=scenario,
            )
        )
        is ProviderFactCommitFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    )


@pytest.mark.parametrize(
    "value",
    [0, 1.0, Decimal("1.1"), Decimal("NaN"), Decimal("Infinity"), Decimal("-1")],
)
def test_jpy_amount_rejects_coercion_fraction_nonfinite_and_negative(
    value: object,
) -> None:
    assert (
        _failure_code(lambda: JpyAmount(value))  # type: ignore[arg-type]
        is ProviderFactCommitFailureCode.INVALID_ARGUMENT
    )


def test_canonical_commission_mapping_cannot_be_invented() -> None:
    scenario = _scenario()
    result = build_provider_fact_commit_result(
        request=scenario.request,
        bundle=scenario.bundle,
        authorization=scenario.authorization,
    )
    event = result.commission_events[0]
    assert (
        _failure_code(
            lambda: RecordedCommissionEvent(
                event_sha256=event.event_sha256,
                fact_sha256=event.fact_sha256,
                source_event_type=event.source_event_type,
                canonical_event_type=CanonicalCommissionEventType.GENERATED,
                mapping=event.mapping,
                provider_occurred_at=event.provider_occurred_at,
                generated_commission_jpy=event.generated_commission_jpy,
                confirmed_commission_jpy=event.confirmed_commission_jpy,
            )
        )
        is ProviderFactCommitFailureCode.INVALID_ARGUMENT
    )


def _write_fixture(tmp_path: Path, value: object) -> Path:
    path = (tmp_path / "fixture.json").resolve()
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return path


def test_fixture_duplicate_unknown_and_invalid_typed_auth_fail_closed(
    tmp_path: Path,
) -> None:
    original = FIXTURE_PATH.read_text(encoding="utf-8")
    duplicate = (tmp_path / "duplicate.json").resolve()
    duplicate.write_text(
        original.replace(
            '"schema_version": "1.0.0",',
            '"schema_version": "1.0.0", "schema_version": "1.0.0",',
            1,
        ),
        encoding="utf-8",
    )
    assert (
        _failure_code(lambda: load_recorded_provider_fact_commit_fixture(duplicate))
        is ProviderFactCommitFailureCode.FIXTURE_INVALID
    )
    for field, value in (("role", "ADMIN"), ("mfa_state", "NOT_SATISFIED")):
        document = json.loads(original)
        document["authorization"][field] = value
        path = _write_fixture(tmp_path, document)
        assert (
            _failure_code(
                lambda path=path: load_recorded_provider_fact_commit_fixture(path)
            )
            is ProviderFactCommitFailureCode.FIXTURE_INVALID
        )
    document = json.loads(original)
    document["unknown"] = False
    path = _write_fixture(tmp_path, document)
    assert (
        _failure_code(lambda: load_recorded_provider_fact_commit_fixture(path))
        is ProviderFactCommitFailureCode.FIXTURE_INVALID
    )


def test_fixture_symlink_and_relative_path_are_rejected(
    tmp_path: Path,
) -> None:
    link = (tmp_path / "fixture-link.json").resolve()
    link.symlink_to(FIXTURE_PATH)
    for path in (link, Path("relative-fixture.json")):
        assert (
            _failure_code(
                lambda path=path: load_recorded_provider_fact_commit_fixture(path)
            )
            is ProviderFactCommitFailureCode.FIXTURE_INVALID
        )
