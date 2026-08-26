"""Hostile-input and fail-closed tests for ST-0905."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import build_st0905_publication_commands_reference_plan as generator


def _rebind_source(root: Path, relative: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    monkeypatch.setattr(
        generator,
        "EXPECTED_SOURCES",
        tuple(
            (role, source, digest if source == relative.as_posix() else expected)
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
        ("document", "command_handlers_authorized", True),
        ("document", "job_producers_authorized", True),
        ("document", "event_emission_authorized", True),
        ("document", "publication_authority", True),
        ("document", "publication_permitted", True),
        ("pro_assistance", "pro_required_for_reference_slice", True),
        ("execution_defaults", "command_handlers", "IMPLEMENTED"),
        ("verification_defaults", "formal_tst_012", "PASS"),
        ("verification_defaults", "formal_tst_013", "PASS"),
        ("verification_defaults", "formal_tst_021", "PASS"),
    ],
)
def test_false_authority_execution_or_readiness_is_rejected(
    section: str, field: str, value: object
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    _mapping = cast(dict[str, Any], contract[section])
    _mapping[field] = value
    with pytest.raises(generator.PublicationCommandsReferenceError):
        generator.validate_contract(contract)


def test_nonempty_records_runtime_module_or_gate_drift_is_rejected() -> None:
    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda value: value["record_defaults"]["commands"].update({"records": [{}]}),
        lambda value: value["implementation_boundary"].update(
            {"runtime_modules": ["python/raos/runtime.py"]}
        ),
        lambda value: value["hard_gates"][0].update({"safe_default": "PUBLISH"}),
        lambda value: value["contract_projection_defaults"]["surface_conflicts"][
            0
        ].update({"status": "RESOLVED"}),
    )
    for mutation in mutations:
        contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
        mutation(contract)
        with pytest.raises(generator.PublicationCommandsReferenceError):
            generator.validate_contract(contract)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["contract_projection_defaults"].pop("command_surfaces"),
        lambda value: value["contract_projection_defaults"].update(
            {"job_surfaces": []}
        ),
        lambda value: value["contract_projection_defaults"]["event_surfaces"].update(
            {"published": []}
        ),
        lambda value: value["contract_projection_defaults"]["security_boundary"].pop(
            "unpublish"
        ),
        lambda value: value["record_defaults"].update({"commands": []}),
        lambda value: value.update({"implementation_boundary": []}),
    ],
)
def test_all_malformed_nested_shapes_are_sanitized(
    mutation: Callable[[dict[str, Any]], object],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(
        generator.PublicationCommandsReferenceError,
        match=(
            r"^ST-0905 build failed: "
            r"(?:SOURCE_SHAPE_INVALID field=contract|TYPE_MISMATCH field=[a-z_.]+)$"
        ),
    ):
        generator.validate_contract(contract)


def test_helper_uses_semantic_owner_without_digest_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "_helper_module", None)
    assert generator._helper().__name__ == "scripts.build_st1505_staging_deployment"


@pytest.mark.parametrize(
    "payload", [b"document: {}\ndocument: {}\n", b"document: &x {}\nauthority: *x\n"]
)
def test_duplicate_or_aliased_yaml_is_rejected(
    isolated_repository: Path, payload: bytes
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(generator.PublicationCommandsReferenceError):
        generator.load_contract(isolated_repository)


def test_symlink_traversal_oversize_and_hash_drift_are_rejected(
    isolated_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(generator.PublicationCommandsReferenceError):
        generator.load_contract(isolated_repository)
    contract.unlink()
    contract.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(generator.PublicationCommandsReferenceError):
        generator.load_contract(isolated_repository)
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(generator.PublicationCommandsReferenceError):
        generator.load_contract(isolated_repository)


def test_output_symlink_is_rejected_without_touching_target(
    isolated_repository: Path, tmp_path: Path
) -> None:
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(generator.PublicationCommandsReferenceError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


@pytest.mark.parametrize(
    "relative",
    [
        generator.STORY_PATH,
        generator.REQUIREMENTS_PATH,
        generator.ADMIN_OPENAPI_PATH,
        generator.JOB_CATALOG_PATH,
        generator.PUBLISHED_EVENT_SCHEMA_PATH,
        Path("changes/st-0903/contracts/publication-snapshot-reference-plan.v1.yaml"),
        Path("changes/st-0904/contracts/public-projection-reference-plan.v1.yaml"),
    ],
)
def test_authority_and_dependency_semantic_drift_is_rejected(
    isolated_repository: Path, relative: Path
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.PublicationCommandsReferenceError):
        generator.render_outputs(isolated_repository)


def test_readme_and_helper_are_semantic_inputs_not_digest_bound(
    isolated_repository: Path,
) -> None:
    for relative in (Path("changes/st-0402/README.md"), generator.HELPER_PATH):
        path = isolated_repository / relative
        path.write_bytes(path.read_bytes() + b"\n# note\n")
    assert generator.render_outputs(isolated_repository)


def test_duplicate_key_json_is_rejected_after_hash_rebind(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = isolated_repository / generator.PUBLISH_JOB_SCHEMA_PATH
    path.write_bytes(b'{"type":"object","type":"array"}')
    _rebind_source(isolated_repository, generator.PUBLISH_JOB_SCHEMA_PATH, monkeypatch)
    with pytest.raises(
        generator.PublicationCommandsReferenceError, match="JSON_DUPLICATE_KEY"
    ):
        generator.load_contract(isolated_repository)


def test_job_semantic_drift_is_rejected_after_hash_rebind(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = isolated_repository / generator.ROLLBACK_JOB_SCHEMA_PATH
    schema = json.loads(path.read_bytes())
    schema["allOf"][1]["properties"]["payload"]["required"].remove("from_snapshot_id")
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    _rebind_source(isolated_repository, generator.ROLLBACK_JOB_SCHEMA_PATH, monkeypatch)
    with pytest.raises(
        generator.PublicationCommandsReferenceError, match="VALUE_MISMATCH"
    ):
        generator.load_contract(isolated_repository)
