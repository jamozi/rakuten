"""Hostile collaborator and denied-network checks for ST-0503 V2."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import socket
from typing import NoReturn, cast

import pytest

from raos.application.catalog.catalog_normalization_runtime_v2 import (
    CatalogNormalizationRuntimeServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CatalogCommitRecoveryOutcomeV2,
    CatalogCommitRecoveryV2,
    CatalogNormalizationBatchV2,
    CatalogNormalizationCommandV2,
    CatalogNormalizationRuntimeFailure,
    CatalogNormalizationRuntimeFailureCode,
    CatalogNormalizedOutboxEventV2,
    CatalogSourceModeV2,
    PersistedCatalogNormalizationV2,
    catalog_normalization_batch_from_mapping_v2,
    catalog_normalization_batch_mapping_v2,
    normalize_persisted_item_search_page_v2,
    persisted_catalog_normalization_from_mapping_v2,
    persisted_catalog_normalization_mapping_v2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ItemSearchWireRequestV2,
    ParsedItemSearchPageV2,
    RawArchiveReceiptV2,
)
from raos.ports.catalog_normalization_runtime_v2 import (
    CatalogNormalizationUnitOfWorkStoreV2,
)

from runtime_v2_fixtures import normalization_store_v2, source_fixture_v2


CANARY = "AKIA-DO-NOT-ECHO-ST0503-HOSTILE"


class _ExplodingSource:
    @property
    def mode(self) -> CatalogSourceModeV2:
        return CatalogSourceModeV2.RECORDED_PERSISTED

    @property
    def external_action_count(self) -> int:
        return 0

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        del receipt
        raise RuntimeError(CANARY)

    def read_page(
        self,
        *,
        receipt: RawArchiveReceiptV2,
        request: ItemSearchWireRequestV2,
    ) -> ParsedItemSearchPageV2:
        del receipt, request
        raise AssertionError("unreachable")


class _ForgedPageSource:
    @property
    def mode(self) -> CatalogSourceModeV2:
        return CatalogSourceModeV2.RECORDED_PERSISTED

    @property
    def external_action_count(self) -> int:
        return 0

    def __init__(self, raw_body: bytes) -> None:
        self.raw_body = raw_body

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        del receipt
        return self.raw_body

    def read_page(
        self,
        *,
        receipt: RawArchiveReceiptV2,
        request: ItemSearchWireRequestV2,
    ) -> ParsedItemSearchPageV2:
        del receipt, request
        return object.__new__(ParsedItemSearchPageV2)


class _ForgedFailureSource(_ExplodingSource):
    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        del receipt
        raise object.__new__(CatalogNormalizationRuntimeFailure)


class _ForgedStore:
    @property
    def external_action_count(self) -> int:
        return 0

    def lookup(
        self, command: CatalogNormalizationCommandV2
    ) -> PersistedCatalogNormalizationV2 | None:
        del command
        return object.__new__(PersistedCatalogNormalizationV2)

    def commit(
        self,
        *,
        command: CatalogNormalizationCommandV2,
        batch: CatalogNormalizationBatchV2,
        event: CatalogNormalizedOutboxEventV2,
    ) -> PersistedCatalogNormalizationV2:
        del command, batch, event
        raise AssertionError("unreachable")

    def recover_commit(
        self, command: CatalogNormalizationCommandV2
    ) -> CatalogCommitRecoveryV2:
        del command
        raise AssertionError("unreachable")

    def load_batch(self, batch_id: object) -> CatalogNormalizationBatchV2:
        del batch_id
        raise AssertionError("unreachable")

    def load_snapshot(self, snapshot_id: object) -> object:
        del snapshot_id
        raise AssertionError("unreachable")

    def load_candidate(self, candidate_id: object) -> object:
        del candidate_id
        raise AssertionError("unreachable")

    def load_offer(self, offer_id: object) -> object:
        del offer_id
        raise AssertionError("unreachable")

    def list_observations(self, offer_id: object) -> tuple[()]:
        del offer_id
        raise AssertionError("unreachable")

    def load_outbox(self, event_id: object) -> CatalogNormalizedOutboxEventV2:
        del event_id
        raise AssertionError("unreachable")


class _ForgedRecoveryStore(_ForgedStore):
    def recover_commit(
        self, command: CatalogNormalizationCommandV2
    ) -> CatalogCommitRecoveryV2:
        del command
        return object.__new__(CatalogCommitRecoveryV2)


def _never_network(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise AssertionError("network attempted")


def _assert_sanitized(
    caught: pytest.ExceptionInfo[CatalogNormalizationRuntimeFailure],
    code: CatalogNormalizationRuntimeFailureCode,
) -> None:
    assert caught.value.code is code
    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_arbitrary_source_exception_is_sanitized_and_page_is_not_called(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=_ExplodingSource(),
        store=normalization_store_v2(tmp_path),
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_sanitized(caught, CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE)


def test_forged_exact_class_page_is_revalidated_and_rejected(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)
    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=_ForgedPageSource(fixture.raw_body),
        store=normalization_store_v2(tmp_path),
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_sanitized(caught, CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY)


def test_forged_exact_class_exception_is_sanitized_to_boundary_code(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=_ForgedFailureSource(),
        store=normalization_store_v2(tmp_path),
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_sanitized(caught, CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE)


def test_forged_exact_class_store_result_is_revalidated_and_rejected(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=fixture.source,
        store=cast(CatalogNormalizationUnitOfWorkStoreV2, _ForgedStore()),
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    assert caught.value.code is CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE


def test_forged_exact_class_recovery_is_revalidated_and_rejected(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=fixture.source,
        store=cast(
            CatalogNormalizationUnitOfWorkStoreV2,
            _ForgedRecoveryStore(),
        ),
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.recover_commit(fixture.command)

    assert caught.value.code is CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE


def test_valid_exact_page_with_receipt_drift_fails_integrity(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)

    class _DriftSource:
        mode = CatalogSourceModeV2.RECORDED_PERSISTED
        external_action_count = 0

        def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
            del receipt
            return fixture.raw_body

        def read_page(
            self,
            *,
            receipt: RawArchiveReceiptV2,
            request: ItemSearchWireRequestV2,
        ) -> ParsedItemSearchPageV2:
            del receipt, request
            return replace(fixture.page, raw_sha256="0" * 64)

    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=_DriftSource(),
        store=normalization_store_v2(tmp_path),
    )
    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)
    assert caught.value.code is CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY


def test_recorded_runtime_succeeds_when_socket_is_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    monkeypatch.setattr(socket, "socket", _never_network)
    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=fixture.source,
        store=normalization_store_v2(tmp_path),
    )

    result = service.normalize(fixture.command)

    assert result.external_actions == 0
    assert result.persisted.batch.external_actions == 0


def test_idempotent_store_hit_still_revalidates_the_exact_source_archive(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)

    class _MutableSource:
        mode = CatalogSourceModeV2.RECORDED_PERSISTED
        external_action_count = 0
        fail = False

        def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
            if self.fail:
                raise RuntimeError(CANARY)
            return fixture.source.read_raw(receipt)

        def read_page(
            self,
            *,
            receipt: RawArchiveReceiptV2,
            request: ItemSearchWireRequestV2,
        ) -> ParsedItemSearchPageV2:
            return fixture.source.read_page(receipt=receipt, request=request)

    source = _MutableSource()
    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=source,
        store=normalization_store_v2(tmp_path),
    )
    service.normalize(fixture.command)
    source.fail = True

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_sanitized(caught, CatalogNormalizationRuntimeFailureCode.SOURCE_UNAVAILABLE)


def test_source_receipt_mutation_is_detected_at_the_call_boundary(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)

    class _MutatingSource:
        mode = CatalogSourceModeV2.RECORDED_PERSISTED
        external_action_count = 0

        def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
            object.__setattr__(receipt, "page", receipt.page + 1)
            return fixture.raw_body

        def read_page(
            self,
            *,
            receipt: RawArchiveReceiptV2,
            request: ItemSearchWireRequestV2,
        ) -> ParsedItemSearchPageV2:
            del receipt, request
            raise AssertionError("mutated receipt must stop before page read")

    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=_MutatingSource(),
        store=normalization_store_v2(tmp_path),
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_sanitized(caught, CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH)


def test_store_command_mutation_is_detected_at_the_call_boundary(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)

    class _MutatingLookupStore(_ForgedStore):
        def lookup(
            self, command: CatalogNormalizationCommandV2
        ) -> PersistedCatalogNormalizationV2 | None:
            object.__setattr__(command, "payload_fingerprint", "0" * 64)
            return None

    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=fixture.source,
        store=cast(CatalogNormalizationUnitOfWorkStoreV2, _MutatingLookupStore()),
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_sanitized(caught, CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE)


def test_store_batch_mutation_cannot_be_recovered_as_an_exact_commit(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)

    class _MutatingCommitStore(_ForgedStore):
        def lookup(
            self, command: CatalogNormalizationCommandV2
        ) -> PersistedCatalogNormalizationV2 | None:
            del command
            return None

        def commit(
            self,
            *,
            command: CatalogNormalizationCommandV2,
            batch: CatalogNormalizationBatchV2,
            event: CatalogNormalizedOutboxEventV2,
        ) -> PersistedCatalogNormalizationV2:
            del command, event
            object.__setattr__(batch, "external_actions", 1)
            return object.__new__(PersistedCatalogNormalizationV2)

        def recover_commit(
            self, command: CatalogNormalizationCommandV2
        ) -> CatalogCommitRecoveryV2:
            del command
            return CatalogCommitRecoveryV2(
                outcome=CatalogCommitRecoveryOutcomeV2.NOT_COMMITTED,
                persisted=None,
            )

    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=fixture.source,
        store=cast(CatalogNormalizationUnitOfWorkStoreV2, _MutatingCommitStore()),
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_sanitized(caught, CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN)


def test_source_and_store_action_count_spoofing_fail_closed(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)

    class _ActionSource:
        mode = CatalogSourceModeV2.RECORDED_PERSISTED

        def __init__(self) -> None:
            self.actions = 0

        @property
        def external_action_count(self) -> int:
            return self.actions

        def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
            del receipt
            self.actions = 1
            return fixture.raw_body

        def read_page(
            self,
            *,
            receipt: RawArchiveReceiptV2,
            request: ItemSearchWireRequestV2,
        ) -> ParsedItemSearchPageV2:
            del receipt, request
            raise AssertionError("action drift must stop before page read")

    source_service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=_ActionSource(),
        store=normalization_store_v2(tmp_path / "source-actions"),
    )
    with pytest.raises(CatalogNormalizationRuntimeFailure) as source:
        source_service.normalize(fixture.command)
    _assert_sanitized(source, CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH)

    class _ActionStore(_ForgedStore):
        def __init__(self) -> None:
            self.actions = 0

        @property
        def external_action_count(self) -> int:
            return self.actions

        def lookup(
            self, command: CatalogNormalizationCommandV2
        ) -> PersistedCatalogNormalizationV2 | None:
            del command
            self.actions = 1
            return None

    store_service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=fixture.source,
        store=cast(CatalogNormalizationUnitOfWorkStoreV2, _ActionStore()),
    )
    with pytest.raises(CatalogNormalizationRuntimeFailure) as store:
        store_service.normalize(fixture.command)
    _assert_sanitized(store, CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE)


def test_forged_chain_hash_is_recomputed_instead_of_trusted(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)
    real_store = normalization_store_v2(tmp_path)
    persisted = (
        CatalogNormalizationRuntimeServiceV2(
            environment=RuntimeEnvironment.CI,
            source=fixture.source,
            store=real_store,
        )
        .normalize(fixture.command)
        .persisted
    )
    forged = persisted_catalog_normalization_from_mapping_v2(
        persisted_catalog_normalization_mapping_v2(persisted)
    )
    object.__setattr__(forged, "chain_hash", "f" * 64)

    class _ForgedHashStore(_ForgedStore):
        def lookup(
            self, command: CatalogNormalizationCommandV2
        ) -> PersistedCatalogNormalizationV2 | None:
            del command
            return forged

    service = CatalogNormalizationRuntimeServiceV2(
        environment=RuntimeEnvironment.CI,
        source=fixture.source,
        store=cast(CatalogNormalizationUnitOfWorkStoreV2, _ForgedHashStore()),
    )
    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_sanitized(caught, CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE)


@pytest.mark.parametrize("field", ("batch_id", "normalized_at"))
def test_noncanonical_uuid_and_rfc3339_mappings_are_rejected(
    tmp_path: Path,
    field: str,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    batch = normalize_persisted_item_search_page_v2(
        command=fixture.command,
        page=fixture.page,
        raw_body=fixture.raw_body,
    )
    mapping = deepcopy(catalog_normalization_batch_mapping_v2(batch))
    if field == "batch_id":
        mapping["batch_id"] = str(mapping["batch_id"]).upper()
    else:
        snapshot = cast(dict[str, object], mapping["source_snapshot"])
        snapshot["normalized_at"] = str(snapshot["normalized_at"]).replace(
            ".000000+00:00",
            "+00:00",
        )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        catalog_normalization_batch_from_mapping_v2(mapping)

    assert caught.value.code is CatalogNormalizationRuntimeFailureCode.INVALID_ARGUMENT
