#!/usr/bin/env python3
"""Build the non-executable ST-0702 context-pack reference plan."""

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
    "changes/st-0702/contracts/context-pack-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0702/generated/context-pack.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0702/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0702_context_pack_reference_plan.py")
README_PATH: Final = Path("changes/st-0702/README.md")
TEST_PATHS: Final = (
    Path("tests/st0702/conftest.py"),
    Path("tests/st0702/test_contract.py"),
    Path("tests/st0702/test_generation.py"),
    Path("tests/st0702/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st0702_context_pack_reference_plan.py"
)
EXPECTED_CONTRACT_SHA256: Final = (
    "4b916ccea6906ecd6795260adbd34e0e4657dcaf7104ab84cfee60aa5c672d33"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "00d791a17bea96a5dc4608876c37907effe53ebb3a8f7786ca7b98823faff5b9"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
STORY_SHA256: Final = "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
INTEGRATION_SHA256: Final = (
    "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
)
ST0604_FEATURE_COMMIT: Final = "24e9640f7fa2b681ea40bb539837e40403928ec8"
ST0701_BASE_COMMIT: Final = "d56da0c85035a85507636c025132550c0b1a7cd2"

ST0604_ARTIFACTS: Final = (
    (
        Path("changes/st-0604/README.md"),
        "5165b09e9049709005a4e2965ca2fb07e01172b4ef3e550892742fafc3e101c8",
    ),
    (
        Path(
            "changes/st-0604/contracts/source-packet-lifecycle-reference-plan.v1.yaml"
        ),
        "a80c41890e6bae7077728d1456f5a3b5d99b1877e047f581beff8ed41e0c2cec",
    ),
    (
        Path(
            "changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json"
        ),
        "00e6e974f9003ee92cb0a9b4a0ca5a975286e7fd41a6e32cf1224e312cd78cec",
    ),
    (
        Path("changes/st-0604/manifest.yaml"),
        "56144e0b9ab315a647d92c665f7502129d3576fac2d9524ca647dc29bfeabdc0",
    ),
    (
        Path("scripts/build_st0604_source_packet_lifecycle_reference_plan.py"),
        "74e2260b2e647129de96d38a8dff0477a8b43947539640dccbcbc35e2072267c",
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
ST0701_ARTIFACTS: Final = (
    (
        Path("changes/st-0701/README.md"),
        "58fcbaf403649f3717803a8d7bd60da8bb2df2e57139fffe42d3fb7112c962b6",
    ),
    (
        Path("changes/st-0701/contracts/ai-contract-registry-loader.v1.yaml"),
        "8898b6f49e692586598109a27c046ae6dff4423f59f81837af00f5c5ab8bb90a",
    ),
    (
        Path("changes/st-0701/generated/ai-task-registry.v1.json"),
        "33bbb3601aae2e02d37bf995a2522e67684befcd9a43ba4375b4a7685aedef07",
    ),
    (
        Path("changes/st-0701/manifest.yaml"),
        "6d73ea4b5fa5fdaeec8b6e115ca75ab8b246fe6aba5024d789734a19151e5f04",
    ),
    (
        Path("scripts/build_st0701_ai_registry.py"),
        "2876b4e3bdc678cd97c11452a0a48e2786279933cbf27c0320307d0eccc1d360",
    ),
    (
        Path("tests/st0701/conftest.py"),
        "a25d2a4025e99331dd5b82cc0e4df093fe75b8b52403c5c8de85f2e8df1dfb9b",
    ),
    (
        Path("tests/st0701/test_compiled_task_registry.py"),
        "bdc75302f0a901e2d0859c8fee03569db6d4f628f77515385d1c9a57d17e8854",
    ),
    (
        Path("tests/st0701/test_contract.py"),
        "d0fe98b31176b23d35d241aa9dd89bdc438412272528bdcffb5d045aa72fbe55",
    ),
    (
        Path("tests/st0701/test_generation.py"),
        "09fa81e4a46d8652c18b1993c200d508ff87e7970fc8f0222b8c6bbc387bf34e",
    ),
)
ST0701_REGISTRY_PATH: Final = ST0701_ARTIFACTS[2][0]
ST0701_MANIFEST_PATH: Final = ST0701_ARTIFACTS[3][0]

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "predecessors",
    "registry_projection",
    "packing_rules",
    "selection_defaults",
    "collection_defaults",
    "build_boundary",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_bindings",
    "registry_projection",
    "packing_rules",
    "selection_boundary",
    "collection_boundary",
    "build_boundary",
    "execution_boundary",
    "verification_boundary",
)
TASK_ROW_KEYS: Final = (
    "binding_sha256",
    "output_schema",
    "prompt",
    "route",
    "task",
    "task_sha256",
)
ACTION_COUNT_KEYS: Final = (
    "build",
    "select",
    "scan",
    "pack",
    "serialize",
    "hash",
    "estimate",
    "reduce_scope",
    "drop_item",
    "create_manifest",
    "provider_call",
    "network",
    "repository_write",
    "database_write",
    "job",
    "event",
    "external",
)

EXPECTED_STORY: Final = {
    "id": "ST-0702",
    "epic_id": "EPIC-07",
    "title": "Context pack builder",
    "objective": "Allowlist FactからCanonical inputを作る",
    "depends_on": ["ST-0604", "ST-0701"],
    "requirement_ids": ["FR-006"],
    "design_refs": [],
    "deliverables": ["manifest builder", "token budget"],
    "acceptance_criteria": ["important fact truncation fails"],
    "test_suites": ["TST-005", "TST-019"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": [],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST0702-CONTEXT-PACK-REFERENCE-PLAN-001",
    "version": "1.0.0",
    "story_id": "ST-0702",
    "classification": "SOURCE_DERIVED_NON_EXECUTABLE_CONTEXT_PACK_REFERENCE_PLAN",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
    "canonical_status": "UNCHANGED",
}
EXPECTED_AUTHORITY: Final = {
    "canonical_story": {
        "path": STORY_PATH.as_posix(),
        "sha256": STORY_SHA256,
        "story_id": "ST-0702",
    },
    "integration_precedence": {
        "path": INTEGRATION_PATH.as_posix(),
        "sha256": INTEGRATION_SHA256,
    },
    "authority_kind": "SOURCE_DERIVED_REFERENCE_ONLY",
    "changes_canonical_status": False,
}


def _artifact_rows(
    artifacts: Sequence[tuple[Path, str]],
) -> dict[str, str]:
    return {path.as_posix(): digest for path, digest in artifacts}


def _artifact_uri_rows(
    artifacts: Sequence[tuple[Path, str]],
) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in artifacts
    ]


EXPECTED_ST0604_SEMANTICS: Final = {
    "decision": "NOT_READY",
    "packet_count": None,
    "fact_count": None,
    "mapping_count": None,
    "approval": False,
    "generation_permitted": False,
    "transition_status": "UNAVAILABLE",
    "mapping_status": "UNAVAILABLE",
}
EXPECTED_ST0701_SEMANTICS: Final = {
    "task_count": 12,
    "complete_binding_metadata": True,
    "task_activation": False,
    "selected_provider": None,
    "provider_call": "NOT_EXECUTED",
    "route_execution": "NOT_EXECUTED",
    "network_access": False,
    "formal_validation": "NOT_EXECUTED",
}
EXPECTED_PREDECESSORS: Final = {
    "st0604": {
        "story_id": "ST-0604",
        "feature_commit": ST0604_FEATURE_COMMIT,
        "binding": "EXACT_COMMITTED_OWNED_BYTES",
        "artifacts": _artifact_rows(ST0604_ARTIFACTS),
        "required_semantics": EXPECTED_ST0604_SEMANTICS,
    },
    "st0701": {
        "story_id": "ST-0701",
        "base_commit": ST0701_BASE_COMMIT,
        "binding": "CURRENT_COMMITTED_OWNED_BYTES_AT_ST0702_BASE",
        "known_owner_debt": "EXPECTED_MANIFEST_ONLY_DRIFT",
        "artifacts": _artifact_rows(ST0701_ARTIFACTS),
        "required_semantics": EXPECTED_ST0701_SEMANTICS,
    },
}
EXPECTED_REGISTRY_PROJECTION: Final = {
    "source_path": ST0701_REGISTRY_PATH.as_posix(),
    "source_sha256": ST0701_ARTIFACTS[2][1],
    "order_source": "EXACT_SOURCE_ORDER",
    "projection": "FULL_BINDING_METADATA",
    "task_count": 12,
    "activation_inferred": False,
    "activated_task_count": None,
    "selected_task_count": None,
}
EXPECTED_PACKING_RULES: Final = {
    "available": {
        "typed_manifest_required": True,
        "input_manifest_check_required": True,
        "audit_manifest_check_required": True,
        "source_packet_requirement_is_task_scoped": True,
        "deterministic_repack_on_context_overflow_required": True,
        "silent_required_fact_truncation_forbidden": True,
        "only_allowlisted_inputs_may_be_considered": True,
        "denied_inputs_must_be_excluded": True,
        "task_input_and_output_bounds_are_descriptive_only": True,
    },
    "unavailable": {
        "context_pack_manifest_schema": None,
        "fact_field_mapping": None,
        "canonical_json_algorithm": None,
        "token_estimator": None,
        "token_overhead": None,
        "scope_reduction_algorithm": None,
        "important_to_required_promotion_rule": None,
        "recursive_input_scan_rule": None,
        "packing_algorithm": None,
    },
    "unavailable_status": "UNAVAILABLE",
}
EXPECTED_SELECTIONS: Final = {
    "task_code": None,
    "prompt_code": None,
    "route_code": None,
    "provider": None,
    "model": None,
    "source_packet_id": None,
    "source_packet_version": None,
    "article_plan_id": None,
    "context_pack_manifest_schema_id": None,
    "context_pack_manifest_schema_version": None,
    "canonical_json_algorithm": None,
    "token_estimator": None,
    "token_estimator_version": None,
    "packing_algorithm": None,
    "packing_algorithm_version": None,
    "output_schema_id": None,
    "environment": None,
    "credential_reference": None,
}
EXPECTED_COLLECTIONS: Final = {
    "source_packets": [],
    "facts": [],
    "claims": [],
    "policies": [],
    "manifests": [],
    "pack_items": [],
    "required_items": [],
    "important_items": [],
    "optional_items": [],
    "dropped_items": [],
    "provider_requests": [],
    "provider_responses": [],
    "source_packet_count": None,
    "fact_count": None,
    "claim_count": None,
    "policy_count": None,
    "manifest_count": None,
    "pack_item_count": None,
    "required_item_count": None,
    "important_item_count": None,
    "optional_item_count": None,
    "dropped_item_count": None,
}
EXPECTED_BUILD_BOUNDARY: Final = {
    "build_permitted": False,
    "provider_call_permitted": False,
    "manifest_creation_permitted": False,
    "context_pack": None,
    "context_pack_manifest": None,
    "context_pack_sha256": None,
    "context_pack_byte_size": None,
    "estimated_input_tokens": None,
    "estimated_overhead_tokens": None,
    "context_overflow": None,
    "scope_reduction_records": [],
    "decision": "NOT_READY",
    "blockers": [
        "APPROVED_SOURCE_PACKET_UNAVAILABLE",
        "FACTS_UNAVAILABLE",
        "CONTEXT_PACK_MANIFEST_SCHEMA_UNAVAILABLE",
        "FACT_FIELD_MAPPING_UNAVAILABLE",
        "PACKING_ALGORITHM_UNAVAILABLE",
        "CANONICAL_JSON_ALGORITHM_UNAVAILABLE",
        "TOKEN_ESTIMATOR_UNAVAILABLE",
        "SCOPE_REDUCTION_ALGORITHM_UNAVAILABLE",
        "GENERATION_PERMISSION_FALSE",
    ],
}
EXPECTED_ACTION_COUNTS: Final = {key: 0 for key in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION: Final = {
    "build": "NOT_EXECUTED",
    "selection": "NOT_EXECUTED",
    "recursive_scan": "NOT_EXECUTED",
    "packing": "NOT_EXECUTED",
    "serialization": "NOT_EXECUTED",
    "hashing": "NOT_EXECUTED",
    "token_estimation": "NOT_EXECUTED",
    "scope_reduction": "NOT_EXECUTED",
    "item_drop": "NOT_EXECUTED",
    "manifest_creation": "NOT_EXECUTED",
    "provider_call": "NOT_EXECUTED",
    "network_access": "NOT_EXECUTED",
    "repository_write": "NOT_EXECUTED",
    "database_write": "NOT_EXECUTED",
    "job_execution": "NOT_EXECUTED",
    "event_emission": "NOT_EXECUTED",
    "external_action": "NOT_EXECUTED",
    "action_counts": EXPECTED_ACTION_COUNTS,
    "external_actions": [],
}
EXPECTED_VERIFICATION: Final = {
    "local_projection_only": True,
    "generated_output_is_recovery_or_runtime_evidence": False,
    "context_pack_built": False,
    "manifest_built": False,
    "provider_invoked": False,
    "formal_validation": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "story_acceptance": False,
}
EXPECTED_TASK_CODES: Final = (
    "ai.article_draft.v1",
    "ai.article_outline.v1",
    "ai.claim_extraction.v1",
    "ai.comparison_axis_suggestion.v1",
    "ai.internal_link_suggestion.v1",
    "ai.opportunity_assessment.v1",
    "ai.policy_assist.v1",
    "ai.quality_remediation.v1",
    "ai.refresh_diff_summary.v1",
    "ai.search_intent_classification.v1",
    "ai.source_packet_gap_analysis.v1",
    "ai.update_priority_explanation.v1",
)
EXPECTED_TOKEN_LIMITS: Final = (
    (120000, 32000, None),
    (70000, 12000, None),
    (100000, 20000, None),
    (60000, 12000, None),
    (50000, 10000, None),
    (80000, 12000, None),
    (120000, 24000, None),
    (100000, 18000, None),
    (80000, 14000, None),
    (70000, 16000, None),
    (100000, 14000, None),
    (50000, 10000, None),
)


class ContextPackReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


class NoAliasDumper(yaml.SafeDumper):
    """Keep the generated manifest explicit and diff-stable."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise ContextPackReferenceError(f"ST-0702 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return cast(list[Any], value)


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
            _same_exact(left_item, right_item)
            for left_item, right_item in zip(left_list, right_list, strict=True)
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


def _text(root: Path, relative: Path, field: str) -> str:
    try:
        return _read(root, relative, field).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail("UTF8_REQUIRED", field)


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_json(root / relative), field)


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _validate_hashes(root: Path) -> None:
    expected = (
        (CONTRACT_PATH, EXPECTED_CONTRACT_SHA256, "contract"),
        (STORY_PATH, STORY_SHA256, "authority.story"),
        (INTEGRATION_PATH, INTEGRATION_SHA256, "authority.integration"),
        (HELPER_PATH, HELPER_SHA256, "implementation.helper"),
        *((path, digest, "predecessor.st0604") for path, digest in ST0604_ARTIFACTS),
        *((path, digest, "predecessor.st0701") for path, digest in ST0701_ARTIFACTS),
    )
    for relative, digest, field in expected:
        if _sha256(_read(root, relative, field)) != digest:
            _fail("SOURCE_HASH_DRIFT", field)


def _validate_authority(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "authority.story")
    _exact(
        _find(stories.get("stories"), "ST-0702", "authority.story"),
        EXPECTED_STORY,
        "authority.story",
    )


def _validate_st0604(root: Path) -> None:
    contract = _load_yaml(root, ST0604_ARTIFACTS[1][0], "predecessor.st0604")
    _exact(contract.get("decision"), "NOT_READY", "predecessor.st0604.decision")
    _exact(contract.get("approval"), False, "predecessor.st0604.approval")
    _exact(
        contract.get("generation_permitted"),
        False,
        "predecessor.st0604.generation",
    )
    collections = _mapping(
        contract.get("collection_defaults"), "predecessor.st0604.collections"
    )
    _exact(collections.get("packet_count"), None, "predecessor.st0604.packet_count")
    _exact(collections.get("mapping_count"), None, "predecessor.st0604.mapping_count")
    predecessor_rows = _list(
        contract.get("predecessors"), "predecessor.st0604.predecessors"
    )
    st0602 = next(
        (
            _mapping(row, "predecessor.st0604.st0602")
            for row in predecessor_rows
            if type(row) is dict and row.get("story_id") == "ST-0602"
        ),
        None,
    )
    if st0602 is None:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0604.fact_count")
    semantics = _mapping(
        st0602.get("required_semantics"), "predecessor.st0604.st0602.semantics"
    )
    _exact(semantics.get("fact_count"), None, "predecessor.st0604.fact_count")
    lifecycle = _mapping(
        contract.get("lifecycle_defaults"), "predecessor.st0604.lifecycle"
    )
    _exact(
        lifecycle.get("transition_status"),
        "UNAVAILABLE",
        "predecessor.st0604.transition",
    )
    _exact(
        lifecycle.get("mapping_status"),
        "UNAVAILABLE",
        "predecessor.st0604.mapping",
    )


def _registry(root: Path) -> Mapping[str, Any]:
    registry = _load_json(root, ST0701_REGISTRY_PATH, "predecessor.st0701.registry")
    if tuple(registry) != ("document", "task_count", "tasks"):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0701.registry")
    _exact(
        registry["document"],
        {
            "id": "RAOS-AI-TASK-REGISTRY-001",
            "status": "IMPLEMENTATION_CANDIDATE",
            "story_id": "ST-0701",
            "version": "1.0.0",
        },
        "predecessor.st0701.document",
    )
    _exact(registry["task_count"], 12, "predecessor.st0701.task_count")
    tasks = _list(registry["tasks"], "predecessor.st0701.tasks")
    if len(tasks) != 12:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0701.tasks")
    task_codes: list[str] = []
    token_limits: list[tuple[object, object, object]] = []
    for index, raw_row in enumerate(tasks):
        row = _mapping(raw_row, "predecessor.st0701.task")
        if tuple(row) != TASK_ROW_KEYS:
            _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0701.task")
        task = _mapping(row.get("task"), "predecessor.st0701.task.metadata")
        code = task.get("task_code")
        if type(code) is not str:
            _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0701.task_code")
        task_codes.append(code)
        token_limits.append(
            (
                task.get("max_input_tokens"),
                task.get("max_output_tokens"),
                task.get("max_output_characters"),
            )
        )
        if (
            task.get("network_access") is not False
            or task.get("can_change_state") is not False
        ):
            _fail("PREDECESSOR_SEMANTIC_DRIFT", f"predecessor.st0701.task.{index}")
    _exact(task_codes, list(EXPECTED_TASK_CODES), "predecessor.st0701.task_order")
    _exact(token_limits, list(EXPECTED_TOKEN_LIMITS), "predecessor.st0701.tokens")
    return registry


def _validate_st0701(root: Path) -> Mapping[str, Any]:
    registry = _registry(root)
    manifest = _load_yaml(root, ST0701_MANIFEST_PATH, "predecessor.st0701.manifest")
    boundary = _mapping(manifest.get("boundary"), "predecessor.st0701.boundary")
    _exact(
        boundary.get("task_activation_or_seed"),
        "NOT_IMPLEMENTED",
        "predecessor.st0701.activation",
    )
    _exact(
        boundary.get("provider_api"),
        "NOT_USED",
        "predecessor.st0701.provider",
    )
    _exact(boundary.get("network"), "NOT_USED", "predecessor.st0701.network")
    _exact(
        boundary.get("formal_tst_017"),
        "NOT_EXECUTED",
        "predecessor.st0701.validation",
    )
    readme = _text(root, ST0701_ARTIFACTS[0][0], "predecessor.st0701.readme")
    for fragment in (
        "does not activate any task",
        "call a provider",
        "does not activate or\nseed tasks",
    ):
        if fragment not in readme:
            _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st0701.readme")
    return registry


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    _exact(contract["authority"], EXPECTED_AUTHORITY, "authority")
    _exact(contract["predecessors"], EXPECTED_PREDECESSORS, "predecessors")
    _exact(
        contract["registry_projection"],
        EXPECTED_REGISTRY_PROJECTION,
        "registry_projection",
    )
    _exact(contract["packing_rules"], EXPECTED_PACKING_RULES, "packing_rules")
    _exact(contract["selection_defaults"], EXPECTED_SELECTIONS, "selection_defaults")
    _exact(contract["collection_defaults"], EXPECTED_COLLECTIONS, "collection_defaults")
    _exact(contract["build_boundary"], EXPECTED_BUILD_BOUNDARY, "build_boundary")
    _exact(contract["execution_boundary"], EXPECTED_EXECUTION, "execution_boundary")
    _exact(
        contract["verification_boundary"],
        EXPECTED_VERIFICATION,
        "verification_boundary",
    )
    _validate_hashes(root)
    _validate_authority(root)
    _validate_st0604(root)
    _validate_st0701(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def _token_limit_distribution(registry: Mapping[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_row in _list(registry["tasks"], "registry.tasks"):
        task = _mapping(
            _mapping(raw_row, "registry.task")["task"], "registry.task.metadata"
        )
        rows.append(
            {
                "task_code": task["task_code"],
                "max_input_tokens": task["max_input_tokens"],
                "max_output_tokens": task["max_output_tokens"],
                "max_output_characters": task["max_output_characters"],
            }
        )
    return rows


def reference_plan(
    contract: Mapping[str, Any], registry: Mapping[str, Any]
) -> dict[str, Any]:
    registry_projection = {
        **_mapping(contract["registry_projection"], "registry_projection"),
        "registry_document": registry["document"],
        "task_codes": list(EXPECTED_TASK_CODES),
        "token_limit_distribution": _token_limit_distribution(registry),
        "tasks": registry["tasks"],
    }
    plan: dict[str, Any] = {
        "document": contract["document"],
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "inventory_derivation": "FIXED_OWNER_INVENTORY_AT_ST0702_BASE",
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_bindings": contract["predecessors"],
        "registry_projection": registry_projection,
        "packing_rules": contract["packing_rules"],
        "selection_boundary": contract["selection_defaults"],
        "collection_boundary": contract["collection_defaults"],
        "build_boundary": contract["build_boundary"],
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
            "story_id": "ST-0604",
            "feature_commit": ST0604_FEATURE_COMMIT,
            "binding": "EXACT_COMMITTED_OWNED_BYTES",
            "inputs": _artifact_uri_rows(ST0604_ARTIFACTS),
        },
        {
            "story_id": "ST-0701",
            "base_commit": ST0701_BASE_COMMIT,
            "binding": "CURRENT_COMMITTED_OWNED_BYTES_AT_ST0702_BASE",
            "known_owner_debt": "EXPECTED_MANIFEST_ONLY_DRIFT",
            "inputs": _artifact_uri_rows(ST0701_ARTIFACTS),
        },
    ]


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0702-CONTEXT-PACK-REFERENCE-PLAN-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0702",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "canonical_story": {
                "uri": f"repo://{STORY_PATH.as_posix()}",
                "sha256": STORY_SHA256,
            },
            "integration_precedence": {
                "uri": f"repo://{INTEGRATION_PATH.as_posix()}",
                "sha256": INTEGRATION_SHA256,
            },
            "inventory_derivation": "FIXED_OWNER_INVENTORY_AT_ST0702_BASE",
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
            "classification": EXPECTED_DOCUMENT["classification"],
            "executable": False,
            "interface_only": True,
            "decision": "NOT_READY",
            "task_count": 12,
            "activation_inferred": False,
            "activated_task_count": None,
            "selected_task_count": None,
            "source_packet_count": None,
            "fact_count": None,
            "manifest_count": None,
            "pack_item_count": None,
            "build_permitted": False,
            "provider_call_permitted": False,
            "manifest_creation_permitted": False,
            "context_pack_built": False,
            "manifest_built": False,
            "provider_invoked": False,
            "runtime_actions": "NOT_EXECUTED",
            "action_count_total": 0,
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_019": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
            "known_predecessor_debt": "EXPECTED_MANIFEST_ONLY_DRIFT",
        },
    }
    return yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    registry = _validate_st0701(root)
    reference_bytes = _json_bytes(reference_plan(contract, registry))
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
    except (ContextPackReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0702 context-pack reference plan checked"
        if args.check
        else "ST-0702 context-pack reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
