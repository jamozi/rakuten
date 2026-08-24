"""Hostile Protocol collaborator checks for the ST-0502 application boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TypeVar, cast

import pytest

from raos.application.catalog.rakuten_item_search_runtime_v2 import (
    RakutenItemSearchRuntimeServiceV2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    CommitRecoveryOutcomeV2,
    IngestionSessionStateV2,
    IngestionStepOutcomeV2,
    ItemSearchCommitRecoveryV2,
    ItemSearchIngestionSessionV2,
    ItemSearchProviderObservationV2,
    ItemSearchRuntimeFailure,
    ItemSearchRuntimeFailureCode,
    ItemSearchStepCommandV2,
    ItemSearchWireRequestV2,
    ParsedItemSearchPageV2,
    PersistedItemSearchStepV2,
    ProviderFailureClassV2,
    ProviderModeV2,
    RawArchiveReceiptV2,
)
from raos.ports.rakuten_item_search_runtime_v2 import (
    ItemSearchIngestionUnitOfWorkStoreV2,
)

from runtime_v2_fixtures import (
    OBSERVED_AT_V2,
    SESSION_ID_V2,
    runtime_command_v2,
    runtime_exchange_v2,
    runtime_failure_observation_v2,
    runtime_plan_v2,
    runtime_provider_v2,
    runtime_service_v2,
    runtime_store_v2,
    runtime_success_observation_v2,
)


_CANARY = "ST0502-COLLABORATOR-CANARY-DO-NOT-ECHO"
_NO_REPLACEMENT = object()
_T = TypeVar("_T")


def _assert_sanitized(error: ItemSearchRuntimeFailure) -> None:
    assert _CANARY not in str(error)
    assert _CANARY not in repr(error)


class _HostileProvider:
    def __init__(
        self,
        observation: ItemSearchProviderObservationV2,
        *,
        failure_property: str | None = None,
        failure_occurrence: int = 1,
        fail_fetch: bool = False,
        replace_observation: bool = False,
    ) -> None:
        self._observation = observation
        self._failure_property = failure_property
        self._failure_occurrence = failure_occurrence
        self._fail_fetch = fail_fetch
        self._replace_observation = replace_observation
        self.mode_reads = 0
        self.action_reads = 0
        self.fetch_calls = 0

    def _property(self, name: str, count: int) -> None:
        if name == self._failure_property and count == self._failure_occurrence:
            raise RuntimeError(_CANARY)

    @property
    def mode(self) -> ProviderModeV2:
        self.mode_reads += 1
        self._property("mode", self.mode_reads)
        return ProviderModeV2.RECORDED_SYNTHETIC

    @property
    def external_action_count(self) -> int:
        self.action_reads += 1
        self._property("external_action_count", self.action_reads)
        return 0

    def fetch_once(
        self,
        request: ItemSearchWireRequestV2,
        *,
        observed_at: datetime,
    ) -> ItemSearchProviderObservationV2:
        del request, observed_at
        self.fetch_calls += 1
        if self._fail_fetch:
            raise RuntimeError(_CANARY)
        if self._replace_observation:
            return cast(ItemSearchProviderObservationV2, object())
        return self._observation


@pytest.mark.parametrize(
    ("failure_property", "failure_occurrence", "fail_fetch", "expected_fetches"),
    (
        ("mode", 1, False, 0),
        ("external_action_count", 1, False, 0),
        ("mode", 2, False, 0),
        ("external_action_count", 2, False, 0),
        (None, 1, True, 1),
        ("mode", 3, False, 1),
        ("external_action_count", 3, False, 1),
    ),
)
def test_provider_property_and_fetch_exceptions_are_sanitized_without_commit(
    tmp_path: Path,
    failure_property: str | None,
    failure_occurrence: int,
    fail_fetch: bool,
    expected_fetches: int,
) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    provider = _HostileProvider(
        runtime_success_observation_v2(request, observed_at=OBSERVED_AT_V2),
        failure_property=failure_property,
        failure_occurrence=failure_occurrence,
        fail_fetch=fail_fetch,
    )
    store = runtime_store_v2(tmp_path / "private")

    if failure_occurrence == 1 and failure_property is not None:
        with pytest.raises(ItemSearchRuntimeFailure) as captured:
            runtime_service_v2(provider=provider, store=store)
    else:
        service = runtime_service_v2(provider=provider, store=store)
        service.create_session(
            session_id=SESSION_ID_V2,
            plan=plan,
            created_at=OBSERVED_AT_V2,
        )
        with pytest.raises(ItemSearchRuntimeFailure) as captured:
            service.step_once(
                runtime_command_v2(
                    operation_index=0,
                    expected_version=0,
                    observed_at=OBSERVED_AT_V2,
                )
            )
        assert store.load_session(SESSION_ID_V2).version == 0

    assert captured.value.code is ItemSearchRuntimeFailureCode.PROVIDER_UNAVAILABLE
    _assert_sanitized(captured.value)
    assert provider.fetch_calls == expected_fetches


def test_forged_provider_return_is_contract_drift_without_store_mutation(
    tmp_path: Path,
) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    provider = _HostileProvider(
        runtime_success_observation_v2(request, observed_at=OBSERVED_AT_V2),
        replace_observation=True,
    )
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(provider=provider, store=store)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        service.step_once(
            runtime_command_v2(
                operation_index=0,
                expected_version=0,
                observed_at=OBSERVED_AT_V2,
            )
        )

    assert captured.value.code is ItemSearchRuntimeFailureCode.CONTRACT_DRIFT
    _assert_sanitized(captured.value)
    assert provider.fetch_calls == 1
    assert store.load_session(SESSION_ID_V2).version == 0


class _HostileStore:
    def __init__(self, delegate: ItemSearchIngestionUnitOfWorkStoreV2) -> None:
        self._delegate = delegate
        self.target: str | None = None
        self.target_occurrence = 1
        self.raise_after = False
        self.replacement: object = _NO_REPLACEMENT
        self._counts: dict[str, int] = {}

    @property
    def external_action_count(self) -> int:
        return 0

    def arm(
        self,
        target: str,
        *,
        occurrence: int = 1,
        raise_after: bool = False,
        replacement: object = _NO_REPLACEMENT,
    ) -> None:
        self.target = target
        self.target_occurrence = occurrence
        self.raise_after = raise_after
        self.replacement = replacement
        self._counts[target] = 0

    def _invoke(self, name: str, action: Callable[[], _T]) -> _T:
        count = self._counts.get(name, 0) + 1
        self._counts[name] = count
        selected = name == self.target and count == self.target_occurrence
        if selected and not self.raise_after and self.replacement is _NO_REPLACEMENT:
            raise RuntimeError(_CANARY)
        result = action()
        if selected and self.raise_after:
            raise RuntimeError(_CANARY)
        if selected and self.replacement is not _NO_REPLACEMENT:
            return cast(_T, self.replacement)
        return result

    def create_session(self, session: ItemSearchIngestionSessionV2) -> None:
        return self._invoke(
            "create_session",
            lambda: self._delegate.create_session(session),
        )

    def load_session(self, session_id: object) -> ItemSearchIngestionSessionV2:
        return self._invoke(
            "load_session",
            lambda: self._delegate.load_session(session_id),
        )

    def lookup_step(
        self,
        command: ItemSearchStepCommandV2,
    ) -> PersistedItemSearchStepV2 | None:
        return self._invoke(
            "lookup_step",
            lambda: self._delegate.lookup_step(command),
        )

    def recover_commit(
        self,
        command: ItemSearchStepCommandV2,
    ) -> ItemSearchCommitRecoveryV2:
        return self._invoke(
            "recover_commit",
            lambda: self._delegate.recover_commit(command),
        )

    def commit_success(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        observation: ItemSearchProviderObservationV2,
        page: ParsedItemSearchPageV2,
    ) -> PersistedItemSearchStepV2:
        return self._invoke(
            "commit_success",
            lambda: self._delegate.commit_success(
                command=command,
                before=before,
                after=after,
                request=request,
                observation=observation,
                page=page,
            ),
        )

    def commit_failure(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        failure_class: ProviderFailureClassV2,
        observation: ItemSearchProviderObservationV2 | None,
    ) -> PersistedItemSearchStepV2:
        return self._invoke(
            "commit_failure",
            lambda: self._delegate.commit_failure(
                command=command,
                before=before,
                after=after,
                request=request,
                failure_class=failure_class,
                observation=observation,
            ),
        )

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        return self._invoke(
            "read_raw",
            lambda: self._delegate.read_raw(receipt),
        )

    def read_page(
        self,
        *,
        receipt: RawArchiveReceiptV2,
        request: ItemSearchWireRequestV2,
    ) -> ParsedItemSearchPageV2:
        return self._invoke(
            "read_page",
            lambda: self._delegate.read_page(receipt=receipt, request=request),
        )


def _service_with_hostile_store(
    tmp_path: Path,
) -> tuple[
    object,
    _HostileStore,
    RakutenItemSearchRuntimeServiceV2,
]:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    provider = runtime_provider_v2(
        runtime_exchange_v2(
            request,
            runtime_success_observation_v2(request, observed_at=OBSERVED_AT_V2),
        )
    )
    store = _HostileStore(runtime_store_v2(tmp_path / "private"))
    service = runtime_service_v2(provider=provider, store=store)
    return provider, store, service


@pytest.mark.parametrize("target", ("create_session", "load_session"))
def test_store_create_and_load_exceptions_are_sanitized_before_provider_use(
    tmp_path: Path,
    target: str,
) -> None:
    provider, store, service = _service_with_hostile_store(tmp_path)
    store.arm(target)

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        service.create_session(
            session_id=SESSION_ID_V2,
            plan=runtime_plan_v2(),
            created_at=OBSERVED_AT_V2,
        )

    assert captured.value.code is ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE
    _assert_sanitized(captured.value)
    assert getattr(provider, "call_count") == 0


@pytest.mark.parametrize("target", ("lookup_step", "load_session"))
def test_store_read_exceptions_stop_before_provider_fetch(
    tmp_path: Path,
    target: str,
) -> None:
    provider, store, service = _service_with_hostile_store(tmp_path)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=runtime_plan_v2(),
        created_at=OBSERVED_AT_V2,
    )
    store.arm(target)

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        service.step_once(
            runtime_command_v2(
                operation_index=0,
                expected_version=0,
                observed_at=OBSERVED_AT_V2,
            )
        )

    assert captured.value.code is ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE
    _assert_sanitized(captured.value)
    assert getattr(provider, "call_count") == 0


@pytest.mark.parametrize("raise_after", (False, True))
def test_commit_exception_is_sanitized_unknown_and_recoverable(
    tmp_path: Path,
    raise_after: bool,
) -> None:
    provider, store, service = _service_with_hostile_store(tmp_path)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=runtime_plan_v2(),
        created_at=OBSERVED_AT_V2,
    )
    store.arm("commit_success", raise_after=raise_after)
    command = runtime_command_v2(
        operation_index=0,
        expected_version=0,
        observed_at=OBSERVED_AT_V2,
    )

    result = service.step_once(command)
    recovery = service.recover_commit(command)

    assert result.persisted.outcome is IngestionStepOutcomeV2.COMMIT_UNKNOWN
    assert _CANARY not in str(result)
    assert _CANARY not in repr(result)
    assert getattr(provider, "call_count") == 1
    assert recovery.outcome is (
        CommitRecoveryOutcomeV2.COMMITTED
        if raise_after
        else CommitRecoveryOutcomeV2.NOT_COMMITTED
    )


def test_commit_failure_exception_is_sanitized_as_unknown(tmp_path: Path) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    provider = runtime_provider_v2(
        runtime_exchange_v2(
            request,
            runtime_failure_observation_v2(
                request,
                observed_at=OBSERVED_AT_V2,
                status=500,
            ),
        )
    )
    store = _HostileStore(runtime_store_v2(tmp_path / "private"))
    service = runtime_service_v2(provider=provider, store=store)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    store.arm("commit_failure")

    result = service.step_once(
        runtime_command_v2(
            operation_index=0,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        )
    )

    assert result.persisted.outcome is IngestionStepOutcomeV2.COMMIT_UNKNOWN
    assert _CANARY not in str(result)
    assert _CANARY not in repr(result)
    assert provider.call_count == 1


def test_read_page_exception_is_sanitized_without_second_provider_fetch(
    tmp_path: Path,
) -> None:
    provider, store, service = _service_with_hostile_store(tmp_path)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=runtime_plan_v2(),
        created_at=OBSERVED_AT_V2,
    )
    command = runtime_command_v2(
        operation_index=0,
        expected_version=0,
        observed_at=OBSERVED_AT_V2,
    )
    service.step_once(command)
    store.arm("read_page")

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        service.step_once(command)

    assert captured.value.code is ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE
    _assert_sanitized(captured.value)
    assert getattr(provider, "call_count") == 1


@pytest.mark.parametrize(
    ("target", "expected_code", "requires_committed_step"),
    (
        ("load_session", ItemSearchRuntimeFailureCode.CONTRACT_DRIFT, False),
        ("lookup_step", ItemSearchRuntimeFailureCode.CONTRACT_DRIFT, False),
        ("commit_success", ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN, False),
        ("read_page", ItemSearchRuntimeFailureCode.CONTRACT_DRIFT, True),
    ),
)
def test_forged_store_returns_are_revalidated_at_every_read_boundary(
    tmp_path: Path,
    target: str,
    expected_code: ItemSearchRuntimeFailureCode,
    requires_committed_step: bool,
) -> None:
    provider, store, service = _service_with_hostile_store(tmp_path)
    if target == "load_session":
        store.arm(target, replacement=object())
        with pytest.raises(ItemSearchRuntimeFailure) as captured:
            service.create_session(
                session_id=SESSION_ID_V2,
                plan=runtime_plan_v2(),
                created_at=OBSERVED_AT_V2,
            )
        assert getattr(provider, "call_count") == 0
    else:
        service.create_session(
            session_id=SESSION_ID_V2,
            plan=runtime_plan_v2(),
            created_at=OBSERVED_AT_V2,
        )
        command = runtime_command_v2(
            operation_index=0,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        )
        if requires_committed_step:
            service.step_once(command)
        store.arm(target, replacement=object())
        if target == "commit_success":
            result = service.step_once(command)
            assert result.persisted.outcome is IngestionStepOutcomeV2.COMMIT_UNKNOWN
            assert _CANARY not in repr(result)
            return
        with pytest.raises(ItemSearchRuntimeFailure) as captured:
            service.step_once(command)

    assert captured.value.code is expected_code
    _assert_sanitized(captured.value)


@pytest.mark.parametrize("mutation", ("outcome_state", "missing_receipt"))
def test_exact_class_persisted_cross_field_forgery_is_rejected(
    tmp_path: Path,
    mutation: str,
) -> None:
    provider, store, service = _service_with_hostile_store(tmp_path)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=runtime_plan_v2(),
        created_at=OBSERVED_AT_V2,
    )
    command = runtime_command_v2(
        operation_index=0,
        expected_version=0,
        observed_at=OBSERVED_AT_V2,
    )
    committed = service.step_once(command).persisted
    forged = (
        replace(
            committed,
            session=replace(
                committed.session,
                state=IngestionSessionStateV2.FAILED,
            ),
        )
        if mutation == "outcome_state"
        else replace(committed, receipt=None)
    )
    store.arm("lookup_step", replacement=forged)

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        service.step_once(command)

    assert captured.value.code is ItemSearchRuntimeFailureCode.CONTRACT_DRIFT
    _assert_sanitized(captured.value)
    assert getattr(provider, "call_count") == 1


class _MutatingRequestProvider:
    mode = ProviderModeV2.RECORDED_SYNTHETIC
    external_action_count = 0

    def __init__(self, observation: ItemSearchProviderObservationV2) -> None:
        self._observation = observation

    def fetch_once(
        self,
        request: ItemSearchWireRequestV2,
        *,
        observed_at: datetime,
    ) -> ItemSearchProviderObservationV2:
        del observed_at
        object.__setattr__(request, "page", 2)
        return self._observation


class _MutatingCommitStore(_HostileStore):
    def commit_success(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        observation: ItemSearchProviderObservationV2,
        page: ParsedItemSearchPageV2,
    ) -> PersistedItemSearchStepV2:
        object.__setattr__(command, "expected_version", 1)
        return self._delegate.commit_success(
            command=command,
            before=before,
            after=after,
            request=request,
            observation=observation,
            page=page,
        )


class _BadActionCountStore(_HostileStore):
    def __init__(
        self,
        delegate: ItemSearchIngestionUnitOfWorkStoreV2,
        value: object,
    ) -> None:
        super().__init__(delegate)
        self._value = value

    @property
    def external_action_count(self) -> int:
        return cast(int, self._value)


class _BadActionCountProvider:
    mode = ProviderModeV2.RECORDED_SYNTHETIC

    def __init__(self, value: object) -> None:
        self._value = value

    @property
    def external_action_count(self) -> int:
        return cast(int, self._value)

    def fetch_once(
        self,
        request: ItemSearchWireRequestV2,
        *,
        observed_at: datetime,
    ) -> ItemSearchProviderObservationV2:
        del request, observed_at
        raise AssertionError("unreachable")


def test_provider_argument_mutation_fails_before_store_persistence(
    tmp_path: Path,
) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
    )
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(
        provider=_MutatingRequestProvider(observation),
        store=store,
    )
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        service.step_once(
            runtime_command_v2(
                operation_index=0,
                expected_version=0,
                observed_at=OBSERVED_AT_V2,
            )
        )
    assert captured.value.code is ItemSearchRuntimeFailureCode.CONTRACT_DRIFT
    assert store.load_session(SESSION_ID_V2).version == 0


def test_store_argument_mutation_fails_before_delegate_persistence(
    tmp_path: Path,
) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
    )
    delegate = runtime_store_v2(tmp_path / "private")
    store = _MutatingCommitStore(delegate)
    service = runtime_service_v2(
        provider=runtime_provider_v2(runtime_exchange_v2(request, observation)),
        store=store,
    )
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )

    result = service.step_once(
        runtime_command_v2(
            operation_index=0,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        )
    )
    assert result.persisted.outcome is IngestionStepOutcomeV2.COMMIT_UNKNOWN
    assert delegate.load_session(SESSION_ID_V2).version == 0


@pytest.mark.parametrize("value", (False, True, 1))
def test_bool_or_nonzero_collaborator_action_count_is_rejected(
    tmp_path: Path,
    value: object,
) -> None:
    delegate = runtime_store_v2(tmp_path / f"store-{value!s}")
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
    )
    with pytest.raises(ItemSearchRuntimeFailure):
        runtime_service_v2(
            provider=runtime_provider_v2(runtime_exchange_v2(request, observation)),
            store=_BadActionCountStore(delegate, value),
        )
    with pytest.raises(ItemSearchRuntimeFailure):
        runtime_service_v2(
            provider=_BadActionCountProvider(value),
            store=delegate,
        )


def test_bool_observation_external_action_count_is_invalid() -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
    )
    with pytest.raises(ItemSearchRuntimeFailure):
        replace(observation, external_actions=cast(int, False))
