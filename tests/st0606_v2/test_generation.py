from __future__ import annotations

from pathlib import Path

import yaml

from scripts import build_st0606_evidence_workspace_v2 as builder


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_owner_artifacts_are_byte_exact() -> None:
    for relative, expected in builder.expected_artifacts(REPO_ROOT):
        assert (REPO_ROOT / relative).read_bytes() == expected


def test_manifest_preserves_disabled_authority_and_formal_boundaries() -> None:
    manifest = yaml.safe_load((REPO_ROOT / builder.MANIFEST_PATH).read_bytes())
    assert manifest["story_id"] == "ST-0606"
    assert manifest["route_boundary"] == {
        "status": "UNREGISTERED_AUTH_TRANSPORT_UNRESOLVED",
        "registered_route_count": 0,
        "auth_transport_decision": "OD-010_UNRESOLVED",
    }
    assert manifest["authority"]
    assert all(value is False for value in manifest["authority"].values())
    assert manifest["verification"]["TST-022"] == "NOT_EXECUTED"
    assert manifest["verification"]["TST-024"] == "NOT_EXECUTED"
    assert manifest["verification"]["browser"] == "NOT_EXECUTED"
    assert manifest["verification"]["production"] == "NOT_EXECUTED"


def test_owner_check_passes() -> None:
    builder.build(REPO_ROOT, check=True)
