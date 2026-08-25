"""Executable-local happy-path and boundary checks for ST-1302."""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
import pickle

import pytest

from raos.adapters.recorded_provider_fact_commit import (
    RecordedProviderFactCommitAdapter,
    load_recorded_provider_fact_commit_fixture,
)
from raos.application.finance.provider_fact_commit import ProviderFactCommitService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.provider_fact_commit import (
    ExternalExecutionStatus,
    LocalMappingState,
    ProviderFactCommitExecution,
    RecordedCommitState,
)
from raos.domain.finance.revenue_import import RevenueEventType


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPOSITORY_ROOT
    / "changes/st-1302/fixtures/provider-fact-commit-recorded.synthetic.v1.json"
)
EXPECTED_FIXTURE_SHA256 = (
    "1839d9bdc4a5dfae3008e0f285bc36f45e48ef6b95b2dfd15ad7c4984cba3cb2"
)
EXPECTED_PREVIEW_BINDING_SHA256 = (
    "4ca67982a8faf600be644e950cd2cdd8826df069f9d6c3d4633550e0d6f6b5ac"
)
EXPECTED_RESULT_SHA256 = (
    "882a330bdc6485d424d55033c0cddbe1748b8b4b3b0751ddf3e4682ef574f7d0"
)


def _scenario():  # type: ignore[no-untyped-def]
    return load_recorded_provider_fact_commit_fixture(FIXTURE_PATH.resolve())


def _execute():  # type: ignore[no-untyped-def]
    scenario = _scenario()
    adapter = RecordedProviderFactCommitAdapter(
        environment=RuntimeEnvironment.CI,
        scenario=scenario,
    )
    service = ProviderFactCommitService(
        environment=RuntimeEnvironment.CI,
        authorization_source=adapter,
        store=adapter,
    )
    result = service.execute(request=scenario.request, bundle=scenario.bundle)
    return scenario, adapter, service, result


def test_fixture_binds_exact_st1301_dry_run_and_recorded_rows() -> None:
    scenario = _scenario()
    assert scenario.fixture_sha256.value == EXPECTED_FIXTURE_SHA256
    assert (
        scenario.bundle.local_preview_binding_sha256.value
        == EXPECTED_PREVIEW_BINDING_SHA256
    )
    assert scenario.request.expected_local_preview_binding_sha256 == (
        scenario.bundle.local_preview_binding_sha256
    )
    assert scenario.request.expected_source_sha256 == (
        scenario.bundle.dry_run.source.source_sha256
    )
    assert [row.row_no for row in scenario.bundle.accepted_rows] == [2, 3]
    assert [row.row_sha256 for row in scenario.bundle.accepted_rows] == [
        preview.row_sha256
        for preview in scenario.bundle.dry_run.previews
        if preview.status.value == "ACCEPTED"
    ]


def test_commit_produces_exact_immutable_local_exchange() -> None:
    scenario, adapter, _service, result = _execute()
    assert result.result_sha256.value == EXPECTED_RESULT_SHA256
    assert result.execution is ProviderFactCommitExecution.RECORDED_SYNTHETIC_ONLY
    assert result.commit_state is RecordedCommitState.PROCESS_LOCAL_ATOMIC_COMMITTED
    assert result.mapping is LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED
    assert tuple(fact.status for fact in result.facts) == (
        RevenueEventType.GENERATED,
        RevenueEventType.CONFIRMED,
    )
    assert tuple(event.source_event_type for event in result.commission_events) == (
        RevenueEventType.GENERATED,
        RevenueEventType.CONFIRMED,
    )
    assert all(event.canonical_event_type is None for event in result.commission_events)
    assert all(
        event.mapping is LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED
        for event in result.commission_events
    )
    assert len(result.audit.audit_sha256.value) == 64
    assert len(result.outbox) == 3
    snapshot = adapter.snapshot()
    assert (
        snapshot.source_count,
        snapshot.fact_count,
        snapshot.commission_event_count,
        snapshot.audit_count,
        snapshot.outbox_count,
    ) == (1, 2, 2, 1, 3)
    assert snapshot.result_sha256s == (result.result_sha256,)
    assert result.request_sha256 == scenario.request.request_sha256


def test_decimal_jpy_and_missingness_are_never_coerced_or_zero_filled() -> None:
    scenario, _adapter, _service, result = _execute()
    assert type(scenario.bundle.generated_commission_jpy.value) is Decimal
    assert scenario.bundle.generated_commission_jpy.value == Decimal("200")
    assert scenario.bundle.confirmed_commission_jpy is not None
    assert scenario.bundle.confirmed_commission_jpy.value == Decimal("80")
    assert scenario.bundle.confirmed_missing_count == 1
    generated, confirmed = result.facts
    assert generated.confirmed_commission_jpy is None
    assert confirmed.confirmed_commission_jpy is not None
    assert confirmed.confirmed_commission_jpy.value == Decimal("80")
    assert [summary.event_type for summary in result.status_summaries] == list(
        RevenueEventType
    )


def test_same_key_same_request_replays_the_identical_result() -> None:
    scenario, adapter, service, result = _execute()
    replay = service.execute(request=scenario.request, bundle=scenario.bundle)
    assert replay is result
    assert replay.canonical_bytes() == result.canonical_bytes()
    snapshot = adapter.snapshot()
    assert snapshot.source_count == 1
    assert snapshot.replay_count == 1


def test_all_external_authority_remains_false_and_not_executed() -> None:
    _scenario_value, _adapter, _service, result = _execute()
    authority = result.authority
    boolean_fields = (
        authority.database_write_authorized,
        authority.provider_call_authorized,
        authority.network_authorized,
        authority.publication_authorized,
        authority.live_authorized,
        authority.staging_authorized,
        authority.release_authorized,
        authority.production_authorized,
    )
    execution_fields = (
        authority.database,
        authority.provider,
        authority.network,
        authority.publication,
        authority.live,
        authority.staging,
        authority.release,
        authority.production,
    )
    assert boolean_fields == (False,) * len(boolean_fields)
    assert execution_fields == (ExternalExecutionStatus.NOT_EXECUTED,) * len(
        execution_fields
    )


def test_sensitive_values_are_redacted_and_generic_serialization_is_forbidden() -> None:
    scenario, adapter, _service, result = _execute()
    canaries = (
        scenario.bundle.accepted_rows[0].provider_event_key.value,
        scenario.request.idempotency_key.value,
        scenario.request.reason.value,
    )
    values = (
        scenario.bundle.accepted_rows[0].provider_event_key,
        scenario.request.idempotency_key,
        scenario.request.reason,
        scenario,
        adapter,
        result,
    )
    rendered = " ".join(f"{value!r} {value}" for value in values)
    canonical = result.canonical_bytes().decode("ascii")
    assert all(canary not in rendered for canary in canaries)
    assert all(canary not in canonical for canary in canaries)
    for value in values:
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_runtime_layers_import_no_network_database_process_or_provider_clients() -> (
    None
):
    paths = (
        "python/raos/domain/finance/provider_fact_commit.py",
        "python/raos/ports/provider_fact_commit.py",
        "python/raos/application/finance/provider_fact_commit.py",
        "python/raos/adapters/recorded_provider_fact_commit.py",
    )
    forbidden = {
        "asyncio",
        "boto3",
        "httpx",
        "os",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "urllib",
    }
    for relative in paths:
        tree = ast.parse((REPOSITORY_ROOT / relative).read_bytes())
        imported = {
            alias.name.split(".", maxsplit=1)[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert imported.isdisjoint(forbidden), relative
