#!/usr/bin/env python3
"""Generate the deterministic ST-0803 V2 fixture and runtime manifest."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime, timezone
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

from raos.adapters.recorded_claim_evidence import (  # noqa: E402
    load_recorded_claim_evidence_fixture,
)
from raos.adapters.recorded_comparison_validation import (  # noqa: E402
    load_recorded_comparison_fixture,
)
from raos.domain.catalog.ids import CanonicalProductId  # noqa: E402
from raos.domain.editorial.comparison_validation_v2 import (  # noqa: E402
    ArticleComparisonBinding,
    AxisCatalogId,
    CandidateUniverse,
    CandidateUniverseId,
    ComparisonAxisCatalog,
    ComparisonAxisDataType,
    ComparisonAxisDefinition,
    ComparisonCell,
    ComparisonCellStatus,
    ComparisonContractBinding,
    ComparisonFactBinding,
    ComparisonProduct,
    ComparisonSnapshotV2,
    ComparisonValidationEnvelopeV2,
    ComparisonValidationStatus,
    TypedComparisonValue,
    article_binding_sha256,
    axis_catalog_sha256,
    candidate_universe_sha256,
    comparison_input_sha256,
    fact_set_sha256,
    temporal_scope_sha256,
    validate_comparison_v2,
)
from raos.domain.editorial.ids import (  # noqa: E402
    ArticleId,
    ArticleVersionId,
    ComparisonAxisId,
)
from raos.domain.evidence.claim_evidence import (  # noqa: E402
    CoverageFindingCode,
    CoverageStatus,
    ValidationAttestationKind,
    complete_claim_set_sha256,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)
from raos.domain.evidence.ids import FactId, SourcePacketVersionId  # noqa: E402
from raos.domain.shared.persistence import (  # noqa: E402
    AwareUtcDateTime,
    Sha256Digest,
)


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
EXPECTED_PYTEST_VERSION: Final = "9.1.1"
EXPECTED_PYDANTIC_VERSION: Final = "2.13.4"
EXPECTED_PYDANTIC_CORE_VERSION: Final = "2.46.4"

CONTRACT_PATH: Final = Path(
    "changes/st-0803/contracts/comparison-validation-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-0803/generated/comparison-validation-pass.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-0803/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0803_comparison_validation_runtime.py")
UPSTREAM_FIXTURE_PATH: Final = Path(
    "changes/st-0605/generated/claim-evidence-runtime-pass.v1.json"
)
UPSTREAM_FIXTURE_SHA256: Final = (
    "b805ee491f7388ab39d99bd61dbc0a29d3b1659a9a44b44ebdeb73063e8356a1"
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
            "contracts/raos-v0.4/contracts/content/RAOS_06_claim_evidence_policy_v0.1.yaml"
        ),
        "fbf2d0ad6e7821a0059f9ceeb53d57268031e2e42b4aad988af9a42378aec5ba",
    ),
    (
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_editorial_policy_catalog_v0.1.yaml"
        ),
        "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a",
    ),
    (
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_recommendation_methodology_v0.1.yaml"
        ),
        "fb71ad7900c7f688f305e10256b49563281893408e54d8668aac02efa7e57862",
    ),
    (
        Path(
            "changes/st-0005/evidence/artifacts/"
            "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d-"
            "RAOS_03_data_catalog_v0.1.yaml"
        ),
        "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d",
    ),
    (
        Path(
            "changes/st-0504/contracts/"
            "product-identity-human-review-reference-plan.v1.yaml"
        ),
        "f8113f69157fc2afce5c5fb40ff5188c55d7d88b30ae7162441a710a7d54d5ab",
    ),
    (
        Path("changes/st-0605/contracts/claim-evidence-runtime.v1.yaml"),
        "7d84f3a4883a226eff782e976aa72169646be67bf1fc798af5b1b65367d2c3cb",
    ),
    (
        Path("python/raos/domain/editorial/article_lifecycle.py"),
        "c44cb8c5d26f4862e7527bcb179c20f1f60d3a069d9ba67fad3b0109ef0c6edd",
    ),
    (
        Path(
            "contracts/raos-v0.4/contracts/content/schemas/blocks/"
            "comparison_table.schema.json"
        ),
        "6da40ea538bd467a759613e0dca62f2e822ac4a9609adb71959d8bb624037c89",
    ),
)
RUNTIME_DEPENDENCY_PATHS: Final = (
    Path("python/raos/__init__.py"),
    Path("python/raos/adapters/__init__.py"),
    Path("python/raos/adapters/recorded_claim_evidence.py"),
    Path("python/raos/config/__init__.py"),
    Path("python/raos/config/runtime.py"),
    Path("python/raos/domain/catalog/ids.py"),
    Path("python/raos/domain/editorial/__init__.py"),
    Path("python/raos/domain/editorial/ids.py"),
    Path("python/raos/domain/evidence/claim_evidence.py"),
    Path("python/raos/domain/evidence/enums.py"),
    Path("python/raos/domain/evidence/ids.py"),
    Path("python/raos/domain/shared/__init__.py"),
    Path("python/raos/domain/shared/identity.py"),
    Path("python/raos/domain/shared/json_values.py"),
    Path("python/raos/domain/shared/persistence.py"),
    Path("python/raos/ports/__init__.py"),
    Path("python/raos/ports/editorial/__init__.py"),
)
OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/editorial/comparison_validation.py"),
    Path("python/raos/domain/editorial/comparison_validation_v2.py"),
    Path("python/raos/ports/editorial/comparison_validation.py"),
    Path("python/raos/application/editorial/comparison_validation.py"),
    Path("python/raos/adapters/recorded_comparison_validation.py"),
    Path("changes/st-0803/README.md"),
    Path("changes/st-0803/HISTORICAL-DRIFT.md"),
    Path("changes/st-0803/completion/completion.v2.yaml"),
    Path("docs/execplans/ST-0803.md"),
    Path("docs/worklogs/ST-0803.md"),
    Path("docs/worklogs/RAOS-IMPLEMENTATION-DEBT.md"),
    Path("tests/st0803_runtime/__init__.py"),
    Path("tests/st0803_runtime/conftest.py"),
    Path("tests/st0803_runtime/test_domain.py"),
    Path("tests/st0803_runtime/test_application_adapter.py"),
    Path("tests/st0803_runtime/test_generation.py"),
    Path("tests/st0803_runtime/test_static_boundary.py"),
    Path("scripts/secure_generated_publication.py"),
)
LOCKED_TOOLCHAIN_PATHS: Final = (
    Path("pyproject.toml"),
    Path("uv.lock"),
)
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
    "classification",
    "runtime",
    "bindings",
    "receipt_boundary",
    "fixture_seed",
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
    for key_node, value_node in cast(list[tuple[yaml.Node, yaml.Node]], node.value):
        key = cast(
            object,
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                key_node, deep=deep
            ),
        )
        if key in result:
            _fail("DUPLICATE_YAML_KEY")
        result[key] = cast(
            object,
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                value_node, deep=deep
            ),
        )
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
        if (
            after.st_dev != opened.st_dev
            or after.st_ino != opened.st_ino
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
        ):
            _fail("SOURCE_CHANGED_DURING_READ")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _sha(path: Path) -> str:
    return hashlib.sha256(_read_regular(path)).hexdigest()


def _require_hashes(root: Path) -> None:
    for relative, expected in (*CANONICAL_BINDINGS, *DEPENDENCY_BINDINGS):
        path = _safe_path(root, relative)
        if _sha(path) != expected:
            _fail("SOURCE_HASH_DRIFT")
    upstream = _safe_path(root, UPSTREAM_FIXTURE_PATH)
    if _sha(upstream) != UPSTREAM_FIXTURE_SHA256:
        _fail("UPSTREAM_FIXTURE_HASH_DRIFT")


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    path = _safe_path(root, CONTRACT_PATH)
    payload = _read_regular(path, maximum=MAX_CONTRACT_BYTES)
    if not payload:
        _fail("CONTRACT_SIZE_INVALID")
    try:
        tokens = tuple(
            cast(
                Iterable[object],
                yaml.scan(payload),  # pyright: ignore[reportUnknownMemberType]
            )
        )
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in tokens
        ):
            _fail("YAML_FEATURE_REJECTED")
        loaded = cast(object, yaml.load(payload, Loader=_UniqueLoader))
    except RuntimeGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    if type(loaded) is not dict:
        _fail("CONTRACT_SHAPE_INVALID")
    result = cast(dict[str, Any], loaded)
    if tuple(result) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SHAPE_INVALID")
    if (
        type(result["schema_version"]) is not int
        or result["schema_version"] != 2
        or result["story_id"] != "ST-0803"
        or result["classification"]
        != "LOCAL_EXECUTABLE_RECORDED_COMPARISON_VALIDATION_RUNTIME_V2"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    if result["runtime"] != {
        "executable": True,
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "repository_write": False,
        "publication_authorized": False,
        "recommendation_authorized": False,
        "ranking_authorized": False,
        "production_eligible": False,
    }:
        _fail("CONTRACT_RUNTIME_INVALID")
    binding = cast(dict[str, object], result["bindings"])
    current = ComparisonContractBinding.current()
    if binding != {
        "comparison_schema_sha256": current.comparison_schema_sha256.value,
        "identity_contract_sha256": current.identity_contract_sha256.value,
        "claim_evidence_contract_sha256": current.claim_evidence_contract_sha256.value,
        "article_lifecycle_source_sha256": (
            current.article_lifecycle_source_sha256.value
        ),
    }:
        _fail("CONTRACT_BINDING_INVALID")
    owner, version, digest = validation_attestation_owner_binding(
        ValidationAttestationKind.COMPARISON
    )
    if result["receipt_boundary"] != {
        "required_kind": "COMPARISON",
        "owner_story_id": owner,
        "contract_version": version,
        "contract_sha256": digest.value,
        "origin": "RECORDED_SYNTHETIC_ONLY",
        "prior_st0605_pass_required": False,
        "preexisting_comparison_receipt_allowed": False,
    }:
        _fail("CONTRACT_RECEIPT_BOUNDARY_INVALID")
    if result["execution_boundary"] != {
        "repository_read": "GENERATED_RECORDED_FIXTURE_ONLY",
        "result_append": "PROCESS_LOCAL_METADATA_ONLY",
        "network": "FORBIDDEN",
        "credential": "FORBIDDEN",
        "provider": "FORBIDDEN",
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


def _as_instant(text: str) -> AwareUtcDateTime:
    return AwareUtcDateTime(
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    )


def _materialize_comparison(
    seed: dict[str, Any],
    complete_claim_sha256: str,
) -> tuple[ComparisonSnapshotV2, dict[str, object]]:
    products_seed = cast(list[dict[str, Any]], seed["products"])
    article = ArticleComparisonBinding(
        article_id=ArticleId(UUID(seed["article_id"])),
        article_version_id=ArticleVersionId(UUID(seed["article_version_id"])),
        article_version_no=cast(int, seed["article_version_no"]),
        article_body_sha256=Sha256Digest(seed["article_body_sha256"]),
        source_packet_version_id=SourcePacketVersionId(
            UUID(seed["source_packet_version_id"])
        ),
        source_packet_content_sha256=Sha256Digest(seed["source_packet_content_sha256"]),
        complete_claim_set_sha256=Sha256Digest(complete_claim_sha256),
        binding_sha256=Sha256Digest("0" * 64),
    )
    article = ArticleComparisonBinding(
        article_id=article.article_id,
        article_version_id=article.article_version_id,
        article_version_no=article.article_version_no,
        article_body_sha256=article.article_body_sha256,
        source_packet_version_id=article.source_packet_version_id,
        source_packet_content_sha256=article.source_packet_content_sha256,
        complete_claim_set_sha256=article.complete_claim_set_sha256,
        binding_sha256=article_binding_sha256(article),
    )
    products = tuple(
        ComparisonProduct(
            product_id=CanonicalProductId(UUID(row["product_id"])),
            variant_identity_sha256=Sha256Digest(row["variant_identity_sha256"]),
            subject_identity_sha256=Sha256Digest(row["subject_identity_sha256"]),
            inclusion_reason_code=row["inclusion_reason_code"],
        )
        for row in products_seed
    )
    universe = CandidateUniverse(
        universe_id=CandidateUniverseId(UUID(seed["universe_id"])),
        version_no=seed["universe_version_no"],
        products=products,
        candidate_universe_sha256=Sha256Digest("0" * 64),
    )
    universe = CandidateUniverse(
        universe_id=universe.universe_id,
        version_no=universe.version_no,
        products=universe.products,
        candidate_universe_sha256=candidate_universe_sha256(universe),
    )
    axis = ComparisonAxisDefinition(
        axis_id=ComparisonAxisId(UUID(seed["axis_id"])),
        axis_code=seed["axis_code"],
        label=seed["axis_label"],
        description=seed["axis_description"],
        data_type=ComparisonAxisDataType.DECIMAL,
        unit_family_code=seed["unit_family_code"],
        unit_code=seed["unit_code"],
        position=0,
        required=True,
    )
    catalog = ComparisonAxisCatalog(
        catalog_id=AxisCatalogId(UUID(seed["catalog_id"])),
        version_no=seed["catalog_version_no"],
        source_sha256=Sha256Digest(seed["catalog_source_sha256"]),
        axes=(axis,),
        axis_catalog_sha256=Sha256Digest("0" * 64),
    )
    catalog = ComparisonAxisCatalog(
        catalog_id=catalog.catalog_id,
        version_no=catalog.version_no,
        source_sha256=catalog.source_sha256,
        axes=catalog.axes,
        axis_catalog_sha256=axis_catalog_sha256(catalog),
    )
    facts = tuple(
        ComparisonFactBinding(
            fact_id=FactId(UUID(row["fact_id"])),
            fact_sha256=Sha256Digest(row["fact_sha256"]),
            product_id=CanonicalProductId(UUID(row["product_id"])),
            variant_identity_sha256=Sha256Digest(row["variant_identity_sha256"]),
            subject_identity_sha256=Sha256Digest(row["subject_identity_sha256"]),
            axis_id=axis.axis_id,
            value=TypedComparisonValue(
                data_type=ComparisonAxisDataType.DECIMAL,
                decimal_value=Decimal(row["value"]),
            ),
            unit_code=seed["unit_code"],
            observed_at=_as_instant(seed["observed_at"]),
            valid_from=_as_instant(seed["valid_from"]),
            valid_until=_as_instant(seed["valid_until"]),
        )
        for row in products_seed
    )
    cells = tuple(
        ComparisonCell(
            product_id=fact.product_id,
            axis_id=fact.axis_id,
            status=ComparisonCellStatus.VALID,
            value=fact.value,
            unit_code=fact.unit_code,
            fact_ids=(fact.fact_id,),
            reason_code=None,
            imputed=False,
        )
        for fact in facts
    )
    snapshot = ComparisonSnapshotV2(
        contract=ComparisonContractBinding.current(),
        article=article,
        evaluated_at=_as_instant(seed["evaluated_at"]),
        candidate_universe=universe,
        axis_catalog=catalog,
        facts=facts,
        cells=cells,
        show_unknown_values=True,
        fact_set_sha256=fact_set_sha256(facts),
        temporal_scope_sha256=temporal_scope_sha256(
            evaluated_at=_as_instant(seed["evaluated_at"]),
            facts=facts,
        ),
        evaluation_input_sha256=Sha256Digest("0" * 64),
    )
    snapshot = ComparisonSnapshotV2(
        contract=snapshot.contract,
        article=snapshot.article,
        evaluated_at=snapshot.evaluated_at,
        candidate_universe=snapshot.candidate_universe,
        axis_catalog=snapshot.axis_catalog,
        facts=snapshot.facts,
        cells=snapshot.cells,
        show_unknown_values=snapshot.show_unknown_values,
        fact_set_sha256=snapshot.fact_set_sha256,
        temporal_scope_sha256=snapshot.temporal_scope_sha256,
        evaluation_input_sha256=comparison_input_sha256(snapshot),
    )
    material: dict[str, object] = {
        "contract": {
            "contract_id": snapshot.contract.contract_id,
            "contract_version": snapshot.contract.contract_version,
            "evaluator_version": snapshot.contract.evaluator_version,
            "comparison_schema_sha256": snapshot.contract.comparison_schema_sha256.value,
            "identity_contract_sha256": snapshot.contract.identity_contract_sha256.value,
            "claim_evidence_contract_sha256": (
                snapshot.contract.claim_evidence_contract_sha256.value
            ),
            "article_lifecycle_source_sha256": (
                snapshot.contract.article_lifecycle_source_sha256.value
            ),
        },
        "article": {
            "article_id": str(article.article_id.value),
            "article_version_id": str(article.article_version_id.value),
            "article_version_no": article.article_version_no,
            "article_body_sha256": article.article_body_sha256.value,
            "source_packet_version_id": str(article.source_packet_version_id.value),
            "source_packet_content_sha256": article.source_packet_content_sha256.value,
            "complete_claim_set_sha256": article.complete_claim_set_sha256.value,
            "binding_sha256": article.binding_sha256.value,
        },
        "evaluated_at": seed["evaluated_at"],
        "candidate_universe": {
            "universe_id": str(universe.universe_id.value),
            "version_no": universe.version_no,
            "products": [
                {
                    "product_id": str(item.product_id.value),
                    "variant_identity_sha256": item.variant_identity_sha256.value,
                    "subject_identity_sha256": item.subject_identity_sha256.value,
                    "inclusion_reason_code": item.inclusion_reason_code,
                }
                for item in products
            ],
            "candidate_universe_sha256": universe.candidate_universe_sha256.value,
        },
        "axis_catalog": {
            "catalog_id": str(catalog.catalog_id.value),
            "version_no": catalog.version_no,
            "source_sha256": catalog.source_sha256.value,
            "axes": [
                {
                    "axis_id": str(axis.axis_id.value),
                    "axis_code": axis.axis_code,
                    "label": axis.label,
                    "description": axis.description,
                    "data_type": axis.data_type.value,
                    "unit_family_code": axis.unit_family_code,
                    "unit_code": axis.unit_code,
                    "position": axis.position,
                    "required": axis.required,
                }
            ],
            "axis_catalog_sha256": catalog.axis_catalog_sha256.value,
        },
        "facts": [
            {
                "fact_id": str(item.fact_id.value),
                "fact_sha256": item.fact_sha256.value,
                "product_id": str(item.product_id.value),
                "variant_identity_sha256": item.variant_identity_sha256.value,
                "subject_identity_sha256": item.subject_identity_sha256.value,
                "axis_id": str(item.axis_id.value),
                "value": {
                    "data_type": item.value.data_type.value,
                    "value": str(item.value.decimal_value),
                },
                "unit_code": item.unit_code,
                "observed_at": seed["observed_at"],
                "valid_from": seed["valid_from"],
                "valid_until": seed["valid_until"],
            }
            for item in facts
        ],
        "cells": [
            {
                "product_id": str(item.product_id.value),
                "axis_id": str(item.axis_id.value),
                "status": item.status.value,
                "value": {
                    "data_type": cast(TypedComparisonValue, item.value).data_type.value,
                    "value": str(cast(TypedComparisonValue, item.value).decimal_value),
                },
                "unit_code": item.unit_code,
                "fact_ids": [str(fact_id.value) for fact_id in item.fact_ids],
                "reason_code": item.reason_code,
                "imputed": item.imputed,
            }
            for item in cells
        ],
        "show_unknown_values": True,
        "fact_set_sha256": snapshot.fact_set_sha256.value,
        "temporal_scope_sha256": snapshot.temporal_scope_sha256.value,
        "evaluation_input_sha256": snapshot.evaluation_input_sha256.value,
    }
    return snapshot, material


def _claim_fixture(
    root: Path,
    seed: dict[str, Any],
    comparison: ComparisonSnapshotV2,
) -> dict[str, object]:
    upstream_payload = _read_regular(_safe_path(root, UPSTREAM_FIXTURE_PATH))
    try:
        loaded = json.loads(upstream_payload)
    except Exception:
        _fail("UPSTREAM_FIXTURE_INVALID")
    if type(loaded) is not dict:
        _fail("UPSTREAM_FIXTURE_INVALID")
    fixture = cast(dict[str, Any], loaded)
    claim = dict(cast(list[dict[str, Any]], fixture["claims"])[0])
    claim["claim_type"] = "comparative"
    claim["affects_purchase_decision"] = True
    claim["allowed_subject_identity_sha256s"] = [
        row["subject_identity_sha256"]
        for row in cast(list[dict[str, Any]], seed["products"])
    ]
    claim_id = seed["comparative_claim_id"]
    claim["claim_id"] = claim_id
    claim["claim_text_sha256"] = seed["comparative_claim_text_sha256"]
    fixture["claims"] = [claim]
    proof = dict(cast(list[dict[str, Any]], fixture["requirement_proofs"])[0])
    proof["claim_id"] = claim_id
    proof["temporal_scope_sha256"] = comparison.temporal_scope_sha256.value
    proof["comparison_population_sha256"] = (
        comparison.candidate_universe.candidate_universe_sha256.value
    )
    proof["unknown_value_handling"] = "NOT_APPLICABLE"
    fixture["requirement_proofs"] = [proof]
    for link in cast(list[dict[str, Any]], fixture["links"]):
        link["claim_id"] = claim_id
    for citation in cast(list[dict[str, Any]], fixture["citations"]):
        citation["claim_id"] = claim_id
    article = cast(dict[str, Any], fixture["article"])
    article["complete_claim_ids"] = [claim_id]
    article["complete_claim_set_sha256"] = "0" * 64
    fixture["attestations"] = []
    provisional_payload = json.dumps(
        fixture,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    provisional = load_recorded_claim_evidence_fixture(provisional_payload)
    article["complete_claim_set_sha256"] = complete_claim_set_sha256(
        provisional.claims
    ).value
    fixture["attestations"] = []
    without_attestations = load_recorded_claim_evidence_fixture(
        json.dumps(
            fixture,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    )
    attestations: list[dict[str, object]] = []
    for kind, subject, input_digest in required_validation_attestation_inputs(
        without_attestations
    ):
        if kind is ValidationAttestationKind.COMPARISON:
            continue
        owner, version, contract_digest = validation_attestation_owner_binding(kind)
        attestations.append(
            {
                "kind": kind.value,
                "owner_story_id": owner,
                "contract_version": version,
                "contract_sha256": contract_digest.value,
                "origin": "RECORDED_SYNTHETIC_ONLY",
                "subject_sha256": subject.value,
                "input_sha256": input_digest.value,
                "decision_sha256": (
                    recorded_synthetic_attestation_decision_sha256(
                        kind,
                        subject,
                        input_digest,
                    ).value
                ),
                "validated_at": "2026-08-23T23:00:00Z",
                "valid": True,
            }
        )
    fixture["attestations"] = attestations
    verified = load_recorded_claim_evidence_fixture(
        json.dumps(
            fixture,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    )
    baseline = evaluate_claim_evidence(verified)
    if baseline.status is not CoverageStatus.UNEVALUABLE or set(baseline.findings) != {
        CoverageFindingCode.REQUIRED_ATTESTATION_MISSING
    }:
        _fail("ST0605_PRECOMPUTED_BASELINE_INVALID")
    return cast(dict[str, object], fixture)


def _fixture_bytes(root: Path, contract: dict[str, Any]) -> bytes:
    seed = cast(dict[str, Any], contract["fixture_seed"])
    provisional_comparison, _ = _materialize_comparison(seed, "0" * 64)
    claim_fixture = _claim_fixture(root, seed, provisional_comparison)
    complete_claim_sha256 = cast(
        str,
        cast(dict[str, object], claim_fixture["article"])["complete_claim_set_sha256"],
    )
    comparison, comparison_material = _materialize_comparison(
        seed,
        complete_claim_sha256,
    )
    claim_fixture = _claim_fixture(root, seed, comparison)
    root_material = {
        "schema_version": 2,
        "comparison": comparison_material,
        "claim_evidence": claim_fixture,
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
    envelope = load_recorded_comparison_fixture(payload)
    if type(envelope) is not ComparisonValidationEnvelopeV2:
        _fail("RECORDED_FIXTURE_INVALID")
    report = validate_comparison_v2(envelope)
    if (
        report.status is not ComparisonValidationStatus.LOCAL_VALIDATED
        or report.findings
        or not report.comparison_attestations
        or report.publication_authorized
        or report.recommendation_authorized
        or report.ranking_authorized
        or report.production_eligible
    ):
        _fail("RECORDED_FIXTURE_NOT_LOCALLY_VALIDATED")
    if comparison.evaluation_input_sha256 != report.evaluation_input_sha256:
        _fail("RECORDED_FIXTURE_INPUT_BINDING_INVALID")
    return payload


def _artifact(root: Path, relative: Path, *, role: str) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, relative))
    suffix = relative.suffix.lower()
    media_type = {
        ".json": "application/json",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
        ".py": "text/x-python",
        ".md": "text/markdown",
        ".toml": "application/toml",
        ".lock": "application/octet-stream",
    }.get(suffix, "application/octet-stream")
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
        "story_id": "ST-0803",
        "classification": (
            "LOCAL_EXECUTABLE_RECORDED_COMPARISON_VALIDATION_RUNTIME_MANIFEST_V2"
        ),
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
            "command": (
                ".venv/bin/python scripts/build_st0803_comparison_validation_runtime.py"
            ),
            "check_command": (
                ".venv/bin/python "
                "scripts/build_st0803_comparison_validation_runtime.py --check"
            ),
            "transaction": "ATOMIC_MULTI_OUTPUT_WITH_ROLLBACK",
            "existing_destination_commit": "RENAMEAT2_EXCHANGE_WITH_REVERSE_VERIFY",
            "missing_destination_commit": "HARDLINK_NO_CLOBBER",
            "foreign_target_policy": "PRESERVE_AND_FAIL_CLOSED",
            "symlink_policy": "REJECT",
            "hardlink_policy": "REJECT",
            "source_identity": "LSTAT_FSTAT_DEVICE_INODE_SIZE_MTIME",
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
            "publication_authorized": False,
            "recommendation_authorized": False,
            "ranking_authorized": False,
            "production_eligible": False,
            "formal_tst_007_status": "NOT_EXECUTED",
            "formal_tst_020_status": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(
        document,
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")


def _replace_generated(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_generated_publication.publish_generated(
            artifacts,
            namespace="st0803",
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
        print("ST-0803 V2 runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0803 V2 runtime checked"
        if arguments.check
        else "ST-0803 V2 runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
