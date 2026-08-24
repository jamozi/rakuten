#!/usr/bin/env python3
"""Build the deterministic recorded ST-1103 workspace projection and manifest."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import errno
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast
from uuid import UUID

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from scripts import secure_generated_publication  # noqa: E402

from raos.domain.freshness.freshness import (  # noqa: E402
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
    FreshnessObservationStatus,
    FreshnessScheduleEntry,
    FreshnessScheduleRequest,
    FreshnessScheduleStatus,
    FreshnessState,
    evaluate_freshness,
    provisional_freshness_policy_binding,
    select_due_freshness,
)
from raos.domain.ops.job_runtime import (  # noqa: E402
    Fingerprint,
    JobLease,
    JobRecord,
    JobState,
    RuntimeFailureCode,
)


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"

CONTRACT_PATH: Final = Path(
    "changes/st-1103/contracts/freshness-operations-workspace.v2.yaml"
)
FIXTURE_PATH: Final = Path("changes/st-1103/freshness-operations-recorded.v2.json")
GENERATED_TS_PATH: Final = Path(
    "packages/web-ui/src/freshness-operations-recorded.v2.ts"
)
MANIFEST_PATH: Final = Path("changes/st-1103/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1103_freshness_operations_workspace.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
SECURE_HELPER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)

CANONICAL_BINDINGS: Final = (
    (
        Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
        "integration",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
        "canonicalDecisions",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
        "openDecisions",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md"),
        "0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e",
        "uiDesign",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml"),
        "dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050",
        "screenCatalog",
    ),
    (
        Path("docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml"),
        "986ed1682b0f6b48c7e9fab04ff51229c000f4673e3cc3981e50903832f208f2",
        "componentCatalog",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
        "securityCatalog",
    ),
    (
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
        "testCatalog",
    ),
    (
        Path("docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md"),
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8",
        "operationsDesign",
    ),
    (
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
        "storyBacklog",
    ),
)

DEPENDENCY_BINDINGS: Final = (
    (
        Path("changes/st-1401/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"),
        "37be7ef769384885aafb802f6c69bb15dc8d7cb0aeaf15dff013144526b6f866",
        "st1401Completion",
    ),
    (
        Path("python/raos/domain/freshness/freshness.py"),
        "3a33b44d99f92fce6417257de8c170d4622dd900fe7cc7cbac0b67494469dd95",
        "st1401Domain",
    ),
    (
        Path("python/raos/adapters/recorded_freshness.py"),
        "83ad91d3301c48d3db3efa40c5835ae97dddaf22ebae4c5aa466bed8a0261ff5",
        "st1401Adapter",
    ),
    (
        Path("python/raos/domain/ops/job_runtime.py"),
        "e3623bdef2c6bdce9a3ed49c2d76929e7e590189af9ae65418cee565120162e6",
        "st1404Domain",
    ),
    (
        Path("python/raos/application/ops/job_runtime.py"),
        "b1ea28fcc6b0e051b5f4a7ba0ae09d1628b4ed9f0400fd747fa7c2f032dc0403",
        "st1404Application",
    ),
    (
        Path("python/raos/adapters/recorded_job_runtime.py"),
        "89db55e209caed06b0be29f95b7b165ded6e9acd9153e01ac54a8e8c51790064",
        "st1404Adapter",
    ),
    (
        Path("packages/web-ui/src/serializable.ts"),
        "56adb1e0356fba66e147be4c055b7a40f1115608a3e29bbee4584234f8b3273d",
        "st1101Serializable",
    ),
    (
        Path("packages/web-ui/src/route-guard.ts"),
        "8395f542c7c65445fa3d1bec4a0e037c96610da8589e1807604b4fb3fa6a584f",
        "st1101RouteGuard",
    ),
    (
        Path("packages/web-ui/src/data-table.ts"),
        "bb999786019d1c01ece36929124359af00c5362134c4ee4faf50ce496d3689f4",
        "st1101DataTable",
    ),
    (
        Path("packages/web-ui/src/dialog.ts"),
        "494ac8b9e2a4087de2d003dd6c28bfcab7c85961f418a5892453c865058724bc",
        "st1101Dialog",
    ),
    (SECURE_HELPER_PATH, SECURE_HELPER_SHA256, "securePublicationHelper"),
)

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("packages/web-ui/src/freshness-operations-workspace.ts"),
    Path("packages/web-ui/src/freshness-operations-workspace-v2.ts"),
    Path("packages/web-ui/src/index.ts"),
    Path("changes/st-1103/README.md"),
    Path("changes/st-1103/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("docs/execplans/ST-1103.md"),
    Path("docs/worklogs/ST-1103.md"),
    Path("tests/st1103/freshness-operations-workspace-contract.test.ts"),
    Path("tests/st1103/freshness-operations-workspace-model.test.ts"),
    Path("tests/st1103/freshness-operations-workspace-boundaries.test.ts"),
    Path("tests/st1103/freshness-operations-workspace-accessibility.test.ts"),
    Path("tests/st1103/freshness-operations-workspace-negative.test.ts"),
    Path("tests/st1103/freshness-operations-workspace-v2-model.test.ts"),
    Path("tests/st1103/freshness-operations-workspace-v2-actions.test.ts"),
    Path("tests/st1103/freshness-operations-workspace-v2-negative.test.ts"),
    Path("tests/st1103/freshness-operations-workspace-v2-generation.test.ts"),
    Path("tests/st1103/test_generation.py"),
)

LOCKED_TOOLCHAIN_PATHS: Final = (
    Path("package.json"),
    Path("package-lock.json"),
    Path("pyproject.toml"),
    Path("uv.lock"),
)

SOURCE_PATHS: Final = (
    *OWNED_SOURCE_PATHS,
    *(path for path, _digest, _name in CANONICAL_BINDINGS),
    *(path for path, _digest, _name in DEPENDENCY_BINDINGS),
    *LOCKED_TOOLCHAIN_PATHS,
)
GENERATED_PATHS: Final = (FIXTURE_PATH, GENERATED_TS_PATH, MANIFEST_PATH)

SCREEN_ORDER: Final = (
    "FRESH-001",
    "FRESH-002",
    "FRESH-003",
    "OPS-001",
    "OPS-002",
    "OPS-003",
    "OPS-004",
    "OPS-005",
)
MAX_CONTRACT_BYTES: Final = 262_144
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024
EVALUATED_AT: Final = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)


class WorkspaceGenerationError(ValueError):
    __slots__ = ()

    def __init__(self, code: str) -> None:
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise WorkspaceGenerationError(code) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            _fail("DUPLICATE_YAML_KEY")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _validate_toolchain() -> None:
    if (
        sys.implementation.name != EXPECTED_PYTHON_IMPLEMENTATION
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
        or getattr(yaml, "__version__", None) != EXPECTED_PYYAML_VERSION
    ):
        _fail("GENERATION_TOOLCHAIN_DRIFT")
    try:
        observed = distribution_version("PyYAML")
    except PackageNotFoundError:
        _fail("GENERATION_TOOLCHAIN_DRIFT")
    if observed != EXPECTED_PYYAML_VERSION:
        _fail("GENERATION_TOOLCHAIN_DRIFT")


def _safe_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("UNSAFE_PATH")
    resolved_root = root.resolve()
    current = resolved_root
    for part in relative.parts:
        current = current / part
        try:
            observed = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(observed.st_mode):
            _fail("SYMLINK_REJECTED")
    return resolved_root / relative


def _read_regular(path: Path, *, maximum: int | None = None) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    noatime = getattr(os, "O_NOATIME", 0)
    try:
        descriptor = os.open(path, flags | noatime)
    except OSError as error:
        if not noatime or error.errno not in {errno.EPERM, errno.EACCES}:
            _fail("SOURCE_OPEN_FAILED")
        try:
            descriptor = os.open(path, flags)
        except OSError:
            _fail("SOURCE_OPEN_FAILED")
    try:
        before = os.lstat(path)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or before.st_dev != opened.st_dev
            or before.st_ino != opened.st_ino
            or (maximum is not None and opened.st_size > maximum)
        ):
            _fail("SOURCE_IDENTITY_INVALID")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            total += len(chunk)
            if maximum is not None and total > maximum:
                _fail("SOURCE_SIZE_INVALID")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        named_after = os.lstat(path)
        if (
            after.st_dev != opened.st_dev
            or after.st_ino != opened.st_ino
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or named_after.st_dev != opened.st_dev
            or named_after.st_ino != opened.st_ino
        ):
            _fail("SOURCE_CHANGED_DURING_READ")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _sha(path: Path) -> str:
    return hashlib.sha256(_read_regular(path)).hexdigest()


def _require_hashes(root: Path) -> None:
    for relative, expected, _name in (*CANONICAL_BINDINGS, *DEPENDENCY_BINDINGS):
        if _sha(_safe_path(root, relative)) != expected:
            _fail("SOURCE_HASH_DRIFT")


def _load_contract(root: Path) -> dict[str, Any]:
    payload = _read_regular(_safe_path(root, CONTRACT_PATH), maximum=MAX_CONTRACT_BYTES)
    try:
        tokens = tuple(yaml.scan(payload))
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in tokens
        ):
            _fail("YAML_FEATURE_REJECTED")
        loaded = yaml.load(payload, Loader=_UniqueLoader)
    except WorkspaceGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    expected_keys = (
        "schema_version",
        "story_id",
        "local_status",
        "classification",
        "screen_order",
        "projection_boundary",
        "action_boundary",
        "accessibility_boundary",
        "verification_boundary",
    )
    if type(loaded) is not dict or tuple(loaded) != expected_keys:
        _fail("CONTRACT_SHAPE_INVALID")
    contract = cast(dict[str, Any], loaded)
    if (
        contract["schema_version"] != 2
        or contract["story_id"] != "ST-1103"
        or contract["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
        or contract["classification"]
        != "LOCAL_EXECUTABLE_RECORDED_FRESHNESS_OPERATIONS_WORKSPACE_V2"
        or tuple(contract["screen_order"]) != SCREEN_ORDER
        or contract["projection_boundary"]
        != {
            "source_mode": "RECORDED_SYNTHETIC_DEV_CI_ONLY",
            "st1401_policy_activation": "DISABLED_UNRESOLVED_OD_007",
            "st1401_policy_authority": "PROVISIONAL_CANONICAL_SAFE_DEFAULT",
            "st1401_persistence": "NOT_EXECUTED",
            "st1401_attestation": "NOT_ATTESTED",
            "st1404_runtime_mode": "RECORDED_ONE_STEP_DEV_CI_ONLY",
            "st1404_durability": "NOT_CLAIMED",
            "undeclared_dependency_state": "UNAVAILABLE",
            "unknown_as_zero_allowed": False,
            "raw_payload_allowed": False,
            "raw_source_allowed": False,
            "credential_allowed": False,
        }
        or contract["action_boundary"]
        != {
            "intent_kind": "HUMAN_REVIEW_REQUEST_ONLY",
            "effect": "NONE",
            "dispatch": "NOT_EXECUTED",
            "persistence": "NOT_EXECUTED",
            "mutation_authorized": False,
            "retry_authorized": False,
            "cancellation_authorized": False,
            "redrive_authorized": False,
            "kill_switch_authorized": False,
            "publication_authorized": False,
            "activation_authorized": False,
            "production_authorized": False,
        }
        or contract["accessibility_boundary"]
        != {
            "status_text_required": True,
            "status_code_required": True,
            "status_icon_required": True,
            "color_only_allowed": False,
            "table_caption_required": True,
            "column_headers_required": True,
            "row_headers_required": True,
            "keyboard_model_required": True,
            "zoom_target_percent": 200,
            "rendered": False,
            "browser_verified": False,
        }
        or contract["verification_boundary"]
        != {
            "TST-022": "NOT_EXECUTED",
            "TST-024": "NOT_EXECUTED",
            "formal_validation": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        }
    ):
        _fail("CONTRACT_CONTENT_INVALID")
    _require_hashes(root)
    return contract


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=False,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo is not UTC:
        _fail("NON_UTC_FIXTURE_TIME")
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _cue(code: str, text: str, icon: str) -> dict[str, object]:
    return {"code": code, "text": text, "icon": icon, "colorOnly": False}


def _status_for_freshness(value: FreshnessEvaluation) -> dict[str, object]:
    mapping = {
        FreshnessState.FRESH: ("FRESH", "Fresh", "STATUS_OK"),
        FreshnessState.WARNING: ("WARNING", "Warning", "STATUS_WARNING"),
        FreshnessState.CRITICAL: ("CRITICAL", "Critical", "STATUS_DANGER"),
        FreshnessState.UNKNOWN: ("UNKNOWN", "Unknown", "STATUS_UNKNOWN"),
    }
    return _cue(*mapping[value.state])


def _status_for_job(value: JobRecord) -> dict[str, object]:
    mapping = {
        JobState.QUEUED: ("QUEUED", "Queued", "STATUS_INFO"),
        JobState.RUNNING: ("RUNNING", "Running", "STATUS_PROGRESS"),
        JobState.RETRY_SCHEDULED: (
            "RETRY_SCHEDULED",
            "Retry scheduled",
            "STATUS_WARNING",
        ),
        JobState.QUARANTINED: (
            "QUARANTINED",
            "Quarantined",
            "STATUS_DANGER",
        ),
    }
    return _cue(*mapping[value.state])


def _dependency(
    story_id: str,
    status: str,
    source_sha256: str | None,
) -> dict[str, object]:
    return {
        "storyId": story_id,
        "status": status,
        "sourceSha256": source_sha256,
        "authority": False,
    }


def _column(identifier: str, label: str) -> dict[str, str]:
    return {"id": identifier, "label": label, "scope": "col"}


def _table(
    *,
    state: str,
    caption: str,
    row_header: str,
    columns: list[dict[str, str]],
    rows: list[dict[str, object]],
    empty: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "state": state,
        "caption": caption,
        "rowHeaderColumn": row_header,
        "columns": columns,
        "rows": rows,
        "emptyState": empty,
    }


def _action(
    *,
    code: str,
    label: str,
    availability: str,
    targets: list[str],
    reasons: list[str],
    step_up: bool,
) -> dict[str, object]:
    return {
        "actionCode": code,
        "label": label,
        "availability": availability,
        "targetFingerprints": targets,
        "reasonCodes": reasons,
        "futureEffectRequirements": {
            "humanApprovalRequired": True,
            "reasonRequired": True,
            "impactPreviewRequired": True,
            "idempotencyRequired": True,
            "auditRequired": True,
            "stepUpRequired": step_up,
        },
        "effect": "NONE",
        "dispatch": "NOT_EXECUTED",
        "persistence": "NOT_EXECUTED",
    }


def _freshness_rows() -> tuple[list[dict[str, object]], list[str]]:
    requests = {
        "FRESH-001": FreshnessEvaluationRequest(
            freshness_class_id="FRESH-001",
            observation_status=FreshnessObservationStatus.VALIDATED,
            observed_at=EVALUATED_AT - timedelta(hours=80),
            evaluated_at=EVALUATED_AT,
            recommendation_basis_affected=True,
        ),
        "FRESH-002": FreshnessEvaluationRequest(
            freshness_class_id="FRESH-002",
            observation_status=FreshnessObservationStatus.MISSING,
            observed_at=None,
            evaluated_at=EVALUATED_AT,
            recommendation_basis_affected=True,
        ),
    }
    evaluations = {
        class_id: evaluate_freshness(request) for class_id, request in requests.items()
    }
    schedules = (
        FreshnessScheduleEntry(
            schedule_id=UUID("00000000-0000-4000-8000-000000000001"),
            subject_fingerprint="1" * 64,
            freshness_class_id="FRESH-001",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT - timedelta(hours=2),
            priority=100,
        ),
        FreshnessScheduleEntry(
            schedule_id=UUID("00000000-0000-4000-8000-000000000002"),
            subject_fingerprint="2" * 64,
            freshness_class_id="FRESH-002",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT - timedelta(hours=1),
            priority=90,
        ),
        FreshnessScheduleEntry(
            schedule_id=UUID("00000000-0000-4000-8000-000000000003"),
            subject_fingerprint="3" * 64,
            freshness_class_id="FRESH-003",
            status=FreshnessScheduleStatus.ACTIVE,
            next_due_at=EVALUATED_AT + timedelta(hours=1),
            priority=80,
        ),
    )
    selection = select_due_freshness(
        FreshnessScheduleRequest(
            evaluated_at=EVALUATED_AT,
            limit=10,
            schedules=schedules,
        )
    )
    rows: list[dict[str, object]] = []
    targets: list[str] = []
    for intent in selection.intents:
        evaluation = evaluations[intent.freshness_class_id]
        target = intent.fingerprint
        targets.append(target)
        rows.append(
            {
                "rowKey": str(intent.schedule_id),
                "scheduleId": str(intent.schedule_id),
                "subjectFingerprint": intent.subject_fingerprint,
                "freshnessClassId": intent.freshness_class_id,
                "nextDueAt": _iso(intent.next_due_at),
                "priority": intent.priority,
                "requestFingerprint": intent.request_fingerprint,
                "evaluationFingerprint": evaluation.fingerprint,
                "state": evaluation.state.value,
                "projectionAction": evaluation.projection_action.value,
                "reviewAction": evaluation.review_action.value,
                "recommendationOrderAction": (
                    evaluation.recommendation_order_action.value
                ),
                "status": _status_for_freshness(evaluation),
            }
        )
    return rows, targets


def _job_rows() -> tuple[list[dict[str, object]], list[str], list[str]]:
    jobs = (
        JobRecord(
            job_id=UUID("00000000-0000-4000-8000-000000000101"),
            state=JobState.QUEUED,
            queue_name="recorded.ops.jobs",
            payload_fingerprint=Fingerprint("a" * 64),
            created_at=EVALUATED_AT - timedelta(hours=2),
            available_at=EVALUATED_AT - timedelta(hours=1),
            job_schema_version=1,
            version=1,
            max_attempts=3,
            delivery_max_attempts=3,
            deadline_at=EVALUATED_AT + timedelta(days=1),
        ),
        JobRecord(
            job_id=UUID("00000000-0000-4000-8000-000000000102"),
            state=JobState.RUNNING,
            queue_name="recorded.ops.jobs",
            payload_fingerprint=Fingerprint("b" * 64),
            created_at=EVALUATED_AT - timedelta(hours=3),
            available_at=EVALUATED_AT - timedelta(hours=2),
            job_schema_version=1,
            version=2,
            max_attempts=3,
            delivery_max_attempts=3,
            attempt_count=1,
            deadline_at=EVALUATED_AT + timedelta(hours=6),
            lease=JobLease(
                UUID("00000000-0000-4000-8000-000000000201"),
                EVALUATED_AT + timedelta(minutes=15),
            ),
        ),
        JobRecord(
            job_id=UUID("00000000-0000-4000-8000-000000000103"),
            state=JobState.RETRY_SCHEDULED,
            queue_name="recorded.ops.jobs",
            payload_fingerprint=Fingerprint("c" * 64),
            created_at=EVALUATED_AT - timedelta(hours=4),
            available_at=EVALUATED_AT + timedelta(minutes=30),
            job_schema_version=1,
            version=4,
            max_attempts=3,
            delivery_max_attempts=3,
            attempt_count=1,
            deadline_at=EVALUATED_AT + timedelta(hours=4),
            failure_code=RuntimeFailureCode.HANDLER_FAILED,
        ),
        JobRecord(
            job_id=UUID("00000000-0000-4000-8000-000000000104"),
            state=JobState.QUARANTINED,
            queue_name="recorded.ops.jobs",
            payload_fingerprint=Fingerprint("d" * 64),
            created_at=EVALUATED_AT - timedelta(hours=5),
            available_at=EVALUATED_AT - timedelta(hours=4),
            job_schema_version=1,
            version=3,
            max_attempts=3,
            delivery_max_attempts=3,
            attempt_count=1,
            deadline_at=EVALUATED_AT + timedelta(hours=2),
            completed_at=EVALUATED_AT - timedelta(minutes=5),
            failure_code=RuntimeFailureCode.HANDLER_FAILED,
        ),
    )
    rows: list[dict[str, object]] = []
    targets: list[str] = []
    quarantined: list[str] = []
    for job in jobs:
        record_material = {
            "attemptCount": job.attempt_count,
            "availableAt": _iso(job.available_at),
            "completedAt": None if job.completed_at is None else _iso(job.completed_at),
            "createdAt": _iso(job.created_at),
            "deadlineAt": None if job.deadline_at is None else _iso(job.deadline_at),
            "failureCode": None if job.failure_code is None else job.failure_code.value,
            "jobId": str(job.job_id),
            "leaseExpiresAt": None if job.lease is None else _iso(job.lease.expires_at),
            "maxAttempts": job.max_attempts,
            "queueName": job.queue_name,
            "state": job.state.value,
            "version": job.version,
        }
        record_fingerprint = _fingerprint(record_material)
        targets.append(record_fingerprint)
        if job.state is JobState.QUARANTINED:
            quarantined.append(record_fingerprint)
        rows.append(
            {
                "rowKey": str(job.job_id),
                **record_material,
                "recordFingerprint": record_fingerprint,
                "status": _status_for_job(job),
            }
        )
    return rows, targets, quarantined


def _unavailable_projection(
    *,
    screen_id: str,
    source_story_ids: list[str],
    components: list[str],
    dependencies: list[dict[str, object]],
    caption: str,
    row_header: str,
    columns: list[dict[str, str]],
    summary_code: str,
    summary_text: str,
    actions: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "screenId": screen_id,
        "dataStatus": "UNAVAILABLE_DEPENDENCY",
        "sourceStoryIds": source_story_ids,
        "components": components,
        "summaryStatus": _cue(summary_code, summary_text, "STATUS_UNKNOWN"),
        "dependencies": dependencies,
        "table": _table(
            state="UNAVAILABLE_DEPENDENCY",
            caption=caption,
            row_header=row_header,
            columns=columns,
            rows=[],
            empty=_cue(
                "UNAVAILABLE_DEPENDENCY",
                "Data source is unavailable; this is not zero items.",
                "STATUS_UNKNOWN",
            ),
        ),
        "actionDescriptors": actions,
        "dataClassification": "INTERNAL_METADATA_ONLY",
        "unknownAsZeroAllowed": False,
        "rawPayloadPresent": False,
    }


def _bindings() -> dict[str, object]:
    canonical_names = {
        "integration",
        "uiDesign",
        "screenCatalog",
        "componentCatalog",
        "operationsDesign",
        "securityCatalog",
        "testCatalog",
        "storyBacklog",
    }
    dependency_names = {
        "st1401Completion",
        "st1401Domain",
        "st1401Adapter",
        "st1404Domain",
        "st1404Application",
        "st1404Adapter",
        "st1101Serializable",
        "st1101RouteGuard",
        "st1101DataTable",
        "st1101Dialog",
    }
    canonical = {
        name: digest
        for _path, digest, name in CANONICAL_BINDINGS
        if name in canonical_names
    }
    dependencies = {
        name: digest
        for _path, digest, name in DEPENDENCY_BINDINGS
        if name in dependency_names
    }
    return {"canonical": canonical, "dependencies": dependencies}


def _fixture_material() -> dict[str, object]:
    freshness_rows, freshness_targets = _freshness_rows()
    job_rows, job_targets, quarantine_targets = _job_rows()
    st1101 = _dependency(
        "ST-1101",
        "DISABLED_HEADLESS_FOUNDATION",
        "56adb1e0356fba66e147be4c055b7a40f1115608a3e29bbee4584234f8b3273d",
    )
    st1401 = _dependency(
        "ST-1401",
        "LOCAL_RECORDED_INPUT",
        "3a33b44d99f92fce6417257de8c170d4622dd900fe7cc7cbac0b67494469dd95",
    )
    st1404 = _dependency(
        "ST-1404",
        "LOCAL_RECORDED_INPUT",
        "e3623bdef2c6bdce9a3ed49c2d76929e7e590189af9ae65418cee565120162e6",
    )
    projections: dict[str, object] = {}
    projections["FRESH-001"] = {
        "screenId": "FRESH-001",
        "dataStatus": "AVAILABLE_RECORDED",
        "sourceStoryIds": ["ST-1101", "ST-1401"],
        "components": [
            "UI-C001",
            "UI-C004",
            "UI-C005",
            "UI-C007",
            "UI-C008",
            "UI-C010",
            "UI-C035",
        ],
        "summaryStatus": _cue(
            "CRITICAL_AND_UNKNOWN_PRESENT",
            "Critical and unknown freshness records require review.",
            "STATUS_DANGER",
        ),
        "dependencies": [st1101, st1401],
        "table": _table(
            state="AVAILABLE_RECORDED",
            caption="Recorded freshness queue",
            row_header="SCHEDULE_ID",
            columns=[
                _column("SCHEDULE_ID", "Schedule"),
                _column("FRESHNESS_CLASS", "Freshness class"),
                _column("NEXT_DUE_AT", "Next due"),
                _column("STATE", "State"),
                _column("ACTION", "Safe degradation"),
            ],
            rows=freshness_rows,
            empty=None,
        ),
        "actionDescriptors": [
            _action(
                code="REQUEST_FRESHNESS_REVIEW",
                label="Request freshness review",
                availability="LOCAL_REVIEW_PROPOSAL_ONLY",
                targets=freshness_targets,
                reasons=["STALE_EVIDENCE", "UNKNOWN_EVIDENCE"],
                step_up=False,
            )
        ],
        "dataClassification": "INTERNAL_METADATA_ONLY",
        "unknownAsZeroAllowed": False,
        "rawPayloadPresent": False,
    }
    projections["FRESH-002"] = _unavailable_projection(
        screen_id="FRESH-002",
        source_story_ids=["ST-1101", "ST-1402"],
        components=["UI-C001", "UI-C004", "UI-C005", "UI-C007", "UI-C008", "UI-C010"],
        dependencies=[
            st1101,
            _dependency("ST-1402", "UNAVAILABLE_UNDECLARED_DEPENDENCY", None),
        ],
        caption="Link health",
        row_header="LINK_ID",
        columns=[
            _column("LINK_ID", "Link"),
            _column("DESTINATION", "Destination state"),
            _column("CHECKED_AT", "Checked at"),
            _column("STATE", "State"),
        ],
        summary_code="LINK_HEALTH_UNAVAILABLE",
        summary_text="Link health source is unavailable.",
        actions=[
            _action(
                code="REQUEST_LINK_REVIEW",
                label="Request link review",
                availability="BLOCKED_DEPENDENCY",
                targets=[],
                reasons=["LINK_HEALTH_REVIEW"],
                step_up=False,
            )
        ],
    )
    projections["FRESH-003"] = _unavailable_projection(
        screen_id="FRESH-003",
        source_story_ids=["ST-1101", "ST-1403"],
        components=["UI-C001", "UI-C004", "UI-C005", "UI-C010", "UI-C015", "UI-C035"],
        dependencies=[
            st1101,
            _dependency("ST-1403", "UNAVAILABLE_UNDECLARED_DEPENDENCY", None),
        ],
        caption="Refresh proposal",
        row_header="PROPOSAL_ID",
        columns=[
            _column("PROPOSAL_ID", "Proposal"),
            _column("DIFF", "Difference"),
            _column("REAPPROVAL", "Reapproval scope"),
            _column("STATE", "State"),
        ],
        summary_code="REFRESH_PROPOSAL_UNAVAILABLE",
        summary_text="Refresh proposal source is unavailable.",
        actions=[
            _action(
                code="REQUEST_REFRESH_PROPOSAL_REVIEW",
                label="Request proposal review",
                availability="BLOCKED_DEPENDENCY",
                targets=[],
                reasons=["REFRESH_PROPOSAL_REVIEW"],
                step_up=False,
            )
        ],
    )
    projections["OPS-001"] = {
        "screenId": "OPS-001",
        "dataStatus": "AVAILABLE_RECORDED",
        "sourceStoryIds": ["ST-1101", "ST-1404"],
        "components": [
            "UI-C001",
            "UI-C004",
            "UI-C005",
            "UI-C007",
            "UI-C008",
            "UI-C010",
            "UI-C017",
        ],
        "summaryStatus": _cue(
            "RECORDED_JOBS_PRESENT",
            "Recorded job states are available; durability is not claimed.",
            "STATUS_INFO",
        ),
        "dependencies": [st1101, st1404],
        "table": _table(
            state="AVAILABLE_RECORDED",
            caption="Recorded job monitor",
            row_header="JOB_ID",
            columns=[
                _column("JOB_ID", "Job"),
                _column("STATE", "State"),
                _column("ATTEMPT", "Attempt"),
                _column("DEADLINE", "Deadline"),
                _column("LEASE", "Lease"),
                _column("FAILURE", "Failure"),
            ],
            rows=job_rows,
            empty=None,
        ),
        "actionDescriptors": [
            _action(
                code="REQUEST_JOB_OPERATOR_REVIEW",
                label="Request operator review",
                availability="LOCAL_REVIEW_PROPOSAL_ONLY",
                targets=job_targets,
                reasons=["OPERATOR_TRIAGE", "JOB_STATE_REVIEW"],
                step_up=False,
            )
        ],
        "dataClassification": "INTERNAL_METADATA_ONLY",
        "unknownAsZeroAllowed": False,
        "rawPayloadPresent": False,
    }
    quarantine_rows = [
        row for row in job_rows if row["recordFingerprint"] in quarantine_targets
    ]
    projections["OPS-002"] = {
        "screenId": "OPS-002",
        "dataStatus": "AVAILABLE_RECORDED",
        "sourceStoryIds": ["ST-1101", "ST-1404"],
        "components": [
            "UI-C001",
            "UI-C004",
            "UI-C005",
            "UI-C006",
            "UI-C007",
            "UI-C008",
            "UI-C010",
            "UI-C012",
            "UI-C017",
        ],
        "summaryStatus": _cue(
            "RECORDED_QUARANTINE_PRESENT",
            "Recorded quarantine metadata requires investigation.",
            "STATUS_DANGER",
        ),
        "dependencies": [st1101, st1404],
        "table": _table(
            state="AVAILABLE_RECORDED",
            caption="Recorded quarantine metadata",
            row_header="JOB_ID",
            columns=[
                _column("JOB_ID", "Job"),
                _column("STATE", "State"),
                _column("FAILURE", "Failure"),
                _column("COMPLETED_AT", "Completed at"),
            ],
            rows=quarantine_rows,
            empty=None,
        ),
        "actionDescriptors": [
            _action(
                code="REQUEST_QUARANTINE_REVIEW",
                label="Request quarantine investigation",
                availability="LOCAL_REVIEW_PROPOSAL_ONLY",
                targets=quarantine_targets,
                reasons=["QUARANTINE_INVESTIGATION"],
                step_up=False,
            ),
            _action(
                code="REQUEST_DLQ_REDRIVE",
                label="Request DLQ redrive",
                availability="BLOCKED_DEPENDENCY",
                targets=[],
                reasons=["DLQ_REDRIVE_REVIEW"],
                step_up=True,
            ),
        ],
        "dataClassification": "INTERNAL_METADATA_ONLY",
        "unknownAsZeroAllowed": False,
        "rawPayloadPresent": False,
    }
    projections["OPS-003"] = _unavailable_projection(
        screen_id="OPS-003",
        source_story_ids=["ST-1101"],
        components=[
            "UI-C001",
            "UI-C004",
            "UI-C005",
            "UI-C006",
            "UI-C010",
            "UI-C016",
            "UI-C030",
        ],
        dependencies=[st1101],
        caption="Incident timeline",
        row_header="INCIDENT_ID",
        columns=[
            _column("INCIDENT_ID", "Incident"),
            _column("SEVERITY", "Severity"),
            _column("TIMELINE", "Timeline"),
            _column("STATE", "State"),
        ],
        summary_code="INCIDENT_SOURCE_UNAVAILABLE",
        summary_text="Incident persistence source is undeclared.",
        actions=[
            _action(
                code="REQUEST_INCIDENT_UPDATE",
                label="Request incident update",
                availability="BLOCKED_DEPENDENCY",
                targets=[],
                reasons=["INCIDENT_REVIEW"],
                step_up=False,
            )
        ],
    )
    projections["OPS-004"] = _unavailable_projection(
        screen_id="OPS-004",
        source_story_ids=["ST-1101", "ST-1405"],
        components=[
            "UI-C001",
            "UI-C004",
            "UI-C005",
            "UI-C010",
            "UI-C012",
            "UI-C013",
            "UI-C029",
        ],
        dependencies=[
            st1101,
            _dependency("ST-1405", "UNAVAILABLE_UNDECLARED_DEPENDENCY", None),
        ],
        caption="Kill switch generations",
        row_header="SCOPE",
        columns=[
            _column("SCOPE", "Scope"),
            _column("GENERATION", "Generation"),
            _column("STATE", "State"),
            _column("ACTOR", "Actor"),
        ],
        summary_code="KILL_SWITCH_SOURCE_UNAVAILABLE",
        summary_text="Kill switch source and step-up authority are unavailable.",
        actions=[
            _action(
                code="REQUEST_KILL_SWITCH_CHANGE",
                label="Request kill switch change",
                availability="BLOCKED_DEPENDENCY",
                targets=[],
                reasons=["EMERGENCY_CONTAINMENT_REVIEW"],
                step_up=True,
            )
        ],
    )
    projections["OPS-005"] = _unavailable_projection(
        screen_id="OPS-005",
        source_story_ids=["ST-1101", "ST-0405"],
        components=[
            "UI-C001",
            "UI-C004",
            "UI-C005",
            "UI-C007",
            "UI-C008",
            "UI-C010",
            "UI-C016",
        ],
        dependencies=[
            st1101,
            _dependency("ST-0405", "UNAVAILABLE_UNDECLARED_DEPENDENCY", None),
        ],
        caption="Audit events",
        row_header="EVENT_ID",
        columns=[
            _column("EVENT_ID", "Event"),
            _column("ACTOR", "Actor"),
            _column("CORRELATION", "Correlation"),
            _column("OCCURRED_AT", "Occurred at"),
        ],
        summary_code="AUDIT_SOURCE_UNAVAILABLE",
        summary_text="Audit read source is unavailable.",
        actions=[],
    )
    policy = provisional_freshness_policy_binding()
    if (
        policy.activation.value != "DISABLED_UNRESOLVED_OD_007"
        or policy.authority.value != "PROVISIONAL_CANONICAL_SAFE_DEFAULT"
        or policy.policy_active is not False
    ):
        _fail("ST1401_POLICY_BOUNDARY_DRIFT")
    return {
        "schemaVersion": 2,
        "storyId": "ST-1103",
        "classification": "RECORDED_SYNTHETIC_FRESHNESS_OPERATIONS_PROJECTION_V2",
        "environment": "CI",
        "evaluatedAt": _iso(EVALUATED_AT),
        "bindings": _bindings(),
        "projections": projections,
    }


def _typescript_bytes(fixture: bytes) -> bytes:
    fixture_sha = hashlib.sha256(fixture).hexdigest()
    fixture_text = fixture.decode("ascii").rstrip("\n")
    encoded_text = fixture_text.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "/* Generated by scripts/build_st1103_freshness_operations_workspace.py. */\n"
        "/* Do not edit by hand. */\n"
        "export const ST1103_RECORDED_PROJECTION_V2_SHA256 =\n"
        f"  '{fixture_sha}' as const;\n"
        "export const ST1103_RECORDED_PROJECTION_V2_JSON =\n"
        f"  '{encoded_text}' as const;\n"
    ).encode("ascii")


def _manifest_bytes(root: Path, fixture: bytes, generated_ts: bytes) -> bytes:
    canonical_paths = {path for path, _digest, _name in CANONICAL_BINDINGS}
    dependency_paths = {path for path, _digest, _name in DEPENDENCY_BINDINGS}
    sources = []
    for path in SOURCE_PATHS:
        source = _read_regular(_safe_path(root, path))
        sources.append(
            {
                "uri": f"repo://{path.as_posix()}",
                "bytes": len(source),
                "sha256": hashlib.sha256(source).hexdigest(),
                "role": (
                    "OWNER_SOURCE"
                    if path in OWNED_SOURCE_PATHS
                    else "CANONICAL_INPUT"
                    if path in canonical_paths
                    else "DEPENDENCY_CONTRACT"
                    if path in dependency_paths
                    else "LOCKED_TOOLCHAIN"
                ),
            }
        )
    document = {
        "schema_version": 2,
        "story_id": "ST-1103",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_RECORDED_FRESHNESS_OPERATIONS_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "artifact_role": "RECORDED_SYNTHETIC_PROJECTION",
                "media_type": "application/json",
                "bytes": len(fixture),
                "sha256": hashlib.sha256(fixture).hexdigest(),
            },
            {
                "uri": f"repo://{GENERATED_TS_PATH.as_posix()}",
                "artifact_role": "IMMUTABLE_TYPESCRIPT_FIXTURE_WRAPPER",
                "media_type": "text/typescript",
                "bytes": len(generated_ts),
                "sha256": hashlib.sha256(generated_ts).hexdigest(),
            },
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": ".venv/bin/python scripts/build_st1103_freshness_operations_workspace.py",
            "check_command": ".venv/bin/python scripts/build_st1103_freshness_operations_workspace.py --check",
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "secure_publication_helper_sha256": SECURE_HELPER_SHA256,
            "python_implementation": "CPython",
            "python_version": ".".join(str(item) for item in EXPECTED_PYTHON_VERSION),
            "pyyaml_version": EXPECTED_PYYAML_VERSION,
        },
        "authority": {
            "route_registered": False,
            "mutation_authorized": False,
            "retry_authorized": False,
            "cancellation_authorized": False,
            "redrive_authorized": False,
            "kill_switch_authorized": False,
            "publication_authorized": False,
            "activation_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "TST-022": "NOT_EXECUTED",
            "TST-024": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def _publish(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_generated_publication.publish_generated(
            artifacts,
            namespace="st1103",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def expected_artifacts(root: Path = REPO_ROOT) -> tuple[tuple[Path, bytes], ...]:
    _validate_toolchain()
    _load_contract(root)
    fixture = _canonical_bytes(_fixture_material())
    generated_ts = _typescript_bytes(fixture)
    manifest = _manifest_bytes(root, fixture, generated_ts)
    return (
        (FIXTURE_PATH, fixture),
        (GENERATED_TS_PATH, generated_ts),
        (MANIFEST_PATH, manifest),
    )


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for relative, payload in artifacts:
            if _read_regular(_safe_path(root, relative)) != payload:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    _publish(
        tuple((_safe_path(root, relative), payload) for relative, payload in artifacts)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    try:
        arguments, unknown = parser.parse_known_args(argv)
        if unknown:
            return 2
        build(check=arguments.check)
    except Exception:
        print("ST-1103 V2 workspace generation failed", file=sys.stderr)
        return 1
    print(
        "ST-1103 V2 workspace checked"
        if arguments.check
        else "ST-1103 V2 workspace generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
