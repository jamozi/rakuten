"""Static storage and registration boundary checks for ST-0601."""

from __future__ import annotations

import ast
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
import inspect

import pytest

from raos.adapters.recorded_artifact_registry import RecordedArtifactCandidateObserver
from raos.domain.ops import artifact_registry as domain
from raos.ports.artifact_registry import ArtifactCandidateObserver

from .support import REPOSITORY_ROOT, observer_for, provenance


OWNED_SOURCES = (
    REPOSITORY_ROOT / "python/raos/domain/ops/artifact_registry.py",
    REPOSITORY_ROOT / "python/raos/ports/artifact_registry.py",
    REPOSITORY_ROOT / "python/raos/application/ops/artifact_registry.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_artifact_registry.py",
)


def _trees() -> tuple[ast.Module, ...]:
    return tuple(ast.parse(path.read_text(encoding="utf-8")) for path in OWNED_SOURCES)


def test_sources_import_no_storage_network_database_filesystem_or_environment() -> None:
    forbidden = {
        "boto3",
        "botocore",
        "http",
        "httpx",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "urllib",
    }
    imported: set[str] = set()
    for tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.partition(".")[0])
    assert imported.isdisjoint(forbidden)


def test_port_exposes_exactly_one_observe_method() -> None:
    methods = {
        name
        for name, value in ArtifactCandidateObserver.__dict__.items()
        if inspect.isfunction(value)
    } - {"__init__"}
    assert methods == {"observe"}


def test_application_observes_once_without_fetch_retry_repair_or_fallback() -> None:
    tree = ast.parse(OWNED_SOURCES[2].read_text(encoding="utf-8"))
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert calls.count("observe") == 1
    assert set(calls).isdisjoint(
        {"fetch", "get", "head", "put", "read", "repair", "retry", "sleep", "write"}
    )


def test_sources_define_no_storage_registry_repository_or_external_method() -> None:
    forbidden = {
        "client",
        "commit",
        "delete",
        "fetch",
        "get",
        "head",
        "list",
        "open",
        "persist",
        "put",
        "read",
        "register",
        "repair",
        "save",
        "transaction",
        "upload",
        "write",
    }
    defined = {
        node.name
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined.isdisjoint(forbidden)


def test_decision_vocabularies_cannot_claim_ready_stored_or_verified() -> None:
    assert {value.value for value in domain.RegistryDecision} == {
        "NOT_READY",
        "REJECTED",
    }
    assert {value.value for value in domain.IntegrityDecision} == {
        "RECORDED_MATCH",
        "TAMPER_DETECTED",
    }
    prohibited = {"READY", "REGISTERED", "STORED", "VERIFIED", "PASS"}
    assert prohibited.isdisjoint(value.value for value in domain.RegistryDecision)
    assert prohibited.isdisjoint(value.value for value in domain.IntegrityDecision)


def test_domain_dataclasses_are_immutable_and_have_no_defaults() -> None:
    candidate = provenance()
    with pytest.raises(FrozenInstanceError):
        setattr(candidate, "byte_size", candidate.byte_size + 1)
    for value in vars(domain).values():
        if inspect.isclass(value) and is_dataclass(value):
            assert all(
                field.default is MISSING and field.default_factory is MISSING
                for field in fields(value)
            )


def test_adapter_has_no_history_bytes_snapshot_or_fake_repository() -> None:
    observer = observer_for(provenance())
    assert type(observer) is RecordedArtifactCandidateObserver
    assert RecordedArtifactCandidateObserver.__slots__ == ("_fixtures",)
    for name in ("history", "bytes", "content", "snapshot", "repository", "items"):
        assert not hasattr(observer, name)


def test_sources_generate_no_clock_random_uuid_uri_or_external_action() -> None:
    forbidden_calls = {
        "getenv",
        "open",
        "publish",
        "request",
        "sleep",
        "time",
        "time_ns",
        "unlink",
        "upload",
        "urlopen",
        "uuid1",
        "uuid4",
        "uuid5",
        "uuid6",
        "uuid7",
    }
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert calls.isdisjoint(forbidden_calls)
