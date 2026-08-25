#!/usr/bin/env python3
"""Build the deterministic local-only ST-1604 fixture report and manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Final, NoReturn, cast
from uuid import UUID


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
for import_root in (REPO_ROOT, PYTHON_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from raos.domain.ops.performance_load import (  # noqa: E402
    LoadEvidenceSource,
    LoadReportStatus,
    LoadSurface,
    PerformanceLoadRequest,
    SurfaceBudget,
    SurfaceObservation,
    evaluate_performance_load,
)
from scripts import (  # noqa: E402
    build_st1604_performance_load_reference_plan as reference,
)


CONTRACT_PATH: Final = Path(
    "changes/st-1604/contracts/local-performance-load-evaluator.v2.json"
)
REPORT_PATH: Final = Path(
    "changes/st-1604/generated/local-performance-load-report.fixture.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-1604/local-runtime-manifest.v2.json")
GENERATOR_PATH: Final = Path("scripts/build_st1604_local_performance_load.py")
README_PATH: Final = Path("changes/st-1604/README.md")
EVIDENCE_PATH: Final = Path("changes/st-1604/LOCAL_COMPLETION_EVIDENCE_V2.md")
DOMAIN_PATH: Final = Path("python/raos/domain/ops/performance_load.py")
DOMAIN_INIT_PATH: Final = Path("python/raos/domain/ops/__init__.py")
PORT_PATH: Final = Path("python/raos/ports/performance_load.py")
APPLICATION_PATH: Final = Path("python/raos/application/ops/performance_load.py")
APPLICATION_INIT_PATH: Final = Path("python/raos/application/ops/__init__.py")
ADAPTER_PATH: Final = Path("python/raos/adapters/recorded_performance_load.py")
TEST_PATHS: Final = (
    Path("tests/st1604_runtime/conftest.py"),
    Path("tests/st1604_runtime/test_boundaries.py"),
    Path("tests/st1604_runtime/test_evaluator.py"),
    Path("tests/st1604_runtime/test_runtime_generation.py"),
    Path("tests/st1604_runtime/test_service_and_journal.py"),
)
AUTHORITY_PATHS: Final = (
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/06_ops/RAOS_12_slo_catalog_v1.0.yaml"),
    Path("docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
)
PREDECESSOR_PATHS: Final = (
    reference.REFERENCE_PLAN_PATH,
    reference.MANIFEST_PATH,
    reference.ST1505_MANIFEST_PATH,
    reference.ST1601_PATH,
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    README_PATH,
    EVIDENCE_PATH,
    GENERATOR_PATH,
    DOMAIN_PATH,
    DOMAIN_INIT_PATH,
    PORT_PATH,
    APPLICATION_PATH,
    APPLICATION_INIT_PATH,
    ADAPTER_PATH,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

_TOP_KEYS: Final = (
    "document",
    "request",
    "budgets",
    "observations",
    "verification_boundary",
    "action_counts",
)
_BUDGET_KEYS: Final = (
    "surface",
    "concurrent_units",
    "duration_ms",
    "max_p95_duration_ms",
    "max_p99_duration_ms",
    "max_error_basis_points",
    "min_throughput_milliops_per_second",
    "max_db_connections",
    "max_queue_age_p95_ms",
)
_OBSERVATION_KEYS: Final = (
    "surface",
    "concurrent_units",
    "duration_ms",
    "successful_operations",
    "duration_samples_ms",
    "max_db_connections",
    "queue_age_samples_ms",
)
_EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST1604-LOCAL-PERFORMANCE-LOAD-EVALUATOR-001",
    "version": "2.0.0",
    "story_id": "ST-1604",
    "classification": "DETERMINISTIC_RECORDED_LOCAL_ONLY_NOT_TST027_EVIDENCE",
    "local_evaluator_enabled": True,
    "recorded_capture_binding": "NOT_IMPLEMENTED_DISABLED",
    "recorded_capture_enabled": False,
    "workload_execution_enabled": False,
    "production_eligible": False,
}
_EXPECTED_VERIFICATION: Final = {
    "formal_tst_027": "NOT_EXECUTED",
    "actual_load": "NOT_EXECUTED",
    "browser_rum": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "canonical_slo_evaluation": "NOT_EVALUATED_TST_027_STAGING_REQUIRED",
}
_EXPECTED_ACTION_COUNTS: Final = {
    "load": 0,
    "browser": 0,
    "network": 0,
    "credential": 0,
    "provider": 0,
    "external": 0,
    "staging": 0,
    "release": 0,
    "production": 0,
}


class LocalPerformanceLoadBuildError(RuntimeError):
    """Stable sanitized V2 builder failure."""


def _fail(code: str) -> NoReturn:
    raise LocalPerformanceLoadBuildError(f"ST1604_LOCAL_BUILD_{code}") from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _real_root(root: Path) -> Path:
    if not root.is_absolute():
        _fail("ROOT_INVALID")
    try:
        resolved = root.resolve(strict=True)
    except OSError:
        _fail("ROOT_INVALID")
    if resolved != root or not root.is_dir():
        _fail("ROOT_INVALID")
    return root


def _regular_file(root: Path, relative: Path) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("PATH_INVALID")
    current = _real_root(root)
    try:
        for component in relative.parts[:-1]:
            current /= component
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail("PATH_INVALID")
        target = current / relative.name
        metadata = target.lstat()
    except LocalPerformanceLoadBuildError:
        raise
    except OSError:
        _fail("FILE_UNAVAILABLE")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("PATH_INVALID")
    return target


def _read(root: Path, relative: Path) -> bytes:
    path = _regular_file(root, relative)
    try:
        content = path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE")
    if not content or len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_INVALID")
    return content


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("DUPLICATE_KEY")
        value[key] = item
    return value


def _json_document(content: bytes) -> dict[str, Any]:
    try:
        decoded = content.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=_object_pairs,
            parse_float=lambda _value: _fail("FLOAT_FORBIDDEN"),
            parse_constant=lambda _value: _fail("CONSTANT_FORBIDDEN"),
        )
    except LocalPerformanceLoadBuildError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID")
    if type(value) is not dict:
        _fail("DOCUMENT_INVALID")
    return cast(dict[str, Any], value)


def _exact_mapping(value: object, keys: tuple[str, ...]) -> dict[str, Any]:
    if type(value) is not dict:
        _fail("CLOSED_SCHEMA_VIOLATION")
    typed = cast(dict[str, Any], value)
    if tuple(typed) != keys:
        _fail("CLOSED_SCHEMA_VIOLATION")
    return typed


def _exact_list(value: object) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_INVALID")
    return cast(list[Any], value)  # type: ignore[redundant-cast]


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
    except TypeError, ValueError, UnicodeError:
        _fail("SERIALIZATION_FAILED")


def _canonical_uuid(value: object) -> UUID:
    if type(value) is not str:
        _fail("UUID_INVALID")
    try:
        value.encode("ascii")
        parsed = UUID(value)
    except UnicodeError, ValueError, AttributeError:
        _fail("UUID_INVALID")
    if str(parsed) != value:
        _fail("UUID_INVALID")
    return parsed


def _compact_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except TypeError, ValueError, UnicodeError:
        _fail("SERIALIZATION_FAILED")


def _request_from_contract(contract: dict[str, Any]) -> PerformanceLoadRequest:
    if tuple(contract) != _TOP_KEYS:
        _fail("CLOSED_SCHEMA_VIOLATION")
    if contract["document"] != _EXPECTED_DOCUMENT:
        _fail("DOCUMENT_POLICY_INVALID")
    if contract["verification_boundary"] != _EXPECTED_VERIFICATION:
        _fail("VERIFICATION_BOUNDARY_INVALID")
    if contract["action_counts"] != _EXPECTED_ACTION_COUNTS or any(
        type(value) is not int or value != 0
        for value in contract["action_counts"].values()
    ):
        _fail("ACTION_BOUNDARY_INVALID")
    request = _exact_mapping(
        contract["request"],
        (
            "run_id",
            "observed_at",
            "evidence_source",
            "source_artifact_sha256",
            "dataset_id",
        ),
    )
    budget_rows = _exact_list(contract["budgets"])
    observation_rows = _exact_list(contract["observations"])
    if len(budget_rows) != 4 or len(observation_rows) != 4:
        _fail("SURFACE_COUNT_INVALID")
    try:
        budgets = tuple(
            SurfaceBudget(
                surface=LoadSurface(row["surface"]),
                concurrent_units=row["concurrent_units"],
                duration_ms=row["duration_ms"],
                max_p95_duration_ms=row["max_p95_duration_ms"],
                max_p99_duration_ms=row["max_p99_duration_ms"],
                max_error_basis_points=row["max_error_basis_points"],
                min_throughput_milliops_per_second=row[
                    "min_throughput_milliops_per_second"
                ],
                max_db_connections=row["max_db_connections"],
                max_queue_age_p95_ms=row["max_queue_age_p95_ms"],
            )
            for item in budget_rows
            for row in (_exact_mapping(item, _BUDGET_KEYS),)
        )
        observations = tuple(
            SurfaceObservation(
                surface=LoadSurface(row["surface"]),
                concurrent_units=row["concurrent_units"],
                duration_ms=row["duration_ms"],
                successful_operations=row["successful_operations"],
                duration_samples_ms=tuple(_exact_list(row["duration_samples_ms"])),
                max_db_connections=row["max_db_connections"],
                queue_age_samples_ms=(
                    None
                    if row["queue_age_samples_ms"] is None
                    else tuple(_exact_list(row["queue_age_samples_ms"]))
                ),
            )
            for item in observation_rows
            for row in (_exact_mapping(item, _OBSERVATION_KEYS),)
        )
        source_digest = _sha256(_compact_json_bytes(observation_rows))
        if source_digest != request["source_artifact_sha256"]:
            _fail("FIXTURE_DIGEST_INVALID")
        result = PerformanceLoadRequest(
            run_id=_canonical_uuid(request["run_id"]),
            observed_at=request["observed_at"],
            evidence_source=LoadEvidenceSource(request["evidence_source"]),
            source_artifact_sha256=request["source_artifact_sha256"],
            dataset_id=request["dataset_id"],
            budgets=budgets,
            observations=observations,
        )
    except LocalPerformanceLoadBuildError:
        raise
    except Exception:
        _fail("FIXTURE_INVALID")
    if tuple(row.surface for row in result.budgets) != tuple(LoadSurface):
        _fail("SURFACE_ORDER_INVALID")
    if tuple(row.surface for row in result.observations) != tuple(LoadSurface):
        _fail("SURFACE_ORDER_INVALID")
    return result


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    return _json_document(_read(root, CONTRACT_PATH))


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative)
    return {
        "bytes": len(content),
        "sha256": _sha256(content),
        "uri": f"repo://{relative.as_posix()}",
    }


def _validate_reference_owner(root: Path) -> None:
    try:
        rendered = reference.render_outputs(root)
    except Exception:
        _fail("REFERENCE_OWNER_INVALID")
    for path in reference.GENERATED_PATHS:
        if _read(root, path) != rendered[path]:
            _fail("REFERENCE_OWNER_DRIFT")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    _validate_reference_owner(root)
    request = _request_from_contract(load_contract(root))
    report = evaluate_performance_load(request)
    if report.report_status is not LoadReportStatus.LOCAL_CAPACITY_DOCUMENTED:
        _fail("FIXTURE_REPORT_NOT_DOCUMENTED")
    report_bytes = _canonical_json_bytes(report.as_dict())
    manifest = {
        "document": {
            "classification": "LOCAL_ONLY_REPRODUCIBLE_IMPLEMENTATION_EVIDENCE",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "id": "RAOS-ST1604-LOCAL-RUNTIME-MANIFEST-001",
            "story_id": "ST-1604",
            "version": "2.0.0",
        },
        "authority_inputs": [_artifact(root, path) for path in AUTHORITY_PATHS],
        "predecessor_inputs": [_artifact(root, path) for path in PREDECESSOR_PATHS],
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifacts": [
            {
                "bytes": len(report_bytes),
                "sha256": _sha256(report_bytes),
                "uri": f"repo://{REPORT_PATH.as_posix()}",
            }
        ],
        "safety_boundary": {
            "action_counts": dict(_EXPECTED_ACTION_COUNTS),
            "actual_load": "NOT_EXECUTED",
            "canonical_slo_evaluation": "NOT_EVALUATED",
            "formal_tst_027": "NOT_EXECUTED",
            "production_capacity_claim": None,
            "production_eligible": False,
            "recorded_capture_enabled": False,
            "rollback_detection_scope": (
                "LIVE_JOURNAL_INSTANCE_ONLY_NO_EXTERNAL_DURABLE_ANCHOR"
            ),
            "staging": "NOT_EXECUTED",
        },
    }
    return {
        REPORT_PATH: report_bytes,
        MANIFEST_PATH: _canonical_json_bytes(manifest),
    }


def _output_path(root: Path, relative: Path, *, create: bool) -> Path:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        _fail("OUTPUT_PATH_INVALID")
    current = _real_root(root)
    for component in relative.parts[:-1]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                _fail("OUTPUT_MISSING")
            current.mkdir(mode=0o755)
            metadata = current.lstat()
        except OSError:
            _fail("OUTPUT_PATH_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("OUTPUT_PATH_INVALID")
    target = current / relative.name
    if target.exists() or target.is_symlink():
        try:
            metadata = target.lstat()
        except OSError:
            _fail("OUTPUT_PATH_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("OUTPUT_PATH_INVALID")
    return target


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    target = _output_path(root, relative, create=True)
    descriptor = -1
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = ""
        os.chmod(target, 0o644, follow_symlinks=False)
    except OSError:
        _fail("OUTPUT_WRITE_FAILED")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        for relative, expected in outputs.items():
            if _read(root, relative) != expected:
                _fail("GENERATED_DRIFT")
        return
    for relative, content in outputs.items():
        _atomic_write(root, relative, content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        build(check=args.check)
    except LocalPerformanceLoadBuildError as error:
        print(error, file=sys.stderr)
        return 1
    print(
        "ST-1604 local performance/load artifacts verified"
        if args.check
        else "ST-1604 local performance/load artifacts generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
