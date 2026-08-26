#!/usr/bin/env python3
"""Build the non-executable ST-0603 Fact conflict-review reference plan."""

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
    "changes/st-0603/contracts/fact-conflict-review-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0603/generated/fact-conflict-review-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0603/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0603_fact_conflict_review_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0603/README.md")
TEST_PATHS: Final = (
    Path("tests/st0603/conftest.py"),
    Path("tests/st0603/test_contract.py"),
    Path("tests/st0603/test_generation.py"),
    Path("tests/st0603/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0603_fact_conflict_review_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "478c70fcdec48ceca5c9d072c84e4ad3dc55f63e8ccbee0f8e09d4d78eb6fdf5"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
STORY_SHA256: Final = "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
PREDECESSOR_COMMIT: Final = "806b978803cbc78392117cbc31015db19ea09a74"
PREDECESSOR_ARTIFACTS: Final = (
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
    "predecessor",
    "canonical_context",
    "input_defaults",
    "selection_defaults",
    "projection_defaults",
    "review_and_resolution_defaults",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_binding",
    "canonical_context",
    "input_boundary",
    "selection_boundary",
    "conflict_projection",
    "review_and_resolution",
    "execution_boundary",
    "verification_boundary",
)
ACTION_COUNT_KEYS: Final = (
    "detect",
    "compare",
    "create_conflict",
    "create_finding",
    "enqueue_review",
    "assign_actor",
    "resolve",
    "emit_event",
    "repository_write",
    "database_write",
    "external",
)


class FactConflictReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise FactConflictReferenceError(f"ST-0603 build failed: {code} field={field}")


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


def _artifact_rows() -> list[dict[str, str]]:
    return [
        {"path": path.as_posix(), "sha256": digest}
        for path, digest in PREDECESSOR_ARTIFACTS
    ]


def _artifact_uri_rows() -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in PREDECESSOR_ARTIFACTS
    ]


EXPECTED_STORY: Final = {
    "id": "ST-0603",
    "epic_id": "EPIC-06",
    "title": "Conflict detection",
    "objective": "同一属性の矛盾を検出",
    "depends_on": ["ST-0602"],
    "requirement_ids": ["FR-008"],
    "design_refs": [],
    "deliverables": ["conflict rules", "queue"],
    "acceptance_criteria": ["conflict not silently resolved"],
    "test_suites": ["TST-007", "TST-020"],
    "priority": "P0",
    "mvp": True,
    "size": "M",
    "open_decisions": [],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_AUTHORITY: Final = {
    "canonical_story_path": STORY_PATH.as_posix(),
    "canonical_story_sha256": STORY_SHA256,
    "objective": "同一属性の矛盾を検出",
    "requirement_ids": ["FR-008"],
    "acceptance_criteria": ["conflict not silently resolved"],
    "test_suites": ["TST-007", "TST-020"],
}
EXPECTED_PREDECESSOR_SEMANTICS: Final[dict[str, object]] = {
    "classification": (
        "SOURCE_DERIVED_NON_EXECUTABLE_FACT_EXTRACTION_VALIDATION_REFERENCE_PLAN"
    ),
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "fact_inputs_available": False,
    "facts": [],
    "fact_ids": [],
    "derivations": [],
    "extraction": "NOT_EXECUTED",
    "validation": "NOT_EXECUTED",
    "repository": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "story_acceptance": False,
}
EXPECTED_PREDECESSOR: Final[dict[str, object]] = {
    "story_id": "ST-0602",
    "commit": PREDECESSOR_COMMIT,
    "relationship": "EMPTY_FACT_INPUT_REFERENCE_ONLY",
    "files": _artifact_rows(),
    "required_semantics": EXPECTED_PREDECESSOR_SEMANTICS,
}
EXPECTED_CANONICAL_CONTEXT: Final = {
    "authority": "DESCRIPTIVE_ONLY",
    "creates_runtime_contract": False,
    "conflict_policy": "DESCRIPTIVE_ONLY_NOT_BOUND",
    "evidence_requirement": "EVD-004_DESCRIPTIVE_ONLY_NOT_BOUND",
    "security_controls": "DESCRIPTIVE_ONLY_NOT_BOUND",
}
EXPECTED_INPUT_DEFAULTS: Final[dict[str, object]] = {
    "facts": [],
    "fact_ids": [],
    "fact_count": None,
}
EXPECTED_SELECTION_DEFAULTS: Final = {
    "conflict_rule": None,
    "comparator": None,
    "tolerance": None,
    "source": None,
    "value": None,
    "severity": None,
    "actor": None,
    "queue_selection": None,
    "resolution_policy": None,
}
EXPECTED_PROJECTION_DEFAULTS: Final[dict[str, object]] = {
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
EXPECTED_BLOCKERS: Final = [
    "FACT_INPUT_UNAVAILABLE",
    "COMPARATOR_NOT_DEFINED",
    "TOLERANCE_NOT_DEFINED",
    "SEVERITY_RULE_NOT_DEFINED",
    "REVIEW_QUEUE_NOT_CONFIGURED",
    "RESOLUTION_POLICY_NOT_DEFINED",
]
EXPECTED_REVIEW_AND_RESOLUTION: Final = {
    "comparison_status": "NOT_EXECUTED",
    "queue_status": "NOT_EXECUTED",
    "resolution_status": "NOT_EXECUTED",
    "automatic_resolution_enabled": False,
    "silent_resolution_allowed": False,
    "blockers": EXPECTED_BLOCKERS,
}
EXPECTED_ACTION_COUNTS: Final = {name: 0 for name in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION: Final = {
    "detector": "NOT_EXECUTED",
    "comparison": "NOT_EXECUTED",
    "review_queue": "NOT_EXECUTED",
    "resolution": "NOT_EXECUTED",
    "repository": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "api": "NOT_EXECUTED",
    "ui": "NOT_EXECUTED",
    "external": "NOT_EXECUTED",
    "action_counts": EXPECTED_ACTION_COUNTS,
}
EXPECTED_VERIFICATION: Final = {
    "predecessor_connection": "NOT_EXECUTED",
    "TST-007": "NOT_EXECUTED",
    "TST-020": "NOT_EXECUTED",
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
        _find(stories.get("stories"), "ST-0603", "authority.story"),
        EXPECTED_STORY,
        "authority.story",
    )


def _validate_predecessor_semantics(root: Path) -> None:
    contract = _load_yaml(root, PREDECESSOR_ARTIFACTS[1][0], "predecessor.contract")
    _exact(
        contract.get("classification"),
        EXPECTED_PREDECESSOR_SEMANTICS["classification"],
        "predecessor.contract.classification",
    )
    for key, expected in (
        ("executable", False),
        ("interface_only", True),
        ("decision", "NOT_READY"),
        ("story_acceptance", False),
    ):
        _exact(contract.get(key), expected, f"predecessor.contract.{key}")
    inputs = _mapping(contract.get("input_defaults"), "predecessor.contract.inputs")
    if any(value is not None for value in inputs.values()):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.contract.inputs")
    projection = _mapping(
        contract.get("fact_projection_defaults"), "predecessor.contract.projection"
    )
    if any(value != [] for value in projection.values()):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.contract.projection")
    execution = _mapping(
        contract.get("execution_boundary"), "predecessor.contract.execution"
    )
    for key in ("extraction", "validation", "repository", "database", "job", "event"):
        _exact(
            execution.get(key),
            "NOT_EXECUTED",
            f"predecessor.contract.execution.{key}",
        )

    plan = _load_json(root, PREDECESSOR_ARTIFACTS[2][0], "predecessor.plan")
    document = _mapping(plan.get("document"), "predecessor.plan.document")
    _exact(document.get("decision"), "NOT_READY", "predecessor.plan.decision")
    _exact(
        document.get("story_acceptance"),
        False,
        "predecessor.plan.story_acceptance",
    )
    _exact(
        plan.get("input_boundary"),
        EXPECTED_INPUT_ABSENCE,
        "predecessor.plan.input_boundary",
    )
    _exact(
        plan.get("fact_projection"),
        EXPECTED_EMPTY_FACT_PROJECTION,
        "predecessor.plan.fact_projection",
    )


EXPECTED_INPUT_ABSENCE: Final = {
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
EXPECTED_EMPTY_FACT_PROJECTION: Final[dict[str, list[object]]] = {
    "facts": [],
    "fact_ids": [],
    "derivations": [],
    "validation_records": [],
    "manual_review_records": [],
}


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["schema_version"], 1, "schema_version")
    _exact(contract["story_id"], "ST-0603", "story_id")
    _exact(
        contract["classification"],
        "SOURCE_DERIVED_NONEXECUTABLE_FACT_CONFLICT_REVIEW_REFERENCE_PLAN",
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
    _exact(contract["predecessor"], EXPECTED_PREDECESSOR, "predecessor")
    _exact(
        contract["canonical_context"],
        EXPECTED_CANONICAL_CONTEXT,
        "canonical_context",
    )
    _exact(contract["input_defaults"], EXPECTED_INPUT_DEFAULTS, "input_defaults")
    _exact(
        contract["selection_defaults"],
        EXPECTED_SELECTION_DEFAULTS,
        "selection_defaults",
    )
    _exact(
        contract["projection_defaults"],
        EXPECTED_PROJECTION_DEFAULTS,
        "projection_defaults",
    )
    _exact(
        contract["review_and_resolution_defaults"],
        EXPECTED_REVIEW_AND_RESOLUTION,
        "review_and_resolution_defaults",
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
    _validate_predecessor_semantics(root)
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
        "predecessor_binding": contract["predecessor"],
        "canonical_context": contract["canonical_context"],
        "input_boundary": contract["input_defaults"],
        "selection_boundary": contract["selection_defaults"],
        "conflict_projection": contract["projection_defaults"],
        "review_and_resolution": contract["review_and_resolution_defaults"],
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
            "id": "RAOS-ST0603-FACT-CONFLICT-REVIEW-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0603",
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
            "predecessor_commit": PREDECESSOR_COMMIT,
            "predecessor_inputs": _artifact_uri_rows(),
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
                "SOURCE_DERIVED_NONEXECUTABLE_FACT_CONFLICT_REVIEW_REFERENCE_PLAN"
            ),
            "executable": False,
            "interface_only": True,
            "decision": "NOT_READY",
            "canonical_context": "DESCRIPTIVE_ONLY",
            "facts_available": False,
            "fact_count": None,
            "comparison_count": None,
            "conflict_count": None,
            "finding_count": None,
            "queue_count": None,
            "resolution_count": None,
            "comparison": "NOT_EXECUTED",
            "review_queue": "NOT_EXECUTED",
            "resolution": "NOT_EXECUTED",
            "automatic_resolution_enabled": False,
            "silent_resolution_allowed": False,
            "repository": "NOT_EXECUTED",
            "database": "NOT_EXECUTED",
            "event": "NOT_EXECUTED",
            "api": "NOT_EXECUTED",
            "ui": "NOT_EXECUTED",
            "formal_tst_007": "NOT_EXECUTED",
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
    except (FactConflictReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0603 Fact conflict-review reference plan checked"
        if args.check
        else "ST-0603 Fact conflict-review reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
