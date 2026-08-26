#!/usr/bin/env python3
"""Build the non-attesting ST-1607 gate report through the shared build core."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import yaml

try:
    from scripts.raos_build_core import atomic_write, canonical_json_bytes
except ModuleNotFoundError:  # direct ``python scripts/build_*.py`` execution
    from raos_build_core import atomic_write, canonical_json_bytes


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-1607/contracts/gate-evidence-pack.v1.yaml")
REPORT_PATH: Final = Path(
    "changes/st-1607/generated/gate-evidence-pack.local-blocked.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1607/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1607_gate_evidence_pack.py")
GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
OWNER_ID: Final = "build_st1607_gate_evidence_pack"
OWNER_VERSION: Final = 2
GATE_IDS: Final = ("GATE-0", "GATE-1", "GATE-2", "GATE-3", "GATE-4")
ACTIVE_BLOCKER_IDS: Final = (
    "OD-001",
    "OD-002",
    "OD-003",
    "OD-005",
    "OD-006",
    "OD-007",
    "OD-008",
    "OD-009",
    "OD-010",
    "OD-011",
    "OD-012",
    "OD-013",
    "OD-014",
    "OD-015",
)
DECISION_TARGETS: Final = (*GATE_IDS, "PRODUCTION_RELEASE")
GLOBAL_BLOCKERS: Final = (
    "TARGET_SNAPSHOT_CONTEXT_MISSING",
    "ST_1603_SECURITY_EVIDENCE_INELIGIBLE",
    "ST_1605_FAILURE_INJECTION_EVIDENCE_INELIGIBLE",
    "ST_1606_BACKUP_RESTORE_EVIDENCE_INELIGIBLE",
    "ACTIVE_BLOCKING_OPEN_DECISIONS",
    "FORMAL_TST_032_NOT_EXECUTED",
    "HUMAN_GATE_APPROVALS_MISSING",
)
EXPECTED_SOURCE_HASHES: Final = {
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    "docs/canonical/01_integration/RAOS_07_status_taxonomy_v1.0.yaml": "e3261a8a6102c1b93e6cc9006c52f01389ec31510e24ca37bc400437aebbf68b",
    "docs/canonical/00_master/RAOS_implementation_status_registry_v1.0.yaml": "1411f55ce60f6316e83567110fb2847e0db49239cb63dcabf9e81612c3b72ab8",
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac",
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md": "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460",
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
}
EXPECTED_PREDECESSORS: Final = {
    "st_0005": ("build_st0005_status", "STATUS_SOURCE"),
    "st_1603": ("build_st1603_security_verification", "SECURITY_VERIFICATION_INPUT"),
    "st_1605": ("build_st1605_failure_injection", "FAILURE_INJECTION_INPUT"),
    "st_1606": ("build_st1606_backup_restore", "BACKUP_RESTORE_INPUT"),
}


class GateEvidencePackError(RuntimeError):
    """Sanitized contract or generated-output validation failure."""


def _load_yaml(root: Path, relative: Path) -> dict[str, Any]:
    loaded = yaml.safe_load((root / relative).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise GateEvidencePackError(f"ST1607_INVALID_MAPPING path={relative}")
    return loaded


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_canonical_sources(contract: Mapping[str, Any], root: Path) -> None:
    rows = contract.get("sources")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_SOURCE_HASHES):
        raise GateEvidencePackError("ST1607_CANONICAL_INVENTORY_DRIFT")
    observed: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise GateEvidencePackError("ST1607_CANONICAL_ROW_INVALID")
        uri, digest = row.get("uri"), row.get("sha256")
        if not isinstance(uri, str) or not isinstance(digest, str):
            raise GateEvidencePackError("ST1607_CANONICAL_ROW_INVALID")
        observed[uri.removeprefix("repo://")] = digest
    if observed != EXPECTED_SOURCE_HASHES:
        raise GateEvidencePackError("ST1607_CANONICAL_BINDING_DRIFT")
    for relative, digest in observed.items():
        if _sha256(root / relative) != digest:
            raise GateEvidencePackError(f"ST1607_CANONICAL_HASH_DRIFT path={relative}")


def _validate_predecessors(contract: Mapping[str, Any]) -> None:
    bindings = contract.get("dependency_bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(EXPECTED_PREDECESSORS):
        raise GateEvidencePackError("ST1607_PREDECESSOR_INVENTORY_DRIFT")
    for key, (owner_id, role) in EXPECTED_PREDECESSORS.items():
        row = bindings[key]
        if not isinstance(row, dict) or row.get("owner_id") != owner_id:
            raise GateEvidencePackError(f"ST1607_PREDECESSOR_OWNER_DRIFT key={key}")
        if row.get("owner_version") != OWNER_VERSION or row.get("role") != role:
            raise GateEvidencePackError(f"ST1607_PREDECESSOR_VERSION_DRIFT key={key}")
    decision = contract.get("decision_gate_binding")
    if (
        not isinstance(decision, dict)
        or decision.get("owner_id") != "build_st0006_decision_gates"
    ):
        raise GateEvidencePackError("ST1607_DECISION_OWNER_DRIFT")
    if decision.get("owner_version") != OWNER_VERSION:
        raise GateEvidencePackError("ST1607_DECISION_VERSION_DRIFT")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    _validate_canonical_sources(contract, root)
    _validate_predecessors(contract)
    document = contract.get("document")
    decision = contract.get("decision_input")
    report = contract.get("gate_report")
    if not isinstance(document, dict) or document.get("story_id") != "ST-1607":
        raise GateEvidencePackError("ST1607_DOCUMENT_DRIFT")
    if (
        not isinstance(decision, dict)
        or decision.get("active_blocker_ids") != list(ACTIVE_BLOCKER_IDS)
    ):
        raise GateEvidencePackError("ST1607_DECISION_INPUT_DRIFT")
    gates = report.get("gates") if isinstance(report, dict) else None
    if not isinstance(gates, list) or [row.get("gate_id") for row in gates] != list(
        GATE_IDS
    ):
        raise GateEvidencePackError("ST1607_GATE_INVENTORY_DRIFT")
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH), root)


def gate_evidence_pack(contract: Mapping[str, Any]) -> dict[str, object]:
    copied = json.loads(json.dumps(contract))
    return {
        "schema_version": "2.0.0",
        "generator": {"owner_id": OWNER_ID, "owner_version": OWNER_VERSION},
        "story": {"id": "ST-1607", "scope": "LOCAL_BLOCKED_REPORT_ONLY"},
        "classification": copied["document"]["classification"],
        **copied,
    }


def _manifest_bytes(report_bytes: bytes, contract: Mapping[str, Any]) -> bytes:
    manifest = {
        "manifest_version": 2,
        "generator": {"owner_id": OWNER_ID, "owner_version": OWNER_VERSION},
        "story_ids": ["ST-1607"],
        "semantic_inputs": {
            "contract": {
                "uri": f"repo://{CONTRACT_PATH}",
                "semantic_id": contract["document"]["id"],
                "version": contract["document"]["version"],
            },
            "predecessors": [
                {"owner_id": owner_id, "owner_version": OWNER_VERSION}
                for owner_id, _role in EXPECTED_PREDECESSORS.values()
            ]
            + [
                {
                    "owner_id": "build_st0006_decision_gates",
                    "owner_version": OWNER_VERSION,
                }
            ],
            "canonical_package": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_SOURCE_HASHES.items()
            ],
        },
        "outputs": [
            {
                "uri": f"repo://{REPORT_PATH}",
                "bytes": len(report_bytes),
                "sha256": hashlib.sha256(report_bytes).hexdigest(),
            }
        ],
        "external_unexecuted": [
            "TST-032",
            "staging",
            "live_provider",
            "release",
            "production",
        ],
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode()


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    report = canonical_json_bytes(gate_evidence_pack(contract))
    return {REPORT_PATH: report, MANIFEST_PATH: _manifest_bytes(report, contract)}


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    for relative, expected in render_outputs(root).items():
        target = root / relative
        if check:
            if not target.is_file() or target.read_bytes() != expected:
                raise GateEvidencePackError(
                    f"ST1607_GENERATED_OUTPUT_DRIFT path={relative}"
                )
        else:
            atomic_write(relative, expected, root=root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        build(check=arguments.check)
    except (GateEvidencePackError, OSError, UnicodeError, yaml.YAMLError) as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
