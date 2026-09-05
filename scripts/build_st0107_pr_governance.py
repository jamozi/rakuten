#!/usr/bin/env python3
"""Build and validate the local ST-0107 pull-request governance artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0107/contracts/pr-governance.v1.yaml")
ARCHITECTURE_SNAPSHOT_PATH: Final = Path(
    "docs/architecture/ST-0107-github-governance-snapshot.yaml"
)
CODEOWNERS_PATH: Final = Path(".github/CODEOWNERS")
PULL_REQUEST_TEMPLATE_PATH: Final = Path(".github/PULL_REQUEST_TEMPLATE.md")
RULESET_POLICY_PATH: Final = Path("changes/st-0107/ruleset-policy.v1.json")
MANIFEST_PATH: Final = Path("changes/st-0107/manifest.yaml")
GENERATED_PATHS: Final = (
    CODEOWNERS_PATH,
    PULL_REQUEST_TEMPLATE_PATH,
    RULESET_POLICY_PATH,
    MANIFEST_PATH,
)
SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st0107_pr_governance.py"
PINNED_SOURCES: Final = {
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/canonical/08_codex/RAOS_14_codex_implementation_handbook_v1.0.md": (
        "501858e7cdb47db5d2987f6e3d778da4fb8d72224b4380790dcd91ffcac615b2"
    ),
    "docs/canonical/08_codex/github/CODEOWNERS.example": (
        "0bfe2c292879ad4bdcb9691f732cfa80972bd3c13ac2fb70e0ff29a12471c2d6"
    ),
    "docs/canonical/08_codex/github/PULL_REQUEST_TEMPLATE.md": (
        "5650dfa26f882e73c7840f12fcf73353f01ac3a741f13135cf73c3f8b95a7c07"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
}

TRACKED_SOURCES: Final = {
    ".github/workflows/ci.yml": ("final-integration-ci", 2),
    ".github/workflows/auto-merge.yml": ("final-integration-auto-merge", 1),
}

EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-PR-GOVERNANCE-002",
    "version": "2.0.0",
    "story_id": "ST-0107",
    "status": "LOCAL_DESIRED_STATE",
    "formal_verification": "NOT_EXECUTED",
}
EXPECTED_OWNER_ROLES: Final = (
    "accessibility",
    "ai",
    "architecture",
    "data",
    "editorial",
    "engineering",
    "finance",
    "operations",
    "security",
)
EXPECTED_CODEOWNER_ENTRIES: Final = (
    ("*", ("engineering",)),
    ("/contracts/", ("architecture", "engineering")),
    ("/migrations/", ("data", "security")),
    ("/infra/", ("operations", "security")),
    ("/docker-compose.yml", ("operations", "security")),
    ("/scripts/build_local_compose.py", ("operations", "security")),
    ("/scripts/postgres_service.sh", ("operations", "security")),
    ("/scripts/object_storage_service.sh", ("operations", "security")),
    ("/scripts/object_storage_fixture.py", ("operations", "security")),
    ("/apps/admin/", ("editorial", "security")),
    ("/apps/public/", ("editorial", "accessibility")),
    ("/apps/web/", ("editorial", "security", "accessibility")),
    ("/packages/ai/", ("ai", "security", "editorial")),
    ("/packages/finance/", ("finance", "security")),
    ("/python/raos/domain/ai/", ("ai", "security", "editorial")),
    ("/python/raos/domain/finance/", ("finance", "security")),
    ("/python/raos/generated/", ("architecture", "engineering")),
    (
        "/packages/web-contracts/src/generated/",
        ("architecture", "engineering"),
    ),
    ("/docs/canonical/", ("architecture",)),
    ("/changes/*/contracts/", ("architecture", "engineering")),
    ("/changes/*/database/", ("data", "security")),
    ("/docs/canonical/04_security/", ("security", "architecture")),
    ("/tests/security/", ("security", "engineering")),
    ("/scripts/scan_secrets.py", ("security", "engineering")),
    ("/scripts/run_network_denied.sh", ("security", "engineering")),
    ("/scripts/assert_network_denied.py", ("security", "engineering")),
    ("/.github/", ("security", "operations")),
)
EXPECTED_CHECK_CONTEXTS: Final = (
    "Final Integration",
)
EXPECTED_OWNER_CATEGORIES: Final = {}
EXPECTED_ACTIVATION_PREREQUISITES: Final = (
    "real repository and default branch identified",
    "Final Integration has run and is bound to GitHub Actions",
    "deletion and force-push protections are confirmed by authenticated read-back",
)
CANONICAL_STORY: Final = {
    "id": "ST-0107",
    "epic_id": "EPIC-01",
    "title": "Install PR governance",
    "objective": "CODEOWNERS、PR template、ruleset definition",
    "depends_on": ["ST-0106"],
    "requirement_ids": [],
    "design_refs": ["RAOS-CODEX-001", "RAOS-SEC-001"],
    "deliverables": ["CODEOWNERS", "templates", "ruleset docs"],
    "acceptance_criteria": ["contract/migration/security owner required"],
    "test_suites": ["TST-001"],
    "priority": "P0",
    "mvp": True,
    "size": "S",
    "open_decisions": [],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}

MAX_YAML_BYTES: Final = 2 * 1024 * 1024
TEAM_HANDLE_PATTERN: Final = re.compile(
    r"^@([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)/([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)$"
)
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


class NoAliasDumper(yaml.SafeDumper):
    """Deterministic YAML dumper without anchors or aliases."""

    def ignore_aliases(self, data: object) -> bool:
        return True


# PyYAML otherwise applies YAML 1.1 boolean rules and turns the GitHub Actions
# key ``on`` into ``True``. Keep strict scalar typing while accepting only the
# YAML 1.2 boolean spellings used by the reviewed inputs.
UniqueKeyLoader.yaml_implicit_resolvers = {
    first_character: [
        (tag, expression)
        for tag, expression in resolvers
        if tag != "tag:yaml.org,2002:bool"
    ]
    for first_character, resolvers in UniqueKeyLoader.yaml_implicit_resolvers.items()
}
UniqueKeyLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"{label} must be a string-keyed mapping")
    return value


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a list")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise RuntimeError(f"{label} keys differ: missing={missing} extra={extra}")


def _regular_file(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} is missing: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} must be a regular non-symlink file: {path}")


def _repository_regular_file(root: Path, relative: Path, label: str) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(f"unsafe repository path for {label}: {relative}")
    try:
        root_metadata = root.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"repository root is missing: {root}") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError(f"repository root must be a real directory: {root}")

    current = root.resolve(strict=True)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError as exc:
            raise RuntimeError(f"{label} ancestor is missing: {current}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(f"{label} ancestor must be a real directory: {current}")
    target = current / relative.name
    _regular_file(target, label)
    return target


def load_yaml(path: Path) -> Any:
    _regular_file(path, "YAML input")
    content = path.read_bytes()
    if len(content) > MAX_YAML_BYTES:
        raise RuntimeError(f"YAML input exceeds size limit: {path}")
    text = content.decode("utf-8")
    for token in yaml.scan(text):
        if isinstance(token, (AliasToken, AnchorToken)):
            raise RuntimeError(f"YAML anchors and aliases are forbidden: {path}")
    return yaml.load(text, Loader=UniqueKeyLoader)


def _repo_relative_uri(uri: object) -> Path:
    if not isinstance(uri, str) or not uri.startswith("repo://"):
        raise RuntimeError("source uri must use repo://")
    relative = uri.removeprefix("repo://")
    raw_parts = relative.split("/")
    if (
        not relative
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        raise RuntimeError(f"unsafe repository source uri: {uri}")
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise RuntimeError(f"unsafe repository source uri: {uri}")
    return Path(*pure.parts)


def _validate_sources(contract: Mapping[str, Any], root: Path) -> None:
    rows = _list(contract["sources"], "sources")
    observed: dict[str, str] = {}
    for index, raw_row in enumerate(rows):
        row = _mapping(raw_row, f"sources[{index}]")
        _exact_keys(row, {"uri", "sha256"}, f"sources[{index}]")
        relative = _repo_relative_uri(row["uri"])
        expected = row["sha256"]
        if not isinstance(expected, str) or not SHA256_PATTERN.fullmatch(expected):
            raise RuntimeError(f"sources[{index}].sha256 is invalid")
        key = relative.as_posix()
        if key in observed:
            raise RuntimeError(f"duplicate source uri: {key}")
        observed[key] = expected
    if observed != PINNED_SOURCES:
        raise RuntimeError("source inventory differs from the reviewed pinned set")
    for relative, expected in PINNED_SOURCES.items():
        source_path = _repository_regular_file(root, Path(relative), "pinned source")
        actual = sha256_file(source_path)
        if actual != expected:
            raise RuntimeError(
                f"pinned source hash mismatch: {relative}: {actual} != {expected}"
            )

    tracked_rows = _list(contract["tracked_sources"], "tracked_sources")
    tracked: dict[str, tuple[str, int]] = {}
    for index, raw_row in enumerate(tracked_rows):
        row = _mapping(raw_row, f"tracked_sources[{index}]")
        _exact_keys(
            row,
            {"uri", "semantic_id", "version"},
            f"tracked_sources[{index}]",
        )
        relative = _repo_relative_uri(row["uri"])
        semantic_id, version = row["semantic_id"], row["version"]
        if not isinstance(semantic_id, str) or not semantic_id:
            raise RuntimeError("tracked source semantic_id is invalid")
        if type(version) is not int or version < 1:
            raise RuntimeError("tracked source version is invalid")
        key = relative.as_posix()
        if key in tracked:
            raise RuntimeError(f"duplicate tracked source uri: {key}")
        tracked[key] = (semantic_id, version)
        _repository_regular_file(root, relative, "tracked source")
    if tracked != TRACKED_SOURCES:
        raise RuntimeError("tracked source inventory differs from policy")


def _validate_architecture_snapshot(root: Path) -> None:
    path = _repository_regular_file(
        root, ARCHITECTURE_SNAPSHOT_PATH, "architecture snapshot"
    )
    snapshot = _mapping(load_yaml(path), "architecture snapshot")
    _exact_keys(
        snapshot,
        {
            "document",
            "official_sources",
            "local_candidate",
            "unverified_live_bindings",
            "desired_ruleset_semantics",
            "activation_preflight",
            "verification_boundary",
        },
        "architecture snapshot",
    )
    document = _mapping(snapshot["document"], "architecture snapshot document")
    _exact_keys(
        document,
        {
            "id",
            "schema_version",
            "story_id",
            "checked_at",
            "rest_api_version",
            "rest_api_version_header",
            "purpose",
        },
        "architecture snapshot document",
    )
    if {
        "id": document["id"],
        "schema_version": document["schema_version"],
        "story_id": document["story_id"],
        "rest_api_version": document["rest_api_version"],
        "rest_api_version_header": document["rest_api_version_header"],
    } != {
        "id": "RAOS-ST0107-GITHUB-GOVERNANCE-SNAPSHOT-001",
        "schema_version": 1,
        "story_id": "ST-0107",
        "rest_api_version": "2026-03-10",
        "rest_api_version_header": "X-GitHub-Api-Version",
    }:
        raise RuntimeError("architecture snapshot identity or API version drifted")

    official_sources = _list(
        snapshot["official_sources"], "architecture snapshot official_sources"
    )
    expected_source_ids = (
        "GITHUB-ABOUT-CODE-OWNERS",
        "GITHUB-AVAILABLE-RULESET-RULES",
        "GITHUB-REST-RULES",
        "GITHUB-TROUBLESHOOT-REQUIRED-STATUS",
    )
    if (
        tuple(
            _mapping(row, "architecture snapshot official source").get("id")
            for row in official_sources
        )
        != expected_source_ids
    ):
        raise RuntimeError("architecture snapshot official source inventory drifted")

    local_candidate = _mapping(
        snapshot["local_candidate"], "architecture snapshot local_candidate"
    )
    if local_candidate.get("source_contract") != SOURCE_CONTRACT_URI:
        raise RuntimeError("architecture snapshot source contract drifted")
    if local_candidate.get("generator") != GENERATOR_URI.removeprefix("repo://"):
        raise RuntimeError("architecture snapshot generator drifted")
    if local_candidate.get("workflow") != "make generate / make check":
        raise RuntimeError("architecture snapshot workflow drifted")
    if local_candidate.get("remote_mutation_capability") != "FORBIDDEN":
        raise RuntimeError("architecture snapshot remote boundary drifted")

    boundary = _mapping(
        snapshot["verification_boundary"],
        "architecture snapshot verification_boundary",
    )
    expected_boundary = {
        "remote_ruleset_apply": "NOT_EXECUTED",
        "authenticated_ruleset_snapshot": "NOT_EXECUTED",
        "live_pull_request_probes": "NOT_EXECUTED",
        "formal_tst_001": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
        "st0005_apply_gate": "NOT_ACTIVATED",
    }
    if any(boundary.get(key) != value for key, value in expected_boundary.items()):
        raise RuntimeError("architecture snapshot verification boundary drifted")


def _validate_canonical_story(root: Path) -> None:
    backlog_path = _repository_regular_file(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "canonical backlog",
    )
    backlog = _mapping(
        load_yaml(backlog_path),
        "canonical backlog",
    )
    stories = _list(backlog.get("stories"), "canonical backlog stories")
    matches = [
        row
        for row in stories
        if isinstance(row, Mapping) and row.get("id") == "ST-0107"
    ]
    if matches != [CANONICAL_STORY]:
        raise RuntimeError(
            "canonical ST-0107 record differs from the reviewed contract"
        )


def _canonical_codeowner_entries(root: Path) -> dict[str, tuple[str, ...]]:
    path = _repository_regular_file(
        root,
        Path("docs/canonical/08_codex/github/CODEOWNERS.example"),
        "canonical CODEOWNERS example",
    )
    entries: dict[str, tuple[str, ...]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2:
            raise RuntimeError("canonical CODEOWNERS example contains an invalid row")
        entries[fields[0]] = tuple(fields[1:])
    return entries


def _validate_owner_bindings(
    contract: Mapping[str, Any], root: Path
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    bindings = _mapping(contract["owner_bindings"], "owner_bindings")
    _exact_keys(bindings, {"organization", "status", "teams"}, "owner_bindings")
    if bindings["organization"] != "raos":
        raise RuntimeError("owner organization must remain the canonical placeholder")
    if bindings["status"] != "UNVERIFIED_PLACEHOLDERS":
        raise RuntimeError("owner bindings cannot be presented as live-verified")
    teams = _mapping(bindings["teams"], "owner_bindings.teams")
    if tuple(sorted(teams)) != EXPECTED_OWNER_ROLES:
        raise RuntimeError("owner role inventory differs from the reviewed set")
    handles: dict[str, str] = {}
    for role, raw_handle in teams.items():
        if not isinstance(raw_handle, str) or not TEAM_HANDLE_PATTERN.fullmatch(
            raw_handle
        ):
            raise RuntimeError(f"invalid GitHub team placeholder for role {role}")
        organization, team = raw_handle[1:].split("/", 1)
        if organization != "raos" or team != role:
            raise RuntimeError(f"owner placeholder does not match role {role}")
        handles[role] = raw_handle
    if len(set(handles.values())) != len(handles):
        raise RuntimeError("owner placeholders must be unique")

    codeowners = _mapping(contract["codeowners"], "codeowners")
    _exact_keys(codeowners, {"entries"}, "codeowners")
    raw_entries = _list(codeowners["entries"], "codeowners.entries")
    entries: list[dict[str, Any]] = []
    by_pattern: dict[str, tuple[str, ...]] = {}
    for index, raw_entry in enumerate(raw_entries):
        entry = _mapping(raw_entry, f"codeowners.entries[{index}]")
        _exact_keys(entry, {"pattern", "roles"}, f"codeowners.entries[{index}]")
        pattern = entry["pattern"]
        roles = _list(entry["roles"], f"codeowners.entries[{index}].roles")
        if not isinstance(pattern, str) or not pattern:
            raise RuntimeError("CODEOWNERS pattern must be a nonempty string")
        if pattern != "*" and not pattern.startswith("/"):
            raise RuntimeError(f"CODEOWNERS pattern must be root anchored: {pattern}")
        if any(token in pattern for token in ("!", "[", "]", "\\", "#")):
            raise RuntimeError(f"unsupported CODEOWNERS pattern syntax: {pattern}")
        if (
            any(character.isspace() for character in pattern)
            or ".." in PurePosixPath(pattern).parts
        ):
            raise RuntimeError(f"unsafe CODEOWNERS pattern: {pattern}")
        if pattern in by_pattern:
            raise RuntimeError(f"duplicate CODEOWNERS pattern: {pattern}")
        if not roles or not all(
            isinstance(role, str) and role in handles for role in roles
        ):
            raise RuntimeError(f"CODEOWNERS roles are invalid for {pattern}")
        if len(set(roles)) != len(roles):
            raise RuntimeError(f"CODEOWNERS roles are duplicated for {pattern}")
        normalized_roles = tuple(roles)
        by_pattern[pattern] = normalized_roles
        entries.append({"pattern": pattern, "roles": list(normalized_roles)})
    if not entries or entries[0]["pattern"] != "*":
        raise RuntimeError("CODEOWNERS must start with the default owner row")
    if entries[-1]["pattern"] != "/.github/":
        raise RuntimeError("/.github/ must be the last and therefore controlling row")
    observed_entries = tuple(
        (str(entry["pattern"]), tuple(_list(entry["roles"], "codeowner roles")))
        for entry in entries
    )
    if observed_entries != EXPECTED_CODEOWNER_ENTRIES:
        raise RuntimeError("CODEOWNERS inventory differs from the reviewed policy")

    inverse = {handle: role for role, handle in handles.items()}
    for pattern, canonical_handles in _canonical_codeowner_entries(root).items():
        try:
            expected_roles = tuple(inverse[handle] for handle in canonical_handles)
        except KeyError as exc:
            raise RuntimeError("canonical CODEOWNERS owner is not bound") from exc
        if by_pattern.get(pattern) != expected_roles:
            raise RuntimeError(f"canonical CODEOWNERS row is not preserved: {pattern}")

    return handles, entries


def _workflow_check_names(root: Path) -> tuple[str, ...]:
    relative = Path(".github/workflows/ci.yml")
    workflow_path = _repository_regular_file(root, relative, "workflow")
    workflow = _mapping(load_yaml(workflow_path), f"workflow {relative}")
    jobs = _mapping(workflow.get("jobs"), f"workflow jobs {relative}")
    final = _mapping(jobs.get("final"), "workflow final job")
    name = final.get("name")
    if name != "Final Integration":
        raise RuntimeError("workflow final job name drifted")
    return (name,)


def _validate_ruleset(
    contract: Mapping[str, Any], entries: Sequence[Mapping[str, Any]], root: Path
) -> Mapping[str, Any]:
    policy = _mapping(contract["ruleset_policy"], "ruleset_policy")
    _exact_keys(
        policy,
        {
            "name",
            "target",
            "include",
            "exclude",
            "desired_enforcement",
            "local_application_status",
            "bypass_actors",
            "prohibit_deletion",
            "prohibit_force_push",
            "require_linear_history",
            "pull_request",
            "required_status_checks",
            "strict_required_status_checks_policy",
            "do_not_enforce_on_create",
            "required_owner_categories",
        },
        "ruleset_policy",
    )
    fixed_values = {
        "name": "RAOS protected default branch",
        "target": "branch",
        "include": ["~DEFAULT_BRANCH"],
        "exclude": [],
        "desired_enforcement": "active",
        "local_application_status": "NOT_EXECUTED",
        "bypass_actors": [],
        "prohibit_deletion": True,
        "prohibit_force_push": True,
        "require_linear_history": True,
        "strict_required_status_checks_policy": True,
        "do_not_enforce_on_create": False,
    }
    for key, expected in fixed_values.items():
        if policy[key] != expected:
            raise RuntimeError(f"ruleset policy field {key} is not fail-closed")

    pull_request = _mapping(policy["pull_request"], "ruleset_policy.pull_request")
    expected_pull_request = {
        "allowed_merge_methods": ["squash"],
        "dismiss_stale_reviews_on_push": False,
        "require_code_owner_review": False,
        "require_last_push_approval": False,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": False,
        "auto_merge_after_required_checks": True,
    }
    if dict(pull_request) != expected_pull_request:
        raise RuntimeError("pull-request protection differs from the reviewed policy")

    raw_checks = _list(
        policy["required_status_checks"], "ruleset_policy.required_status_checks"
    )
    checks: list[dict[str, str]] = []
    for index, raw_check in enumerate(raw_checks):
        check = _mapping(raw_check, f"required_status_checks[{index}]")
        _exact_keys(
            check,
            {"context", "expected_source", "integration_id_binding"},
            f"required_status_checks[{index}]",
        )
        if check["expected_source"] != "github-actions":
            raise RuntimeError("required checks must be bound to GitHub Actions")
        if check["integration_id_binding"] != "REQUIRED_AT_ACTIVATION":
            raise RuntimeError("required check source must remain unbound locally")
        context = check["context"]
        if not isinstance(context, str):
            raise RuntimeError("required check context must be a string")
        checks.append(dict(check))
    contexts = tuple(check["context"] for check in checks)
    if contexts != EXPECTED_CHECK_CONTEXTS:
        raise RuntimeError("required status-check inventory differs from policy")
    if _workflow_check_names(root) != EXPECTED_CHECK_CONTEXTS:
        raise RuntimeError("required status checks drifted from workflow job names")

    categories = _mapping(
        policy["required_owner_categories"],
        "ruleset_policy.required_owner_categories",
    )
    if dict(categories) != EXPECTED_OWNER_CATEGORIES:
        raise RuntimeError("required owner categories differ from the reviewed policy")
    entry_roles = {
        str(entry["pattern"]): set(_list(entry["roles"], "entry roles"))
        for entry in entries
    }
    for category_name, raw_category in categories.items():
        category = _mapping(raw_category, f"owner category {category_name}")
        _exact_keys(category, {"patterns", "roles"}, f"owner category {category_name}")
        patterns = _list(
            category["patterns"], f"owner category {category_name}.patterns"
        )
        roles = set(_list(category["roles"], f"owner category {category_name}.roles"))
        if not patterns or not roles:
            raise RuntimeError(f"owner category {category_name} cannot be empty")
        for pattern in patterns:
            if not isinstance(pattern, str) or not roles.issubset(
                entry_roles.get(pattern, set())
            ):
                raise RuntimeError(
                    f"owner category {category_name} is not enforced for {pattern}"
                )
    return policy


def _validate_template(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    template = _mapping(contract["pull_request_template"], "pull_request_template")
    expected = {
        "story_ids_are_tracking_only": True,
        "repeated_owner_routing": False,
        "require_generated_or_ai_assisted_review": False,
        "record_once": [
            "story_ids",
            "summary",
            "verification",
            "external_not_run",
        ],
    }
    if dict(template) != expected:
        raise RuntimeError("pull-request template extension differs from policy")
    return template


def _validate_activation(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    activation = _mapping(contract["activation"], "activation")
    _exact_keys(
        activation,
        {
            "generator_remote_mutation",
            "live_status",
            "formal_tst_001",
            "prerequisites",
        },
        "activation",
    )
    if activation["generator_remote_mutation"] != "FORBIDDEN":
        raise RuntimeError("the local generator must never mutate GitHub")
    if activation["live_status"] != "NOT_EXECUTED":
        raise RuntimeError("live ruleset application is not locally proven")
    if activation["formal_tst_001"] != "NOT_EXECUTED":
        raise RuntimeError("formal TST-001 cannot be promoted by local generation")
    if (
        tuple(_list(activation["prerequisites"], "activation.prerequisites"))
        != EXPECTED_ACTIVATION_PREREQUISITES
    ):
        raise RuntimeError("activation prerequisite inventory differs from policy")
    return activation


def load_and_validate_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "governance contract")
    contract = _mapping(load_yaml(contract_path), "governance contract")
    _exact_keys(
        contract,
        {
            "document",
            "sources",
            "tracked_sources",
            "owner_bindings",
            "codeowners",
            "pull_request_template",
            "ruleset_policy",
            "activation",
        },
        "governance contract",
    )
    document = _mapping(contract["document"], "document")
    if dict(document) != EXPECTED_DOCUMENT:
        raise RuntimeError("governance document identity/status differs from policy")
    _validate_sources(contract, root)
    _validate_canonical_story(root)
    _, entries = _validate_owner_bindings(contract, root)
    _validate_template(contract)
    _validate_ruleset(contract, entries, root)
    _validate_activation(contract)
    return dict(contract)


def render_codeowners(contract: Mapping[str, Any]) -> bytes:
    bindings = _mapping(contract["owner_bindings"], "owner_bindings")
    teams = _mapping(bindings["teams"], "owner_bindings.teams")
    codeowners = _mapping(contract["codeowners"], "codeowners")
    entries = _list(codeowners["entries"], "codeowners.entries")
    lines = [
        "# Generated by scripts/build_st0107_pr_governance.py. Do not edit.",
        f"# Source contract: {SOURCE_CONTRACT_URI}",
        "# Owner binding status: UNVERIFIED_PLACEHOLDERS (@raos/* canonical placeholders).",
        "# Do not enforce until every team is visible and has repository write access.",
    ]
    for raw_entry in entries:
        entry = _mapping(raw_entry, "codeowners entry")
        roles = _list(entry["roles"], "codeowners entry roles")
        owners = " ".join(str(teams[role]) for role in roles)
        lines.append(f"{entry['pattern']} {owners}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_pull_request_template(contract: Mapping[str, Any], root: Path) -> bytes:
    _validate_template(contract)
    del root
    return (
        "<!-- Generated from PR governance v2. -->\n"
        "## Tracking\n\n"
        "- Story / requirement IDs:\n"
        "- Integration branch:\n\n"
        "## Summary\n\n"
        "## Verification\n\n"
        "- `make fast`:\n"
        "- Optional full diagnostics (only if run):\n"
        "- Final Integration CI (affected or full):\n\n"
        "## External operations not run\n\n"
        "List live, external, owner-private, staging, deployment, release, or "
        "Production checks intentionally not executed.\n\n"
        "## Rollback\n"
    ).encode("utf-8")


def render_ruleset_policy(contract: Mapping[str, Any]) -> bytes:
    policy = _mapping(contract["ruleset_policy"], "ruleset_policy")
    activation = _mapping(contract["activation"], "activation")
    output = {
        "document": {
            "id": "RAOS-GITHUB-RULESET-POLICY-002",
            "version": "2.0.0",
            "story_id": "ST-0107",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "artifact_kind": "DESIRED_STATE_NOT_API_PAYLOAD",
            "github_api_version": "2026-03-10",
            "live_status": activation["live_status"],
            "formal_tst_001": activation["formal_tst_001"],
        },
        "ruleset": dict(policy),
        "activation": dict(activation),
    }
    return (
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def render_manifest(
    root: Path, generated_without_manifest: Mapping[Path, bytes]
) -> bytes:
    del root
    generated_artifacts = []
    for relative in (CODEOWNERS_PATH, PULL_REQUEST_TEMPLATE_PATH, RULESET_POLICY_PATH):
        content = generated_without_manifest[relative]
        generated_artifacts.append(
            {
                "uri": f"repo://{relative.as_posix()}",
                "bytes": len(content),
                "sha256": sha256_bytes(content),
            }
        )
    manifest = {
        "document": {
            "id": "RAOS-BUILD-MANIFEST-002",
            "version": "2.0.0",
            "owner_id": "build_st0107_pr_governance",
            "owner_version": 2,
            "story_ids": ["ST-0107"],
        },
        "semantic_inputs": {
            "immutable": [
                {"uri": f"repo://{relative}", "sha256": digest}
                for relative, digest in PINNED_SOURCES.items()
            ],
            "tracked": [
                {
                    "uri": f"repo://{relative}",
                    "semantic_id": semantic_id,
                    "version": version,
                }
                for relative, (semantic_id, version) in TRACKED_SOURCES.items()
            ],
        },
        "outputs": generated_artifacts,
    }
    return yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_and_validate_contract(root)
    outputs: dict[Path, bytes] = {
        CODEOWNERS_PATH: render_codeowners(contract),
        PULL_REQUEST_TEMPLATE_PATH: render_pull_request_template(contract, root),
        RULESET_POLICY_PATH: render_ruleset_policy(contract),
    }
    outputs[MANIFEST_PATH] = render_manifest(root, outputs)
    return outputs


def _safe_parent(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError(f"unsafe generated path: {relative}")
    physical_root = root.resolve(strict=True)
    current = physical_root
    for part in relative.parent.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError(
                    f"generated parent is not a real directory: {current}"
                )
        else:
            current.mkdir(mode=0o755)
            descriptor = os.open(current.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    return current


def _stage_file(parent: Path, name: str, content: bytes) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.st0107-", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def install_outputs(outputs: Mapping[Path, bytes], root: Path = REPO_ROOT) -> None:
    staged: dict[Path, Path] = {}
    previous: dict[Path, bytes | None] = {}
    installed: list[Path] = []
    try:
        for relative, content in outputs.items():
            parent = _safe_parent(root, relative)
            target = parent / relative.name
            if target.is_symlink():
                raise RuntimeError(f"generated target cannot be a symlink: {target}")
            if target.exists() and not target.is_file():
                raise RuntimeError(f"generated target must be a regular file: {target}")
            previous[relative] = target.read_bytes() if target.exists() else None
            staged[relative] = _stage_file(parent, relative.name, content)
        for relative in GENERATED_PATHS:
            target = root.resolve(strict=True) / relative
            temporary = staged[relative]
            os.replace(temporary, target)
            staged.pop(relative)
            _fsync_directory(target.parent)
            installed.append(relative)
    except BaseException as install_error:
        rollback_errors: list[str] = []
        for relative in reversed(installed):
            target = root.resolve(strict=True) / relative
            old_content = previous[relative]
            try:
                if old_content is None:
                    target.unlink(missing_ok=True)
                    _fsync_directory(target.parent)
                else:
                    replacement = _stage_file(target.parent, target.name, old_content)
                    os.replace(replacement, target)
                    _fsync_directory(target.parent)
            except BaseException as rollback_error:
                rollback_errors.append(f"{relative}: {rollback_error}")
        if rollback_errors:
            raise RuntimeError(
                "generated install failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from install_error
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def check_generated(root: Path = REPO_ROOT) -> None:
    expected = render_outputs(root)
    for relative in GENERATED_PATHS:
        target = _repository_regular_file(root, relative, "generated artifact")
        metadata = target.stat()
        if metadata.st_mode & 0o022:
            raise RuntimeError(
                f"generated artifact is group/world writable: {relative}"
            )
        actual = target.read_bytes()
        if actual != expected[relative]:
            raise RuntimeError(f"generated artifact drift: {relative}")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or check the local ST-0107 governance artifacts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed artifacts byte-for-byte without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        if arguments.check:
            check_generated()
            mode = "check"
        else:
            install_outputs(render_outputs())
            mode = "install"
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "generated_artifacts": len(GENERATED_PATHS),
                "live_ruleset": "NOT_EXECUTED",
                "mode": mode,
                "owner_bindings": "UNVERIFIED_PLACEHOLDERS",
                "status": "PASS",
                "story_id": "ST-0107",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
