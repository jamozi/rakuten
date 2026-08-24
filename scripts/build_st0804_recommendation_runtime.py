#!/usr/bin/env python3
"""Generate the deterministic ST-0804 V2 fixture and runtime manifest."""

from __future__ import annotations

import argparse
from dataclasses import replace
from decimal import Decimal
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

from raos.adapters.recorded_comparison_validation import (  # noqa: E402
    load_recorded_comparison_fixture,
)
from raos.adapters.recorded_recommendation import (  # noqa: E402
    load_recorded_recommendation_fixture,
)
from raos.domain.editorial.comparison_validation_v2 import (  # noqa: E402
    ComparisonCellStatus,
    ComparisonRecordReceipt,
    ComparisonValidationStatus,
    canonical_decimal,
    validate_comparison_v2,
)
from raos.domain.editorial.recommendation_v2 import (  # noqa: E402
    ArticleRecommendationContextV2,
    ConflictState,
    DecisionContextId,
    DimensionAssessmentV2,
    HardConstraintState,
    MethodologyBindingV2,
    NormalizationBasis,
    RecommendationContractBinding,
    RecommendationDimensionV2,
    RecommendationEnvelopeV2,
    StalenessState,
    assessment_set_sha256,
    axis_definition_sha256,
    comparison_receipt_sha256,
    decision_context_sha256,
    dimension_set_sha256,
    evaluate_recommendations_v2,
    normalization_decision_sha256,
    normalization_input_sha256,
    recommendation_input_sha256,
)
from raos.domain.shared.persistence import Sha256Digest  # noqa: E402


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
EXPECTED_PYTEST_VERSION: Final = "9.1.1"
EXPECTED_PYDANTIC_VERSION: Final = "2.13.4"
EXPECTED_PYDANTIC_CORE_VERSION: Final = "2.46.4"

CONTRACT_PATH: Final = Path("changes/st-0804/contracts/recommendation-runtime.v2.yaml")
FIXTURE_PATH: Final = Path("changes/st-0804/generated/recommendation-pass.v2.json")
MANIFEST_PATH: Final = Path("changes/st-0804/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0804_recommendation_runtime.py")
UPSTREAM_FIXTURE_PATH: Final = Path(
    "changes/st-0803/generated/comparison-validation-pass.v2.json"
)
UPSTREAM_FIXTURE_SHA256: Final = (
    "21594b37e56f32f7b82ac51ab5a428c97b6875d4dea7660541b513515a31a25b"
)
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
SECURE_HELPER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)

CANONICAL_BINDINGS: Final = (
    (
        Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
)
DEPENDENCY_BINDINGS: Final = (
    (
        Path(
            "changes/st-0004/contracts/content/RAOS_06_recommendation_methodology_v0.1.yaml"
        ),
        "fb71ad7900c7f688f305e10256b49563281893408e54d8668aac02efa7e57862",
    ),
    (
        Path("changes/st-0803/contracts/comparison-validation-runtime.v2.yaml"),
        "ca198b81bf9a3886712efd660fa4b9700c4f24a67cd8a92f580e38ff135f591f",
    ),
    (
        Path("python/raos/domain/editorial/comparison_validation_v2.py"),
        "010f445797704e72a5c5cdaf2355e36ed9bf70f536dc1574fe23fb802e91d552",
    ),
    (
        Path("python/raos/adapters/recorded_comparison_validation.py"),
        "7771067b307e4e99c2a64a280a297aa91828f75260ddaafdff8d1028a42a4d8d",
    ),
    (
        Path("changes/st-0803/runtime-manifest.v2.yaml"),
        "2e4f5d02d12255f0e7b41b778cdb94dbc9b0c8093c27452a5a1ad10809781f7e",
    ),
    (SECURE_HELPER_PATH, SECURE_HELPER_SHA256),
)
RUNTIME_DEPENDENCY_PATHS: Final = (
    Path("python/raos/__init__.py"),
    Path("python/raos/adapters/__init__.py"),
    Path("python/raos/config/__init__.py"),
    Path("python/raos/config/runtime.py"),
    Path("python/raos/domain/catalog/ids.py"),
    Path("python/raos/domain/editorial/__init__.py"),
    Path("python/raos/domain/editorial/ids.py"),
    Path("python/raos/domain/evidence/ids.py"),
    Path("python/raos/domain/shared/__init__.py"),
    Path("python/raos/domain/shared/identity.py"),
    Path("python/raos/domain/shared/persistence.py"),
    Path("python/raos/ports/__init__.py"),
    Path("python/raos/ports/editorial/__init__.py"),
)
OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/editorial/recommendation.py"),
    Path("python/raos/domain/editorial/recommendation_v2.py"),
    Path("python/raos/ports/editorial/recommendation.py"),
    Path("python/raos/application/editorial/recommendation.py"),
    Path("python/raos/adapters/recorded_recommendation.py"),
    Path("changes/st-0804/README.md"),
    Path("changes/st-0804/HISTORICAL-DRIFT.md"),
    Path("changes/st-0804/completion/completion.v2.yaml"),
    Path("docs/execplans/ST-0804.md"),
    Path("docs/worklogs/ST-0804.md"),
    Path("tests/st0804_runtime/__init__.py"),
    Path("tests/st0804_runtime/conftest.py"),
    Path("tests/st0804_runtime/helpers.py"),
    Path("tests/st0804_runtime/test_domain.py"),
    Path("tests/st0804_runtime/test_application_adapter.py"),
    Path("tests/st0804_runtime/test_generation.py"),
    Path("tests/st0804_runtime/test_static_boundary.py"),
)
LOCKED_TOOLCHAIN_PATHS: Final = (Path("pyproject.toml"), Path("uv.lock"))
SOURCE_PATHS: Final = (
    *OWNED_SOURCE_PATHS,
    UPSTREAM_FIXTURE_PATH,
    *(path for path, _digest in CANONICAL_BINDINGS),
    *(path for path, _digest in DEPENDENCY_BINDINGS),
    *RUNTIME_DEPENDENCY_PATHS,
    *LOCKED_TOOLCHAIN_PATHS,
)
GENERATED_PATHS: Final = (FIXTURE_PATH, MANIFEST_PATH)
MAX_CONTRACT_BYTES: Final = 262_144
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024
TOP_LEVEL_KEYS: Final = (
    "schema_version",
    "story_id",
    "local_status",
    "classification",
    "runtime",
    "bindings",
    "comparison_boundary",
    "decision_context",
    "dimension_defaults",
    "fixture_scores",
    "fixture_states",
    "execution_boundary",
    "verification_boundary",
)


class RuntimeGenerationError(ValueError):
    __slots__ = ()

    def __init__(self, code: str) -> None:
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise RuntimeGenerationError(code) from None


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
    expected = (
        ("pytest", EXPECTED_PYTEST_VERSION),
        ("pydantic", EXPECTED_PYDANTIC_VERSION),
        ("pydantic-core", EXPECTED_PYDANTIC_CORE_VERSION),
    )
    for package, package_version in expected:
        try:
            observed = distribution_version(package)
        except PackageNotFoundError:
            _fail("GENERATION_TOOLCHAIN_DRIFT")
        if observed != package_version:
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
            or before.st_dev != opened.st_dev
            or before.st_ino != opened.st_ino
            or opened.st_nlink != 1
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
    for relative, expected in (*CANONICAL_BINDINGS, *DEPENDENCY_BINDINGS):
        if _sha(_safe_path(root, relative)) != expected:
            _fail("SOURCE_HASH_DRIFT")
    if _sha(_safe_path(root, UPSTREAM_FIXTURE_PATH)) != UPSTREAM_FIXTURE_SHA256:
        _fail("UPSTREAM_FIXTURE_HASH_DRIFT")


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    path = _safe_path(root, CONTRACT_PATH)
    payload = _read_regular(path, maximum=MAX_CONTRACT_BYTES)
    if not payload:
        _fail("CONTRACT_SIZE_INVALID")
    try:
        tokens = tuple(yaml.scan(payload))
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in tokens
        ):
            _fail("YAML_FEATURE_REJECTED")
        loaded = yaml.load(payload, Loader=_UniqueLoader)
    except RuntimeGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    if type(loaded) is not dict or tuple(loaded) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SHAPE_INVALID")
    result = cast(dict[str, Any], loaded)
    if (
        type(result["schema_version"]) is not int
        or result["schema_version"] != 2
        or result["story_id"] != "ST-0804"
        or result["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
        or result["classification"]
        != "LOCAL_EXECUTABLE_RECORDED_RECOMMENDATION_RUNTIME_V2"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    if result["runtime"] != {
        "executable": True,
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "repository_write": False,
        "approval_authorized": False,
        "override_supported": False,
        "recommendation_authorized": False,
        "ranking_authorized": False,
        "publication_authorized": False,
        "activation_authorized": False,
        "production_eligible": False,
    }:
        _fail("CONTRACT_RUNTIME_INVALID")
    current = RecommendationContractBinding.current()
    if result["bindings"] != {
        "methodology_id": MethodologyBindingV2.current().methodology_id,
        "methodology_version": MethodologyBindingV2.current().methodology_version,
        "methodology_source_sha256": current.methodology_source_sha256.value,
        "st0803_contract_sha256": current.st0803_contract_sha256.value,
        "st0803_domain_sha256": current.st0803_domain_sha256.value,
        "st0803_recorded_fixture_sha256": (
            current.st0803_recorded_fixture_sha256.value
        ),
        "st0803_runtime_manifest_sha256": (
            current.st0803_runtime_manifest_sha256.value
        ),
        "secure_publication_helper_sha256": SECURE_HELPER_SHA256,
    }:
        _fail("CONTRACT_BINDING_INVALID")
    if result["comparison_boundary"] != {
        "request_source": UPSTREAM_FIXTURE_PATH.as_posix(),
        "require_local_validated_report": True,
        "require_exact_report_bytes": True,
        "require_exact_record_receipt": True,
        "receipt_sequence": 1,
        "prior_st0605_pass_required": False,
    }:
        _fail("CONTRACT_COMPARISON_BOUNDARY_INVALID")
    if result["execution_boundary"] != {
        "repository_read": "GENERATED_RECORDED_FIXTURE_ONLY",
        "result_append": "PROCESS_LOCAL_METADATA_ONLY",
        "network": "FORBIDDEN",
        "credential": "FORBIDDEN",
        "provider": "FORBIDDEN",
        "approval": "FORBIDDEN",
        "override": "FORBIDDEN",
        "article_mutation": "FORBIDDEN",
        "recommendation_mutation": "FORBIDDEN",
        "ranking_mutation": "FORBIDDEN",
        "publication_snapshot_mutation": "FORBIDDEN",
    }:
        _fail("CONTRACT_EXECUTION_BOUNDARY_INVALID")
    if result["verification_boundary"] != {
        "TST-007": "NOT_EXECUTED",
        "TST-020": "NOT_EXECUTED",
        "formal_validation": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }:
        _fail("CONTRACT_VERIFICATION_BOUNDARY_INVALID")
    _require_hashes(root)
    return result


def _rule_material(rule: object) -> dict[str, object]:
    typed = cast(Any, rule)
    return {
        "rule_id": typed.rule_id,
        "version": typed.version,
        "source_sha256": typed.source_sha256.value,
    }


def _methodology_material(value: MethodologyBindingV2) -> dict[str, object]:
    return {
        "methodology_id": value.methodology_id,
        "methodology_version": value.methodology_version,
        "source_sha256": value.source_sha256.value,
        "hard_constraint_rule": _rule_material(value.hard_constraint_rule),
        "weighting_rule": _rule_material(value.weighting_rule),
        "normalization_rule": _rule_material(value.normalization_rule),
        "coverage_rule": _rule_material(value.coverage_rule),
        "conflict_penalty_rule": _rule_material(value.conflict_penalty_rule),
        "staleness_penalty_rule": _rule_material(value.staleness_penalty_rule),
        "tie_rule": _rule_material(value.tie_rule),
    }


def _context_material(value: ArticleRecommendationContextV2) -> dict[str, object]:
    return {
        "article_id": str(value.article_id.value),
        "article_version_id": str(value.article_version_id.value),
        "article_binding_sha256": value.article_binding_sha256.value,
        "decision_context_id": str(value.decision_context_id.value),
        "decision_context_version_no": value.decision_context_version_no,
        "target_reader_code": value.target_reader_code,
        "use_case_code": value.use_case_code,
        "budget_context_code": value.budget_context_code,
        "context_source_sha256": value.context_source_sha256.value,
        "binding_sha256": value.binding_sha256.value,
    }


def _dimension_material(value: RecommendationDimensionV2) -> dict[str, object]:
    return {
        "axis_id": str(value.axis_id.value),
        "axis_definition_sha256": value.axis_definition_sha256.value,
        "weight": canonical_decimal(value.weight),
        "critical": value.critical,
        "hard_constraint": value.hard_constraint,
        "normalization_basis": value.normalization_basis.value,
        "normalization_rule": _rule_material(value.normalization_rule),
    }


def _assessment_material(value: DimensionAssessmentV2) -> dict[str, object]:
    return {
        "product_id": str(value.product_id.value),
        "axis_id": str(value.axis_id.value),
        "cell_status": value.cell_status.value,
        "fact_ids": [str(item.value) for item in value.fact_ids],
        "normalization_basis": value.normalization_basis.value,
        "normalized_score": (
            None
            if value.normalized_score is None
            else canonical_decimal(value.normalized_score)
        ),
        "hard_constraint_state": value.hard_constraint_state.value,
        "conflict_state": value.conflict_state.value,
        "conflict_penalty": canonical_decimal(value.conflict_penalty),
        "staleness_state": value.staleness_state.value,
        "staleness_penalty": canonical_decimal(value.staleness_penalty),
        "normalization_input_sha256": value.normalization_input_sha256.value,
        "normalization_decision_sha256": value.normalization_decision_sha256.value,
    }


def _fixture_bytes(root: Path, contract: dict[str, Any]) -> bytes:
    upstream_payload = _read_regular(
        _safe_path(root, UPSTREAM_FIXTURE_PATH), maximum=MAX_GENERATED_BYTES
    )
    try:
        upstream_material = json.loads(upstream_payload)
    except Exception:
        _fail("UPSTREAM_FIXTURE_PARSE_FAILED")
    comparison = load_recorded_comparison_fixture(upstream_payload)
    comparison_report = validate_comparison_v2(comparison)
    comparison_report.require_valid()
    if (
        comparison_report.status is not ComparisonValidationStatus.LOCAL_VALIDATED
        or comparison_report.findings
    ):
        _fail("UPSTREAM_COMPARISON_NOT_LOCAL_VALIDATED")
    comparison_receipt = ComparisonRecordReceipt(
        sequence=cast(dict[str, Any], contract["comparison_boundary"])[
            "receipt_sequence"
        ],
        report_sha256=comparison_report.report_sha256,
    )
    comparison_receipt.require_valid()

    context_seed = cast(dict[str, Any], contract["decision_context"])
    context = ArticleRecommendationContextV2(
        article_id=comparison.comparison.article.article_id,
        article_version_id=comparison.comparison.article.article_version_id,
        article_binding_sha256=comparison.comparison.article.binding_sha256,
        decision_context_id=DecisionContextId(
            UUID(context_seed["decision_context_id"])
        ),
        decision_context_version_no=context_seed["decision_context_version_no"],
        target_reader_code=context_seed["target_reader_code"],
        use_case_code=context_seed["use_case_code"],
        budget_context_code=context_seed["budget_context_code"],
        context_source_sha256=Sha256Digest(context_seed["context_source_sha256"]),
        binding_sha256=Sha256Digest("0" * 64),
    )
    context = replace(context, binding_sha256=decision_context_sha256(context))

    methodology = MethodologyBindingV2.current()
    dimension_seed = cast(dict[str, Any], contract["dimension_defaults"])
    dimensions = tuple(
        RecommendationDimensionV2(
            axis_id=axis.axis_id,
            axis_definition_sha256=axis_definition_sha256(axis),
            weight=Decimal(dimension_seed["weight"]),
            critical=dimension_seed["critical"],
            hard_constraint=dimension_seed["hard_constraint"],
            normalization_basis=NormalizationBasis(
                dimension_seed["normalization_basis"]
            ),
            normalization_rule=methodology.normalization_rule,
        )
        for axis in comparison.comparison.axis_catalog.axes
    )
    dimension_by_axis = {item.axis_id: item for item in dimensions}
    score_seed = cast(dict[str, str], contract["fixture_scores"])
    state_seed = cast(dict[str, Any], contract["fixture_states"])
    assessments: list[DimensionAssessmentV2] = []
    for cell in comparison.comparison.cells:
        if cell.status is not ComparisonCellStatus.VALID:
            _fail("FIXTURE_CELL_NOT_VALID")
        dimension = dimension_by_axis[cell.axis_id]
        try:
            score = Decimal(score_seed[str(cell.product_id.value)])
        except Exception:
            _fail("FIXTURE_SCORE_MISSING")
        input_sha256 = normalization_input_sha256(
            comparison=comparison.comparison,
            context=context,
            methodology=methodology,
            dimension=dimension,
            cell=cell,
            basis=dimension.normalization_basis,
        )
        decision_sha256 = normalization_decision_sha256(
            input_sha256=input_sha256,
            basis=dimension.normalization_basis,
            normalized_score=score,
        )
        assessments.append(
            DimensionAssessmentV2(
                product_id=cell.product_id,
                axis_id=cell.axis_id,
                cell_status=cell.status,
                fact_ids=cell.fact_ids,
                normalization_basis=dimension.normalization_basis,
                normalized_score=score,
                hard_constraint_state=HardConstraintState(
                    state_seed["hard_constraint_state"]
                ),
                conflict_state=ConflictState(state_seed["conflict_state"]),
                conflict_penalty=Decimal(state_seed["conflict_penalty"]),
                staleness_state=StalenessState(state_seed["staleness_state"]),
                staleness_penalty=Decimal(state_seed["staleness_penalty"]),
                normalization_input_sha256=input_sha256,
                normalization_decision_sha256=decision_sha256,
            )
        )
    assessments_tuple = tuple(assessments)
    envelope = RecommendationEnvelopeV2(
        contract=RecommendationContractBinding.current(),
        comparison=comparison,
        comparison_report=comparison_report,
        comparison_receipt=comparison_receipt,
        context=context,
        methodology=methodology,
        dimensions=dimensions,
        assessments=assessments_tuple,
        dimension_set_sha256=dimension_set_sha256(dimensions),
        assessment_set_sha256=assessment_set_sha256(assessments_tuple),
        recommendation_input_sha256=Sha256Digest("0" * 64),
    )
    envelope = replace(
        envelope,
        recommendation_input_sha256=recommendation_input_sha256(envelope),
    )
    report = evaluate_recommendations_v2(envelope)
    report.require_valid()
    if not report.locally_calculated or report.findings:
        _fail("FIXTURE_RECOMMENDATION_NOT_LOCAL_CALCULATED")
    comparison_report_material = json.loads(comparison_report.canonical_bytes())
    root_material = {
        "schema_version": 2,
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "contract": {
            "contract_id": envelope.contract.contract_id,
            "contract_version": envelope.contract.contract_version,
            "evaluator_version": envelope.contract.evaluator_version,
            "methodology_source_sha256": (
                envelope.contract.methodology_source_sha256.value
            ),
            "st0803_contract_sha256": envelope.contract.st0803_contract_sha256.value,
            "st0803_domain_sha256": envelope.contract.st0803_domain_sha256.value,
            "st0803_recorded_fixture_sha256": (
                envelope.contract.st0803_recorded_fixture_sha256.value
            ),
            "st0803_runtime_manifest_sha256": (
                envelope.contract.st0803_runtime_manifest_sha256.value
            ),
        },
        "comparison_request": upstream_material,
        "comparison_report": comparison_report_material,
        "comparison_record_receipt": {
            "sequence": comparison_receipt.sequence,
            "report_sha256": comparison_receipt.report_sha256.value,
            "publication_authorized": False,
        },
        "context": _context_material(context),
        "methodology": _methodology_material(methodology),
        "dimensions": [_dimension_material(item) for item in dimensions],
        "assessments": [_assessment_material(item) for item in assessments_tuple],
        "declared_hashes": {
            "comparison_request_sha256": (
                comparison.comparison.evaluation_input_sha256.value
            ),
            "comparison_report_sha256": comparison_report.report_sha256.value,
            "comparison_receipt_sha256": comparison_receipt_sha256(
                comparison_receipt
            ).value,
            "decision_context_sha256": context.binding_sha256.value,
            "dimension_set_sha256": envelope.dimension_set_sha256.value,
            "assessment_set_sha256": envelope.assessment_set_sha256.value,
            "recommendation_input_sha256": envelope.recommendation_input_sha256.value,
        },
    }
    payload = (
        json.dumps(
            root_material,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("ascii")
    loaded = load_recorded_recommendation_fixture(payload)
    observed = evaluate_recommendations_v2(loaded)
    if observed.canonical_bytes() != report.canonical_bytes():
        _fail("RECORDED_FIXTURE_ROUND_TRIP_INVALID")
    return payload


def _artifact(root: Path, relative: Path, *, role: str) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, relative))
    media_type = {
        ".json": "application/json",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
        ".py": "text/x-python",
        ".md": "text/markdown",
        ".toml": "application/toml",
        ".lock": "application/octet-stream",
    }.get(relative.suffix.lower(), "application/octet-stream")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "artifact_role": role,
        "media_type": media_type,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _manifest_bytes(root: Path, fixture: bytes) -> bytes:
    canonical_paths = {path for path, _digest in CANONICAL_BINDINGS}
    dependency_paths = {path for path, _digest in DEPENDENCY_BINDINGS}
    sources = [
        _artifact(
            root,
            path,
            role=(
                "OWNER_SOURCE"
                if path in OWNED_SOURCE_PATHS
                else "UPSTREAM_RECORDED_FIXTURE"
                if path == UPSTREAM_FIXTURE_PATH
                else "CANONICAL_INPUT"
                if path in canonical_paths
                else "DEPENDENCY_CONTRACT"
                if path in dependency_paths
                else "RUNTIME_DEPENDENCY"
                if path in RUNTIME_DEPENDENCY_PATHS
                else "LOCKED_TOOLCHAIN"
            ),
        )
        for path in SOURCE_PATHS
    ]
    document = {
        "schema_version": 2,
        "story_id": "ST-0804",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_EXECUTABLE_RECORDED_RECOMMENDATION_RUNTIME_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "artifact_role": "RECORDED_SYNTHETIC_FIXTURE",
                "media_type": "application/json",
                "bytes": len(fixture),
                "sha256": hashlib.sha256(fixture).hexdigest(),
            }
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": ".venv/bin/python scripts/build_st0804_recommendation_runtime.py",
            "check_command": (
                ".venv/bin/python scripts/build_st0804_recommendation_runtime.py --check"
            ),
            "transaction": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "existing_destination_commit": "RENAMEAT2_EXCHANGE_WITH_REVERSE_VERIFY",
            "missing_destination_commit": "HARDLINK_NO_CLOBBER",
            "foreign_target_policy": "PRESERVE_AND_FAIL_CLOSED",
            "symlink_policy": "REJECT",
            "hardlink_policy": "REJECT",
            "source_identity": "LSTAT_FSTAT_DEVICE_INODE_SIZE_MTIME",
            "secure_publication_helper_sha256": SECURE_HELPER_SHA256,
            "toolchain": {
                "python_implementation": "CPython",
                "python_version": ".".join(
                    str(part) for part in EXPECTED_PYTHON_VERSION
                ),
                "pyyaml_version": EXPECTED_PYYAML_VERSION,
                "pytest_version": EXPECTED_PYTEST_VERSION,
                "pydantic_version": EXPECTED_PYDANTIC_VERSION,
                "pydantic_core_version": EXPECTED_PYDANTIC_CORE_VERSION,
            },
        },
        "authority": {
            "approval_authorized": False,
            "override_supported": False,
            "publication_authorized": False,
            "recommendation_authorized": False,
            "ranking_authorized": False,
            "activation_authorized": False,
            "production_eligible": False,
            "formal_tst_007_status": "NOT_EXECUTED",
            "formal_tst_020_status": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def _replace_generated(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_generated_publication.publish_generated(
            artifacts,
            namespace="st0804",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    _validate_toolchain()
    contract = load_contract(root)
    fixture = _fixture_bytes(root, contract)
    expected = (
        (FIXTURE_PATH, fixture),
        (MANIFEST_PATH, _manifest_bytes(root, fixture)),
    )
    if check:
        for relative, payload in expected:
            destination = _safe_path(root, relative)
            if _read_regular(destination) != payload:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    _replace_generated(
        tuple((_safe_path(root, relative), payload) for relative, payload in expected)
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
        print("ST-0804 V2 runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0804 V2 runtime checked"
        if arguments.check
        else "ST-0804 V2 runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
