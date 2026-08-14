#!/usr/bin/env python3
"""Build the non-executable ST-0705 AI output-validation reference plan."""

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
    "changes/st-0705/contracts/ai-output-validation-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0705/generated/ai-output-validation-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0705/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0705_ai_output_validation_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0705/README.md")
TEST_PATHS: Final = (
    Path("tests/st0705/conftest.py"),
    Path("tests/st0705/test_contract.py"),
    Path("tests/st0705/test_generation.py"),
    Path("tests/st0705/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (README_PATH, CONTRACT_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
MAX_SOURCE_BYTES: Final = base.MAX_DOCUMENT_BYTES

INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
BACKLOG_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
AI_DESIGN_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_05_ai_agent_prompt_routing_evaluation_design_v0.1.md"
)
QUALITY_GATE_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/ai/RAOS_05_quality_gate_catalog_v0.1.yaml"
)
FAILURE_TAXONOMY_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/ai/RAOS_05_failure_taxonomy_v0.1.yaml"
)
SECURITY_CONTROL_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)
TEST_SUITE_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)

AUTHORITY_SHA256: Final[dict[Path, str]] = {
    INTEGRATION_PATH: "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    BACKLOG_PATH: "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    AI_DESIGN_PATH: "475e4b6b4490110fd9f94a07aaf4cf979bea99d59b7ef8b95ba0fdbe61219476",
    QUALITY_GATE_PATH: "a4664f082662ced52c3316ffa95ba0a7e0362d87401871e7fc7f5fbb6a77ecdc",
    FAILURE_TAXONOMY_PATH: "55db49d67678a1d8052fd4da9035ebfe2516913659c528bccd9f1a0313b38504",
    SECURITY_CONTROL_PATH: "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    TEST_SUITE_PATH: "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
}
AUTHORITY_PATHS: Final = tuple(AUTHORITY_SHA256)

ST0702_PATHS: Final = (
    Path("changes/st-0702/README.md"),
    Path("changes/st-0702/contracts/context-pack-reference-plan.v1.yaml"),
    Path("changes/st-0702/generated/context-pack.reference-plan.v1.json"),
    Path("changes/st-0702/manifest.yaml"),
    Path("scripts/build_st0702_context_pack_reference_plan.py"),
    Path("tests/st0702/conftest.py"),
    Path("tests/st0702/test_contract.py"),
    Path("tests/st0702/test_generation.py"),
    Path("tests/st0702/test_negative_cases.py"),
)
ST0703_PLAN_PATH: Final = Path(
    "changes/st-0703/contracts/openai-responses-adapter.v1.yaml"
)
ST0703_PATHS: Final = (
    Path("changes/st-0703/README.md"),
    ST0703_PLAN_PATH,
    Path("changes/st-0703/generated/recorded-fixture-registry.v1.json"),
    Path("python/raos/domain/ai/provider.py"),
    Path("python/raos/ports/ai_provider.py"),
    Path("python/raos/adapters/openai_responses.py"),
)
ST0605_PATHS: Final = (
    Path("changes/st-0605/README.md"),
    Path("changes/st-0605/contracts/claim-evidence-coverage-reference-plan.v1.yaml"),
    Path("changes/st-0605/generated/claim-evidence-coverage-reference-plan.v1.json"),
    Path("changes/st-0605/manifest.yaml"),
    Path("scripts/build_st0605_claim_evidence_coverage_reference_plan.py"),
    Path("tests/st0605/conftest.py"),
    Path("tests/st0605/test_contract.py"),
    Path("tests/st0605/test_generation.py"),
    Path("tests/st0605/test_negative_cases.py"),
)
PREDECESSOR_SHA256: Final[dict[Path, str]] = {
    ST0702_PATHS[0]: "c0e31aec0c41ccd61d91c0f3fba464a06464686eb961e3b855cef703051184d9",
    ST0702_PATHS[1]: "dfaa44687787dc9c38442d4e0bb3dbd2091e12ba78ffbc1a430f8d02a92b0320",
    ST0702_PATHS[2]: "7286ed1b1510fa7d12818023e6fb9fecab5147f06c6dfc5dd898a35eb81342cb",
    ST0702_PATHS[3]: "0b0e2ad6051759e3f0c2b0c4c4f232f1a62afc5d7fefc91a6a6414d15bdc776e",
    ST0702_PATHS[4]: "76be5a7756b9da1f76dca5c825457fa9aa3fff75fe3409c00e0157ddcff18b96",
    ST0702_PATHS[5]: "264e9473e46515d4992542f38ea329887a316e9e9216a4db399727679df7f6ab",
    ST0702_PATHS[6]: "876b66542dd6f2ad338ed96aa7a2a793c3118e38329ee2da439cff8d48bc72df",
    ST0702_PATHS[7]: "f13d528f54216dfcba9b415acba7075bc28fb5263a4fa17ba0cbdafdda97c979",
    ST0702_PATHS[8]: "c2e116fb803a013b80ed52cde46f0f8f7bb5dd210436f89ce98f9bd1d8272808",
    ST0703_PATHS[0]: "18b91c6d0edad9546c2bef77d2b0ffb39ae01810d85f8d4945762fcb8972b83c",
    ST0703_PATHS[1]: "016396ae0e09152cdf46ad4e6b0e64c530d2c7435b3ff59dcac1c4056c8bdd09",
    ST0703_PATHS[2]: "680f0ba9150dba7d9bdcdb539f06a23606300fb25d596460d5dbe0ab3b569715",
    ST0703_PATHS[3]: "179f608a54c87037556f3c202b08fc7be3207081e9737466e24b9de84392e991",
    ST0703_PATHS[4]: "3b4ccb19ba26793251b938954c736fdc8be871d618312d3eea2d6a4eff1a5c62",
    ST0703_PATHS[5]: "d1ca262711e73af59923d852fdc299ecc9ba67ae29675fd8e2512ea357d26017",
    ST0605_PATHS[0]: "f5a59ab0542a95987720c5d9ec43ef4355d92cea2b7bafcf8851e510fb98cf4b",
    ST0605_PATHS[1]: "a8e1a07f2520b3b874d89fbfc44cd872fa84d6b193d2b433a4723e5e3523dd35",
    ST0605_PATHS[2]: "c691565befc1f49196a9b313543df8c0488cc19e7fc2ab78250fe98ab999cdb1",
    ST0605_PATHS[3]: "ca59f65b8265212d0abf415a39df28b3abe157ff060edf0b4c3c469ffb5f92cf",
    ST0605_PATHS[4]: "2609a41dd138eeb8574c51f91bf931385183748a72a0914c59a817148835595f",
    ST0605_PATHS[5]: "089d70a4d95bda6c984646153129cd091126199806136a71e2b8621a01cd1219",
    ST0605_PATHS[6]: "4dbfe43f08382899de0bd65901f91dda0831f64298ae3dafedb06fe6f20cff86",
    ST0605_PATHS[7]: "fd305593ae296ec6e763c5b88aa6ee89ff5aa25feb6b4296b3730d3b21f2e9e1",
    ST0605_PATHS[8]: "463e15c2ead5deab957cf755a7865e38d92a3fa4fb270a8886c4dc10fe42bd35",
}
PREDECESSOR_PATHS: Final = tuple(PREDECESSOR_SHA256)
EXPECTED_INPUT_SHA256: dict[Path, str] = {
    **AUTHORITY_SHA256,
    **PREDECESSOR_SHA256,
}

EXPECTED_DOCUMENT: Final = {
    "schema_version": "1.0.0",
    "story_id": "ST-0705",
    "classification": "SOURCE_DERIVED_NON_EXECUTABLE_AI_OUTPUT_VALIDATION_REFERENCE_PLAN",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "activation": False,
    "runtime_eligible": False,
    "authority": "SOURCE_DERIVED_REFERENCE_ONLY",
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
    "canonical_status": "UNCHANGED",
}
EXPECTED_AUTHORITY: Final = {
    "dependencies": ["ST-0702", "ST-0703", "ST-0605"],
    "requirement_ids": ["FR-007", "FR-008"],
    "test_suites": ["TST-019", "TST-020"],
    "open_decisions": [],
    "canonical_status_changes": False,
}
EXPECTED_PREDECESSOR_BOUNDARY: Final = {
    "binding": "EXACT_CURRENT_COMMITTED_BYTES_AND_SEMANTICS",
    "story_ids": ["ST-0702", "ST-0703", "ST-0605"],
    "recorded_schema_success_is_content_validation": False,
    "predecessor_runtime_activation": False,
}
EXPECTED_EVALUATION_BOUNDARY: Final = {
    "candidate_validation": "UNEVALUABLE",
    "content_validation": "UNEVALUABLE",
    "decision": "NOT_READY",
    "story_acceptance_satisfied": False,
    "schema_only_acceptance_forbidden": True,
    "event_emission": False,
}
OBSERVED_KEYS: Final = (
    "candidates",
    "facts",
    "claims",
    "mappings",
    "findings",
    "evidence",
    "reports",
)
EXPECTED_VALIDATION_STATE: Final[dict[str, object]] = {
    "validators": [],
    "candidates": [],
    "context": None,
    "facts": [],
    "claims": [],
    "mappings": [],
    "findings": [],
    "evidence": [],
    "reports": [],
    "observed_counts": {key: None for key in OBSERVED_KEYS},
}
ACTION_KEYS: Final = (
    "validation",
    "runtime",
    "provider",
    "job",
    "event",
    "formal",
    "live",
)
EXPECTED_EXECUTION_STATE: Final = {
    **{key: "NOT_EXECUTED" for key in ACTION_KEYS},
    "action_counts": {key: 0 for key in ACTION_KEYS},
    "external_actions": [],
}
EXPECTED_PROHIBITED_INFERENCES: Final = [
    "algorithm",
    "threshold",
    "mapping",
    "model",
    "provider",
    "cost",
    "identity",
    "persistence",
    "approval",
]
EXPECTED_ACCEPTANCE_BOUNDARY: Final = {
    "local_generation_only": True,
    "formal_tst_019": "NOT_EXECUTED",
    "formal_tst_020": "NOT_EXECUTED",
    "runtime_validation": "NOT_EXECUTED",
    "provider_validation": "NOT_EXECUTED",
    "staging_validation": "NOT_EXECUTED",
    "release_validation": "NOT_EXECUTED",
    "production_validation": "NOT_EXECUTED",
    "release_candidate_created": False,
    "story_acceptance": False,
}
EXPECTED_CONTRACT: Final = {
    "document": EXPECTED_DOCUMENT,
    "authority": EXPECTED_AUTHORITY,
    "predecessor_boundary": EXPECTED_PREDECESSOR_BOUNDARY,
    "evaluation_boundary": EXPECTED_EVALUATION_BOUNDARY,
    "validation_state": EXPECTED_VALIDATION_STATE,
    "execution_state": EXPECTED_EXECUTION_STATE,
    "prohibited_inferences": EXPECTED_PROHIBITED_INFERENCES,
    "acceptance_boundary": EXPECTED_ACCEPTANCE_BOUNDARY,
}
CONTRACT_KEYS: Final = tuple(EXPECTED_CONTRACT)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "source_bindings",
    "predecessor_bindings",
    "gate_catalog",
    "validator_catalog",
    "failure_catalog",
    "security_controls",
    "test_suites",
    "evaluation_boundary",
    "validation_state",
    "execution_state",
    "prohibited_inferences",
    "acceptance_boundary",
)

GATE_IDS: Final = tuple(f"AIG-{number:03d}" for number in range(0, 100, 10))
VALIDATOR_CATALOG: Final = (
    "JSON parse and exact JSON Schema",
    "Unknown Property and Enum",
    "Resource ID and Manifest membership",
    "Fact ID and Subject/Product identity",
    "Number/date/unit/tax/currency exactness",
    "Rank/order preservation",
    "Forbidden Field/Term and review-body contamination marker",
    "Secret/credential pattern",
    "Output length and Claim count",
    "Hash/version consistency",
)
FAILURE_CODES: Final = (
    *(f"AI-OUT-{number:03d}" for number in range(1, 5)),
    *(f"AI-FCT-{number:03d}" for number in range(1, 5)),
    *(f"AI-POL-{number:03d}" for number in range(1, 6)),
)
SECURITY_IDS: Final = tuple(f"SEC-AI-{number:03d}" for number in range(1, 9))
TEST_IDS: Final = ("TST-019", "TST-020")

FEATURE_COMMITS: Final = {
    "ST-0702": "8d57e38b622285a4de1aeb2beeafcb3596b66d0b",
    "ST-0703": "aff94a21ac9f03886b19e32fef6e1c8b16de5b95",
    "ST-0605": "72541b0e855954005231368e48a7811abe4b3ea4",
}


class AiOutputValidationReferenceError(RuntimeError):
    """Sanitized, stable ST-0705 generation failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise AiOutputValidationReferenceError(code) from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, relative: Path, field: str) -> bytes:
    try:
        path = base._repository_regular_file(root, relative, field)
        content = path.read_bytes()
    except base.StagingDeploymentContractError:
        _fail("FILE_BOUNDARY_VIOLATION")
    except OSError:
        _fail("FILE_UNAVAILABLE")
    if len(content) > MAX_SOURCE_BYTES:
        _fail("SOURCE_SIZE_LIMIT")
    return content


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(type(key) is str for key in value):
        _fail(code)
    return cast(Mapping[str, Any], value)


def _rows(value: object, code: str) -> list[Mapping[str, Any]]:
    if type(value) is not list:
        _fail(code)
    result: list[Mapping[str, Any]] = []
    for row in cast(list[object], value):
        result.append(_mapping(row, code))
    return result


def _strict_match(actual: object, expected: object) -> None:
    boundary_failed = False
    try:
        base._strict_match(actual, expected, "contract")
    except base.StagingDeploymentContractError:
        boundary_failed = True
    if boundary_failed:
        _fail("CONTRACT_BOUNDARY_VIOLATION")


def validate_contract(contract: Mapping[str, Any]) -> None:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_BOUNDARY_VIOLATION")
    _strict_match(contract, EXPECTED_CONTRACT)


def load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        path = base._repository_regular_file(root, CONTRACT_PATH, "contract")
        loaded = base.load_yaml(path)
    except base.StagingDeploymentContractError:
        _fail("CONTRACT_READ_FAILED")
    contract = dict(_mapping(loaded, "CONTRACT_TYPE_MISMATCH"))
    validate_contract(contract)
    return contract


def _verify_pinned_inputs(root: Path) -> None:
    for relative, expected in EXPECTED_INPUT_SHA256.items():
        if _sha256(_read(root, relative, "pinned_input")) != expected:
            _fail("PINNED_INPUT_DRIFT")
    if _sha256(_read(root, HELPER_PATH, "helper")) != HELPER_SHA256:
        _fail("HELPER_DRIFT")


def _load_yaml_mapping(root: Path, relative: Path) -> Mapping[str, Any]:
    try:
        path = base._repository_regular_file(root, relative, "source")
        loaded = base.load_yaml(path)
    except base.StagingDeploymentContractError:
        _fail("SOURCE_PARSE_FAILED")
    return _mapping(loaded, "SOURCE_TYPE_MISMATCH")


def _load_json_mapping(root: Path, relative: Path) -> Mapping[str, Any]:
    try:
        path = base._repository_regular_file(root, relative, "source")
        loaded = base.load_json(path)
    except base.StagingDeploymentContractError:
        _fail("SOURCE_PARSE_FAILED")
    return _mapping(loaded, "SOURCE_TYPE_MISMATCH")


def _find_exact(
    rows: list[Mapping[str, Any]], key: str, value: str
) -> Mapping[str, Any]:
    matches = [row for row in rows if row.get(key) == value]
    if len(matches) != 1:
        _fail("SOURCE_RECORD_DRIFT")
    return matches[0]


def _validate_authority(
    root: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    backlog = _load_yaml_mapping(root, BACKLOG_PATH)
    story = _find_exact(_rows(backlog.get("stories"), "BACKLOG_DRIFT"), "id", "ST-0705")
    required_story = {
        "depends_on": ["ST-0702", "ST-0703", "ST-0605"],
        "requirement_ids": ["FR-007", "FR-008"],
        "acceptance_criteria": ["schema pass alone not accepted"],
        "test_suites": ["TST-019", "TST-020"],
        "open_decisions": [],
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }
    for key, expected in required_story.items():
        if story.get(key) != expected:
            _fail("STORY_SEMANTIC_DRIFT")

    gate_document = _load_yaml_mapping(root, QUALITY_GATE_PATH)
    gates = [dict(row) for row in _rows(gate_document.get("gates"), "GATE_DRIFT")]
    if tuple(row.get("id") for row in gates) != GATE_IDS:
        _fail("GATE_DRIFT")
    if any(row.get("blocking") is not True for row in gates):
        _fail("GATE_DRIFT")

    ai_design = _read(root, AI_DESIGN_PATH, "ai_design").decode("utf-8")
    if any(f"- {validator}" not in ai_design for validator in VALIDATOR_CATALOG):
        _fail("VALIDATOR_CATALOG_DRIFT")

    failure_document = _load_yaml_mapping(root, FAILURE_TAXONOMY_PATH)
    all_failures = _rows(failure_document.get("failures"), "FAILURE_DRIFT")
    failures = [dict(_find_exact(all_failures, "code", code)) for code in FAILURE_CODES]
    if tuple(row.get("domain") for row in failures) != (
        *("OUTPUT" for _ in range(4)),
        *("FACTUAL" for _ in range(4)),
        *("POLICY" for _ in range(5)),
    ):
        _fail("FAILURE_DRIFT")

    security_document = _load_yaml_mapping(root, SECURITY_CONTROL_PATH)
    all_controls = _rows(security_document.get("controls"), "SECURITY_DRIFT")
    controls = [
        dict(_find_exact(all_controls, "id", row_id)) for row_id in SECURITY_IDS
    ]

    suite_document = _load_yaml_mapping(root, TEST_SUITE_PATH)
    all_suites = _rows(suite_document.get("suites"), "TEST_SUITE_DRIFT")
    suites = [dict(_find_exact(all_suites, "id", row_id)) for row_id in TEST_IDS]
    if any(row.get("execution_status") != "NOT_EXECUTED" for row in suites):
        _fail("TEST_SUITE_DRIFT")
    return gates, failures, controls, suites


def _validate_predecessors(root: Path) -> None:
    st0702 = _load_yaml_mapping(root, ST0702_PATHS[1])
    st0702_document = _mapping(st0702.get("document"), "ST0702_DRIFT")
    if (
        st0702_document.get("executable") is not False
        or st0702_document.get("decision") != "NOT_READY"
        or st0702_document.get("story_acceptance") is not False
    ):
        _fail("ST0702_SEMANTIC_DRIFT")
    st0702_plan = _load_json_mapping(root, ST0702_PATHS[2])
    st0702_execution = _mapping(st0702_plan.get("execution_boundary"), "ST0702_DRIFT")
    if (
        st0702_execution.get("provider_call") != "NOT_EXECUTED"
        or st0702_execution.get("event_emission") != "NOT_EXECUTED"
    ):
        _fail("ST0702_SEMANTIC_DRIFT")

    st0703 = _load_yaml_mapping(root, ST0703_PLAN_PATH)
    authority = _mapping(st0703.get("implementation_authority"), "ST0703_DRIFT")
    recorded = _mapping(st0703.get("recorded_exchange_contract"), "ST0703_DRIFT")
    canonical_json = _mapping(recorded.get("canonical_json"), "ST0703_DRIFT")
    request = _mapping(st0703.get("request_contract"), "ST0703_DRIFT")
    if (
        authority.get("authority") != "ST0703_RECORDED_SCOPE_ONLY"
        or canonical_json.get("allow_nan") is not False
        or request.get("call_limit_per_execute") != 1
    ):
        _fail("ST0703_SEMANTIC_DRIFT")

    st0605 = _load_yaml_mapping(root, ST0605_PATHS[1])
    if (
        st0605.get("executable") is not False
        or st0605.get("decision") != "NOT_READY"
        or st0605.get("story_acceptance") is not False
    ):
        _fail("ST0605_SEMANTIC_DRIFT")
    st0605_plan = _load_json_mapping(root, ST0605_PATHS[2])
    st0605_execution = _mapping(st0605_plan.get("execution_boundary"), "ST0605_DRIFT")
    if (
        st0605_execution.get("coverage_calculation") != "NOT_EXECUTED"
        or st0605_execution.get("event") != "NOT_EXECUTED"
    ):
        _fail("ST0605_SEMANTIC_DRIFT")


def _artifact_rows(root: Path, paths: Sequence[Path]) -> list[dict[str, object]]:
    return [
        {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(_read(root, relative, "artifact")),
            "sha256": EXPECTED_INPUT_SHA256[relative],
        }
        for relative in paths
    ]


def expected_authority_manifest_rows(root: Path = REPO_ROOT) -> list[dict[str, object]]:
    return _artifact_rows(root, AUTHORITY_PATHS)


def expected_predecessor_manifest_rows(
    root: Path = REPO_ROOT,
) -> list[dict[str, object]]:
    return _artifact_rows(root, PREDECESSOR_PATHS)


def expected_predecessor_bindings(root: Path = REPO_ROOT) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for story_id, paths in (
        ("ST-0702", ST0702_PATHS),
        ("ST-0703", ST0703_PATHS),
        ("ST-0605", ST0605_PATHS),
    ):
        row: dict[str, object] = {
            "story_id": story_id,
            "feature_commit": FEATURE_COMMITS[story_id],
            "binding": "EXACT_CURRENT_COMMITTED_BYTES_AND_SEMANTICS",
            "artifacts": _artifact_rows(root, paths),
            "runtime_activated": False,
            "story_acceptance_inherited": False,
        }
        if story_id == "ST-0703":
            row["recorded_schema_success_is_content_validation"] = False
            row["content_validation"] = "NOT_EXECUTED"
        rows.append(row)
    return rows


def rebind_predecessor_hash_for_test(
    *,
    root: Path,
    relative: Path,
    digest: str,
    monkeypatch: Any,
) -> None:
    del root
    if relative not in PREDECESSOR_SHA256 or len(digest) != 64:
        _fail("TEST_REBIND_REJECTED")
    updated = dict(EXPECTED_INPUT_SHA256)
    updated[relative] = digest
    monkeypatch.setattr(sys.modules[__name__], "EXPECTED_INPUT_SHA256", updated)


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, object]:
    validate_contract(contract)
    _verify_pinned_inputs(root)
    gates, failures, controls, suites = _validate_authority(root)
    _validate_predecessors(root)
    document: dict[str, object] = {
        "document": EXPECTED_DOCUMENT,
        "authority": EXPECTED_AUTHORITY,
        "source_bindings": expected_authority_manifest_rows(root),
        "predecessor_bindings": expected_predecessor_bindings(root),
        "gate_catalog": gates,
        "validator_catalog": list(VALIDATOR_CATALOG),
        "failure_catalog": failures,
        "security_controls": controls,
        "test_suites": suites,
        "evaluation_boundary": EXPECTED_EVALUATION_BOUNDARY,
        "validation_state": EXPECTED_VALIDATION_STATE,
        "execution_state": EXPECTED_EXECUTION_STATE,
        "prohibited_inferences": EXPECTED_PROHIBITED_INFERENCES,
        "acceptance_boundary": EXPECTED_ACCEPTANCE_BOUNDARY,
    }
    if tuple(document) != PLAN_KEYS:
        _fail("PLAN_INVENTORY_DRIFT")
    return document


def _json_bytes(document: Mapping[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=False,
            )
            + "\n"
        ).encode("utf-8")
    except TypeError, ValueError:
        _fail("JSON_RENDER_FAILED")


def _yaml_bytes(document: Mapping[str, object]) -> bytes:
    try:
        return yaml.dump(
            document,
            Dumper=base.NoAliasDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ).encode("utf-8")
    except yaml.YAMLError:
        _fail("YAML_RENDER_FAILED")


def _source_artifacts(root: Path) -> list[dict[str, object]]:
    return [
        {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(_read(root, relative, "source")),
            "sha256": _sha256(_read(root, relative, "source")),
        }
        for relative in SOURCE_PATHS
    ]


def _manifest(root: Path, reference_bytes: bytes) -> bytes:
    document: dict[str, object] = {
        "document": {
            "schema_version": "1.0.0",
            "story_id": "ST-0705",
            "classification": "GENERATOR_OWNED_REFERENCE_PLAN_MANIFEST",
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": _source_artifacts(root),
        "provenance": {
            "authority_inputs": expected_authority_manifest_rows(root),
            "predecessor_inputs": expected_predecessor_manifest_rows(root),
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
            "generation_command": (
                "python scripts/build_st0705_ai_output_validation_reference_plan.py"
            ),
        },
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
    }
    return _yaml_bytes(document)


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    plan = reference_plan(contract, root)
    reference_bytes = _json_bytes(plan)
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest(root, reference_bytes),
    }


def _check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if tuple(expected) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT")
    for relative in GENERATED_PATHS:
        try:
            path = base._output_file(root, relative)
            actual = path.read_bytes()
        except base.StagingDeploymentContractError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE")
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        _check_outputs(root, outputs)
        return
    for relative in GENERATED_PATHS:
        try:
            base._atomic_write(root, relative, outputs[relative])
        except base.StagingDeploymentContractError:
            _fail("OUTPUT_WRITE_FAILED")


class _SilentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise SystemExit(2)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _SilentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(args.check))
    except (
        AiOutputValidationReferenceError,
        base.StagingDeploymentContractError,
    ) as exc:
        code = exc.code if hasattr(exc, "code") else "BOUNDARY_FAILURE"
        print(f"ERROR code={code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-0705 AI output validation reference plan checked"
        if args.check
        else "ST-0705 AI output validation reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
