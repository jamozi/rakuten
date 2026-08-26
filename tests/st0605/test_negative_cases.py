from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import raos_build_core as base
from scripts import build_st0605_claim_evidence_coverage_reference_plan as generator


EXPECTED_ERRORS = (
    generator.ClaimEvidenceCoverageReferenceError,
    base.StagingDeploymentContractError,
)


def _load(root: Path) -> dict[str, Any]:
    loaded = yaml.safe_load((root / generator.CONTRACT_PATH).read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def _write(root: Path, contract: dict[str, Any]) -> None:
    (root / generator.CONTRACT_PATH).write_bytes(
        yaml.safe_dump(contract, sort_keys=False, allow_unicode=True).encode("utf-8")
    )


def _assert_rejected(root: Path) -> str:
    with pytest.raises(EXPECTED_ERRORS) as caught:
        generator.load_contract(root)
    return str(caught.value)


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("section", "field", "value"),
    [
        ("vocabulary_context", "inferred_mappings", ["invented"]),
        ("collection_defaults", "claims", [{"id": "invented"}]),
        ("collection_defaults", "facts", [{"id": "invented"}]),
        ("collection_defaults", "links", [{"id": "invented"}]),
        ("collection_defaults", "claim_count", 0),
        ("collection_defaults", "fact_count", 0),
        ("collection_defaults", "link_count", 0),
        ("coverage_defaults", "major_claim_evidence_coverage_ratio", 0.0),
        ("coverage_defaults", "all_verifiable_claim_evidence_coverage_ratio", 0.0),
        ("coverage_defaults", "major_claim_requirement_satisfied", False),
        ("coverage_defaults", "all_verifiable_claim_requirement_satisfied", False),
        ("coverage_defaults", "coverage_evaluable", True),
        ("coverage_defaults", "publication_permitted", True),
        ("coverage_defaults", "vacuous_zero_over_zero_pass_forbidden", False),
    ],
)
def test_rejects_inferred_mapping_evidence_or_vacuous_coverage(
    isolated_repository: Path,
    section: str,
    field: str,
    value: object,
) -> None:
    contract = _load(isolated_repository)
    contract[section][field] = value
    _write(isolated_repository, contract)
    _assert_rejected(isolated_repository)


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("section", "field"),
    [
        ("selection_defaults", "claim_id"),
        ("selection_defaults", "fact_id"),
        ("selection_defaults", "link_id"),
        ("selection_defaults", "policy_claim_type"),
        ("selection_defaults", "source_tier"),
    ],
)
def test_rejects_runtime_selection_values(
    isolated_repository: Path, section: str, field: str
) -> None:
    contract = _load(isolated_repository)
    contract[section][field] = "sensitive-canary-value"
    _write(isolated_repository, contract)
    message = _assert_rejected(isolated_repository)
    assert "sensitive-canary-value" not in message


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "value", [True, 1.0, "0"]
)
def test_rejects_bool_float_or_string_as_zero_action_count(
    isolated_repository: Path, value: object
) -> None:
    contract = _load(isolated_repository)
    contract["execution_boundary"]["action_counts"]["create_claim"] = value
    _write(isolated_repository, contract)
    _assert_rejected(isolated_repository)


def test_rejects_unknown_missing_and_reordered_contract_keys(
    isolated_repository: Path,
) -> None:
    original = _load(isolated_repository)
    variants = []
    unknown = copy.deepcopy(original)
    unknown["invented"] = None
    variants.append(unknown)
    missing = copy.deepcopy(original)
    del missing["coverage_defaults"]
    variants.append(missing)
    reordered = {"story_id": original["story_id"], "schema_version": 1}
    reordered.update(
        (key, value)
        for key, value in original.items()
        if key not in {"story_id", "schema_version"}
    )
    variants.append(reordered)
    for variant in variants:
        _write(isolated_repository, variant)
        _assert_rejected(isolated_repository)


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "payload",
    [
        b"schema_version: 1\nschema_version: 1\n",
        b"schema_version: &value 1\nstory_id: *value\n",
        b"schema_version: !!python/object/apply:os.system ['false']\n",
        b"defaults: &defaults {schema_version: 1}\n<<: *defaults\n",
    ],
)
def test_rejects_duplicate_alias_tag_and_merge_yaml(
    isolated_repository: Path, payload: bytes
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    _assert_rejected(isolated_repository)


def test_rejects_oversized_contract(isolated_repository: Path) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(
        b"#" * (base.MAX_DOCUMENT_BYTES + 1)
    )
    _assert_rejected(isolated_repository)


def test_predecessor_whitespace_is_not_digest_bound(isolated_repository: Path) -> None:
    path = isolated_repository / generator.ST0602_ARTIFACTS[2][0]
    path.write_bytes(path.read_bytes() + b"\n")
    assert generator.render_outputs(isolated_repository)


def test_rejects_predecessor_semantic_tamper_even_when_hash_is_rebound(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = generator.ST0602_ARTIFACTS[2][0]
    path = isolated_repository / relative
    tampered = path.read_text(encoding="utf-8").replace(
        '"facts": []', '"facts": [{"id": "invented"}]', 1
    )
    path.write_text(tampered, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (candidate, digest if candidate == relative else expected)
        for candidate, expected in generator.ST0602_ARTIFACTS
    )
    monkeypatch.setattr(generator, "ST0602_ARTIFACTS", rebound)
    contract = _load(isolated_repository)
    for row in contract["predecessors"][0]["files"]:
        if row["path"] == relative.as_posix():
            row["sha256"] = digest
    _write(isolated_repository, contract)
    message = _assert_rejected(isolated_repository)
    assert "predecessor.st0602.plan.projection" in message


def test_rejects_source_matrix_drift(isolated_repository: Path) -> None:
    path = isolated_repository / generator.MATRIX_PATH
    path.write_bytes(path.read_bytes().replace(b"CT-0389", b"CT-9999", 1))
    message = _assert_rejected(isolated_repository)
    assert "SOURCE_HASH_DRIFT" in message


def test_rejects_symlink_contract_target(isolated_repository: Path) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    replacement = contract.with_name("replacement.yaml")
    replacement.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(replacement.name)
    _assert_rejected(isolated_repository)


def test_rejects_symlink_contract_ancestor(isolated_repository: Path) -> None:
    changes = isolated_repository / "changes"
    moved = isolated_repository / "real-changes"
    changes.rename(moved)
    changes.symlink_to(moved.name, target_is_directory=True)
    _assert_rejected(isolated_repository)


def test_rejects_output_path_traversal_without_escape(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    escaped = isolated_repository.parent / "escaped.json"
    monkeypatch.setattr(generator, "REFERENCE_PLAN_PATH", Path("../escaped.json"))
    with pytest.raises(EXPECTED_ERRORS):
        generator.build(isolated_repository)
    assert not escaped.exists()


def test_check_rejects_generated_drift_without_writing(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.write_bytes(target.read_bytes() + b"\n")
    before = target.read_bytes()
    with pytest.raises(EXPECTED_ERRORS):
        generator.build(isolated_repository, check=True)
    assert target.read_bytes() == before
