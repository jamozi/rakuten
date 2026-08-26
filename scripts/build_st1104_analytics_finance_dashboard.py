#!/usr/bin/env python3
"""Build the deterministic ST-1104 recorded dashboard projection and manifest."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import os
from pathlib import Path
import stat
import sys
from typing import Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT / "python", REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from raos.adapters.recorded_analytics_finance_dashboard import (  # noqa: E402
    RecordedAnalyticsFinanceDashboardAdapter,
)
from raos.adapters.recorded_kpi_input import (  # noqa: E402
    COMPLETE_FIXTURE_BYTES,
    COMPLETE_FIXTURE_SHA256,
    RecordedKpiInputAdapter,
)
from raos.adapters.recorded_unit_economics import (  # noqa: E402
    RecordedUnitEconomicsAdapter,
    load_recorded_unit_economics_fixture,
)
from scripts.raos_build_core import input_hash_required  # noqa: E402
from raos.application.analytics.analytics_finance_dashboard import (  # noqa: E402
    AnalyticsFinanceDashboardService,
)
from raos.application.analytics.kpi_read_model import (  # noqa: E402
    RecordedKpiCalculationJob,
)
from raos.application.finance.unit_economics import UnitEconomicsService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.analytics.analytics_finance_dashboard import (  # noqa: E402
    AnalyticsFinanceDashboardSnapshot,
    DashboardDigest,
    RecordedDashboardCommand,
    SCHEMA_VERSION,
    SCREEN_ORDER,
)
from raos.domain.analytics.kpi_read_model import (  # noqa: E402
    AttributionBasis,
    CalculationContext,
    COMPLETE_RECORDED_INPUT_SHA256,
    FixtureByteLength,
    KpiCalculationCommand,
    MeasurementPeriod,
    ProgramId,
    RAKUTEN_BLOG_PROGRAM,
    Sha256Digest,
)
from scripts import build_st1303_attribution_engine as st1303  # noqa: E402
from scripts import secure_generated_publication  # noqa: E402


EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 8 * 1024 * 1024

CONTRACT_PATH: Final = Path(
    "changes/st-1104/contracts/analytics-finance-dashboard.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1104/fixtures/analytics-finance-dashboard-recorded.synthetic.v2.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1104/generated/analytics-finance-dashboard-recorded.v2.json"
)
GENERATED_TS_PATH: Final = Path("packages/web-ui/src/analytics-finance-recorded.v2.ts")
MANIFEST_PATH: Final = Path("changes/st-1104/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1104_analytics_finance_dashboard.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
ST1205_FIXTURE_PATH: Final = Path(
    "changes/st-1205/fixtures/recorded/kpi-calculation-complete.v2.json"
)
ST1304_FIXTURE_PATH: Final = Path(
    "changes/st-1304/fixtures/cost-unit-economics-recorded.synthetic.v2.json"
)
ST1303_FIXTURE_PATH: Final = Path(
    "changes/st-1303/fixtures/attribution-engine-recorded.synthetic.v2.json"
)

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1104/PREFLIGHT-v2.md"),
    Path("changes/st-1104/README.md"),
    Path("changes/st-1104/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("docs/worklogs/ST-1104.md"),
    Path("python/raos/domain/analytics/analytics_finance_dashboard.py"),
    Path("python/raos/application/analytics/analytics_finance_dashboard.py"),
    Path("python/raos/ports/analytics_finance_dashboard.py"),
    Path("python/raos/adapters/recorded_analytics_finance_dashboard.py"),
    Path("packages/web-ui/src/index.ts"),
    GENERATOR_PATH,
    Path("tests/st1104_v2/__init__.py"),
    Path("tests/st1104_v2/conftest.py"),
    Path("tests/st1104_v2/test_runtime.py"),
    Path("tests/st1104_v2/test_negative.py"),
    Path("tests/st1104_v2/test_generation.py"),
    Path("tests/st1104/analytics-finance-workspace-v2-generation.test.ts"),
)
LOCKED_TOOLCHAIN_PATHS: Final = (
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("package.json"),
    Path("package-lock.json"),
)

TOP_LEVEL_KEYS: Final = (
    "document",
    "source_bindings",
    "recorded_fixture",
    "screen_contract",
    "data_contract",
    "unavailable_contract",
    "accessibility_contract",
    "security_controls",
    "authority_boundary",
    "verification_boundary",
)


class DashboardBuildError(RuntimeError):
    """Sanitized owner-build failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise DashboardBuildError(f"ST-1104 build failed: {code} field={field}") from None


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


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("PATH_INVALID", relative.as_posix())
    return root / relative


def _read_regular(path: Path) -> bytes:
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
        content = absolute.read_bytes()
    except OSError:
        _fail("INPUT_UNAVAILABLE", path.as_posix())
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not content
        or len(content) != metadata.st_size
        or len(content) > MAX_SOURCE_BYTES
    ):
        _fail("INPUT_INVALID", path.as_posix())
    return content


def _mapping(value: object, field: str) -> dict[str, object]:
    if type(value) is not dict or any(
        type(key) is not str for key in cast(dict[object, object], value)
    ):
        _fail("SHAPE_INVALID", field)
    return cast(dict[str, object], value)


def _load_contract(root: Path = REPO_ROOT) -> dict[str, object]:
    content = _read_regular(_safe_path(root, CONTRACT_PATH))
    try:
        value = yaml.load(content, Loader=UniqueSafeLoader)
    except DashboardBuildError:
        raise
    except Exception:
        _fail("YAML_INVALID", "contract")
    contract = _mapping(value, "contract")
    if tuple(contract) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    document = _mapping(contract["document"], "document")
    if document != {
        "schema_version": SCHEMA_VERSION,
        "story_id": "ST-1104",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_RECORDED_SYNTHETIC_ANALYTICS_FINANCE_DASHBOARD_V2"
        ),
        "status": "LOCAL_CODE_COMPLETE",
        "executable_environments": ["ENV-DEV", "ENV-CI"],
        "canonical_status": "UNCHANGED",
        "historical_v1_replaced": False,
        "formal_validation_claimed": False,
        "production_eligible": False,
    }:
        _fail("CONTRACT_VALUE_INVALID", "document")
    bindings = _mapping(contract["source_bindings"], "source_bindings")
    if not bindings:
        _fail("CONTRACT_VALUE_INVALID", "source_bindings")
    for name, value in bindings.items():
        row = _mapping(value, f"source_bindings.{name}")
        if tuple(row) != ("path", "sha256"):
            _fail("CONTRACT_SHAPE_INVALID", f"source_bindings.{name}")
        path = row["path"]
        digest = row["sha256"]
        if type(path) is not str or type(digest) is not str:
            _fail("CONTRACT_VALUE_INVALID", f"source_bindings.{name}")
        content = _read_regular(_safe_path(root, Path(path)))
        if input_hash_required(path) and _sha256(content) != digest:
            _fail("SOURCE_HASH_DRIFT", name)
    fixture = _mapping(contract["recorded_fixture"], "recorded_fixture")
    fixture_bytes = _read_regular(_safe_path(root, FIXTURE_PATH))
    if fixture != {
        "path": FIXTURE_PATH.as_posix(),
        "sha256": _sha256(fixture_bytes),
        "bytes": len(fixture_bytes),
        "synthetic": True,
        "environment": "ENV-CI",
        "st1205_input_sha256": COMPLETE_RECORDED_INPUT_SHA256,
        "st1304_input_sha256": (
            "550088b277a4a566a19ae79cd330031d87ec1223359fce4f2995f2d8259be7fe"
        ),
        "st1304_result_sha256": (
            "7108e8cd43b5f047ad1cd5ffd9d84874eb937ea95f57004386b38e6182789571"
        ),
        "provider_execution": "NOT_EXECUTED",
    }:
        _fail("CONTRACT_VALUE_INVALID", "recorded_fixture")
    screen = _mapping(contract["screen_contract"], "screen_contract")
    order = screen.get("order")
    if (
        type(order) is not list
        or any(type(item) is not str for item in cast(list[object], order))
        or tuple(cast(list[str], order)) != SCREEN_ORDER
        or screen.get("exact_count") != 6
        or screen.get("route_registration") != "DISABLED_ST1101_AUTH_TRANSPORT"
        or screen.get("source_period_merge_allowed") is not False
        or screen.get("unknown_as_zero_allowed") is not False
    ):
        _fail("CONTRACT_VALUE_INVALID", "screen_contract")
    data = _mapping(contract["data_contract"], "data_contract")
    if (
        data.get("classification") != "CONFIDENTIAL"
        or data.get("source_mode") != "RECORDED_SYNTHETIC_DEV_CI_ONLY"
        or data.get("program") != RAKUTEN_BLOG_PROGRAM
        or data.get("live_verification_claimed") is not False
        or data.get("current_or_stale_inference_allowed") is not False
        or data.get("recommendation_input_allowed") is not False
        or data.get("public_projection_allowed") is not False
    ):
        _fail("CONTRACT_VALUE_INVALID", "data_contract")
    unavailable = _mapping(contract["unavailable_contract"], "unavailable_contract")
    if (
        unavailable.get("missing") != "UNAVAILABLE"
        or unavailable.get("unverified") != "UNAVAILABLE"
        or unavailable.get("zero_denominator") != "UNAVAILABLE"
        or unavailable.get("period_mismatch") != "UNAVAILABLE_PERIOD_MISMATCH"
        or unavailable.get("verified_zero") != "AVAILABLE_ZERO"
        or unavailable.get("unavailable_value") is not None
    ):
        _fail("CONTRACT_VALUE_INVALID", "unavailable_contract")
    authority = _mapping(contract["authority_boundary"], "authority_boundary")
    if not authority or any(value is not False for value in authority.values()):
        _fail("CONTRACT_VALUE_INVALID", "authority_boundary")
    return contract


def _validate_toolchain() -> None:
    if (
        sys.implementation.name != "cpython"
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
    ):
        _fail("PYTHON_TOOLCHAIN_DRIFT", "python")
    try:
        pyyaml_version = package_version("PyYAML")
    except PackageNotFoundError:
        _fail("PYTHON_TOOLCHAIN_DRIFT", "PyYAML")
    if pyyaml_version != EXPECTED_PYYAML_VERSION:
        _fail("PYTHON_TOOLCHAIN_DRIFT", "PyYAML")


def _execute_snapshot(
    root: Path, contract: Mapping[str, object]
) -> AnalyticsFinanceDashboardSnapshot:
    kpi_fixture = _read_regular(_safe_path(root, ST1205_FIXTURE_PATH))
    kpi_command = KpiCalculationCommand(
        recording_id="complete",
        fixture_digest=Sha256Digest(COMPLETE_FIXTURE_SHA256),
        fixture_length=FixtureByteLength(COMPLETE_FIXTURE_BYTES),
        expected_input_digest=Sha256Digest(COMPLETE_RECORDED_INPUT_SHA256),
        context=CalculationContext(
            MeasurementPeriod(date(2026, 7, 1), date(2026, 7, 31)),
            ProgramId(RAKUTEN_BLOG_PROGRAM),
            AttributionBasis.DIRECT,
        ),
    )
    kpi_snapshot = RecordedKpiCalculationJob(
        exchange=RecordedKpiInputAdapter(kpi_fixture)
    ).calculate(kpi_command)
    measurement_contract = st1303.load_contract(root)[1]
    scenario = load_recorded_unit_economics_fixture(
        _safe_path(root, ST1304_FIXTURE_PATH).resolve(),
        attribution_fixture_path=_safe_path(root, ST1303_FIXTURE_PATH).resolve(),
        contract=measurement_contract,
    )
    unit_result = UnitEconomicsService(
        environment=RuntimeEnvironment.CI,
        runner=RecordedUnitEconomicsAdapter(),
    ).execute(scenario.request)
    fixture = _read_regular(_safe_path(root, FIXTURE_PATH))
    fixture_contract = _mapping(contract["recorded_fixture"], "recorded_fixture")
    command = RecordedDashboardCommand(
        fixture_sha256=DashboardDigest(cast(str, fixture_contract["sha256"])),
        fixture_bytes=cast(int, fixture_contract["bytes"]),
        expected_kpi_input_sha256=DashboardDigest(
            cast(str, fixture_contract["st1205_input_sha256"])
        ),
        expected_unit_input_sha256=DashboardDigest(
            cast(str, fixture_contract["st1304_input_sha256"])
        ),
        expected_unit_result_sha256=DashboardDigest(
            cast(str, fixture_contract["st1304_result_sha256"])
        ),
    )
    source = RecordedAnalyticsFinanceDashboardAdapter(
        fixture_bytes=fixture,
        kpi_snapshot=kpi_snapshot,
        unit_request=scenario.request,
        unit_result=unit_result,
    )
    return AnalyticsFinanceDashboardService(
        environment=RuntimeEnvironment.CI,
        source=source,
    ).execute(command)


def _json_bytes(value: object) -> bytes:
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


def _typescript_bytes(output: bytes) -> bytes:
    payload = output.decode("ascii").rstrip("\n")
    encoded = (
        "'"
        + payload.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        + "'"
    )
    return (
        "/* Generated by scripts/build_st1104_analytics_finance_dashboard.py. */\n"
        "/* Do not edit by hand. */\n"
        "export const ST1104_RECORDED_DASHBOARD_V2_SHA256 =\n"
        f"  '{_sha256(output)}' as const;\n"
        "export const ST1104_RECORDED_DASHBOARD_V2_JSON =\n"
        f"  {encoded} as const;\n"
    ).encode("ascii")


def _source_paths(contract: Mapping[str, object]) -> tuple[tuple[Path, str], ...]:
    bindings = _mapping(contract["source_bindings"], "source_bindings")
    canonical = tuple(
        (Path(cast(str, _mapping(value, name)["path"])), "BOUND_INPUT")
        for name, value in bindings.items()
    )
    return (
        *((path, "OWNER_SOURCE") for path in OWNED_SOURCE_PATHS),
        *((path, "LOCKED_TOOLCHAIN") for path in LOCKED_TOOLCHAIN_PATHS),
        (SECURE_HELPER_PATH, "GENERATION_SECURITY_CONTROL"),
        *canonical,
    )


def _manifest_bytes(
    root: Path,
    contract: Mapping[str, object],
    output: bytes,
    generated_ts: bytes,
) -> bytes:
    seen: set[Path] = set()
    sources = []
    for path, role in _source_paths(contract):
        if path in seen:
            continue
        seen.add(path)
        content = _read_regular(_safe_path(root, path))
        sources.append(
            {
                "uri": f"repo://{path.as_posix()}",
                "role": role,
                "bytes": len(content),
                "sha256": _sha256(content),
            }
        )
    document = {
        "schema_version": 2,
        "story_id": "ST-1104",
        "local_status": "LOCAL_CODE_COMPLETE",
        "classification": "LOCAL_RECORDED_ANALYTICS_FINANCE_DASHBOARD_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{OUTPUT_PATH.as_posix()}",
                "role": "HEADLESS_RECORDED_READ_MODEL",
                "bytes": len(output),
                "sha256": _sha256(output),
            },
            {
                "uri": f"repo://{GENERATED_TS_PATH.as_posix()}",
                "role": "IMMUTABLE_TYPESCRIPT_FIXTURE_WRAPPER",
                "bytes": len(generated_ts),
                "sha256": _sha256(generated_ts),
            },
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": ".venv/bin/python scripts/build_st1104_analytics_finance_dashboard.py",
            "check_command": (
                ".venv/bin/python scripts/build_st1104_analytics_finance_dashboard.py --check"
            ),
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "secure_helper_sha256": _sha256(
                _read_regular(_safe_path(root, SECURE_HELPER_PATH))
            ),
            "python": "3.14.6",
            "pyyaml": EXPECTED_PYYAML_VERSION,
        },
        "authority": {
            "route_registered": False,
            "render_enabled": False,
            "mutation_authorized": False,
            "public_projection": False,
            "publication_authorized": False,
            "release_authorized": False,
            "production_authorized": False,
            "TST-022": "NOT_EXECUTED",
            "TST-024": "NOT_EXECUTED",
            "TST-030": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def expected_artifacts(root: Path = REPO_ROOT) -> tuple[tuple[Path, bytes], ...]:
    _validate_toolchain()
    contract = _load_contract(root)
    snapshot = _execute_snapshot(root, contract)
    output = _json_bytes(snapshot.payload())
    generated_ts = _typescript_bytes(output)
    manifest = _manifest_bytes(root, contract, output, generated_ts)
    return (
        (OUTPUT_PATH, output),
        (GENERATED_TS_PATH, generated_ts),
        (MANIFEST_PATH, manifest),
    )


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for relative, expected in artifacts:
            if _read_regular(_safe_path(root, relative)) != expected:
                _fail("GENERATED_ARTIFACT_DRIFT", relative.as_posix())
        return
    try:
        secure_generated_publication.publish_generated(
            tuple(
                (_safe_path(root, relative), content) for relative, content in artifacts
            ),
            namespace="st1104",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED", "generated_artifacts")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    try:
        build(check=bool(arguments.check))
    except Exception:
        print("ST-1104 dashboard generation failed", file=sys.stderr)
        return 1
    print(
        "ST-1104 dashboard checked"
        if arguments.check
        else "ST-1104 dashboard generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
