#!/usr/bin/env python3
# ST-1904 owner generator; generated artifacts must not be hand-edited.
"""Build the maximum-safe disabled multi-category evaluation evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
for _import_root in (REPO_ROOT, PYTHON_ROOT):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from raos.adapters.recorded_multi_category import (  # noqa: E402
    CallerBytesRecordedMultiCategorySource,
)
from raos.application.catalog.multi_category import (  # noqa: E402
    MultiCategoryEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.catalog.multi_category import (  # noqa: E402
    MULTI_CATEGORY_PARSER_VERSION,
    MultiCategoryEvaluationCommand,
    MultiCategoryScope,
    canonical_json_bytes,
    report_projection,
)
from scripts import secure_generated_publication as _publication  # noqa: E402


CONTRACT_PATH: Final = Path("changes/st-1904/contracts/multi-category.v1.yaml")
FIXTURE_PATH: Final = Path(
    "changes/st-1904/fixtures/recorded/multi-category.synthetic.v1.json"
)
REPORT_PATH: Final = Path("changes/st-1904/generated/multi-category-evaluation.v1.json")
MANIFEST_PATH: Final = Path("changes/st-1904/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1904_multi_category.py")
HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
BASE_COMMIT: Final = "0aaaa69d7776c6e6c4d131246c57c06d2ec996a5"
RECORDING_ID: Final = "st1904_recorded_multi_category_v1"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)
OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1904/PREFLIGHT.md"),
    Path("changes/st-1904/README.md"),
    Path("changes/st-1904/completion/completion.v1.yaml"),
    Path("docs/worklogs/ST-1904.md"),
    Path("python/raos/domain/catalog/multi_category.py"),
    Path("python/raos/ports/multi_category.py"),
    Path("python/raos/application/catalog/multi_category.py"),
    Path("python/raos/adapters/recorded_multi_category.py"),
    GENERATOR_PATH,
    Path("tests/st1904/__init__.py"),
    Path("tests/st1904/conftest.py"),
    Path("tests/st1904/support.py"),
    Path("tests/st1904/test_contract.py"),
    Path("tests/st1904/test_service.py"),
    Path("tests/st1904/test_negative_cases.py"),
    Path("tests/st1904/test_generation.py"),
    Path("tests/st1904/test_security_boundaries.py"),
)
SOURCE_ARTIFACT_PATHS: Final = OWNED_SOURCE_PATHS + (HELPER_PATH,)


class MultiCategoryBuildError(RuntimeError):
    """Stable owner failure that cannot retain rejected source material."""

    __slots__ = ("code",)

    def __init__(self, code: str = "ST1904_BUILD_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST1904_BUILD_FAILED") -> NoReturn:
    raise MultiCategoryBuildError(code) from None


def sha256_bytes(content: bytes) -> str:
    if type(content) is not bytes:
        _fail("HASH_INPUT_INVALID")
    return hashlib.sha256(content).hexdigest()


def _repository_path(root: Path, relative: Path) -> Path:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, Path)
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("FILE_BOUNDARY_VIOLATION")
    absolute_root = Path(os.path.abspath(root))
    candidate = Path(os.path.abspath(absolute_root / relative))
    try:
        candidate.relative_to(absolute_root)
    except ValueError:
        _fail("FILE_BOUNDARY_VIOLATION")
    return candidate


def _read(root: Path, relative: Path) -> bytes:
    path = _repository_path(root, relative)
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_SOURCE_BYTES
        ):
            _fail("FILE_BOUNDARY_VIOLATION")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            expected = (before.st_dev, before.st_ino, before.st_size)
            if (opened.st_dev, opened.st_ino, opened.st_size) != expected:
                _fail("FILE_BOUNDARY_VIOLATION")
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    _fail("FILE_BOUNDARY_VIOLATION")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                _fail("FILE_BOUNDARY_VIOLATION")
            after = os.fstat(descriptor)
            named = path.lstat()
            if (after.st_dev, after.st_ino, after.st_size) != expected or (
                named.st_dev,
                named.st_ino,
                named.st_size,
            ) != expected:
                _fail("FILE_BOUNDARY_VIOLATION")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except MultiCategoryBuildError:
        raise
    except Exception:
        _fail("FILE_BOUNDARY_VIOLATION")


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueSafeLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str or key in result:
            _fail("YAML_DUPLICATE_OR_NONSTRING_KEY")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _parse_yaml(content: bytes) -> dict[str, Any]:
    if type(content) is not bytes or not content or len(content) > MAX_SOURCE_BYTES:
        _fail("YAML_INVALID")
    try:
        text = content.decode("utf-8", errors="strict")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail("YAML_COMPLEXITY_FORBIDDEN")
        loaded = yaml.load(text, Loader=_UniqueSafeLoader)
    except MultiCategoryBuildError:
        raise
    except Exception:
        _fail("YAML_INVALID")
    if type(loaded) is not dict:
        _fail("YAML_INVALID")
    return cast(dict[str, Any], loaded)


def _json_pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _fail("JSON_DUPLICATE_OR_NONSTRING_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail("JSON_INVALID")


def _parse_json(content: bytes) -> dict[str, Any]:
    if type(content) is not bytes or not content or len(content) > MAX_SOURCE_BYTES:
        _fail("JSON_INVALID")
    try:
        loaded: object = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_json_pairs,
            parse_constant=_reject_constant,
        )
    except MultiCategoryBuildError:
        raise
    except Exception:
        _fail("JSON_INVALID")
    if type(loaded) is not dict:
        _fail("JSON_INVALID")
    return cast(dict[str, Any], loaded)


def _mapping(value: object, code: str = "CONTRACT_INVALID") -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail(code)
    return cast(dict[str, Any], value)


def _list(value: object, code: str = "CONTRACT_INVALID") -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _string(value: object, code: str = "CONTRACT_INVALID") -> str:
    if type(value) is not str or not value:
        _fail(code)
    return value


def _canonical_output(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _validate_hash_binding(root: Path, row: object) -> Path:
    binding = _mapping(row)
    relative = Path(_string(binding.get("path")))
    if sha256_bytes(_read(root, relative)) != _string(binding.get("sha256")):
        _fail("SOURCE_HASH_DRIFT")
    return relative


def _find_by_id(rows: object, identifier: str, code: str) -> dict[str, Any]:
    found = [
        _mapping(row, code)
        for row in _list(rows, code)
        if type(row) is dict and row.get("id") == identifier
    ]
    if len(found) != 1:
        _fail(code)
    return found[0]


def _validate_canonical(root: Path, contract: dict[str, Any]) -> None:
    authority = _mapping(contract.get("authority"))
    for name in (
        "integration_precedence",
        "canonical_decisions",
        "open_decisions",
        "canonical_story",
        "test_acceptance_design",
        "test_catalog",
        "security_design",
        "data_classification",
        "security_controls",
        "threat_register",
    ):
        _validate_hash_binding(root, authority.get(name))

    backlog_binding = _mapping(authority.get("canonical_story"))
    backlog = _parse_yaml(_read(root, Path(_string(backlog_binding.get("path")))))
    story = _find_by_id(backlog.get("stories"), "ST-1904", "CANONICAL_STORY_DRIFT")
    if story != {
        "id": "ST-1904",
        "epic_id": "EPIC-19",
        "title": "Multiple categories",
        "objective": "カテゴリ別Identity/Freshness/Templateを追加",
        "depends_on": ["ST-1805"],
        "requirement_ids": [],
        "design_refs": [],
        "deliverables": ["post-MVP design revision and implementation"],
        "acceptance_criteria": ["separate release decision required"],
        "test_suites": ["TST-032"],
        "priority": "P2",
        "mvp": False,
        "size": "M",
        "open_decisions": [],
        "one_pr_preferred": True,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "DEFERRED_POST_MVP",
        "verification_status": "NOT_EXECUTED",
    }:
        _fail("CANONICAL_STORY_DRIFT")

    test_binding = _mapping(authority.get("test_catalog"))
    catalog = _parse_yaml(_read(root, Path(_string(test_binding.get("path")))))
    suite = _find_by_id(catalog.get("suites"), "TST-032", "TST032_CONTRACT_DRIFT")
    if (
        suite.get("release_blocking") is not True
        or suite.get("environments") != ["staging"]
        or suite.get("owner") != "Product Owner"
        or suite.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("TST032_CONTRACT_DRIFT")

    open_binding = _mapping(authority.get("open_decisions"))
    open_document = _parse_yaml(_read(root, Path(_string(open_binding.get("path")))))
    expected_open = {
        "OD-001": ("HUMAN_DECISION_REQUIRED", True),
        "OD-006": ("EXTERNAL_EVIDENCE_REQUIRED", True),
        "OD-007": ("HUMAN_DECISION_REQUIRED", True),
    }
    for identifier, (status_value, blocking) in expected_open.items():
        row = _find_by_id(open_document.get("items"), identifier, "OPEN_DECISION_DRIFT")
        if row.get("status") != status_value or row.get("blocking") is not blocking:
            _fail("OPEN_DECISION_DRIFT")

    control_binding = _mapping(authority.get("security_controls"))
    control_catalog = _parse_yaml(
        _read(root, Path(_string(control_binding.get("path"))))
    )
    expected_controls = tuple(_list(control_binding.get("controls")))
    observed_controls = {
        _string(_mapping(row).get("id"))
        for row in _list(control_catalog.get("controls"))
    }
    if len(expected_controls) != len(set(expected_controls)) or not set(
        expected_controls
    ).issubset(observed_controls):
        _fail("SECURITY_CONTROL_DRIFT")

    threat_binding = _mapping(authority.get("threat_register"))
    threat_catalog = _parse_yaml(_read(root, Path(_string(threat_binding.get("path")))))
    expected_threats = tuple(_list(threat_binding.get("threats")))
    observed_threats = {
        _string(_mapping(row).get("id")) for row in _list(threat_catalog.get("threats"))
    }
    if len(expected_threats) != len(set(expected_threats)) or not set(
        expected_threats
    ).issubset(observed_threats):
        _fail("THREAT_REGISTER_DRIFT")


def _validate_predecessor(root: Path, contract: dict[str, Any]) -> None:
    predecessor = _mapping(contract.get("predecessor"))
    if (
        predecessor.get("story_id") != "ST-1805"
        or predecessor.get("binding") != "EXACT_BASE_COMMIT_BYTES"
        or predecessor.get("base_commit") != BASE_COMMIT
    ):
        _fail("PREDECESSOR_INVALID")
    for relative_text, digest in _mapping(predecessor.get("artifacts")).items():
        if sha256_bytes(_read(root, Path(relative_text))) != _string(digest):
            _fail("PREDECESSOR_HASH_DRIFT")
    report = _parse_json(
        _read(
            root,
            Path("changes/st-1805/generated/portfolio-decision.local-blocked.v1.json"),
        )
    )
    decision = _mapping(report.get("decision"), "PREDECESSOR_SEMANTIC_DRIFT")
    authority = _mapping(report.get("authority"), "PREDECESSOR_SEMANTIC_DRIFT")
    if (
        report.get("overall") != "BLOCKED"
        or report.get("acceptance_criteria_satisfied") is not False
        or report.get("actual_observations") != []
        or decision.get("outcome") != "NO_DECISION"
        or decision.get("authorized") is not False
        or decision.get("category_limit_change") is not None
        or authority.get("category_change") != "NONE"
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT")


def _validate_dependencies(root: Path, contract: dict[str, Any]) -> None:
    dependencies = _mapping(contract.get("dependency_contracts"))
    for row in dependencies.values():
        _validate_hash_binding(root, row)

    runtime = _parse_json(
        _read(
            root,
            Path(
                _string(
                    _mapping(dependencies.get("st1702_recorded_fixture")).get("path")
                )
            ),
        )
    )
    identity_policy = _mapping(runtime.get("identityPolicy"), "DEPENDENCY_DRIFT")
    freshness = _mapping(runtime.get("freshnessPolicy"), "DEPENDENCY_DRIFT")
    category = _mapping(runtime.get("category"), "DEPENDENCY_DRIFT")
    runtime_authority = _mapping(runtime.get("authority"), "DEPENDENCY_DRIFT")
    if (
        runtime.get("dataClass") != "SYNTHETIC_VALIDATOR_FIXTURE_ONLY"
        or category.get("candidateApplied") is not False
        or category.get("activation") != "DISABLED_UNRESOLVED_OD_001"
        or identity_policy.get("automaticMergeEnabled") is not False
        or identity_policy.get("automaticSplitEnabled") is not False
        or identity_policy.get("humanReviewRequired") is not True
        or freshness.get("categoryOverrides") != []
        or freshness.get("providerOverrides") != []
        or freshness.get("staleNeverFresh") is not True
        or freshness.get("recommendationAutoReorder") != "FORBIDDEN"
        or any(
            runtime_authority.get(field) is not False
            for field in (
                "runtimeEnabled",
                "providerAccessEnabled",
                "networkEnabled",
                "persistenceEnabled",
                "publicationAuthorized",
                "activationAuthorized",
                "releaseAuthorized",
                "productionAuthorized",
            )
        )
    ):
        _fail("DEPENDENCY_DRIFT")

    identity = _parse_json(
        _read(
            root,
            Path(
                _string(
                    _mapping(dependencies.get("identity_reference_plan")).get("path")
                )
            ),
        )
    )
    identity_document = _mapping(identity.get("document"), "IDENTITY_DEPENDENCY_DRIFT")
    open_decision = _mapping(identity.get("open_decision"), "IDENTITY_DEPENDENCY_DRIFT")
    identity_boundary = _mapping(
        identity.get("identity_boundary"), "IDENTITY_DEPENDENCY_DRIFT"
    )
    human_review = _mapping(identity.get("human_review"), "IDENTITY_DEPENDENCY_DRIFT")
    if (
        identity_document.get("decision") != "NOT_READY"
        or open_decision.get("resolved") is not False
        or open_decision.get("safe_default")
        != "NO_AUTOMATIC_MERGE_HUMAN_REVIEW_REQUIRED"
        or identity_boundary.get("automatic_merge_enabled") is not False
        or identity_boundary.get("automatic_split_enabled") is not False
        or human_review.get("required") is not True
    ):
        _fail("IDENTITY_DEPENDENCY_DRIFT")

    freshness_contract = _parse_yaml(
        _read(
            root,
            Path(_string(_mapping(dependencies.get("freshness_policy")).get("path"))),
        )
    )
    freshness_document = _mapping(
        freshness_contract.get("document"), "FRESHNESS_DEPENDENCY_DRIFT"
    )
    if (
        freshness_document.get("id") != "RAOS-CONTENT-FRESH-001"
        or freshness_contract.get("policy_version") != "1.0.0"
        or not _string(freshness_contract.get("threshold_status")).startswith(
            "PROVISIONAL"
        )
        or "never_auto_reorder_recommendations"
        not in _list(freshness_contract.get("safe_degradation_priority"))
    ):
        _fail("FRESHNESS_DEPENDENCY_DRIFT")

    for name, expected_template_id in (
        ("template_selection_guide", "TPL-AT-001"),
        ("template_product_comparison", "TPL-AT-003"),
    ):
        binding = _mapping(dependencies.get(name))
        template = _parse_yaml(_read(root, Path(_string(binding.get("path")))))
        if (
            binding.get("template_id") != expected_template_id
            or template.get("template_id") != expected_template_id
            or template.get("version") != "1.0.0"
            or template.get("status") != "ACTIVE"
        ):
            _fail("TEMPLATE_DEPENDENCY_DRIFT")


def _validate_contract(root: Path, contract: dict[str, Any]) -> None:
    expected_keys = {
        "authority",
        "debt",
        "dependency_contracts",
        "document",
        "feature_scope",
        "multi_category_contract",
        "mutation_boundary",
        "owned_sources",
        "predecessor",
        "recorded_fixture",
        "result_contract",
        "verification_boundary",
    }
    if set(contract) != expected_keys:
        _fail("CONTRACT_KEYS_INVALID")
    document = _mapping(contract.get("document"))
    if document != {
        "schema_version": "1.0.0",
        "story_id": "ST-1904",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_MULTI_CATEGORY_CONTRACT_V1"
        ),
        "status": "LOCAL_CODE_COMPLETE_MAX_SAFE_DISABLED",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }:
        _fail("CONTRACT_DOCUMENT_INVALID")
    _validate_canonical(root, contract)
    _validate_predecessor(root, contract)
    _validate_dependencies(root, contract)

    fixture = _mapping(contract.get("recorded_fixture"))
    fixture_path = Path(_string(fixture.get("path")))
    fixture_bytes = _read(root, fixture_path)
    if (
        fixture_path != FIXTURE_PATH
        or fixture.get("bytes") != len(fixture_bytes)
        or fixture.get("sha256") != sha256_bytes(fixture_bytes)
        or fixture.get("binding_set_sha256")
        != "498defa989d3368651b8e1625393e88d358aedca0b541284fe7000efa83106ea"
        or fixture.get("synthetic") is not True
        or fixture.get("real_category_present") is not False
        or fixture.get("provider_evidence_present") is not False
        or fixture.get("publication_eligible") is not False
        or fixture.get("release_eligible") is not False
    ):
        _fail("FIXTURE_HASH_DRIFT")

    scope = _mapping(contract.get("feature_scope"))
    if (
        scope.get("default") != "DISABLED"
        or scope.get("closed_states")
        != ["DISABLED", "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY"]
        or scope.get("executable_environments") != ["ENV-DEV", "ENV-CI"]
        or scope.get("provider_neutral") is not True
        or scope.get("caller_bytes_only") is not True
        or scope.get("disabled_fails_before_port_call") is not True
        or any(
            scope.get(field) is not False
            for field in (
                "live_enabled_state_exists",
                "category_activation_state_exists",
                "template_activation_state_exists",
                "release_interface_exists",
            )
        )
    ):
        _fail("FEATURE_SCOPE_INVALID")

    category_contract = _mapping(contract.get("multi_category_contract"))
    if category_contract != {
        "real_category_selected": False,
        "synthetic_category_count": 2,
        "identity_rule_state": "NOT_DEFINED_UNRESOLVED_OD_006",
        "identity_disposition": "HUMAN_REVIEW_REQUIRED",
        "automatic_merge_enabled": False,
        "automatic_split_enabled": False,
        "freshness_rule_state": "PROVISIONAL_SAFE_DEFAULT_UNMODIFIED",
        "category_override": None,
        "provider_override": None,
        "stale_never_fresh": True,
        "recommendation_auto_reorder": "FORBIDDEN",
        "template_state": "SYNTHETIC_CANDIDATE_NOT_APPLIED",
        "template_active": False,
        "candidate_templates": {
            "synthetic_category_alpha": "TPL-AT-001",
            "synthetic_category_beta": "TPL-AT-003",
        },
    }:
        _fail("MULTI_CATEGORY_CONTRACT_INVALID")

    result = _mapping(contract.get("result_contract"))
    if result != {
        "outcome": "INTERFACE_COMPATIBLE_RECORDED_SYNTHETIC_ONLY",
        "authority": "NONE",
        "category_selection": "HUMAN_DECISION_REQUIRED",
        "identity_rules": "HUMAN_DECISION_REQUIRED",
        "freshness_sla": "HUMAN_DECISION_REQUIRED",
        "category_activation": "DISABLED",
        "template_activation": "DISABLED",
        "release_decision": "RELEASE_DECISION_REQUIRED",
        "canonical_status": "DEFERRED_POST_MVP",
        "formal_TST-032": "NOT_EXECUTED",
    }:
        _fail("RESULT_BOUNDARY_INVALID")

    mutation = _mapping(contract.get("mutation_boundary"))
    for field in (
        "provider_call",
        "network",
        "category_selection",
        "category_activation",
        "identity_decision",
        "freshness_override",
        "template_activation",
        "editorial_mutation",
        "article_html_mutation",
        "cta_mutation",
        "product_selection_mutation",
        "recommendation_order_mutation",
        "publication_snapshot_mutation",
        "publication",
        "status_apply",
    ):
        if mutation.get(field) != "FORBIDDEN":
            _fail("MUTATION_BOUNDARY_INVALID")
    if (
        mutation.get("credentials") != "NOT_USED"
        or mutation.get("persistence") != "NOT_EXECUTED"
    ):
        _fail("MUTATION_BOUNDARY_INVALID")

    owned = tuple(Path(_string(path)) for path in _list(contract.get("owned_sources")))
    if owned != OWNED_SOURCE_PATHS:
        _fail("OWNED_SOURCE_INVENTORY_DRIFT")


def _build_report(root: Path, contract: dict[str, Any]) -> bytes:
    fixture = _read(root, FIXTURE_PATH)
    fixture_contract = _mapping(contract.get("recorded_fixture"))
    command = MultiCategoryEvaluationCommand(
        recording_id=RECORDING_ID,
        source_sha256=sha256_bytes(fixture),
        source_bytes=len(fixture),
        expected_binding_set_sha256=_string(fixture_contract.get("binding_set_sha256")),
        scope=MultiCategoryScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY,
        parser_version=MULTI_CATEGORY_PARSER_VERSION,
    )
    service = MultiCategoryEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=CallerBytesRecordedMultiCategorySource(fixture),
    )
    report = service.evaluate(command)
    return _canonical_output(
        {
            "document": {
                "authority": "NONE",
                "canonical_status": "DEFERRED_POST_MVP",
                "classification": ("RECORDED_SYNTHETIC_MULTI_CATEGORY_EVALUATION_V1"),
                "formal_validation": "NOT_EXECUTED",
                "production_eligible": False,
                "status": "LOCAL_CODE_COMPLETE_MAX_SAFE_DISABLED",
                "story_id": "ST-1904",
                "version": "1.0.0",
            },
            "report": report_projection(report),
        }
    )


def _manifest_bytes(
    root: Path,
    contract: dict[str, Any],
    report: bytes,
) -> bytes:
    source_rows = [
        {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": len(content),
            "sha256": sha256_bytes(content),
        }
        for relative in SOURCE_ARTIFACT_PATHS
        for content in (_read(root, relative),)
    ]
    fixture = _read(root, FIXTURE_PATH)
    contract_bytes = _read(root, CONTRACT_PATH)
    parsed_report = _parse_json(report)
    report_payload = _mapping(parsed_report.get("report"), "REPORT_INVALID")
    manifest = {
        "document": {
            "id": "RAOS-ST1904-MULTI-CATEGORY-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1904",
            "status": "LOCAL_CODE_COMPLETE_MAX_SAFE_DISABLED",
            "canonical_status": "DEFERRED_POST_MVP",
            "authority": "NONE",
            "production_eligible": False,
        },
        "provenance": {
            "base_commit": BASE_COMMIT,
            "contract_uri": f"repo://{CONTRACT_PATH.as_posix()}",
            "contract_sha256": sha256_bytes(contract_bytes),
            "fixture_uri": f"repo://{FIXTURE_PATH.as_posix()}",
            "fixture_sha256": sha256_bytes(fixture),
            "binding_set_sha256": report_payload["binding_set_sha256"],
            "evaluation_report_sha256": report_payload["report_sha256"],
            "report_artifact_sha256": sha256_bytes(report),
        },
        "source_artifact_count": len(source_rows),
        "source_artifacts": source_rows,
        "generated_artifacts": [
            {
                "uri": f"repo://{REPORT_PATH.as_posix()}",
                "bytes": len(report),
                "sha256": sha256_bytes(report),
            }
        ],
        "boundary": {
            "default_enabled": False,
            "recorded_synthetic_only": True,
            "real_category_selected": False,
            "category_identity_resolved": False,
            "freshness_sla_resolved": False,
            "templates_activated": False,
            "live_enabled_state_exists": False,
            "provider_called": False,
            "network_used": False,
            "credential_read": False,
            "persistence_used": False,
            "editorial_mutated": False,
            "recommendation_mutated": False,
            "publication_snapshot_mutated": False,
            "publication_allowed": False,
            "release_authorized": False,
            "production_eligible": False,
        },
        "formal_status": {
            "formal_TST-032": "NOT_EXECUTED",
            "category_selection": "HUMAN_DECISION_REQUIRED",
            "identity_rules": "EXTERNAL_EVIDENCE_REQUIRED",
            "freshness_sla": "HUMAN_DECISION_REQUIRED",
            "live_provider": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
        },
        "debt": {
            "introduced": [],
            "external_or_formal_remaining": _mapping(contract.get("debt")).get(
                "external_or_formal_remaining"
            ),
        },
    }
    try:
        return yaml.safe_dump(
            manifest,
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8", errors="strict")
    except Exception:
        _fail("MANIFEST_RENDER_FAILED")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = _parse_yaml(_read(root, CONTRACT_PATH))
    _validate_contract(root, contract)
    report = _build_report(root, contract)
    return {
        REPORT_PATH: report,
        MANIFEST_PATH: _manifest_bytes(root, contract, report),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if tuple(expected) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT")
    for relative in GENERATED_PATHS:
        if _read(root, relative) != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT")


def _ensure_output_parents(root: Path) -> None:
    for relative in GENERATED_PATHS:
        parent = _repository_path(root, relative).parent
        try:
            parent.mkdir(mode=0o755, parents=False, exist_ok=True)
            metadata = parent.lstat()
        except Exception:
            _fail("OUTPUT_WRITE_FAILED")
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            _fail("OUTPUT_WRITE_FAILED")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    _ensure_output_parents(root)
    try:
        _publication.publish_generated(
            tuple(
                (_repository_path(root, relative), payload)
                for relative, payload in outputs.items()
            ),
            namespace="st1904",
            maximum_payload_bytes=MAX_SOURCE_BYTES,
        )
    except _publication.SecurePublicationError:
        _fail("OUTPUT_WRITE_FAILED")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        build(check=bool(arguments.check))
    except MultiCategoryBuildError as failure:
        print(f"ERROR code={failure.code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-1904 multi-category evaluation checked"
        if arguments.check
        else "ST-1904 multi-category evaluation generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "BASE_COMMIT",
    "CONTRACT_PATH",
    "FIXTURE_PATH",
    "GENERATED_PATHS",
    "GENERATOR_PATH",
    "HELPER_PATH",
    "MANIFEST_PATH",
    "MultiCategoryBuildError",
    "OWNED_SOURCE_PATHS",
    "REPORT_PATH",
    "REPO_ROOT",
    "SOURCE_ARTIFACT_PATHS",
    "build",
    "check_outputs",
    "main",
    "parse_args",
    "render_outputs",
    "sha256_bytes",
)
