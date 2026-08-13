#!/usr/bin/env python3
"""Build the inert, unapproved ST-1903 autonomous-publication policy pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final, NoReturn

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
HANDOFF_PATH: Final = Path(
    "changes/st-1903/DESIGN_HANDOFF_V1_ST1903_AUTONOMOUS_PUBLICATION_POLICY_V1.yaml"
)
CONTRACT_PATH: Final = Path(
    "changes/st-1903/contracts/autonomous-publication-policy.v1.yaml"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1903/generated/autonomous-publication-policy.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1903/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1903_autonomous_publication_policy.py")
GENERATED_PATHS: Final = (OUTPUT_PATH, MANIFEST_PATH)

GENERATION_COMMAND: Final = (
    "python scripts/build_st1903_autonomous_publication_policy.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"
MAX_SOURCE_BYTES: Final = 1_048_576
GENERATED_MODE: Final = 0o644
EXPECTED_CONTRACT_SEMANTIC_SHA256: Final = (
    "1c9c1ab87d42cb07a8b1d1be8920dbe30e0bda73a21f61549b1e3a041c1fd3a9"
)
EXPECTED_HANDOFF_SHA256: Final = (
    "f7bda7008d10ecf5e1b980602495e487f694552a15b31ca60ec45eb0c61d810b"
)
EXPECTED_HANDOFF_BYTES: Final = 18_189
EXPECTED_BASE_COMMIT: Final = "acd79848a1b5bc33974bbcdbf5e2bd1d8e2ca60d"
EXPECTED_BASE_TREE: Final = "85620e53419b65e3053e4454c6c1cb522de4459b"
EXPECTED_PARALLEL_COMMIT: Final = "6c014bee7004a9f1dfa726686b91f436fc9cd2f7"
EXPECTED_PARALLEL_TREE: Final = "9a1824f948b0bceb416417bfedaf101f1a452ebf"

SOURCE_ARTIFACT_PATHS: Final = (
    Path("changes/st-1903/README.md"),
    HANDOFF_PATH,
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("tests/st1903/conftest.py"),
    Path("tests/st1903/test_contract.py"),
    Path("tests/st1903/test_generation.py"),
    Path("tests/st1903/test_negative_cases.py"),
)

HANDOFF_KEYS: Final = (
    "schema",
    "document_version",
    "approval_status",
    "authority",
    "approved_story",
    "approved_scope",
    "source_design_refs",
    "repository_bindings",
    "policy_source_binding",
    "decision",
    "rationale",
    "rejected_alternatives",
    "constraints",
    "security_and_approval_gates",
    "acceptance_criteria",
    "required_test_evidence",
    "inherited_unresolved_canonical_open_decisions",
    "open_decisions",
    "canonical_reconciliation_status",
    "pro_review_status",
    "activation_status",
    "actions",
    "effects",
    "evidence",
)
CONTRACT_KEYS: Final = (
    "schema",
    "document_version",
    "policy_id",
    "policy_version",
    "story_id",
    "candidate_status",
    "authority",
    "activation",
    "canonical_reconciliation",
    "implementation_status",
    "verification_status",
    "production_readiness",
    "approval_binding",
    "repository_bindings",
    "prerequisites",
    "publication_policy",
    "code_change_policy",
    "execution_topology",
    "analytics_privacy_policy",
    "editorial_style_policy",
    "optimizer_containment",
    "canonical_conflicts",
    "blocking_open_decision_ids",
    "inherited_unresolved_canonical_open_decisions",
    "projection_boundary",
    "actions",
    "effects",
    "evidence",
)
EXPECTED_DENIED_CATEGORIES: Final = (
    "MEDICAL",
    "FINANCIAL",
    "LEGAL",
    "SAFETY",
    "MINORS",
)
EXPECTED_OWNER_GATED_CLASSES: Final = (
    "SECRETS",
    "PERMISSIONS",
    "DATABASE",
    "CANONICAL",
    "PUBLICATION",
    "RELEASE_POLICY",
)
EXPECTED_OPEN_DECISION_IDS: Final = tuple(f"OD-{number:03d}" for number in range(1, 16))
EXPECTED_NONBLOCKING_OPEN_DECISION_IDS: Final = ("OD-004",)


class BuildRefusal(RuntimeError):
    """A sanitized, stable build refusal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StrictLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: StrictLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    for key_node, _value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge" or key_node.value == "<<":
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "merge mapping key is forbidden",
                key_node.start_mark,
            )
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate mapping key",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


class NoAliasDumper(yaml.SafeDumper):
    """YAML dumper that never emits anchors or aliases."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str) -> NoReturn:
    raise BuildRefusal(code)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    ).encode("utf-8")


def _exact_keys(value: object, expected: Sequence[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or type(value) is not dict:
        _fail(code)
    if tuple(value) != tuple(expected):
        _fail(code)
    if not all(type(key) is str for key in value):
        _fail(code)
    return value


def _plain_data(value: object, code: str, *, depth: int = 0) -> None:
    if depth > 96:
        _fail(code)
    if value is None or type(value) in {str, int, bool, float}:
        return
    if type(value) is list:
        for item in value:
            _plain_data(item, code, depth=depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or key == "<<":
                _fail(code)
            _plain_data(item, code, depth=depth + 1)
        return
    _fail(code)


def _repo_path(path: Path, *, required_ancestors: bool = True) -> Path:
    pure = PurePosixPath(path.as_posix())
    if path.is_absolute() or not pure.parts or ".." in pure.parts:
        _fail("PATH_INVALID")
    try:
        root_metadata = REPO_ROOT.lstat()
    except OSError:
        _fail("PATH_ANCESTOR_INVALID")
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        _fail("PATH_ANCESTOR_INVALID")
    current = REPO_ROOT
    for part in pure.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if required_ancestors:
                _fail("SOURCE_MISSING")
            break
        except OSError:
            _fail("PATH_ANCESTOR_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("PATH_ANCESTOR_INVALID")
    return REPO_ROOT / path


def _read_regular(path: Path, *, required: bool = True) -> bytes | None:
    absolute = _repo_path(path, required_ancestors=required)
    try:
        metadata = absolute.lstat()
    except FileNotFoundError:
        if required:
            _fail("SOURCE_MISSING")
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("SOURCE_NOT_REGULAR")
    if metadata.st_size > MAX_SOURCE_BYTES:
        _fail("SOURCE_TOO_LARGE")
    try:
        data = absolute.read_bytes()
    except OSError:
        _fail("SOURCE_READ_FAILED")
    if len(data) != metadata.st_size:
        _fail("SOURCE_CHANGED_DURING_READ")
    return data


def _load_yaml(path: Path, code: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path)
    assert raw is not None
    try:
        text = raw.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                _fail(code)
        loaded = yaml.load(text, Loader=StrictLoader)
    except UnicodeDecodeError, yaml.YAMLError:
        _fail(code)
    _plain_data(loaded, code)
    if type(loaded) is not dict:
        _fail(code)
    return loaded, raw


def _git(*arguments: str, code: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except OSError, subprocess.SubprocessError:
        _fail(code)
    if result.returncode != 0:
        _fail(code)
    return result.stdout.strip()


def _validate_git_binding(commit: str, tree: str, code: str) -> None:
    if not isinstance(commit, str) or not isinstance(tree, str):
        _fail(code)
    if len(commit) != 40 or len(tree) != 40:
        _fail(code)
    if _git("cat-file", "-t", commit, code=code) != "commit":
        _fail(code)
    if _git("rev-parse", f"{commit}^{{tree}}", code=code) != tree:
        _fail(code)


def _git_is_ancestor(ancestor: str, descendant: str, code: str) -> bool:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except OSError, subprocess.SubprocessError:
        _fail(code)
    if result.returncode not in {0, 1}:
        _fail(code)
    return result.returncode == 0


def _validate_handoff(
    handoff: dict[str, Any],
    raw: bytes,
    contract: dict[str, Any],
    contract_raw: bytes,
) -> None:
    _exact_keys(handoff, HANDOFF_KEYS, "HANDOFF_SHAPE_INVALID")
    if len(raw) != EXPECTED_HANDOFF_BYTES or _sha256(raw) != EXPECTED_HANDOFF_SHA256:
        _fail("HANDOFF_BYTES_INVALID")
    if handoff["schema"] != "DESIGN_HANDOFF_V1":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if handoff["approval_status"] != "PENDING_OWNER_SHA256_APPROVAL":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if handoff["authority"] != "UNAPPROVED_POLICY_REVISION_CANDIDATE":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if handoff["approved_story"] != "ST-1903" or handoff["open_decisions"] != []:
        _fail("HANDOFF_AUTHORITY_INVALID")
    authority = handoff["decision"]["authority_model"]
    if authority["canonical_authority"] != "UNCHANGED":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if authority["canonical_reconciliation"] != "NOT_EXECUTED":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if (
        authority["normal_eligible_article_per_article_owner_approval_after_activation"]
        != "NOT_REQUIRED"
    ):
        _fail("HANDOFF_POLICY_INVALID")
    if handoff["security_and_approval_gates"]["activation"] != "DISABLED":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if handoff["security_and_approval_gates"]["approval_record"] != "ABSENT":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if handoff["canonical_reconciliation_status"] != "NOT_EXECUTED":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if handoff["pro_review_status"] != "REVIEW_NOT_OBTAINED":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if handoff["activation_status"] != "DISABLED":
        _fail("HANDOFF_AUTHORITY_INVALID")
    if (
        handoff["actions"] != []
        or handoff["effects"] != []
        or handoff["evidence"] != []
    ):
        _fail("HANDOFF_AUTHORITY_INVALID")
    policy_source_binding = _exact_keys(
        handoff["policy_source_binding"],
        (
            "path",
            "bytes",
            "sha256",
            "ordered_semantic_sha256",
            "generated_projection_path",
            "relationship",
        ),
        "HANDOFF_CONTRACT_BINDING_INVALID",
    )
    if policy_source_binding != {
        "path": CONTRACT_PATH.as_posix(),
        "bytes": len(contract_raw),
        "sha256": _sha256(contract_raw),
        "ordered_semantic_sha256": _sha256(_canonical_json(contract)),
        "generated_projection_path": OUTPUT_PATH.as_posix(),
        "relationship": "ROOT_HANDOFF_BINDS_EXACT_CONTRACT_BYTES_AND_ORDERED_SEMANTICS",
    }:
        _fail("HANDOFF_CONTRACT_BINDING_INVALID")
    bindings = handoff["repository_bindings"]
    if bindings["candidate_base"] != {
        "commit": EXPECTED_BASE_COMMIT,
        "tree": EXPECTED_BASE_TREE,
        "relationship": "EXACT_IMPLEMENTATION_BASE",
        "validation_requirement": "COMMIT_OBJECT_EXISTS_AND_TREE_MATCHES",
    }:
        _fail("HANDOFF_GIT_BINDING_INVALID")
    if bindings["parallel_lineage"] != {
        "commit": EXPECTED_PARALLEL_COMMIT,
        "tree": EXPECTED_PARALLEL_TREE,
        "relationship": "REFERENCE_ONLY_PARALLEL_LINEAGE_NOT_MERGED",
        "validation_requirement": "COMMIT_OBJECT_EXISTS_AND_TREE_MATCHES",
        "merged_into_candidate": False,
        "source_files_copied": False,
    }:
        _fail("HANDOFF_GIT_BINDING_INVALID")


def _validate_contract(contract: dict[str, Any]) -> None:
    _exact_keys(contract, CONTRACT_KEYS, "CONTRACT_SHAPE_INVALID")
    if _sha256(_canonical_json(contract)) != EXPECTED_CONTRACT_SEMANTIC_SHA256:
        _fail("CONTRACT_SEMANTICS_INVALID")
    if (
        contract["schema"] != "RAOS_AUTONOMOUS_PUBLICATION_POLICY_V1"
        or contract["story_id"] != "ST-1903"
        or contract["candidate_status"] != "PENDING_OWNER_SHA256_APPROVAL"
        or contract["authority"] != "UNAPPROVED_POLICY_REVISION_CANDIDATE"
        or contract["activation"] != "DISABLED"
        or contract["canonical_reconciliation"] != "NOT_EXECUTED"
        or contract["production_readiness"] != "NOT_READY"
    ):
        _fail("CONTRACT_AUTHORITY_INVALID")
    binding = contract["approval_binding"]
    if binding != {
        "target_kind": "DESIGN_HANDOFF_V1_ROOT_POLICY",
        "path": HANDOFF_PATH.as_posix(),
        "contract_binding_direction": (
            "ROOT_HANDOFF_BINDS_EXACT_CONTRACT_BYTES_AND_ORDERED_SEMANTICS"
        ),
        "status": "PENDING_OWNER_SHA256_APPROVAL",
        "exact_immutable_sha256_required": True,
        "one_repository_owner_approval_required": True,
        "normal_eligible_article_per_article_owner_approval_after_activation": (
            "NOT_REQUIRED"
        ),
        "exception_queue_does_not_restore_blanket_per_article_approval": True,
        "derived_contract_may_change_decision": False,
        "revision_requires_new_sha256_and_owner_decision": True,
        "approval_record": None,
        "self_approval_forbidden_for": [
            "GENERATOR",
            "OPTIMIZER",
            "CODEX",
            "PRO",
            "CI",
            "CMS",
            "PUBLICATION_ENGINE",
        ],
    }:
        _fail("CONTRACT_HANDOFF_BINDING_INVALID")
    if (
        binding["normal_eligible_article_per_article_owner_approval_after_activation"]
        != "NOT_REQUIRED"
    ):
        _fail("CONTRACT_POLICY_INVALID")
    prerequisites = contract["prerequisites"]
    expected_prerequisites = {
        "st_1805": "UNMET",
        "tst_032": "NOT_EXECUTED",
        "separate_release_decision": "NOT_OBTAINED",
        "canonical_reconciliation": "NOT_EXECUTED",
        "exact_sha256_owner_approval": "NOT_OBTAINED",
        "pro_review": "REVIEW_NOT_OBTAINED",
        "security_and_step_up_controls": "NOT_VALIDATED",
    }
    for name, status_value in expected_prerequisites.items():
        if prerequisites[name] != {"required": True, "current_status": status_value}:
            _fail("CONTRACT_PREREQUISITE_INVALID")
    publication = contract["publication_policy"]
    rate = publication["rate_limit"]
    if rate["maximum_new_articles_per_calendar_day"] != 1:
        _fail("CONTRACT_POLICY_INVALID")
    if (
        rate["catch_up"] != "FORBIDDEN"
        or rate["unused_capacity_rollover"] != "FORBIDDEN"
    ):
        _fail("CONTRACT_POLICY_INVALID")
    risk = publication["risk_gate"]
    if tuple(risk["denied_categories"]) != EXPECTED_DENIED_CATEGORIES:
        _fail("CONTRACT_POLICY_INVALID")
    if (
        risk["ordinary_eligible_result_after_activation"]
        != "CONTINUE_WITHOUT_PER_ARTICLE_OWNER_APPROVAL"
    ):
        _fail("CONTRACT_POLICY_INVALID")
    commercial = publication["commercial_component"]
    if commercial["maximum_weight_basis_points"] != 1000:
        _fail("CONTRACT_POLICY_INVALID")
    if commercial["activation"] != "DISABLED":
        _fail("CONTRACT_POLICY_INVALID")
    if (
        commercial["canonical_compatibility"]
        != "CONFLICT_REQUIRES_APPROVED_CANONICAL_REVISION"
    ):
        _fail("CONTRACT_POLICY_INVALID")
    if publication["pro_review"]["outage_result"] != "QUEUE_WITHOUT_PUBLICATION":
        _fail("CONTRACT_POLICY_INVALID")
    if publication["affiliate"]["source_field"] != "affiliateUrl":
        _fail("CONTRACT_POLICY_INVALID")
    if publication["affiliate"]["hand_built_url"] != "FORBIDDEN":
        _fail("CONTRACT_POLICY_INVALID")
    if publication["affiliate"]["raos_redirect"] != "FORBIDDEN":
        _fail("CONTRACT_POLICY_INVALID")
    if (
        publication["wordpress"]["ambiguous_write_result"]
        != "STOP_AND_QUEUE_RECONCILIATION"
    ):
        _fail("CONTRACT_POLICY_INVALID")
    if publication["wordpress"]["blind_retry_after_ambiguous_result"] != "FORBIDDEN":
        _fail("CONTRACT_POLICY_INVALID")
    code_policy = contract["code_change_policy"]
    if (
        tuple(code_policy["owner_required_change_classes"])
        != EXPECTED_OWNER_GATED_CLASSES
    ):
        _fail("CONTRACT_POLICY_INVALID")
    if code_policy["current_auto_merge_authority"] != "NONE":
        _fail("CONTRACT_AUTHORITY_INVALID")
    privacy = contract["analytics_privacy_policy"]
    if any(
        privacy[name] != "FORBIDDEN"
        for name in ("raw_ip", "full_user_agent", "fingerprinting", "invented_identity")
    ):
        _fail("CONTRACT_PRIVACY_INVALID")
    editorial = contract["editorial_style_policy"]
    if editorial["fabricated_first_person_experience"] != "FORBIDDEN":
        _fail("CONTRACT_EDITORIAL_INVALID")
    if editorial["detector_evasion"] != "FORBIDDEN":
        _fail("CONTRACT_EDITORIAL_INVALID")
    if any(contract["optimizer_containment"].values()):
        _fail("CONTRACT_OPTIMIZER_INVALID")
    decisions = contract["inherited_unresolved_canonical_open_decisions"]
    if (
        type(decisions) is not list
        or tuple(item["id"] for item in decisions) != EXPECTED_OPEN_DECISION_IDS
    ):
        _fail("CONTRACT_OPEN_DECISIONS_INVALID")
    nonblocking = tuple(item["id"] for item in decisions if item["blocking"] is False)
    if nonblocking != EXPECTED_NONBLOCKING_OPEN_DECISION_IDS:
        _fail("CONTRACT_OPEN_DECISIONS_INVALID")
    if any(item["candidate_resolution"] != "UNCHANGED" for item in decisions):
        _fail("CONTRACT_OPEN_DECISIONS_INVALID")
    expected_blocking = tuple(
        item["id"] for item in decisions if item["blocking"] is True
    )
    if tuple(contract["blocking_open_decision_ids"]) != expected_blocking:
        _fail("CONTRACT_OPEN_DECISIONS_INVALID")
    projection = contract["projection_boundary"]
    if any(projection.values()):
        _fail("CONTRACT_AUTHORITY_INVALID")
    if (
        contract["actions"] != []
        or contract["effects"] != []
        or contract["evidence"] != []
    ):
        _fail("CONTRACT_AUTHORITY_INVALID")


def _validate_source_refs(handoff: dict[str, Any]) -> None:
    refs = handoff["source_design_refs"]
    if type(refs) is not list or not refs:
        _fail("AUTHORITY_SOURCE_INVALID")
    seen: set[str] = set()
    for ref in refs:
        _exact_keys(ref, ("path", "bytes", "sha256"), "AUTHORITY_SOURCE_INVALID")
        path_text = ref["path"]
        if type(path_text) is not str or path_text in seen:
            _fail("AUTHORITY_SOURCE_INVALID")
        seen.add(path_text)
        data = _read_regular(Path(path_text))
        assert data is not None
        if len(data) != ref["bytes"] or _sha256(data) != ref["sha256"]:
            _fail("AUTHORITY_SOURCE_INVALID")


def _validate_canonical_records(contract: dict[str, Any]) -> None:
    backlog, _ = _load_yaml(
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "CANONICAL_BACKLOG_INVALID",
    )
    stories = backlog.get("stories")
    if type(stories) is not list:
        _fail("CANONICAL_BACKLOG_INVALID")
    by_id = {story.get("id"): story for story in stories if type(story) is dict}
    story = by_id.get("ST-1903")
    if story is None:
        _fail("CANONICAL_STORY_INVALID")
    if story.get("depends_on") != ["ST-1805"]:
        _fail("CANONICAL_STORY_INVALID")
    if story.get("implementation_status") != "DEFERRED_POST_MVP":
        _fail("CANONICAL_STORY_INVALID")
    if story.get("verification_status") != "NOT_EXECUTED":
        _fail("CANONICAL_STORY_INVALID")
    if story.get("test_suites") != ["TST-032"]:
        _fail("CANONICAL_STORY_INVALID")
    decisions_doc, _ = _load_yaml(
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "CANONICAL_OPEN_DECISIONS_INVALID",
    )
    items = decisions_doc.get("items")
    if type(items) is not list:
        _fail("CANONICAL_OPEN_DECISIONS_INVALID")
    canonical = {item.get("id"): item for item in items if type(item) is dict}
    projected = contract["inherited_unresolved_canonical_open_decisions"]
    if tuple(canonical) != EXPECTED_OPEN_DECISION_IDS:
        _fail("CANONICAL_OPEN_DECISIONS_INVALID")
    for row in projected:
        source = canonical[row["id"]]
        if row["canonical_status"] != source.get("status"):
            _fail("CANONICAL_OPEN_DECISIONS_INVALID")
        if row["blocking"] is not source.get("blocking"):
            _fail("CANONICAL_OPEN_DECISIONS_INVALID")


def load_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    handoff, handoff_raw = _load_yaml(HANDOFF_PATH, "HANDOFF_YAML_INVALID")
    contract, contract_raw = _load_yaml(CONTRACT_PATH, "CONTRACT_YAML_INVALID")
    _validate_contract(contract)
    _validate_handoff(handoff, handoff_raw, contract, contract_raw)
    _validate_source_refs(handoff)
    _validate_canonical_records(contract)
    _validate_git_binding(
        EXPECTED_BASE_COMMIT, EXPECTED_BASE_TREE, "BASE_GIT_BINDING_INVALID"
    )
    _validate_git_binding(
        EXPECTED_PARALLEL_COMMIT,
        EXPECTED_PARALLEL_TREE,
        "PARALLEL_GIT_BINDING_INVALID",
    )
    current_head = _git("rev-parse", "HEAD", code="CURRENT_HEAD_INVALID")
    if not _git_is_ancestor(
        EXPECTED_BASE_COMMIT, current_head, "BASE_GIT_BINDING_INVALID"
    ):
        _fail("BASE_GIT_BINDING_INVALID")
    if _git_is_ancestor(
        EXPECTED_PARALLEL_COMMIT, current_head, "PARALLEL_GIT_BINDING_INVALID"
    ):
        _fail("PARALLEL_LINEAGE_MERGED")
    return contract, handoff


def _artifact(path: Path) -> dict[str, object]:
    data = _read_regular(path)
    assert data is not None
    return {"path": path.as_posix(), "bytes": len(data), "sha256": _sha256(data)}


def _render_json(contract: dict[str, Any]) -> bytes:
    return (
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def _render_manifest(
    contract: dict[str, Any], handoff: dict[str, Any], output: bytes
) -> bytes:
    manifest: dict[str, object] = {
        "schema": "RAOS_ST1903_AUTONOMOUS_PUBLICATION_POLICY_MANIFEST_V1",
        "story_id": "ST-1903",
        "classification": "UNAPPROVED_NON_EXECUTABLE_NON_ATTESTING_POLICY_CANDIDATE",
        "generation": {
            "command": GENERATION_COMMAND,
            "check_command": CHECK_COMMAND,
            "contract_semantic_sha256": EXPECTED_CONTRACT_SEMANTIC_SHA256,
        },
        "approval_target": {
            "path": HANDOFF_PATH.as_posix(),
            "bytes": EXPECTED_HANDOFF_BYTES,
            "sha256": EXPECTED_HANDOFF_SHA256,
            "status": "PENDING_OWNER_SHA256_APPROVAL",
            "approval_record": None,
            "policy_source_binding": handoff["policy_source_binding"],
        },
        "repository_bindings": handoff["repository_bindings"],
        "authority_sources": handoff["source_design_refs"],
        "source_artifacts": [_artifact(path) for path in SOURCE_ARTIFACT_PATHS],
        "generated_artifacts": [
            {
                "path": OUTPUT_PATH.as_posix(),
                "bytes": len(output),
                "sha256": _sha256(output),
            }
        ],
        "boundary": {
            "activation": contract["activation"],
            "canonical_reconciliation": contract["canonical_reconciliation"],
            "pro_review": contract["prerequisites"]["pro_review"]["current_status"],
            "actions": [],
            "effects": [],
            "evidence": [],
        },
    }
    rendered = yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    )
    if any(token in rendered for token in ("&id", "*id", "!!python", "<<:")):
        _fail("MANIFEST_SERIALIZATION_INVALID")
    return rendered.encode("utf-8")


def build_outputs() -> dict[Path, bytes]:
    contract, handoff = load_inputs()
    output = _render_json(contract)
    manifest = _render_manifest(contract, handoff, output)
    return {OUTPUT_PATH: output, MANIFEST_PATH: manifest}


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        _fail("OUTPUT_INSTALL_FAILED")
    try:
        os.fsync(descriptor)
    except OSError:
        _fail("OUTPUT_INSTALL_FAILED")
    finally:
        os.close(descriptor)


def _stage_file(target: Path, data: bytes, *, mode: int = GENERATED_MODE) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".st1903-stage-", dir=target.parent)
    stage = Path(name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return stage
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        stage.unlink(missing_ok=True)
        raise


def _replace_file(source: Path, target: Path) -> None:
    os.replace(source, target)


def _restore_file(
    target: Path, previous: bytes | None, previous_mode: int | None
) -> None:
    if previous is None:
        target.unlink(missing_ok=True)
        _fsync_directory(target.parent)
        return
    if previous_mode is None:
        _fail("OUTPUT_ROLLBACK_FAILED")
    stage = _stage_file(target, previous, mode=previous_mode)
    try:
        _replace_file(stage, target)
        _fsync_directory(target.parent)
    finally:
        stage.unlink(missing_ok=True)


def _atomic_install(outputs: Mapping[Path, bytes]) -> None:
    targets = [
        _repo_path(path, required_ancestors=False) if not path.is_absolute() else path
        for path in outputs
    ]
    previous: dict[Path, tuple[bytes | None, int | None]] = {}
    staged: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for relative, target in zip(outputs, targets, strict=True):
            if target.exists() or target.is_symlink():
                metadata = target.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    _fail("OUTPUT_TARGET_INVALID")
                if metadata.st_size > MAX_SOURCE_BYTES:
                    _fail("OUTPUT_TARGET_INVALID")
                previous[target] = (
                    target.read_bytes(),
                    stat.S_IMODE(metadata.st_mode),
                )
            else:
                previous[target] = (None, None)
            staged[target] = _stage_file(target, outputs[relative])
        for target in targets:
            installed.append(target)
            _replace_file(staged[target], target)
            _fsync_directory(target.parent)
    except BaseException as error:
        rollback_failed = False
        for target in reversed(installed):
            try:
                previous_bytes, previous_mode = previous[target]
                _restore_file(target, previous_bytes, previous_mode)
            except BaseException:
                rollback_failed = True
        for stage in staged.values():
            stage.unlink(missing_ok=True)
        if rollback_failed:
            _fail("OUTPUT_ROLLBACK_FAILED")
        if isinstance(error, BuildRefusal):
            raise
        _fail("OUTPUT_INSTALL_FAILED")
    finally:
        for stage in staged.values():
            stage.unlink(missing_ok=True)


def check_outputs(outputs: Mapping[Path, bytes]) -> None:
    for path, expected in outputs.items():
        actual = _read_regular(path, required=False)
        if actual is None or actual != expected:
            _fail("GENERATED_DRIFT")
        try:
            mode = stat.S_IMODE(_repo_path(path).lstat().st_mode)
        except OSError:
            _fail("GENERATED_DRIFT")
        if mode != GENERATED_MODE:
            _fail("GENERATED_MODE_DRIFT")


def _parse_args(arguments: Sequence[str]) -> argparse.Namespace:
    exact_arguments = list(arguments)
    if exact_arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(
        description="Build the disabled ST-1903 autonomous-publication policy pack.",
        allow_abbrev=False,
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(exact_arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = _parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        outputs = build_outputs()
        if options.check:
            check_outputs(outputs)
            print("ST-1903 autonomous-publication policy candidate check passed")
        else:
            _atomic_install(outputs)
            print("ST-1903 autonomous-publication policy candidate generated")
        return 0
    except BuildRefusal as error:
        print(
            f"ST-1903 autonomous-publication policy candidate failed: {error.code}",
            file=sys.stderr,
        )
        return 2
    except BaseException:
        print(
            "ST-1903 autonomous-publication policy candidate failed: INTERNAL_ERROR",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
