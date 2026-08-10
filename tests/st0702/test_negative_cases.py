"""Hostile closed-boundary tests for the ST-0702 owner builder."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import build_st0702_context_pack_reference_plan as generator


def test_contract_safe_boundary_mutations_are_rejected(
    isolated_repository: Path,
) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    mutations = (
        ("document", "executable", True),
        ("document", "decision", "READY"),
        ("build_boundary", "build_permitted", True),
        ("build_boundary", "manifest_creation_permitted", True),
        ("execution_boundary", "provider_call", "EXECUTED"),
    )
    original = path.read_bytes()
    for section, key, value in mutations:
        contract = yaml.safe_load(original)
        contract[section][key] = value
        path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
        with pytest.raises(generator.ContextPackReferenceError):
            generator.render_outputs(isolated_repository)
    path.write_bytes(original)


@pytest.mark.parametrize(
    "relative",
    [
        generator.STORY_PATH,
        generator.INTEGRATION_PATH,
        *(path for path, _digest in generator.ST0604_ARTIFACTS),
        *(path for path, _digest in generator.ST0701_ARTIFACTS),
    ],
)
def test_authority_or_predecessor_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.ContextPackReferenceError):
        generator.render_outputs(isolated_repository)


def test_duplicate_yaml_key_and_generated_drift_are_rejected(
    isolated_repository: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    contract.write_bytes(contract.read_bytes() + b"\ndocument: {}\n")
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)

    contract.write_bytes((generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes())
    generator.build(isolated_repository)
    output = isolated_repository / generator.REFERENCE_PLAN_PATH
    output.write_bytes(output.read_bytes() + b"drift")
    with pytest.raises(generator.ContextPackReferenceError):
        generator.build(isolated_repository, check=True)


def test_path_traversal_and_output_symlink_ancestor_are_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)
    monkeypatch.undo()

    generated = isolated_repository / generator.REFERENCE_PLAN_PATH.parent
    outside = tmp_path / "outside"
    outside.mkdir()
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.symlink_to(outside, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert not tuple(outside.iterdir())
