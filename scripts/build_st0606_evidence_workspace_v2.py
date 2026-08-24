#!/usr/bin/env python3
"""Build the deterministic, disabled ST-0606 V2 evidence read projection."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT / "python", REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from raos.adapters.recorded_claim_evidence import (  # noqa: E402
    load_recorded_claim_evidence_fixture,
)
from raos.domain.evidence.claim_evidence import (  # noqa: E402
    CoverageStatus,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)


EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 8 * 1024 * 1024

CONTRACT_PATH: Final = Path("changes/st-0606/contracts/evidence-workspace.v2.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-0606/fixtures/evidence-workspace-recorded.synthetic.v2.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-0606/generated/evidence-workspace-recorded.v2.json"
)
GENERATED_TS_PATH: Final = Path("packages/web-ui/src/evidence-workspace-recorded.v2.ts")
MANIFEST_PATH: Final = Path("changes/st-0606/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0606_evidence_workspace_v2.py")
ST0604_LIFECYCLE_PATH: Final = Path(
    "changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json"
)
ST0605_FIXTURE_PATH: Final = Path(
    "changes/st-0605/generated/claim-evidence-runtime-pass.v1.json"
)

EXPECTED_SOURCE_BINDINGS: Final = {
    "repo://changes/st-0604/contracts/source-packet-lifecycle-reference-plan.v1.yaml": (
        "a80c41890e6bae7077728d1456f5a3b5d99b1877e047f581beff8ed41e0c2cec"
    ),
    "repo://changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json": (
        "00e6e974f9003ee92cb0a9b4a0ca5a975286e7fd41a6e32cf1224e312cd78cec"
    ),
    "repo://changes/st-0604/manifest.yaml": (
        "56144e0b9ab315a647d92c665f7502129d3576fac2d9524ca647dc29bfeabdc0"
    ),
    "repo://changes/st-0605/contracts/claim-evidence-runtime.v1.yaml": (
        "7d84f3a4883a226eff782e976aa72169646be67bf1fc798af5b1b65367d2c3cb"
    ),
    "repo://changes/st-0605/generated/claim-evidence-runtime-pass.v1.json": (
        "eb1c36bd1f70ea27e57e1720b937211286578136e701664b5fb4c8c823395226"
    ),
    "repo://changes/st-0605/runtime-manifest.v1.yaml": (
        "1bdc789e2faed53a66c3d6605a7fe0d4d842a21799c3a6202b02e3231eac3efb"
    ),
    "repo://changes/st-0605/contracts/claim-evidence-coverage-reference-plan.v1.yaml": (
        "3eb1bccf5e6b2599690e2c9cdd2490dc0a2177e41689f8955c0bc1dfb8e068f2"
    ),
    "repo://changes/st-0605/generated/claim-evidence-coverage-reference-plan.v1.json": (
        "820ca8cb8e302adc862be95ad9e6ca59f30ca8795ba0191018b99407aae08d74"
    ),
    "repo://changes/st-0605/manifest.yaml": (
        "c6d79d4d566ec1bc2a3268cf3394ec5c9f4bb27a335466f12be0a87cef9e1573"
    ),
    "repo://packages/web-ui/src/route-guard.ts": (
        "8395f542c7c65445fa3d1bec4a0e037c96610da8589e1807604b4fb3fa6a584f"
    ),
    "repo://changes/st-1101/README.md": (
        "b2bb91e89d5948f8081853e39596951adcee16974ce2a6ffa159892310ead08c"
    ),
}

EXPECTED_CANONICAL_BINDINGS: Final = {
    "repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "repo://docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md": (
        "0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e"
    ),
    "repo://docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml": (
        "dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050"
    ),
    "repo://docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml": (
        "986ed1682b0f6b48c7e9fab04ff51229c000f4673e3cc3981e50903832f208f2"
    ),
    "repo://docs/canonical/02_ui/RAOS_08_workflow_catalog_v1.0.yaml": (
        "59983683ec920cf450d0d887ee43f0b9871e500c2025562f9bec5c6bbc6fe87e"
    ),
    "repo://docs/canonical/02_ui/RAOS_08_accessibility_checklist_v1.0.csv": (
        "690233f34abb08608e3e1241e6108fb93d4c6bb47ffe23be02e34f2a02b6d77e"
    ),
    "repo://docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml": (
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984"
    ),
    "repo://docs/canonical/04_security/RAOS_10_data_classification_v1.0.yaml": (
        "59854810967b8fa1f0df759bf5160d128fc4dea00084a95f6b4f11876a415ab0"
    ),
    "repo://docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "repo://docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml": (
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd"
    ),
    "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
}

EXPECTED_SCREENS: Final = (
    (
        "EVD-001",
        "Source Packet一覧",
        "/admin/evidence/source-packets",
        ("MANAGING_EDITOR", "EDITOR", "REVIEWER"),
        ("UI-C001", "UI-C005", "UI-C007", "UI-C010", "UI-C035", "UI-C036"),
    ),
    (
        "EVD-002",
        "Source Packet詳細",
        "/admin/evidence/source-packets/{id}",
        ("MANAGING_EDITOR", "EDITOR", "REVIEWER"),
        (
            "UI-C001",
            "UI-C005",
            "UI-C018",
            "UI-C019",
            "UI-C020",
            "UI-C021",
            "UI-C035",
            "UI-C036",
        ),
    ),
    (
        "EVD-003",
        "Fact Explorer",
        "/admin/evidence/facts",
        ("EDITOR", "REVIEWER", "ANALYST"),
        ("UI-C001", "UI-C005", "UI-C007", "UI-C019", "UI-C035", "UI-C036"),
    ),
    (
        "EVD-004",
        "Evidence Conflict Queue",
        "/admin/evidence/conflicts",
        ("MANAGING_EDITOR", "EDITOR", "REVIEWER"),
        ("UI-C001", "UI-C005", "UI-C007", "UI-C010", "UI-C035", "UI-C036"),
    ),
)

TOP_LEVEL_KEYS: Final = (
    "document",
    "source_bindings",
    "canonical_bindings",
    "screen_contract",
    "projection_contract",
    "source_access_contract",
    "unknown_contract",
    "accessibility_contract",
    "security_controls",
    "authority_boundary",
    "verification_boundary",
)

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-0606/PREFLIGHT-v2.md"),
    Path("changes/st-0606/README.md"),
    Path("changes/st-0606/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("docs/execplans/ST-0606.md"),
    Path("docs/worklogs/ST-0606.md"),
    Path("packages/web-ui/src/evidence-workspace-v2.ts"),
    GENERATOR_PATH,
    Path("tests/st0606_v2/evidence-workspace-v2-generation.test.ts"),
    Path("tests/st0606_v2/evidence-workspace-v2-model.test.ts"),
    Path("tests/st0606_v2/evidence-workspace-v2-negative.test.ts"),
    Path("tests/st0606_v2/test_generation.py"),
    Path("tests/st0606_v2/test_negative.py"),
)


class EvidenceWorkspaceBuildError(RuntimeError):
    """Sanitized, closed ST-0606 owner-build failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise EvidenceWorkspaceBuildError(
        f"ST-0606 build failed: {code} field={field}"
    ) from None


class UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: UniqueSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    if not isinstance(node, yaml.MappingNode):
        _fail("YAML_SHAPE_INVALID", "contract")
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            _fail("YAML_DUPLICATE_KEY", "contract")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("PATH_INVALID", relative.as_posix())
    return root / relative


def _read_regular(path: Path, *, maximum: int = MAX_SOURCE_BYTES) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            _fail("INPUT_UNAVAILABLE", path.as_posix())
        if stat.S_ISLNK(metadata.st_mode):
            _fail("SYMLINK_REJECTED", path.as_posix())
    try:
        metadata = absolute.stat()
        payload = absolute.read_bytes()
    except OSError:
        _fail("INPUT_UNAVAILABLE", path.as_posix())
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size != len(payload)
        or not payload
        or len(payload) > maximum
    ):
        _fail("INPUT_INVALID", path.as_posix())
    return payload


def _mapping(value: object, field: str) -> dict[str, object]:
    if type(value) is not dict or any(
        type(key) is not str for key in cast(dict[object, object], value)
    ):
        _fail("SHAPE_INVALID", field)
    return cast(dict[str, object], value)


def _sequence(value: object, field: str) -> list[object]:
    if type(value) is not list or len(cast(list[object], value)) > 10_000:
        _fail("SHAPE_INVALID", field)
    return cast(list[object], value)


def _string(value: object, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("VALUE_INVALID", field)
    return value


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail("JSON_DUPLICATE_KEY", "json")
        result[key] = value
    return result


def _load_json(root: Path, relative: Path) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, relative))
    try:
        value = json.loads(payload, object_pairs_hook=_json_pairs)
    except EvidenceWorkspaceBuildError:
        raise
    except Exception:
        _fail("JSON_INVALID", relative.as_posix())
    return _mapping(value, relative.as_posix())


def _load_contract(root: Path) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, CONTRACT_PATH))
    try:
        value = yaml.load(payload, Loader=UniqueSafeLoader)
    except EvidenceWorkspaceBuildError:
        raise
    except Exception:
        _fail("YAML_INVALID", "contract")
    contract = _mapping(value, "contract")
    if tuple(contract) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    document = _mapping(contract["document"], "document")
    if document != {
        "schema_version": 2,
        "story_id": "ST-0606",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_RECORDED_SYNTHETIC_EVIDENCE_WORKSPACE_V2"
        ),
        "status": "LOCAL_CODE_COMPLETE",
        "executable_environments": ["ENV-DEV", "ENV-CI"],
        "canonical_status": "UNCHANGED",
        "historical_v1_replaced": False,
        "data_classification": "CONFIDENTIAL",
        "production_eligible": False,
    }:
        _fail("CONTRACT_VALUE_INVALID", "document")
    _validate_bindings(root, contract)
    _validate_screens(contract)
    _validate_contract_boundaries(contract)
    return contract


def _validate_bindings(root: Path, contract: dict[str, object]) -> None:
    observed: dict[str, str] = {}
    for group_value in _sequence(contract["source_bindings"], "source_bindings"):
        group = _mapping(group_value, "source_binding")
        if tuple(group) != ("story_id", "semantic", "artifacts"):
            _fail("CONTRACT_SHAPE_INVALID", "source_binding")
        _string(group["story_id"], "source_binding.story_id")
        _string(group["semantic"], "source_binding.semantic")
        for artifact_value in _sequence(group["artifacts"], "source_artifacts"):
            artifact = _mapping(artifact_value, "source_artifact")
            if tuple(artifact) != ("uri", "sha256"):
                _fail("CONTRACT_SHAPE_INVALID", "source_artifact")
            uri = _string(artifact["uri"], "source_artifact.uri")
            digest = _string(artifact["sha256"], "source_artifact.sha256")
            if uri in observed:
                _fail("DUPLICATE_BINDING", "source_artifact.uri")
            observed[uri] = digest
    if observed != EXPECTED_SOURCE_BINDINGS:
        _fail("SOURCE_BINDING_INVALID", "source_bindings")

    canonical: dict[str, str] = {}
    for artifact_value in _sequence(
        contract["canonical_bindings"], "canonical_bindings"
    ):
        artifact = _mapping(artifact_value, "canonical_binding")
        if tuple(artifact) != ("uri", "sha256"):
            _fail("CONTRACT_SHAPE_INVALID", "canonical_binding")
        uri = _string(artifact["uri"], "canonical_binding.uri")
        digest = _string(artifact["sha256"], "canonical_binding.sha256")
        if uri in canonical:
            _fail("DUPLICATE_BINDING", "canonical_binding.uri")
        canonical[uri] = digest
    if canonical != EXPECTED_CANONICAL_BINDINGS:
        _fail("CANONICAL_BINDING_INVALID", "canonical_bindings")

    for uri, digest in {**observed, **canonical}.items():
        if not uri.startswith("repo://"):
            _fail("URI_INVALID", "binding.uri")
        relative = Path(uri.removeprefix("repo://"))
        payload = _read_regular(_safe_path(root, relative))
        if _sha256(payload) != digest:
            _fail("BINDING_HASH_MISMATCH", relative.as_posix())


def _validate_screens(contract: dict[str, object]) -> None:
    screens = _sequence(contract["screen_contract"], "screen_contract")
    if len(screens) != len(EXPECTED_SCREENS):
        _fail("SCREEN_CONTRACT_INVALID", "screen_contract")
    for value, expected in zip(screens, EXPECTED_SCREENS, strict=True):
        row = _mapping(value, "screen")
        if tuple(row) != ("id", "name", "route", "roles", "components"):
            _fail("SCREEN_CONTRACT_INVALID", "screen")
        if (
            row["id"],
            row["name"],
            row["route"],
            tuple(_sequence(row["roles"], "screen.roles")),
            tuple(_sequence(row["components"], "screen.components")),
        ) != expected:
            _fail("SCREEN_CONTRACT_INVALID", str(row.get("id", "screen")))


def _validate_contract_boundaries(contract: dict[str, object]) -> None:
    projection = _mapping(contract["projection_contract"], "projection_contract")
    if projection != {
        "source_projection": "RECORDED_SYNTHETIC_READ_ONLY",
        "fact_projection": "RECORDED_SYNTHETIC_READ_ONLY",
        "conflict_projection": "RECORDED_SYNTHETIC_READ_ONLY",
        "coverage_projection": "EXACT_ST0605_REPORT_READ_ONLY",
        "matrix_projection": "CLAIM_FACT_SOURCE_CITATION_READ_ONLY",
        "lifecycle_projection": "EXACT_ST0604_CURRENT_SOURCE_READ_ONLY",
        "attestation_projection": "EXACT_KIND_SUBJECT_INPUT_CONTRACT_PROVENANCE",
        "raw_source_bytes_included": False,
        "source_url_included": False,
        "personal_data_included": False,
        "finance_inputs_included": False,
        "recommendation_ranking_inputs_included": False,
    }:
        _fail("BOUNDARY_INVALID", "projection_contract")
    access = _mapping(contract["source_access_contract"], "source_access_contract")
    if access != {
        "maximum_deterministic_actions": 2,
        "action_semantics": "READ_ONLY_FOCUS_PATH_CONTRACT",
        "dispatch": "NOT_EXECUTED",
        "target": "RECORDED_SOURCE_METADATA_AND_SNAPSHOT_HASH_ONLY",
    }:
        _fail("BOUNDARY_INVALID", "source_access_contract")
    unknown = _mapping(contract["unknown_contract"], "unknown_contract")
    if unknown != {
        "missing": "UNAVAILABLE",
        "unevaluated": "UNKNOWN",
        "conflict": "EXPLICIT_CONFLICT",
        "live_freshness": "UNKNOWN",
        "nullable_value": None,
        "unknown_as_zero_allowed": False,
        "unknown_as_pass_allowed": False,
        "known_recorded_empty_collection_may_be_zero": True,
    }:
        _fail("BOUNDARY_INVALID", "unknown_contract")
    authority = _mapping(contract["authority_boundary"], "authority_boundary")
    if set(authority) != {
        "route_registration",
        "rendering",
        "authentication",
        "authorization",
        "backend_data",
        "network",
        "user_actions",
        "mutation",
        "persistence",
        "publication",
        "activation",
        "staging",
        "release",
        "production",
        "role_metadata_is_authority",
    } or any(value is not False for value in authority.values()):
        _fail("AUTHORITY_INVALID", "authority_boundary")
    verification = _mapping(contract["verification_boundary"], "verification_boundary")
    if verification != {
        "local_owner_check": "EXECUTED",
        "local_model_tests": "EXECUTED",
        "TST-022": "NOT_EXECUTED",
        "TST-024": "NOT_EXECUTED",
        "browser": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }:
        _fail("VERIFICATION_BOUNDARY_INVALID", "verification_boundary")


def _load_fixture(root: Path) -> dict[str, object]:
    fixture = _load_json(root, FIXTURE_PATH)
    if tuple(fixture) != (
        "schema_version",
        "story_id",
        "classification",
        "source_mode",
        "recorded_at",
        "upstream",
        "presentation",
        "sanitization",
        "authority",
    ):
        _fail("FIXTURE_SHAPE_INVALID", "fixture")
    if (
        fixture["schema_version"] != 2
        or fixture["story_id"] != "ST-0606"
        or fixture["classification"]
        != "SANITIZED_RECORDED_SYNTHETIC_EVIDENCE_WORKSPACE_INPUT_V2"
        or fixture["source_mode"] != "RECORDED_SYNTHETIC_DEV_CI_ONLY"
        or fixture["recorded_at"] != "2026-08-24T00:00:00Z"
    ):
        _fail("FIXTURE_VALUE_INVALID", "fixture")
    sanitization = _mapping(fixture["sanitization"], "fixture.sanitization")
    if not sanitization or any(value is not False for value in sanitization.values()):
        _fail("FIXTURE_SANITIZATION_INVALID", "fixture.sanitization")
    authority = _mapping(fixture["authority"], "fixture.authority")
    if not authority or any(value is not False for value in authority.values()):
        _fail("FIXTURE_AUTHORITY_INVALID", "fixture.authority")
    return fixture


def _verify_lifecycle(root: Path) -> dict[str, object]:
    lifecycle = _load_json(root, ST0604_LIFECYCLE_PATH)
    document = _mapping(lifecycle.get("document"), "st0604.document")
    collection = _mapping(
        lifecycle.get("collection_boundary"), "st0604.collection_boundary"
    )
    boundary = _mapping(
        lifecycle.get("lifecycle_boundary"), "st0604.lifecycle_boundary"
    )
    if (
        document.get("story_id") != "ST-0604"
        or document.get("decision") != "NOT_READY"
        or document.get("approval") is not False
        or document.get("generation_permitted") is not False
        or collection.get("packets") != []
        or collection.get("packet_count") is not None
        or collection.get("versions") != []
        or collection.get("version_count") is not None
        or boundary.get("transition_status") != "UNAVAILABLE"
        or boundary.get("mapping_status") != "UNAVAILABLE"
        or boundary.get("approval") is not False
        or boundary.get("generation_permitted") is not False
    ):
        _fail("ST0604_SEMANTIC_DRIFT", "st0604.lifecycle")
    blockers = _sequence(boundary.get("blockers"), "st0604.blockers")
    if not blockers or any(type(item) is not str for item in blockers):
        _fail("ST0604_SEMANTIC_DRIFT", "st0604.blockers")
    return {
        "story_id": "ST-0604",
        "source_sha256": EXPECTED_SOURCE_BINDINGS[
            "repo://changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json"
        ],
        "authority": "CURRENT_LIFECYCLE_SOURCE",
        "decision": "NOT_READY",
        "availability": "UNAVAILABLE",
        "packet_count": None,
        "version_count": None,
        "transition_status": "UNAVAILABLE",
        "mapping_status": "UNAVAILABLE",
        "approval": False,
        "generation_permitted": False,
        "blockers": blockers,
    }


def _verify_evidence(
    root: Path, fixture: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    payload = _read_regular(_safe_path(root, ST0605_FIXTURE_PATH))
    try:
        snapshot = load_recorded_claim_evidence_fixture(payload)
        report = evaluate_claim_evidence(snapshot)
    except Exception:
        _fail("ST0605_EVIDENCE_INVALID", "st0605.fixture")
    if (
        report.status is not CoverageStatus.PASS
        or report.findings
        or report.publication_authorized is not False
        or report.production_eligible is not False
    ):
        _fail("ST0605_REPORT_INVALID", "st0605.report")
    try:
        report_payload = json.loads(report.canonical_bytes())
    except Exception:
        _fail("ST0605_REPORT_INVALID", "st0605.report")
    report_row = _mapping(report_payload, "st0605.report")
    upstream = _mapping(fixture["upstream"], "fixture.upstream")
    if upstream != {
        "st0604_lifecycle_sha256": EXPECTED_SOURCE_BINDINGS[
            "repo://changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json"
        ],
        "st0605_fixture_sha256": _sha256(payload),
        "st0605_evaluation_input_sha256": report_row["evaluation_input_sha256"],
        "st0605_report_sha256": report_row["report_sha256"],
        "st0605_attestation_count": len(snapshot.attestations),
    }:
        _fail("FIXTURE_UPSTREAM_BINDING_INVALID", "fixture.upstream")

    requirements = required_validation_attestation_inputs(snapshot)
    requirement_rows = {
        (kind.value, subject.value, input_digest.value)
        for kind, subject, input_digest in requirements
    }
    attestation_rows: list[dict[str, object]] = []
    for index, attestation in enumerate(snapshot.attestations, start=1):
        requirement = (
            attestation.kind.value,
            attestation.subject_sha256.value,
            attestation.input_sha256.value,
        )
        if requirement not in requirement_rows:
            _fail("ST0605_ATTESTATION_BINDING_INVALID", "attestation.requirement")
        owner, version, contract_digest = validation_attestation_owner_binding(
            attestation.kind
        )
        decision = recorded_synthetic_attestation_decision_sha256(
            attestation.kind,
            attestation.subject_sha256,
            attestation.input_sha256,
        )
        if (
            attestation.owner_story_id != owner
            or attestation.contract_version != version
            or attestation.contract_sha256 != contract_digest
            or attestation.decision_sha256 != decision
            or attestation.origin.value != "RECORDED_SYNTHETIC_ONLY"
            or attestation.valid is not True
        ):
            _fail("ST0605_ATTESTATION_BINDING_INVALID", "attestation.provenance")
        attestation_rows.append(
            {
                "attestation_id": f"ATT-{index:03d}",
                "kind": attestation.kind.value,
                "owner_story_id": attestation.owner_story_id,
                "contract_version": attestation.contract_version,
                "contract_sha256": attestation.contract_sha256.value,
                "origin": attestation.origin.value,
                "subject_sha256": attestation.subject_sha256.value,
                "input_sha256": attestation.input_sha256.value,
                "decision_sha256": attestation.decision_sha256.value,
                "validated_at": attestation.validated_at.value.isoformat().replace(
                    "+00:00", "Z"
                ),
                "valid": True,
            }
        )
    if len(attestation_rows) != len(requirement_rows):
        _fail("ST0605_ATTESTATION_SET_INVALID", "attestations")
    source = _load_json(root, ST0605_FIXTURE_PATH)
    return report_row, {"source": source, "attestations": attestation_rows}


def _instant(value: object, field: str) -> datetime:
    text = _string(value, field)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except Exception:
        _fail("INSTANT_INVALID", field)
    return parsed


def _table(
    *,
    table_id: str,
    caption: str,
    columns: tuple[tuple[str, str], ...],
    row_header_column: str,
    rows: list[dict[str, object]],
    availability: str,
    empty_state: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "table_id": table_id,
        "caption": caption,
        "columns": [
            {"id": column_id, "label": label, "scope": "col"}
            for column_id, label in columns
        ],
        "row_header_column": row_header_column,
        "row_header_scope": "row",
        "availability": availability,
        "row_count": len(rows) if availability.startswith("AVAILABLE") else None,
        "rows": rows,
        "empty_state": empty_state,
    }


def _status(code: str, text: str, icon: str) -> dict[str, object]:
    return {"code": code, "text": text, "icon": icon, "color_only": False}


def _screen(
    *,
    spec: tuple[str, str, str, tuple[str, ...], tuple[str, ...]],
    table: dict[str, object],
    status: dict[str, object],
    section_ids: tuple[str, ...],
) -> dict[str, object]:
    screen_id, name, route, roles, components = spec
    return {
        "screen_id": screen_id,
        "name": name,
        "route_pattern": route,
        "roles": list(roles),
        "role_metadata_authority": "DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION",
        "components": list(components),
        "route": {
            "registered": False,
            "render_enabled": False,
            "status": "UNREGISTERED_AUTH_TRANSPORT_UNRESOLVED",
        },
        "semantic_view": {
            "document_title": f"{name} | RAOS",
            "skip_link": {"href": f"#{screen_id.lower()}-main", "text": "本文へ移動"},
            "main_landmark": {
                "id": f"{screen_id.lower()}-main",
                "role": "main",
                "labelled_by": f"{screen_id.lower()}-h1",
            },
            "h1": {"id": f"{screen_id.lower()}-h1", "text": name, "count": 1},
            "sections": [
                {
                    "id": section_id,
                    "heading_level": 2,
                    "labelled": True,
                }
                for section_id in section_ids
            ],
            "focus_order": [
                f"{screen_id.lower()}-skip",
                f"{screen_id.lower()}-h1",
                f"{screen_id.lower()}-status",
                cast(str, table["table_id"]),
            ],
            "keyboard_contract": ["Tab", "Shift+Tab", "ArrowUp", "ArrowDown"],
            "status_cue": status,
            "rendered": False,
            "browser_verified": False,
        },
        "table": table,
    }


def _projection(
    root: Path, contract: dict[str, object], fixture: dict[str, object]
) -> dict[str, object]:
    lifecycle = _verify_lifecycle(root)
    report, verified = _verify_evidence(root, fixture)
    source = _mapping(verified["source"], "st0605.source")
    presentation = _mapping(fixture["presentation"], "fixture.presentation")
    evaluated_at = _instant(source["evaluated_at"], "st0605.evaluated_at")

    source_rows: list[dict[str, object]] = []
    snapshot_by_id: dict[str, dict[str, object]] = {}
    for snapshot_value in _sequence(source["snapshots"], "st0605.snapshots"):
        snapshot = _mapping(snapshot_value, "st0605.snapshot")
        snapshot_id = _string(snapshot["source_snapshot_id"], "snapshot.id")
        snapshot_by_id[snapshot_id] = snapshot
    for source_value in _sequence(source["sources"], "st0605.sources"):
        source_record = _mapping(source_value, "st0605.source")
        source_id = _string(source_record["source_id"], "source.id")
        snapshots = [
            snapshot
            for snapshot in snapshot_by_id.values()
            if snapshot.get("source_id") == source_id
        ]
        recorded_current = bool(snapshots) and all(
            snapshot.get("validation_status") == "VALID"
            and _instant(snapshot.get("acquired_at"), "snapshot.acquired_at")
            <= evaluated_at
            and snapshot.get("expires_at") is not None
            and evaluated_at
            < _instant(snapshot.get("expires_at"), "snapshot.expires_at")
            for snapshot in snapshots
        )
        source_rows.append(
            {
                "source_id": source_id,
                "label": presentation["source_label"],
                "tier": source_record["tier"],
                "origin": source_record["origin"],
                "active": source_record["active"],
                "snapshot_count": len(snapshots),
                "snapshots": [
                    {
                        "source_snapshot_id": snapshot["source_snapshot_id"],
                        "content_sha256": snapshot["content_sha256"],
                        "validation_status": snapshot["validation_status"],
                        "acquired_at": snapshot["acquired_at"],
                        "expires_at": snapshot["expires_at"],
                    }
                    for snapshot in snapshots
                ],
                "recorded_freshness": (
                    "CURRENT_AT_RECORDED_EVALUATION"
                    if recorded_current
                    else "EXPLICIT_CONFLICT"
                ),
                "live_freshness": "UNKNOWN",
                "live_checked_at": None,
                "live_label": presentation["live_freshness_unknown_label"],
                "raw_source_body": None,
                "source_url": None,
            }
        )

    citation_by_pair: dict[tuple[str, str], dict[str, object]] = {}
    for citation_value in _sequence(source["citations"], "st0605.citations"):
        citation = _mapping(citation_value, "st0605.citation")
        citation_by_pair[(str(citation["claim_id"]), str(citation["fact_id"]))] = (
            citation
        )
    link_by_fact: dict[str, list[dict[str, object]]] = {}
    for link_value in _sequence(source["links"], "st0605.links"):
        link = _mapping(link_value, "st0605.link")
        link_by_fact.setdefault(str(link["fact_id"]), []).append(link)

    fact_rows: list[dict[str, object]] = []
    source_access_paths: list[dict[str, object]] = []
    for index, fact_value in enumerate(
        _sequence(source["facts"], "st0605.facts"), start=1
    ):
        fact = _mapping(fact_value, "st0605.fact")
        fact_id = _string(fact["fact_id"], "fact.id")
        fact_snapshot = snapshot_by_id.get(str(fact["source_snapshot_id"]))
        if fact_snapshot is None:
            _fail("FACT_SOURCE_UNREACHABLE", "fact.source_snapshot_id")
        source_id = _string(fact_snapshot["source_id"], "snapshot.source_id")
        path_id = f"SOURCE-PATH-FACT-{index:03d}"
        links = link_by_fact.get(fact_id, [])
        fact_rows.append(
            {
                "fact_id": fact_id,
                "label": f"{presentation['fact_label_prefix']} {index}",
                "fact_sha256": fact["fact_sha256"],
                "subject_identity_sha256": fact["subject_identity_sha256"],
                "source_snapshot_id": fact["source_snapshot_id"],
                "source_id": source_id,
                "claim_ids": sorted(str(link["claim_id"]) for link in links),
                "support_types": sorted(str(link["support_type"]) for link in links),
                "source_access_path_id": path_id,
                "live_freshness": "UNKNOWN",
                "live_freshness_value": None,
            }
        )
        source_access_paths.append(
            {
                "path_id": path_id,
                "origin_type": "FACT",
                "origin_id": fact_id,
                "source_id": source_id,
                "maximum_steps": 2,
                "step_count": 2,
                "steps": [
                    {
                        "position": 1,
                        "code": "FOCUS_SOURCE_REFERENCE",
                        "target_ref": fact["source_snapshot_id"],
                    },
                    {
                        "position": 2,
                        "code": "INSPECT_RECORDED_SOURCE_METADATA",
                        "target_ref": source_id,
                    },
                ],
                "effect": "NONE",
                "dispatch": "NOT_EXECUTED",
            }
        )

    facts_by_id = {str(row["fact_id"]): row for row in fact_rows}
    claim_by_id = {
        str(_mapping(item, "st0605.claim")["claim_id"]): _mapping(item, "st0605.claim")
        for item in _sequence(source["claims"], "st0605.claims")
    }
    matrix_rows: list[dict[str, object]] = []
    for index, link_value in enumerate(
        _sequence(source["links"], "st0605.links"), start=1
    ):
        link = _mapping(link_value, "st0605.link")
        claim_id = _string(link["claim_id"], "link.claim_id")
        fact_id = _string(link["fact_id"], "link.fact_id")
        claim_record = claim_by_id.get(claim_id)
        fact_record = facts_by_id.get(fact_id)
        citation_record = citation_by_pair.get((claim_id, fact_id))
        if claim_record is None or fact_record is None or citation_record is None:
            _fail("MATRIX_REFERENCE_INVALID", "matrix")
        path_id = f"SOURCE-PATH-MATRIX-{index:03d}"
        matrix_rows.append(
            {
                "matrix_row_id": f"MATRIX-{index:03d}",
                "claim_id": claim_id,
                "claim_type": claim_record["claim_type"],
                "criticality": claim_record["criticality"],
                "fact_id": fact_id,
                "support_type": link["support_type"],
                "citation_id": citation_record["citation_id"],
                "source_id": fact_record["source_id"],
                "source_snapshot_id": fact_record["source_snapshot_id"],
                "coverage_state": "SUPPORTED_RECORDED_SYNTHETIC",
                "conflict_state": "KNOWN_RECORDED_NONE",
                "live_freshness": "UNKNOWN",
                "source_access_path_id": path_id,
            }
        )
        source_access_paths.append(
            {
                "path_id": path_id,
                "origin_type": "MATRIX_ROW",
                "origin_id": f"MATRIX-{index:03d}",
                "source_id": fact_record["source_id"],
                "maximum_steps": 2,
                "step_count": 2,
                "steps": [
                    {
                        "position": 1,
                        "code": "FOCUS_SUPPORTING_FACT",
                        "target_ref": fact_id,
                    },
                    {
                        "position": 2,
                        "code": "INSPECT_RECORDED_SOURCE_METADATA",
                        "target_ref": fact_record["source_id"],
                    },
                ],
                "effect": "NONE",
                "dispatch": "NOT_EXECUTED",
            }
        )

    conflicts = _sequence(source["conflicts"], "st0605.conflicts")
    if conflicts:
        _fail("RECORDED_FIXTURE_CONFLICT_DRIFT", "st0605.conflicts")
    conflict_rows: list[dict[str, object]] = []
    lifecycle_empty = _status(
        "UNAVAILABLE",
        str(presentation["lifecycle_unavailable_label"]),
        "question",
    )
    conflict_empty = _status(
        "KNOWN_RECORDED_EMPTY",
        str(presentation["conflict_empty_label"]),
        "check",
    )
    recorded_status = _status(
        "AVAILABLE_RECORDED_SYNTHETIC",
        str(presentation["coverage_non_authority_label"]),
        "record",
    )

    packet_table = _table(
        table_id="evd-001-packet-table",
        caption="Source Packet lifecycle一覧",
        columns=(("packet_id", "Packet"), ("status", "状態"), ("freshness", "鮮度")),
        row_header_column="packet_id",
        rows=[],
        availability="UNAVAILABLE_DEPENDENCY",
        empty_state=lifecycle_empty,
    )
    matrix_table = _table(
        table_id="evd-002-matrix-table",
        caption="Claim・Fact・Source対応表",
        columns=(
            ("claim_id", "Claim"),
            ("fact_id", "Fact"),
            ("support_type", "対応"),
            ("source_id", "Source"),
            ("live_freshness", "現在の鮮度"),
        ),
        row_header_column="claim_id",
        rows=matrix_rows,
        availability="AVAILABLE_RECORDED_SYNTHETIC",
        empty_state=None,
    )
    fact_table = _table(
        table_id="evd-003-fact-table",
        caption="記録済み合成Fact一覧",
        columns=(
            ("fact_id", "Fact"),
            ("source_id", "Source"),
            ("support_types", "根拠関係"),
            ("live_freshness", "現在の鮮度"),
        ),
        row_header_column="fact_id",
        rows=fact_rows,
        availability="AVAILABLE_RECORDED_SYNTHETIC",
        empty_state=None,
    )
    conflict_table = _table(
        table_id="evd-004-conflict-table",
        caption="記録済み合成Conflict一覧",
        columns=(("conflict_id", "Conflict"), ("status", "状態"), ("fact_ids", "Fact")),
        row_header_column="conflict_id",
        rows=conflict_rows,
        availability="AVAILABLE_RECORDED_SYNTHETIC_EMPTY",
        empty_state=conflict_empty,
    )
    screens = [
        _screen(
            spec=EXPECTED_SCREENS[0],
            table=packet_table,
            status=lifecycle_empty,
            section_ids=("lifecycle-status", "packet-list"),
        ),
        _screen(
            spec=EXPECTED_SCREENS[1],
            table=matrix_table,
            status=recorded_status,
            section_ids=(
                "packet-binding",
                "coverage",
                "claim-evidence-matrix",
                "sources",
            ),
        ),
        _screen(
            spec=EXPECTED_SCREENS[2],
            table=fact_table,
            status=recorded_status,
            section_ids=("fact-list", "source-access"),
        ),
        _screen(
            spec=EXPECTED_SCREENS[3],
            table=conflict_table,
            status=conflict_empty,
            section_ids=("conflict-status", "conflict-list"),
        ),
    ]

    return {
        "schema_version": 2,
        "story_id": "ST-0606",
        "classification": ("LOCAL_EXECUTABLE_RECORDED_SYNTHETIC_EVIDENCE_WORKSPACE_V2"),
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "canonical_status": {
            "implementation": "NOT_STARTED",
            "verification": "NOT_EXECUTED",
        },
        "source_mode": "RECORDED_SYNTHETIC_DEV_CI_ONLY",
        "contract_sha256": _sha256(_read_regular(_safe_path(root, CONTRACT_PATH))),
        "fixture_sha256": _sha256(_read_regular(_safe_path(root, FIXTURE_PATH))),
        "source_bindings": [
            {"uri": uri, "sha256": digest}
            for uri, digest in EXPECTED_SOURCE_BINDINGS.items()
        ],
        "lifecycle": lifecycle,
        "coverage": {
            "authority": "RECORDED_SYNTHETIC_COVERAGE_ONLY",
            "report": report,
            "publication_authorized": False,
            "production_eligible": False,
            "live_state": "UNKNOWN",
        },
        "attestations": verified["attestations"],
        "sources": source_rows,
        "facts": fact_rows,
        "conflicts": {
            "availability": "AVAILABLE_RECORDED_SYNTHETIC_EMPTY",
            "known_recorded_count": 0,
            "live_count": None,
            "live_state": "UNKNOWN",
            "rows": conflict_rows,
        },
        "matrix": {
            "availability": "AVAILABLE_RECORDED_SYNTHETIC",
            "rows": matrix_rows,
        },
        "source_access": {
            "maximum_deterministic_steps": 2,
            "semantics": "READ_ONLY_FOCUS_PATH_CONTRACT",
            "paths": source_access_paths,
            "dispatch": "NOT_EXECUTED",
        },
        "screens": screens,
        "unknown_policy": _mapping(contract["unknown_contract"], "unknown_contract"),
        "editorial_independence": {
            "prohibited_input_categories": [
                "AFFILIATE_COMPENSATION",
                "COMMERCIAL_PERFORMANCE",
                "RECOMMENDATION_ORDERING",
            ],
            "inputs_present": False,
        },
        "authority": _mapping(contract["authority_boundary"], "authority_boundary"),
        "verification": _mapping(
            contract["verification_boundary"], "verification_boundary"
        ),
        "formal_acceptance_achieved": False,
        "production_eligible": False,
    }


def _json_bytes(value: object) -> bytes:
    payload = (
        json.dumps(value, ensure_ascii=True, indent=2, separators=(",", ": ")) + "\n"
    ).encode("ascii")
    if len(payload) > MAX_GENERATED_BYTES:
        _fail("GENERATED_SIZE_INVALID", "projection")
    return payload


def _generated_ts_bytes(projection_bytes: bytes) -> bytes:
    digest = _sha256(projection_bytes)
    text = projection_bytes.decode("ascii").removesuffix("\n")
    literal = (
        "'"
        + text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
        + "'"
    )
    payload = (
        "// Generated by scripts/build_st0606_evidence_workspace_v2.py; do not edit.\n"
        "export const ST0606_RECORDED_PROJECTION_V2_SHA256 =\n"
        f"  '{digest}' as const;\n"
        "export const ST0606_RECORDED_PROJECTION_V2_JSON =\n"
        f"  {literal} as const;\n"
    ).encode("ascii")
    if len(payload) > MAX_GENERATED_BYTES:
        _fail("GENERATED_SIZE_INVALID", "typescript")
    return payload


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, relative))
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _manifest_bytes(
    root: Path, projection_bytes: bytes, generated_ts_bytes: bytes
) -> bytes:
    sources = [_artifact(root, path) for path in OWNED_SOURCE_PATHS]
    manifest = {
        "schema_version": 2,
        "story_id": "ST-0606",
        "classification": (
            "LOCAL_RECORDED_SYNTHETIC_EVIDENCE_WORKSPACE_RUNTIME_MANIFEST_V2"
        ),
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{OUTPUT_PATH.as_posix()}",
                "bytes": len(projection_bytes),
                "sha256": _sha256(projection_bytes),
            },
            {
                "uri": f"repo://{GENERATED_TS_PATH.as_posix()}",
                "bytes": len(generated_ts_bytes),
                "sha256": _sha256(generated_ts_bytes),
            },
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": (
                ".venv/bin/python scripts/build_st0606_evidence_workspace_v2.py"
            ),
            "check_command": (
                ".venv/bin/python scripts/build_st0606_evidence_workspace_v2.py --check"
            ),
            "toolchain": {
                "python_implementation": "CPython",
                "python_version": ".".join(
                    str(part) for part in EXPECTED_PYTHON_VERSION
                ),
                "pyyaml_version": EXPECTED_PYYAML_VERSION,
                "node_version": "24.18.1",
                "npm_version": "11.16.0",
            },
        },
        "route_boundary": {
            "status": "UNREGISTERED_AUTH_TRANSPORT_UNRESOLVED",
            "registered_route_count": 0,
            "auth_transport_decision": "OD-010_UNRESOLVED",
        },
        "authority": {
            "authentication": False,
            "authorization": False,
            "network": False,
            "backend": False,
            "actions": False,
            "persistence": False,
            "publication": False,
            "staging": False,
            "release": False,
            "production": False,
        },
        "verification": {
            "local_owner_check": "EXECUTED",
            "local_model_tests": "EXECUTED",
            "TST-022": "NOT_EXECUTED",
            "TST-024": "NOT_EXECUTED",
            "browser": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def _stage_payload(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            staged = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(staged, 0o644)
        return staged
    except BaseException:
        _fail("GENERATION_STAGE_FAILED", path.as_posix())


def _replace_generated(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for destination, payload in artifacts:
            if destination.is_symlink() or (
                destination.exists() and not destination.is_file()
            ):
                _fail("GENERATION_DESTINATION_INVALID", destination.as_posix())
            staged.append((destination, _stage_payload(destination, payload)))
        for destination, temporary in staged:
            os.replace(temporary, destination)
    except BaseException:
        for _destination, temporary in staged:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _validate_toolchain() -> None:
    if sys.implementation.name != "cpython" or sys.version_info[:3] != (
        *EXPECTED_PYTHON_VERSION,
    ):
        _fail("TOOLCHAIN_INVALID", "python")
    try:
        observed = package_version("PyYAML")
    except PackageNotFoundError:
        _fail("TOOLCHAIN_INVALID", "pyyaml")
    if observed != EXPECTED_PYYAML_VERSION:
        _fail("TOOLCHAIN_INVALID", "pyyaml")


def expected_artifacts(root: Path = REPO_ROOT) -> tuple[tuple[Path, bytes], ...]:
    contract = _load_contract(root)
    fixture = _load_fixture(root)
    projection_bytes = _json_bytes(_projection(root, contract, fixture))
    generated_ts_bytes = _generated_ts_bytes(projection_bytes)
    manifest_bytes = _manifest_bytes(root, projection_bytes, generated_ts_bytes)
    return (
        (OUTPUT_PATH, projection_bytes),
        (GENERATED_TS_PATH, generated_ts_bytes),
        (MANIFEST_PATH, manifest_bytes),
    )


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    _validate_toolchain()
    expected = expected_artifacts(root)
    if check:
        for relative, payload in expected:
            path = _safe_path(root, relative)
            if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
                _fail("GENERATED_ARTIFACT_DRIFT", relative.as_posix())
        return
    _replace_generated(
        tuple((_safe_path(root, relative), payload) for relative, payload in expected)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        build(check=arguments.check)
    except EvidenceWorkspaceBuildError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
