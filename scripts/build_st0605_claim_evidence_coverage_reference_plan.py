#!/usr/bin/env python3
"""Build the non-executable ST-0605 Claim/evidence coverage reference plan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
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
    "changes/st-0605/contracts/claim-evidence-coverage-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0605/generated/claim-evidence-coverage-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0605/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0605_claim_evidence_coverage_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0605/README.md")
TEST_PATHS: Final = (
    Path("tests/st0605/conftest.py"),
    Path("tests/st0605/test_contract.py"),
    Path("tests/st0605/test_generation.py"),
    Path("tests/st0605/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0605_claim_evidence_coverage_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "478c70fcdec48ceca5c9d072c84e4ad3dc55f63e8ccbee0f8e09d4d78eb6fdf5"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
STORY_SHA256: Final = "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
ST0602_COMMIT: Final = "806b978803cbc78392117cbc31015db19ea09a74"
ST0603_COMMIT: Final = "4f4285f0385a14b83e027e9c4527c17b8966bb70"
ST0604_COMMIT: Final = "89d8074951ce73a5c76ca55f0ea3b2c129559d81"

POLICY_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/RAOS_06_claim_evidence_policy_v0.1.yaml"
)
POLICY_SHA256: Final = (
    "fbf2d0ad6e7821a0059f9ceeb53d57268031e2e42b4aad988af9a42378aec5ba"
)
MATRIX_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/RAOS_06_content_test_matrix_v0.1.csv"
)
MATRIX_SHA256: Final = (
    "9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564"
)
CLAIM_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/schemas/claim.schema.json"
)
CLAIM_SCHEMA_SHA256: Final = (
    "db1004163eaf42eb88ba1c7336b6da43e6e2f90ceb390d396003d5b0c58ccde3"
)
PERSISTED_CATALOG_PATH: Final = Path("changes/st-0304/generated/domain-catalog.v1.json")
PERSISTED_CATALOG_SHA256: Final = (
    "41d0c9c4ba94aaf65587687a31bbab1caa05a8fed1d323d99991363013258208"
)
AI_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/ai/claim-extraction-output.schema.json"
)
AI_SCHEMA_SHA256: Final = (
    "0b82454a43c2c5aed37f2fe72f74d1e124dfb1f7fe1ee2fb9c996827d1c2bd75"
)
CONTEXT_SOURCES: Final = (
    (POLICY_PATH, POLICY_SHA256, "CLAIM_EVIDENCE_POLICY_CONTEXT_ONLY"),
    (
        MATRIX_PATH,
        MATRIX_SHA256,
        "CLAIM_EVIDENCE_TEST_MATRIX_EXPECTATIONS_ONLY",
    ),
    (CLAIM_SCHEMA_PATH, CLAIM_SCHEMA_SHA256, "POLICY_CLAIM_SCHEMA_CONTEXT_ONLY"),
    (
        PERSISTED_CATALOG_PATH,
        PERSISTED_CATALOG_SHA256,
        "PERSISTED_CLAIM_LINK_CONTEXT_ONLY",
    ),
    (AI_SCHEMA_PATH, AI_SCHEMA_SHA256, "AI_CLAIM_EXTRACTION_CONTEXT_ONLY"),
)

ST0602_ARTIFACTS: Final = (
    (
        Path("changes/st-0602/README.md"),
        "f3590fb864de262eb1d31769ffe892010f41f98084c27634f099dfca9573f2f8",
    ),
    (
        Path(
            "changes/st-0602/contracts/"
            "fact-extraction-validation-reference-plan.v1.yaml"
        ),
        "c7d7c16ee41a3d3ba5203c9cb091cc6f09fd1556400abb0d42438434d8bea073",
    ),
    (
        Path(
            "changes/st-0602/generated/"
            "fact-extraction-validation-reference-plan.v1.json"
        ),
        "c515af3410be014a714be4d9f9cd133bd320f4c19e5da5820bb3cd6b1a39abb5",
    ),
    (
        Path("changes/st-0602/manifest.yaml"),
        "e4ac2cbe7458035e53356ab0647bcd8439cec4c352297538ef7b595edf5bd18e",
    ),
    (
        Path("scripts/build_st0602_fact_extraction_validation_reference_plan.py"),
        "94947fcde0e2f5d9c972c38dbe9d1fea287659c5a0e7ab329a485eaf61b1e753",
    ),
    (
        Path("tests/st0602/conftest.py"),
        "a687a2fee7033a83b82caa305712a1885a3c66d11d0efc7b761397447746d1c8",
    ),
    (
        Path("tests/st0602/test_contract.py"),
        "8d1fe6cfa6edac6910802a1be71370a2e371144e4b7ca7d4e3a3bc145f66e775",
    ),
    (
        Path("tests/st0602/test_generation.py"),
        "1b5d8314fe24cbe9f76556fb5699d22168f17736ccce982f129de8a2209db2b2",
    ),
    (
        Path("tests/st0602/test_negative_cases.py"),
        "46b65c0b3954da438425f734c7898dccdf39c9dd7445d4b4e15ac682b15c78c9",
    ),
)
ST0603_ARTIFACTS: Final = (
    (
        Path("changes/st-0603/README.md"),
        "22ba200315f8cd36198930842c12f0e17008b979b6f38f850cc534c13af7e071",
    ),
    (
        Path("changes/st-0603/contracts/fact-conflict-review-reference-plan.v1.yaml"),
        "74d58a889c0e20cb74e699196c267b270a86db80667459c9178b04aefe66c093",
    ),
    (
        Path("changes/st-0603/generated/fact-conflict-review-reference-plan.v1.json"),
        "16a934d5a84b0a76e291026be708f6ae15a68523c5c2bdc1d816196eb58ed148",
    ),
    (
        Path("changes/st-0603/manifest.yaml"),
        "f7aadcf22785f96360be081c3754021dc72f4f6ade9570c39a8a53e80afb8a86",
    ),
    (
        Path("scripts/build_st0603_fact_conflict_review_reference_plan.py"),
        "c18ec5df96bfbaa1a18d86cba3fd468221ae1b8fffdf2a5d38dd3a2e9af9b589",
    ),
    (
        Path("tests/st0603/conftest.py"),
        "b0041b91eac50acd6ba109e7218b24886197619130b2ddf5e803e84a5311f977",
    ),
    (
        Path("tests/st0603/test_contract.py"),
        "ad08282af371e0f207bfb54969944b63d52ad9796b016203cabd8c4a3c8b8c8a",
    ),
    (
        Path("tests/st0603/test_generation.py"),
        "30010ac3fb8dc51cb8ff1ebeb87ca689dde607713a43e26c8ebfdca5cb673c77",
    ),
    (
        Path("tests/st0603/test_negative_cases.py"),
        "1aa9580ccfe4a61fc9ad52899f09ca2366a8683a7d45454e92a00c26e6d9504e",
    ),
)
ST0604_ARTIFACTS: Final = (
    (
        Path("changes/st-0604/README.md"),
        "b3d71908781fcdd2d442b3f16ed7fade49780d18bcca688c4b88ee0204c089ff",
    ),
    (
        Path(
            "changes/st-0604/contracts/source-packet-lifecycle-reference-plan.v1.yaml"
        ),
        "5f0fc1d75207535a89e5e50d6b33bc3f710d17e60183e63ab39e394b5e8d049c",
    ),
    (
        Path(
            "changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json"
        ),
        "3c7a7cc6a296c96162847f2bb452bba2ff7048bc8f277dbe720bf19a97fafaee",
    ),
    (
        Path("changes/st-0604/manifest.yaml"),
        "df78078b95d6042a08651cdef6923c01009362655393ab47af39eba2f3e420b6",
    ),
    (
        Path("scripts/build_st0604_source_packet_lifecycle_reference_plan.py"),
        "7e6e1dcb1ea4ddec72b71e246769de940032b97dc86976fa8cc91f47e46ed97f",
    ),
    (
        Path("tests/st0604/conftest.py"),
        "d53440253de34f65e95f9668ac2c8bd3c55855797f99723d848613bd1d3fc04a",
    ),
    (
        Path("tests/st0604/test_contract.py"),
        "68c3fad0196b6fc353dd354c172d32dcc64106474754a54665f362a51b415462",
    ),
    (
        Path("tests/st0604/test_generation.py"),
        "5ed32f62c06924f3f6931fb827a6c68dc4ffcbd415ddc6b8ece54c66e93a9cca",
    ),
    (
        Path("tests/st0604/test_negative_cases.py"),
        "143ea1cf8f9b5558f98c521909be7c1506e8ad6cbda5534edb01c11ef8afdb45",
    ),
)

CONTRACT_KEYS: Final = (
    "schema_version",
    "story_id",
    "classification",
    "status",
    "executable",
    "interface_only",
    "decision",
    "production_eligible",
    "approval",
    "story_acceptance",
    "publication_permitted",
    "canonical_story_status",
    "authority",
    "predecessors",
    "source_bindings",
    "vocabulary_context",
    "coverage_policy",
    "selection_defaults",
    "collection_defaults",
    "coverage_defaults",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_bindings",
    "source_bindings",
    "vocabulary_context",
    "coverage_policy",
    "matrix_projection",
    "selection_boundary",
    "collection_boundary",
    "coverage_boundary",
    "execution_boundary",
    "verification_boundary",
)
ACTION_COUNT_KEYS: Final = (
    "create_claim",
    "create_link",
    "select_source",
    "create_citation",
    "map_vocabulary",
    "evaluate_matrix",
    "calculate_coverage",
    "repository_write",
    "database_write",
    "enqueue_job",
    "emit_event",
    "call_api",
    "publish",
    "external",
)


class ClaimEvidenceCoverageReferenceError(RuntimeError):
    """Stable sanitized ST-0605 contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise ClaimEvidenceCoverageReferenceError(
        f"ST-0605 build failed: {code} field={field}"
    )


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return cast(dict[str, Any], value)


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return cast(list[Any], value)  # type: ignore[redundant-cast]


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
    physical = base._repository_regular_file(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        root, relative, field
    )
    try:
        content: bytes = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        root, relative, field
    )
    return _mapping(base.load_yaml(root / relative), field)


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(_read(root, relative, field))
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", field)
    return _mapping(parsed, field)


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for item in _list(items, field):
        if type(item) is not dict:
            continue
        row = cast(dict[str, Any], item)
        if row.get("id") == identity:
            matches.append(row)
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _find_fully_qualified(
    value: object, identity: str, field: str
) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []

    def visit(item: object) -> None:
        if type(item) is dict:
            row = cast(dict[str, object], item)
            if row.get("fully_qualified_name") == identity:
                matches.append(row)
            for child in row.values():
                visit(child)
        elif type(item) is list:
            for child in cast(list[object], item):
                visit(child)

    visit(value)
    if len(matches) != 1:
        _fail("SOURCE_RECORD_MISSING", field)
    return matches[0]


def _artifact_rows(
    artifacts: Sequence[tuple[Path, str]],
) -> list[dict[str, str]]:
    return [{"path": path.as_posix(), "sha256": digest} for path, digest in artifacts]


def _artifact_uri_rows(
    artifacts: Sequence[tuple[Path, str]],
) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in artifacts
    ]


EXPECTED_STORY: Final[dict[str, object]] = {
    "id": "ST-0605",
    "epic_id": "EPIC-06",
    "title": "Claim/evidence service",
    "objective": "ClaimとFactのLink/Coverage",
    "depends_on": ["ST-0604"],
    "requirement_ids": ["FR-007"],
    "design_refs": [],
    "deliverables": ["claim service", "coverage"],
    "acceptance_criteria": ["major 100% rule"],
    "test_suites": ["TST-020", "TST-021"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": [],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_AUTHORITY: Final[dict[str, object]] = {
    "canonical_story_path": STORY_PATH.as_posix(),
    "canonical_story_sha256": STORY_SHA256,
    "objective": "ClaimとFactのLink/Coverage",
    "requirement_ids": ["FR-007"],
    "acceptance_criteria": ["major 100% rule"],
    "test_suites": ["TST-020", "TST-021"],
}
EXPECTED_ST0602_SEMANTICS: Final[dict[str, object]] = {
    "decision": "NOT_READY",
    "facts": [],
    "fact_ids": [],
    "derivations": [],
    "fact_count": None,
    "derivation_count": None,
    "extraction": "NOT_EXECUTED",
    "validation": "NOT_EXECUTED",
}
EXPECTED_ST0603_SEMANTICS: Final[dict[str, object]] = {
    "decision": "NOT_READY",
    "facts": [],
    "fact_ids": [],
    "comparisons": [],
    "conflicts": [],
    "findings": [],
    "queue": [],
    "resolutions": [],
    "fact_count": None,
    "comparison_count": None,
    "conflict_count": None,
    "finding_count": None,
    "queue_count": None,
    "resolution_count": None,
}
EXPECTED_ST0604_SEMANTICS: Final[dict[str, object]] = {
    "decision": "NOT_READY",
    "packets": [],
    "versions": [],
    "jobs": [],
    "transitions": [],
    "mappings": [],
    "reviews": [],
    "approvals": [],
    "artifacts": [],
    "packet_count": None,
    "version_count": None,
    "job_count": None,
    "transition_count": None,
    "mapping_count": None,
    "review_count": None,
    "approval_count": None,
    "artifact_count": None,
    "transition_status": "UNAVAILABLE",
    "mapping_status": "UNAVAILABLE",
    "approval": False,
    "generation_permitted": False,
}


def _expected_predecessors() -> list[dict[str, object]]:
    return [
        {
            "story_id": "ST-0602",
            "commit": ST0602_COMMIT,
            "relationship": "EMPTY_FACT_INPUT_REFERENCE_ONLY",
            "files": _artifact_rows(ST0602_ARTIFACTS),
            "required_semantics": EXPECTED_ST0602_SEMANTICS,
        },
        {
            "story_id": "ST-0603",
            "commit": ST0603_COMMIT,
            "relationship": "EMPTY_CONFLICT_INPUT_REFERENCE_ONLY",
            "files": _artifact_rows(ST0603_ARTIFACTS),
            "required_semantics": EXPECTED_ST0603_SEMANTICS,
        },
        {
            "story_id": "ST-0604",
            "commit": ST0604_COMMIT,
            "relationship": "EMPTY_UNAPPROVED_PACKET_REFERENCE_ONLY",
            "files": _artifact_rows(ST0604_ARTIFACTS),
            "required_semantics": EXPECTED_ST0604_SEMANTICS,
        },
    ]


def _expected_source_bindings() -> list[dict[str, str]]:
    return [
        {"relationship": relationship, "path": path.as_posix(), "sha256": digest}
        for path, digest, relationship in CONTEXT_SOURCES
    ]


POLICY_SOURCE_TIERS: Final[list[str]] = [
    "SRC-TIER-A",
    "SRC-TIER-B",
    "SRC-TIER-C",
    "SRC-TIER-D",
    "SRC-DISCOVERY",
    "SRC-EXCLUDED",
]
POLICY_CLAIM_TYPES: Final[list[str]] = [
    "direct_fact",
    "derived_fact",
    "comparative",
    "recommendation",
    "experience",
    "price_availability",
    "superlative",
    "safety_legal_regulatory",
    "predictive",
]
PERSISTED_CLAIM_TYPES: Final[list[str]] = [
    "FACTUAL",
    "COMPARATIVE",
    "RECOMMENDATION",
    "DISCLOSURE",
    "EXPERIENCE",
    "OPINION",
]
PERSISTED_CRITICALITIES: Final[list[str]] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
PERSISTED_SUPPORT_STATUSES: Final[list[str]] = [
    "PENDING",
    "SUPPORTED",
    "PARTIAL",
    "UNSUPPORTED",
    "CONFLICT",
    "NOT_REQUIRED",
]
PERSISTED_LINK_SUPPORT_TYPES: Final[list[str]] = [
    "SUPPORTS",
    "QUALIFIES",
    "CONTRADICTS",
]
AI_CRITICALITIES: Final[list[str]] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
AI_SUPPORT_STATUSES: Final[list[str]] = [
    "SUPPORTED",
    "PARTIAL",
    "UNSUPPORTED",
    "CONFLICTING",
]
EXPECTED_VOCABULARY_CONTEXT: Final[dict[str, object]] = {
    "authority": "DESCRIPTIVE_ONLY",
    "creates_runtime_contract": False,
    "policy_source_tier_namespace": {
        "name": "CLAIM_EVIDENCE_POLICY_SOURCE_TIER",
        "values": POLICY_SOURCE_TIERS,
    },
    "policy_claim_type_namespace": {
        "name": "CLAIM_EVIDENCE_POLICY_CLAIM_TYPE",
        "values": POLICY_CLAIM_TYPES,
    },
    "persisted_claim_namespace": {
        "name": "EVIDENCE_CLAIM_CHECK_CONSTRAINT",
        "claim_type_values": PERSISTED_CLAIM_TYPES,
        "criticality_values": PERSISTED_CRITICALITIES,
        "support_status_values": PERSISTED_SUPPORT_STATUSES,
    },
    "persisted_link_namespace": {
        "name": "EVIDENCE_CLAIM_LINK_CHECK_CONSTRAINT",
        "support_type_values": PERSISTED_LINK_SUPPORT_TYPES,
        "support_strength_minimum": 0.0,
        "support_strength_maximum": 1.0,
    },
    "ai_claim_extraction_namespace": {
        "name": "AI_CLAIM_EXTRACTION_OUTPUT",
        "claim_type_enumeration": None,
        "criticality_values": AI_CRITICALITIES,
        "support_status_values": AI_SUPPORT_STATUSES,
    },
    "inferred_mappings": [],
}
EXPECTED_COVERAGE_POLICY: Final[dict[str, object]] = {
    "major_claim_definition": (
        "criticality >= 4 または購買判断・順位・価格・安全・法令に影響するClaim"
    ),
    "major_claim_evidence_coverage_required": 1.0,
    "all_verifiable_claim_evidence_coverage_required": 0.95,
    "matrix": {
        "semantics": "CANONICAL_EXPECTED_OUTCOMES_ONLY",
        "source_path": MATRIX_PATH.as_posix(),
        "source_sha256": MATRIX_SHA256,
        "first_test_id": "CT-0389",
        "last_test_id": "CT-0550",
        "row_count": 162,
        "expected_outcome_counts": {
            "PASS": 36,
            "FAIL": 63,
            "FAIL_BLOCKER": 54,
            "FAIL_OR_DEGRADE": 9,
        },
        "executable": False,
        "mapping_authority": "UNAVAILABLE",
    },
}
EXPECTED_SELECTIONS: Final[dict[str, object]] = {
    "source_packet_id": None,
    "source_packet_version_id": None,
    "article_version_id": None,
    "claim_id": None,
    "fact_id": None,
    "link_id": None,
    "source_id": None,
    "citation_id": None,
    "conflict_id": None,
    "policy_claim_type": None,
    "persisted_claim_type": None,
    "ai_claim_type": None,
    "source_tier": None,
    "link_support_type": None,
}
EXPECTED_COLLECTIONS: Final[dict[str, object]] = {
    "claims": [],
    "facts": [],
    "links": [],
    "sources": [],
    "citations": [],
    "conflicts": [],
    "claim_count": None,
    "fact_count": None,
    "link_count": None,
    "source_count": None,
    "citation_count": None,
    "conflict_count": None,
    "major_claim_count": None,
    "evidenced_major_claim_count": None,
    "verifiable_claim_count": None,
    "evidenced_verifiable_claim_count": None,
}
EXPECTED_BLOCKERS: Final[list[str]] = [
    "CLAIMS_UNAVAILABLE",
    "FACTS_UNAVAILABLE",
    "EVIDENCE_LINKS_UNAVAILABLE",
    "SOURCES_AND_CITATIONS_UNAVAILABLE",
    "CONFLICT_STATE_UNAVAILABLE",
    "CLAIM_VOCABULARY_MAPPING_UNAVAILABLE",
    "SOURCE_TIER_ELIGIBILITY_MAPPING_UNAVAILABLE",
    "LINK_SUPPORT_OUTCOME_MAPPING_UNAVAILABLE",
    "COVERAGE_NUMERATOR_RULE_UNAVAILABLE",
]
EXPECTED_COVERAGE_DEFAULTS: Final[dict[str, object]] = {
    "coverage_status": "UNEVALUABLE",
    "coverage_evaluable": False,
    "major_claim_evidence_coverage_ratio": None,
    "all_verifiable_claim_evidence_coverage_ratio": None,
    "major_claim_requirement_satisfied": None,
    "all_verifiable_claim_requirement_satisfied": None,
    "zero_denominator_outcome": "UNEVALUABLE",
    "vacuous_zero_over_zero_pass_forbidden": True,
    "publication_permitted": False,
    "blockers": EXPECTED_BLOCKERS,
}
EXPECTED_ACTION_COUNTS: Final[dict[str, int]] = {name: 0 for name in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION: Final[dict[str, object]] = {
    "claim": "NOT_EXECUTED",
    "evidence_link": "NOT_EXECUTED",
    "matrix": "NOT_EXECUTED",
    "coverage_calculation": "NOT_EXECUTED",
    "mapping": "NOT_EXECUTED",
    "repository": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "api": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "external": "NOT_EXECUTED",
    "action_counts": EXPECTED_ACTION_COUNTS,
}
EXPECTED_VERIFICATION: Final[dict[str, str]] = {
    "predecessor_connection": "NOT_EXECUTED",
    "TST-020": "NOT_EXECUTED",
    "TST-021": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


def _validate_hashes(root: Path) -> None:
    if _sha256(_read(root, STORY_PATH, "authority.story")) != STORY_SHA256:
        _fail("SOURCE_HASH_DRIFT", "authority.story")
    for relative, digest in (
        *ST0602_ARTIFACTS,
        *ST0603_ARTIFACTS,
        *ST0604_ARTIFACTS,
    ):
        if _sha256(_read(root, relative, "predecessor.artifact")) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", "predecessor.artifact")
    for relative, digest, _relationship in CONTEXT_SOURCES:
        if _sha256(_read(root, relative, "context.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "context.source")
    if _sha256(_read(root, HELPER_PATH, "implementation.helper")) != HELPER_SHA256:
        _fail("IMPLEMENTATION_HELPER_DRIFT", "implementation.helper")


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "authority.story")
    _exact(
        _find(stories.get("stories"), "ST-0605", "authority.story"),
        EXPECTED_STORY,
        "authority.story",
    )


def _validate_st0602_semantics(root: Path) -> None:
    contract = _load_yaml(root, ST0602_ARTIFACTS[1][0], "predecessor.st0602")
    _exact(contract.get("decision"), "NOT_READY", "predecessor.st0602.decision")
    projection = _mapping(
        contract.get("fact_projection_defaults"), "predecessor.st0602.projection"
    )
    if any(value != [] for value in projection.values()):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0602.projection")
    plan = _load_json(root, ST0602_ARTIFACTS[2][0], "predecessor.st0602.plan")
    _exact(
        plan.get("fact_projection"),
        {
            "facts": [],
            "fact_ids": [],
            "derivations": [],
            "validation_records": [],
            "manual_review_records": [],
        },
        "predecessor.st0602.plan.projection",
    )


def _validate_st0603_semantics(root: Path) -> None:
    plan = _load_json(root, ST0603_ARTIFACTS[2][0], "predecessor.st0603.plan")
    _exact(
        plan.get("conflict_projection"),
        {
            "comparisons": [],
            "conflicts": [],
            "findings": [],
            "queue": [],
            "resolutions": [],
            "comparison_count": None,
            "conflict_count": None,
            "finding_count": None,
            "queue_count": None,
            "resolution_count": None,
        },
        "predecessor.st0603.plan.projection",
    )
    document = _mapping(plan.get("document"), "predecessor.st0603.document")
    _exact(document.get("decision"), "NOT_READY", "predecessor.st0603.decision")


def _validate_st0604_semantics(root: Path) -> None:
    plan = _load_json(root, ST0604_ARTIFACTS[2][0], "predecessor.st0604.plan")
    document = _mapping(plan.get("document"), "predecessor.st0604.document")
    _exact(document.get("decision"), "NOT_READY", "predecessor.st0604.decision")
    _exact(
        document.get("generation_permitted"),
        False,
        "predecessor.st0604.generation",
    )
    _exact(
        plan.get("collection_boundary"),
        {
            "packets": [],
            "versions": [],
            "jobs": [],
            "transitions": [],
            "mappings": [],
            "reviews": [],
            "approvals": [],
            "artifacts": [],
            "packet_count": None,
            "version_count": None,
            "job_count": None,
            "transition_count": None,
            "mapping_count": None,
            "review_count": None,
            "approval_count": None,
            "artifact_count": None,
        },
        "predecessor.st0604.collections",
    )
    lifecycle = _mapping(plan.get("lifecycle_boundary"), "predecessor.st0604.lifecycle")
    _exact(
        lifecycle.get("transition_status"),
        "UNAVAILABLE",
        "predecessor.st0604.transition",
    )
    _exact(lifecycle.get("mapping_status"), "UNAVAILABLE", "predecessor.st0604.mapping")
    _exact(lifecycle.get("approval"), False, "predecessor.st0604.approval")


def _validate_policy_semantics(root: Path) -> None:
    policy = _load_yaml(root, POLICY_PATH, "context.policy")
    _exact(
        [
            row.get("id")
            for row in map(
                lambda item: _mapping(item, "context.policy.tier"),
                _list(policy.get("source_tiers"), "context.policy.tiers"),
            )
        ],
        POLICY_SOURCE_TIERS,
        "context.policy.tiers",
    )
    _exact(
        [
            row.get("code")
            for row in map(
                lambda item: _mapping(item, "context.policy.claim"),
                _list(policy.get("claim_types"), "context.policy.claims"),
            )
        ],
        POLICY_CLAIM_TYPES,
        "context.policy.claims",
    )
    coverage = _mapping(policy.get("coverage_rules"), "context.policy.coverage")
    _exact(
        coverage.get("major_claim_definition"),
        EXPECTED_COVERAGE_POLICY["major_claim_definition"],
        "context.policy.major_definition",
    )
    _exact(
        coverage.get("major_claim_evidence_coverage_required"),
        1.0,
        "context.policy.major_ratio",
    )
    _exact(
        coverage.get("all_verifiable_claim_evidence_coverage_required"),
        0.95,
        "context.policy.verifiable_ratio",
    )


def _validate_claim_schema_semantics(root: Path) -> None:
    schema = _load_json(root, CLAIM_SCHEMA_PATH, "context.claim_schema")
    properties = _mapping(schema.get("properties"), "context.claim_schema.properties")
    claim_type = _mapping(properties.get("claim_type"), "context.claim_schema.type")
    _exact(claim_type.get("enum"), POLICY_CLAIM_TYPES, "context.claim_schema.type")
    status = _mapping(properties.get("status"), "context.claim_schema.status")
    _exact(
        status.get("enum"),
        ["proposed", "supported", "conflicted", "unsupported", "removed"],
        "context.claim_schema.status",
    )


def _constraints(table: Mapping[str, Any], field: str) -> dict[str, str]:
    rows = [
        _mapping(item, field) for item in _list(table.get("check_constraints"), field)
    ]
    result: dict[str, str] = {}
    for row in rows:
        name = row.get("name")
        expression = row.get("expression")
        if type(name) is not str or type(expression) is not str or name in result:
            _fail("SOURCE_SEMANTIC_DRIFT", field)
        result[name] = expression
    return result


def _validate_persisted_semantics(root: Path) -> None:
    catalog = _load_json(root, PERSISTED_CATALOG_PATH, "context.persisted")
    claim = _find_fully_qualified(catalog, "evidence.claim", "context.persisted.claim")
    _exact(
        _constraints(claim, "context.persisted.claim.constraints"),
        {
            "ck_evidence_claim_type": (
                "claim_type IN ('FACTUAL', 'COMPARATIVE', 'RECOMMENDATION', "
                "'DISCLOSURE', 'EXPERIENCE', 'OPINION')"
            ),
            "ck_evidence_claim_criticality": (
                "criticality IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')"
            ),
            "ck_evidence_claim_support": (
                "support_status IN ('PENDING', 'SUPPORTED', 'PARTIAL', "
                "'UNSUPPORTED', 'CONFLICT', 'NOT_REQUIRED')"
            ),
        },
        "context.persisted.claim.constraints",
    )
    link = _find_fully_qualified(
        catalog,
        "evidence.claim_evidence_link",
        "context.persisted.link",
    )
    _exact(
        _constraints(link, "context.persisted.link.constraints"),
        {
            "ck_evidence_claim_link_type": (
                "support_type IN ('SUPPORTS', 'QUALIFIES', 'CONTRADICTS')"
            ),
            "ck_evidence_claim_link_strength": "support_strength BETWEEN 0 AND 1",
        },
        "context.persisted.link.constraints",
    )


def _validate_ai_semantics(root: Path) -> None:
    schema = _load_json(root, AI_SCHEMA_PATH, "context.ai")
    properties = _mapping(schema.get("properties"), "context.ai.properties")
    claims = _mapping(properties.get("claims"), "context.ai.claims")
    items = _mapping(claims.get("items"), "context.ai.items")
    item_properties = _mapping(items.get("properties"), "context.ai.item_properties")
    _exact(
        item_properties.get("claim_type"),
        {"type": "string"},
        "context.ai.claim_type",
    )
    criticality = _mapping(item_properties.get("criticality"), "context.ai.criticality")
    support = _mapping(item_properties.get("support_status"), "context.ai.support")
    _exact(criticality.get("enum"), AI_CRITICALITIES, "context.ai.criticality")
    _exact(support.get("enum"), AI_SUPPORT_STATUSES, "context.ai.support")


MATRIX_COLUMNS: Final[list[str]] = [
    "test_id",
    "area",
    "artifact_or_rule",
    "scenario",
    "expected_result",
    "priority",
    "test_type",
    "requirement_ids",
    "implementation_slice",
]
EXPECTED_MATRIX_OUTCOME_COUNTS: Final[dict[str, int]] = {
    "PASS": 36,
    "FAIL": 63,
    "FAIL_BLOCKER": 54,
    "FAIL_OR_DEGRADE": 9,
}


def _matrix_rows(root: Path) -> list[dict[str, str]]:
    try:
        text = _read(root, MATRIX_PATH, "context.matrix").decode(
            "utf-8-sig", errors="strict"
        )
    except UnicodeDecodeError:
        _fail("UTF8_REQUIRED", "context.matrix")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != MATRIX_COLUMNS:
        _fail("SOURCE_SCHEMA_DRIFT", "context.matrix.columns")
    all_rows: list[dict[str, str]] = []
    for raw in reader:
        if None in raw or any(type(raw.get(key)) is not str for key in MATRIX_COLUMNS):
            _fail("SOURCE_SCHEMA_DRIFT", "context.matrix.row")
        all_rows.append({key: cast(str, raw[key]) for key in MATRIX_COLUMNS})
    start = [index for index, row in enumerate(all_rows) if row["test_id"] == "CT-0389"]
    end = [index for index, row in enumerate(all_rows) if row["test_id"] == "CT-0550"]
    if len(start) != 1 or len(end) != 1 or end[0] < start[0]:
        _fail("SOURCE_RECORD_MISSING", "context.matrix.range")
    rows = all_rows[start[0] : end[0] + 1]
    expected_ids = [f"CT-{number:04d}" for number in range(389, 551)]
    if [row["test_id"] for row in rows] != expected_ids:
        _fail("SOURCE_ORDER_DRIFT", "context.matrix.ids")
    if any(
        row["area"] != "claim_evidence"
        or row["artifact_or_rule"] != f"CLM-TYPE-{index // 18 + 1:03d}"
        or row["test_type"] != "policy"
        or row["implementation_slice"] != "CONT-SLICE-004"
        for index, row in enumerate(rows)
    ):
        _fail("SOURCE_SEMANTIC_DRIFT", "context.matrix.rows")
    counts = {key: 0 for key in EXPECTED_MATRIX_OUTCOME_COUNTS}
    for row in rows:
        outcome = row["expected_result"]
        if outcome not in counts:
            _fail("SOURCE_SEMANTIC_DRIFT", "context.matrix.outcome")
        counts[outcome] += 1
    if counts != EXPECTED_MATRIX_OUTCOME_COUNTS:
        _fail("SOURCE_SEMANTIC_DRIFT", "context.matrix.outcome_counts")
    return rows


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["schema_version"], 1, "schema_version")
    _exact(contract["story_id"], "ST-0605", "story_id")
    _exact(
        contract["classification"],
        "SOURCE_DERIVED_NONEXECUTABLE_CLAIM_EVIDENCE_COVERAGE_REFERENCE_PLAN",
        "classification",
    )
    _exact(contract["status"], "LOCAL_IMPLEMENTATION_CANDIDATE", "status")
    _exact(contract["executable"], False, "executable")
    _exact(contract["interface_only"], True, "interface_only")
    _exact(contract["decision"], "NOT_READY", "decision")
    _exact(contract["production_eligible"], False, "production_eligible")
    _exact(contract["approval"], False, "approval")
    _exact(contract["story_acceptance"], False, "story_acceptance")
    _exact(contract["publication_permitted"], False, "publication_permitted")
    _exact(
        contract["canonical_story_status"],
        {"implementation": "NOT_STARTED", "verification": "NOT_EXECUTED"},
        "canonical_story_status",
    )
    _exact(contract["authority"], EXPECTED_AUTHORITY, "authority")
    _exact(contract["predecessors"], _expected_predecessors(), "predecessors")
    _exact(contract["source_bindings"], _expected_source_bindings(), "source_bindings")
    _exact(
        contract["vocabulary_context"],
        EXPECTED_VOCABULARY_CONTEXT,
        "vocabulary_context",
    )
    _exact(contract["coverage_policy"], EXPECTED_COVERAGE_POLICY, "coverage_policy")
    _exact(contract["selection_defaults"], EXPECTED_SELECTIONS, "selection_defaults")
    _exact(contract["collection_defaults"], EXPECTED_COLLECTIONS, "collection_defaults")
    _exact(
        contract["coverage_defaults"], EXPECTED_COVERAGE_DEFAULTS, "coverage_defaults"
    )
    _exact(contract["execution_boundary"], EXPECTED_EXECUTION, "execution_boundary")
    _exact(
        contract["verification_boundary"],
        EXPECTED_VERIFICATION,
        "verification_boundary",
    )
    _validate_hashes(root)
    _validate_authority_semantics(root)
    _validate_st0602_semantics(root)
    _validate_st0603_semantics(root)
    _validate_st0604_semantics(root)
    _validate_policy_semantics(root)
    _validate_claim_schema_semantics(root)
    _validate_persisted_semantics(root)
    _validate_ai_semantics(root)
    _matrix_rows(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, Any]:
    matrix_policy = _mapping(
        _mapping(contract["coverage_policy"], "coverage_policy")["matrix"],
        "coverage_policy.matrix",
    )
    rows = _matrix_rows(root)
    plan: dict[str, Any] = {
        "document": {
            "schema_version": contract["schema_version"],
            "story_id": contract["story_id"],
            "classification": contract["classification"],
            "status": contract["status"],
            "executable": contract["executable"],
            "interface_only": contract["interface_only"],
            "decision": contract["decision"],
            "production_eligible": contract["production_eligible"],
            "approval": contract["approval"],
            "story_acceptance": contract["story_acceptance"],
            "publication_permitted": contract["publication_permitted"],
            "canonical_story_status": contract["canonical_story_status"],
        },
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "inventory_derivation": "COMMIT_DIFF_TREE_FIXED_AT_AUTHORING",
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_bindings": contract["predecessors"],
        "source_bindings": contract["source_bindings"],
        "vocabulary_context": contract["vocabulary_context"],
        "coverage_policy": contract["coverage_policy"],
        "matrix_projection": {
            "semantics": matrix_policy["semantics"],
            "source_path": matrix_policy["source_path"],
            "source_sha256": matrix_policy["source_sha256"],
            "first_test_id": matrix_policy["first_test_id"],
            "last_test_id": matrix_policy["last_test_id"],
            "expected_outcome_counts": matrix_policy["expected_outcome_counts"],
            "executable": matrix_policy["executable"],
            "mapping_authority": matrix_policy["mapping_authority"],
            "row_count": len(rows),
            "rows": rows,
        },
        "selection_boundary": contract["selection_defaults"],
        "collection_boundary": contract["collection_defaults"],
        "coverage_boundary": contract["coverage_defaults"],
        "execution_boundary": contract["execution_boundary"],
        "verification_boundary": contract["verification_boundary"],
    }
    if tuple(plan) != PLAN_KEYS:
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


def _predecessor_manifest_rows() -> list[dict[str, object]]:
    return [
        {
            "story_id": "ST-0602",
            "commit": ST0602_COMMIT,
            "inputs": _artifact_uri_rows(ST0602_ARTIFACTS),
        },
        {
            "story_id": "ST-0603",
            "commit": ST0603_COMMIT,
            "inputs": _artifact_uri_rows(ST0603_ARTIFACTS),
        },
        {
            "story_id": "ST-0604",
            "commit": ST0604_COMMIT,
            "inputs": _artifact_uri_rows(ST0604_ARTIFACTS),
        },
    ]


def _context_manifest_rows() -> list[dict[str, str]]:
    return [
        {
            "relationship": relationship,
            "uri": f"repo://{path.as_posix()}",
            "sha256": digest,
        }
        for path, digest, relationship in CONTEXT_SOURCES
    ]


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0605-CLAIM-EVIDENCE-COVERAGE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0605",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "canonical_story": {
                "uri": f"repo://{STORY_PATH.as_posix()}",
                "sha256": STORY_SHA256,
            },
            "inventory_derivation": "COMMIT_DIFF_TREE_FIXED_AT_AUTHORING",
            "predecessors": _predecessor_manifest_rows(),
            "context_sources": _context_manifest_rows(),
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
            "classification": (
                "SOURCE_DERIVED_NONEXECUTABLE_CLAIM_EVIDENCE_COVERAGE_REFERENCE_PLAN"
            ),
            "executable": False,
            "interface_only": True,
            "decision": "NOT_READY",
            "vocabulary_authority": "DESCRIPTIVE_ONLY",
            "inferred_mapping_count": 0,
            "source_tier_count": 6,
            "policy_claim_type_count": 9,
            "matrix_row_count": 162,
            "matrix_first_test_id": "CT-0389",
            "matrix_last_test_id": "CT-0550",
            "matrix_expected_outcome_counts": EXPECTED_MATRIX_OUTCOME_COUNTS,
            "major_required_ratio": 1.0,
            "all_verifiable_required_ratio": 0.95,
            "claim_count": None,
            "fact_count": None,
            "link_count": None,
            "source_count": None,
            "citation_count": None,
            "conflict_count": None,
            "major_observed_ratio": None,
            "all_verifiable_observed_ratio": None,
            "coverage_evaluable": False,
            "vacuous_zero_over_zero_pass_forbidden": True,
            "publication_permitted": False,
            "repository": "NOT_EXECUTED",
            "database": "NOT_EXECUTED",
            "job": "NOT_EXECUTED",
            "event": "NOT_EXECUTED",
            "api": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "formal_tst_021": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
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
        path = base._output_file(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            root, relative
        )
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
        base._atomic_write(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
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
    except (
        ClaimEvidenceCoverageReferenceError,
        base.StagingDeploymentContractError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0605 Claim/evidence coverage reference plan checked"
        if args.check
        else "ST-0605 Claim/evidence coverage reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
