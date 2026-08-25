#!/usr/bin/env python3
"""Build the non-executable ST-0604 Source Packet lifecycle reference plan."""

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

from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-0604/contracts/source-packet-lifecycle-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0604/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0604_source_packet_lifecycle_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0604/README.md")
TEST_PATHS: Final = (
    Path("tests/st0604/conftest.py"),
    Path("tests/st0604/test_contract.py"),
    Path("tests/st0604/test_generation.py"),
    Path("tests/st0604/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0604_source_packet_lifecycle_reference_plan.py"
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
ST0403_COMMIT: Final = "ad36831bef1182b555baeb03ba977623f9a68854"

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
ST0403_ARTIFACTS: Final = (
    (
        Path("changes/st-0403/README.md"),
        "d21f1ddefd4f201a6618e9baa8889d6c77302b141070d89d03b4e2199746d5cc",
    ),
    (
        Path("python/raos/adapters/development_authorization.py"),
        "dbcb97f3f71a7359297f36cf29d5d6e88879c990ff506bc884b09de235c92658",
    ),
    (
        Path("python/raos/application/iam/authorization.py"),
        "8c1133b948fc935b62d8e2ed964a795a7f9e24c9943c9aa1b44bcf898dba3814",
    ),
    (
        Path("python/raos/domain/iam/authorization.py"),
        "18b21b95dd3dc154b40f11f605b6289e0e27576f3401bb294606d871e78185f7",
    ),
    (
        Path("python/raos/ports/authorization.py"),
        "9f008f67337f1ceac44f94979f2741a96900c41408ee17fa3d887015a24ea9de",
    ),
    (
        Path("tests/st0403/conftest.py"),
        "9811af4233700ac6ad4de6209d37d08ac442b7f3946f6e074e6a9839ed339459",
    ),
    (
        Path("tests/st0403/test_authorization.py"),
        "5df2d5a51188f9ed0de2252695b7ccdb980b1ffd6e7a4132486d404c28277995",
    ),
    (
        Path("tests/st0403/test_boundaries.py"),
        "dcf612fe47ae9987457c61d5d7a23a2a71c957b8226a105195f20d1807228240",
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
    "generation_permitted",
    "canonical_story_status",
    "authority",
    "predecessors",
    "vocabulary_context",
    "selection_defaults",
    "collection_defaults",
    "lifecycle_defaults",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_bindings",
    "vocabulary_context",
    "selection_boundary",
    "collection_boundary",
    "lifecycle_boundary",
    "execution_boundary",
    "verification_boundary",
)
ACTION_COUNT_KEYS: Final = (
    "create_packet",
    "create_version",
    "transition",
    "map_status",
    "review",
    "authorize",
    "approve",
    "bind_artifact",
    "enqueue_job",
    "emit_event",
    "repository_write",
    "database_write",
    "generate",
    "external",
)


class SourcePacketReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise SourcePacketReferenceError(f"ST-0604 build failed: {code} field={field}")


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


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(_read(root, relative, field))
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", field)
    return _mapping(parsed, field)


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
    "id": "ST-0604",
    "epic_id": "EPIC-06",
    "title": "Source packet lifecycle",
    "objective": "Draft/approve/version/lockを実装",
    "depends_on": ["ST-0602", "ST-0603", "ST-0403"],
    "requirement_ids": ["FR-006"],
    "design_refs": [],
    "deliverables": ["packet service/API"],
    "acceptance_criteria": ["unapproved cannot generate"],
    "test_suites": ["TST-012", "TST-020"],
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
    "objective": "Draft/approve/version/lockを実装",
    "requirement_ids": ["FR-006"],
    "acceptance_criteria": ["unapproved cannot generate"],
    "test_suites": ["TST-012", "TST-020"],
}
EXPECTED_ST0602_SEMANTICS: Final[dict[str, object]] = {
    "decision": "NOT_READY",
    "facts": [],
    "fact_ids": [],
    "fact_count": None,
    "extraction": "NOT_EXECUTED",
    "validation": "NOT_EXECUTED",
}
EXPECTED_ST0603_SEMANTICS: Final[dict[str, object]] = {
    "decision": "NOT_READY",
    "facts": [],
    "fact_ids": [],
    "fact_count": None,
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
}
EXPECTED_ST0403_SEMANTICS: Final = {
    "mode": "RECORDED_TEST",
    "deny_by_default": True,
    "live_authorization_available": False,
    "production_approval_available": False,
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
            "story_id": "ST-0403",
            "commit": ST0403_COMMIT,
            "relationship": "DENY_DEFAULT_RECORDED_AUTHORIZATION_CONTEXT_ONLY",
            "files": _artifact_rows(ST0403_ARTIFACTS),
            "required_semantics": EXPECTED_ST0403_SEMANTICS,
        },
    ]


EXPECTED_VOCABULARY_CONTEXT: Final[dict[str, object]] = {
    "authority": "DESCRIPTIVE_ONLY",
    "creates_runtime_contract": False,
    "packet_namespace": {
        "name": "STORY_PACKET_LIFECYCLE_TERMS",
        "values": ["DRAFT", "APPROVE", "VERSION", "LOCK"],
    },
    "version_namespace": {
        "name": "SOURCE_PACKET_VERSION_STATE_MACHINE",
        "values": [
            "BUILDING",
            "READY",
            "IN_REVIEW",
            "APPROVED",
            "REJECTED",
            "SUPERSEDED",
            "INVALID",
        ],
    },
    "job_namespace": {
        "name": "CANONICAL_JOB_STATE",
        "values": [
            "REQUESTED",
            "QUEUED",
            "RUNNING",
            "SUCCEEDED",
            "FAILED_RETRYABLE",
            "RETRY_SCHEDULED",
            "FAILED_TERMINAL",
            "QUARANTINED",
            "CANCELLED",
            "EXPIRED",
        ],
    },
    "inferred_mappings": [],
}
EXPECTED_SELECTIONS: Final = {
    "packet_id": None,
    "packet_status": None,
    "version_id": None,
    "version_status": None,
    "job_id": None,
    "job_status": None,
    "reviewer": None,
    "authorization": None,
    "artifact_id": None,
    "artifact_ref": None,
    "content_hash": None,
}
EXPECTED_COLLECTIONS: Final[dict[str, object]] = {
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
}
EXPECTED_BLOCKERS: Final = [
    "SOURCE_FACTS_UNAVAILABLE",
    "CONFLICT_FINDINGS_UNAVAILABLE",
    "VOCABULARY_MAPPING_UNAVAILABLE",
    "LIFECYCLE_TRANSITIONS_UNAVAILABLE",
    "REVIEWER_UNAVAILABLE",
    "AUTHORIZATION_NOT_GRANTED",
    "ARTIFACT_BINDING_UNAVAILABLE",
]
EXPECTED_LIFECYCLE: Final = {
    "transition_status": "UNAVAILABLE",
    "mapping_status": "UNAVAILABLE",
    "approval": False,
    "generation_permitted": False,
    "blockers": EXPECTED_BLOCKERS,
}
EXPECTED_ACTION_COUNTS: Final = {name: 0 for name in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION: Final = {
    "packet": "NOT_EXECUTED",
    "version": "NOT_EXECUTED",
    "transition": "NOT_EXECUTED",
    "mapping": "NOT_EXECUTED",
    "review": "NOT_EXECUTED",
    "authorization": "NOT_EXECUTED",
    "artifact": "NOT_EXECUTED",
    "repository": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "api": "NOT_EXECUTED",
    "approval": "NOT_EXECUTED",
    "generation": "NOT_EXECUTED",
    "external": "NOT_EXECUTED",
    "action_counts": EXPECTED_ACTION_COUNTS,
}
EXPECTED_VERIFICATION: Final = {
    "predecessor_connection": "NOT_EXECUTED",
    "TST-012": "NOT_EXECUTED",
    "TST-020": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


def _validate_hashes(root: Path) -> None:
    if _sha256(_read(root, STORY_PATH, "authority.story")) != STORY_SHA256:
        _fail("SOURCE_HASH_DRIFT", "authority.story")
    for relative, digest in (*ST0602_ARTIFACTS, *ST0603_ARTIFACTS, *ST0403_ARTIFACTS):
        if _sha256(_read(root, relative, "predecessor.artifact")) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", "predecessor.artifact")
    if _sha256(_read(root, HELPER_PATH, "implementation.helper")) != HELPER_SHA256:
        _fail("IMPLEMENTATION_HELPER_DRIFT", "implementation.helper")


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "authority.story")
    _exact(
        _find(stories.get("stories"), "ST-0604", "authority.story"),
        EXPECTED_STORY,
        "authority.story",
    )


def _validate_st0602_semantics(root: Path) -> None:
    contract = _load_yaml(root, ST0602_ARTIFACTS[1][0], "predecessor.st0602")
    _exact(contract.get("decision"), "NOT_READY", "predecessor.st0602.decision")
    inputs = _mapping(contract.get("input_defaults"), "predecessor.st0602.inputs")
    if any(value is not None for value in inputs.values()):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0602.inputs")
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
    contract = _load_yaml(root, ST0603_ARTIFACTS[1][0], "predecessor.st0603")
    _exact(contract.get("decision"), "NOT_READY", "predecessor.st0603.decision")
    _exact(
        contract.get("input_defaults"),
        {"facts": [], "fact_ids": [], "fact_count": None},
        "predecessor.st0603.inputs",
    )
    _exact(
        contract.get("projection_defaults"),
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
        "predecessor.st0603.projection",
    )
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


def _require_fragments(text: str, fragments: Sequence[str], field: str) -> None:
    if any(fragment not in text for fragment in fragments):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", field)


def _validate_st0403_semantics(root: Path) -> None:
    _require_fragments(
        _text(root, ST0403_ARTIFACTS[0][0], "predecessor.st0403.readme"),
        (
            "without\ngranting live, provider, publication, service-principal, or Production\nauthority",
            "Unknown operations",
            "deny",
            "exclusive `O_EXCL` path",
            "process-lifetime count/head/prefix anchor",
            "service-principal port\nalways denies",
        ),
        "predecessor.st0403.readme",
    )
    _require_fragments(
        _text(root, ST0403_ARTIFACTS[3][0], "predecessor.st0403.domain"),
        (
            'DISABLED = "DISABLED"',
            'RECORDED_TEST = "RECORDED_TEST"',
            'ALLOW = "ALLOW"',
            'DENY = "DENY"',
            'DENIED = "DENIED"',
        ),
        "predecessor.st0403.domain",
    )
    _require_fragments(
        _text(root, ST0403_ARTIFACTS[2][0], "predecessor.st0403.application"),
        (
            "if policy.mode is PolicyMode.DISABLED:",
            "if policy.mode is not PolicyMode.RECORDED_TEST:",
            "effect=DecisionEffect.DENY",
        ),
        "predecessor.st0403.application",
    )
    _require_fragments(
        _text(root, ST0403_ARTIFACTS[1][0], "predecessor.st0403.adapter"),
        (
            "environment is not RuntimeEnvironment.ENV_DEV",
            "PolicyMode.RECORDED_TEST",
        ),
        "predecessor.st0403.adapter",
    )


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["schema_version"], 1, "schema_version")
    _exact(contract["story_id"], "ST-0604", "story_id")
    _exact(
        contract["classification"],
        "SOURCE_DERIVED_NON_EXECUTABLE_SOURCE_PACKET_LIFECYCLE_REFERENCE_PLAN",
        "classification",
    )
    _exact(contract["status"], "LOCAL_IMPLEMENTATION_CANDIDATE", "status")
    _exact(contract["executable"], False, "executable")
    _exact(contract["interface_only"], True, "interface_only")
    _exact(contract["decision"], "NOT_READY", "decision")
    _exact(contract["production_eligible"], False, "production_eligible")
    _exact(contract["approval"], False, "approval")
    _exact(contract["story_acceptance"], False, "story_acceptance")
    _exact(contract["generation_permitted"], False, "generation_permitted")
    _exact(
        contract["canonical_story_status"],
        {"implementation": "NOT_STARTED", "verification": "NOT_EXECUTED"},
        "canonical_story_status",
    )
    _exact(contract["authority"], EXPECTED_AUTHORITY, "authority")
    _exact(contract["predecessors"], _expected_predecessors(), "predecessors")
    _exact(
        contract["vocabulary_context"],
        EXPECTED_VOCABULARY_CONTEXT,
        "vocabulary_context",
    )
    _exact(contract["selection_defaults"], EXPECTED_SELECTIONS, "selection_defaults")
    _exact(
        contract["collection_defaults"],
        EXPECTED_COLLECTIONS,
        "collection_defaults",
    )
    _exact(contract["lifecycle_defaults"], EXPECTED_LIFECYCLE, "lifecycle_defaults")
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
    _validate_st0602_semantics(root)
    _validate_st0603_semantics(root)
    _validate_st0403_semantics(root)
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
            "generation_permitted": contract["generation_permitted"],
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
        "vocabulary_context": contract["vocabulary_context"],
        "selection_boundary": contract["selection_defaults"],
        "collection_boundary": contract["collection_defaults"],
        "lifecycle_boundary": contract["lifecycle_defaults"],
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
            "story_id": "ST-0403",
            "commit": ST0403_COMMIT,
            "inputs": _artifact_uri_rows(ST0403_ARTIFACTS),
        },
    ]


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0604-SOURCE-PACKET-LIFECYCLE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0604",
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
                "SOURCE_DERIVED_NON_EXECUTABLE_SOURCE_PACKET_LIFECYCLE_REFERENCE_PLAN"
            ),
            "executable": False,
            "interface_only": True,
            "decision": "NOT_READY",
            "vocabulary_authority": "DESCRIPTIVE_ONLY",
            "inferred_mapping_count": 0,
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
            "repository": "NOT_EXECUTED",
            "database": "NOT_EXECUTED",
            "job": "NOT_EXECUTED",
            "event": "NOT_EXECUTED",
            "api": "NOT_EXECUTED",
            "artifact": "NOT_EXECUTED",
            "formal_tst_012": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
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
    except (SourcePacketReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0604 Source Packet lifecycle reference plan checked"
        if args.check
        else "ST-0604 Source Packet lifecycle reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
