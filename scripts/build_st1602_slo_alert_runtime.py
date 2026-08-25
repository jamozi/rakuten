#!/usr/bin/env python3
"""Build the additive ST-1602 typed local SLO/alert runtime artifacts."""

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
from scripts import build_st1602_slo_alert_reference_plan as v1  # noqa: E402


CONTRACT_PATH: Final = Path("changes/st-1602/contracts/slo-alert-runtime.v2.yaml")
CATALOG_PATH: Final = Path(
    "changes/st-1602/generated/slo-alert-runtime-catalog.v2.json"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1602/generated/slo-alert-runtime-recorded-fixture.v2.json"
)
EVIDENCE_PATH: Final = Path(
    "changes/st-1602/evidence/slo-alert-runtime-local-completion.v2.yaml"
)
MANIFEST_PATH: Final = Path("changes/st-1602/manifest.v2.yaml")
README_PATH: Final = Path("changes/st-1602/README-v2.md")
GENERATOR_PATH: Final = Path("scripts/build_st1602_slo_alert_runtime.py")
HELPER_PATH: Final = v1.HELPER_PATH
ALERT_PATH: Final = v1.ALERT_PATH
DOMAIN_PATH: Final = Path("python/raos/domain/ops/slo_alert_runtime_v2.py")
PORT_PATH: Final = Path("python/raos/ports/slo_alert_runtime_v2.py")
APPLICATION_PATH: Final = Path("python/raos/application/ops/slo_alert_runtime_v2.py")
ADAPTER_PATH: Final = Path("python/raos/adapters/recorded_slo_alert_runtime_v2.py")
TEST_PATHS: Final = (
    Path("tests/st1602/test_local_runtime_v2.py"),
    Path("tests/st1602/test_local_journal_v2.py"),
    Path("tests/st1602/test_local_hostile_v2.py"),
    Path("tests/st1602/test_local_generation_v2.py"),
    Path("tests/st1602/test_local_static_v2.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    README_PATH,
    DOMAIN_PATH,
    PORT_PATH,
    APPLICATION_PATH,
    ADAPTER_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (
    CATALOG_PATH,
    FIXTURE_PATH,
    EVIDENCE_PATH,
    MANIFEST_PATH,
)
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1602_slo_alert_runtime.py"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
EXPECTED_CONTRACT_SHA256: Final = (
    "ff1f3e47865e3d2b273b1b202a3830feb4c557a6b44dc7965fe31d534f6c621a"
)

AUTHORITY_SOURCES: Final = (
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
        "story",
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "operations_design",
        "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md",
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8",
    ),
    (
        "slo_catalog",
        v1.SLO_PATH.as_posix(),
        "320a880073e3c9d87c361fa8620e1202898ffa719e2b8e94872d185415abcdf2",
    ),
    (
        "alert_catalog",
        v1.ALERT_PATH.as_posix(),
        "f180e950f659d27e9270b6c1f9c1dcb6d0fa6194acdc1fdd7026ac7cea560be0",
    ),
    (
        "runbook_catalog",
        v1.RUNBOOK_PATH.as_posix(),
        "2aed21892e78ead32fc647b928f50014971d280142d0f49f4e0d1e7d68897100",
    ),
    (
        "security_design",
        "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md",
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    ),
    (
        "security_controls",
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
)
DEPENDENCY_SOURCES: Final = (
    (
        "changes/st-1601/README.md",
        "9eade86a2f3f7cae147d0ca26db1be0828be09250b068ac8f78832cf36ca65ef",
    ),
    (
        "python/raos/domain/ops/telemetry.py",
        "6639598c0d7019297a9843b72a06cac35a2eb4a6fd76cfc24d64cbd8dbd64e93",
    ),
    (
        "python/raos/ports/telemetry.py",
        "7892fc09f5913b96be84b35e1da118cd0a031669cca133bdcb58af8cc8fb2db9",
    ),
    (
        "python/raos/application/ops/telemetry.py",
        "ae9f2c2bede2d4b4f251f6b28f1a474096870de30b1818fe81a5153d308cf016",
    ),
    (
        "python/raos/adapters/recorded_telemetry.py",
        "dc958ba32e94ab2aa601bac471958cc9f5a74a0dedfda1d0f6e8a17a32ca03ee",
    ),
)
V1_SOURCES: Final = (
    (
        "changes/st-1602/README.md",
        "9ed7dfa14f736cf30aa166c8c79d3f42386abfab90ec31b2792454e89ad976bc",
    ),
    (
        v1.CONTRACT_PATH.as_posix(),
        "31c8d3c57501e351bd9bcde3c796abe70eb80277b4cb7a1c738cf93817ba65b1",
    ),
    (
        v1.REFERENCE_PLAN_PATH.as_posix(),
        "b4a8723c3fa4b70d30bf8ac8b145daaa4d7e41c993d53de3364d1c0a6a8ad4b3",
    ),
    (
        v1.MANIFEST_PATH.as_posix(),
        "89b37ab9fc483573aa9743a7e36edc9963f4865126a26e1b0c1ae938b0a79809",
    ),
    (
        v1.GENERATOR_PATH.as_posix(),
        "6b7cc5d945710173acff0d54216046f56af3ac6675a1308c7b12b1e7364c380f",
    ),
)
IMPLEMENTATION_HELPER: Final = (
    HELPER_PATH.as_posix(),
    "478c70fcdec48ceca5c9d072c84e4ad3dc55f63e8ccbee0f8e09d4d78eb6fdf5",
)

ROUTE_MAP: Final = {
    "ALT-001": "RB-001",
    "ALT-002": "RB-002",
    "ALT-003": "RB-003",
    "ALT-004": "RB-004",
    "ALT-005": "RB-005",
    "ALT-006": "RB-006",
    "ALT-007": "RB-006",
    "ALT-008": "RB-009",
    "ALT-009": "RB-011",
    "ALT-010": "RB-013",
    "ALT-011": "RB-017",
    "ALT-012": "RB-016",
    "ALT-013": "RB-002",
    "ALT-014": "RB-010",
    "ALT-015": "RB-012",
    "ALT-016": "RB-014",
    "ALT-017": "RB-014",
    "ALT-018": "RB-007",
    "ALT-019": "RB-018",
    "ALT-020": "RB-017",
}

SLO_EVALUATION: Final = {
    "SLO-001": ("RATIO_MINIMUM", ("numerator", "denominator"), (995_000, 1_000_000)),
    "SLO-002": ("RATIO_MINIMUM", ("numerator", "denominator"), (990_000, 1_000_000)),
    "SLO-003": ("UPPER_BOUND", ("p95_milliseconds",), (500,)),
    "SLO-004": ("UPPER_BOUND", ("p95_milliseconds",), (1_000,)),
    "SLO-005": ("RATIO_MINIMUM", ("numerator", "denominator"), (990_000, 1_000_000)),
    "SLO-006": ("RATIO_MINIMUM", ("numerator", "denominator"), (999_000, 1_000_000)),
    "SLO-007": ("RATIO_MINIMUM", ("numerator", "denominator"), (990_000, 1_000_000)),
    "SLO-008": ("UPPER_BOUND", ("p95_seconds",), (600,)),
    "SLO-009": ("RATIO_MINIMUM", ("numerator", "denominator"), (990_000, 1_000_000)),
    "SLO-010": ("UPPER_BOUND", ("age_seconds",), (259_200,)),
    "SLO-011": ("RATIO_MINIMUM", ("numerator", "denominator"), (1_000_000, 1_000_000)),
    "SLO-012": (
        "COMPOSITE_UPPER_BOUND",
        ("lcp_milliseconds", "inp_milliseconds", "cls_ppm"),
        (2_500, 200, 100_000),
    ),
    "SLO-013": ("UPPER_BOUND", ("data_loss_seconds",), (900,)),
    "SLO-014": ("UPPER_BOUND", ("recovery_seconds",), (14_400,)),
}

TARGET_TEXT: Final = {
    "SLO-001": "99.5%",
    "SLO-002": "99.0%",
    "SLO-003": "<=500 ms",
    "SLO-004": "<=1000 ms",
    "SLO-005": "99% within 5 min",
    "SLO-006": "99.9%",
    "SLO-007": ">=99% excluding validated business rejection",
    "SLO-008": "<10 min P95",
    "SLO-009": ">=99%",
    "SLO-010": "<=72 h",
    "SLO-011": "100%",
    "SLO-012": "LCP<=2.5s, INP<=200ms, CLS<=0.1",
    "SLO-013": "<=15 min",
    "SLO-014": "<=4 h",
}

HOLD_BY_DETECTION: Final = {
    "immediate": ("IMMEDIATE", (("DEFAULT", 0, False),)),
    "5 min": ("DURATION", (("DEFAULT", 300, False),)),
    "10 min": ("DURATION", (("DEFAULT", 600, False),)),
    "30 min": ("DURATION", (("DEFAULT", 1_800, False),)),
    "per batch": ("CYCLE", (("PER_BATCH", None, True),)),
    "daily": ("CYCLE", (("DAILY", None, True),)),
    "15 min": ("DURATION", (("DEFAULT", 900, False),)),
    "hourly": ("CYCLE", (("HOURLY", None, True),)),
    "5/30 min": (
        "DUAL_DURATION",
        (("FAST", 300, False), ("SLOW", 1_800, False)),
    ),
    "daily/release": (
        "DUAL_CYCLE",
        (("DAILY", None, True), ("RELEASE", None, True)),
    ),
    "weekly": ("CYCLE", (("WEEKLY", None, True),)),
    "monthly": ("CYCLE", (("MONTHLY", None, True),)),
}


class SloAlertRuntimeBuildError(RuntimeError):
    """Sanitized owner-generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise SloAlertRuntimeBuildError(
        f"ST-1602 V2 build failed: {code} field={field}"
    ) from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical: Path = base._repository_regular_file(  # pyright: ignore[reportPrivateUsage]
        root, relative, field
    )
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return cast(list[Any], value)  # type: ignore[redundant-cast]


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(  # pyright: ignore[reportPrivateUsage]
        root, relative, field
    )
    return _mapping(base.load_yaml(root / relative), field)


def _source_rows(rows: Sequence[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in rows
    ]


def _uri_hash_rows(rows: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"uri": f"repo://{path}", "sha256": digest} for path, digest in rows]


def _exact(value: object, expected: object, field: str) -> None:
    if type(value) is not type(expected) or value != expected:
        _fail("VALUE_MISMATCH", field)


def _validate_hashes(root: Path) -> None:
    for _role, path, digest in AUTHORITY_SOURCES:
        if _sha256(_read(root, Path(path), "authority.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "authority.source")
    for path, digest in (*DEPENDENCY_SOURCES, *V1_SOURCES):
        if _sha256(_read(root, Path(path), "bound.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "bound.source")
    helper_path, helper_digest = IMPLEMENTATION_HELPER
    if (
        _sha256(_read(root, Path(helper_path), "implementation.helper"))
        != helper_digest
    ):
        _fail("SOURCE_HASH_DRIFT", "implementation.helper")
    if _sha256(_read(root, CONTRACT_PATH, "contract")) != EXPECTED_CONTRACT_SHA256:
        _fail("CONTRACT_HASH_DRIFT", "contract")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != (
        "document",
        "authority",
        "dependency",
        "v1_compatibility",
        "implementation_helper",
        "compiler",
        "alert_routing",
        "runtime_boundary",
        "journal",
        "verification_boundary",
    ):
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(
        contract["document"],
        {
            "id": "RAOS-ST1602-SLO-ALERT-RUNTIME-002",
            "version": "2.0.0",
            "story_id": "ST-1602",
            "classification": "LOCAL_SYNTHETIC_NON_ATTESTING_SLO_ALERT_RUNTIME",
            "status": "LOCAL_CODE_COMPLETE_CANDIDATE",
            "executable_external_actions": False,
            "production_eligible": False,
            "approval": None,
        },
        "document",
    )
    authority = _mapping(contract["authority"], "authority")
    _exact(tuple(authority), ("precedence", "sources"), "authority")
    _exact(
        authority["precedence"],
        "CANONICAL_INTEGRATION_THEN_STORY_THEN_CATALOGS",
        "authority.precedence",
    )
    _exact(authority["sources"], _source_rows(AUTHORITY_SOURCES), "authority.sources")
    dependency = _mapping(contract["dependency"], "dependency")
    _exact(
        dependency,
        {
            "story_id": "ST-1601",
            "sources": _uri_hash_rows(DEPENDENCY_SOURCES),
            "interface_status": "AVAILABLE_RECORDED_INPUT_ONLY",
            "live_connection": "NOT_EXECUTED",
        },
        "dependency",
    )
    _exact(
        contract["v1_compatibility"],
        {"semantics": "UNCHANGED", "artifacts": _uri_hash_rows(V1_SOURCES)},
        "v1_compatibility",
    )
    _exact(
        contract["implementation_helper"],
        {
            "uri": f"repo://{IMPLEMENTATION_HELPER[0]}",
            "sha256": IMPLEMENTATION_HELPER[1],
            "purpose": "OWNER_SAFE_LOCAL_FILE_IO_ONLY",
            "semantics": "NO_RUNTIME_AUTHORITY",
        },
        "implementation_helper",
    )
    _exact(
        contract["compiler"],
        {
            "exact_slo_count": 14,
            "exact_alert_count": 20,
            "exact_runbook_count": 20,
            "preserve_catalog_order": True,
            "targets_are_provisional": True,
            "actual_measurement_claim": False,
            "missing_is_unavailable": True,
            "invalid_is_unavailable": True,
            "stale_is_unavailable": True,
            "zero_denominator_is_unavailable": True,
        },
        "compiler",
    )
    routing = _mapping(contract["alert_routing"], "alert_routing")
    expected_mappings = [
        {"alert_id": alert_id, "runbook_id": runbook_id}
        for alert_id, runbook_id in ROUTE_MAP.items()
    ]
    _exact(
        routing,
        {
            "owner": "Operations Owner",
            "owner_source": "OD-011",
            "mappings": expected_mappings,
            "notification_mode": "LOCAL_LOG_ONLY_DISABLED",
            "notifications_enabled": False,
            "channel": None,
            "contact": None,
            "delivery_claim": False,
        },
        "alert_routing",
    )
    _exact(
        contract["runtime_boundary"],
        {
            "source": "SYNTHETIC_RECORDED_FIXTURE_ONLY",
            "auto_evaluation_loop": False,
            "clock_source": "CALLER_SUPPLIED",
            "network": "FORBIDDEN",
            "credentials": "ABSENT",
            "smtp": "ABSENT",
            "webhook": "ABSENT",
            "provider": "ABSENT",
            "external_actions": 0,
            "production": "NOT_AUTHORIZED",
        },
        "runtime_boundary",
    )
    _exact(
        contract["journal"],
        {
            "mode": "OWNER_PRIVATE_SQLITE_APPEND_ONLY",
            "schema_version": 2,
            "hash_algorithm": "SHA-256",
            "hash_chain": True,
            "compare_and_swap": True,
            "idempotency": True,
            "restart_recovery": True,
            "commit_ambiguity_recovery": True,
            "cross_restart_rollback_detection": "NOT_CLAIMED_NO_EXTERNAL_ANCHOR",
            "exact_schema": True,
            "owner_directory_mode": "0700",
            "database_file_mode": "0600",
        },
        "journal",
    )
    _exact(
        contract["verification_boundary"],
        {
            "formal_tst_027": "NOT_EXECUTED",
            "formal_tst_028": "NOT_EXECUTED",
            "hosted_ci": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "notification_delivery": "NOT_EXECUTED",
            "actual_slo_attainment": "NOT_EXECUTED",
            "effective_canonical_status": "UNCHANGED",
        },
        "verification_boundary",
    )
    _validate_hashes(root)
    _validate_authority_semantics(root)
    return contract


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for item in _list(items, field):
        raw: object = item
        if type(raw) is not dict:
            continue
        candidate = _mapping(cast(object, raw), field)
        if candidate.get("id") == identity:
            matches.append(candidate)
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _validate_authority_semantics(root: Path) -> None:
    decisions = _load_yaml(
        root,
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "decisions",
    )
    decision = _find(decisions.get("items"), "OD-011", "decisions")
    if decision != {
        "id": "OD-011",
        "topic": "notification_channels",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Incident operations",
        "owner": "Operations Owner",
        "decision_needed": "Critical/High通知先とEscalation連絡先を設定",
        "default_behavior": "Local logのみ。Production不可",
        "blocking": True,
    }:
        _fail("OPEN_DECISION_DRIFT", "decisions")
    stories = _load_yaml(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "stories",
    )
    story = _find(stories.get("stories"), "ST-1602", "stories")
    if (
        story.get("depends_on") != ["ST-1601"]
        or story.get("acceptance_criteria") != ["alert routes to owner/runbook"]
        or story.get("test_suites") != ["TST-027", "TST-028"]
        or story.get("open_decisions") != ["OD-011"]
    ):
        _fail("STORY_DRIFT", "stories")
    suites = _load_yaml(
        root,
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "suites",
    )
    for suite_id in ("TST-027", "TST-028"):
        suite = _find(suites.get("suites"), suite_id, "suites")
        if (
            suite.get("implementation_status") != "NOT_STARTED"
            or suite.get("execution_status") != "NOT_EXECUTED"
            or suite.get("release_blocking") is not True
        ):
            _fail("SUITE_DRIFT", "suites")


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def _catalog_rows(
    root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    slos = v1._project_catalog(  # pyright: ignore[reportPrivateUsage]
        root, v1.SLO_PATH, "slos", v1.SLO_FIELDS, "SLO", 14
    )
    alerts = v1._project_catalog(  # pyright: ignore[reportPrivateUsage]
        root, v1.ALERT_PATH, "alerts", v1.ALERT_FIELDS, "ALT", 20
    )
    runbooks = v1._project_catalog(  # pyright: ignore[reportPrivateUsage]
        root, v1.RUNBOOK_PATH, "runbooks", v1.RUNBOOK_FIELDS, "RB", 20
    )
    return slos, alerts, runbooks


def runtime_catalog(root: Path = REPO_ROOT) -> dict[str, object]:
    load_contract(root)
    slos, alerts, runbooks = _catalog_rows(root)
    compiled_slos: list[dict[str, object]] = []
    for row in slos:
        slo_id = cast(str, row["id"])
        if row["target"] != TARGET_TEXT[slo_id]:
            _fail("SLO_TARGET_DRIFT", "slo.target")
        kind, components, thresholds = SLO_EVALUATION[slo_id]
        compiled_slos.append(
            {
                **row,
                "evaluation": {
                    "kind": kind,
                    "components": list(components),
                    "thresholds": list(thresholds),
                },
            }
        )
    compiled_alerts: list[dict[str, object]] = []
    for row in alerts:
        alert_id = cast(str, row["id"])
        detection = cast(str, row["detection"])
        if detection not in HOLD_BY_DETECTION:
            _fail("ALERT_DETECTION_DRIFT", "alert.detection")
        kind, variants = HOLD_BY_DETECTION[detection]
        compiled_alerts.append(
            {
                **row,
                "route": {
                    "owner": "Operations Owner",
                    "runbook_id": ROUTE_MAP[alert_id],
                    "notification_mode": "LOCAL_LOG_ONLY_DISABLED",
                },
                "hold": {
                    "kind": kind,
                    "variants": [
                        {
                            "variant": variant,
                            "duration_seconds": duration,
                            "cycle_required": cycle,
                        }
                        for variant, duration, cycle in variants
                    ],
                },
            }
        )
    return {
        "document": {
            "id": "RAOS-ST1602-SLO-ALERT-RUNTIME-CATALOG-002",
            "version": "2.0.0",
            "story_id": "ST-1602",
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "classification": "LOCAL_SYNTHETIC_NON_ATTESTING_SLO_ALERT_RUNTIME",
        },
        "authority": {
            "slo_catalog_sha256": AUTHORITY_SOURCES[4][2],
            "alert_catalog_sha256": AUTHORITY_SOURCES[5][2],
            "runbook_catalog_sha256": AUTHORITY_SOURCES[6][2],
        },
        "slos": compiled_slos,
        "alerts": compiled_alerts,
        "runbooks": runbooks,
        "boundary": {
            "source": "SYNTHETIC_RECORDED_FIXTURE_ONLY",
            "notifications_enabled": False,
            "notification_mode": "LOCAL_LOG_ONLY_DISABLED",
            "external_action_count": 0,
            "formal_tst_027": "NOT_EXECUTED",
            "formal_tst_028": "NOT_EXECUTED",
            "production": "NOT_AUTHORIZED",
        },
    }


def recorded_fixture(catalog: Mapping[str, object]) -> dict[str, object]:
    slo_windows: list[dict[str, object]] = []
    for slo in cast(list[dict[str, object]], catalog["slos"]):
        evaluation = cast(dict[str, object], slo["evaluation"])
        components = cast(list[str], evaluation["components"])
        thresholds = cast(list[int], evaluation["thresholds"])
        if evaluation["kind"] == "RATIO_MINIMUM":
            values = [
                {"name": "numerator", "value": thresholds[0]},
                {"name": "denominator", "value": 1_000_000},
            ]
        else:
            values = [
                {"name": name, "value": threshold}
                for name, threshold in zip(components, thresholds, strict=True)
            ]
        slo_windows.append(
            {
                "slo_id": slo["id"],
                "source": "SYNTHETIC_RECORDED_FIXTURE_ONLY",
                "observed_at_epoch_seconds": 10_000,
                "evaluated_at_epoch_seconds": 10_010,
                "fresh_until_epoch_seconds": 20_000,
                "window_start_epoch_seconds": 1_000,
                "window_end_epoch_seconds": 10_000,
                "sample_count": 1_000,
                "mature": True,
                "values": values,
            }
        )
    alert_observations: list[dict[str, object]] = []
    for alert in cast(list[dict[str, object]], catalog["alerts"]):
        variants = cast(dict[str, object], alert["hold"])["variants"]
        first = cast(list[dict[str, object]], variants)[0]
        duration = first["duration_seconds"]
        alert_id = cast(str, alert["id"])
        alert_observations.append(
            {
                "alert_id": alert_id,
                "instance_id": f"recorded-{alert_id.lower()}",
                "source": "SYNTHETIC_RECORDED_FIXTURE_ONLY",
                "observed_at_epoch_seconds": 10_000,
                "evaluated_at_epoch_seconds": 10_010,
                "fresh_until_epoch_seconds": 20_000,
                "sample_count": 100,
                "mature": True,
                "condition_state": "BREACH",
                "hold_variant": first["variant"],
                "condition_started_at_epoch_seconds": (
                    0 if duration is not None else None
                ),
                "cycle_complete": first["cycle_required"],
                "observation_sha256": _sha256(
                    f"ST1602|{alert_id}|RECORDED".encode("ascii")
                ),
            }
        )
    return {
        "document": {
            "id": "RAOS-ST1602-SLO-ALERT-RECORDED-FIXTURE-002",
            "version": "2.0.0",
            "story_id": "ST-1602",
            "classification": "LOCAL_SYNTHETIC_NON_ATTESTING",
            "catalog_sha256": _canonical_sha256(catalog),
        },
        "slo_windows": slo_windows,
        "alert_observations": alert_observations,
        "boundary": {
            "actual_measurement": False,
            "notification_delivery": False,
            "external_action_count": 0,
            "production": "NOT_AUTHORIZED",
        },
    }


def _canonical_sha256(value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256(content)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _evidence(catalog: Mapping[str, object], fixture: Mapping[str, object]) -> bytes:
    alerts = cast(list[dict[str, object]], catalog["alerts"])
    evidence = {
        "document": {
            "id": "RAOS-ST1602-SLO-ALERT-LOCAL-COMPLETION-002",
            "version": "2.0.0",
            "story_id": "ST-1602",
            "classification": "LOCAL_GENERATED_NON_ATTESTING_EVIDENCE",
        },
        "inventory": {
            "typed_slo_rules": len(cast(list[object], catalog["slos"])),
            "typed_alert_rules": len(alerts),
            "runbook_catalog_rows": len(cast(list[object], catalog["runbooks"])),
            "owner_routes": sum(
                1
                for row in alerts
                if cast(dict[str, object], row["route"])["owner"] == "Operations Owner"
            ),
            "runbook_routes": sum(
                1
                for row in alerts
                if cast(dict[str, object], row["route"])["runbook_id"]
                in set(ROUTE_MAP.values())
            ),
            "recorded_slo_windows": len(cast(list[object], fixture["slo_windows"])),
            "recorded_alert_observations": len(
                cast(list[object], fixture["alert_observations"])
            ),
        },
        "safety_boundary": {
            "od_011": "HUMAN_DECISION_REQUIRED",
            "notification_mode": "LOCAL_LOG_ONLY_DISABLED",
            "notification_delivery_claim": False,
            "actual_slo_attainment_claim": False,
            "external_action_count": 0,
            "formal_tst_027": "NOT_EXECUTED",
            "formal_tst_028": "NOT_EXECUTED",
            "hosted_ci": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(evidence, sort_keys=False, allow_unicode=True).encode("utf-8")


def _manifest(
    root: Path,
    catalog_bytes: bytes,
    fixture_bytes: bytes,
    evidence_bytes: bytes,
) -> bytes:
    generated = (
        (CATALOG_PATH, catalog_bytes),
        (FIXTURE_PATH, fixture_bytes),
        (EVIDENCE_PATH, evidence_bytes),
    )
    manifest = {
        "document": {
            "id": "RAOS-ST1602-SLO-ALERT-RUNTIME-MANIFEST-002",
            "version": "2.0.0",
            "story_id": "ST-1602",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "authority_sources": _source_rows(AUTHORITY_SOURCES),
            "dependency_sources": _uri_hash_rows(DEPENDENCY_SOURCES),
            "v1_compatibility_sources": _uri_hash_rows(V1_SOURCES),
            "implementation_helper": {
                "uri": f"repo://{IMPLEMENTATION_HELPER[0]}",
                "sha256": IMPLEMENTATION_HELPER[1],
                "purpose": "OWNER_SAFE_LOCAL_FILE_IO_ONLY",
                "semantics": "NO_RUNTIME_AUTHORITY",
            },
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": len(generated),
        "generated_artifacts": [
            {
                "uri": f"repo://{path.as_posix()}",
                "bytes": len(content),
                "sha256": _sha256(content),
            }
            for path, content in generated
        ],
        "boundary": {
            "v1_semantics": "UNCHANGED",
            "external_action_count": 0,
            "formal_tst_027": "NOT_EXECUTED",
            "formal_tst_028": "NOT_EXECUTED",
            "notification_delivery": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    catalog = runtime_catalog(root)
    fixture = recorded_fixture(catalog)
    catalog_bytes = _json_bytes(catalog)
    fixture_bytes = _json_bytes(fixture)
    evidence_bytes = _evidence(catalog, fixture)
    return {
        CATALOG_PATH: catalog_bytes,
        FIXTURE_PATH: fixture_bytes,
        EVIDENCE_PATH: evidence_bytes,
        MANIFEST_PATH: _manifest(root, catalog_bytes, fixture_bytes, evidence_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if tuple(expected) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT", "outputs")
    for relative in GENERATED_PATHS:
        path = base._output_file(  # pyright: ignore[reportPrivateUsage]
            root, relative
        )
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "outputs")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "outputs")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative, content in outputs.items():
        base._atomic_write(  # pyright: ignore[reportPrivateUsage]
            root, relative, content
        )


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
    except (SloAlertRuntimeBuildError, v1.SloAlertReferenceError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        "ST-1602 typed SLO/alert runtime checked"
        if args.check
        else "ST-1602 typed SLO/alert runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
