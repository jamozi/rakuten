#!/usr/bin/env python3
"""Build the non-executable ST-0504 Human Review reference plan."""

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
    "changes/st-0504/contracts/product-identity-human-review-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0504/generated/product-identity-human-review-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0504/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0504_product_identity_human_review_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0504/README.md")
TEST_PATHS: Final = (
    Path("tests/st0504/conftest.py"),
    Path("tests/st0504/test_contract.py"),
    Path("tests/st0504/test_generation.py"),
    Path("tests/st0504/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0504_product_identity_human_review_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "00d791a17bea96a5dc4608876c37907effe53ebb3a8f7786ca7b98823faff5b9"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")

EXPECTED_SOURCES: Final = (
    (
        "integration",
        INTEGRATION_PATH.as_posix(),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "open_decisions",
        OPEN_DECISIONS_PATH.as_posix(),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "test_catalog",
        TEST_CATALOG_PATH.as_posix(),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "story",
        STORY_PATH.as_posix(),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
)
PREDECESSOR_COMMIT: Final = "b61d4dd83b87495dfd672bdf8960dc3b1ff29d79"
EXPECTED_PREDECESSOR_ARTIFACTS: Final = (
    (
        Path("changes/st-0503/README.md"),
        "aa956454a96c0c88dedd52982264fdf5ad66f181ee3c3717a1aea8204bfbf138",
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
    "document",
    "authority",
    "predecessor",
    "open_decision",
    "candidate_projection",
    "human_review_default",
    "identity_defaults",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_binding",
    "open_decision",
    "test_suites",
    "candidate_projection",
    "human_review",
    "identity_boundary",
    "execution_boundary",
    "verification_boundary",
)
ACTION_COUNT_KEYS: Final = (
    "evaluate",
    "score",
    "merge",
    "split",
    "assign",
    "review",
    "approve",
    "enqueue",
    "emit",
    "create",
    "update",
    "delete",
    "persist",
    "external",
)


class ProductIdentityReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise ProductIdentityReferenceError(f"ST-0504 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


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
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _expected_source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _expected_predecessor_artifacts() -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in EXPECTED_PREDECESSOR_ARTIFACTS
    ]


def _validate_hashes(root: Path) -> None:
    for _role, source_path, digest in EXPECTED_SOURCES:
        if _sha256(_read(root, Path(source_path), "authority.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "authority.source")
    for predecessor_path, digest in EXPECTED_PREDECESSOR_ARTIFACTS:
        if _sha256(_read(root, predecessor_path, "predecessor.artifact")) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", "predecessor.artifact")
    if _sha256(_read(root, HELPER_PATH, "implementation.helper")) != HELPER_SHA256:
        _fail("IMPLEMENTATION_HELPER_DRIFT", "implementation.helper")


EXPECTED_STORY: Final = {
    "id": "ST-0504",
    "epic_id": "EPIC-05",
    "title": "Product identity decision engine",
    "objective": "自動候補とHuman統合/分離Decision",
    "depends_on": ["ST-0503"],
    "requirement_ids": ["FR-003"],
    "design_refs": [],
    "deliverables": ["rule engine", "decision history"],
    "acceptance_criteria": ["ambiguous defaults to review", "supersede not mutate"],
    "test_suites": ["TST-007", "TST-020"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": ["OD-006"],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_OPEN_DECISION_ROW: Final = {
    "id": "OD-006",
    "topic": "category_product_identity_rules",
    "status": "EXTERNAL_EVIDENCE_REQUIRED",
    "required_by": "Catalog grouping",
    "owner": "Domain Editor",
    "decision_needed": "型番、容量、色、セット、JAN等の統合/分離ルールをカテゴリごとに定義",
    "default_behavior": "自動統合せずHuman Reviewへ送る",
    "blocking": True,
}
EXPECTED_TEST_SUITES: Final = (
    {
        "id": "TST-007",
        "name": "Property-based domain tests",
        "layer": "unit",
        "purpose": "冪等性、状態遷移、金額、正規化の不変条件",
        "candidate_tools": ["hypothesis", "fast-check"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
    {
        "id": "TST-020",
        "name": "Content AST and policy",
        "layer": "content",
        "purpose": "5記事型、Block、Claim、Recommendation、Disclosure",
        "candidate_tools": ["pytest", "schema fixtures"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
)


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "story")
    _exact(_find(stories.get("stories"), "ST-0504", "story"), EXPECTED_STORY, "story")
    decisions = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decision")
    _exact(
        _find(decisions.get("items"), "OD-006", "open_decision"),
        EXPECTED_OPEN_DECISION_ROW,
        "open_decision",
    )
    suites = _load_yaml(root, TEST_CATALOG_PATH, "test_suites")
    for expected in EXPECTED_TEST_SUITES:
        _exact(
            _find(suites.get("suites"), cast(str, expected["id"]), "test_suites"),
            expected,
            "test_suites",
        )


def _validate_predecessor_semantics(root: Path) -> None:
    readme = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[0][0], "predecessor.readme"
    ).decode("utf-8", errors="strict")
    required_readme = (
        "LOSSLESS_PASSTHROUGH",
        "`REVIEW_REQUIRED`",
        "confidence `SOURCE_ABSENT`",
        "canonical products",
        "repository `ABSENT`",
        "persistence false",
        "decision is `NOT_READY`",
    )
    if any(fragment not in readme for fragment in required_readme):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.readme")

    domain = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[1][0], "predecessor.domain"
    ).decode("utf-8", errors="strict")
    required_domain = (
        'REVIEW_REQUIRED = "REVIEW_REQUIRED"',
        'SOURCE_ABSENT = "SOURCE_ABSENT"',
        'LOSSLESS_STRUCTURAL_ONLY = "LOSSLESS_STRUCTURAL_ONLY"',
        "canonical_products=()",
        "grouping_decisions=()",
        "identity_decisions=()",
        "memberships=()",
        "merges=()",
        "splits=()",
        "repository=RepositoryBoundary.ABSENT",
        "persistence_executed=False",
        "database=ExecutionStatus.NOT_EXECUTED",
        "job=ExecutionStatus.NOT_EXECUTED",
        "event=ExecutionStatus.NOT_EXECUTED",
        "live_eligible=False",
        "decision=NormalizationDecision.NOT_READY",
    )
    if any(fragment not in domain for fragment in required_domain):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.domain")

    port = _read(root, EXPECTED_PREDECESSOR_ARTIFACTS[2][0], "predecessor.port").decode(
        "utf-8", errors="strict"
    )
    if "def normalize(" not in port or any(
        fragment in port
        for fragment in ("def save(", "def merge(", "def approve(", "def persist(")
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.port")

    application = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[3][0], "predecessor.application"
    ).decode("utf-8", errors="strict")
    if (
        "outcome = self._exchange.normalize(command)" not in application
        or "if outcome != expected:" not in application
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.application")


EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST0504-PRODUCT-IDENTITY-HUMAN-REVIEW-REFERENCE-PLAN-001",
    "version": "1.0.0",
    "story_id": "ST-0504",
    "classification": (
        "SOURCE_DERIVED_NON_EXECUTABLE_PRODUCT_IDENTITY_HUMAN_REVIEW_REFERENCE_PLAN"
    ),
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
    "effective_canonical_status": "UNCHANGED",
}
EXPECTED_PREDECESSOR_SEMANTICS: Final[dict[str, object]] = {
    "mode": "RECORDED_TEST_ONLY",
    "scope": "LOSSLESS_STRUCTURAL_ONLY",
    "provenance_preserved": True,
    "identity_status": "REVIEW_REQUIRED",
    "confidence_status": "SOURCE_ABSENT",
    "canonical_products": [],
    "grouping_decisions": [],
    "identity_decisions": [],
    "memberships": [],
    "merges": [],
    "splits": [],
    "repository": "ABSENT",
    "persistence_executed": False,
    "database": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "live_eligible": False,
    "decision": "NOT_READY",
    "approval": None,
}
EXPECTED_PREDECESSOR: Final = {
    "story_id": "ST-0503",
    "commit": PREDECESSOR_COMMIT,
    "status": "NORMALIZED_PROVENANCE_PRESERVING_CANDIDATES_ONLY",
    "connection_status": "INTERFACE_AVAILABLE_NOT_CONNECTED",
    "artifacts": _expected_predecessor_artifacts(),
    "semantics": EXPECTED_PREDECESSOR_SEMANTICS,
}
EXPECTED_OPEN_DECISION: Final[dict[str, object]] = {
    "id": "OD-006",
    "status": "EXTERNAL_EVIDENCE_REQUIRED",
    "blocking": True,
    "safe_default": "NO_AUTOMATIC_MERGE_HUMAN_REVIEW_REQUIRED",
    "resolved": False,
    "category_rules": [],
    "thresholds": [],
    "scores": [],
}
EXPECTED_CANDIDATE_PROJECTION: Final[dict[str, object]] = {
    "source": "ST0503_CANDIDATE_DRAFT_INTERFACE_ONLY",
    "provenance_required": True,
    "candidate_records": [],
    "candidate_count": None,
    "source_snapshots": [],
    "input_evidence": [],
    "empty_interpretation": "NO_RUNTIME_INPUT_OR_EVIDENCE_NOT_ZERO_CANDIDATES",
}
EXPECTED_HUMAN_REVIEW: Final[dict[str, object]] = {
    "required": True,
    "status": "REQUIRED_NOT_EXECUTED",
    "routing_status": "NOT_CONFIGURED",
    "queue": None,
    "route": None,
    "reviewer": None,
    "actor": None,
    "role": None,
    "assignment": None,
    "sla": None,
    "approval": None,
    "review_records": [],
    "delivery_records": [],
}
EXPECTED_IDENTITY: Final[dict[str, object]] = {
    "automatic_merge_enabled": False,
    "automatic_split_enabled": False,
    "category_rule": None,
    "threshold": None,
    "score": None,
    "confidence": None,
    "canonical_product_id": None,
    "identity_decisions": [],
    "membership_records": [],
    "merge_records": [],
    "split_records": [],
    "supersession_records": [],
    "decision_history": [],
    "external_actions": [],
}
EXPECTED_ACTION_COUNTS: Final = {name: 0 for name in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION: Final = {
    "enabled": False,
    "status": "DISABLED",
    "rule_engine": "NOT_EXECUTED",
    "human_review": "NOT_EXECUTED",
    "queue": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "repository": "ABSENT",
    "database": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "provider": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "action_counts": EXPECTED_ACTION_COUNTS,
}
EXPECTED_VERIFICATION: Final = {
    "formal_tst_007": "NOT_EXECUTED",
    "formal_tst_020": "NOT_EXECUTED",
    "rule_engine": "NOT_EXECUTED",
    "human_review": "NOT_EXECUTED",
    "decision_history": "NOT_EXECUTED",
    "repository": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "runtime": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "decision": "NOT_READY",
    "approval": None,
    "story_acceptance": False,
    "production_eligible": False,
    "effective_canonical_status": "UNCHANGED",
}


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    authority = _mapping(contract["authority"], "authority")
    if tuple(authority) != ("precedence", "sources"):
        _fail("CONTRACT_SCHEMA_DRIFT", "authority")
    _exact(
        authority["precedence"],
        "CANONICAL_INTEGRATION_THEN_STORY_THEN_OPEN_DECISION_AND_TEST_CATALOG",
        "authority.precedence",
    )
    _exact(authority["sources"], _expected_source_rows(), "authority.sources")
    _exact(contract["predecessor"], EXPECTED_PREDECESSOR, "predecessor")
    _exact(contract["open_decision"], EXPECTED_OPEN_DECISION, "open_decision")
    _exact(
        contract["candidate_projection"],
        EXPECTED_CANDIDATE_PROJECTION,
        "candidate_projection",
    )
    _exact(
        contract["human_review_default"],
        EXPECTED_HUMAN_REVIEW,
        "human_review_default",
    )
    _exact(contract["identity_defaults"], EXPECTED_IDENTITY, "identity_defaults")
    _exact(contract["execution_boundary"], EXPECTED_EXECUTION, "execution_boundary")
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
    verification = _mapping(contract["verification_boundary"], "verification")
    plan: dict[str, Any] = {
        "document": dict(_mapping(contract["document"], "document")),
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
        "open_decision": contract["open_decision"],
        "test_suites": [
            {
                **dict(row),
                "formal_execution": "NOT_EXECUTED",
                "evidence": None,
            }
            for row in EXPECTED_TEST_SUITES
        ],
        "candidate_projection": contract["candidate_projection"],
        "human_review": contract["human_review_default"],
        "identity_boundary": {
            **dict(_mapping(contract["identity_defaults"], "identity_defaults")),
            "safe_default": "NO_AUTOMATIC_MERGE_HUMAN_REVIEW_REQUIRED",
            "empty_interpretation": (
                "NO_IDENTITY_CONFIGURATION_DECISION_OR_HISTORY_NOT_ZERO_PRODUCTS"
            ),
        },
        "execution_boundary": contract["execution_boundary"],
        "verification_boundary": {
            "projection_only": True,
            "predecessor_connection": "NOT_EXECUTED",
            **dict(verification),
        },
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
            "id": "RAOS-ST0504-PRODUCT-IDENTITY-HUMAN-REVIEW-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0504",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": _expected_source_rows(),
            "predecessor_commit": PREDECESSOR_COMMIT,
            "predecessor_inputs": _expected_predecessor_artifacts(),
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
            "classification": EXPECTED_DOCUMENT["classification"],
            "executable": False,
            "interface_only": True,
            "od_006": "EXTERNAL_EVIDENCE_REQUIRED",
            "safe_default": "NO_AUTOMATIC_MERGE_HUMAN_REVIEW_REQUIRED",
            "automatic_merge_enabled": False,
            "automatic_split_enabled": False,
            "human_review": "NOT_EXECUTED",
            "rule_engine": "NOT_EXECUTED",
            "queue": "NOT_EXECUTED",
            "event": "NOT_EXECUTED",
            "repository": "ABSENT",
            "database": "NOT_EXECUTED",
            "formal_tst_007": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
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
        path = base._output_file(root, relative)  # noqa: SLF001
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
        base._atomic_write(root, relative, content)  # noqa: SLF001


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
    except (ProductIdentityReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0504 product identity Human Review reference plan checked"
        if args.check
        else "ST-0504 product identity Human Review reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
