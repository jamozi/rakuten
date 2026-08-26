"""Static and hostile capability boundaries for the ST-0406 local slice."""

from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import pickle
from uuid import UUID

import pytest

from .support import (
    CONTENT,
    REPOSITORY_ROOT,
    authorization_grant,
    clean_inspection,
    intake_descriptor,
    intake_policy,
    make_recorded_adapter,
    synthetic_source,
)
from raos.adapters.recorded_object_intake import (
    RecordedObjectIntakeAdapter,
    SyntheticChunkReader,
)
from raos.application.ops.object_intake import ObjectIntakeService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.object_intake import (
    IntakeDescriptor,
    IntakePolicy,
    MediaType,
    ObjectInspectionReport,
    ObjectIntakeFailure,
    SafeLeafName,
    Sha256Digest,
)


OWNED_SOURCE_PATHS = (
    Path("python/raos/domain/ops/object_intake.py"),
    Path("python/raos/ports/object_intake.py"),
    Path("python/raos/application/ops/object_intake.py"),
    Path("python/raos/adapters/recorded_object_intake.py"),
)


def _tree(path: Path) -> ast.Module:
    return ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_dependencies_point_inward_and_exclude_runtime_integrations() -> None:
    domain_imports = _imports(OWNED_SOURCE_PATHS[0])
    port_imports = _imports(OWNED_SOURCE_PATHS[1])
    application_imports = _imports(OWNED_SOURCE_PATHS[2])
    adapter_imports = _imports(OWNED_SOURCE_PATHS[3])

    assert {name for name in domain_imports if name.startswith("raos.")} == set()
    assert {name for name in port_imports if name.startswith("raos.")} == {
        "raos.domain.ops.object_intake"
    }
    assert {name for name in application_imports if name.startswith("raos.")} == {
        "raos.domain.iam.authorization",
        "raos.domain.ops.object_intake",
        "raos.ports.object_intake",
    }
    assert {name for name in adapter_imports if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.ops.object_intake",
    }

    forbidden_roots = {
        "boto3",
        "botocore",
        "fastapi",
        "httpx",
        "logging",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "tempfile",
        "urllib",
    }
    all_imports = set().union(
        domain_imports,
        port_imports,
        application_imports,
        adapter_imports,
    )
    assert not {
        name for name in all_imports if name.partition(".")[0] in forbidden_roots
    }


def test_owned_sources_have_no_file_network_provider_process_or_ambient_calls() -> None:
    forbidden_calls = {
        "connect",
        "getenv",
        "open",
        "popen",
        "read_bytes",
        "read_text",
        "request",
        "run",
        "urlopen",
        "write_bytes",
        "write_text",
    }
    for path in OWNED_SOURCE_PATHS:
        tree = _tree(path)
        calls = {
            node.func.id.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        attributes = {
            node.func.attr.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert forbidden_calls.isdisjoint(calls | attributes)
        assert not any(
            isinstance(node, (ast.AsyncFor, ast.AsyncFunctionDef, ast.Await))
            for node in ast.walk(tree)
        )


def test_ports_expose_only_bounded_append_only_quarantine_operations() -> None:
    tree = _tree(Path("python/raos/ports/object_intake.py"))
    protocols = {
        node.name: {
            child.name
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    assert protocols == {
        "AppendOnlyQuarantine": {"append", "begin", "record_disposition", "seal"},
        "BoundedChunkReader": {"read_chunk"},
        "DuplicateRegistry": {"lookup", "record_clean"},
        "MalwareScanner": {"scan"},
        "ObjectInspector": {"inspect"},
    }
    forbidden = {
        "cleanup",
        "delete",
        "download",
        "export",
        "lifecycle",
        "promote",
        "purge",
        "read",
        "release",
        "retention",
        "restore",
    }
    assert forbidden.isdisjoint(set().union(*protocols.values()))


def test_application_has_one_public_command_and_no_retry_or_background_loop() -> None:
    tree = _tree(Path("python/raos/application/ops/object_intake.py"))
    service = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ObjectIntakeService"
    )
    public_methods = {
        node.name
        for node in service.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert public_methods == {"intake"}
    assert not any(
        isinstance(node, ast.For) and isinstance(node.iter, ast.Call)
        for node in ast.walk(service)
    )
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(service))


def test_adapter_public_surface_has_metadata_snapshots_but_no_content_access() -> None:
    allowed = {
        "append",
        "begin",
        "duplicate_snapshot",
        "environment",
        "inspect",
        "lookup",
        "quarantine_snapshot",
        "record_clean",
        "record_disposition",
        "scan",
        "seal",
    }
    public = {
        name for name in dir(RecordedObjectIntakeAdapter) if not name.startswith("_")
    }
    assert public == allowed
    assert {
        "content",
        "delete",
        "download",
        "export",
        "lifecycle",
        "promote",
        "purge",
        "read",
        "release",
        "retention",
    }.isdisjoint(public)


def test_public_domain_records_have_no_raw_bytes_or_arbitrary_mapping_fields() -> None:
    for record_type in (IntakeDescriptor, IntakePolicy, ObjectInspectionReport):
        annotations = record_type.__annotations__
        assert all(
            "bytes" not in str(annotation) for annotation in annotations.values()
        )
        assert all(
            fragment not in str(annotation).lower()
            for annotation in annotations.values()
            for fragment in ("any", "dict", "mapping")
        )


@pytest.mark.parametrize(
    "factory",
    (
        lambda: SafeLeafName(""),
        lambda: SafeLeafName("../unsafe.csv"),
        lambda: SafeLeafName("unsafe\\name.csv"),
        lambda: SafeLeafName(".hidden"),
        lambda: MediaType("Text/CSV"),
        lambda: MediaType("text/csv; charset=utf-8"),
        lambda: MediaType("text csv"),
        lambda: Sha256Digest("A" * 64),
        lambda: Sha256Digest("f" * 63),
        lambda: intake_descriptor(intake_id=UUID(int=0)),
        lambda: intake_descriptor(site_id=UUID(int=0)),
        lambda: intake_descriptor(declared_size=True),
        lambda: replace(intake_policy(), max_chunk_bytes=True),
        lambda: replace(intake_policy(), max_csv_rows=0),
        lambda: replace(
            intake_policy(),
            allowed_media_types=[],  # type: ignore[arg-type]
        ),
    ),
)
def test_untrusted_descriptor_and_policy_shapes_fail_exactly(factory: object) -> None:
    with pytest.raises(ObjectIntakeFailure):
        factory()  # type: ignore[operator]


def test_policy_has_no_defaults_and_is_frozen() -> None:
    parameters = inspect.signature(IntakePolicy).parameters.values()
    assert parameters
    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters)
    policy = intake_policy()
    with pytest.raises((AttributeError, TypeError)):
        policy.max_object_bytes = 1  # type: ignore[misc]
    assert not hasattr(policy, "__dict__")


def test_values_fail_pickle_and_redact_repr() -> None:
    values = (
        intake_descriptor(),
        intake_policy(),
        clean_inspection(),
        synthetic_source(),
    )
    for value in values:
        assert "synthetic.csv" not in repr(value)
        assert CONTENT.decode() not in repr(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_recorded_source_rejects_every_non_dev_ci_environment(
    environment: RuntimeEnvironment,
) -> None:
    with pytest.raises(ObjectIntakeFailure):
        SyntheticChunkReader(
            environment=environment,
            byte_capacity=len(CONTENT),
            content=CONTENT,
        )


@pytest.mark.parametrize("capacity", (0, -1, True, 100_001))
def test_recorded_source_rejects_invalid_exact_capacity(capacity: int) -> None:
    with pytest.raises(ObjectIntakeFailure):
        SyntheticChunkReader(
            environment=RuntimeEnvironment.ENV_DEV,
            byte_capacity=capacity,
            content=CONTENT,
        )


def test_metadata_snapshots_are_tuple_only_and_never_contain_bytes() -> None:
    adapter = make_recorded_adapter()
    service = ObjectIntakeService(
        policy=intake_policy(),
        quarantine=adapter,
        inspector=adapter,
        malware=adapter,
        duplicate_registry=adapter,
    )
    service.intake(
        grant=authorization_grant(),
        descriptor=intake_descriptor(),
        source=synthetic_source(),
    )

    snapshots = (adapter.quarantine_snapshot(), adapter.duplicate_snapshot())
    assert all(type(snapshot) is tuple for snapshot in snapshots)
    for snapshot in snapshots:
        for record in snapshot:
            assert all(
                not isinstance(getattr(record, field.name), bytes)
                for field in fields(record)
            )
            assert CONTENT.decode() not in repr(record)
