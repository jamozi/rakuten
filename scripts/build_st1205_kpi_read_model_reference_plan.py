#!/usr/bin/env python3
"""Build the executable recorded-only ST-1205 KPI V2 contract projection."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import importlib
import json
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raos.adapters.recorded_kpi_input import (  # noqa: E402
    COMPLETE_FIXTURE_BYTES,
    COMPLETE_FIXTURE_SHA256,
    RecordedKpiInputAdapter,
)
from raos.application.analytics.kpi_read_model import (  # noqa: E402
    RecordedKpiCalculationJob,
)
from raos.domain.analytics.kpi_read_model import (  # noqa: E402
    AttributionBasis,
    CalculationContext,
    COMPLETE_RECORDED_INPUT_SHA256,
    FixtureByteLength,
    InputSpec,
    KPI_CALCULATION_VERSION,
    KPI_DEFINITIONS,
    KPI_DEFINITION_VERSION,
    KPI_IDS,
    KpiAvailability,
    KpiCalculationCommand,
    KpiDefinition,
    MeasurementPeriod,
    ProgramId,
    RAKUTEN_BLOG_PROGRAM,
    Sha256Digest,
)

base: Any = importlib.import_module("scripts.build_st1505_staging_deployment")


CONTRACT_PATH: Final = Path("changes/st-1205/contracts/kpi-read-model.v2.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-1205/fixtures/recorded/kpi-calculation-complete.v2.json"
)
LEGACY_CONTRACT_PATH: Final = Path(
    "changes/st-1205/contracts/kpi-read-model-reference-plan.v1.yaml"
)
LEGACY_REFERENCE_PATH: Final = Path(
    "changes/st-1205/generated/kpi-read-model-reference-plan.v1.json"
)
REFERENCE_PLAN_PATH: Final = Path("changes/st-1205/generated/kpi-read-model.v2.json")
MANIFEST_PATH: Final = Path("changes/st-1205/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1205_kpi_read_model_reference_plan.py")
README_PATH: Final = Path("changes/st-1205/README.md")
DOMAIN_PATH: Final = Path("python/raos/domain/analytics/kpi_read_model.py")
PORT_PATH: Final = Path("python/raos/ports/kpi_read_model.py")
APPLICATION_PATH: Final = Path("python/raos/application/analytics/kpi_read_model.py")
ADAPTER_PATH: Final = Path("python/raos/adapters/recorded_kpi_input.py")
TEST_PATHS: Final = (
    Path("tests/st1205/conftest.py"),
    Path("tests/st1205/test_contract.py"),
    Path("tests/st1205/test_calculation.py"),
    Path("tests/st1205/test_adapter_job.py"),
    Path("tests/st1205/test_negative_cases.py"),
    Path("tests/st1205/test_generation.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    README_PATH,
    GENERATOR_PATH,
    DOMAIN_PATH,
    PORT_PATH,
    APPLICATION_PATH,
    ADAPTER_PATH,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
KPI_CATALOG_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_kpi_catalog_v1.0.yaml"
)
ANALYTICS_DESIGN_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md"
)
ATTRIBUTION_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml"
)
INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)

EXPECTED_CONTRACT_SHA256: Final = (
    "bfc6ca7722e8cafdaee558881227531e8e74e3630f3cc13455f2e3e05ff2137f"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
GENERATION_COMMAND: Final = (
    "uv run --frozen --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st1205_kpi_read_model_reference_plan.py"
)

AUTHORITY_HASHES: Final = {
    STORY_PATH: "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    KPI_CATALOG_PATH: "f1cad721ade082f588461ff58c415fa21786e30b85c8281e651476514e2560a2",
    ANALYTICS_DESIGN_PATH: "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460",
    ATTRIBUTION_PATH: "29624996381ff0709c6499edcdca1109eb713ce56ad8b981df02153e11fc8b0c",
    INTEGRATION_PATH: "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
}
PREDECESSOR_HASHES: Final = {
    Path(
        "changes/st-1201/README.md"
    ): "f7264bda2e0e6c4fcfbd6d7050552170974f85ae014106d10ad36e03b94b2e09",
    Path(
        "python/raos/domain/analytics/event_collector.py"
    ): "e7350bac934fc3d190d9c041915a7ea708092519e4ddccb2c70e0c850bde50ff",
    Path(
        "changes/st-1203/README.md"
    ): "c333b3400b8f0f13ce18be7e04d43345caa812b4d818dae8222cb8b498099c3e",
    Path(
        "changes/st-1203/manifest.json"
    ): "d9f40d3fa26bdaeea2d84fb9f28550a84981edeef8a93aa6e1e44494a0de441f",
    Path(
        "python/raos/domain/analytics/search_console.py"
    ): "e49396e6dfac336b05488ae4ba80100c106fc4bf64c2ed476d16f459c16759ce",
    Path(
        "changes/st-1204/RUNTIME-SLICE-v1.md"
    ): "6d8b61dab7c296f6156f2ed249cd5498a23d82427f139fda614a7f1272a57aa7",
    Path(
        "changes/st-1204/generated/manifest.json"
    ): "80ee0253d5a7d0a051932bee8a8916fddf16c7ace8580081a1331ffa56d65924",
    Path(
        "python/raos/domain/analytics/ga4.py"
    ): "785dd16788fffabd5ab6c05c6f43f535bc6521630a246c93a54d23d257de124f",
}


class KpiReadModelBuildError(RuntimeError):
    """Stable, sanitized owner-generator failure."""


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise KpiReadModelBuildError(f"ST-1205 build failed: {code} field={field}")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        observed = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if type(observed) is not bytes:
        _fail("FILE_TYPE_MISMATCH", field)
    content = observed
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_json(root / relative), field)


def _find_story(stories: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        _mapping(item, "authority.story")
        for item in _list(stories.get("stories"), "authority.story")
        if type(item) is dict and item.get("id") == "ST-1205"
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", "authority.story")
    return matches[0]


def _validate_hashes(root: Path) -> None:
    if _sha256(_read(root, CONTRACT_PATH, "contract")) != EXPECTED_CONTRACT_SHA256:
        _fail("SOURCE_HASH_DRIFT", "contract")
    for relative, digest in (*AUTHORITY_HASHES.items(), *PREDECESSOR_HASHES.items()):
        if _sha256(_read(root, relative, "bound_source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "bound_source")
    fixture = _read(root, FIXTURE_PATH, "recorded_fixture")
    if (
        len(fixture) != COMPLETE_FIXTURE_BYTES
        or _sha256(fixture) != COMPLETE_FIXTURE_SHA256
    ):
        _fail("SOURCE_HASH_DRIFT", "recorded_fixture")


def _validate_story(root: Path) -> None:
    story = _find_story(_load_yaml(root, STORY_PATH, "authority.story"))
    expected = {
        "id": "ST-1205",
        "epic_id": "EPIC-12",
        "title": "KPI read models",
        "objective": "30 KPIを定義Version付きで計算",
        "depends_on": ["ST-1201", "ST-1203", "ST-1204"],
        "requirement_ids": ["FR-013", "FR-015"],
        "design_refs": [],
        "deliverables": ["SQL/jobs/read models"],
        "acceptance_criteria": ["fixture formulas reproduce"],
        "test_suites": ["TST-030"],
        "priority": "P0",
        "mvp": True,
        "size": "L",
        "open_decisions": [],
        "one_pr_preferred": False,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }
    if story != expected or tuple(story) != tuple(expected):
        _fail("CANONICAL_SEMANTIC_DRIFT", "authority.story")


def _validate_catalog(root: Path) -> list[Mapping[str, Any]]:
    catalog = _load_yaml(root, KPI_CATALOG_PATH, "authority.kpi_catalog")
    if tuple(catalog) != ("document", "kpis") or catalog["document"] != {
        "id": "RAOS-ANALYTICS-KPI-001",
        "version": "1.0",
    }:
        _fail("CANONICAL_SCHEMA_DRIFT", "authority.kpi_catalog")
    rows = [
        _mapping(item, "authority.kpi_catalog.row")
        for item in _list(catalog["kpis"], "authority.kpi_catalog.kpis")
    ]
    if len(rows) != 30 or tuple(row.get("id") for row in rows) != KPI_IDS:
        _fail("CANONICAL_SEMANTIC_DRIFT", "authority.kpi_catalog.order")
    for row, definition in zip(rows, KPI_DEFINITIONS, strict=True):
        if (
            row.get("id") != definition.kpi_id
            or row.get("name") != definition.name
            or row.get("formula") != definition.canonical_formula
            or row.get("cadence") != definition.time_grain
            or row.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("runtime_verification") != "NOT_EXECUTED"
        ):
            _fail("RUNTIME_DEFINITION_DRIFT", "authority.kpi_catalog.row")
    return rows


def _validate_contract(contract: Mapping[str, Any], root: Path) -> None:
    expected_keys = (
        "document",
        "authority",
        "predecessors",
        "input_contract",
        "definition_contract",
        "availability_contract",
        "read_model_contract",
        "learning_contract",
        "recorded_fixture_contract",
        "execution_boundary",
        "debt",
    )
    if tuple(contract) != expected_keys:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    document = _mapping(contract["document"], "document")
    if document != {
        "schema_version": "2.0.0",
        "story_id": "ST-1205",
        "classification": "MAXIMUM_SAFE_LOCAL_EXECUTABLE_RECORDED_KPI_READ_MODEL_V2",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "local_formula_engine": True,
        "local_read_model": True,
        "recorded_synthetic_only": True,
        "non_attesting": True,
        "formal_validation": "NOT_EXECUTED",
        "production_eligible": False,
        "approval": None,
        "canonical_status": "UNCHANGED",
    }:
        _fail("CONTRACT_SEMANTIC_DRIFT", "document")
    inputs = _mapping(contract["input_contract"], "input_contract")
    definitions = _mapping(contract["definition_contract"], "definition_contract")
    availability = _mapping(contract["availability_contract"], "availability_contract")
    learning = _mapping(contract["learning_contract"], "learning_contract")
    recorded = _mapping(
        contract["recorded_fixture_contract"], "recorded_fixture_contract"
    )
    execution = _mapping(contract["execution_boundary"], "execution_boundary")
    if (
        inputs.get("program_id") != RAKUTEN_BLOG_PROGRAM
        or inputs.get("numeric_type")
        != "decimal.Decimal from canonical decimal strings only"
        or inputs.get("float_allowed") is not False
        or inputs.get("missing_allowed_as_zero") is not False
        or inputs.get("live_provider_rows") is not False
        or definitions.get("definition_version") != KPI_DEFINITION_VERSION
        or definitions.get("calculation_version") != KPI_CALCULATION_VERSION
        or definitions.get("canonical_definition_count") != 30
        or definitions.get("calculation_count") != 30
        or definitions.get("rounding") != "ROUND_HALF_EVEN"
        or definitions.get("zero_denominator") != "UNAVAILABLE"
        or availability.get("unavailable_value") is not None
        or availability.get("unavailable_is_zero") is not False
        or learning.get("same_period_required") is not True
        or learning.get("same_program_required") is not True
        or learning.get("verified_attribution_required") is not True
        or learning.get("modifies_recommendation_order") is not False
        or recorded.get("sha256") != COMPLETE_FIXTURE_SHA256
        or recorded.get("bytes") != COMPLETE_FIXTURE_BYTES
        or recorded.get("normalized_input_sha256") != COMPLETE_RECORDED_INPUT_SHA256
        or execution.get("provider") != "NOT_EXECUTED"
        or execution.get("network") != "NOT_EXECUTED"
        or execution.get("public_projection") != "NOT_EXECUTED"
        or execution.get("recommendation_input") != "DISABLED"
        or execution.get("production") != "NOT_EXECUTED"
        or execution.get("formal_TST-030") != "NOT_EXECUTED"
        or execution.get("story_acceptance") is not False
    ):
        _fail("CONTRACT_SEMANTIC_DRIFT", "safety_boundary")
    _validate_hashes(root)
    _validate_story(root)


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    contract = _load_yaml(root, CONTRACT_PATH, "contract")
    _validate_contract(contract, root)
    return contract


def _input_document(spec: InputSpec) -> dict[str, object]:
    return {
        "metric_key": spec.metric_key,
        "source": spec.source.value,
        "role": spec.role.value,
        "attribution_requirement": spec.attribution_requirement.value,
        "allow_negative": spec.allow_negative,
    }


def _definition_document(
    definition: KpiDefinition, canonical: Mapping[str, Any]
) -> dict[str, object]:
    return {
        "id": definition.kpi_id,
        "name": definition.name,
        "canonical_formula": definition.canonical_formula,
        "canonical_domain": canonical["domain"],
        "canonical_interpretation": canonical["interpretation"],
        "formula_kind": definition.formula_kind.value,
        "typed_sources_and_roles": [
            _input_document(item) for item in definition.inputs
        ],
        "result_unit": definition.unit.value,
        "decimal_quantization": str(definition.quantize),
        "time_grain": definition.time_grain,
        "cohort": definition.cohort,
        "included_traffic": list(definition.included_traffic),
        "excluded_traffic": list(definition.excluded_traffic),
        "attribution_display": definition.attribution_display,
        "rounding": definition.rounding,
        "zero_semantics": definition.zero_semantics,
        "division_by_zero": definition.division_by_zero,
        "owner": definition.owner,
        "decision_use": definition.decision_use,
        "definition_version": KPI_DEFINITION_VERSION,
    }


def _recorded_reproduction(root: Path) -> dict[str, object]:
    fixture_bytes = _read(root, FIXTURE_PATH, "recorded_fixture")
    fixture = _load_json(root, FIXTURE_PATH, "recorded_fixture")
    period = _mapping(fixture["period"], "recorded_fixture.period")
    command = KpiCalculationCommand(
        recording_id="complete",
        fixture_digest=Sha256Digest(COMPLETE_FIXTURE_SHA256),
        fixture_length=FixtureByteLength(COMPLETE_FIXTURE_BYTES),
        expected_input_digest=Sha256Digest(COMPLETE_RECORDED_INPUT_SHA256),
        context=CalculationContext(
            MeasurementPeriod(
                date.fromisoformat(cast(str, period["start_date"])),
                date.fromisoformat(cast(str, period["end_date"])),
            ),
            ProgramId(cast(str, fixture["program_id"])),
            AttributionBasis(cast(str, fixture["selected_attribution_basis"])),
        ),
    )
    snapshot = RecordedKpiCalculationJob(
        exchange=RecordedKpiInputAdapter(fixture_bytes)
    ).calculate(command)
    expected = _list(fixture["expected_results"], "recorded_fixture.expected_results")
    expected_learning = _list(
        fixture["expected_learning_results"],
        "recorded_fixture.expected_learning_results",
    )
    actual = [
        {"kpi_id": row.kpi_id, "value": None if row.value is None else str(row.value)}
        for row in snapshot.rows
    ]
    actual_learning = [
        {
            "metric_id": row.metric_id,
            "value": None if row.value is None else str(row.value),
        }
        for row in snapshot.learning_rows
    ]
    if (
        any(row.availability is not KpiAvailability.AVAILABLE for row in snapshot.rows)
        or actual != expected
        or actual_learning != expected_learning
    ):
        _fail("FIXTURE_REPRODUCTION_FAILED", "recorded_fixture")
    return {
        "recording_id": "complete",
        "fixture_sha256": COMPLETE_FIXTURE_SHA256,
        "input_sha256": snapshot.input_digest.value,
        "period": {
            "start_date": snapshot.context.period.start_date.isoformat(),
            "end_date": snapshot.context.period.end_date.isoformat(),
        },
        "program_id": snapshot.context.program_id.value,
        "attribution_basis": snapshot.context.selected_attribution_basis.value,
        "available_kpis": 30,
        "expected_kpis_reproduced": 30,
        "expected_learning_metrics_reproduced": 5,
        "results": actual,
        "learning_results": actual_learning,
        "execution": snapshot.execution.value,
        "read_model": snapshot.read_model.value,
        "persistence": snapshot.persistence.value,
        "provider": snapshot.provider.value,
        "network": snapshot.network.value,
        "public_projection": snapshot.public_projection.value,
        "recommendation_input": snapshot.recommendation_input.value,
        "formal_TST-030": snapshot.formal_tst_030.value,
        "decision": snapshot.decision.value,
    }


def reference_plan(root: Path = REPO_ROOT) -> dict[str, object]:
    contract = load_contract(root)
    canonical_rows = _validate_catalog(root)
    return {
        "document": contract["document"],
        "authority": contract["authority"],
        "definition_version": KPI_DEFINITION_VERSION,
        "calculation_version": KPI_CALCULATION_VERSION,
        "definition_count": 30,
        "definitions": [
            _definition_document(definition, canonical)
            for definition, canonical in zip(
                KPI_DEFINITIONS, canonical_rows, strict=True
            )
        ],
        "input_contract": contract["input_contract"],
        "availability_contract": contract["availability_contract"],
        "read_model_contract": contract["read_model_contract"],
        "learning_contract": contract["learning_contract"],
        "recorded_reproduction": _recorded_reproduction(root),
        "execution_boundary": contract["execution_boundary"],
        "debt": contract["debt"],
    }


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "source_artifact")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    contract = load_contract(root)
    legacy_contract = _read(root, LEGACY_CONTRACT_PATH, "legacy_reference")
    legacy_reference = _read(root, LEGACY_REFERENCE_PATH, "legacy_reference")
    manifest = {
        "document": {
            "id": "RAOS-ST1205-KPI-READ-MODEL-V2-MANIFEST-001",
            "version": "2.0.0",
            "story_id": "ST-1205",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "authority": contract["authority"],
            "predecessors": contract["predecessors"],
            "legacy_reference": {
                "classification": "SUPERSEDED_NON_EXECUTABLE_REFERENCE_PRESERVED",
                "contract_uri": f"repo://{LEGACY_CONTRACT_PATH.as_posix()}",
                "contract_sha256": _sha256(legacy_contract),
                "projection_uri": f"repo://{LEGACY_REFERENCE_PATH.as_posix()}",
                "projection_sha256": _sha256(legacy_reference),
            },
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact_row(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "local_completion": {
            "local_code_status": "LOCAL_CODE_COMPLETE",
            "definitions": 30,
            "calculations": 30,
            "recorded_fixture_reproductions": 30,
            "learning_metric_reproductions": 5,
            "DEBT-W2-054": "CLOSED",
            "DEBT-W2-062": "CLOSED",
            "formal_TST-030": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
            "database": "NOT_EXECUTED",
            "public_projection": "NOT_EXECUTED",
            "recommendation_input": "DISABLED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    reference_bytes = _json_bytes(reference_plan(root))
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
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            _fail("GENERATED_OUTPUT_MODE_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative in GENERATED_PATHS:
        base._atomic_write(root, relative, outputs[relative])  # noqa: SLF001


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
    except (KpiReadModelBuildError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("ST-1205 build failed: UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    print("ST-1205 KPI V2 checked" if args.check else "ST-1205 KPI V2 generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
