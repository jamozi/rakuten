#!/usr/bin/env python3
"""Build the non-authoritative ST-1701 unresolved business-input registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st0006_decision_gates as predecessor  # noqa: E402
from scripts import build_st1506_production_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml"
)
REFERENCE_PATH: Final = Path(
    "changes/st-1701/generated/unresolved-mvp-business-inputs.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1701/manifest.yaml")
README_PATH: Final = Path("changes/st-1701/README.md")
GENERATOR_PATH: Final = Path("scripts/build_st1701_business_inputs.py")
TEST_PATHS: Final = (
    Path("tests/st1701/conftest.py"),
    Path("tests/st1701/test_contract.py"),
    Path("tests/st1701/test_generation.py"),
    Path("tests/st1701/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1701_business_inputs.py"
)

POLICY_PATH: Final = Path("changes/st-0006/contracts/decision-gate-policy.v1.yaml")
REPORT_PATH: Final = Path("changes/st-0006/gate-blocker-report.v1.yaml")
PREDECESSOR_GENERATOR_PATH: Final = Path("scripts/build_st0006_decision_gates.py")

TOP_LEVEL_KEYS: Final = (
    "document",
    "sources",
    "predecessor_binding",
    "scope",
    "decisions",
    "business_inputs",
    "safe_defaults",
    "activation",
    "gates",
    "action_boundary",
    "evidence_boundary",
    "downstream_boundary",
)
SCOPED_IDS: Final = (
    "OD-001",
    "OD-002",
    "OD-005",
    "OD-006",
    "OD-007",
    "OD-008",
    "OD-009",
)
BLOCKED_TARGETS: Final = (
    "GATE-0",
    "GATE-1",
    "GATE-2",
    "GATE-3",
    "GATE-4",
    "PRODUCTION_RELEASE",
)
GATE_IDS: Final = BLOCKED_TARGETS[:5]
ACTION_NAMES: Final = (
    "decision",
    "approval",
    "research",
    "external",
    "publication",
    "staging",
    "release",
    "production",
)

EXPECTED_SOURCE_ROWS: Final = (
    (
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        7943,
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        3955,
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        4956,
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        24993,
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        11395,
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        71458,
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md",
        10741,
        "9996eb1ff99d84cd1f666663011e53de37ab5c99234707698cad9be04d972d8b",
    ),
)
EXPECTED_PREDECESSOR_ROWS: Final = (
    (
        PREDECESSOR_GENERATOR_PATH.as_posix(),
        66037,
        "0f6ad788aa90660775cb7852f7bb2ab7d8712d62bbf17dcaa651fe0fb8f6e06f",
    ),
    (
        POLICY_PATH.as_posix(),
        1064,
        "127da325fa02682f2d3ce13bedfb0830e47eb17db401fa4d94b73c698d08d989",
    ),
    (
        REPORT_PATH.as_posix(),
        9999,
        "92fc3fdbe021db08508bc0cc5ee1f6542de94d5fc336b40e45ace30037bdff15",
    ),
)
IMPLEMENTATION_DEPENDENCIES: Final = {
    "scripts/build_st1506_production_deployment.py": (
        "ef2c4c887886444041609fc88b6fdef928190e56c4f7882b1f76e3a127ce863f"
    )
}

EXPECTED_BUSINESS_INPUTS: Final[dict[str, object]] = {
    "initial_category": None,
    "brand_name": None,
    "domain_name": None,
    "operator_identity": None,
    "primary_reviewer": None,
    "alternate_reviewer": None,
    "labor_hourly_cost": None,
    "product_identity_rules": None,
    "freshness_sla": None,
    "legal_review_boundary": None,
    "monthly_budget": None,
    "budget_currency": None,
    "automatic_stop_threshold": None,
    "resolution_payload": None,
    "approval_payload": None,
    "evidence_payload": None,
    "research_payload": None,
}
EXPECTED_SAFE_DEFAULTS: Final[dict[str, object]] = {
    "selected_values": "FORBIDDEN",
    "safe_defaults_are_resolutions": False,
    "synthetic_fixtures_only": True,
    "category_specific_implementation": "BLOCKED",
    "external_publication": "BLOCKED",
    "labor_cost_basis": "UNKNOWN",
    "human_review": "REQUIRED_UNCONFIGURED",
    "automatic_product_identity_merge": "DISABLED",
    "stale_content_visibility": "HIDDEN",
    "legal_judgment_by_ai_or_developer": "FORBIDDEN",
    "production": "DISABLED",
}
EXPECTED_ACTION_BOUNDARY: Final[dict[str, object]] = {
    "external_actions": "FORBIDDEN",
    "external_publication": "FORBIDDEN",
    "staging": "FORBIDDEN",
    "release": "FORBIDDEN",
    "production": "FORBIDDEN",
    "action_counts": {name: 0 for name in ACTION_NAMES},
}
EXPECTED_EVIDENCE_BOUNDARY: Final[dict[str, object]] = {
    "formal_tst_032": "NOT_EXECUTED",
    "human_approvals": "NOT_OBTAINED",
    "external_evidence": "NOT_OBTAINED",
    "canonical_status": "UNCHANGED",
    "st_1701_acceptance_achieved": False,
    "local_evidence": "IMPLEMENTATION_ONLY_NOT_FORMAL_VALIDATION",
}
EXPECTED_DOWNSTREAM_BOUNDARY: Final[dict[str, object]] = {
    "st_1702_ready": False,
    "readiness_status": "BLOCKED_BY_ST_1701_ACCEPTANCE",
    "publication_ready": False,
    "release_ready": False,
    "production_ready": False,
}


class BusinessInputsError(RuntimeError):
    """Sanitized ST-1701 owner failure."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"ST1701_ERROR code={code} field={field}")
        self.code = code
        self.field = field


def _fail(code: str, field: str) -> NoReturn:
    raise BusinessInputsError(code, field) from None


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_TYPE", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("INVALID_TYPE", field)
    return value


def _exact_mapping(
    value: object, expected: Mapping[str, object], field: str
) -> Mapping[str, Any]:
    observed = _mapping(value, field)
    if tuple(observed.keys()) != tuple(expected.keys()) or observed != expected:
        _fail("CONTRACT_SECTION_DRIFT", field)
    return observed


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, relative: Path, field: str) -> bytes:
    path = cast(
        Path,
        base._repository_regular_file(root, relative, field),  # noqa: SLF001
    )
    try:
        return path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _verify_rows(
    root: Path,
    rows: object,
    expected: Sequence[tuple[str, int, str]],
    field: str,
) -> None:
    observed_rows = _list(rows, field)
    if len(observed_rows) != len(expected):
        _fail("INVENTORY_DRIFT", field)
    for index, (raw, expected_row) in enumerate(
        zip(observed_rows, expected, strict=True)
    ):
        row = _mapping(raw, f"{field}[{index}]")
        if tuple(row.keys()) != ("uri", "bytes", "sha256"):
            _fail("INVENTORY_SCHEMA_DRIFT", f"{field}[{index}]")
        relative, size, digest = expected_row
        if row != {"uri": f"repo://{relative}", "bytes": size, "sha256": digest}:
            _fail("INVENTORY_DRIFT", f"{field}[{index}]")
        content = _read(root, Path(relative), f"{field}.input")
        if len(content) != size or _sha256(content) != digest:
            _fail("INPUT_HASH_DRIFT", field)


def _validate_implementation_dependencies(root: Path) -> None:
    for relative, digest in IMPLEMENTATION_DEPENDENCIES.items():
        if _sha256(_read(root, Path(relative), "implementation.input")) != digest:
            _fail("IMPLEMENTATION_DEPENDENCY_DRIFT", "implementation")


def _validate_predecessor(
    contract: Mapping[str, Any], root: Path
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    binding = _mapping(contract["predecessor_binding"], "predecessor_binding")
    if tuple(binding.keys()) != (
        "story_id",
        "owner_check",
        "generator",
        "policy",
        "report",
        "required_semantics",
    ):
        _fail("PREDECESSOR_SCHEMA_DRIFT", "predecessor_binding")
    if binding["story_id"] != "ST-0006":
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.story_id")
    if binding["owner_check"] != "scripts.build_st0006_decision_gates.check_generated":
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.owner_check")
    for key, expected in zip(
        ("generator", "policy", "report"), EXPECTED_PREDECESSOR_ROWS, strict=True
    ):
        relative, size, digest = expected
        _exact_mapping(
            binding[key],
            {"uri": f"repo://{relative}", "bytes": size, "sha256": digest},
            f"predecessor.{key}",
        )
        content = _read(root, Path(relative), f"predecessor.{key}")
        if len(content) != size or _sha256(content) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", f"predecessor.{key}")
    _exact_mapping(
        binding["required_semantics"],
        {
            "overall_open_decision_check": "BLOCKED",
            "global_decision_count": 15,
            "global_unresolved_blocker_count": 14,
            "global_blocked_target_count": 6,
            "target_mapping": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS",
            "required_by_interpretation": "OPAQUE_CONTEXT_ONLY",
            "safe_default_interpretation": "SAFE_FALLBACK_NOT_RESOLUTION",
            "clear_does_not_imply_gate_pass": True,
        },
        "predecessor.required_semantics",
    )
    policy = _load_yaml(root, POLICY_PATH, "predecessor.policy")
    report = _load_yaml(root, REPORT_PATH, "predecessor.report")
    policy_mapping = _mapping(policy.get("mapping"), "policy.mapping")
    if policy_mapping != {
        "targets": list(BLOCKED_TARGETS),
        "active_blocker": "blocking=true AND status!=RESOLVED",
        "target_policy": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS",
        "required_by_interpretation": "OPAQUE_CONTEXT_ONLY",
        "default_behavior_interpretation": "SAFE_FALLBACK_NOT_RESOLUTION",
        "clear_means_gate_pass": False,
    }:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "policy.mapping")
    if _mapping(report.get("counts"), "report.counts") != {
        "decisions": 15,
        "resolved": 0,
        "unresolved": 15,
        "blocking": 14,
        "unresolved_blocking": 14,
        "unresolved_nonblocking": 1,
        "blocked_targets": 6,
    }:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "report.counts")
    if report.get("overall_open_decision_check") != "BLOCKED":
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "report.status")
    decisions = [
        _mapping(row, "report.decisions")
        for row in _list(report.get("decisions"), "report.decisions")
    ]
    if root.resolve() == REPO_ROOT.resolve():
        try:
            predecessor.check_generated()
        except Exception:
            _fail("PREDECESSOR_OWNER_CHECK_FAILED", "predecessor")
    return report, decisions


def _expected_decisions(
    report_decisions: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    by_id = {str(row["id"]): row for row in report_decisions}
    if (
        tuple(identifier for identifier in by_id if identifier in SCOPED_IDS)
        != SCOPED_IDS
    ):
        _fail("SCOPED_ORDER_DRIFT", "decisions")
    expected: list[dict[str, object]] = []
    for identifier in SCOPED_IDS:
        source = by_id.get(identifier)
        if source is None:
            _fail("SCOPED_INVENTORY_DRIFT", "decisions")
        expected.append(
            {
                "id": identifier,
                "topic": source["topic"],
                "source_status": source["source_status"],
                "required_by": source["required_by"],
                "owner": source["owner"],
                "decision_needed": source["decision_needed"],
                "default_behavior": source["default_behavior"],
                "blocking": True,
                "resolution_state": "UNRESOLVED",
                "active_blocker": True,
                "blocked_targets": list(BLOCKED_TARGETS),
                "safe_default_is_resolution": False,
                "selected_value": None,
                "resolution_payload": "FORBIDDEN_IN_V1",
            }
        )
    if expected[3]["source_status"] != "EXTERNAL_EVIDENCE_REQUIRED":
        _fail("SCOPED_STATUS_DRIFT", "decisions.OD-006")
    if any(
        row["source_status"] != "HUMAN_DECISION_REQUIRED"
        for index, row in enumerate(expected)
        if index != 3
    ):
        _fail("SCOPED_STATUS_DRIFT", "decisions")
    return expected


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract.keys()) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact_mapping(
        contract["document"],
        {
            "id": "RAOS-UNRESOLVED-MVP-BUSINESS-INPUTS-001",
            "version": "1.0.0",
            "story_id": "ST-1701",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "classification": ("SOURCE_DERIVED_NON_AUTHORITATIVE_UNRESOLVED_REGISTRY"),
            "executable": False,
            "canonical_acceptance_achieved": False,
        },
        "document",
    )
    _verify_rows(root, contract["sources"], EXPECTED_SOURCE_ROWS, "sources")
    _validate_implementation_dependencies(root)
    _report, report_decisions = _validate_predecessor(contract, root)
    _exact_mapping(
        contract["scope"],
        {
            "decision_ids": list(SCOPED_IDS),
            "decision_count": 7,
            "resolved_count": 0,
            "unresolved_count": 7,
            "active_blocker_count": 7,
            "inventory_kind": "EXACT_ORDERED_ST0006_SUBSET",
            "source_facts_interpretation": "OPAQUE_NO_DERIVATION",
            "global_counts_preserved": True,
        },
        "scope",
    )
    decisions = _list(contract["decisions"], "decisions")
    if decisions != _expected_decisions(report_decisions):
        _fail("DECISION_PROJECTION_DRIFT", "decisions")
    _exact_mapping(
        contract["business_inputs"], EXPECTED_BUSINESS_INPUTS, "business_inputs"
    )
    _exact_mapping(contract["safe_defaults"], EXPECTED_SAFE_DEFAULTS, "safe_defaults")
    _exact_mapping(
        contract["activation"],
        {"enabled": False, "status": "BLOCKED_UNRESOLVED_INPUTS"},
        "activation",
    )
    expected_gates = [
        {"gate_id": gate, "status": "BLOCKED", "blocker_count": 7} for gate in GATE_IDS
    ]
    if _list(contract["gates"], "gates") != expected_gates:
        _fail("GATE_BOUNDARY_DRIFT", "gates")
    action_boundary = _exact_mapping(
        contract["action_boundary"], EXPECTED_ACTION_BOUNDARY, "action_boundary"
    )
    for key, value in _mapping(
        action_boundary["action_counts"], "action_counts"
    ).items():
        if type(value) is not int or value != 0:
            _fail("NONZERO_ACTION", f"action_counts.{key}")
    _exact_mapping(
        contract["evidence_boundary"],
        EXPECTED_EVIDENCE_BOUNDARY,
        "evidence_boundary",
    )
    _exact_mapping(
        contract["downstream_boundary"],
        EXPECTED_DOWNSTREAM_BOUNDARY,
        "downstream_boundary",
    )
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_document(contract: Mapping[str, Any]) -> dict[str, object]:
    return {
        "document": {
            "id": "RAOS-UNRESOLVED-MVP-BUSINESS-INPUTS-REGISTRY-001",
            "version": "1.0.0",
            "story_id": "ST-1701",
            "classification": ("SOURCE_DERIVED_NON_AUTHORITATIVE_UNRESOLVED_REGISTRY"),
            "authority": "NON_AUTHORITATIVE",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "executable": False,
            "canonical_acceptance_achieved": False,
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "predecessor_binding": contract["predecessor_binding"],
        "registry": {
            **dict(_mapping(contract["scope"], "scope")),
            "global_decision_count": 15,
            "global_unresolved_blocker_count": 14,
            "global_blocked_target_count": 6,
            "blocked_targets": list(BLOCKED_TARGETS),
            "decisions": contract["decisions"],
        },
        "business_inputs": contract["business_inputs"],
        "safe_defaults": contract["safe_defaults"],
        "activation": contract["activation"],
        "gates": contract["gates"],
        "action_boundary": contract["action_boundary"],
        "evidence_boundary": contract["evidence_boundary"],
        "downstream_boundary": contract["downstream_boundary"],
        "prohibited_interpretations": [
            "SAFE_DEFAULT_IS_NOT_A_DECISION",
            "UNRESOLVED_REGISTRY_IS_NOT_APPROVAL",
            "LOCAL_TESTS_ARE_NOT_FORMAL_TST_032",
            "ZERO_ACTIONS_ARE_NOT_ST_1701_ACCEPTANCE",
            "SCOPED_SEVEN_DO_NOT_CLEAR_OTHER_GLOBAL_BLOCKERS",
            "NO_CATEGORY_PUBLICATION_RELEASE_OR_PRODUCTION_VALUE_MAY_BE_INFERRED",
        ],
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    document = {
        "document": {
            "id": "RAOS-UNRESOLVED-MVP-BUSINESS-INPUTS-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1701",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": [
                {"uri": f"repo://{path}", "bytes": size, "sha256": digest}
                for path, size, digest in EXPECTED_SOURCE_ROWS
            ],
            "predecessor_inputs": [
                {"uri": f"repo://{path}", "bytes": size, "sha256": digest}
                for path, size, digest in EXPECTED_PREDECESSOR_ROWS
            ],
            "implementation_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in IMPLEMENTATION_DEPENDENCIES.items()
            ],
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact_row(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "authority": "NON_AUTHORITATIVE",
            "decision_count": 7,
            "resolved_count": 0,
            "active_blocker_count": 7,
            "global_unresolved_blocker_count": 14,
            "activation": "BLOCKED_UNRESOLVED_INPUTS",
            "formal_tst_032": "NOT_EXECUTED",
            "st_1701_acceptance_achieved": False,
            "st_1702_ready": False,
            "publication_ready": False,
            "release_ready": False,
            "production_ready": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode()


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_document(contract))
    return {
        REFERENCE_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(root, reference_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = base._output_file(root, relative)  # noqa: SLF001
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative, content in outputs.items():
        base._atomic_write(root, relative, content)  # noqa: SLF001


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except (BusinessInputsError, base.ProductionDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1701 unresolved business-input registry checked"
        if args.check
        else "ST-1701 unresolved business-input registry generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
