#!/usr/bin/env python3
"""Build the non-attesting ST-1602 SLO and alert reference plan."""

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

from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1602/contracts/slo-alert-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1602/generated/slo-alert-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1602/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1602_slo_alert_reference_plan.py")
README_PATH: Final = Path("changes/st-1602/README.md")
TEST_PATHS: Final = (
    Path("tests/st1602/conftest.py"),
    Path("tests/st1602/test_contract.py"),
    Path("tests/st1602/test_generation.py"),
    Path("tests/st1602/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1602_slo_alert_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9afb71a8715ea76a65e4a681a3d41940e38d5d3dc4a0b838f7bd7eea6180065b"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

SLO_PATH: Final = Path("docs/canonical/06_ops/RAOS_12_slo_catalog_v1.0.yaml")
ALERT_PATH: Final = Path("docs/canonical/06_ops/RAOS_12_alert_catalog_v1.0.yaml")
RUNBOOK_PATH: Final = Path("docs/canonical/06_ops/RAOS_12_runbook_index_v1.0.yaml")
ST1601_PATH: Final = Path("changes/st-1601/README.md")

EXPECTED_SOURCES: Final = (
    (
        "integration",
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "open_decisions",
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "test_catalog",
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "slo_catalog",
        SLO_PATH.as_posix(),
        "320a880073e3c9d87c361fa8620e1202898ffa719e2b8e94872d185415abcdf2",
    ),
    (
        "alert_catalog",
        ALERT_PATH.as_posix(),
        "f180e950f659d27e9270b6c1f9c1dcb6d0fa6194acdc1fdd7026ac7cea560be0",
    ),
    (
        "runbook_catalog",
        RUNBOOK_PATH.as_posix(),
        "2aed21892e78ead32fc647b928f50014971d280142d0f49f4e0d1e7d68897100",
    ),
    (
        "story",
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
)
ST1601_SHA256: Final = (
    "9eade86a2f3f7cae147d0ca26db1be0828be09250b068ac8f78832cf36ca65ef"
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "dependency",
    "open_decision",
    "projection_rules",
    "routing_defaults",
    "telemetry_defaults",
    "verification_defaults",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "dependency",
    "open_decision",
    "catalog_projection",
    "routing",
    "execution_boundary",
    "verification_boundary",
)
SLO_FIELDS: Final = (
    "id",
    "name",
    "scope",
    "sli",
    "target",
    "window",
    "notes",
    "status",
    "implementation_status",
    "measurement_status",
)
ALERT_FIELDS: Final = (
    "id",
    "severity",
    "name",
    "condition",
    "detection",
    "initial_action",
    "implementation_status",
    "test_status",
)
RUNBOOK_FIELDS: Final = (
    "id",
    "title",
    "severity",
    "minimum_steps",
    "document_status",
    "implementation_status",
    "drill_status",
)


class SloAlertReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise SloAlertReferenceError(f"ST-1602 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _same_exact(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        left_map = cast(dict[str, object], left)
        right_map = cast(dict[str, object], right)
        return tuple(left_map) == tuple(right_map) and all(
            _same_exact(left_map[key], right_map[key]) for key in right_map
        )
    if type(right) is list:
        left_list = cast(list[object], left)
        right_list = cast(list[object], right)
        return len(left_list) == len(right_list) and all(
            _same_exact(a, b) for a, b in zip(left_list, right_list, strict=True)
        )
    return left == right


def _exact(value: object, expected: object, field: str) -> None:
    if not _same_exact(value, expected):
        _fail("VALUE_MISMATCH", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _expected_source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _validate_source_hashes(root: Path) -> None:
    for _role, path, digest in EXPECTED_SOURCES:
        if _sha256(_read(root, Path(path), "authority.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "authority.source")
    if _sha256(_read(root, ST1601_PATH, "dependency")) != ST1601_SHA256:
        _fail("DEPENDENCY_HASH_DRIFT", "dependency")
    if _sha256(_read(root, HELPER_PATH, "implementation.helper")) != HELPER_SHA256:
        _fail("IMPLEMENTATION_HELPER_DRIFT", "implementation.helper")


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "story",
    )
    story = _find(stories.get("stories"), "ST-1602", "story")
    if (
        story.get("depends_on") != ["ST-1601"]
        or story.get("acceptance_criteria") != ["alert routes to owner/runbook"]
        or story.get("test_suites") != ["TST-027", "TST-028"]
        or story.get("open_decisions") != ["OD-011"]
        or story.get("implementation_status") != "NOT_STARTED"
        or story.get("verification_status") != "NOT_EXECUTED"
    ):
        _fail("CANONICAL_STORY_DRIFT", "story")
    decisions = _load_yaml(
        root,
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "open_decision",
    )
    decision = _find(decisions.get("items"), "OD-011", "open_decision")
    if (
        decision.get("status") != "HUMAN_DECISION_REQUIRED"
        or decision.get("default_behavior") != "Local logのみ。Production不可"
        or decision.get("blocking") is not True
    ):
        _fail("OPEN_DECISION_DRIFT", "open_decision")
    suites = _load_yaml(
        root,
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "test_catalog",
    )
    for suite_id in ("TST-027", "TST-028"):
        suite = _find(suites.get("suites"), suite_id, "test_catalog")
        if (
            suite.get("implementation_status") != "NOT_STARTED"
            or suite.get("execution_status") != "NOT_EXECUTED"
            or suite.get("release_blocking") is not True
        ):
            _fail("TEST_SUITE_DRIFT", "test_catalog")
    dependency_text = _read(root, ST1601_PATH, "dependency.semantic").decode(
        "utf-8", errors="strict"
    )
    required = (
        "one inward sink port",
        "does not install or configure OpenTelemetry",
        "SLOs owned by ST-1602",
    )
    if any(fragment not in dependency_text for fragment in required):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "dependency")


def _project_catalog(
    root: Path,
    path: Path,
    collection: str,
    fields: tuple[str, ...],
    prefix: str,
    count: int,
) -> list[dict[str, object]]:
    catalog = _load_yaml(root, path, collection)
    if tuple(catalog.keys()) != ("document", collection):
        _fail("CATALOG_SCHEMA_DRIFT", collection)
    catalog_document = _mapping(catalog["document"], f"{collection}.document")
    expected_document_ids = {
        "slos": "RAOS-OPS-SLO-001",
        "alerts": "RAOS-OPS-ALERTS-001",
        "runbooks": "RAOS-OPS-RUNBOOKS-001",
    }
    if (
        catalog_document.get("id") != expected_document_ids[collection]
        or catalog_document.get("version") != "1.0"
    ):
        _fail("CATALOG_DOCUMENT_DRIFT", collection)
    rows = _list(catalog[collection], collection)
    if len(rows) != count:
        _fail("CATALOG_COUNT_DRIFT", collection)
    projected: list[dict[str, object]] = []
    for index, raw in enumerate(rows, start=1):
        row = _mapping(raw, collection)
        if tuple(row.keys()) != fields or row.get("id") != f"{prefix}-{index:03d}":
            _fail("CATALOG_ROW_DRIFT", collection)
        if collection == "slos" and (
            row.get("status") != "PROVISIONAL_TARGET"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("measurement_status") != "NOT_EXECUTED"
            or type(row.get("target")) is not str
            or not row.get("target")
            or type(row.get("window")) is not str
            or not row.get("window")
        ):
            _fail("CATALOG_SEMANTIC_DRIFT", collection)
        if collection == "alerts" and (
            row.get("severity") not in {"SEV1", "SEV2", "SEV3", "SEV4"}
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("test_status") != "NOT_EXECUTED"
            or any(
                type(row.get(name)) is not str or not row.get(name)
                for name in ("condition", "detection", "initial_action")
            )
        ):
            _fail("CATALOG_SEMANTIC_DRIFT", collection)
        if collection == "runbooks" and (
            row.get("document_status") != "DESIGNED_INDEX_ONLY"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("drill_status") != "NOT_EXECUTED"
            or type(row.get("minimum_steps")) is not list
            or not row.get("minimum_steps")
            or any(
                type(step) is not str or not step
                for step in _list(row.get("minimum_steps"), "runbooks.steps")
            )
        ):
            _fail("CATALOG_SEMANTIC_DRIFT", collection)
        projected.append(dict(row))
    return projected


EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST1602-SLO-ALERT-REFERENCE-PLAN-001",
    "version": "1.0.0",
    "story_id": "ST-1602",
    "classification": "SOURCE_DERIVED_NON_ATTESTING_SLO_ALERT_REFERENCE_PLAN",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
}
EXPECTED_DEPENDENCY: Final = {
    "story_id": "ST-1601",
    "uri": "repo://changes/st-1601/README.md",
    "sha256": ST1601_SHA256,
    "interface_status": "AVAILABLE_NOT_CONNECTED",
    "connection_status": "NOT_EXECUTED",
    "semantics": "UNCHANGED",
}
EXPECTED_OPEN_DECISION: Final = {
    "id": "OD-011",
    "status": "HUMAN_DECISION_REQUIRED",
    "safe_default": "LOCAL_LOG_ONLY",
    "notifications_enabled": False,
    "channel": None,
    "escalation_contact": None,
}
EXPECTED_RULES: Final = {
    "preserve_catalog_order": True,
    "exact_slo_count": 14,
    "exact_alert_count": 20,
    "exact_runbook_count": 20,
    "infer_links_from_identifiers": False,
    "initial_actions_are_inert_text": True,
    "minimum_steps_are_inert_text": True,
    "empty_arrays_mean_no_configuration_or_evidence": True,
}
EXPECTED_ROUTING: Final = {
    "mode": "LOCAL_LOG_ONLY",
    "route_status": "NOT_CONFIGURED",
    "notifications_enabled": False,
    "channel": None,
    "contact": None,
    "owner": None,
    "runbook_route": None,
    "slo_links": [],
    "runbook_links": [],
    "delivery_records": [],
    "external_actions": [],
}
EXPECTED_TELEMETRY: Final = {
    "interface_available": True,
    "connected": False,
    "runtime_status": "NOT_EXECUTED",
    "metric": None,
    "log": None,
    "formula": None,
    "trigger": None,
    "window": None,
    "error_budget": None,
    "backend": None,
}
EXPECTED_VERIFICATION: Final = {
    "implemented_count": 0,
    "measured_count": 0,
    "tested_count": 0,
    "drilled_count": 0,
    "owner_route_count": 0,
    "runbook_route_count": 0,
    "formal_tst_027": "NOT_EXECUTED",
    "formal_tst_028": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract.keys()) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    authority = _mapping(contract["authority"], "authority")
    if tuple(authority.keys()) != ("precedence", "sources"):
        _fail("CONTRACT_SCHEMA_DRIFT", "authority")
    _exact(
        authority["precedence"],
        "CANONICAL_INTEGRATION_THEN_STORY_THEN_CATALOGS",
        "authority.precedence",
    )
    _exact(authority["sources"], _expected_source_rows(), "authority.sources")
    _exact(contract["dependency"], EXPECTED_DEPENDENCY, "dependency")
    _exact(contract["open_decision"], EXPECTED_OPEN_DECISION, "open_decision")
    _exact(contract["projection_rules"], EXPECTED_RULES, "projection_rules")
    _exact(contract["routing_defaults"], EXPECTED_ROUTING, "routing")
    _exact(contract["telemetry_defaults"], EXPECTED_TELEMETRY, "telemetry")
    _exact(contract["verification_defaults"], EXPECTED_VERIFICATION, "verification")
    _validate_source_hashes(root)
    _validate_authority_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, Any]:
    slos = _project_catalog(root, SLO_PATH, "slos", SLO_FIELDS, "SLO", 14)
    alerts = _project_catalog(root, ALERT_PATH, "alerts", ALERT_FIELDS, "ALT", 20)
    runbooks = _project_catalog(
        root, RUNBOOK_PATH, "runbooks", RUNBOOK_FIELDS, "RB", 20
    )
    plan: dict[str, Any] = {
        "document": dict(_mapping(contract["document"], "document")),
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "dependency": contract["dependency"],
        "open_decision": contract["open_decision"],
        "catalog_projection": {
            "coverage": {
                "slos": {"projected": 14, "canonical": 14},
                "alerts": {"projected": 20, "canonical": 20},
                "runbooks": {"projected": 20, "canonical": 20},
            },
            "slos": slos,
            "alerts": alerts,
            "runbooks": runbooks,
            "inferred_links": [],
            "telemetry_binding": contract["telemetry_defaults"],
        },
        "routing": {
            **dict(_mapping(contract["routing_defaults"], "routing")),
            "empty_interpretation": "NO_CONFIGURATION_OR_EVIDENCE_NOT_ZERO_INCIDENTS",
        },
        "execution_boundary": {
            "executable": False,
            "interface_only": True,
            "runtime": "NOT_EXECUTED",
            "telemetry_connection": "NOT_EXECUTED",
            "backend": "NOT_EXECUTED",
            "notifications": "NOT_EXECUTED",
            "initial_actions": "INERT_TEXT_NOT_EXECUTED",
            "runbook_steps": "INERT_TEXT_NOT_EXECUTED",
            "external_actions": [],
            "action_counts": {
                "execute": 0,
                "create": 0,
                "update": 0,
                "delete": 0,
                "notify": 0,
                "deliver": 0,
                "external": 0,
            },
        },
        "verification_boundary": {
            "projection_coverage": "14/14 SLO; 20/20 alert; 20/20 runbook",
            **dict(_mapping(contract["verification_defaults"], "verification")),
            "approval": None,
            "decision": "NOT_READY",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    if tuple(plan.keys()) != PLAN_KEYS:
        _fail("PLAN_SCHEMA_DRIFT", "plan")
    return plan


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST1602-SLO-ALERT-REFERENCE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1602",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": _expected_source_rows(),
            "dependency_input": {
                "uri": f"repo://{ST1601_PATH.as_posix()}",
                "sha256": ST1601_SHA256,
            },
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "boundary": {
            "classification": EXPECTED_DOCUMENT["classification"],
            "executable": False,
            "formal_tst_027": "NOT_EXECUTED",
            "formal_tst_028": "NOT_EXECUTED",
            "notifications": "NOT_EXECUTED",
            "backend": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_plan(contract, root))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
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
    except (SloAlertReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1602 SLO/alert reference plan checked"
        if args.check
        else "ST-1602 SLO/alert reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
