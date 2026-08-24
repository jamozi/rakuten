#!/usr/bin/env python3
"""Generate the deterministic recorded ST-0605 runtime fixture and manifest."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.adapters.recorded_claim_evidence import (  # noqa: E402
    load_recorded_claim_evidence_fixture,
)
from raos.domain.evidence.claim_evidence import (  # noqa: E402
    CLAIM_SET_PROFILE,
    EVALUATOR_VERSION,
    POLICY_DOCUMENT_ID,
    POLICY_SHA256,
    POLICY_VERSION,
    CoverageStatus,
    PolicyClaimType,
    PolicyLinkSupportType,
    PolicySourceTier,
    ValidationAttestationKind,
    complete_claim_set_sha256,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
EXPECTED_PYTEST_VERSION: Final = "9.1.1"
EXPECTED_PYDANTIC_VERSION: Final = "2.13.4"
EXPECTED_PYDANTIC_CORE_VERSION: Final = "2.46.4"
CONTRACT_PATH: Final = Path("changes/st-0605/contracts/claim-evidence-runtime.v1.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-0605/generated/claim-evidence-runtime-pass.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0605/runtime-manifest.v1.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0605_claim_evidence_runtime.py")
RUNTIME_DOCUMENTATION_PATH: Final = Path("changes/st-0605/RUNTIME.md")
ST0604_CURRENT_CONTRACT_PATH: Final = Path(
    "changes/st-0604/contracts/source-packet-lifecycle-runtime.v2.json"
)
ST0604_CURRENT_CONTRACT_VERSION: Final = "SOURCE-PACKET-LIFECYCLE-RUNTIME@2.0.0"
ST0604_CURRENT_CONTRACT_SHA256: Final = (
    "719f5366eced10c19a16dc11355d92680fb66dfe08bebce5be5251618e79cfbe"
)
SOURCE_BINDINGS: Final = (
    (
        Path(
            "contracts/raos-v0.4/contracts/content/"
            "RAOS_06_claim_evidence_policy_v0.1.yaml"
        ),
        POLICY_SHA256,
    ),
    (
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_content_test_matrix_v0.1.csv"
        ),
        "9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564",
    ),
    (
        Path("contracts/raos-v0.4/contracts/content/schemas/claim.schema.json"),
        "db1004163eaf42eb88ba1c7336b6da43e6e2f90ceb390d396003d5b0c58ccde3",
    ),
    (
        Path("changes/st-0304/generated/domain-catalog.v1.json"),
        "41d0c9c4ba94aaf65587687a31bbab1caa05a8fed1d323d99991363013258208",
    ),
    (
        Path(
            "contracts/raos-v0.4/contracts/schemas/ai/"
            "claim-extraction-output.schema.json"
        ),
        "0b82454a43c2c5aed37f2fe72f74d1e124dfb1f7fe1ee2fb9c996827d1c2bd75",
    ),
)
IMPLEMENTATION_INPUT_BINDINGS: Final = (
    (
        Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
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
        Path("docs/canonical/05_test/RAOS_11_acceptance_traceability_v1.0.csv"),
        "253293a34e91b81d88dee103da8ee77ed5ff604689c3eb434f0c0ae231d50341",
    ),
    (
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
)
ATTESTATION_OWNER_BINDINGS: Final[
    tuple[tuple[ValidationAttestationKind, str, str, Path, str], ...]
] = (
    (
        ValidationAttestationKind.CLAIM_INVENTORY,
        "ST-0605",
        "RAOS-CONTENT-EVIDENCE-001@1.0.0",
        SOURCE_BINDINGS[0][0],
        POLICY_SHA256,
    ),
    (
        ValidationAttestationKind.ARTICLE_PACKET_BINDING,
        "ST-0802",
        "RESOURCE-CONTRACTS@0.4",
        Path("contracts/raos-v0.4/contracts/catalogs/resource-contracts.v0.4.yaml"),
        "aa53bf68b125821a46c093e653464e7f80e5710e31f6f860251aa8ebc30480c0",
    ),
    (
        ValidationAttestationKind.PACKET_APPROVAL_MEMBERSHIP,
        "ST-0604",
        ST0604_CURRENT_CONTRACT_VERSION,
        ST0604_CURRENT_CONTRACT_PATH,
        ST0604_CURRENT_CONTRACT_SHA256,
    ),
    (
        ValidationAttestationKind.FACT_VALIDATION,
        "ST-0602",
        "FACT-EXTRACTION-VALIDATION-REFERENCE-PLAN@1",
        Path(
            "changes/st-0602/contracts/"
            "fact-extraction-validation-reference-plan.v1.yaml"
        ),
        "c7d7c16ee41a3d3ba5203c9cb091cc6f09fd1556400abb0d42438434d8bea073",
    ),
    (
        ValidationAttestationKind.CONFLICT_CLOSURE,
        "ST-0603",
        "FACT-CONFLICT-REVIEW-REFERENCE-PLAN@1",
        Path("changes/st-0603/contracts/fact-conflict-review-reference-plan.v1.yaml"),
        "bca7c63e49be113d7e2b7d15017d22ad6a9b27c59509325b2bbca407081246ef",
    ),
    (
        ValidationAttestationKind.IDENTITY_DECISION,
        "ST-0504",
        "PRODUCT-IDENTITY-HUMAN-REVIEW-REFERENCE-PLAN@1",
        Path(
            "changes/st-0504/contracts/"
            "product-identity-human-review-reference-plan.v1.yaml"
        ),
        "9e73f7e436ab14df75394b2337e853f1dcbf553c16e0f950a8bdb604da685304",
    ),
    (
        ValidationAttestationKind.DERIVATION,
        "ST-0602",
        "FACT-EXTRACTION-VALIDATION-REFERENCE-PLAN@1",
        Path(
            "changes/st-0602/contracts/"
            "fact-extraction-validation-reference-plan.v1.yaml"
        ),
        "c7d7c16ee41a3d3ba5203c9cb091cc6f09fd1556400abb0d42438434d8bea073",
    ),
    (
        ValidationAttestationKind.COMPARISON,
        "ST-0803",
        "COMPARISON-TABLE-SCHEMA@1",
        Path(
            "contracts/raos-v0.4/contracts/content/schemas/blocks/"
            "comparison_table.schema.json"
        ),
        "6da40ea538bd467a759613e0dca62f2e822ac4a9609adb71959d8bb624037c89",
    ),
    (
        ValidationAttestationKind.RECOMMENDATION,
        "ST-0804",
        "RECOMMENDATION-METHODOLOGY@0.1",
        Path(
            "contracts/raos-v0.4/contracts/content/"
            "RAOS_06_recommendation_methodology_v0.1.yaml"
        ),
        "fb71ad7900c7f688f305e10256b49563281893408e54d8668aac02efa7e57862",
    ),
    (
        ValidationAttestationKind.EXPERIENCE,
        "ST-0605",
        "FIRST-HAND-EXPERIENCE-RECORD@1",
        Path(
            "contracts/raos-v0.4/contracts/schemas/content-revision/"
            "first-hand-experience-record.v1.schema.json"
        ),
        "34dcb19731e44c3aa8a6991503cb78933461866f6393635d118eae9143f2f4ce",
    ),
    (
        ValidationAttestationKind.OFFER_FRESHNESS,
        "ST-1401",
        "FRESHNESS-UPDATE-POLICY@0.1",
        Path(
            "contracts/raos-v0.4/contracts/content/"
            "RAOS_06_freshness_update_policy_v0.1.yaml"
        ),
        "a4d490d2a54b3def63c9c240b09d34a759ebd3924e60cfcca438ee979334cea2",
    ),
    (
        ValidationAttestationKind.SAFETY_COMPLIANCE,
        "ST-0805",
        "EDITORIAL-POLICY-CATALOG@0.1",
        Path(
            "contracts/raos-v0.4/contracts/content/"
            "RAOS_06_editorial_policy_catalog_v0.1.yaml"
        ),
        "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a",
    ),
)
ATTESTATION_OWNER_INPUT_BINDINGS: Final[tuple[tuple[Path, str], ...]] = (
    (ATTESTATION_OWNER_BINDINGS[1][3], ATTESTATION_OWNER_BINDINGS[1][4]),
    (ATTESTATION_OWNER_BINDINGS[2][3], ATTESTATION_OWNER_BINDINGS[2][4]),
    (ATTESTATION_OWNER_BINDINGS[3][3], ATTESTATION_OWNER_BINDINGS[3][4]),
    (ATTESTATION_OWNER_BINDINGS[4][3], ATTESTATION_OWNER_BINDINGS[4][4]),
    (ATTESTATION_OWNER_BINDINGS[5][3], ATTESTATION_OWNER_BINDINGS[5][4]),
    (ATTESTATION_OWNER_BINDINGS[7][3], ATTESTATION_OWNER_BINDINGS[7][4]),
    (ATTESTATION_OWNER_BINDINGS[8][3], ATTESTATION_OWNER_BINDINGS[8][4]),
    (ATTESTATION_OWNER_BINDINGS[9][3], ATTESTATION_OWNER_BINDINGS[9][4]),
    (ATTESTATION_OWNER_BINDINGS[10][3], ATTESTATION_OWNER_BINDINGS[10][4]),
    (ATTESTATION_OWNER_BINDINGS[11][3], ATTESTATION_OWNER_BINDINGS[11][4]),
)
DIRECT_EXECUTABLE_DEPENDENCY_PATHS: Final = (
    Path("python/raos/config/runtime.py"),
    Path("python/raos/domain/editorial/ids.py"),
    Path("python/raos/domain/evidence/enums.py"),
    Path("python/raos/domain/evidence/ids.py"),
    Path("python/raos/domain/shared/identity.py"),
    Path("python/raos/domain/shared/json_values.py"),
    Path("python/raos/domain/shared/persistence.py"),
)
RUNTIME_PACKAGE_BOUNDARY_PATHS: Final = (
    Path("python/raos/__init__.py"),
    Path("python/raos/adapters/__init__.py"),
    Path("python/raos/config/__init__.py"),
    Path("python/raos/domain/editorial/__init__.py"),
    Path("python/raos/domain/shared/__init__.py"),
    Path("python/raos/ports/__init__.py"),
    Path("python/raos/ports/evidence/__init__.py"),
)
LOCKED_TOOLCHAIN_PATHS: Final = (
    Path("pyproject.toml"),
    Path("uv.lock"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    *(path for path, _digest in SOURCE_BINDINGS),
    *(path for path, _digest in IMPLEMENTATION_INPUT_BINDINGS),
    *(path for path, _digest in ATTESTATION_OWNER_INPUT_BINDINGS),
    Path("python/raos/domain/evidence/claim_evidence.py"),
    Path("python/raos/ports/evidence/claim_evidence.py"),
    Path("python/raos/application/evidence/claim_evidence.py"),
    Path("python/raos/application/evidence/__init__.py"),
    Path("python/raos/adapters/recorded_claim_evidence.py"),
    *DIRECT_EXECUTABLE_DEPENDENCY_PATHS,
    *RUNTIME_PACKAGE_BOUNDARY_PATHS,
    *LOCKED_TOOLCHAIN_PATHS,
    RUNTIME_DOCUMENTATION_PATH,
    Path("docs/execplans/ST-0605.md"),
    Path("docs/worklogs/ST-0605.md"),
    Path("tests/st0605_runtime/__init__.py"),
    Path("tests/st0605_runtime/conftest.py"),
    Path("tests/st0605_runtime/test_claim_evidence.py"),
    Path("tests/st0605_runtime/test_application_and_adapter.py"),
    Path("tests/st0605_runtime/test_generation.py"),
    Path("tests/st0605_runtime/test_static_boundary.py"),
)
GENERATED_PATHS: Final = (FIXTURE_PATH, MANIFEST_PATH)
MAX_CONTRACT_BYTES: Final = 1_048_576
TOP_LEVEL_KEYS: Final = (
    "schema_version",
    "story_id",
    "classification",
    "runtime",
    "policy_binding",
    "thresholds",
    "vocabulary_boundary",
    "precedence",
    "source_bindings",
    "fixture",
    "execution_boundary",
    "verification_boundary",
)


class RuntimeGenerationError(ValueError):
    __slots__ = ()

    def __init__(self, code: str) -> None:
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise RuntimeGenerationError(code) from None


def _validate_generation_toolchain() -> None:
    if (
        sys.implementation.name != EXPECTED_PYTHON_IMPLEMENTATION
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
    ):
        _fail("GENERATION_PYTHON_TOOLCHAIN_DRIFT")
    if getattr(yaml, "__version__", None) != EXPECTED_PYYAML_VERSION:
        _fail("GENERATION_PYYAML_TOOLCHAIN_DRIFT")
    expected_distributions = (
        ("PyYAML", EXPECTED_PYYAML_VERSION, "GENERATION_PYYAML_TOOLCHAIN_DRIFT"),
        (
            "pydantic",
            EXPECTED_PYDANTIC_VERSION,
            "GENERATION_PYDANTIC_TOOLCHAIN_DRIFT",
        ),
        (
            "pydantic-core",
            EXPECTED_PYDANTIC_CORE_VERSION,
            "GENERATION_PYDANTIC_CORE_TOOLCHAIN_DRIFT",
        ),
        ("pytest", EXPECTED_PYTEST_VERSION, "GENERATION_PYTEST_TOOLCHAIN_DRIFT"),
    )
    for distribution, expected, code in expected_distributions:
        try:
            observed = distribution_version(distribution)
        except PackageNotFoundError:
            _fail(code)
        if observed != expected:
            _fail(code)


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = cast(
            object,
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                key_node, deep=deep
            ),
        )
        if key in result:
            _fail("DUPLICATE_YAML_KEY")
        result[key] = loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
            value_node, deep=deep
        )
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _safe_file(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("UNSAFE_PATH")
    root = root.resolve()
    candidate = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            _fail("SYMLINK_REJECTED")
    return candidate


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _matches_exact(value: object, expected: object) -> bool:
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        value_mapping = cast(dict[object, object], value)
        expected_mapping = cast(dict[object, object], expected)
        return tuple(value_mapping) == tuple(expected_mapping) and all(
            _matches_exact(value_mapping[key], expected_mapping[key])
            for key in expected_mapping
        )
    if type(expected) is list:
        value_items = cast(list[object], value)
        expected_items = cast(list[object], expected)
        return len(value_items) == len(expected_items) and all(
            _matches_exact(observed, wanted)
            for observed, wanted in zip(value_items, expected_items, strict=True)
        )
    return value == expected


def _require_exact(value: object, expected: object, code: str) -> None:
    if not _matches_exact(value, expected):
        _fail(code)


def _load_closed_json_object(root: Path, relative: Path) -> dict[str, Any]:
    path = _safe_file(root, relative)
    try:
        payload = path.read_bytes()
    except OSError:
        _fail("ST0604_RUNTIME_CONTRACT_INVALID")
    if not payload or len(payload) > MAX_CONTRACT_BYTES:
        _fail("ST0604_RUNTIME_CONTRACT_INVALID")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("ST0604_RUNTIME_CONTRACT_INVALID")
            result[key] = value
        return result

    try:
        loaded: object = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except RuntimeGenerationError:
        raise
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        _fail("ST0604_RUNTIME_CONTRACT_INVALID")
    if type(loaded) is not dict:
        _fail("ST0604_RUNTIME_CONTRACT_INVALID")
    return cast(dict[str, Any], loaded)


def _validate_st0604_runtime_semantics(root: Path) -> None:
    document = _load_closed_json_object(root, ST0604_CURRENT_CONTRACT_PATH)
    _require_exact(
        {
            "schema_version": document.get("schema_version"),
            "story_id": document.get("story_id"),
            "classification": document.get("classification"),
            "local_implementation_status": document.get("local_implementation_status"),
            "canonical_status": document.get("canonical_status"),
        },
        {
            "schema_version": "2.0.0",
            "story_id": "ST-0604",
            "classification": (
                "MAXIMUM_SAFE_RECORDED_LOCAL_DURABLE_SOURCE_PACKET_LIFECYCLE"
            ),
            "local_implementation_status": "LOCAL_CODE_COMPLETE",
            "canonical_status": "UNCHANGED",
        },
        "ST0604_RUNTIME_SEMANTIC_DRIFT",
    )
    _require_exact(
        document.get("approval_binding"),
        {
            "human_recorded_authorization_required": True,
            "active_session_recovery_required": True,
            "exact_packet_version_content_sha256": True,
            "exact_ST0602_fact_membership_sha256": True,
            "exact_ST0603_no_open_conflict_scan_sha256": True,
            "exact_ST0403_authorization_audit_digest": True,
            "reviewer_session_fingerprint_bound": True,
            "deny_default": True,
            "synthetic_or_recorded_local_only": True,
        },
        "ST0604_RUNTIME_SEMANTIC_DRIFT",
    )
    _require_exact(
        document.get("generation_gate"),
        {
            "required_current": True,
            "required_status": "APPROVED",
            "required_lock": True,
            "required_open_conflict_count": 0,
            "required_conflict_queue_count": 0,
            "unapproved_cannot_generate": True,
            "noncurrent_cannot_generate": True,
            "unlocked_cannot_generate": True,
            "rejected_cannot_generate": True,
            "dedicated_output_type": "ApprovedLockedGenerationInputV2",
        },
        "ST0604_RUNTIME_SEMANTIC_DRIFT",
    )
    _require_exact(
        document.get("authority_boundary"),
        {
            "ai": False,
            "network": False,
            "provider": False,
            "publication": False,
            "ranking": False,
            "recommendation": False,
            "revenue": False,
            "credential_read": False,
            "staging": False,
            "release": False,
            "production": False,
            "external_action_count": 0,
            "provider_action_count": 0,
            "publication_action_count": 0,
            "ai_action_count": 0,
            "production_authority": "NONE",
        },
        "ST0604_RUNTIME_SEMANTIC_DRIFT",
    )


def _expected_source_bindings() -> list[dict[str, str]]:
    return [
        {"path": path.as_posix(), "sha256": digest} for path, digest in SOURCE_BINDINGS
    ]


def _validate_policy_source_identity(root: Path) -> None:
    policy_path, policy_digest = SOURCE_BINDINGS[0]
    source = _safe_file(root, policy_path)
    payload = source.read_bytes()
    if hashlib.sha256(payload).hexdigest() != policy_digest:
        _fail("SOURCE_HASH_DRIFT")
    try:
        loaded = yaml.load(payload, Loader=_UniqueLoader)
    except RuntimeGenerationError:
        raise
    except Exception:
        _fail("POLICY_SOURCE_PARSE_FAILED")
    if type(loaded) is not dict:
        _fail("POLICY_SOURCE_IDENTITY_INVALID")
    policy = cast(dict[object, object], loaded)
    document = policy.get("document")
    if type(document) is not dict:
        _fail("POLICY_SOURCE_IDENTITY_INVALID")
    identity = cast(dict[object, object], document)
    if (
        type(identity.get("id")) is not str
        or identity.get("id") != POLICY_DOCUMENT_ID
        or type(policy.get("policy_version")) is not str
        or policy.get("policy_version") != POLICY_VERSION
    ):
        _fail("POLICY_SOURCE_IDENTITY_INVALID")


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    path = _safe_file(root, CONTRACT_PATH)
    payload = path.read_bytes()
    if not payload or len(payload) > MAX_CONTRACT_BYTES:
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
        loaded = yaml.load(payload, Loader=_UniqueLoader)
    except RuntimeGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")
    if type(loaded) is not dict:
        _fail("CONTRACT_SHAPE_INVALID")
    contract = cast(dict[str, Any], loaded)
    if tuple(contract) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SHAPE_INVALID")
    if (
        contract["schema_version"] != 1
        or type(contract["schema_version"]) is not int
        or contract["story_id"] != "ST-0605"
        or contract["classification"]
        != "LOCAL_EXECUTABLE_RECORDED_CLAIM_EVIDENCE_RUNTIME_V1"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")

    exact_sections: tuple[tuple[str, object, str], ...] = (
        (
            "runtime",
            {
                "executable": True,
                "provider_mode": "RECORDED_SYNTHETIC_ONLY",
                "repository_write": False,
                "publication_authorized": False,
                "production_eligible": False,
            },
            "CONTRACT_RUNTIME_INVALID",
        ),
        (
            "policy_binding",
            {
                "policy_document_id": POLICY_DOCUMENT_ID,
                "policy_version": POLICY_VERSION,
                "policy_sha256": POLICY_SHA256,
                "evaluator_version": EVALUATOR_VERSION,
                "claim_set_profile": CLAIM_SET_PROFILE,
            },
            "CONTRACT_POLICY_BINDING_INVALID",
        ),
        (
            "thresholds",
            {
                "major": {"evidenced_numerator": 1, "total_denominator": 1},
                "all_verifiable": {
                    "evidenced_numerator": 95,
                    "total_denominator": 100,
                },
                "arithmetic": "INTEGER_CROSS_MULTIPLICATION",
                "zero_denominator": "UNEVALUABLE",
            },
            "CONTRACT_THRESHOLDS_INVALID",
        ),
        (
            "vocabulary_boundary",
            {
                "policy_claim_types": [item.value for item in PolicyClaimType],
                "policy_source_tiers": [item.value for item in PolicySourceTier],
                "policy_link_support_types": [
                    item.value for item in PolicyLinkSupportType
                ],
                "inferred_persistence_mapping": False,
                "inferred_ai_mapping": False,
            },
            "CONTRACT_VOCABULARY_INVALID",
        ),
        (
            "precedence",
            {
                "predictive_default": "BLOCKED_IN_MVP",
                "note": (
                    "The explicit Claim-Evidence policy blocking condition "
                    "overrides the generic repeated matrix PASS label."
                ),
            },
            "CONTRACT_PRECEDENCE_INVALID",
        ),
        (
            "execution_boundary",
            {
                "repository_read": "RECORDED_SYNTHETIC_ONLY",
                "result_append": "PROCESS_LOCAL_ONLY",
                "pure_evaluator_authority": "NONE",
                "trusted_snapshot_resolution": "PRELOADED_EXACT_INPUT",
                "recorded_attestation_decision": (
                    "DETERMINISTIC_CORRUPTION_CHECK_NOT_AUTHENTICATION"
                ),
                "article_mutation": "FORBIDDEN",
                "recommendation_mutation": "FORBIDDEN",
                "publication_snapshot_mutation": "FORBIDDEN",
                "network": "FORBIDDEN",
                "credential": "FORBIDDEN",
                "provider": "FORBIDDEN",
            },
            "CONTRACT_EXECUTION_BOUNDARY_INVALID",
        ),
        (
            "verification_boundary",
            {
                "TST-020": "NOT_EXECUTED",
                "TST-021": "NOT_EXECUTED",
                "formal_validation": "NOT_EXECUTED",
                "live": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
            },
            "CONTRACT_VERIFICATION_BOUNDARY_INVALID",
        ),
    )
    for section, expected, code in exact_sections:
        _require_exact(contract[section], expected, code)
    _require_exact(
        contract["source_bindings"],
        _expected_source_bindings(),
        "SOURCE_BINDING_INVALID",
    )
    policy_binding = cast(dict[str, object], contract["policy_binding"])
    first_binding = _expected_source_bindings()[0]
    if policy_binding["policy_sha256"] != first_binding["sha256"]:
        _fail("POLICY_CROSS_BINDING_INVALID")
    for source_path, digest in SOURCE_BINDINGS:
        source = _safe_file(root, source_path)
        if not source.is_file() or _sha(source) != digest:
            _fail("SOURCE_HASH_DRIFT")
    for source_path, digest in IMPLEMENTATION_INPUT_BINDINGS:
        source = _safe_file(root, source_path)
        if not source.is_file() or _sha(source) != digest:
            _fail("IMPLEMENTATION_INPUT_HASH_DRIFT")
    if tuple(row[0] for row in ATTESTATION_OWNER_BINDINGS) != tuple(
        ValidationAttestationKind
    ):
        _fail("ATTESTATION_OWNER_BINDING_INVALID")
    for (
        kind,
        expected_owner,
        expected_version,
        source_path,
        expected_digest,
    ) in ATTESTATION_OWNER_BINDINGS:
        owner, version, observed_digest = validation_attestation_owner_binding(kind)
        if (
            owner != expected_owner
            or version != expected_version
            or observed_digest.value != expected_digest
        ):
            _fail("ATTESTATION_OWNER_BINDING_INVALID")
        source = _safe_file(root, source_path)
        if not source.is_file() or _sha(source) != expected_digest:
            _fail("ATTESTATION_OWNER_SOURCE_HASH_DRIFT")
    _validate_st0604_runtime_semantics(root)
    _validate_policy_source_identity(root)
    return contract


def _fixture_bytes(contract: dict[str, Any]) -> bytes:
    fixture = json.loads(json.dumps(contract["fixture"], ensure_ascii=True))
    provisional = dict(fixture)
    article = dict(provisional["article"])
    article["complete_claim_set_sha256"] = "0" * 64
    provisional["article"] = article
    provisional_bytes = json.dumps(
        provisional,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    snapshot = load_recorded_claim_evidence_fixture(provisional_bytes)
    digest = complete_claim_set_sha256(snapshot.claims)
    article["complete_claim_set_sha256"] = digest.value
    fixture["article"] = article
    fixture["attestations"] = []
    snapshot_without_attestations = load_recorded_claim_evidence_fixture(
        json.dumps(
            fixture,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    )
    attestations: list[dict[str, object]] = []
    for kind, subject, input_digest in required_validation_attestation_inputs(
        snapshot_without_attestations
    ):
        owner, version, contract_digest = validation_attestation_owner_binding(kind)
        decision_digest = recorded_synthetic_attestation_decision_sha256(
            kind,
            subject,
            input_digest,
        ).value
        attestations.append(
            {
                "kind": kind.value,
                "owner_story_id": owner,
                "contract_version": version,
                "contract_sha256": contract_digest.value,
                "origin": "RECORDED_SYNTHETIC_ONLY",
                "subject_sha256": subject.value,
                "input_sha256": input_digest.value,
                "decision_sha256": decision_digest,
                "validated_at": "2026-08-23T23:00:00Z",
                "valid": True,
            }
        )
    fixture["attestations"] = attestations
    payload = (
        json.dumps(
            fixture,
            ensure_ascii=True,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("ascii")
    verified = load_recorded_claim_evidence_fixture(payload)
    report = evaluate_claim_evidence(verified)
    if report.status is not CoverageStatus.PASS or report.findings:
        _fail("RECORDED_FIXTURE_NOT_PASSING")
    return payload


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    path = _safe_file(root, relative)
    payload = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _manifest_bytes(root: Path, fixture: bytes) -> bytes:
    sources = [_artifact(root, path) for path in SOURCE_PATHS]
    document = {
        "schema_version": 1,
        "story_id": "ST-0605",
        "classification": "LOCAL_EXECUTABLE_RECORDED_CLAIM_EVIDENCE_RUNTIME_MANIFEST_V1",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "bytes": len(fixture),
                "sha256": hashlib.sha256(fixture).hexdigest(),
            }
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": (
                ".venv/bin/python scripts/build_st0605_claim_evidence_runtime.py"
            ),
            "toolchain": {
                "lock": "repo://uv.lock",
                "project": "repo://pyproject.toml",
                "python_implementation": "CPython",
                "python_version": ".".join(
                    str(part) for part in EXPECTED_PYTHON_VERSION
                ),
                "pyyaml_version": EXPECTED_PYYAML_VERSION,
                "pydantic_version": EXPECTED_PYDANTIC_VERSION,
                "pydantic_core_version": EXPECTED_PYDANTIC_CORE_VERSION,
                "pytest_version": EXPECTED_PYTEST_VERSION,
            },
        },
        "authority": {
            "publication_authorized": False,
            "production_eligible": False,
            "formal_test_status": "NOT_EXECUTED",
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


def _stage_payload(path: Path, payload: bytes, *, mode: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        return temporary
    except BaseException:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except BaseException:
                _fail("GENERATION_STAGE_CLEANUP_FAILED")
        raise


def _replace_generated(
    artifacts: tuple[tuple[Path, bytes], ...],
) -> None:
    if (
        not artifacts
        or any(
            not isinstance(path, Path)  # pyright: ignore[reportUnnecessaryIsInstance]
            or type(payload) is not bytes
            for path, payload in artifacts
        )
        or len({path for path, _payload in artifacts}) != len(artifacts)
    ):
        _fail("GENERATION_TRANSACTION_INPUT_INVALID")

    prepared: list[tuple[Path, Path, Path | None]] = []
    committed: list[tuple[Path, Path, Path | None]] = []
    preserve_on_failure: set[Path] = set()
    try:
        for destination, payload in artifacts:
            if destination.is_symlink() or (
                destination.exists() and not destination.is_file()
            ):
                _fail("GENERATION_DESTINATION_INVALID")
            backup: Path | None = None
            if destination.exists():
                current = destination.read_bytes()
                mode = destination.stat().st_mode & 0o777
                backup = _stage_payload(destination, current, mode=mode)
            try:
                staged = _stage_payload(destination, payload, mode=0o644)
            except BaseException:
                if backup is not None:
                    try:
                        backup.unlink(missing_ok=True)
                    except BaseException:
                        _fail("GENERATION_STAGE_CLEANUP_FAILED")
                raise
            prepared.append((destination, staged, backup))

        for row in prepared:
            destination, staged, _backup = row
            # Record the row before replace: an asynchronous BaseException may
            # arrive immediately after the filesystem operation committed.
            committed.append(row)
            os.replace(staged, destination)
    except BaseException as failure:
        rollback_failed = False
        for destination, _staged, backup in reversed(committed):
            try:
                if backup is None:
                    destination.unlink(missing_ok=True)
                else:
                    os.replace(backup, destination)
            except BaseException:
                rollback_failed = True
                if backup is not None:
                    preserve_on_failure.add(backup)
        for _destination, staged, backup in prepared:
            try:
                staged.unlink(missing_ok=True)
            except BaseException:
                rollback_failed = True
            if backup is not None and backup not in preserve_on_failure:
                try:
                    backup.unlink(missing_ok=True)
                except BaseException:
                    rollback_failed = True
        if rollback_failed:
            _fail("GENERATION_ROLLBACK_FAILED")
        if isinstance(failure, Exception):
            _fail("GENERATION_TRANSACTION_FAILED")
        raise

    pending_cleanup = [
        path
        for _destination, staged, backup in prepared
        for path in (staged, backup)
        if path is not None
    ]
    for _attempt in range(2):
        remaining: list[Path] = []
        for path in pending_cleanup:
            try:
                path.unlink(missing_ok=True)
            except BaseException:
                remaining.append(path)
        pending_cleanup = remaining
        if not pending_cleanup:
            return
    _fail("GENERATION_POST_COMMIT_CLEANUP_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    _validate_generation_toolchain()
    contract = load_contract(root)
    fixture = _fixture_bytes(contract)
    expected = (
        (FIXTURE_PATH, fixture),
        (MANIFEST_PATH, _manifest_bytes(root, fixture)),
    )
    if check:
        for relative, payload in expected:
            path = _safe_file(root, relative)
            if not path.is_file() or path.read_bytes() != payload:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    _replace_generated(
        tuple((_safe_file(root, relative), payload) for relative, payload in expected)
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
        print("ST-0605 runtime generation failed", file=sys.stderr)
        return 1
    print("ST-0605 runtime checked" if arguments.check else "ST-0605 runtime generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
