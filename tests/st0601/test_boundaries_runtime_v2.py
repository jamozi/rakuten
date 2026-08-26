"""Capability, failure hygiene, exception, and denied-network boundaries."""

from __future__ import annotations

import ast
from contextlib import contextmanager
import inspect
from pathlib import Path
import pickle
import socket
from typing import Generator, cast

import pytest

from raos.adapters.recorded_artifact_source_runtime_v2 import (
    RecordedItemSearchRawArchiveSourceV2,
    RecordedItemSearchRawFixtureV2,
)
from raos.adapters.sqlite_artifact_registry_runtime_v2 import (
    RecordedSqliteArtifactRegistryFactoryV2,
    RecordedSqliteArtifactRegistryStoreV2,
)
from raos.application.ops.artifact_registry_runtime_v2 import (
    DurableArtifactRegistryServiceV2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import RawArchiveReceiptV2
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ArtifactPutCommandV2,
    ArtifactPutReceiptV2,
    ArtifactReadbackV2,
    ArtifactRegistryRuntimeFailureCodeV2,
    ArtifactRegistryRuntimeFailureV2,
    PersistedArtifactV2,
    RecordedLocalArtifactRefV2,
    fail_artifact_registry_runtime_v2,
)
from raos.ports.artifact_registry_runtime_v2 import (
    ArtifactRegistryStoreFactoryV2,
    ArtifactRegistryStoreV2,
    ItemSearchRawArchiveSourceV2,
)

from .runtime_v2_fixtures import (
    BODY_ONE,
    private_root,
    receipt_for,
    request_for,
    service_for,
    source_for,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OWNED_V2_SOURCES = (
    REPOSITORY_ROOT / "python/raos/domain/ops/artifact_registry_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/ports/artifact_registry_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/application/ops/artifact_registry_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_artifact_source_runtime_v2.py",
    REPOSITORY_ROOT / "python/raos/adapters/sqlite_artifact_registry_runtime_v2.py",
)
CANARY = "ST0601_REJECTED_SOURCE_CANARY_DO_NOT_ECHO"


def _methods(protocol: type[object]) -> set[str]:
    return {
        name
        for name, value in protocol.__dict__.items()
        if inspect.isfunction(value) and not name.startswith("__")
    }


def test_ports_are_closed_and_have_no_mutation_export_or_provider_surface() -> None:
    assert _methods(ItemSearchRawArchiveSourceV2) == {"read_raw"}
    assert _methods(ArtifactRegistryStoreV2) == {
        "append",
        "recover_exact",
        "load_exact",
        "read_exact",
        "verify_chain",
    }
    assert _methods(ArtifactRegistryStoreFactoryV2) == {"open"}
    forbidden = {
        "delete",
        "download",
        "export",
        "lifecycle",
        "list",
        "provider",
        "publish",
        "purge",
        "retention",
        "update",
        "upload",
    }
    for implementation in (
        RecordedItemSearchRawArchiveSourceV2,
        RecordedSqliteArtifactRegistryFactoryV2,
        RecordedSqliteArtifactRegistryStoreV2,
        DurableArtifactRegistryServiceV2,
    ):
        assert forbidden.isdisjoint(
            name for name in implementation.__dict__ if not name.startswith("_")
        )


def test_v2_sources_import_no_network_provider_sdk_or_process_runtime() -> None:
    forbidden = {
        "boto3",
        "botocore",
        "http",
        "httpx",
        "openai",
        "psycopg",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    imports: set[str] = set()
    for path in OWNED_V2_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.partition(".")[0])
    assert imports.isdisjoint(forbidden)


class _CountingSource:
    def __init__(self, delegate: ItemSearchRawArchiveSourceV2) -> None:
        self.delegate = delegate
        self.calls = 0

    @property
    def external_action_count(self) -> int:
        return 0

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        self.calls += 1
        return self.delegate.read_raw(receipt)


class _FailingSource:
    @property
    def external_action_count(self) -> int:
        return 0

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        del receipt
        raise RuntimeError(CANARY)


class _WrongSource:
    @property
    def external_action_count(self) -> int:
        return 0

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        del receipt
        return cast(bytes, "not-bytes")


class _FailingStore:
    def append(
        self, *, command: ArtifactPutCommandV2, content: bytes
    ) -> ArtifactPutReceiptV2:
        del command, content
        raise RuntimeError(CANARY)

    def recover_exact(self, command: ArtifactPutCommandV2) -> ArtifactPutReceiptV2:
        del command
        raise AssertionError("recovery must not run")

    def load_exact(
        self, artifact_ref: RecordedLocalArtifactRefV2
    ) -> PersistedArtifactV2 | None:
        del artifact_ref
        return None

    def read_exact(
        self, artifact_ref: RecordedLocalArtifactRefV2
    ) -> ArtifactReadbackV2:
        del artifact_ref
        raise AssertionError("read must not run")

    def verify_chain(self) -> tuple[str, int]:
        raise AssertionError("verify must not run")


class _FailingStoreFactory:
    @property
    def external_action_count(self) -> int:
        return 0

    @property
    def open_count(self) -> int:
        return 1

    def open(self) -> ArtifactRegistryStoreV2:
        return _FailingStore()


def test_source_is_read_exactly_once_per_registration(tmp_path: Path) -> None:
    receipt = receipt_for()
    delegate = source_for((receipt, BODY_ONE))
    source = _CountingSource(delegate)
    _, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    service = DurableArtifactRegistryServiceV2(source=source, store_factory=factory)

    service.register(request_for(receipt))

    assert source.calls == 1


@pytest.mark.parametrize("source", (_FailingSource(), _WrongSource()))
def test_source_failure_is_sanitized_without_retry_or_context(
    tmp_path: Path, source: ItemSearchRawArchiveSourceV2
) -> None:
    receipt = receipt_for()
    _, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    service = DurableArtifactRegistryServiceV2(source=source, store_factory=factory)

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        service.register(request_for(receipt))

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.SOURCE_UNAVAILABLE
    assert CANARY not in f"{caught.value!s} {caught.value!r}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_store_failure_is_sanitized_without_retry_or_context(tmp_path: Path) -> None:
    del tmp_path
    receipt = receipt_for()
    service = DurableArtifactRegistryServiceV2(
        source=source_for((receipt, BODY_ONE)),
        store_factory=_FailingStoreFactory(),
    )

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        service.register(request_for(receipt))

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE
    assert CANARY not in f"{caught.value!s} {caught.value!r}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_recorded_fixture_defensively_copies_and_redacts_bytes() -> None:
    receipt = receipt_for()
    fixture = RecordedItemSearchRawFixtureV2(receipt=receipt, content=BODY_ONE)
    source = source_for((receipt, BODY_ONE))

    assert source.read_raw(receipt) == BODY_ONE
    assert "Items" not in repr(fixture)
    assert "Items" not in repr(source)
    with pytest.raises(TypeError):
        pickle.dumps(fixture)
    with pytest.raises(TypeError):
        pickle.dumps(source)


@contextmanager
def _passthrough() -> Generator[None, None, None]:
    yield


def test_closed_failure_supports_traceback_and_contextmanager_reraise() -> None:
    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as direct:
        fail_artifact_registry_runtime_v2(
            ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    assert direct.value.__traceback__ is not None

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as propagated:
        with _passthrough():
            raise direct.value
    assert propagated.value is direct.value
    assert propagated.value.__traceback__ is not None
    with pytest.raises(TypeError):
        pickle.dumps(propagated.value)


def test_runtime_completes_with_network_connect_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny_connect(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", deny_connect)
    receipt = receipt_for()
    service, _ = service_for(private_root(tmp_path), (receipt, BODY_ONE))

    commit = service.register(request_for(receipt))

    assert service.readback(commit.record.artifact_ref).content == BODY_ONE
