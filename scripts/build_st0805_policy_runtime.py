#!/usr/bin/env python3
"""Generate the deterministic ST-0805 V2 policy fixture and manifest."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
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
for candidate in (REPO_ROOT, REPO_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import secure_generated_publication  # noqa: E402

from raos.adapters.recorded_policy_engine import (  # noqa: E402
    build_policy_input_from_seed,
    load_recorded_policy_fixture,
)
from raos.adapters.recorded_recommendation import (  # noqa: E402
    load_recorded_recommendation_fixture,
)
from raos.domain.editorial.article_lifecycle import (  # noqa: E402
    ArticleVersionState,
    BodySha256,
    SourcePacketVerification,
    VersionDisplayId,
    VersionSnapshot,
)
from raos.domain.editorial.article_plan import ArticlePlanType  # noqa: E402
from raos.domain.editorial.comparison_validation_v2 import (  # noqa: E402
    ComparisonRecordReceipt,
    ComparisonValidationStatus,
    article_binding_sha256,
    comparison_input_sha256,
    validate_comparison_v2,
)
from raos.domain.editorial.content_ast import (  # noqa: E402
    dump_content_ast_json,
    load_content_ast,
)
from raos.domain.editorial.policy_engine import (  # noqa: E402
    POLICY_DEFINITIONS,
    QUALITY_AXIS_DEFINITIONS,
    QUALITY_GATE_DEFINITIONS,
    ZERO_TOLERANCE_LABELS,
    evaluate_editorial_policy,
)
from raos.domain.editorial.policy_engine_v2 import (  # noqa: E402
    DraftAstBindingV2,
    PolicyContractBindingV2,
    PolicyEvaluationEnvelopeV2,
    PolicyEvaluationStatusV2,
    coverage_receipt_sha256,
    draft_ast_sha256,
    draft_binding_sha256,
    evaluate_editorial_policy_v2,
    policy_evaluation_input_sha256,
    policy_result_sha256,
    recommendation_receipt_sha256,
)
from raos.domain.editorial.recommendation_v2 import (  # noqa: E402
    DimensionAssessmentV2,
    RecommendationRecordReceipt,
    assessment_set_sha256,
    comparison_receipt_sha256,
    decision_context_sha256,
    evaluate_recommendations_v2,
    normalization_decision_sha256,
    normalization_input_sha256,
    recommendation_input_sha256,
)
from raos.domain.evidence.claim_evidence import (  # noqa: E402
    CoverageRecordReceipt,
    CoverageStatus,
    EvidenceValidationAttestation,
    ValidationAttestationKind,
    ValidationAttestationOrigin,
    complete_claim_set_sha256,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)
from raos.domain.portfolio.workflow import (  # noqa: E402
    EntityVersion,
    StrongEtag,
    UtcTimestamp,
)
from raos.domain.shared.persistence import Sha256Digest  # noqa: E402


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
EXPECTED_PYTEST_VERSION: Final = "9.1.1"
EXPECTED_PYDANTIC_VERSION: Final = "2.13.4"
EXPECTED_PYDANTIC_CORE_VERSION: Final = "2.46.4"

CONTRACT_PATH: Final = Path("changes/st-0805/contracts/policy-runtime.v2.yaml")
FIXTURE_PATH: Final = Path("changes/st-0805/generated/policy-pass.v2.json")
MANIFEST_PATH: Final = Path("changes/st-0805/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0805_policy_runtime.py")
UPSTREAM_RECOMMENDATION_PATH: Final = Path(
    "changes/st-0804/generated/recommendation-pass.v2.json"
)
UPSTREAM_RECOMMENDATION_SHA256: Final = (
    "52a48ea6608d54abc0346c559823b5994c67eca59012c10e19291d0dcfc2cbc6"
)
UPSTREAM_RECOMMENDATION_MANIFEST: Final = Path(
    "changes/st-0804/runtime-manifest.v2.yaml"
)
UPSTREAM_RECOMMENDATION_MANIFEST_SHA256: Final = (
    "15e8a2087a45602070e140d00b6f5f4755085fdbab6fc2c55b2e8d04d6fce5da"
)
CONTENT_AST_SEED_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/fixtures/valid/selection_guide.json"
)
CONTENT_AST_SEED_SHA256: Final = (
    "8467c824215c548479f1ccba5877797910c3a4abec736af37627605059422489"
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
            "changes/st-0004/contracts/content/RAOS_06_editorial_policy_catalog_v0.1.yaml"
        ),
        "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a",
    ),
    (
        Path(
            "changes/st-0004/contracts/content/RAOS_06_quality_gate_catalog_v0.1.yaml"
        ),
        "90ab554aa55dda335ba69bbb306772306494e2e4ba899c3d22af4a9d9a030efb",
    ),
    (
        Path(
            "changes/st-0004/contracts/content/RAOS_06_claim_evidence_policy_v0.1.yaml"
        ),
        "fbf2d0ad6e7821a0059f9ceeb53d57268031e2e42b4aad988af9a42378aec5ba",
    ),
    (
        Path(
            "changes/st-0004/contracts/content/RAOS_06_recommendation_methodology_v0.1.yaml"
        ),
        "fb71ad7900c7f688f305e10256b49563281893408e54d8668aac02efa7e57862",
    ),
    (
        Path("python/raos/domain/editorial/policy_engine.py"),
        "d858a9b010253cf411083bd5eb9da995ff3f9a172c7626ca9e499a6256559e51",
    ),
    (
        Path("python/raos/domain/editorial/article_lifecycle.py"),
        "c44cb8c5d26f4862e7527bcb179c20f1f60d3a069d9ba67fad3b0109ef0c6edd",
    ),
    (
        Path("python/raos/domain/editorial/content_ast.py"),
        "7cb4054cc8ab9b950cc572c0d8fa23dafe5baf77c40c242f81dac0fc0a492f68",
    ),
    (
        Path("python/raos/domain/editorial/recommendation_v2.py"),
        "d7b020a65dfe2071335fda7bdb9b804fcd02def954c415a36318437a9e4d5de4",
    ),
    (UPSTREAM_RECOMMENDATION_PATH, UPSTREAM_RECOMMENDATION_SHA256),
    (
        UPSTREAM_RECOMMENDATION_MANIFEST,
        UPSTREAM_RECOMMENDATION_MANIFEST_SHA256,
    ),
    (CONTENT_AST_SEED_PATH, CONTENT_AST_SEED_SHA256),
    (SECURE_HELPER_PATH, SECURE_HELPER_SHA256),
)

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/editorial/policy_engine_v2.py"),
    Path("python/raos/ports/editorial/policy_engine.py"),
    Path("python/raos/application/editorial/policy_engine.py"),
    Path("python/raos/adapters/recorded_policy_engine.py"),
    Path("changes/st-0805/README-v2.md"),
    Path("changes/st-0805/HISTORICAL-DRIFT.md"),
    Path("changes/st-0805/completion/completion.v2.yaml"),
    Path("docs/execplans/ST-0805.md"),
    Path("docs/worklogs/ST-0805.md"),
    Path("docs/worklogs/RAOS-IMPLEMENTATION-DEBT.md"),
    Path("tests/st0805_runtime/__init__.py"),
    Path("tests/st0805_runtime/conftest.py"),
    Path("tests/st0805_runtime/test_domain.py"),
    Path("tests/st0805_runtime/test_application_adapter.py"),
    Path("tests/st0805_runtime/test_generation.py"),
    Path("tests/st0805_runtime/test_static_boundary.py"),
)
RUNTIME_DEPENDENCY_PATHS: Final = (
    Path("python/raos/__init__.py"),
    Path("python/raos/adapters/__init__.py"),
    Path("python/raos/config/runtime.py"),
    Path("python/raos/domain/editorial/ids.py"),
    Path("python/raos/domain/evidence/claim_evidence.py"),
    Path("python/raos/domain/shared/persistence.py"),
    Path("python/raos/ports/__init__.py"),
    Path("python/raos/ports/editorial/__init__.py"),
)
LOCKED_TOOLCHAIN_PATHS: Final = (Path("pyproject.toml"), Path("uv.lock"))
SOURCE_PATHS: Final = (
    *OWNED_SOURCE_PATHS,
    *(path for path, _digest_value in CANONICAL_BINDINGS),
    *(path for path, _digest_value in DEPENDENCY_BINDINGS),
    *RUNTIME_DEPENDENCY_PATHS,
    *LOCKED_TOOLCHAIN_PATHS,
)
GENERATED_PATHS: Final = (FIXTURE_PATH, MANIFEST_PATH)
MAX_CONTRACT_BYTES: Final = 262_144
MAX_GENERATED_BYTES: Final = 8 * 1024 * 1024
TOP_LEVEL_KEYS: Final = (
    "schema_version",
    "story_id",
    "local_status",
    "classification",
    "runtime",
    "bindings",
    "draft_seed",
    "policy_defaults",
    "dependency_boundary",
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
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _validate_toolchain() -> None:
    if (
        sys.implementation.name != EXPECTED_PYTHON_IMPLEMENTATION
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
        or getattr(yaml, "__version__", None) != EXPECTED_PYYAML_VERSION
    ):
        _fail("GENERATION_TOOLCHAIN_DRIFT")
    for package, expected in (
        ("pytest", EXPECTED_PYTEST_VERSION),
        ("pydantic", EXPECTED_PYDANTIC_VERSION),
        ("pydantic-core", EXPECTED_PYDANTIC_CORE_VERSION),
    ):
        try:
            observed = distribution_version(package)
        except PackageNotFoundError:
            _fail("GENERATION_TOOLCHAIN_DRIFT")
        if observed != expected:
            _fail("GENERATION_TOOLCHAIN_DRIFT")


def _safe_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("UNSAFE_PATH")
    resolved = root.resolve()
    current = resolved
    for part in relative.parts:
        current /= part
        try:
            observed = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(observed.st_mode):
            _fail("SYMLINK_REJECTED")
    return resolved / relative


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
        named_before = os.lstat(path)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or named_before.st_dev != opened.st_dev
            or named_before.st_ino != opened.st_ino
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


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    payload = _read_regular(_safe_path(root, CONTRACT_PATH), maximum=MAX_CONTRACT_BYTES)
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
        or result["story_id"] != "ST-0805"
        or result["local_status"] != "LOCAL_IMPLEMENTATION_COMPLETE"
        or result["classification"]
        != "LOCAL_EXECUTABLE_RECORDED_EDITORIAL_POLICY_RUNTIME_V2"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    if result["runtime"] != {
        "executable": True,
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "repository_write": False,
        "finding_proposal_only": True,
        "waiver_proposal_only": True,
        "approval_authorized": False,
        "waiver_apply_authorized": False,
        "merge_authorized": False,
        "recommendation_override_authorized": False,
        "ranking_override_authorized": False,
        "publication_authorized": False,
        "activation_authorized": False,
        "production_eligible": False,
    }:
        _fail("CONTRACT_RUNTIME_INVALID")
    if result["policy_defaults"] != {
        "evaluated_at": "2026-08-24T00:00:00Z",
        "policy_count": len(POLICY_DEFINITIONS),
        "policy_result": "PASS",
        "quality_axis_count": len(QUALITY_AXIS_DEFINITIONS),
        "quality_axis_state": "EVALUATED",
        "quality_axis_score": "CATALOG_WEIGHT",
        "zero_tolerance_count": len(ZERO_TOLERANCE_LABELS),
        "zero_tolerance_state": "CLEAR",
        "quality_gate_count": len(QUALITY_GATE_DEFINITIONS),
        "quality_gate_state": "PASS",
        "waiver_policy_ids": [],
    }:
        _fail("CONTRACT_POLICY_DEFAULT_INVALID")
    if result["draft_seed"] != {
        "article_id": "018f3e90-7b00-7000-8000-000000000805",
        "article_version_id": "018f3e90-7b00-7000-8000-000000000806",
        "source_packet_version_id": "018f3e90-7b00-7000-8000-000000000807",
        "display_id": "ARV-RECORDED-0805",
        "article_type": "SELECTION_GUIDE",
        "title": "ST-0805 recorded policy draft",
        "created_at": "2026-08-24T00:00:00Z",
        "version_no": 1,
    }:
        _fail("CONTRACT_DRAFT_SEED_INVALID")
    if result["dependency_boundary"] != {
        "st0605_coverage_report_required": "PASS",
        "st0605_exact_report_receipt": True,
        "st0802_exact_draft_ast": True,
        "st0804_recommendation_report_required": "LOCAL_CALCULATED",
        "st0804_exact_report_receipt": True,
        "common_article_body_packet_claim_core": True,
        "unknown_missing_conflict_unevaluated_to_pass": False,
    }:
        _fail("CONTRACT_DEPENDENCY_BOUNDARY_INVALID")
    if result["execution_boundary"] != {
        "repository_read": "GENERATED_RECORDED_FIXTURE_ONLY",
        "result_append": "PROCESS_LOCAL_METADATA_ONLY",
        "network": "FORBIDDEN",
        "credential": "FORBIDDEN",
        "provider": "FORBIDDEN",
        "approval": "FORBIDDEN",
        "waiver_apply": "FORBIDDEN",
        "article_mutation": "FORBIDDEN",
        "recommendation_mutation": "FORBIDDEN",
        "ranking_mutation": "FORBIDDEN",
        "publication_snapshot_mutation": "FORBIDDEN",
    }:
        _fail("CONTRACT_EXECUTION_BOUNDARY_INVALID")
    if result["verification_boundary"] != {
        "TST-019": "NOT_EXECUTED",
        "TST-020": "NOT_EXECUTED",
        "formal_validation": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "publication": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }:
        _fail("CONTRACT_VERIFICATION_BOUNDARY_INVALID")
    bindings = cast(dict[str, Any], result["bindings"])
    current = PolicyContractBindingV2.current()
    if bindings != {
        "policy_catalog_id": "RAOS-CONTENT-POLICY-001",
        "policy_catalog_version": "0.1",
        "policy_catalog_sha256": current.policy_catalog_sha256.value,
        "quality_catalog_id": "RAOS-CONTENT-QG-001",
        "quality_catalog_version": "0.1",
        "quality_catalog_sha256": current.quality_catalog_sha256.value,
        "claim_evidence_policy_sha256": current.claim_evidence_policy_sha256.value,
        "recommendation_methodology_sha256": (
            current.recommendation_methodology_sha256.value
        ),
        "legacy_policy_engine_sha256": current.legacy_policy_engine_sha256.value,
        "article_lifecycle_sha256": current.article_lifecycle_sha256.value,
        "content_ast_source_sha256": current.content_ast_source_sha256.value,
        "st0804_domain_sha256": current.st0804_domain_sha256.value,
        "st0804_recorded_fixture_sha256": UPSTREAM_RECOMMENDATION_SHA256,
        "st0804_runtime_manifest_sha256": (UPSTREAM_RECOMMENDATION_MANIFEST_SHA256),
        "content_ast_seed_sha256": CONTENT_AST_SEED_SHA256,
        "secure_publication_helper_sha256": SECURE_HELPER_SHA256,
    }:
        _fail("CONTRACT_BINDING_INVALID")
    _require_hashes(root)
    return result


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except Exception:
        _fail("CONTRACT_INSTANT_INVALID")
    if (
        parsed.tzinfo is not timezone.utc
        or parsed.isoformat().replace("+00:00", "Z") != value
    ):
        _fail("CONTRACT_INSTANT_INVALID")
    return parsed


def _attestation_material(value: EvidenceValidationAttestation) -> dict[str, object]:
    return {
        "kind": value.kind.value,
        "owner_story_id": value.owner_story_id,
        "contract_version": value.contract_version,
        "contract_sha256": value.contract_sha256.value,
        "origin": value.origin.value,
        "subject_sha256": value.subject_sha256.value,
        "input_sha256": value.input_sha256.value,
        "decision_sha256": value.decision_sha256.value,
        "validated_at": value.validated_at.value.isoformat().replace("+00:00", "Z"),
        "valid": value.valid,
    }


def _contract_material(value: PolicyContractBindingV2) -> dict[str, object]:
    return {
        "contract_id": value.contract_id,
        "contract_version": value.contract_version,
        "evaluator_version": value.evaluator_version,
        "policy_catalog_sha256": value.policy_catalog_sha256.value,
        "quality_catalog_sha256": value.quality_catalog_sha256.value,
        "claim_evidence_policy_sha256": value.claim_evidence_policy_sha256.value,
        "recommendation_methodology_sha256": (
            value.recommendation_methodology_sha256.value
        ),
        "legacy_policy_engine_sha256": value.legacy_policy_engine_sha256.value,
        "article_lifecycle_sha256": value.article_lifecycle_sha256.value,
        "content_ast_source_sha256": value.content_ast_source_sha256.value,
        "st0804_domain_sha256": value.st0804_domain_sha256.value,
    }


def _policy_seed(contract: dict[str, Any]) -> dict[str, object]:
    defaults = cast(dict[str, Any], contract["policy_defaults"])
    return {
        "evaluated_at": defaults["evaluated_at"],
        "policy_results": [
            {"policy_id": item.policy_id, "result": defaults["policy_result"]}
            for item in POLICY_DEFINITIONS
        ],
        "axis_assessments": [
            {
                "axis_id": item.axis_id,
                "state": defaults["quality_axis_state"],
                "score": format(item.weight, "f"),
            }
            for item in QUALITY_AXIS_DEFINITIONS
        ],
        "zero_tolerance_assessments": [
            {"label": label, "state": defaults["zero_tolerance_state"]}
            for label in ZERO_TOLERANCE_LABELS
        ],
        "gate_assessments": [
            {"gate_id": item.gate_id, "state": defaults["quality_gate_state"]}
            for item in QUALITY_GATE_DEFINITIONS
        ],
        "waiver_policy_ids": defaults["waiver_policy_ids"],
    }


def _build_fixture(root: Path, contract: dict[str, Any]) -> bytes:
    upstream_payload = _read_regular(
        _safe_path(root, UPSTREAM_RECOMMENDATION_PATH),
        maximum=MAX_GENERATED_BYTES,
    )
    try:
        upstream_material = json.loads(upstream_payload)
        ast_seed = json.loads(_read_regular(_safe_path(root, CONTENT_AST_SEED_PATH)))
    except Exception:
        _fail("UPSTREAM_PARSE_FAILED")
    upstream = load_recorded_recommendation_fixture(upstream_payload)
    draft_seed = cast(dict[str, Any], contract["draft_seed"])
    article_id = UUID(draft_seed["article_id"])
    article_version_id = UUID(draft_seed["article_version_id"])
    source_packet_version_id = UUID(draft_seed["source_packet_version_id"])
    ast_seed["article_id"] = str(article_id)
    ast_seed["article_version_id"] = str(article_version_id)
    ast_seed["source_packet_version_ref"] = str(source_packet_version_id)
    ast_seed["title"] = draft_seed["title"]
    content_ast = load_content_ast(json.dumps(ast_seed, ensure_ascii=False))
    created_at = _instant(draft_seed["created_at"])
    draft_snapshot = VersionSnapshot(
        version_id=article_version_id,
        display_id=VersionDisplayId(draft_seed["display_id"]),
        article_id=article_id,
        version_no=draft_seed["version_no"],
        article_type=ArticlePlanType(draft_seed["article_type"]),
        title=draft_seed["title"],
        source_packet_version_id=source_packet_version_id,
        source_packet_verification=SourcePacketVerification.NOT_VERIFIED,
        based_on_version_id=None,
        content_ast=content_ast,
        body_sha256=BodySha256.of(content_ast),
        state=ArticleVersionState.DRAFT,
        submitted_at=None,
        reviewed_at=None,
        approved_at=None,
        published_at=None,
        version=EntityVersion(0),
        etag=StrongEtag('"st0805-recorded-v0"'),
        created_at=UtcTimestamp(created_at),
        updated_at=UtcTimestamp(created_at),
    )
    draft = DraftAstBindingV2(
        snapshot=draft_snapshot,
        canonical_ast_sha256=draft_ast_sha256(draft_snapshot),
        binding_sha256=draft_binding_sha256(draft_snapshot),
    )

    old_claim = upstream.comparison.claim_evidence
    typed_article_version = type(old_claim.article.article_version_id)(
        article_version_id
    )
    typed_packet_version = type(old_claim.article.source_packet_version_id)(
        source_packet_version_id
    )
    claims = tuple(
        replace(item, article_version_id=typed_article_version)
        for item in old_claim.claims
    )
    claim_set_hash = complete_claim_set_sha256(claims)
    coverage_article = replace(
        old_claim.article,
        article_version_id=typed_article_version,
        article_body_sha256=Sha256Digest(draft_snapshot.body_sha256.value),
        source_packet_version_id=typed_packet_version,
        complete_claim_set_sha256=claim_set_hash,
    )
    approved_packet = replace(
        old_claim.approved_packet,
        source_packet_version_id=typed_packet_version,
    )
    claim_base = replace(
        old_claim,
        article=coverage_article,
        approved_packet=approved_packet,
        claims=claims,
        attestations=(),
    )
    attestations: list[EvidenceValidationAttestation] = []
    for kind, subject_hash, input_hash in required_validation_attestation_inputs(
        claim_base
    ):
        owner, contract_version, contract_hash = validation_attestation_owner_binding(
            kind
        )
        attestations.append(
            EvidenceValidationAttestation(
                kind=kind,
                owner_story_id=owner,
                contract_version=contract_version,
                contract_sha256=contract_hash,
                origin=ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY,
                subject_sha256=subject_hash,
                input_sha256=input_hash,
                decision_sha256=recorded_synthetic_attestation_decision_sha256(
                    kind, subject_hash, input_hash
                ),
                validated_at=claim_base.evaluated_at,
                valid=True,
            )
        )
    coverage_snapshot = replace(claim_base, attestations=tuple(attestations))
    coverage_report = evaluate_claim_evidence(coverage_snapshot)
    coverage_report.require_valid()
    if coverage_report.status is not CoverageStatus.PASS or coverage_report.findings:
        _fail("COVERAGE_NOT_PASS")
    coverage_receipt = CoverageRecordReceipt(1, coverage_report.report_sha256)
    coverage_receipt.require_valid()
    comparison_claim = replace(
        claim_base,
        attestations=tuple(
            item
            for item in attestations
            if item.kind is not ValidationAttestationKind.COMPARISON
        ),
    )

    comparison_old = upstream.comparison.comparison
    comparison_article_old = comparison_old.article
    typed_article_id = type(comparison_article_old.article_id)(article_id)
    comparison_article = replace(
        comparison_article_old,
        article_id=typed_article_id,
        article_version_id=typed_article_version,
        article_body_sha256=Sha256Digest(draft_snapshot.body_sha256.value),
        source_packet_version_id=typed_packet_version,
        complete_claim_set_sha256=claim_set_hash,
        binding_sha256=Sha256Digest("0" * 64),
    )
    comparison_article = replace(
        comparison_article,
        binding_sha256=article_binding_sha256(comparison_article),
    )
    comparison = replace(
        comparison_old,
        article=comparison_article,
        evaluation_input_sha256=Sha256Digest("0" * 64),
    )
    comparison = replace(
        comparison,
        evaluation_input_sha256=comparison_input_sha256(comparison),
    )
    comparison_envelope = replace(
        upstream.comparison,
        comparison=comparison,
        claim_evidence=comparison_claim,
    )
    comparison_report = validate_comparison_v2(comparison_envelope)
    comparison_report.require_valid()
    if (
        comparison_report.status is not ComparisonValidationStatus.LOCAL_VALIDATED
        or comparison_report.findings
    ):
        _fail("COMPARISON_NOT_LOCAL_VALIDATED")
    comparison_receipt = ComparisonRecordReceipt(1, comparison_report.report_sha256)
    comparison_receipt.require_valid()
    context = replace(
        upstream.context,
        article_id=typed_article_id,
        article_version_id=typed_article_version,
        article_binding_sha256=comparison_article.binding_sha256,
        binding_sha256=Sha256Digest("0" * 64),
    )
    context = replace(context, binding_sha256=decision_context_sha256(context))
    cells = {(item.product_id, item.axis_id): item for item in comparison.cells}
    dimensions = {item.axis_id: item for item in upstream.dimensions}
    assessments: list[DimensionAssessmentV2] = []
    for assessment in upstream.assessments:
        dimension = dimensions[assessment.axis_id]
        cell = cells[(assessment.product_id, assessment.axis_id)]
        normalization_input = normalization_input_sha256(
            comparison=comparison,
            context=context,
            methodology=upstream.methodology,
            dimension=dimension,
            cell=cell,
            basis=assessment.normalization_basis,
        )
        normalization_decision = normalization_decision_sha256(
            input_sha256=normalization_input,
            basis=assessment.normalization_basis,
            normalized_score=assessment.normalized_score,
        )
        assessments.append(
            replace(
                assessment,
                normalization_input_sha256=normalization_input,
                normalization_decision_sha256=normalization_decision,
            )
        )
    assessment_tuple = tuple(assessments)
    recommendation = replace(
        upstream,
        comparison=comparison_envelope,
        comparison_report=comparison_report,
        comparison_receipt=comparison_receipt,
        context=context,
        assessments=assessment_tuple,
        assessment_set_sha256=assessment_set_sha256(assessment_tuple),
        recommendation_input_sha256=Sha256Digest("0" * 64),
    )
    recommendation = replace(
        recommendation,
        recommendation_input_sha256=recommendation_input_sha256(recommendation),
    )
    recommendation_report = evaluate_recommendations_v2(recommendation)
    recommendation_report.require_valid()
    if not recommendation_report.locally_calculated or recommendation_report.findings:
        _fail("RECOMMENDATION_NOT_LOCAL_CALCULATED")
    recommendation_receipt = RecommendationRecordReceipt(
        1, recommendation_report.report_sha256
    )
    recommendation_receipt.require_valid()

    claim_raw = deepcopy(upstream_material["comparison_request"]["claim_evidence"])
    claim_raw["article"]["article_version_id"] = str(article_version_id)
    claim_raw["article"]["article_body_sha256"] = draft_snapshot.body_sha256.value
    claim_raw["article"]["source_packet_version_id"] = str(source_packet_version_id)
    claim_raw["article"]["complete_claim_set_sha256"] = claim_set_hash.value
    claim_raw["approved_packet"]["source_packet_version_id"] = str(
        source_packet_version_id
    )
    for claim in claim_raw["claims"]:
        claim["article_version_id"] = str(article_version_id)
    claim_raw["attestations"] = [_attestation_material(item) for item in attestations]
    comparison_claim_raw = deepcopy(claim_raw)
    comparison_claim_raw["attestations"] = [
        _attestation_material(item) for item in comparison_claim.attestations
    ]
    comparison_raw = deepcopy(upstream_material["comparison_request"]["comparison"])
    comparison_raw["article"].update(
        {
            "article_id": str(article_id),
            "article_version_id": str(article_version_id),
            "article_version_no": draft_snapshot.version_no,
            "article_body_sha256": draft_snapshot.body_sha256.value,
            "source_packet_version_id": str(source_packet_version_id),
            "complete_claim_set_sha256": claim_set_hash.value,
            "binding_sha256": comparison_article.binding_sha256.value,
        }
    )
    comparison_raw["evaluation_input_sha256"] = comparison.evaluation_input_sha256.value
    recommendation_raw = deepcopy(upstream_material)
    recommendation_raw["comparison_request"] = {
        "schema_version": 2,
        "comparison": comparison_raw,
        "claim_evidence": comparison_claim_raw,
    }
    recommendation_raw["comparison_report"] = json.loads(
        comparison_report.canonical_bytes()
    )
    recommendation_raw["comparison_record_receipt"] = {
        "sequence": comparison_receipt.sequence,
        "report_sha256": comparison_receipt.report_sha256.value,
        "publication_authorized": False,
    }
    recommendation_raw["context"].update(
        {
            "article_id": str(article_id),
            "article_version_id": str(article_version_id),
            "article_binding_sha256": comparison_article.binding_sha256.value,
            "binding_sha256": context.binding_sha256.value,
        }
    )
    raw_assessments = cast(list[dict[str, Any]], recommendation_raw["assessments"])
    for raw, assessment in zip(raw_assessments, assessment_tuple, strict=True):
        raw["normalization_input_sha256"] = assessment.normalization_input_sha256.value
        raw["normalization_decision_sha256"] = (
            assessment.normalization_decision_sha256.value
        )
    recommendation_raw["declared_hashes"].update(
        {
            "comparison_request_sha256": comparison.evaluation_input_sha256.value,
            "comparison_report_sha256": comparison_report.report_sha256.value,
            "comparison_receipt_sha256": comparison_receipt_sha256(
                comparison_receipt
            ).value,
            "decision_context_sha256": context.binding_sha256.value,
            "assessment_set_sha256": recommendation.assessment_set_sha256.value,
            "recommendation_input_sha256": (
                recommendation.recommendation_input_sha256.value
            ),
        }
    )
    round_trip = load_recorded_recommendation_fixture(
        json.dumps(
            recommendation_raw,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
    )
    if (
        evaluate_recommendations_v2(round_trip).canonical_bytes()
        != recommendation_report.canonical_bytes()
    ):
        _fail("RECOMMENDATION_ROUND_TRIP_INVALID")

    policy_seed = _policy_seed(contract)
    policy_input = build_policy_input_from_seed(
        policy_seed,
        draft=draft,
        coverage_report_sha256=coverage_report.report_sha256.value,
        coverage_receipt_digest=coverage_receipt_sha256(coverage_receipt).value,
        recommendation_report_sha256=recommendation_report.report_sha256.value,
        recommendation_receipt_digest=recommendation_receipt_sha256(
            recommendation_receipt
        ).value,
    )
    legacy_result = evaluate_editorial_policy(policy_input)
    if not legacy_result.local_eligibility:
        _fail("POLICY_DEFAULT_NOT_ELIGIBLE")
    policy_digest = policy_result_sha256(legacy_result)
    input_digest = policy_evaluation_input_sha256(
        contract=PolicyContractBindingV2.current(),
        draft=draft,
        coverage_report=coverage_report,
        coverage_receipt=coverage_receipt,
        recommendation_report=recommendation_report,
        recommendation_receipt=recommendation_receipt,
        policy_result_digest=policy_digest,
    )
    root_material = {
        "schema_version": 2,
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "contract": _contract_material(PolicyContractBindingV2.current()),
        "draft": {
            "version_id": str(draft_snapshot.version_id),
            "display_id": draft_snapshot.display_id.value,
            "article_id": str(draft_snapshot.article_id),
            "version_no": draft_snapshot.version_no,
            "article_type": draft_snapshot.article_type.value,
            "title": draft_snapshot.title,
            "source_packet_version_id": str(draft_snapshot.source_packet_version_id),
            "source_packet_verification": (
                draft_snapshot.source_packet_verification.value
            ),
            "based_on_version_id": None,
            "content_ast": json.loads(dump_content_ast_json(content_ast)),
            "body_sha256": draft_snapshot.body_sha256.value,
            "state": draft_snapshot.state.value,
            "version": draft_snapshot.version.value,
            "etag": draft_snapshot.etag.value,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": created_at.isoformat().replace("+00:00", "Z"),
            "canonical_ast_sha256": draft.canonical_ast_sha256.value,
            "binding_sha256": draft.binding_sha256.value,
        },
        "coverage": {
            "request": claim_raw,
            "report": json.loads(coverage_report.canonical_bytes()),
            "receipt": {
                "sequence": coverage_receipt.sequence,
                "report_sha256": coverage_receipt.report_sha256.value,
                "publication_authorized": False,
            },
        },
        "recommendation": {
            "request": recommendation_raw,
            "report": json.loads(recommendation_report.canonical_bytes()),
            "receipt": {
                "sequence": recommendation_receipt.sequence,
                "report_sha256": recommendation_receipt.report_sha256.value,
                "publication_authorized": False,
                "ranking_authorized": False,
            },
        },
        "policy_seed": policy_seed,
        "declared_hashes": {
            "coverage_report_sha256": coverage_report.report_sha256.value,
            "coverage_receipt_sha256": coverage_receipt_sha256(coverage_receipt).value,
            "recommendation_report_sha256": recommendation_report.report_sha256.value,
            "recommendation_receipt_sha256": recommendation_receipt_sha256(
                recommendation_receipt
            ).value,
            "policy_result_sha256": policy_digest.value,
            "evaluation_input_sha256": input_digest.value,
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
    loaded = load_recorded_policy_fixture(payload)
    report = evaluate_editorial_policy_v2(loaded)
    report.require_valid()
    if (
        report.status is not PolicyEvaluationStatusV2.LOCAL_EVALUATED
        or report.findings
        or not report.local_eligibility
    ):
        _fail("POLICY_FIXTURE_NOT_LOCAL_EVALUATED")
    expected = PolicyEvaluationEnvelopeV2(
        contract=PolicyContractBindingV2.current(),
        draft=draft,
        coverage_snapshot=coverage_snapshot,
        coverage_report=coverage_report,
        coverage_receipt=coverage_receipt,
        recommendation=recommendation,
        recommendation_report=recommendation_report,
        recommendation_receipt=recommendation_receipt,
        policy_input=policy_input,
        policy_result_sha256=policy_digest,
        evaluation_input_sha256=input_digest,
    )
    if (
        evaluate_editorial_policy_v2(expected).canonical_bytes()
        != report.canonical_bytes()
    ):
        _fail("POLICY_FIXTURE_ROUND_TRIP_INVALID")
    return payload


def _artifact(root: Path, relative: Path, *, role: str) -> dict[str, object]:
    payload = _read_regular(_safe_path(root, relative))
    media_type = {
        ".json": "application/json",
        ".yaml": "application/yaml",
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
    canonical = {path for path, _digest_value in CANONICAL_BINDINGS}
    dependencies = {path for path, _digest_value in DEPENDENCY_BINDINGS}
    sources = [
        _artifact(
            root,
            path,
            role=(
                "OWNER_SOURCE"
                if path in OWNED_SOURCE_PATHS
                else "CANONICAL_INPUT"
                if path in canonical
                else "DEPENDENCY_CONTRACT"
                if path in dependencies
                else "RUNTIME_DEPENDENCY"
                if path in RUNTIME_DEPENDENCY_PATHS
                else "LOCKED_TOOLCHAIN"
            ),
        )
        for path in SOURCE_PATHS
    ]
    document = {
        "schema_version": 2,
        "story_id": "ST-0805",
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "classification": "LOCAL_EXECUTABLE_RECORDED_EDITORIAL_POLICY_RUNTIME_MANIFEST_V2",
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
            "command": ".venv/bin/python scripts/build_st0805_policy_runtime.py",
            "check_command": (
                ".venv/bin/python scripts/build_st0805_policy_runtime.py --check"
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
            "finding_proposal_only": True,
            "waiver_proposal_only": True,
            "approval_authorized": False,
            "waiver_apply_authorized": False,
            "merge_authorized": False,
            "recommendation_override_authorized": False,
            "ranking_override_authorized": False,
            "publication_authorized": False,
            "activation_authorized": False,
            "production_eligible": False,
            "formal_tst_019_status": "NOT_EXECUTED",
            "formal_tst_020_status": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def _replace_generated(artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    try:
        secure_generated_publication.publish_generated(
            artifacts,
            namespace="st0805",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    _validate_toolchain()
    contract = load_contract(root)
    fixture = _build_fixture(root, contract)
    expected = (
        (FIXTURE_PATH, fixture),
        (MANIFEST_PATH, _manifest_bytes(root, fixture)),
    )
    if check:
        for relative, payload in expected:
            if _read_regular(_safe_path(root, relative)) != payload:
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
        print("ST-0805 V2 runtime generation failed", file=sys.stderr)
        return 1
    print(
        "ST-0805 V2 runtime checked"
        if arguments.check
        else "ST-0805 V2 runtime generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
