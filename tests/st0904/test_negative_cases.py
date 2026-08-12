"""Hostile-input and fail-closed tests for ST-0904."""

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import build_st0904_public_projection_reference_plan as generator


def _rebind_source(
    root: Path,
    relative: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    monkeypatch.setattr(
        generator,
        "EXPECTED_SOURCES",
        tuple(
            (
                role,
                source,
                digest if source == relative.as_posix() else expected,
            )
            for role, source, expected in generator.EXPECTED_SOURCES
        ),
    )
    contract_path = root / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    for row in contract["authority"]["sources"]:
        if row["uri"] == f"repo://{relative.as_posix()}":
            row["sha256"] = digest
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setattr(
        generator,
        "CONTRACT_SHA256",
        hashlib.sha256(contract_path.read_bytes()).hexdigest(),
    )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "projector_authorized", True),
        ("document", "runtime_projector_authorized", True),
        ("document", "publication_permitted", True),
        ("pro_assistance", "proposal_captured", True),
        ("execution_defaults", "pure_projector", "IMPLEMENTED"),
        ("verification_defaults", "formal_tst_011", "PASS"),
        ("verification_defaults", "formal_tst_021", "PASS"),
    ],
)
def test_false_authority_execution_or_readiness_is_rejected(
    section: str, field: str, value: object
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.PublicProjectionReferenceError):
        generator.validate_contract(contract)


def test_nonempty_projection_runtime_module_or_gate_drift_is_rejected() -> None:
    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda value: value["record_defaults"]["projections"].update({"records": [{}]}),
        lambda value: value["implementation_boundary"].update(
            {"runtime_modules": ["python/raos/runtime.py"]}
        ),
        lambda value: value["hard_gates"][0].update({"safe_default": "PROJECT"}),
    )
    for mutation in mutations:
        contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
        mutation(contract)
        with pytest.raises(generator.PublicProjectionReferenceError):
            generator.validate_contract(contract)


def test_malformed_nested_shape_is_sanitized() -> None:
    contract = deepcopy(generator.load_contract())
    del contract["contract_projection_defaults"]["job_surfaces"]
    with pytest.raises(
        generator.PublicProjectionReferenceError,
        match=r"^ST-0904 build failed: SOURCE_SHAPE_INVALID field=contract$",
    ):
        generator.validate_contract(contract)


def test_helper_hash_is_verified_before_import(monkeypatch: pytest.MonkeyPatch) -> None:
    imported = False

    def forbidden(_name: str) -> object:
        nonlocal imported
        imported = True
        raise AssertionError

    monkeypatch.setattr(generator, "_HELPER_MODULE", None)
    monkeypatch.setattr(generator, "HELPER_SHA256", "0" * 64)
    monkeypatch.setattr(importlib, "import_module", forbidden)
    with pytest.raises(
        generator.PublicProjectionReferenceError, match="HELPER_HASH_MISMATCH"
    ):
        generator._helper()
    assert imported is False


@pytest.mark.parametrize(
    "payload", [b"document: {}\ndocument: {}\n", b"document: &x {}\nauthority: *x\n"]
)
def test_duplicate_or_aliased_yaml_is_rejected(
    isolated_repository: Path, payload: bytes
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(generator.PublicProjectionReferenceError):
        generator.load_contract(isolated_repository)


def test_symlink_traversal_oversize_and_hash_drift_are_rejected(
    isolated_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(generator.PublicProjectionReferenceError):
        generator.load_contract(isolated_repository)
    contract.unlink()
    contract.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(generator.PublicProjectionReferenceError):
        generator.load_contract(isolated_repository)
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(generator.PublicProjectionReferenceError):
        generator.load_contract(isolated_repository)


def test_output_symlink_is_rejected_without_touching_target(
    isolated_repository: Path, tmp_path: Path
) -> None:
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(generator.PublicProjectionReferenceError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


@pytest.mark.parametrize(
    "relative",
    [
        generator.STORY_PATH,
        generator.REQUIREMENTS_PATH,
        generator.SNAPSHOT_SCHEMA_PATH,
        generator.JOB_CATALOG_PATH,
        Path("changes/st-0903/contracts/publication-snapshot-reference-plan.v1.yaml"),
        Path("changes/st-0306/contracts/database-roles-grants.v1.yaml"),
        generator.HELPER_PATH,
    ],
)
def test_authority_dependency_and_helper_byte_drift_is_rejected(
    isolated_repository: Path, relative: Path
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.PublicProjectionReferenceError):
        generator.render_outputs(isolated_repository)


def test_duplicate_key_json_is_rejected_after_hash_rebind(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = isolated_repository / generator.SNAPSHOT_SCHEMA_PATH
    path.write_bytes(b'{"type":"object","type":"array"}')
    _rebind_source(isolated_repository, generator.SNAPSHOT_SCHEMA_PATH, monkeypatch)
    with pytest.raises(
        generator.PublicProjectionReferenceError, match="JSON_DUPLICATE_KEY"
    ):
        generator.load_contract(isolated_repository)


def test_schema_semantic_drift_is_rejected_after_hash_rebind(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = isolated_repository / generator.SNAPSHOT_SCHEMA_PATH
    schema = json.loads(path.read_bytes())
    schema["required"].remove("snapshot_sha256")
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    _rebind_source(isolated_repository, generator.SNAPSHOT_SCHEMA_PATH, monkeypatch)
    with pytest.raises(
        generator.PublicProjectionReferenceError, match="VALUE_MISMATCH"
    ):
        generator.load_contract(isolated_repository)


def test_conflict_claim_drift_is_rejected_after_contract_hash_rebind(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    contract["contract_projection_defaults"]["surface_conflicts"]["heading_level"][
        "database"
    ] = "2..4"
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setattr(
        generator,
        "CONTRACT_SHA256",
        hashlib.sha256(contract_path.read_bytes()).hexdigest(),
    )
    with pytest.raises(
        generator.PublicProjectionReferenceError, match="VALUE_MISMATCH"
    ):
        generator.load_contract(isolated_repository)
