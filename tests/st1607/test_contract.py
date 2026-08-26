from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import build_st1607_gate_evidence_pack as builder

from .support import repository_copy


def test_contract_uses_canonical_checksums_and_semantic_predecessors() -> None:
    contract = builder.load_contract()
    assert len(contract["sources"]) == len(builder.EXPECTED_SOURCE_HASHES)
    assert {
        row["owner_id"] for row in contract["dependency_bindings"].values()
    } == {owner for owner, _role in builder.EXPECTED_PREDECESSORS.values()}
    assert contract["decision_gate_binding"]["owner_id"] == (
        "build_st0006_decision_gates"
    )
    serialized = yaml.safe_dump(contract)
    assert "base_commit" not in serialized
    assert "reviewed_implementation_tree_commit" not in serialized
    assert "approval_sha256" not in serialized


def test_canonical_checksum_drift_is_rejected(tmp_path: Path) -> None:
    root = repository_copy(tmp_path)
    relative = Path(next(iter(builder.EXPECTED_SOURCE_HASHES)))
    (root / relative).write_bytes((root / relative).read_bytes() + b"\n")
    with pytest.raises(builder.GateEvidencePackError, match="CANONICAL_HASH_DRIFT"):
        builder.load_contract(root)


def test_predecessor_owner_or_version_drift_is_rejected(tmp_path: Path) -> None:
    root = repository_copy(tmp_path)
    contract = yaml.safe_load((root / builder.CONTRACT_PATH).read_text())
    contract["dependency_bindings"]["st_1603"]["owner_version"] = 3
    (root / builder.CONTRACT_PATH).write_text(yaml.safe_dump(contract))
    with pytest.raises(builder.GateEvidencePackError, match="PREDECESSOR_VERSION_DRIFT"):
        builder.load_contract(root)
