"""Hostile-input and fail-closed tests for the ST-0903 generator."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
from pathlib import Path

import pytest
import yaml

from scripts import build_st0903_publication_snapshot_reference_plan as generator


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "snapshot_builder_authorized", True),
        ("document", "runtime_builder_authorized", True),
        ("document", "approval_authority", True),
        ("document", "publication_permitted", True),
        ("document", "story_acceptance", True),
        ("document", "readiness", "READY"),
        ("pro_assistance", "status", "CAPTURED"),
        ("pro_assistance", "proposal_captured", True),
        ("execution_defaults", "pure_snapshot_builder", "IMPLEMENTED"),
        ("execution_defaults", "database", "EXECUTED"),
        ("execution_defaults", "object_storage", "EXECUTED"),
        ("verification_defaults", "formal_tst_014", "PASS"),
        ("verification_defaults", "formal_tst_021", "PASS"),
        ("verification_defaults", "production", "READY"),
    ],
)
def test_authority_execution_and_false_readiness_claims_are_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.validate_contract(contract)


def test_nonempty_snapshot_record_is_rejected() -> None:
    contract = deepcopy(generator.load_contract())
    contract["record_defaults"]["snapshots"]["records"] = [{"claimed": True}]

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.validate_contract(contract)


def test_runtime_module_or_builder_handoff_drift_is_rejected() -> None:
    contract = deepcopy(generator.load_contract())
    contract["implementation_boundary"]["runtime_modules"] = ["python/raos/runtime.py"]

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["authority"].update({"precedence": "CONTRACT_FIRST"}),
        lambda value: value["dependencies"].pop(),
        lambda value: value["dependencies"][0].update(
            {"authority_status": "AUTHORITATIVE_APPROVAL"}
        ),
        lambda value: value["hard_gates"].pop(),
        lambda value: value["hard_gates"][0].update({"safe_default": "BUILD"}),
    ],
)
def test_precedence_dependencies_and_hard_gates_are_exact(
    mutation: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    mutation(contract)  # type: ignore[operator]

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.validate_contract(contract)


def test_malformed_nested_shape_is_a_sanitized_builder_failure() -> None:
    contract = deepcopy(generator.load_contract())
    del contract["contract_projection_defaults"]["build_snapshot_job_schema"]

    with pytest.raises(
        generator.PublicationSnapshotReferenceError,
        match=r"^ST-0903 build failed: SOURCE_SHAPE_INVALID field=contract$",
    ) as raised:
        generator.validate_contract(contract)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


def test_helper_hash_is_verified_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = False

    def forbidden_import(_name: str) -> object:
        nonlocal imported
        imported = True
        raise AssertionError("helper import occurred")

    monkeypatch.setattr(generator, "_HELPER_MODULE", None)
    monkeypatch.setattr(generator, "HELPER_SHA256", "0" * 64)
    monkeypatch.setattr(importlib, "import_module", forbidden_import)

    with pytest.raises(
        generator.PublicationSnapshotReferenceError,
        match=r"HELPER_HASH_MISMATCH field=helper$",
    ):
        generator._helper()
    assert imported is False


@pytest.mark.parametrize(
    "payload",
    [
        b"document: {}\ndocument: {}\n",
        b"document: &shared {}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {enabled: false}\nmerged: {<<: *base}\n",
    ],
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path,
    payload: bytes,
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.load_contract(isolated_repository)


def test_symlink_contract_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.load_contract(isolated_repository)


def test_symlink_authority_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    authority = isolated_repository / generator.STORY_PATH
    outside_directory = tmp_path / "outside-authority"
    authority.parent.rename(outside_directory)
    authority.parent.symlink_to(outside_directory, target_is_directory=True)

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.load_contract(isolated_repository)


def test_output_symlink_and_path_traversal_are_rejected(
    isolated_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"

    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [
        generator.STORY_PATH,
        generator.REQUIREMENTS_PATH,
        generator.MASTER_TRACE_PATH,
        generator.SNAPSHOT_SCHEMA_PATH,
        generator.JOB_CATALOG_PATH,
        generator.JOB_SCHEMA_PATH,
        generator.EVENT_SCHEMA_PATH,
        Path("changes/st-0902/contracts/final-approval-reference-plan.v1.yaml"),
        generator.HELPER_PATH,
    ],
)
def test_authority_dependency_or_helper_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.render_outputs(isolated_repository)


def test_duplicate_key_json_schema_is_rejected_after_hash_rebind(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.SNAPSHOT_SCHEMA_PATH
    path.write_bytes(b'{"type":"object","type":"array"}')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (
            role,
            source,
            digest if source == generator.SNAPSHOT_SCHEMA_PATH.as_posix() else expected,
        )
        for role, source, expected in generator.EXPECTED_SOURCES
    )
    monkeypatch.setattr(generator, "EXPECTED_SOURCES", rebound)
    contract_path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    for source in contract["authority"]["sources"]:
        if source["role"] == "publication_snapshot_schema":
            source["sha256"] = digest
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setattr(
        generator,
        "CONTRACT_SHA256",
        hashlib.sha256(contract_path.read_bytes()).hexdigest(),
    )

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.load_contract(isolated_repository)


def test_schema_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.SNAPSHOT_SCHEMA_PATH
    schema = yaml.safe_load(path.read_bytes())
    schema["required"].remove("snapshot_sha256")
    path.write_text(json_dump(schema), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (
            role,
            source,
            digest if source == generator.SNAPSHOT_SCHEMA_PATH.as_posix() else expected,
        )
        for role, source, expected in generator.EXPECTED_SOURCES
    )
    monkeypatch.setattr(generator, "EXPECTED_SOURCES", rebound)
    contract_path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    for source in contract["authority"]["sources"]:
        if source["role"] == "publication_snapshot_schema":
            source["sha256"] = digest
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setattr(
        generator,
        "CONTRACT_SHA256",
        hashlib.sha256(contract_path.read_bytes()).hexdigest(),
    )

    with pytest.raises(generator.PublicationSnapshotReferenceError):
        generator.load_contract(isolated_repository)


def json_dump(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
