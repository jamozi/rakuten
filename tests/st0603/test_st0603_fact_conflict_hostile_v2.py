"""Hostile collaborator and authority-boundary checks for ST-0603 V2."""

from __future__ import annotations

import ast
from collections.abc import Iterator
import inspect
from pathlib import Path
import socket
import tempfile
from typing import cast

import pytest

from raos.adapters.sqlite_fact_conflict_runtime_v2 import (
    OwnerPrivateSqliteFactConflictStoreV2,
)
from raos.application.evidence.fact_conflict_runtime_v2 import (
    DurableFactConflictDetectionServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.evidence.fact_conflict_runtime_v2 import (
    FACT_CONFLICT_GENESIS_SHA256_V2,
    FactConflictDetectionBatchV2,
    FactConflictFailureCodeV2,
    FactConflictFailureV2,
    FactConflictScanCommandV2,
    FactConflictsRecordedOutboxEventV2,
    PersistedFactConflictDetectionV2,
    build_fact_conflict_artifacts_v2,
)
from tests.st0603.st0603_runtime_v2_fixtures import (
    conflict_store_v2,
    derive_persisted_fact_v2,
    exact_persisted_fact_v2,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATHS = (
    Path("python/raos/domain/evidence/fact_conflict_runtime_v2.py"),
    Path("python/raos/ports/fact_conflict_runtime_v2.py"),
    Path("python/raos/application/evidence/fact_conflict_runtime_v2.py"),
    Path("python/raos/adapters/sqlite_fact_conflict_runtime_v2.py"),
)


def _code(call: object) -> FactConflictFailureCodeV2:
    assert callable(call)
    with pytest.raises(FactConflictFailureV2) as captured:
        call()
    return captured.value.code


@pytest.fixture()
def st0603_hostile_root_v2() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="st0603-hostile-", dir="/tmp") as raw:
        root = Path(raw)
        root.chmod(0o700)
        yield root


class _StoreDouble:
    def __init__(self) -> None:
        self.lookup_value: object = None
        self.commit_value: object = None
        self.recovery_value: object = None
        self.verify_value: object = (FACT_CONFLICT_GENESIS_SHA256_V2, 0)
        self.raise_commit = False
        self.mutate_lookup_command = False
        self.mutate_commit_batch = False
        self.mutate_recovery_command = False

    def lookup(self, command: FactConflictScanCommandV2):
        if self.mutate_lookup_command:
            object.__setattr__(command, "payload_sha256", "f" * 64)
        return self.lookup_value

    def commit(
        self,
        *,
        command: FactConflictScanCommandV2,
        batch: FactConflictDetectionBatchV2,
        event: FactConflictsRecordedOutboxEventV2,
    ):
        del command, event
        if self.mutate_commit_batch:
            object.__setattr__(batch, "provider_action_count", False)
        if self.raise_commit:
            raise RuntimeError("opaque collaborator failure")
        return self.commit_value

    def recover_exact(self, command: FactConflictScanCommandV2):
        if self.mutate_recovery_command:
            object.__setattr__(command, "payload_sha256", "f" * 64)
        return self.recovery_value

    def load_batch(self, scan_id):
        del scan_id
        raise AssertionError("not called")

    def load_conflict(self, conflict_id):
        del conflict_id
        raise AssertionError("not called")

    def load_queue(self, queue_id):
        del queue_id
        raise AssertionError("not called")

    def load_outbox(self, event_id):
        del event_id
        raise AssertionError("not called")

    def verify_chain(self):
        return self.verify_value


def _inputs(root: Path):
    first = exact_persisted_fact_v2(root / "upstream")
    second = derive_persisted_fact_v2(first, label="hostile", price_delta=1)
    return first, second


def test_non_exact_dependency_and_chain_tamper_fail_closed(
    st0603_hostile_root_v2,
) -> None:
    inputs = _inputs(st0603_hostile_root_v2)
    assert _code(lambda: build_fact_conflict_artifacts_v2(cast(object, inputs[0]))) is (
        FactConflictFailureCodeV2.INPUT_LIMIT_EXCEEDED
    )
    assert _code(lambda: build_fact_conflict_artifacts_v2(())) is (
        FactConflictFailureCodeV2.INPUT_LIMIT_EXCEEDED
    )
    assert _code(lambda: build_fact_conflict_artifacts_v2((inputs[0],) * 65)) is (
        FactConflictFailureCodeV2.INPUT_LIMIT_EXCEEDED
    )
    object.__setattr__(inputs[0], "chain_hash", "f" * 64)
    assert _code(lambda: build_fact_conflict_artifacts_v2(inputs)) is (
        FactConflictFailureCodeV2.DEPENDENCY_MISMATCH
    )


def test_oversized_mutated_predecessor_is_rejected_before_iteration(
    st0603_hostile_root_v2,
) -> None:
    persisted = exact_persisted_fact_v2(st0603_hostile_root_v2 / "upstream")
    object.__setattr__(persisted.batch, "facts", persisted.batch.facts * 4097)
    object.__setattr__(
        persisted.batch,
        "validations",
        persisted.batch.validations * 4097,
    )
    assert _code(lambda: build_fact_conflict_artifacts_v2((persisted,))) is (
        FactConflictFailureCodeV2.INPUT_LIMIT_EXCEEDED
    )


@pytest.mark.parametrize(
    "verify_value",
    [
        None,
        ("0" * 63, 0),
        ("0" * 64, False),
        ("z" * 64, 0),
        ("0" * 64, -1),
    ],
)
def test_malformed_store_chain_is_rejected_before_commit(
    st0603_hostile_root_v2,
    verify_value: object,
) -> None:
    inputs = _inputs(st0603_hostile_root_v2)
    store = _StoreDouble()
    store.verify_value = verify_value
    service = DurableFactConflictDetectionServiceV2(store)
    assert _code(lambda: service.detect(inputs=inputs)) is (
        FactConflictFailureCodeV2.TAMPER_DETECTED
    )


def test_spoofed_lookup_and_commit_results_never_cross_boundary(
    st0603_hostile_root_v2,
) -> None:
    inputs = _inputs(st0603_hostile_root_v2)
    lookup_store = _StoreDouble()
    lookup_store.lookup_value = object()
    assert (
        _code(
            lambda: DurableFactConflictDetectionServiceV2(lookup_store).detect(
                inputs=inputs
            )
        )
        is FactConflictFailureCodeV2.TAMPER_DETECTED
    )

    commit_store = _StoreDouble()
    commit_store.commit_value = object()
    assert (
        _code(
            lambda: DurableFactConflictDetectionServiceV2(commit_store).detect(
                inputs=inputs
            )
        )
        is FactConflictFailureCodeV2.TAMPER_DETECTED
    )

    ambiguous_store = _StoreDouble()
    ambiguous_store.raise_commit = True
    assert (
        _code(
            lambda: DurableFactConflictDetectionServiceV2(ambiguous_store).detect(
                inputs=inputs
            )
        )
        is FactConflictFailureCodeV2.COMMIT_UNKNOWN
    )


@pytest.mark.parametrize(
    "boundary",
    ["lookup", "commit", "recover"],
)
def test_collaborator_cannot_mutate_scan_artifacts_in_place(
    st0603_hostile_root_v2,
    boundary: str,
) -> None:
    inputs = _inputs(st0603_hostile_root_v2)
    store = _StoreDouble()
    if boundary == "lookup":
        store.mutate_lookup_command = True
    elif boundary == "commit":
        store.mutate_commit_batch = True
    else:
        store.raise_commit = True
        store.mutate_recovery_command = True
    assert (
        _code(
            lambda: DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs)
        )
        is FactConflictFailureCodeV2.TAMPER_DETECTED
    )


def test_action_count_mutation_after_collaborator_is_detected(
    st0603_hostile_root_v2,
) -> None:
    inputs = _inputs(st0603_hostile_root_v2)
    real_store = conflict_store_v2(st0603_hostile_root_v2 / "store")
    persisted = (
        DurableFactConflictDetectionServiceV2(real_store)
        .detect(inputs=inputs)
        .persisted
    )
    object.__setattr__(persisted.batch, "provider_action_count", False)
    store = _StoreDouble()
    store.lookup_value = persisted
    store.verify_value = (persisted.chain_hash, 1)
    assert (
        _code(
            lambda: DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs)
        )
        is FactConflictFailureCodeV2.TAMPER_DETECTED
    )


def test_store_rejects_boolean_action_count_spoofing_directly(
    st0603_hostile_root_v2,
) -> None:
    command, batch, event = build_fact_conflict_artifacts_v2(
        _inputs(st0603_hostile_root_v2)
    )
    object.__setattr__(batch, "provider_action_count", False)
    store = conflict_store_v2(st0603_hostile_root_v2 / "store")
    assert (
        _code(lambda: store.commit(command=command, batch=batch, event=event))
        is FactConflictFailureCodeV2.INVALID_ARGUMENT
    )


def test_complete_recorded_pipeline_succeeds_with_network_denied(
    st0603_hostile_root_v2,
    monkeypatch,
) -> None:
    def denied(*_args, **_kwargs):
        raise AssertionError("network capability forbidden")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    inputs = _inputs(st0603_hostile_root_v2)
    store = conflict_store_v2(st0603_hostile_root_v2 / "store")
    result = DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs)
    assert len(result.persisted.batch.conflicts) == 1
    assert result.external_action_count == 0


def test_runtime_imports_expose_no_external_action_or_business_inputs() -> None:
    forbidden_import_roots = {
        "aiohttp",
        "boto3",
        "httpx",
        "openai",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_identifiers = {
        "affiliate_rate",
        "credential",
        "epc",
        "profit",
        "provider_client",
        "publication_client",
        "revenue",
        "rpm",
        "secret_key",
    }
    for relative in RUNTIME_PATHS:
        source = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import) and node.names
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert not imports & forbidden_import_roots
        identifiers = {
            node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        assert not identifiers & forbidden_identifiers


def test_public_surfaces_have_no_resolution_publication_or_generic_sql() -> None:
    service_public = {
        name
        for name, value in inspect.getmembers(DurableFactConflictDetectionServiceV2)
        if not name.startswith("_") and callable(value)
    }
    store_public = {
        name
        for name, value in inspect.getmembers(OwnerPrivateSqliteFactConflictStoreV2)
        if not name.startswith("_") and callable(value)
    }
    assert service_public == {"detect"}
    assert store_public == {
        "commit",
        "load_batch",
        "load_conflict",
        "load_outbox",
        "load_queue",
        "lookup",
        "recover_exact",
        "verify_chain",
    }
    forbidden = {
        "approve",
        "convert",
        "deliver",
        "execute",
        "publish",
        "rank",
        "recommend",
        "resolve",
        "review",
        "rollback",
        "sql",
        "winner",
    }
    assert not service_public & forbidden
    assert not store_public & forbidden


def test_only_dev_and_ci_private_roots_are_accepted(st0603_hostile_root_v2) -> None:
    assert (
        _code(
            lambda: OwnerPrivateSqliteFactConflictStoreV2(
                environment=RuntimeEnvironment.PRODUCTION,
                root=st0603_hostile_root_v2 / "prod",
            )
        )
        is FactConflictFailureCodeV2.INVALID_ARGUMENT
    )
    public_root = st0603_hostile_root_v2 / "public"
    public_root.mkdir(mode=0o755)
    assert (
        _code(
            lambda: OwnerPrivateSqliteFactConflictStoreV2(
                environment=RuntimeEnvironment.CI,
                root=public_root,
            )
        )
        is FactConflictFailureCodeV2.UNSAFE_PATH
    )


def test_persisted_database_contains_no_urls_or_business_metric_terms(
    st0603_hostile_root_v2,
) -> None:
    inputs = _inputs(st0603_hostile_root_v2)
    store = conflict_store_v2(st0603_hostile_root_v2 / "store")
    DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs)
    payload = store.database_path.read_bytes().lower()
    for term in (
        b"http://",
        b"https://",
        b"credential",
        b"affiliate_rate",
        b"profit",
        b"revenue",
        b"epc",
        b"rpm",
    ):
        assert term not in payload


def test_persisted_type_annotation_remains_exact() -> None:
    annotation = cast(
        object,
        PersistedFactConflictDetectionV2.__annotations__["batch"],
    )
    assert annotation == "FactConflictDetectionBatchV2"
