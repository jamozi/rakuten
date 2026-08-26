"""ST-0702 fail-closed semantic checks."""

from __future__ import annotations

import copy

import pytest

from scripts import build_st0702_context_pack_reference_plan as generator


def test_external_execution_enablement_is_rejected() -> None:
    contract = copy.deepcopy(generator.load_contract())
    contract["execution_boundary"]["network_access"] = True
    with pytest.raises(generator.ContextPackReferenceError):
        generator.validate_contract(contract)


def test_canonical_checksum_drift_is_rejected(tmp_path) -> None:
    root = tmp_path / "repository"
    required = (
        generator.CONTRACT_PATH,
        generator.STORY_PATH,
        generator.INTEGRATION_PATH,
        generator.ST0604_CONTRACT_PATH,
        generator.ST0701_README_PATH,
        generator.ST0701_REGISTRY_PATH,
        generator.ST0701_MANIFEST_PATH,
    )
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((generator.REPO_ROOT / relative).read_bytes())
    (root / generator.STORY_PATH).write_bytes(b"drift")
    with pytest.raises(generator.ContextPackReferenceError):
        generator.load_contract(root)


def test_owner_binding_drift_is_rejected() -> None:
    contract = copy.deepcopy(generator.load_contract())
    contract["predecessors"]["st0701"]["owner_version"] = "999"
    with pytest.raises(generator.ContextPackReferenceError):
        generator.validate_contract(contract)
