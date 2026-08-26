#!/usr/bin/env python3
"""Build the non-executable ST-0602 Fact extraction reference plan."""

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

from scripts import raos_build_core as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-0602/contracts/fact-extraction-validation-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0602/generated/fact-extraction-validation-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0602/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0602_fact_extraction_validation_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0602/README.md")
TEST_PATHS: Final = (
    Path("tests/st0602/conftest.py"),
    Path("tests/st0602/test_contract.py"),
    Path("tests/st0602/test_generation.py"),
    Path("tests/st0602/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0602_fact_extraction_validation_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "478c70fcdec48ceca5c9d072c84e4ad3dc55f63e8ccbee0f8e09d4d78eb6fdf5"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
STORY_SHA256: Final = "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
ST0601_COMMIT: Final = "38ac757b814c24c913031485a78bbf7d2206f2a5"
ST0503_COMMIT: Final = "80162f932738f9c3854ff012ae8e488275f7e1f5"

ST0601_ARTIFACTS: Final = (
    (
        Path("changes/st-0601/README.md"),
        "67e1476c7f8104d3d99802c745b74a0f605b07e28619b2b7da66ec836bd7c355",
    ),
    (
        Path("python/raos/domain/ops/artifact_registry.py"),
        "114da597e5a2350a3b5412a94c98f964397c86264009737183f225ad30f81af4",
    ),
    (
        Path("python/raos/ports/artifact_registry.py"),
        "973c43c6233eccd11f068ab69794c31e7f5fc81ed2f4632937a3bf392c25a747",
    ),
    (
        Path("python/raos/application/ops/artifact_registry.py"),
        "334b116682e37beb652e38354e62eaaacfb1c6be17f844a689401228f20edb9b",
    ),
    (
        Path("python/raos/adapters/recorded_artifact_registry.py"),
        "a47dfa52627f8212a75f76f9b6ef8cf7e13fc6b6b90f171b1a72dbad6c0d06c5",
    ),
    (
        Path("tests/st0601/conftest.py"),
        "26d28a320cc0ccc6480aee68b508abf62b33cebb71177df629d5d61b81d2a459",
    ),
    (
        Path("tests/st0601/test_artifact_registry.py"),
        "827e3e6f522edf4c7bc5e83c49afbb41933b6d73e4efa9759a556f8702d91e82",
    ),
    (
        Path("tests/st0601/test_failure_isolation.py"),
        "89c13714d24f34d76ec49a4c3131ba1d53642393a7797d08e9e5fcb74f948970",
    ),
    (
        Path("tests/st0601/test_boundaries.py"),
        "5d5981813b80c2cd3d15f1b287ba3d4b601b114608e3e13b84058209f8aa3a72",
    ),
)
ST0503_ARTIFACTS: Final = (
    (
        Path("changes/st-0503/README.md"),
        "e372c00533e7ddddb71e10308fb703e8c31261351c61d593c520371c505b2f0b",
    ),
    (
        Path("python/raos/domain/catalog/catalog_normalization.py"),
        "6fa0adbd3ade25c5e6880e5aaec70f2c010173873b3cd3d11987d317f81642d9",
    ),
    (
        Path("python/raos/ports/catalog_normalization.py"),
        "c2bd6979baf05f778059df28bb3c34cdcd3862d871fc0ea238626790bfa218e1",
    ),
    (
        Path("python/raos/application/catalog/catalog_normalization.py"),
        "02ec218119133ac64df4228a588f415c99f64e898be9c9fa581222b5933abfe4",
    ),
    (
        Path("python/raos/adapters/recorded_catalog_normalization.py"),
        "2f25cce21d5368d31a5129df61c07c12ae018f879631f760ee27c97cf917fa9b",
    ),
    (
        Path("tests/st0503/conftest.py"),
        "8073bb2e43b470bd19bcdf50fcb9f3a1fbc42e6614586e814c4bfd4452491bf1",
    ),
    (
        Path("tests/st0503/test_normalization.py"),
        "1bd442a1160be528e677a7f026e449f65a9bb937b91e29f78daa1d231c2feb1f",
    ),
    (
        Path("tests/st0503/test_failure_isolation.py"),
        "3655c1757ce6eee01cab7deb198f8daad25a61cf045de07165f0eda7368d0056",
    ),
    (
        Path("tests/st0503/test_boundaries.py"),
        "f1ebe757961349fe8deac3ed2e3c4217181a9bef423f0091803a0459a655356a",
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
    "canonical_story_status",
    "authority",
    "predecessors",
    "canonical_context",
    "input_defaults",
    "fact_projection_defaults",
    "validation_defaults",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_bindings",
    "canonical_context",
    "input_boundary",
    "fact_projection",
    "validation",
    "execution_boundary",
    "verification_boundary",
)
ACTION_COUNT_KEYS: Final = (
    "extract",
    "validate",
    "create_fact",
    "derive",
    "manual_review",
    "enqueue_job",
    "emit_event",
    "repository_write",
    "database_write",
    "external",
)


class FactExtractionReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise FactExtractionReferenceError(f"ST-0602 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return cast(dict[str, Any], value)


def _list(value: object, field: str) -> list[object]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return cast(list[object], value)


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
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _text(root: Path, relative: Path, field: str) -> str:
    try:
        return _read(root, relative, field).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail("UTF8_REQUIRED", field)


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        root, relative, field
    )
    return _mapping(base.load_yaml(root / relative), field)


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(cast(object, item), field)
        for item in _list(items, field)
        if type(item) is dict and cast(dict[str, object], item).get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
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


EXPECTED_STORY: Final = {
    "id": "ST-0602",
    "epic_id": "EPIC-06",
    "title": "Fact extraction and validation",
    "objective": "原本から型付きFactを作成",
    "depends_on": ["ST-0601", "ST-0503"],
    "requirement_ids": ["FR-004"],
    "design_refs": [],
    "deliverables": ["fact service", "validators"],
    "acceptance_criteria": ["unit/time/source/confidence"],
    "test_suites": ["TST-005", "TST-007"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": [],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_AUTHORITY: Final = {
    "canonical_story_path": STORY_PATH.as_posix(),
    "canonical_story_sha256": STORY_SHA256,
    "objective": "原本から型付きFactを作成",
    "requirement_ids": ["FR-004"],
    "acceptance_criteria": ["unit/time/source/confidence"],
    "test_suites": ["TST-005", "TST-007"],
}
EXPECTED_ST0601_SEMANTICS: Final = {
    "accepted_kind": "raw_provider_response",
    "real_artifact_available": False,
    "source_snapshot_available": False,
    "storage_execution": "NOT_EXECUTED",
    "read_execution": "NOT_EXECUTED",
    "write_execution": "NOT_EXECUTED",
    "roundtrip_execution": "NOT_EXECUTED",
    "attestation_execution": "NOT_EXECUTED",
    "persistence_execution": "NOT_EXECUTED",
    "matching_decision": "NOT_READY",
    "artifact_id": None,
    "artifact_ref": None,
}
EXPECTED_ST0503_SEMANTICS: Final = {
    "normalization": "LOSSLESS_STRUCTURAL_ONLY",
    "source_snapshot_id": None,
    "source_snapshot_status": "NOT_AVAILABLE",
    "authoritative_subject_available": False,
    "confidence": None,
    "confidence_basis": "SOURCE_ABSENT",
    "identity_decision": "REVIEW_REQUIRED",
    "persistence_execution": "NOT_EXECUTED",
}


def _expected_predecessors() -> list[dict[str, object]]:
    return [
        {
            "story_id": "ST-0601",
            "commit": ST0601_COMMIT,
            "relationship": "SOURCE_BOUND_RECORDED_NON_ATTESTING_INPUT_ONLY",
            "files": _artifact_rows(ST0601_ARTIFACTS),
            "required_semantics": EXPECTED_ST0601_SEMANTICS,
        },
        {
            "story_id": "ST-0503",
            "commit": ST0503_COMMIT,
            "relationship": "LOSSLESS_NORMALIZATION_CONTEXT_ONLY",
            "files": _artifact_rows(ST0503_ARTIFACTS),
            "required_semantics": EXPECTED_ST0503_SEMANTICS,
        },
    ]


EXPECTED_CANONICAL_CONTEXT: Final = {
    "authority": "DESCRIPTIVE_ONLY",
    "creates_runtime_contract": False,
    "fact_model": "DESCRIPTIVE_ONLY_NOT_BOUND",
    "extraction_job": "DESCRIPTIVE_ONLY_NOT_BOUND",
    "fact_event": "DESCRIPTIVE_ONLY_NOT_BOUND",
    "security_controls": "DESCRIPTIVE_ONLY_NOT_BOUND",
}
EXPECTED_INPUT_DEFAULTS: Final = {
    "source_snapshot_id": None,
    "artifact_id": None,
    "artifact_ref": None,
    "subject_id": None,
    "predicate": None,
    "unit": None,
    "confidence": None,
    "locator": None,
    "extractor": None,
    "manual_review_count": None,
}
EXPECTED_FACT_PROJECTION: Final[dict[str, list[object]]] = {
    "facts": [],
    "fact_ids": [],
    "derivations": [],
    "validation_records": [],
    "manual_review_records": [],
}
EXPECTED_BLOCKERS: Final = [
    "REAL_ARTIFACT_UNAVAILABLE",
    "SOURCE_SNAPSHOT_UNAVAILABLE",
    "AUTHORITATIVE_SUBJECT_UNAVAILABLE",
    "CONFIDENCE_SOURCE_ABSENT",
    "EXTRACTOR_NOT_IMPLEMENTED",
    "PERSISTENCE_BOUNDARY_UNAVAILABLE",
]
EXPECTED_VALIDATION: Final = {
    "status": "NOT_EXECUTED",
    "unit_validation": "NOT_EXECUTED",
    "time_validation": "NOT_EXECUTED",
    "source_validation": "NOT_EXECUTED",
    "confidence_validation": "NOT_EXECUTED",
    "passed": False,
    "blockers": EXPECTED_BLOCKERS,
}
EXPECTED_ACTION_COUNTS: Final = {name: 0 for name in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION: Final = {
    "extraction": "NOT_EXECUTED",
    "validation": "NOT_EXECUTED",
    "manual_review": "NOT_EXECUTED",
    "repository": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "provider": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "external": "NOT_EXECUTED",
    "action_counts": EXPECTED_ACTION_COUNTS,
}
EXPECTED_VERIFICATION: Final = {
    "TST-005": "NOT_EXECUTED",
    "TST-007": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


def _validate_hashes(root: Path) -> None:
    if _sha256(_read(root, STORY_PATH, "authority.story")) != STORY_SHA256:
        _fail("SOURCE_HASH_DRIFT", "authority.story")


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "authority.story")
    _exact(
        _find(stories.get("stories"), "ST-0602", "authority.story"),
        EXPECTED_STORY,
        "authority.story",
    )


def _require_fragments(text: str, fragments: Sequence[str], field: str) -> None:
    if any(fragment not in text for fragment in fragments):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", field)


def _validate_st0601_semantics(root: Path) -> None:
    _require_fragments(
        _text(root, ST0601_ARTIFACTS[0][0], "predecessor.st0601.readme"),
        (
            "SOURCE_BOUND_RECORDED_NON_ATTESTING_ARTIFACT_REGISTRY_REFERENCE_PLAN",
            "`raw_provider_response`",
            "`NOT_READY / RECORDED_MATCH`",
            "Every storage, read, write, round-trip, attestation, and persistence",
            "Artifact ID, ArtifactRef, retention value, and actions are",
            "Story acceptance remains false",
        ),
        "predecessor.st0601.readme",
    )
    _require_fragments(
        _text(root, ST0601_ARTIFACTS[1][0], "predecessor.st0601.domain"),
        (
            'RAW_PROVIDER_RESPONSE = "raw_provider_response"',
            'NOT_EXECUTED = "NOT_EXECUTED"',
            'NOT_READY = "NOT_READY"',
            "MATCHING_BLOCKERS: tuple[RegistryBlocker, ...]",
            "artifact_id: None",
            "artifact_ref: None",
            "retention: None",
            "persistence_execution: ExecutionStatus",
            "actions: tuple[()]",
        ),
        "predecessor.st0601.domain",
    )
    port = _text(root, ST0601_ARTIFACTS[2][0], "predecessor.st0601.port")
    if "def observe(" not in port or any(
        fragment in port
        for fragment in (
            "def save(",
            "def store(",
            "def read(",
            "def write(",
            "def delete(",
        )
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0601.port")
    _require_fragments(
        _text(root, ST0601_ARTIFACTS[3][0], "predecessor.st0601.application"),
        (
            "observed = self._observer.observe(candidate)",
            "RegistryDecision.NOT_READY if matches else RegistryDecision.REJECTED",
            "artifact_id=None",
            "artifact_ref=None",
            "retention=None",
            "storage_execution=ExecutionStatus.NOT_EXECUTED",
            "persistence_execution=ExecutionStatus.NOT_EXECUTED",
            "actions=()",
        ),
        "predecessor.st0601.application",
    )
    _require_fragments(
        _text(root, ST0601_ARTIFACTS[4][0], "predecessor.st0601.adapter"),
        (
            "ArtifactObservation.from_synthetic(",
            "environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}",
            "return matches[0].observation",
        ),
        "predecessor.st0601.adapter",
    )


def _validate_st0503_semantics(root: Path) -> None:
    _require_fragments(
        _text(root, ST0503_ARTIFACTS[0][0], "predecessor.st0503.readme"),
        (
            "LOSSLESS_PASSTHROUGH",
            "snapshot `NOT_AVAILABLE`",
            "confidence `SOURCE_ABSENT`",
            "repository `ABSENT`",
            "identity is\n  `REVIEW_REQUIRED`",
            "decision is `NOT_READY`",
        ),
        "predecessor.st0503.readme",
    )
    _require_fragments(
        _text(root, ST0503_ARTIFACTS[1][0], "predecessor.st0503.domain"),
        (
            'LOSSLESS_STRUCTURAL_ONLY = "LOSSLESS_STRUCTURAL_ONLY"',
            'NOT_AVAILABLE = "NOT_AVAILABLE"',
            'SOURCE_ABSENT = "SOURCE_ABSENT"',
            'REVIEW_REQUIRED = "REVIEW_REQUIRED"',
            "source_snapshot_id=None",
            "confidence=None",
            "canonical_products=()",
            "grouping_decisions=()",
            "identity_decisions=()",
            "repository=RepositoryBoundary.ABSENT",
            "persistence_executed=False",
            "job=ExecutionStatus.NOT_EXECUTED",
            "event=ExecutionStatus.NOT_EXECUTED",
            "decision=NormalizationDecision.NOT_READY",
        ),
        "predecessor.st0503.domain",
    )
    port = _text(root, ST0503_ARTIFACTS[2][0], "predecessor.st0503.port")
    if "def normalize(" not in port or any(
        fragment in port
        for fragment in ("def save(", "def merge(", "def approve(", "def persist(")
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0503.port")
    _require_fragments(
        _text(root, ST0503_ARTIFACTS[3][0], "predecessor.st0503.application"),
        (
            "outcome = self._exchange.normalize(command)",
            "expected = lossless_batch_from_command(command)",
            "if outcome != expected:",
        ),
        "predecessor.st0503.application",
    )
    _require_fragments(
        _text(root, ST0503_ARTIFACTS[4][0], "predecessor.st0503.adapter"),
        (
            "environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}",
            "return matches[0].batch",
        ),
        "predecessor.st0503.adapter",
    )


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["schema_version"], 1, "schema_version")
    _exact(contract["story_id"], "ST-0602", "story_id")
    _exact(
        contract["classification"],
        "SOURCE_DERIVED_NON_EXECUTABLE_FACT_EXTRACTION_VALIDATION_REFERENCE_PLAN",
        "classification",
    )
    _exact(contract["status"], "LOCAL_IMPLEMENTATION_CANDIDATE", "status")
    _exact(contract["executable"], False, "executable")
    _exact(contract["interface_only"], True, "interface_only")
    _exact(contract["decision"], "NOT_READY", "decision")
    _exact(contract["production_eligible"], False, "production_eligible")
    _exact(contract["approval"], None, "approval")
    _exact(contract["story_acceptance"], False, "story_acceptance")
    _exact(
        contract["canonical_story_status"],
        {"implementation": "NOT_STARTED", "verification": "NOT_EXECUTED"},
        "canonical_story_status",
    )
    _exact(contract["authority"], EXPECTED_AUTHORITY, "authority")
    _exact(contract["predecessors"], _expected_predecessors(), "predecessors")
    _exact(
        contract["canonical_context"],
        EXPECTED_CANONICAL_CONTEXT,
        "canonical_context",
    )
    _exact(contract["input_defaults"], EXPECTED_INPUT_DEFAULTS, "input_defaults")
    _exact(
        contract["fact_projection_defaults"],
        EXPECTED_FACT_PROJECTION,
        "fact_projection_defaults",
    )
    _exact(
        contract["validation_defaults"],
        EXPECTED_VALIDATION,
        "validation_defaults",
    )
    _exact(
        contract["execution_boundary"],
        EXPECTED_EXECUTION,
        "execution_boundary",
    )
    _exact(
        contract["verification_boundary"],
        EXPECTED_VERIFICATION,
        "verification_boundary",
    )
    _validate_hashes(root)
    _validate_authority_semantics(root)
    _validate_st0601_semantics(root)
    _validate_st0503_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(contract: Mapping[str, Any]) -> dict[str, Any]:
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
            "canonical_story_status": contract["canonical_story_status"],
        },
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_bindings": contract["predecessors"],
        "canonical_context": contract["canonical_context"],
        "input_boundary": contract["input_defaults"],
        "fact_projection": contract["fact_projection_defaults"],
        "validation": contract["validation_defaults"],
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


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0602-FACT-EXTRACTION-VALIDATION-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0602",
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
            "predecessors": [
                {
                    "story_id": "ST-0601",
                    "commit": ST0601_COMMIT,
                    "inputs": _artifact_uri_rows(ST0601_ARTIFACTS),
                },
                {
                    "story_id": "ST-0503",
                    "commit": ST0503_COMMIT,
                    "inputs": _artifact_uri_rows(ST0503_ARTIFACTS),
                },
            ],
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
                "SOURCE_DERIVED_NON_EXECUTABLE_FACT_EXTRACTION_VALIDATION_REFERENCE_PLAN"
            ),
            "executable": False,
            "interface_only": True,
            "decision": "NOT_READY",
            "canonical_context": "DESCRIPTIVE_ONLY",
            "real_artifact_available": False,
            "source_snapshot_available": False,
            "authoritative_subject_available": False,
            "confidence_source": "ABSENT",
            "facts": 0,
            "fact_ids": 0,
            "derivations": 0,
            "validation": "NOT_EXECUTED",
            "repository": "NOT_EXECUTED",
            "database": "NOT_EXECUTED",
            "job": "NOT_EXECUTED",
            "event": "NOT_EXECUTED",
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_007": "NOT_EXECUTED",
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
    reference_bytes = _json_bytes(reference_plan(contract))
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
    except (FactExtractionReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0602 Fact extraction validation reference plan checked"
        if args.check
        else "ST-0602 Fact extraction validation reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
