"""Hostile collaborator and denied-network checks for ST-0503 V2."""

from __future__ import annotations

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
    CatalogCommitRecoveryV2,
    CatalogNormalizationBatchV2,
    CatalogNormalizationCommandV2,
    CatalogNormalizationRuntimeFailure,
    CatalogNormalizationRuntimeFailureCode,
    CatalogNormalizedOutboxEventV2,
    CatalogSourceModeV2,
    PersistedCatalogNormalizationV2,
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

    assert caught.value.code is CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY


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
