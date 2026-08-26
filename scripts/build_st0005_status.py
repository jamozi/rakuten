#!/usr/bin/env python3
"""Build and validate the ST-0005 operational status overlay."""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken

SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if __package__:
    from scripts import import_raos_design
else:
    SCRIPT_MODULE_ROOT = Path(__file__).resolve().parent
    if str(SCRIPT_MODULE_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPT_MODULE_ROOT))
    import import_raos_design  # type: ignore[no-redef]  # noqa: E402


REPO_ROOT: Final = SCRIPT_REPO_ROOT
DOCS_ROOT: Final = REPO_ROOT / "docs"
DEFAULT_BUNDLE_ROOT: Final = REPO_ROOT / "changes" / "st-0005"
REQUESTS_ROOT: Final = DEFAULT_BUNDLE_ROOT / "requests"
EVIDENCE_ROOT: Final = DEFAULT_BUNDLE_ROOT / "evidence"
SUITE_EVIDENCE_URI_PREFIX: Final = "changes/st-0005/evidence/"
EVIDENCE_ARTIFACTS_ROOT: Final = EVIDENCE_ROOT / "artifacts"
EVIDENCE_ARTIFACT_URI_PREFIX: Final = "changes/st-0005/evidence/artifacts/"
CONTRACTS_NAME: Final = "contracts"
OVERLAY_NAME: Final = "status-overlay.v1.yaml"
MANIFEST_NAME: Final = "manifest.yaml"
GENERATED_NAMES: Final = (CONTRACTS_NAME, OVERLAY_NAME, MANIFEST_NAME)

IMPORT_MANIFEST = DOCS_ROOT / "manifest.json"
CANONICAL_REGISTRY = (
    DOCS_ROOT
    / "canonical"
    / "00_master"
    / "RAOS_implementation_status_registry_v1.0.yaml"
)
STORY_CATALOG = (
    DOCS_ROOT / "canonical" / "07_backlog" / "RAOS_13_story_backlog_v1.0.yaml"
)
SUITE_CATALOG = (
    DOCS_ROOT / "canonical" / "05_test" / "RAOS_11_test_suite_catalog_v1.0.yaml"
)
STATUS_TAXONOMY = (
    DOCS_ROOT / "canonical" / "01_integration" / "RAOS_07_status_taxonomy_v1.0.yaml"
)

REVISION_ID: Final = "RAOS-STATUS-REGISTRY-OVERLAY-001"
REVISION_VERSION: Final = "1.0.0"
GENERATOR_PATH: Final = "scripts/build_st0005_status.py"
REQUEST_SCHEMA_PATH: Final = "contracts/status-transition-request.schema.json"

PINNED_INPUT_HASHES: Final = {
    "docs/manifest.json": (
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e"
    ),
    "docs/canonical/00_master/RAOS_implementation_status_registry_v1.0.yaml": (
        "1411f55ce60f6316e83567110fb2847e0db49239cb63dcabf9e81612c3b72ab8"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/01_integration/RAOS_07_status_taxonomy_v1.0.yaml": (
        "e3261a8a6102c1b93e6cc9006c52f01389ec31510e24ca37bc400437aebbf68b"
    ),
}

IMPLEMENTATION_CHAIN: Final = (
    "NOT_STARTED",
    "IN_PROGRESS",
    "IMPLEMENTED_NOT_VALIDATED",
    "VALIDATED",
    "DEPLOYED_STAGING",
    "DEPLOYED_PRODUCTION",
)
NON_CHAIN_IMPLEMENTATION_STATUSES: Final = (
    "DEFERRED_POST_MVP",
    "OUT_OF_SCOPE",
)
VERIFICATION_STATUSES: Final = (
    "NOT_EXECUTED",
    "PARTIAL",
    "PASS",
    "FAIL",
    "NOT_APPLICABLE",
)
ACTOR_TYPES: Final = ("HUMAN", "AUTOMATION", "SERVICE")
EVIDENCE_CLASSES: Final = (
    "CHANGE_PLAN",
    "LOCAL_IMPLEMENTATION",
    "PR_CHANGESET",
    "RUNTIME_SUITE_RESULT",
    "STAGING_DEPLOYMENT",
    "PRODUCTION_RELEASE",
    "REGRESSION",
    "EXPIRY",
    "ROLLBACK_DECISION",
    "SCOPE_DECISION",
)

FORWARD_TRANSITIONS: Final = frozenset(
    zip(IMPLEMENTATION_CHAIN, IMPLEMENTATION_CHAIN[1:])
)
DEMOTION_TRANSITIONS: Final = frozenset(
    (target, source)
    for source, target in zip(IMPLEMENTATION_CHAIN, IMPLEMENTATION_CHAIN[1:])
)
HIGH_AUTHORITY_TARGETS: Final = frozenset({"VALIDATED", "DEPLOYED_PRODUCTION"})
LIVE_APPLY_ACTIVATION_PREREQUISITES: Final = ("ST-0006", "ST-0107")
DEPLOYMENT_APPLY_ACTIVATION_PREREQUISITES: Final = (
    "ST-1505",
    "ST-1506",
    "ST-1607",
)
SPECIAL_SCOPE_TRANSITIONS: Final = {
    ("DEFERRED_POST_MVP", "IN_PROGRESS"): "POST_MVP_ACTIVATION",
    ("NOT_STARTED", "DEFERRED_POST_MVP"): "DEFERRAL",
    ("IN_PROGRESS", "DEFERRED_POST_MVP"): "DEFERRAL",
    ("NOT_STARTED", "OUT_OF_SCOPE"): "SCOPE_CHANGE",
    ("IN_PROGRESS", "OUT_OF_SCOPE"): "SCOPE_CHANGE",
    ("DEFERRED_POST_MVP", "OUT_OF_SCOPE"): "SCOPE_CHANGE",
    ("OUT_OF_SCOPE", "NOT_STARTED"): "SCOPE_CHANGE",
    ("OUT_OF_SCOPE", "IN_PROGRESS"): "SCOPE_CHANGE",
    ("OUT_OF_SCOPE", "DEFERRED_POST_MVP"): "SCOPE_CHANGE",
}
VERIFICATION_ONLY_TRANSITIONS: Final = {
    ("NOT_EXECUTED", "PARTIAL"): "VERIFICATION_RESULT",
    ("NOT_EXECUTED", "FAIL"): "VERIFICATION_RESULT",
    ("PARTIAL", "NOT_EXECUTED"): "EXPIRY",
    ("PARTIAL", "PASS"): "VERIFICATION_RESULT",
    ("PARTIAL", "FAIL"): "VERIFICATION_RESULT",
    ("PASS", "NOT_EXECUTED"): "EXPIRY",
    ("PASS", "PARTIAL"): "REGRESSION",
    ("PASS", "FAIL"): "REGRESSION",
    ("FAIL", "NOT_EXECUTED"): "EXPIRY",
    ("FAIL", "PARTIAL"): "VERIFICATION_RESULT",
    ("FAIL", "PASS"): "VERIFICATION_RESULT",
}
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
HEAD_SHA_PATTERN: Final = re.compile(r"^[0-9a-f]{40,64}$")
REQUEST_ID_PATTERN: Final = re.compile(r"^STATUS-[A-Z0-9][A-Z0-9_-]{7,95}$")
STORY_ID_PATTERN: Final = re.compile(r"^ST-[0-9]{4}$")
SUITE_ID_PATTERN: Final = re.compile(r"^TST-[0-9]{3}$")
GITHUB_PR_PATTERN: Final = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*$"
)
UTC_TIMESTAMP_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
MAX_YAML_BYTES: Final = 1024 * 1024
MAX_YAML_DEPTH: Final = 64
MAX_YAML_NODES: Final = 100_000


class NoAliasDumper(yaml.SafeDumper):
    """Emit deterministic YAML without aliases."""

    def ignore_aliases(self, data: object) -> bool:
        return True


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
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
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def object_digest(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def relative_repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def checked_relative_path(value: str, *, source: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError(f"unsafe relative path in {source}: {value!r}")
    return path


def path_has_symlink(root: Path, relative: PurePosixPath) -> bool:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def load_yaml(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"required regular YAML file is missing: {path}")
    content = path.read_bytes()
    if len(content) > MAX_YAML_BYTES:
        raise RuntimeError(f"YAML file exceeds {MAX_YAML_BYTES} bytes: {path}")
    text = content.decode("utf-8")
    if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(text)):
        raise RuntimeError(f"YAML anchors and aliases are forbidden: {path}")
    loaded = yaml.load(text, Loader=UniqueKeyLoader)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"expected YAML mapping: {path}")
    node_count = 0

    def visit(value: object, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_YAML_NODES or depth > MAX_YAML_DEPTH:
            raise RuntimeError(f"YAML structure exceeds complexity limits: {path}")
        if isinstance(value, dict):
            for key, item in value.items():
                visit(key, depth + 1)
                visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)

    visit(loaded, 0)
    return loaded


def write_yaml(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.dump(
        dict(document),
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    )
    path.write_text(rendered, encoding="utf-8", newline="\n")


def write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def assert_exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | frozenset[str] = frozenset(),
    source: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unknown = sorted(actual - required - set(optional))
    if missing or unknown:
        raise RuntimeError(
            f"strict field violation in {source}: missing={missing}, unknown={unknown}"
        )


def require_string(
    value: object,
    *,
    source: str,
    minimum: int = 1,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise RuntimeError(f"invalid string in {source}")
    return value


def parse_utc_timestamp(value: object, *, source: str) -> datetime:
    text = require_string(value, source=source, minimum=1, maximum=64)
    if not UTC_TIMESTAMP_PATTERN.fullmatch(text):
        raise RuntimeError(f"{source} must be strict UTC RFC3339 with Z")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise RuntimeError(f"invalid UTC timestamp in {source}") from exc
    return parsed


def current_utc() -> datetime:
    return datetime.now(timezone.utc)


def validate_temporal_evidence(
    value: Mapping[str, Any], *, source: str
) -> tuple[str, str | None, datetime]:
    observed_text = require_string(
        value.get("observed_at"), source=f"{source}.observed_at"
    )
    observed_at = parse_utc_timestamp(observed_text, source=f"{source}.observed_at")
    if "expires_at" not in value:
        return observed_text, None, observed_at
    expires_value = value["expires_at"]
    expires_text = require_string(expires_value, source=f"{source}.expires_at")
    if not UTC_TIMESTAMP_PATTERN.fullmatch(expires_text):
        raise RuntimeError(f"{source}.expires_at must be strict UTC RFC3339 with Z")
    try:
        expires_at = datetime.strptime(expires_text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise RuntimeError(f"invalid UTC timestamp in {source}.expires_at") from exc
    if expires_at <= observed_at:
        raise RuntimeError(f"evidence expiry must be after observation in {source}")
    return observed_text, expires_text, observed_at


def require_evidence_fresh_at(
    value: Mapping[str, Any], *, reference: datetime, source: str
) -> None:
    if "expires_at" not in value:
        return
    expires_value = value["expires_at"]
    expires_at = parse_utc_timestamp(expires_value, source=f"{source}.expires_at")
    if expires_at <= reference:
        raise RuntimeError(f"expired evidence is forbidden at {source} reference time")


def require_mapping(value: object, *, source: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"expected mapping in {source}")
    return value


def require_list(value: object, *, source: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"expected list in {source}")
    return value


def assert_immutable_inputs() -> None:
    for logical, expected in PINNED_INPUT_HASHES.items():
        relative = checked_relative_path(logical, source="pinned input")
        path = REPO_ROOT.joinpath(*relative.parts)
        if (
            path.is_symlink()
            or path_has_symlink(REPO_ROOT, relative)
            or not path.is_file()
        ):
            raise RuntimeError(f"pinned immutable input is missing: {logical}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"immutable input hash mismatch for {logical}: "
                f"expected {expected}, got {actual}"
            )

    capture = io.StringIO()
    try:
        with contextlib.redirect_stdout(capture):
            import_raos_design.verify_import(DOCS_ROOT)
    except import_raos_design.DesignPackageError as exc:
        raise RuntimeError(
            f"ST-0001 immutable import verification failed: {exc}"
        ) from exc


def canonical_inputs() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    registry = load_yaml(CANONICAL_REGISTRY)
    stories = load_yaml(STORY_CATALOG)
    suites = load_yaml(SUITE_CATALOG)
    taxonomy = load_yaml(STATUS_TAXONOMY)
    return registry, stories, suites, taxonomy


def canonical_base_digest() -> str:
    return object_digest(
        {
            logical: digest
            for logical, digest in sorted(PINNED_INPUT_HASHES.items())
            if logical != "docs/manifest.json"
        }
    )


def index_records(
    document: Mapping[str, Any], *, collection: str, source: str
) -> dict[str, dict[str, Any]]:
    rows = require_list(document.get(collection), source=f"{source}.{collection}")
    indexed: dict[str, dict[str, Any]] = {}
    for position, raw in enumerate(rows):
        row = require_mapping(raw, source=f"{source}.{collection}[{position}]")
        identifier = require_string(
            row.get("id"), source=f"{source}.{collection}[{position}].id"
        )
        if identifier in indexed:
            raise RuntimeError(f"duplicate {source} id: {identifier}")
        indexed[identifier] = row
    return indexed


def normalized_suite_environments(value: object, *, source: str) -> list[str]:
    raw = require_list(value, source=source)
    mapping = {
        "CI": "CI",
        "staging": "STAGING",
        "staging/recovery": "RECOVERY",
    }
    normalized: list[str] = []
    for position, item in enumerate(raw):
        label = require_string(item, source=f"{source}[{position}]")
        try:
            environment = mapping[label]
        except KeyError as exc:
            raise RuntimeError(
                f"unknown canonical Suite environment label: {label}"
            ) from exc
        if environment not in normalized:
            normalized.append(environment)
    return normalized


def initial_effective_state(
    registry: Mapping[str, Any],
    story_document: Mapping[str, Any],
    suite_document: Mapping[str, Any],
) -> dict[str, Any]:
    story_index = index_records(
        story_document, collection="stories", source="canonical story catalog"
    )
    suite_index = index_records(
        suite_document, collection="suites", source="canonical suite catalog"
    )
    environments = require_list(
        registry.get("environments"), source="canonical registry.environments"
    )
    environment_rows: list[dict[str, Any]] = []
    seen_environments: set[str] = set()
    for position, raw in enumerate(environments):
        row = require_mapping(
            raw, source=f"canonical registry.environments[{position}]"
        )
        identifier = require_string(
            row.get("id"), source=f"canonical registry.environments[{position}].id"
        )
        if identifier in seen_environments:
            raise RuntimeError(f"duplicate canonical environment: {identifier}")
        seen_environments.add(identifier)
        environment_rows.append(
            {
                "environment_id": identifier,
                "base_record_sha256": object_digest(row),
                "effective_status": row.get("status"),
                "effective_runtime_validation": row.get("runtime_validation"),
            }
        )

    story_rows: list[dict[str, Any]] = []
    for identifier, row in story_index.items():
        story_rows.append(
            {
                "story_id": identifier,
                "base_record_sha256": object_digest(row),
                "effective_implementation_status": row.get("implementation_status"),
                "effective_verification_status": row.get("verification_status"),
                "required_suites": list(row.get("test_suites", [])),
                "open_decisions": list(row.get("open_decisions", [])),
                "proposal_request_ids": [],
            }
        )

    suite_rows: list[dict[str, Any]] = []
    for identifier, row in suite_index.items():
        suite_rows.append(
            {
                "suite_id": identifier,
                "base_record_sha256": object_digest(row),
                "effective_implementation_status": row.get("implementation_status"),
                "effective_execution_status": row.get("execution_status"),
                "canonical_environment_labels": list(row.get("environments", [])),
                "canonical_environments": normalized_suite_environments(
                    row.get("environments"),
                    source=f"canonical suite {identifier}.environments",
                ),
            }
        )

    return {
        "stories": story_rows,
        "test_suites": suite_rows,
        "environments": environment_rows,
        "transition_control": {
            "sequence": 0,
            "history_head_sha256": sha256_bytes(b""),
            "last_requested_at": None,
            "last_decided_at": None,
            "consumed_evidence_identities": [],
            "story_invalidation_watermarks": {},
            "story_active_evidence_sha256": {},
            "story_active_evidence_observed_at": {},
            "story_active_evidence_valid_until": {},
        },
    }


def effective_status_digest(state: Mapping[str, Any]) -> str:
    stories = require_list(state.get("stories"), source="effective stories")
    suites = require_list(state.get("test_suites"), source="effective test suites")
    environments = require_list(
        state.get("environments"), source="effective environments"
    )
    effective = {
        "stories": [
            {
                key: row[key]
                for key in (
                    "story_id",
                    "base_record_sha256",
                    "effective_implementation_status",
                    "effective_verification_status",
                )
            }
            for row in stories
        ],
        "test_suites": [
            {
                key: row[key]
                for key in (
                    "suite_id",
                    "base_record_sha256",
                    "effective_implementation_status",
                    "effective_execution_status",
                )
            }
            for row in suites
        ],
        "environments": environments,
        "transition_control": require_mapping(
            state.get("transition_control"), source="effective transition control"
        ),
    }
    return object_digest(effective)


def transition_control(state: Mapping[str, Any]) -> dict[str, Any]:
    control = require_mapping(
        state.get("transition_control"), source="state.transition_control"
    )
    assert_exact_keys(
        control,
        required={
            "sequence",
            "history_head_sha256",
            "last_requested_at",
            "last_decided_at",
            "consumed_evidence_identities",
            "story_invalidation_watermarks",
            "story_active_evidence_sha256",
            "story_active_evidence_observed_at",
            "story_active_evidence_valid_until",
        },
        source="state.transition_control",
    )
    if type(control.get("sequence")) is not int or int(control["sequence"]) < 0:
        raise RuntimeError("transition sequence is malformed")
    head = require_string(
        control.get("history_head_sha256"),
        source="state.transition_control.history_head_sha256",
    )
    if not SHA256_PATTERN.fullmatch(head):
        raise RuntimeError("transition history head is malformed")
    for field in ("last_requested_at", "last_decided_at"):
        value = control.get(field)
        if value is not None:
            parse_utc_timestamp(value, source=f"state.transition_control.{field}")
    consumed = require_list(
        control.get("consumed_evidence_identities"),
        source="state.transition_control.consumed_evidence_identities",
    )
    if len(consumed) != len(set(consumed)) or not all(
        isinstance(item, str) and SHA256_PATTERN.fullmatch(item) for item in consumed
    ):
        raise RuntimeError("consumed evidence digest history is malformed")
    watermarks = require_mapping(
        control.get("story_invalidation_watermarks"),
        source="state.transition_control.story_invalidation_watermarks",
    )
    for story_id, timestamp in watermarks.items():
        if not isinstance(story_id, str) or not STORY_ID_PATTERN.fullmatch(story_id):
            raise RuntimeError("Story invalidation watermark key is malformed")
        parse_utc_timestamp(
            timestamp,
            source=f"state.transition_control.story_invalidation_watermarks.{story_id}",
        )
    active = require_mapping(
        control.get("story_active_evidence_sha256"),
        source="state.transition_control.story_active_evidence_sha256",
    )
    for story_id, digests in active.items():
        if not isinstance(story_id, str) or not STORY_ID_PATTERN.fullmatch(story_id):
            raise RuntimeError("active Story evidence key is malformed")
        values = require_list(digests, source=f"active Story evidence {story_id}")
        if (
            not values
            or len(values) != len(set(values))
            or not all(
                isinstance(item, str) and SHA256_PATTERN.fullmatch(item)
                for item in values
            )
        ):
            raise RuntimeError("active Story evidence digest inventory is malformed")
    observations = require_mapping(
        control.get("story_active_evidence_observed_at"),
        source="state.transition_control.story_active_evidence_observed_at",
    )
    if set(observations) != set(active):
        raise RuntimeError("active evidence observation inventory is inconsistent")
    for story_id, timestamp in observations.items():
        parse_utc_timestamp(
            timestamp,
            source=f"active Story evidence {story_id} observation watermark",
        )
    validity = require_mapping(
        control.get("story_active_evidence_valid_until"),
        source="state.transition_control.story_active_evidence_valid_until",
    )
    if not set(validity).issubset(active):
        raise RuntimeError("active evidence validity has no corresponding evidence")
    for story_id, timestamp in validity.items():
        parse_utc_timestamp(
            timestamp, source=f"active Story evidence {story_id} validity"
        )
    return control


def evidence_identity_digests(changes: Sequence[Mapping[str, Any]]) -> set[str]:
    identities: set[str] = set()
    for change in changes:
        story_id = require_string(
            change.get("story_id"), source="validated change.story_id"
        )
        for evidence in require_list(
            change.get("evidence"), source="validated change.evidence"
        ):
            item = require_mapping(evidence, source="validated change.evidence[]")
            suite_id = require_string(
                item.get("suite_id"), source="validated evidence.suite_id"
            )
            evidence_class = require_string(
                item.get("evidence_class"), source="validated evidence.evidence_class"
            )
            artifact_digests: set[str] = set()
            for digest in require_list(
                item.get("snapshot_artifact_sha256"),
                source="validated evidence.snapshot_artifact_sha256",
            ):
                digest_text = require_string(
                    digest, source="validated snapshot artifact SHA-256"
                )
                if not SHA256_PATTERN.fullmatch(digest_text):
                    raise RuntimeError(
                        "validated snapshot artifact digest is malformed"
                    )
                artifact_digests.add(digest_text)
            if not artifact_digests:
                raise RuntimeError("validated snapshot artifact inventory is empty")
            for artifact_digest in sorted(artifact_digests):
                identities.add(
                    object_digest(
                        {
                            "story_id": story_id,
                            "suite_id": suite_id,
                            "evidence_class": evidence_class,
                            "source_capture_sha256": artifact_digest,
                        }
                    )
                )
    return identities


def request_evidence_identity_digests(request: Mapping[str, Any]) -> set[str]:
    changes = [
        require_mapping(item, source="validated request.changes[]")
        for item in require_list(
            request.get("changes"), source="validated request.changes"
        )
    ]
    identities = evidence_identity_digests(changes)
    pr_evidence = request.get("pr_evidence")
    if isinstance(pr_evidence, dict) and isinstance(pr_evidence.get("uri"), str):
        identities.add(
            object_digest(
                {
                    "kind": "PR_URI",
                    "uri": pr_evidence["uri"],
                }
            )
        )
        if all(
            isinstance(pr_evidence.get(field), str)
            for field in ("implementation_commit_sha", "sha256")
        ):
            identities.add(
                object_digest(
                    {
                        "kind": "PR_CHANGESET",
                        "uri": pr_evidence["uri"],
                        "implementation_commit_sha": pr_evidence[
                            "implementation_commit_sha"
                        ],
                        "sha256": pr_evidence["sha256"],
                    }
                )
            )
    approval = request.get("approval")
    if isinstance(approval, dict) and isinstance(approval.get("evidence"), dict):
        identities.add(
            object_digest(
                {
                    "kind": "APPROVAL",
                    "sha256": str(approval["evidence"]["sha256"]),
                }
            )
        )
    production = request.get("production_approval_evidence")
    if isinstance(production, dict):
        for name, item in production.items():
            if isinstance(item, dict) and "sha256" in item:
                identities.add(
                    object_digest(
                        {
                            "kind": f"PRODUCTION_{name}",
                            "story_id": str(changes[0]["story_id"]),
                            "sha256": str(item["sha256"]),
                        }
                    )
                )
    scope = request.get("scope_decision_evidence")
    if isinstance(scope, dict) and "sha256" in scope:
        identities.add(
            object_digest(
                {
                    "kind": "SCOPE_DECISION",
                    "story_id": str(changes[0]["story_id"]),
                    "sha256": str(scope["sha256"]),
                }
            )
        )
    return identities


def request_schema() -> dict[str, Any]:
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    timestamp = {
        "type": "string",
        "pattern": ("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"),
    }
    actor = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "actor_type"],
        "properties": {
            "id": {"type": "string", "minLength": 3, "maxLength": 128},
            "actor_type": {"enum": list(ACTOR_TYPES)},
        },
    }
    evidence = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "suite_id",
            "environment",
            "evidence_class",
            "uri",
            "sha256",
            "observed_at",
        ],
        "properties": {
            "suite_id": {"type": "string", "pattern": "^TST-[0-9]{3}$"},
            "environment": {
                "enum": [
                    "LOCAL",
                    "DEV",
                    "CI",
                    "INTEGRATION",
                    "STAGING",
                    "RECOVERY",
                    "PRODUCTION",
                ]
            },
            "evidence_class": {"enum": list(EVIDENCE_CLASSES)},
            "uri": {"type": "string", "pattern": "^repo://"},
            "sha256": sha,
            "observed_at": timestamp,
            "expires_at": timestamp,
        },
    }
    change = {
        "type": "object",
        "additionalProperties": False,
        "required": ["story_id", "expected", "target", "evidence"],
        "properties": {
            "story_id": {"type": "string", "pattern": "^ST-[0-9]{4}$"},
            "expected": {
                "type": "object",
                "additionalProperties": False,
                "required": ["implementation_status", "verification_status"],
                "properties": {
                    "implementation_status": {
                        "enum": list(IMPLEMENTATION_CHAIN)
                        + list(NON_CHAIN_IMPLEMENTATION_STATUSES)
                    },
                    "verification_status": {"enum": list(VERIFICATION_STATUSES)},
                },
            },
            "target": {
                "type": "object",
                "additionalProperties": False,
                "required": ["implementation_status", "verification_status"],
                "properties": {
                    "implementation_status": {
                        "enum": list(IMPLEMENTATION_CHAIN)
                        + list(NON_CHAIN_IMPLEMENTATION_STATUSES)
                    },
                    "verification_status": {"enum": list(VERIFICATION_STATUSES)},
                },
            },
            "evidence": {"type": "array", "minItems": 1, "items": evidence},
        },
    }
    repo_evidence = {
        "type": "object",
        "additionalProperties": False,
        "required": ["uri", "sha256", "observed_at"],
        "properties": {
            "uri": {"type": "string", "pattern": "^repo://"},
            "sha256": sha,
            "observed_at": timestamp,
            "expires_at": timestamp,
        },
    }
    approval = {
        "type": "object",
        "additionalProperties": False,
        "required": ["approver", "decision", "reason", "decided_at", "evidence"],
        "properties": {
            "approver": actor,
            "decision": {"const": "APPROVED"},
            "reason": {"type": "string", "minLength": 12, "maxLength": 2048},
            "decided_at": timestamp,
            "evidence": repo_evidence,
        },
    }
    pr_evidence = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "uri",
            "implementation_commit_sha",
            "sha256",
            "observed_at",
        ],
        "properties": {
            "uri": {"type": "string", "format": "uri"},
            "implementation_commit_sha": {
                "type": "string",
                "pattern": "^[0-9a-f]{40,64}$",
            },
            "sha256": sha,
            "observed_at": timestamp,
            "expires_at": timestamp,
        },
    }
    production_approval_evidence = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "release_decision",
            "gate_report",
            "security_approval",
            "operations_approval",
        ],
        "properties": {
            "release_decision": repo_evidence,
            "gate_report": repo_evidence,
            "security_approval": repo_evidence,
            "operations_approval": repo_evidence,
        },
    }
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:raos:status-transition-request:v1",
        "title": "RAOS status transition request v1",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "document",
            "requested_by",
            "requested_at",
            "reason",
            "expected",
            "changes",
        ],
        "properties": {
            "document": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "schema_version", "intent"],
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^STATUS-[A-Z0-9][A-Z0-9_-]{7,95}$",
                    },
                    "schema_version": {"const": 1},
                    "intent": {"enum": ["PROPOSE", "APPLY"]},
                },
            },
            "requested_by": actor,
            "requested_at": timestamp,
            "reason": {"type": "string", "minLength": 12, "maxLength": 4096},
            "expected": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "canonical_base_sha256",
                    "effective_status_sha256",
                ],
                "properties": {
                    "canonical_base_sha256": sha,
                    "effective_status_sha256": sha,
                },
            },
            "changes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": change,
            },
            "pr_evidence": pr_evidence,
            "approval": approval,
            "production_approval_evidence": production_approval_evidence,
            "scope_decision_evidence": repo_evidence,
        },
        "allOf": [
            {
                "if": {
                    "properties": {
                        "document": {"properties": {"intent": {"const": "PROPOSE"}}}
                    }
                },
                "then": {
                    "not": {
                        "anyOf": [
                            {"required": ["pr_evidence"]},
                            {"required": ["approval"]},
                            {"required": ["production_approval_evidence"]},
                            {"required": ["scope_decision_evidence"]},
                        ]
                    }
                },
                "else": {"required": ["pr_evidence", "approval"]},
            }
        ],
    }
    return schema


def validate_repo_evidence(
    value: Mapping[str, Any],
    *,
    source: str,
    required_suite: bool = True,
    immutable_artifact_prefix: str | None = None,
) -> dict[str, Any]:
    required = {"uri", "sha256", "observed_at"}
    if required_suite:
        required |= {"suite_id", "environment", "evidence_class"}
    assert_exact_keys(value, required=required, optional={"expires_at"}, source=source)
    validate_temporal_evidence(value, source=source)
    uri = require_string(value.get("uri"), source=f"{source}.uri", maximum=1024)
    if not uri.startswith("repo://"):
        raise RuntimeError(
            f"only hash-verifiable repo:// evidence is allowed: {source}"
        )
    relative_value = uri.removeprefix("repo://")
    relative = checked_relative_path(relative_value, source=f"{source}.uri")
    if immutable_artifact_prefix is not None and not relative.as_posix().startswith(
        immutable_artifact_prefix
    ):
        raise RuntimeError(f"{source} must use the immutable evidence artifact store")
    path = REPO_ROOT.joinpath(*relative.parts)
    if path_has_symlink(REPO_ROOT, relative):
        raise RuntimeError(f"evidence path contains a symlink component: {uri}")
    try:
        path.resolve(strict=True).relative_to(REPO_ROOT.resolve())
    except (FileNotFoundError, ValueError) as exc:
        raise RuntimeError(f"evidence escapes or is missing: {uri}") from exc
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"evidence must be a regular non-symlink file: {uri}")
    expected = require_string(value.get("sha256"), source=f"{source}.sha256")
    if not SHA256_PATTERN.fullmatch(expected):
        raise RuntimeError(f"invalid evidence SHA-256 in {source}")
    if immutable_artifact_prefix is not None and not relative.name.startswith(
        f"{expected}-"
    ):
        raise RuntimeError(
            f"{source} content-addressed filename must start with its SHA-256"
        )
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(
            f"evidence hash mismatch for {uri}: expected {expected}, got {actual}"
        )
    return dict(value)


def validate_repo_artifact_reference(
    value: Mapping[str, Any],
    *,
    source: str,
    artifact_uri_prefix: str,
    verify_original: bool = False,
) -> dict[str, str]:
    """Validate an immutable content-addressed capture, not its mutable origin."""

    assert_exact_keys(
        value,
        required={"original_uri", "artifact_uri", "sha256"},
        source=source,
    )
    original_uri = require_string(
        value.get("original_uri"), source=f"{source}.original_uri", maximum=1024
    )
    if not original_uri.startswith("repo://"):
        raise RuntimeError(f"snapshot original must use repo:// URI: {source}")
    original_relative = checked_relative_path(
        original_uri.removeprefix("repo://"), source=f"{source}.original_uri"
    )
    sensitive_components = {
        ".aws",
        ".git",
        ".gnupg",
        ".secrets",
        ".ssh",
        "credentials",
        "secrets",
    }
    folded_parts = {part.casefold() for part in original_relative.parts}
    original_name = original_relative.name.casefold()
    if (
        folded_parts & sensitive_components
        or original_name.startswith(".env")
        or original_name
        in {
            ".netrc",
            ".npmrc",
            ".pypirc",
            "id_ecdsa",
            "id_ed25519",
            "id_rsa",
        }
        or PurePosixPath(original_name).suffix in {".key", ".pem", ".p12", ".pfx"}
    ):
        raise RuntimeError("sensitive paths cannot be captured as status evidence")
    artifact_uri = require_string(
        value.get("artifact_uri"), source=f"{source}.artifact_uri", maximum=1024
    )
    if not artifact_uri.startswith("repo://"):
        raise RuntimeError(f"snapshot capture must use repo:// URI: {source}")
    relative = checked_relative_path(
        artifact_uri.removeprefix("repo://"), source=f"{source}.artifact_uri"
    )
    if not relative.as_posix().startswith(artifact_uri_prefix):
        raise RuntimeError("snapshot capture must use the immutable artifact store")
    path = REPO_ROOT.joinpath(*relative.parts)
    if path_has_symlink(REPO_ROOT, relative):
        raise RuntimeError(
            f"snapshot capture contains a symlink component: {artifact_uri}"
        )
    try:
        path.resolve(strict=True).relative_to(REPO_ROOT.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise RuntimeError(
            f"snapshot capture escapes or is missing: {artifact_uri}"
        ) from exc
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(
            f"snapshot capture must be a regular non-symlink file: {artifact_uri}"
        )
    expected = require_string(value.get("sha256"), source=f"{source}.sha256")
    if not SHA256_PATTERN.fullmatch(expected):
        raise RuntimeError(f"invalid snapshot capture SHA-256 in {source}")
    if not relative.name.startswith(f"{expected}-"):
        raise RuntimeError("snapshot capture filename must start with its SHA-256")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(
            f"snapshot capture hash mismatch for {artifact_uri}: "
            f"expected {expected}, got {actual}"
        )
    if verify_original:
        original_path = REPO_ROOT.joinpath(*original_relative.parts)
        if path_has_symlink(REPO_ROOT, original_relative):
            raise RuntimeError(
                f"snapshot original contains a symlink component: {original_uri}"
            )
        try:
            original_path.resolve(strict=True).relative_to(
                REPO_ROOT.resolve(strict=True)
            )
        except (FileNotFoundError, ValueError) as exc:
            raise RuntimeError(
                f"snapshot original escapes or is missing: {original_uri}"
            ) from exc
        if original_path.is_symlink() or not original_path.is_file():
            raise RuntimeError(
                f"snapshot original must be a regular file: {original_uri}"
            )
        if sha256_file(original_path) != expected:
            raise RuntimeError(
                "new live snapshot capture does not match its declared original"
            )
    return {
        "original_uri": original_uri,
        "artifact_uri": artifact_uri,
        "sha256": expected,
    }


def validate_evidence_snapshot(
    path: Path,
    *,
    artifact_uri_prefix: str = EVIDENCE_ARTIFACT_URI_PREFIX,
    known_suite_ids: set[str] | None = None,
    verify_original_artifacts: bool = False,
) -> dict[str, Any]:
    snapshot = load_yaml(path)
    assert_exact_keys(
        snapshot,
        required={
            "document",
            "story_id",
            "evidence_class",
            "formal_suite_status",
            "source_artifacts",
            "suite_results",
            "local_results",
            "boundary",
        },
        optional={"invalidates_evidence_sha256"},
        source=f"evidence snapshot {path.name}",
    )
    document = require_mapping(
        snapshot.get("document"), source=f"evidence snapshot {path.name}.document"
    )
    assert_exact_keys(
        document,
        required={"id", "schema_version", "recorded_at"},
        optional={"valid_until"},
        source=f"evidence snapshot {path.name}.document",
    )
    require_string(
        document.get("id"), source=f"evidence snapshot {path.name}.document.id"
    )
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
    ):
        raise RuntimeError(f"unsupported evidence snapshot version: {path}")
    recorded_at = require_string(
        document.get("recorded_at"),
        source=f"evidence snapshot {path.name}.recorded_at",
    )
    parse_utc_timestamp(
        recorded_at, source=f"evidence snapshot {path.name}.recorded_at"
    )
    valid_until: str | None = None
    if "valid_until" in document:
        valid_until = require_string(
            document["valid_until"],
            source=f"evidence snapshot {path.name}.document.valid_until",
        )
        if parse_utc_timestamp(
            valid_until,
            source=f"evidence snapshot {path.name}.document.valid_until",
        ) <= parse_utc_timestamp(
            recorded_at, source=f"evidence snapshot {path.name}.document.recorded_at"
        ):
            raise RuntimeError("snapshot valid_until must follow recorded_at")
    story_id = require_string(
        snapshot.get("story_id"), source=f"evidence snapshot {path.name}.story_id"
    )
    if not STORY_ID_PATTERN.fullmatch(story_id):
        raise RuntimeError(f"invalid Story ID in evidence snapshot: {path}")
    evidence_class = require_string(
        snapshot.get("evidence_class"),
        source=f"evidence snapshot {path.name}.evidence_class",
    )
    if evidence_class not in EVIDENCE_CLASSES:
        raise RuntimeError(f"unknown evidence class in snapshot: {path}")
    invalidates_raw = snapshot.get("invalidates_evidence_sha256")
    invalidates: list[str] = []
    if evidence_class == "EXPIRY":
        invalidates = [
            require_string(item, source=f"evidence snapshot {path.name}.invalidates[]")
            for item in require_list(
                invalidates_raw,
                source=f"evidence snapshot {path.name}.invalidates_evidence_sha256",
            )
        ]
        if (
            not invalidates
            or len(invalidates) != len(set(invalidates))
            or not all(SHA256_PATTERN.fullmatch(item) for item in invalidates)
        ):
            raise RuntimeError("EXPIRY snapshot invalidation digest list is malformed")
    elif "invalidates_evidence_sha256" in snapshot:
        raise RuntimeError("only EXPIRY snapshots may invalidate prior evidence")
    formal_status = require_string(
        snapshot.get("formal_suite_status"),
        source=f"evidence snapshot {path.name}.formal_suite_status",
    )
    if formal_status not in VERIFICATION_STATUSES:
        raise RuntimeError(f"unknown formal Suite status in snapshot: {path}")

    source_artifacts = require_list(
        snapshot.get("source_artifacts"),
        source=f"evidence snapshot {path.name}.source_artifacts",
    )
    if not source_artifacts:
        raise RuntimeError(f"evidence snapshot source_artifacts is empty: {path}")
    normalized_artifacts: list[dict[str, str]] = []
    seen_artifacts: set[tuple[str, str]] = set()
    seen_artifact_digests: set[str] = set()
    for position, raw in enumerate(source_artifacts):
        source = f"evidence snapshot {path.name}.source_artifacts[{position}]"
        artifact = validate_repo_artifact_reference(
            require_mapping(raw, source=source),
            source=source,
            artifact_uri_prefix=artifact_uri_prefix,
            verify_original=verify_original_artifacts,
        )
        identity = (artifact["artifact_uri"], artifact["sha256"])
        if identity in seen_artifacts:
            raise RuntimeError(f"duplicate source artifact in snapshot: {path}")
        if artifact["sha256"] in seen_artifact_digests:
            raise RuntimeError(f"duplicate source artifact digest in snapshot: {path}")
        seen_artifacts.add(identity)
        seen_artifact_digests.add(artifact["sha256"])
        normalized_artifacts.append(artifact)

    suite_results = require_list(
        snapshot.get("suite_results"),
        source=f"evidence snapshot {path.name}.suite_results",
    )
    if not suite_results:
        raise RuntimeError(f"evidence snapshot suite_results is empty: {path}")
    seen_suites: set[str] = set()
    normalized_results: list[dict[str, str]] = []
    allowed_results = {
        "LOCAL_PASS",
        "PLANNED",
        "PR_REVIEWED",
        "PASS",
        "PARTIAL",
        "FAIL",
        "EXPIRED",
        "ROLLBACK_APPROVED",
        "DEPLOYED",
        "RELEASED",
        "SCOPE_APPROVED",
    }
    for position, raw in enumerate(suite_results):
        source = f"evidence snapshot {path.name}.suite_results[{position}]"
        item = require_mapping(raw, source=source)
        assert_exact_keys(
            item,
            required={"suite_id", "environment", "result"},
            source=source,
        )
        suite_id = require_string(item.get("suite_id"), source=f"{source}.suite_id")
        environment = require_string(
            item.get("environment"), source=f"{source}.environment"
        )
        result = require_string(item.get("result"), source=f"{source}.result")
        if not SUITE_ID_PATTERN.fullmatch(suite_id):
            raise RuntimeError(f"invalid Suite ID in {source}")
        if known_suite_ids is not None and suite_id not in known_suite_ids:
            raise RuntimeError(f"unknown canonical Suite ID in {source}: {suite_id}")
        if suite_id in seen_suites:
            raise RuntimeError(f"duplicate Suite result in snapshot: {suite_id}")
        if environment not in {
            "LOCAL",
            "DEV",
            "CI",
            "INTEGRATION",
            "STAGING",
            "RECOVERY",
            "PRODUCTION",
        }:
            raise RuntimeError(f"unknown evidence environment in {source}")
        if result not in allowed_results:
            raise RuntimeError(f"unknown evidence result in {source}")
        seen_suites.add(suite_id)
        normalized_results.append(
            {"suite_id": suite_id, "environment": environment, "result": result}
        )

    local_results = require_list(
        snapshot.get("local_results"),
        source=f"evidence snapshot {path.name}.local_results",
    )
    for position, raw in enumerate(local_results):
        source = f"evidence snapshot {path.name}.local_results[{position}]"
        item = require_mapping(raw, source=source)
        assert_exact_keys(item, required={"command", "result"}, source=source)
        require_string(item.get("command"), source=f"{source}.command")
        require_string(item.get("result"), source=f"{source}.result")
    require_string(
        snapshot.get("boundary"), source=f"evidence snapshot {path.name}.boundary"
    )
    return {
        **snapshot,
        "document": {
            **document,
            "recorded_at": recorded_at,
            **({"valid_until": valid_until} if valid_until is not None else {}),
        },
        "story_id": story_id,
        "evidence_class": evidence_class,
        "formal_suite_status": formal_status,
        "source_artifacts": normalized_artifacts,
        "suite_results": normalized_results,
        "invalidates_evidence_sha256": invalidates,
    }


def validate_snapshot_binding(
    path: Path,
    *,
    story_id: str,
    suite_id: str,
    evidence_class: str,
    environment: str,
    observed_at: str,
    expires_at: str | None,
    target_verification: str,
    artifact_uri_prefix: str,
    known_suite_ids: set[str],
    verify_original_artifacts: bool,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    snapshot = validate_evidence_snapshot(
        path,
        artifact_uri_prefix=artifact_uri_prefix,
        known_suite_ids=known_suite_ids,
        verify_original_artifacts=verify_original_artifacts,
    )
    if snapshot["story_id"] != story_id:
        raise RuntimeError(
            f"evidence snapshot Story mismatch: expected {story_id}, "
            f"got {snapshot['story_id']}"
        )
    if snapshot["evidence_class"] != evidence_class:
        raise RuntimeError(
            "evidence snapshot class mismatch: "
            f"expected {evidence_class}, got {snapshot['evidence_class']}"
        )
    if snapshot["document"]["recorded_at"] != observed_at:
        raise RuntimeError("evidence observed_at must equal snapshot recorded_at")
    if snapshot["document"].get("valid_until") != expires_at:
        raise RuntimeError("evidence expires_at must equal snapshot valid_until")
    results = [
        item for item in snapshot["suite_results"] if item["suite_id"] == suite_id
    ]
    if len(results) != 1:
        raise RuntimeError(f"snapshot must contain exactly one result for {suite_id}")
    result = results[0]
    if result["environment"] != environment:
        raise RuntimeError(f"evidence snapshot environment mismatch for {suite_id}")
    expected_results: dict[str, set[str]] = {
        "CHANGE_PLAN": {"PLANNED"},
        "LOCAL_IMPLEMENTATION": {"LOCAL_PASS"},
        "PR_CHANGESET": {"PR_REVIEWED"},
        "REGRESSION": ({"PARTIAL"} if target_verification == "PARTIAL" else {"FAIL"}),
        "EXPIRY": {"EXPIRED"},
        "ROLLBACK_DECISION": {"ROLLBACK_APPROVED"},
        "STAGING_DEPLOYMENT": {"DEPLOYED"},
        "PRODUCTION_RELEASE": {"RELEASED"},
        "SCOPE_DECISION": {"SCOPE_APPROVED"},
    }
    if evidence_class == "RUNTIME_SUITE_RESULT":
        expected_results[evidence_class] = (
            {"PASS"}
            if target_verification == "PASS"
            else {"FAIL"}
            if target_verification == "FAIL"
            else {"PASS", "PARTIAL", "FAIL"}
        )
    allowed = expected_results.get(evidence_class)
    if allowed is None or result["result"] not in allowed:
        raise RuntimeError(
            f"evidence snapshot result {result['result']} is inconsistent with "
            f"{evidence_class}/{target_verification}"
        )
    formal_status = snapshot["formal_suite_status"]
    expected_formal_status = {
        "CHANGE_PLAN": "NOT_EXECUTED",
        "LOCAL_IMPLEMENTATION": "NOT_EXECUTED",
        "PR_CHANGESET": "NOT_EXECUTED",
        "STAGING_DEPLOYMENT": "PASS",
        "PRODUCTION_RELEASE": "PASS",
        "REGRESSION": target_verification,
        "EXPIRY": "NOT_EXECUTED",
        "ROLLBACK_DECISION": "NOT_EXECUTED",
        "SCOPE_DECISION": "NOT_EXECUTED",
    }.get(evidence_class, target_verification)
    if formal_status != expected_formal_status:
        raise RuntimeError(
            "evidence snapshot formal status mismatch: "
            f"expected {expected_formal_status}, got {formal_status}"
        )
    artifact_digests = tuple(
        sorted(str(item["sha256"]) for item in snapshot["source_artifacts"])
    )
    return (
        str(result["result"]),
        artifact_digests,
        tuple(snapshot["invalidates_evidence_sha256"]),
    )


def validate_actor(value: Mapping[str, Any], *, source: str) -> dict[str, str]:
    assert_exact_keys(value, required={"id", "actor_type"}, source=source)
    actor_id = require_string(
        value.get("id"), source=f"{source}.id", minimum=3, maximum=128
    )
    actor_type = require_string(
        value.get("actor_type"), source=f"{source}.actor_type", maximum=32
    )
    if actor_type not in ACTOR_TYPES:
        raise RuntimeError(f"unknown actor type in {source}: {actor_type}")
    return {"id": actor_id, "actor_type": actor_type}


def pr_evidence_digest(uri: str, implementation_commit_sha: str) -> str:
    return sha256_bytes(f"{uri}\n{implementation_commit_sha}\n".encode())


def validate_pr_evidence(
    value: Mapping[str, Any], *, require_context: bool
) -> dict[str, str]:
    assert_exact_keys(
        value,
        required={"uri", "implementation_commit_sha", "sha256", "observed_at"},
        optional={"expires_at"},
        source="request.pr_evidence",
    )
    validate_temporal_evidence(value, source="request.pr_evidence")
    uri = require_string(value.get("uri"), source="request.pr_evidence.uri")
    implementation_commit_sha = require_string(
        value.get("implementation_commit_sha"),
        source="request.pr_evidence.implementation_commit_sha",
    )
    digest = require_string(value.get("sha256"), source="request.pr_evidence.sha256")
    if not GITHUB_PR_PATTERN.fullmatch(uri):
        raise RuntimeError("PR evidence must identify a concrete GitHub pull request")
    if not HEAD_SHA_PATTERN.fullmatch(implementation_commit_sha):
        raise RuntimeError(
            "PR evidence implementation_commit_sha must be a 40-64 character hex SHA"
        )
    expected = pr_evidence_digest(uri, implementation_commit_sha)
    if digest != expected:
        raise RuntimeError("PR evidence digest mismatch")
    if require_context:
        event = os.environ.get("GITHUB_EVENT_NAME")
        context_uri = os.environ.get("RAOS_PR_URI")
        context_head = os.environ.get("RAOS_STATUS_PR_HEAD_SHA")
        context_base = os.environ.get("RAOS_BASE_SHA")
        if event not in {"pull_request", "pull_request_target"}:
            raise RuntimeError("APPLY requires a live GitHub pull-request context")
        if (
            context_uri != uri
            or not isinstance(context_head, str)
            or not isinstance(context_base, str)
        ):
            raise RuntimeError("PR evidence does not match the live GitHub context")
        if not HEAD_SHA_PATTERN.fullmatch(
            context_head
        ) or not HEAD_SHA_PATTERN.fullmatch(context_base):
            raise RuntimeError("live status PR base/head SHA is malformed")
        if context_base == context_head:
            raise RuntimeError("live pull request base and head must differ")
        if implementation_commit_sha in {context_base, context_head}:
            raise RuntimeError(
                "implementation_commit_sha must be a distinct commit inside the PR"
            )
        actual_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if actual_head != context_head:
            raise RuntimeError(
                "checked-out tree does not equal the live status PR head"
            )
        ancestry_pairs = (
            (context_base, context_head, "PR base is not an ancestor of PR head"),
            (
                context_base,
                implementation_commit_sha,
                "implementation commit is not inside the PR base..head range",
            ),
            (
                implementation_commit_sha,
                context_head,
                "implementation commit is not an ancestor of the request-bearing PR head",
            ),
        )
        for ancestor_sha, descendant_sha, message in ancestry_pairs:
            ancestor = subprocess.run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    ancestor_sha,
                    descendant_sha,
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if ancestor.returncode != 0:
                raise RuntimeError(message)
    result = {
        "uri": uri,
        "implementation_commit_sha": implementation_commit_sha,
        "sha256": digest,
        "observed_at": value["observed_at"],
    }
    if "expires_at" in value:
        result["expires_at"] = value["expires_at"]
    return result


def validate_approval(
    value: Mapping[str, Any],
    *,
    requester: Mapping[str, str],
    requested_at: datetime,
    artifact_uri_prefix: str,
) -> dict[str, Any]:
    assert_exact_keys(
        value,
        required={"approver", "decision", "reason", "decided_at", "evidence"},
        source="request.approval",
    )
    approver = validate_actor(
        require_mapping(value.get("approver"), source="request.approval.approver"),
        source="request.approval.approver",
    )
    if approver["actor_type"] != "HUMAN":
        raise RuntimeError("status APPLY approval must come from a human")
    if approver["id"] == requester["id"]:
        raise RuntimeError("requester cannot approve their own status transition")
    if value.get("decision") != "APPROVED":
        raise RuntimeError("status APPLY requires an APPROVED decision")
    reason = require_string(
        value.get("reason"),
        source="request.approval.reason",
        minimum=12,
        maximum=2048,
    )
    decided_text = require_string(
        value.get("decided_at"), source="request.approval.decided_at"
    )
    decided_at = parse_utc_timestamp(decided_text, source="request.approval.decided_at")
    if decided_at < requested_at:
        raise RuntimeError("approval decided_at must not precede requested_at")
    evidence = validate_repo_evidence(
        require_mapping(value.get("evidence"), source="request.approval.evidence"),
        source="request.approval.evidence",
        required_suite=False,
        immutable_artifact_prefix=artifact_uri_prefix,
    )
    evidence_observed = parse_utc_timestamp(
        evidence["observed_at"], source="request.approval.evidence.observed_at"
    )
    if evidence_observed > decided_at:
        raise RuntimeError("approval evidence cannot postdate approval decision")
    require_evidence_fresh_at(
        evidence, reference=decided_at, source="request.approval.evidence"
    )
    return {
        "approver": approver,
        "decision": "APPROVED",
        "reason": reason,
        "decided_at": decided_text,
        "evidence": evidence,
    }


def validate_production_approval_evidence(
    value: Mapping[str, Any], *, artifact_uri_prefix: str
) -> dict[str, dict[str, Any]]:
    required = {
        "release_decision",
        "gate_report",
        "security_approval",
        "operations_approval",
    }
    assert_exact_keys(
        value,
        required=required,
        source="request.production_approval_evidence",
    )
    validated = {
        name: validate_repo_evidence(
            require_mapping(
                value.get(name), source=f"request.production_approval_evidence.{name}"
            ),
            source=f"request.production_approval_evidence.{name}",
            required_suite=False,
            immutable_artifact_prefix=artifact_uri_prefix,
        )
        for name in sorted(required)
    }
    identities = {(item["uri"], item["sha256"]) for item in validated.values()}
    if len(identities) != len(required):
        raise RuntimeError(
            "production governance artifacts must be four distinct files"
        )
    return validated


def implementation_transition_kind(source: str, target: str) -> str:
    pair = (source, target)
    special = SPECIAL_SCOPE_TRANSITIONS.get(pair)
    if special is not None:
        return special
    if pair in FORWARD_TRANSITIONS:
        return "FORWARD"
    if pair in DEMOTION_TRANSITIONS:
        return "DEMOTION"
    raise RuntimeError(f"forbidden implementation transition: {source} -> {target}")


def verification_transition_kind(source: str, target: str) -> str:
    if source == target:
        raise RuntimeError("status transition request must not be a no-op")
    kind = VERIFICATION_ONLY_TRANSITIONS.get((source, target))
    if kind is not None:
        return kind
    raise RuntimeError(f"forbidden verification transition: {source} -> {target}")


def evidence_policy_for_target(target: str, kind: str) -> tuple[str, str]:
    if kind == "DEMOTION":
        return "DEMOTION_EVIDENCE", "ANY_CANONICAL"
    if kind == "REGRESSION":
        return "REGRESSION", "SUITE_CANONICAL"
    if kind == "EXPIRY":
        return "EXPIRY", "SUITE_CANONICAL"
    if kind == "VERIFICATION_RESULT":
        return "RUNTIME_SUITE_RESULT", "SUITE_CANONICAL"
    if kind == "POST_MVP_ACTIVATION":
        return "CHANGE_PLAN", "LOCAL"
    if kind in {"DEFERRAL", "SCOPE_CHANGE"}:
        return "SCOPE_DECISION", "LOCAL"
    policies = {
        "IN_PROGRESS": ("CHANGE_PLAN", "LOCAL"),
        "IMPLEMENTED_NOT_VALIDATED": ("PR_CHANGESET", "CI"),
        "VALIDATED": ("RUNTIME_SUITE_RESULT", "SUITE_CANONICAL"),
        "DEPLOYED_STAGING": ("STAGING_DEPLOYMENT", "STAGING"),
        "DEPLOYED_PRODUCTION": ("PRODUCTION_RELEASE", "PRODUCTION"),
    }
    try:
        return policies[target]
    except KeyError as exc:
        raise RuntimeError(
            f"no evidence policy for transition target: {target}"
        ) from exc


def validate_evidence_set(
    raw_evidence: object,
    *,
    source: str,
    story_id: str,
    target_verification: str,
    required_suites: Sequence[str],
    suite_index: Mapping[str, Mapping[str, Any]],
    expected_class: str,
    environment_policy: str,
    coverage_policy: str = "EXACT",
    evidence_uri_prefix: str = SUITE_EVIDENCE_URI_PREFIX,
    artifact_uri_prefix: str = EVIDENCE_ARTIFACT_URI_PREFIX,
    allowed_evidence_classes: set[str] | None = None,
    verify_original_artifacts: bool = False,
) -> list[dict[str, Any]]:
    entries = require_list(raw_evidence, source=source)
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    snapshot_results: list[str] = []
    for position, raw in enumerate(entries):
        entry_source = f"{source}[{position}]"
        entry = validate_repo_evidence(
            require_mapping(raw, source=entry_source), source=entry_source
        )
        uri = require_string(entry.get("uri"), source=f"{entry_source}.uri")
        relative = checked_relative_path(
            uri.removeprefix("repo://"), source=f"{entry_source}.uri"
        )
        if not relative.as_posix().startswith(evidence_uri_prefix):
            raise RuntimeError(
                "Suite evidence must reference an append-only evidence snapshot"
            )
        suite_id = require_string(
            entry.get("suite_id"), source=f"{entry_source}.suite_id"
        )
        if not SUITE_ID_PATTERN.fullmatch(suite_id) or suite_id not in suite_index:
            raise RuntimeError(f"unknown suite in {entry_source}: {suite_id}")
        if suite_id in seen:
            raise RuntimeError(f"duplicate suite evidence for {suite_id}")
        seen.add(suite_id)
        evidence_class = entry.get("evidence_class")
        if evidence_class not in EVIDENCE_CLASSES:
            raise RuntimeError(f"unknown evidence class in {entry_source}")
        allowed_classes = allowed_evidence_classes or (
            {"REGRESSION", "EXPIRY", "ROLLBACK_DECISION"}
            if expected_class == "DEMOTION_EVIDENCE"
            else {expected_class}
        )
        if evidence_class not in allowed_classes:
            raise RuntimeError(
                f"evidence class {evidence_class} is inconsistent with "
                f"required {sorted(allowed_classes)}"
            )
        environment = entry.get("environment")
        canonical_environments = normalized_suite_environments(
            suite_index[suite_id].get("environments"),
            source=f"canonical suite {suite_id}.environments",
        )
        if environment_policy == "LOCAL" and environment != "LOCAL":
            raise RuntimeError(f"{expected_class} evidence must use LOCAL")
        if environment_policy == "CI" and environment != "CI":
            raise RuntimeError(f"{expected_class} evidence must use CI")
        if environment_policy == "STAGING" and environment != "STAGING":
            raise RuntimeError(f"{expected_class} evidence must use STAGING")
        if environment_policy == "PRODUCTION" and environment != "PRODUCTION":
            raise RuntimeError(f"{expected_class} evidence must use PRODUCTION")
        if (
            environment_policy in {"SUITE_CANONICAL", "ANY_CANONICAL"}
            and environment not in canonical_environments
        ):
            raise RuntimeError(
                f"evidence environment {environment} is not declared for {suite_id}"
            )
        snapshot_result, artifact_digests, invalidates = validate_snapshot_binding(
            REPO_ROOT.joinpath(*relative.parts),
            story_id=story_id,
            suite_id=suite_id,
            evidence_class=str(evidence_class),
            environment=str(environment),
            observed_at=require_string(
                entry.get("observed_at"), source=f"{entry_source}.observed_at"
            ),
            expires_at=(
                require_string(
                    entry.get("expires_at"), source=f"{entry_source}.expires_at"
                )
                if "expires_at" in entry
                else None
            ),
            target_verification=target_verification,
            artifact_uri_prefix=artifact_uri_prefix,
            known_suite_ids=set(suite_index),
            verify_original_artifacts=verify_original_artifacts,
        )
        snapshot_results.append(snapshot_result)
        entry["snapshot_artifact_sha256"] = list(artifact_digests)
        entry["invalidates_evidence_sha256"] = list(invalidates)
        validated.append(entry)
    required_set = set(required_suites)
    if coverage_policy == "EXACT" and seen != required_set:
        raise RuntimeError(
            "required suite evidence mismatch: "
            f"missing={sorted(set(required_suites) - seen)}, "
            f"unexpected={sorted(seen - required_set)}"
        )
    if coverage_policy == "NONEMPTY_SUBSET" and (
        not seen or not seen.issubset(required_set)
    ):
        raise RuntimeError(
            "evidence must be a nonempty subset of required suites: "
            f"required={sorted(required_set)}, actual={sorted(seen)}"
        )
    if coverage_policy not in {"EXACT", "NONEMPTY_SUBSET"}:
        raise RuntimeError(f"unknown evidence coverage policy: {coverage_policy}")
    if target_verification == "PASS" and any(
        result != "PASS" for result in snapshot_results
    ):
        raise RuntimeError("verification PASS requires PASS from every required Suite")
    if target_verification == "FAIL" and "FAIL" not in snapshot_results:
        raise RuntimeError("verification FAIL requires at least one Suite FAIL")
    if target_verification == "PARTIAL" and (
        "FAIL" in snapshot_results
        or (
            seen == required_set
            and all(result == "PASS" for result in snapshot_results)
        )
    ):
        raise RuntimeError(
            "verification PARTIAL requires incomplete or PARTIAL non-failing evidence"
        )
    return validated


def validate_verification_coupling(
    *,
    implementation_status: str,
    verification_status: str,
    implementation_changed: bool,
    transition_kind: str,
) -> None:
    if verification_status == "PASS" and implementation_status not in {
        "VALIDATED",
        "DEPLOYED_STAGING",
        "DEPLOYED_PRODUCTION",
    }:
        raise RuntimeError(
            "verification PASS requires implementation VALIDATED or deployed"
        )
    if (
        implementation_changed
        and transition_kind == "FORWARD"
        and implementation_status == "VALIDATED"
        and verification_status != "PASS"
    ):
        raise RuntimeError("forward VALIDATED promotion requires verification PASS")


def validate_proposal_change(
    change: Mapping[str, Any],
    *,
    story_row: Mapping[str, Any],
    story_definition: Mapping[str, Any],
    suite_index: Mapping[str, Mapping[str, Any]],
    source: str,
    evidence_uri_prefix: str = SUITE_EVIDENCE_URI_PREFIX,
    artifact_uri_prefix: str = EVIDENCE_ARTIFACT_URI_PREFIX,
    verify_original_artifacts: bool = False,
) -> dict[str, Any]:
    expected = require_mapping(change.get("expected"), source=f"{source}.expected")
    target = require_mapping(change.get("target"), source=f"{source}.target")
    for label, value in (("expected", expected), ("target", target)):
        assert_exact_keys(
            value,
            required={"implementation_status", "verification_status"},
            source=f"{source}.{label}",
        )
    if expected.get("implementation_status") != story_row.get(
        "effective_implementation_status"
    ) or expected.get("verification_status") != story_row.get(
        "effective_verification_status"
    ):
        raise RuntimeError(f"lost update detected for {change.get('story_id')}")
    if story_row.get("effective_implementation_status") not in {
        "NOT_STARTED",
        "IN_PROGRESS",
    }:
        raise RuntimeError(
            "local proposal requires an in-scope NOT_STARTED or IN_PROGRESS Story"
        )
    target_impl = require_string(
        target.get("implementation_status"),
        source=f"{source}.target.implementation_status",
    )
    target_verification = require_string(
        target.get("verification_status"),
        source=f"{source}.target.verification_status",
    )
    if target_impl not in IMPLEMENTATION_CHAIN + NON_CHAIN_IMPLEMENTATION_STATUSES:
        raise RuntimeError(f"unknown implementation status: {target_impl}")
    if target_verification not in VERIFICATION_STATUSES:
        raise RuntimeError(f"unknown verification status: {target_verification}")
    if target_impl not in {"IN_PROGRESS", "IMPLEMENTED_NOT_VALIDATED"}:
        raise RuntimeError(
            "local proposal may target only IN_PROGRESS or IMPLEMENTED_NOT_VALIDATED"
        )
    if target_verification != "NOT_EXECUTED":
        raise RuntimeError("local proposal cannot claim formal verification execution")
    required_suites = story_definition.get("test_suites")
    if not isinstance(required_suites, list) or not all(
        isinstance(item, str) for item in required_suites
    ):
        raise RuntimeError(f"story {change.get('story_id')} has malformed suites")
    evidence_class = (
        "CHANGE_PLAN" if target_impl == "IN_PROGRESS" else "LOCAL_IMPLEMENTATION"
    )
    evidence = validate_evidence_set(
        change.get("evidence"),
        source=f"{source}.evidence",
        story_id=str(change["story_id"]),
        target_verification=target_verification,
        required_suites=required_suites,
        suite_index=suite_index,
        expected_class=evidence_class,
        environment_policy="LOCAL",
        evidence_uri_prefix=evidence_uri_prefix,
        artifact_uri_prefix=artifact_uri_prefix,
        verify_original_artifacts=verify_original_artifacts,
    )
    return {
        "story_id": change["story_id"],
        "expected": dict(expected),
        "target": dict(target),
        "evidence": evidence,
    }


def validate_apply_change(
    change: Mapping[str, Any],
    *,
    story_row: Mapping[str, Any],
    story_definition: Mapping[str, Any],
    suite_index: Mapping[str, Mapping[str, Any]],
    requester: Mapping[str, str],
    source: str,
    evidence_uri_prefix: str = SUITE_EVIDENCE_URI_PREFIX,
    artifact_uri_prefix: str = EVIDENCE_ARTIFACT_URI_PREFIX,
    verify_original_artifacts: bool = False,
) -> tuple[dict[str, Any], str]:
    expected = require_mapping(change.get("expected"), source=f"{source}.expected")
    target = require_mapping(change.get("target"), source=f"{source}.target")
    for label, value in (("expected", expected), ("target", target)):
        assert_exact_keys(
            value,
            required={"implementation_status", "verification_status"},
            source=f"{source}.{label}",
        )
    current_impl = story_row.get("effective_implementation_status")
    current_verification = story_row.get("effective_verification_status")
    if (
        expected.get("implementation_status") != current_impl
        or expected.get("verification_status") != current_verification
    ):
        raise RuntimeError(f"lost update detected for {change.get('story_id')}")
    target_impl = require_string(
        target.get("implementation_status"),
        source=f"{source}.target.implementation_status",
    )
    target_verification = require_string(
        target.get("verification_status"),
        source=f"{source}.target.verification_status",
    )
    if target_impl not in IMPLEMENTATION_CHAIN + NON_CHAIN_IMPLEMENTATION_STATUSES:
        raise RuntimeError(f"unknown or non-transitionable status: {target_impl}")
    if target_verification not in VERIFICATION_STATUSES:
        raise RuntimeError(f"unknown verification status: {target_verification}")
    current_impl_value = require_string(
        current_impl, source=f"{source}.current.implementation_status"
    )
    current_verification_value = require_string(
        current_verification, source=f"{source}.current.verification_status"
    )
    if target_impl == current_impl_value:
        if target_impl not in IMPLEMENTATION_CHAIN:
            raise RuntimeError(
                f"verification-only change is not supported for {target_impl}"
            )
        kind = verification_transition_kind(
            current_verification_value, target_verification
        )
    else:
        kind = implementation_transition_kind(current_impl_value, target_impl)
        if (
            kind == "FORWARD"
            and target_impl != "VALIDATED"
            and target_verification != current_verification_value
        ):
            raise RuntimeError(
                "forward implementation transition cannot silently change verification"
            )
    if target_impl != current_impl_value and (
        target_impl in {"DEPLOYED_STAGING", "DEPLOYED_PRODUCTION"}
        or current_impl_value in {"DEPLOYED_STAGING", "DEPLOYED_PRODUCTION"}
    ):
        raise RuntimeError(
            "deployment status transitions are fail-closed until ST-1505/ST-1506/"
            "ST-1607 typed deployment gates are integrated"
        )
    validate_verification_coupling(
        implementation_status=target_impl,
        verification_status=target_verification,
        implementation_changed=(target_impl != current_impl_value),
        transition_kind=kind,
    )
    if target_impl == "DEFERRED_POST_MVP" and target_verification != "NOT_EXECUTED":
        raise RuntimeError("DEFERRED_POST_MVP requires verification NOT_EXECUTED")
    if target_impl == "OUT_OF_SCOPE" and target_verification != "NOT_APPLICABLE":
        raise RuntimeError("OUT_OF_SCOPE requires verification NOT_APPLICABLE")
    if (
        current_impl_value == "OUT_OF_SCOPE"
        and target_impl != "OUT_OF_SCOPE"
        and target_verification != "NOT_EXECUTED"
    ):
        raise RuntimeError("OUT_OF_SCOPE exit requires verification NOT_EXECUTED")
    if kind == "POST_MVP_ACTIVATION" and target_verification != "NOT_EXECUTED":
        raise RuntimeError("post-MVP activation starts with verification NOT_EXECUTED")
    if (
        target_impl in HIGH_AUTHORITY_TARGETS
        or kind in {"POST_MVP_ACTIVATION", "DEFERRAL", "SCOPE_CHANGE"}
    ) and requester["actor_type"] != "HUMAN":
        raise RuntimeError(f"{target_impl} may only be requested by a human")
    required_suites = story_definition.get("test_suites")
    if not isinstance(required_suites, list) or not all(
        isinstance(item, str) for item in required_suites
    ):
        raise RuntimeError(f"story {change.get('story_id')} has malformed suites")
    evidence_class, environment_policy = evidence_policy_for_target(target_impl, kind)
    allowed_evidence_classes: set[str] | None = None
    if kind == "DEMOTION":
        if target_verification == current_verification_value:
            allowed_evidence_classes = {"ROLLBACK_DECISION"}
        elif target_verification == "NOT_EXECUTED":
            allowed_evidence_classes = {"EXPIRY"}
        elif current_verification_value == "PASS" and target_verification in {
            "PARTIAL",
            "FAIL",
        }:
            allowed_evidence_classes = {"REGRESSION"}
        else:
            raise RuntimeError(
                "implementation demotion may preserve verification with a rollback "
                "decision, reset expired evidence, or record a PASS regression"
            )
    coverage_policy = (
        "NONEMPTY_SUBSET"
        if kind in {"DEMOTION", "REGRESSION", "EXPIRY"}
        or target_verification in {"PARTIAL", "FAIL"}
        else "EXACT"
    )
    evidence = validate_evidence_set(
        change.get("evidence"),
        source=f"{source}.evidence",
        story_id=str(change["story_id"]),
        target_verification=target_verification,
        required_suites=required_suites,
        suite_index=suite_index,
        expected_class=evidence_class,
        environment_policy=environment_policy,
        coverage_policy=coverage_policy,
        evidence_uri_prefix=evidence_uri_prefix,
        artifact_uri_prefix=artifact_uri_prefix,
        allowed_evidence_classes=allowed_evidence_classes,
        verify_original_artifacts=verify_original_artifacts,
    )
    return (
        {
            "story_id": change["story_id"],
            "expected": dict(expected),
            "target": dict(target),
            "evidence": evidence,
        },
        kind,
    )


def validate_request(
    request: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    story_index: Mapping[str, Mapping[str, Any]],
    suite_index: Mapping[str, Mapping[str, Any]],
    require_pr_context: bool = False,
    evidence_uri_prefix: str = SUITE_EVIDENCE_URI_PREFIX,
    artifact_uri_prefix: str = EVIDENCE_ARTIFACT_URI_PREFIX,
    wall_clock_reference: datetime | None = None,
) -> dict[str, Any]:
    if require_pr_context and wall_clock_reference is None:
        wall_clock_reference = current_utc()
    assert_exact_keys(
        request,
        required={
            "document",
            "requested_by",
            "requested_at",
            "reason",
            "expected",
            "changes",
        },
        optional={
            "pr_evidence",
            "approval",
            "production_approval_evidence",
            "scope_decision_evidence",
        },
        source="request",
    )
    document = require_mapping(request.get("document"), source="request.document")
    assert_exact_keys(
        document,
        required={"id", "schema_version", "intent"},
        source="request.document",
    )
    request_id = require_string(document.get("id"), source="request.document.id")
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise RuntimeError(f"invalid request id: {request_id}")
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
    ):
        raise RuntimeError("unsupported status request schema version")
    intent = require_string(document.get("intent"), source="request.document.intent")
    if intent not in {"PROPOSE", "APPLY"}:
        raise RuntimeError(f"unknown request intent: {intent}")
    requester = validate_actor(
        require_mapping(request.get("requested_by"), source="request.requested_by"),
        source="request.requested_by",
    )
    requested_at_text = require_string(
        request.get("requested_at"), source="request.requested_at"
    )
    requested_at = parse_utc_timestamp(requested_at_text, source="request.requested_at")
    if wall_clock_reference is not None and requested_at > wall_clock_reference:
        raise RuntimeError("future timestamp is forbidden in request.requested_at")
    reason = require_string(
        request.get("reason"), source="request.reason", minimum=12, maximum=4096
    )
    expected = require_mapping(request.get("expected"), source="request.expected")
    assert_exact_keys(
        expected,
        required={"canonical_base_sha256", "effective_status_sha256"},
        source="request.expected",
    )
    if expected.get("canonical_base_sha256") != canonical_base_digest():
        raise RuntimeError("request canonical base digest is stale")
    current_effective_digest = effective_status_digest(state)
    if expected.get("effective_status_sha256") != current_effective_digest:
        raise RuntimeError("request effective status digest is stale (lost update)")
    control = transition_control(state)
    if intent == "APPLY" and control["last_decided_at"] is not None:
        last_decided_at = parse_utc_timestamp(
            control["last_decided_at"],
            source="state.transition_control.last_decided_at",
        )
        if requested_at < last_decided_at:
            raise RuntimeError(
                "APPLY requested_at must not precede the prior approval decision"
            )

    story_rows = {
        row["story_id"]: row
        for row in require_list(state.get("stories"), source="state.stories")
    }
    changes = require_list(request.get("changes"), source="request.changes")
    if len(changes) != 1:
        raise RuntimeError("each status request must contain exactly one Story change")
    validated_changes: list[dict[str, Any]] = []
    transition_kinds: list[str] = []
    seen_stories: set[str] = set()
    for position, raw in enumerate(changes):
        source = f"request.changes[{position}]"
        change = require_mapping(raw, source=source)
        assert_exact_keys(
            change,
            required={"story_id", "expected", "target", "evidence"},
            source=source,
        )
        story_id = require_string(change.get("story_id"), source=f"{source}.story_id")
        if not STORY_ID_PATTERN.fullmatch(story_id) or story_id not in story_index:
            raise RuntimeError(f"unknown story in {source}: {story_id}")
        if story_id in seen_stories:
            raise RuntimeError(f"duplicate story change in request: {story_id}")
        seen_stories.add(story_id)
        story_row = story_rows.get(story_id)
        if story_row is None:
            raise RuntimeError(f"effective overlay is missing story row: {story_id}")
        if intent == "PROPOSE":
            validated_changes.append(
                validate_proposal_change(
                    change,
                    story_row=story_row,
                    story_definition=story_index[story_id],
                    suite_index=suite_index,
                    source=source,
                    evidence_uri_prefix=evidence_uri_prefix,
                    artifact_uri_prefix=artifact_uri_prefix,
                    verify_original_artifacts=require_pr_context,
                )
            )
            transition_kinds.append("PROPOSAL_ONLY")
        else:
            validated, kind = validate_apply_change(
                change,
                story_row=story_row,
                story_definition=story_index[story_id],
                suite_index=suite_index,
                requester=requester,
                source=source,
                evidence_uri_prefix=evidence_uri_prefix,
                artifact_uri_prefix=artifact_uri_prefix,
                verify_original_artifacts=require_pr_context,
            )
            validated_changes.append(validated)
            transition_kinds.append(kind)

    for change in validated_changes:
        for position, evidence in enumerate(change["evidence"]):
            observed_at = parse_utc_timestamp(
                evidence["observed_at"],
                source=(
                    f"request change {change['story_id']} "
                    f"evidence[{position}].observed_at"
                ),
            )
            if observed_at > requested_at:
                raise RuntimeError("status evidence cannot postdate requested_at")
            require_evidence_fresh_at(
                evidence,
                reference=requested_at,
                source=f"request change {change['story_id']} evidence[{position}]",
            )
            if wall_clock_reference is not None:
                require_evidence_fresh_at(
                    evidence,
                    reference=wall_clock_reference,
                    source=(
                        f"live request change {change['story_id']} evidence[{position}]"
                    ),
                )

    if intent == "APPLY":
        consumed = set(control["consumed_evidence_identities"])
        request_digests = evidence_identity_digests(validated_changes)
        reused = sorted(request_digests & consumed)
        if reused:
            raise RuntimeError(
                f"APPLY cannot reuse a consumed evidence snapshot: {reused}"
            )
        watermarks = control["story_invalidation_watermarks"]
        active_evidence = control["story_active_evidence_sha256"]
        active_observations = control["story_active_evidence_observed_at"]
        active_validity = control["story_active_evidence_valid_until"]
        for change, transition_kind in zip(validated_changes, transition_kinds):
            story_id = str(change["story_id"])
            active_observed_text = active_observations.get(story_id)
            if active_observed_text is not None:
                active_observed_at = parse_utc_timestamp(
                    active_observed_text,
                    source=f"active Story evidence {story_id} observation watermark",
                )
                for evidence in change["evidence"]:
                    observed_at = parse_utc_timestamp(
                        evidence["observed_at"],
                        source=f"Story {story_id} status-changing evidence",
                    )
                    if observed_at <= active_observed_at:
                        raise RuntimeError(
                            "status-changing evidence must postdate the active "
                            f"evidence observation for {story_id}"
                        )
            expiry_entries = [
                evidence
                for evidence in change["evidence"]
                if evidence["evidence_class"] == "EXPIRY"
            ]
            if transition_kind == "EXPIRY" or expiry_entries:
                expected_invalidations = set(active_evidence.get(story_id, []))
                actual_invalidations = {
                    str(digest)
                    for evidence in expiry_entries
                    for digest in evidence["invalidates_evidence_sha256"]
                }
                if (
                    not expected_invalidations
                    or actual_invalidations != expected_invalidations
                ):
                    raise RuntimeError(
                        "EXPIRY evidence must identify the exact active evidence set"
                    )
                validity_text = active_validity.get(story_id)
                if validity_text is None:
                    raise RuntimeError(
                        "active evidence has no immutable valid_until for EXPIRY"
                    )
                validity = parse_utc_timestamp(
                    validity_text, source=f"active Story evidence {story_id} validity"
                )
                if requested_at < validity:
                    raise RuntimeError(
                        "EXPIRY transition predates active evidence expiry"
                    )
                for evidence in expiry_entries:
                    expiry_observed_at = parse_utc_timestamp(
                        evidence["observed_at"],
                        source=f"Story {story_id} EXPIRY evidence",
                    )
                    if expiry_observed_at < validity:
                        raise RuntimeError(
                            "EXPIRY evidence observation predates active evidence expiry"
                        )
            watermark_text = watermarks.get(story_id)
            if watermark_text is None:
                continue
            watermark = parse_utc_timestamp(
                watermark_text,
                source=f"Story {story_id} invalidation watermark",
            )
            for evidence in change["evidence"]:
                observed_at = parse_utc_timestamp(
                    evidence["observed_at"],
                    source=f"Story {story_id} post-invalidation evidence",
                )
                if observed_at <= watermark:
                    raise RuntimeError(
                        "status-changing evidence must postdate the latest "
                        f"applied approval decision for {story_id}"
                    )

    result: dict[str, Any] = {
        "document": dict(document),
        "requested_by": requester,
        "requested_at": requested_at_text,
        "reason": reason,
        "expected": dict(expected),
        "changes": validated_changes,
        "transition_kinds": transition_kinds,
    }
    if intent == "PROPOSE":
        if any(
            field in request
            for field in (
                "pr_evidence",
                "approval",
                "production_approval_evidence",
                "scope_decision_evidence",
            )
        ):
            raise RuntimeError(
                "PROPOSE must not contain PR, approval, production, or scope "
                "governance evidence"
            )
    else:
        if "pr_evidence" not in request or "approval" not in request:
            raise RuntimeError("APPLY requires PR evidence and human approval")
        result["pr_evidence"] = validate_pr_evidence(
            require_mapping(request.get("pr_evidence"), source="request.pr_evidence"),
            require_context=require_pr_context,
        )
        pr_observed_at = parse_utc_timestamp(
            result["pr_evidence"]["observed_at"],
            source="request.pr_evidence.observed_at",
        )
        if pr_observed_at > requested_at:
            raise RuntimeError("PR evidence cannot postdate requested_at")
        require_evidence_fresh_at(
            result["pr_evidence"],
            reference=requested_at,
            source="request.pr_evidence",
        )
        if wall_clock_reference is not None:
            require_evidence_fresh_at(
                result["pr_evidence"],
                reference=wall_clock_reference,
                source="live request.pr_evidence",
            )
        result["approval"] = validate_approval(
            require_mapping(request.get("approval"), source="request.approval"),
            requester=requester,
            requested_at=requested_at,
            artifact_uri_prefix=artifact_uri_prefix,
        )
        approval_decided_at = parse_utc_timestamp(
            result["approval"]["decided_at"], source="request.approval.decided_at"
        )
        if (
            wall_clock_reference is not None
            and approval_decided_at > wall_clock_reference
        ):
            raise RuntimeError(
                "future timestamp is forbidden in request.approval.decided_at"
            )
        if wall_clock_reference is not None:
            require_evidence_fresh_at(
                result["approval"]["evidence"],
                reference=wall_clock_reference,
                source="live request.approval.evidence",
            )
        for change in validated_changes:
            for position, evidence in enumerate(change["evidence"]):
                require_evidence_fresh_at(
                    evidence,
                    reference=approval_decided_at,
                    source=(
                        f"approved request change {change['story_id']} "
                        f"evidence[{position}]"
                    ),
                )
        require_evidence_fresh_at(
            result["pr_evidence"],
            reference=approval_decided_at,
            source="approved request.pr_evidence",
        )
        production_target = any(
            change["expected"]["implementation_status"] != "DEPLOYED_PRODUCTION"
            and change["target"]["implementation_status"] == "DEPLOYED_PRODUCTION"
            for change in validated_changes
        )
        if production_target:
            if "production_approval_evidence" not in request:
                raise RuntimeError(
                    "production transition requires Release Decision, Gate, Security, "
                    "and Operations approval evidence"
                )
            result["production_approval_evidence"] = (
                validate_production_approval_evidence(
                    require_mapping(
                        request.get("production_approval_evidence"),
                        source="request.production_approval_evidence",
                    ),
                    artifact_uri_prefix=artifact_uri_prefix,
                )
            )
            for name, evidence in result["production_approval_evidence"].items():
                observed_at = parse_utc_timestamp(
                    evidence["observed_at"],
                    source=(f"request.production_approval_evidence.{name}.observed_at"),
                )
                if observed_at > approval_decided_at:
                    raise RuntimeError(
                        "production governance evidence cannot postdate approval"
                    )
                require_evidence_fresh_at(
                    evidence,
                    reference=approval_decided_at,
                    source=f"request.production_approval_evidence.{name}",
                )
                if wall_clock_reference is not None:
                    require_evidence_fresh_at(
                        evidence,
                        reference=wall_clock_reference,
                        source=f"live production approval evidence {name}",
                    )
        elif "production_approval_evidence" in request:
            raise RuntimeError(
                "production approval evidence is forbidden for non-production transitions"
            )
        scope_transition = any(
            kind in {"POST_MVP_ACTIVATION", "DEFERRAL", "SCOPE_CHANGE"}
            for kind in transition_kinds
        )
        if scope_transition:
            if "scope_decision_evidence" not in request:
                raise RuntimeError(
                    "deferred/out-of-scope transition requires a scope decision artifact"
                )
            result["scope_decision_evidence"] = validate_repo_evidence(
                require_mapping(
                    request.get("scope_decision_evidence"),
                    source="request.scope_decision_evidence",
                ),
                source="request.scope_decision_evidence",
                required_suite=False,
                immutable_artifact_prefix=artifact_uri_prefix,
            )
            scope_observed_at = parse_utc_timestamp(
                result["scope_decision_evidence"]["observed_at"],
                source="request.scope_decision_evidence.observed_at",
            )
            if scope_observed_at > requested_at:
                raise RuntimeError(
                    "scope decision evidence cannot postdate requested_at"
                )
            require_evidence_fresh_at(
                result["scope_decision_evidence"],
                reference=requested_at,
                source="request.scope_decision_evidence",
            )
            require_evidence_fresh_at(
                result["scope_decision_evidence"],
                reference=approval_decided_at,
                source="approved request.scope_decision_evidence",
            )
            if (
                result["scope_decision_evidence"]["sha256"]
                == result["approval"]["evidence"]["sha256"]
            ):
                raise RuntimeError(
                    "scope decision evidence must be separate from approval evidence"
                )
            if wall_clock_reference is not None:
                require_evidence_fresh_at(
                    result["scope_decision_evidence"],
                    reference=wall_clock_reference,
                    source="live request.scope_decision_evidence",
                )
        elif "scope_decision_evidence" in request:
            raise RuntimeError(
                "scope decision evidence is forbidden for ordinary transitions"
            )
        reused = sorted(
            request_evidence_identity_digests(result)
            & set(control["consumed_evidence_identities"])
        )
        if reused:
            raise RuntimeError(
                f"APPLY cannot reuse consumed evidence identities: {reused}"
            )
    return result


def apply_validated_request(state: dict[str, Any], request: Mapping[str, Any]) -> None:
    request_id = request["document"]["id"]
    intent = request["document"]["intent"]
    story_rows = {row["story_id"]: row for row in state["stories"]}
    if intent == "PROPOSE":
        for change in request["changes"]:
            row = story_rows[change["story_id"]]
            row["proposal_request_ids"].append(request_id)
        state["proposals"].append(
            {
                "request_id": request_id,
                "requested_by": request["requested_by"],
                "requested_at": request["requested_at"],
                "reason": request["reason"],
                "outcome": "PENDING_PR_EVIDENCE_AND_APPLY_REQUEST",
                "changes": request["changes"],
            }
        )
        return

    before = effective_status_digest(state)
    control = transition_control(state)
    changes = require_list(request.get("changes"), source="validated request.changes")
    transition_kinds = require_list(
        request.get("transition_kinds"), source="validated request.transition_kinds"
    )
    if len(changes) != len(transition_kinds):
        raise RuntimeError("validated transition kind inventory is malformed")
    for change in changes:
        row = story_rows[change["story_id"]]
        row["effective_implementation_status"] = change["target"][
            "implementation_status"
        ]
        row["effective_verification_status"] = change["target"]["verification_status"]
    consumed = set(control["consumed_evidence_identities"])
    consumed.update(request_evidence_identity_digests(request))
    control["consumed_evidence_identities"] = sorted(consumed)
    watermarks = control["story_invalidation_watermarks"]
    active_evidence = control["story_active_evidence_sha256"]
    active_observations = control["story_active_evidence_observed_at"]
    active_validity = control["story_active_evidence_valid_until"]
    for change, kind in zip(changes, transition_kinds):
        before_implementation = change["expected"]["implementation_status"]
        after_implementation = change["target"]["implementation_status"]
        before_verification = change["expected"]["verification_status"]
        after_verification = change["target"]["verification_status"]
        if (
            before_implementation != after_implementation
            or before_verification != after_verification
        ):
            watermarks[change["story_id"]] = request["approval"]["decided_at"]
        classes = {str(item["evidence_class"]) for item in change["evidence"]}
        story_id = str(change["story_id"])
        if after_verification in {"NOT_EXECUTED", "NOT_APPLICABLE"}:
            active_evidence.pop(story_id, None)
            active_observations.pop(story_id, None)
            active_validity.pop(story_id, None)
        elif classes & {"RUNTIME_SUITE_RESULT", "REGRESSION"}:
            active_evidence[story_id] = sorted(
                {str(item["sha256"]) for item in change["evidence"]}
            )
            active_observations[story_id] = max(
                (str(item["observed_at"]) for item in change["evidence"]),
                key=lambda value: parse_utc_timestamp(
                    value, source=f"Story {story_id} evidence observation"
                ),
            )
            valid_until_values = [
                str(item["expires_at"])
                for item in change["evidence"]
                if "expires_at" in item
            ]
            if valid_until_values:
                active_validity[story_id] = min(
                    valid_until_values,
                    key=lambda value: parse_utc_timestamp(
                        value, source=f"Story {story_id} evidence validity"
                    ),
                )
            else:
                active_validity.pop(story_id, None)
    sequence = int(control["sequence"]) + 1
    previous_head = str(control["history_head_sha256"])
    head_payload: dict[str, Any] = {
        "sequence": sequence,
        "previous_history_head_sha256": previous_head,
        "request_id": request_id,
        "requested_at": request["requested_at"],
        "approval_decided_at": request["approval"]["decided_at"],
        "request_sha256": object_digest(request),
    }
    history_head = object_digest(head_payload)
    control["sequence"] = sequence
    control["history_head_sha256"] = history_head
    control["last_requested_at"] = request["requested_at"]
    control["last_decided_at"] = request["approval"]["decided_at"]
    after = effective_status_digest(state)
    history = {
        "request_id": request_id,
        "sequence": sequence,
        "previous_history_head_sha256": previous_head,
        "history_head_sha256": history_head,
        "before_effective_status_sha256": before,
        "after_effective_status_sha256": after,
        "requested_by": request["requested_by"],
        "requested_at": request["requested_at"],
        "approval": request["approval"],
        "pr_evidence": request["pr_evidence"],
        "transition_kinds": transition_kinds,
        "changes": changes,
    }
    if "production_approval_evidence" in request:
        history["production_approval_evidence"] = request[
            "production_approval_evidence"
        ]
    if "scope_decision_evidence" in request:
        history["scope_decision_evidence"] = request["scope_decision_evidence"]
    state["applied_transitions"].append(history)


def request_files() -> list[Path]:
    if REQUESTS_ROOT.is_symlink() or not REQUESTS_ROOT.is_dir():
        raise RuntimeError(
            f"status request source directory is missing: {REQUESTS_ROOT}"
        )
    files = sorted(REQUESTS_ROOT.glob("*.yaml"))
    if not files:
        raise RuntimeError("at least one status proposal/request is required")
    for path in REQUESTS_ROOT.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix != ".yaml":
            raise RuntimeError(f"unexpected request source artifact: {path}")
    for sequence, path in enumerate(files, start=1):
        expected_prefix = f"{sequence:04d}-"
        if not path.name.startswith(expected_prefix) or len(path.stem) <= len(
            expected_prefix
        ):
            raise RuntimeError(
                "status request filenames must be contiguous append-only sequence "
                f"1..N; expected {expected_prefix}*, got {path.name}"
            )
    return files


def evidence_files() -> list[Path]:
    if EVIDENCE_ROOT.is_symlink() or not EVIDENCE_ROOT.is_dir():
        raise RuntimeError(
            f"status evidence source directory is missing: {EVIDENCE_ROOT}"
        )
    files = sorted(EVIDENCE_ROOT.glob("*.yaml"))
    if not files:
        raise RuntimeError(
            "at least one append-only status evidence snapshot is required"
        )
    seen_document_ids: set[str] = set()
    for path in EVIDENCE_ROOT.iterdir():
        if path == EVIDENCE_ARTIFACTS_ROOT:
            if path.is_symlink() or not path.is_dir():
                raise RuntimeError(f"unsafe evidence artifact store: {path}")
            continue
        if path.is_symlink() or not path.is_file() or path.suffix != ".yaml":
            raise RuntimeError(f"unexpected evidence source artifact: {path}")
        snapshot = validate_evidence_snapshot(path)
        document_id = str(snapshot["document"]["id"])
        if document_id in seen_document_ids:
            raise RuntimeError(
                f"duplicate evidence snapshot document id: {document_id}"
            )
        seen_document_ids.add(document_id)
    return files


def evidence_artifact_files() -> list[Path]:
    if EVIDENCE_ARTIFACTS_ROOT.is_symlink() or not EVIDENCE_ARTIFACTS_ROOT.is_dir():
        raise RuntimeError(
            f"status evidence artifact store is missing: {EVIDENCE_ARTIFACTS_ROOT}"
        )
    files = sorted(EVIDENCE_ARTIFACTS_ROOT.iterdir())
    if not files:
        raise RuntimeError(
            "at least one content-addressed evidence artifact is required"
        )
    seen_digests: dict[str, Path] = {}
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"unexpected evidence artifact store entry: {path}")
        digest = path.name.split("-", 1)[0]
        if not SHA256_PATTERN.fullmatch(digest) or sha256_file(path) != digest:
            raise RuntimeError(f"evidence artifact is not content-addressed: {path}")
        if digest in seen_digests:
            raise RuntimeError(
                "duplicate content-addressed evidence artifact digest: "
                f"{seen_digests[digest]} and {path}"
            )
        seen_digests[digest] = path
    return files


def snapshot_artifact_paths(
    snapshot_paths: Iterable[Path], *, known_suite_ids: set[str]
) -> set[str]:
    referenced: set[str] = set()
    for path in snapshot_paths:
        snapshot = validate_evidence_snapshot(path, known_suite_ids=known_suite_ids)
        for artifact in snapshot["source_artifacts"]:
            referenced.add(str(artifact["artifact_uri"]).removeprefix("repo://"))
    return referenced


def suite_evidence_paths(request: Mapping[str, Any]) -> set[str]:
    """Return the append-only snapshots referenced by validated Story changes."""

    paths: set[str] = set()
    for change in require_list(request.get("changes"), source="request.changes"):
        change_mapping = require_mapping(change, source="request.changes[]")
        for evidence in require_list(
            change_mapping.get("evidence"), source="request.changes[].evidence"
        ):
            evidence_mapping = require_mapping(
                evidence, source="request.changes[].evidence[]"
            )
            uri = require_string(
                evidence_mapping.get("uri"),
                source="request.changes[].evidence[].uri",
            )
            if not uri.startswith(f"repo://{SUITE_EVIDENCE_URI_PREFIX}"):
                raise RuntimeError("validated Suite evidence escaped its source prefix")
            paths.add(uri.removeprefix("repo://"))
    return paths


def governance_artifact_paths(request: Mapping[str, Any]) -> set[str]:
    paths: set[str] = set()
    approval = request.get("approval")
    if isinstance(approval, dict) and isinstance(approval.get("evidence"), dict):
        paths.add(str(approval["evidence"]["uri"]).removeprefix("repo://"))
    production = request.get("production_approval_evidence")
    if isinstance(production, dict):
        paths.update(
            str(item["uri"]).removeprefix("repo://")
            for item in production.values()
            if isinstance(item, dict) and "uri" in item
        )
    scope = request.get("scope_decision_evidence")
    if isinstance(scope, dict) and "uri" in scope:
        paths.add(str(scope["uri"]).removeprefix("repo://"))
    return paths


def build_overlay(*, live_request: Path | None = None) -> dict[str, Any]:
    registry, story_document, suite_document, taxonomy = canonical_inputs()
    story_index = index_records(
        story_document, collection="stories", source="canonical story catalog"
    )
    suite_index = index_records(
        suite_document, collection="suites", source="canonical suite catalog"
    )
    state = initial_effective_state(registry, story_document, suite_document)
    state["proposals"] = []
    state["applied_transitions"] = []
    seen_request_ids: set[str] = set()
    request_inventory: list[dict[str, Any]] = []
    referenced_evidence: set[str] = set()
    referenced_governance_artifacts: set[str] = set()
    committed_requests = request_files()
    live_resolved = live_request.resolve() if live_request is not None else None
    if live_resolved is not None and live_resolved not in {
        path.resolve() for path in committed_requests
    }:
        raise RuntimeError("live request must be a committed ST-0005 request file")
    for path in committed_requests:
        request = load_yaml(path)
        validated = validate_request(
            request,
            state=state,
            story_index=story_index,
            suite_index=suite_index,
            require_pr_context=(live_resolved == path.resolve()),
        )
        request_id = validated["document"]["id"]
        if request_id in seen_request_ids:
            raise RuntimeError(f"duplicate status request id: {request_id}")
        seen_request_ids.add(request_id)
        referenced_evidence.update(suite_evidence_paths(validated))
        referenced_governance_artifacts.update(governance_artifact_paths(validated))
        apply_validated_request(state, validated)
        request_inventory.append(
            {
                "request_id": request_id,
                "path": relative_repo_path(path),
                "sha256": sha256_file(path),
                "intent": validated["document"]["intent"],
            }
        )

    committed_evidence = {relative_repo_path(path) for path in evidence_files()}
    if referenced_evidence != committed_evidence:
        raise RuntimeError(
            "append-only evidence inventory mismatch: "
            f"orphan={sorted(committed_evidence - referenced_evidence)}, "
            f"untracked={sorted(referenced_evidence - committed_evidence)}"
        )
    referenced_artifacts = (
        snapshot_artifact_paths(evidence_files(), known_suite_ids=set(suite_index))
        | referenced_governance_artifacts
    )
    committed_artifacts = {
        relative_repo_path(path) for path in evidence_artifact_files()
    }
    if referenced_artifacts != committed_artifacts:
        raise RuntimeError(
            "content-addressed evidence artifact inventory mismatch: "
            f"orphan={sorted(committed_artifacts - referenced_artifacts)}, "
            f"untracked={sorted(referenced_artifacts - committed_artifacts)}"
        )

    implementation_statuses = taxonomy.get("implementation_status")
    verification_statuses = taxonomy.get("verification_status")
    if not isinstance(implementation_statuses, dict) or not isinstance(
        verification_statuses, dict
    ):
        raise RuntimeError("canonical status taxonomy is malformed")
    known_implementation = set(implementation_statuses)
    if known_implementation != set(IMPLEMENTATION_CHAIN) | set(
        NON_CHAIN_IMPLEMENTATION_STATUSES
    ):
        raise RuntimeError(
            "implementation status policy differs from canonical taxonomy"
        )
    if set(verification_statuses) != set(VERIFICATION_STATUSES):
        raise RuntimeError("verification status policy differs from canonical taxonomy")

    return {
        "document": {
            "id": REVISION_ID,
            "version": REVISION_VERSION,
            "story_id": "ST-0005",
            "status": "IMPLEMENTATION_CANDIDATE",
            "generated_by": GENERATOR_PATH,
        },
        "base": {
            "canonical_version": "1.0",
            "canonical_base_sha256": canonical_base_digest(),
            "pinned_inputs": [
                {"path": path, "sha256": digest}
                for path, digest in sorted(PINNED_INPUT_HASHES.items())
            ],
            "effective_status_sha256": effective_status_digest(state),
        },
        "policy": {
            "canonical_source_rows_and_files_are_immutable": True,
            "effective_status_fields_change_only_via_apply": True,
            "one_story_change_per_request": True,
            "proposal_never_changes_effective_status": True,
            "proposal_governance_fields": "FORBIDDEN",
            "proposal_sources": ["NOT_STARTED", "IN_PROGRESS"],
            "proposal_targets": ["IN_PROGRESS", "IMPLEMENTED_NOT_VALIDATED"],
            "proposal_verification_status": "NOT_EXECUTED",
            "apply_requires_pr_evidence": True,
            "apply_requires_distinct_human_approval": True,
            "authoritative_live_apply": "BLOCKED_PENDING_GOVERNANCE",
            "currently_executable_live_apply_transitions": [],
            "live_apply_activation_requires": list(LIVE_APPLY_ACTIVATION_PREREQUISITES),
            "deployment_apply_activation_additionally_requires": list(
                DEPLOYMENT_APPLY_ACTIVATION_PREREQUISITES
            ),
            "deployment_transition_pairs_in_offline_grammar": True,
            "implementation_transitions_involving_deployed_statuses": (
                "BLOCKED_PENDING_TYPED_GATES"
            ),
            "validated_and_production_requester_human_only": True,
            "scope_transition_requires_human_requester": True,
            "scope_transition_requires_pr": True,
            "scope_transition_requires_distinct_human_approver": True,
            "scope_transition_requires_separate_scope_authority_artifact": True,
            "scope_verification_status_coupling": {
                "DEFERRED_POST_MVP": "NOT_EXECUTED",
                "OUT_OF_SCOPE": "NOT_APPLICABLE",
                "OUT_OF_SCOPE_EXIT": "NOT_EXECUTED",
            },
            "formal_suite_pass_without_runtime_evidence": "FORBIDDEN",
            "verification_pass_requires_implementation_status": [
                "VALIDATED",
                "DEPLOYED_STAGING",
                "DEPLOYED_PRODUCTION",
            ],
            "forward_validated_promotion_requires_verification": "PASS",
            "forward_deployment_promotion_requires_verification": "PASS",
            "verification_only_transition_does_not_change_implementation": True,
            "snapshot_binding_story_class_suite_environment_result_time_formal": (
                "REQUIRED"
            ),
            "snapshot_content_addressed_capture_path_and_sha": "REQUIRED",
            "content_addressed_capture_digest_uniqueness": "ONE_FILE_PER_SHA256",
            "status_evidence_atomic_identity_fields": [
                "story_id",
                "suite_id",
                "evidence_class",
                "source_capture_sha256",
            ],
            "apply_status_evidence_atomic_identity_single_use": True,
            "apply_evidence_identity_scopes": {
                "status": "STORY_SUITE_CLASS_CAPTURE",
                "pull_request_uri": "GLOBAL",
                "pull_request_changeset": "GLOBAL",
                "approval_artifact": "GLOBAL",
                "production_governance_artifact": (
                    "STORY_GOVERNANCE_ROLE_AND_ARTIFACT_SHA256"
                ),
                "scope_decision_artifact": "STORY_AND_ARTIFACT_SHA256",
            },
            "new_live_snapshot_original_path_and_sha": "REQUIRED",
            "offline_replay_uses_committed_capture": True,
            "apply_status_evidence_must_postdate_active_observation": True,
            "apply_status_evidence_must_postdate_latest_applied_approval": True,
            "apply_evidence_valid_through_approval_decision": True,
            "expires_at_strictly_after_observed_at": True,
            "approval_decided_at_not_before_requested_at": True,
            "apply_requested_at_not_before_prior_approval_decision": True,
            "offline_replay_wall_clock_independent": True,
            "live_future_request_observation_or_decision_timestamps": "REJECT",
            "evidence_expired_at_request_approval_or_live_reference": "REJECT",
            "explicit_null_temporal_or_governance_fields": "REJECT",
            "change_pr_scope_evidence_postdating_request": "REJECT",
            "approval_or_production_evidence_postdating_decision": "REJECT",
            "pull_request_uri_single_use": True,
            "approval_artifact_single_use": True,
            "production_governance_identity_scope": (
                "STORY_GOVERNANCE_ROLE_AND_ARTIFACT_SHA256"
            ),
            "scope_decision_identity_scope": "STORY_AND_ARTIFACT_SHA256",
            "production_and_scope_artifact_cross_story_reuse": "ALLOWED",
            "scope_decision_separate_from_approval": True,
            "expiry_invalidates_evidence": "EXACT_ACTIVE_SET",
            "expiry_requested_at_and_observed_at_must_be_at_or_after_active_valid_until": (
                True
            ),
            "verification_evidence_coverage": {
                "PASS": "EXACT_REQUIRED_SUITE_SET",
                "PARTIAL": "NONEMPTY_REQUIRED_SUITE_SUBSET",
                "FAIL": "NONEMPTY_REQUIRED_SUITE_SUBSET",
                "REGRESSION": "NONEMPTY_REQUIRED_SUITE_SUBSET",
                "EXPIRY": "NONEMPTY_REQUIRED_SUITE_SUBSET",
                "DEMOTION": "NONEMPTY_REQUIRED_SUITE_SUBSET",
            },
            "verification_aggregate_result_contract": {
                "PASS": "ALL_REQUIRED_SUITES_PASS",
                "PARTIAL": "NO_FAIL_AND_INCOMPLETE_OR_AT_LEAST_ONE_PARTIAL",
                "FAIL": "AT_LEAST_ONE_FAIL",
            },
            "production_governance_artifacts": [
                "release_decision",
                "gate_report",
                "security_approval",
                "operations_approval",
            ],
            "production_governance_artifacts_must_be_distinct": True,
            "orphan_evidence_snapshot": "REJECT",
            "unknown_story_suite_status_field": "REJECT",
            "lost_update": "REJECT",
            "local_evidence_environment": "LOCAL_NON_CANONICAL_NON_RUNTIME",
        },
        "request_inventory": request_inventory,
        "counts": {
            "story_rows": len(state["stories"]),
            "test_suite_rows": len(state["test_suites"]),
            "environment_rows": len(state["environments"]),
            "proposal_requests": len(state["proposals"]),
            "applied_requests": len(state["applied_transitions"]),
        },
        **state,
    }


def build_policy() -> dict[str, Any]:
    return {
        "document": {
            "id": "RAOS-STATUS-TRANSITION-POLICY-001",
            "version": REVISION_VERSION,
            "status": "IMPLEMENTATION_CANDIDATE",
        },
        "canonical_taxonomy": "RAOS-STATUS-TAXONOMY-001@1.0",
        "implementation": {
            "canonical_source_rows_and_files_are_immutable": True,
            "effective_status_fields_change_only_via_apply": True,
            "one_story_change_per_request": True,
            "structurally_adjacent_forward_pairs": [
                {"from": source, "to": target}
                for source, target in sorted(FORWARD_TRANSITIONS)
            ],
            "structurally_adjacent_demotion_pairs": [
                {"from": source, "to": target}
                for source, target in sorted(DEMOTION_TRANSITIONS)
            ],
            "proposal_targets": ["IN_PROGRESS", "IMPLEMENTED_NOT_VALIDATED"],
            "proposal_sources": ["NOT_STARTED", "IN_PROGRESS"],
            "proposal_verification_status": "NOT_EXECUTED",
            "scope_transitions": [
                {"from": source, "to": target, "kind": kind}
                for (source, target), kind in sorted(SPECIAL_SCOPE_TRANSITIONS.items())
            ],
            "deployment_transition_pairs_in_offline_grammar": True,
            "implementation_transitions_involving_deployed_statuses": (
                "BLOCKED_PENDING_TYPED_GATES"
            ),
            "forward_validated_promotion_requires_verification": "PASS",
            "forward_deployment_promotion_requires_verification": "PASS",
            "verification_only_transition_does_not_change_implementation": True,
            "verification_pass_requires_implementation_status": [
                "VALIDATED",
                "DEPLOYED_STAGING",
                "DEPLOYED_PRODUCTION",
            ],
            "scope_verification_status_coupling": {
                "DEFERRED_POST_MVP": "NOT_EXECUTED",
                "OUT_OF_SCOPE": "NOT_APPLICABLE",
                "OUT_OF_SCOPE_EXIT": "NOT_EXECUTED",
            },
            "verification_only_transition_matrix": [
                {"from": source, "to": target, "kind": kind}
                for (source, target), kind in sorted(
                    VERIFICATION_ONLY_TRANSITIONS.items()
                )
            ],
        },
        "demotion": {
            "human_approval_required": True,
            "preserved_verification_requires_rollback_decision": True,
            "pass_to_partial_or_fail_requires_regression": True,
            "ordinary_verification_reset_to_not_executed_requires_expiry": True,
            "scope_exit_reset_to_not_executed_requires_scope_decision": True,
            "effective_history_is_append_only": True,
        },
        "authority": {
            "all_apply_requests_require_pr": True,
            "all_apply_requests_require_distinct_human_approver": True,
            "authoritative_live_apply": "BLOCKED_PENDING_GOVERNANCE",
            "currently_executable_live_apply_transitions": [],
            "live_apply_activation_requires": list(LIVE_APPLY_ACTIVATION_PREREQUISITES),
            "deployment_apply_activation_additionally_requires": list(
                DEPLOYMENT_APPLY_ACTIVATION_PREREQUISITES
            ),
            "human_requester_required_for": sorted(HIGH_AUTHORITY_TARGETS),
            "scope_transition_requires_human_requester": True,
            "scope_transition_requires_pr": True,
            "scope_transition_requires_distinct_human_approver": True,
            "scope_transition_requires_separate_scope_authority_artifact": True,
            "automation_cannot_approve": True,
            "requester_cannot_self_approve": True,
            "production_governance_artifacts": [
                "release_decision",
                "gate_report",
                "security_approval",
                "operations_approval",
            ],
            "production_governance_artifacts_must_be_distinct": True,
        },
        "proposal": {
            "changes_effective_status": False,
            "governance_fields": "FORBIDDEN",
            "implementation_sources": ["NOT_STARTED", "IN_PROGRESS"],
            "implementation_targets": [
                "IN_PROGRESS",
                "IMPLEMENTED_NOT_VALIDATED",
            ],
            "verification_status": "NOT_EXECUTED",
        },
        "verification": {
            "verification_only_transitions_preserve_implementation_status": True,
            "evidence_coverage": {
                "PASS": "EXACT_REQUIRED_SUITE_SET",
                "PARTIAL": "NONEMPTY_REQUIRED_SUITE_SUBSET",
                "FAIL": "NONEMPTY_REQUIRED_SUITE_SUBSET",
                "REGRESSION": "NONEMPTY_REQUIRED_SUITE_SUBSET",
                "EXPIRY": "NONEMPTY_REQUIRED_SUITE_SUBSET",
                "DEMOTION": "NONEMPTY_REQUIRED_SUITE_SUBSET",
            },
            "aggregate_result_contract": {
                "PASS": "ALL_REQUIRED_SUITES_PASS",
                "PARTIAL": "NO_FAIL_AND_INCOMPLETE_OR_AT_LEAST_ONE_PARTIAL",
                "FAIL": "AT_LEAST_ONE_FAIL",
            },
        },
        "history": {
            "request_and_evidence_sources": "APPEND_ONLY",
            "existing_source_modify_delete_rename": (
                "FORBIDDEN_BY_BASE_OWNED_PR_WORKFLOW"
            ),
            "append_only_modify_delete_rename_enforcement": ("BASE_OWNED_PR_WORKFLOW"),
            "correction_method": "NEW_EVIDENCE_AND_NEW_REQUEST",
            "suite_evidence_uri_prefix": "repo://changes/st-0005/evidence/",
            "snapshot_binding_fields": [
                "story_id",
                "evidence_class",
                "suite_id",
                "environment",
                "result",
                "recorded_at",
                "formal_suite_status",
            ],
            "snapshot_content_addressed_capture_path_and_sha": "REQUIRED",
            "content_addressed_capture_digest_uniqueness": "ONE_FILE_PER_SHA256",
            "status_evidence_atomic_identity_fields": [
                "story_id",
                "suite_id",
                "evidence_class",
                "source_capture_sha256",
            ],
            "apply_status_evidence_atomic_identity_single_use": True,
            "apply_evidence_identity_scopes": {
                "status": "STORY_SUITE_CLASS_CAPTURE",
                "pull_request_uri": "GLOBAL",
                "pull_request_changeset": "GLOBAL",
                "approval_artifact": "GLOBAL",
                "production_governance_artifact": (
                    "STORY_GOVERNANCE_ROLE_AND_ARTIFACT_SHA256"
                ),
                "scope_decision_artifact": "STORY_AND_ARTIFACT_SHA256",
            },
            "new_live_snapshot_original_path_and_sha": "REQUIRED",
            "offline_replay_uses_committed_capture": True,
            "apply_status_evidence_must_postdate_active_observation": True,
            "apply_status_evidence_must_postdate_latest_applied_approval": True,
            "apply_evidence_valid_through_approval_decision": True,
            "expires_at_strictly_after_observed_at": True,
            "approval_decided_at_not_before_requested_at": True,
            "apply_requested_at_not_before_prior_approval_decision": True,
            "pull_request_uri_single_use": True,
            "approval_artifact_single_use": True,
            "production_governance_identity_scope": (
                "STORY_GOVERNANCE_ROLE_AND_ARTIFACT_SHA256"
            ),
            "scope_decision_identity_scope": "STORY_AND_ARTIFACT_SHA256",
            "production_and_scope_artifact_cross_story_reuse": "ALLOWED",
            "scope_decision_separate_from_approval": True,
            "expiry_invalidates_evidence": "EXACT_ACTIVE_SET",
            "expiry_requested_at_and_observed_at_must_be_at_or_after_active_valid_until": (
                True
            ),
            "unreferenced_snapshot": "REJECT",
            "requested_observed_expires_decided_timestamps": "STRICT_UTC_RFC3339",
            "explicit_null_temporal_or_governance_fields": "REJECT",
            "change_pr_scope_evidence_postdating_request": "REJECT",
            "approval_or_production_evidence_postdating_decision": "REJECT",
            "evidence_expired_at_request_approval_or_live_reference": "REJECT",
            "offline_replay_wall_clock_independent": True,
            "live_future_request_observation_or_decision_timestamps": "REJECT",
        },
        "evidence_classes": {
            "CHANGE_PLAN": {
                "environment_contract": "LOCAL",
                "allowed_results": ["PLANNED"],
                "formal_suite_status_contract": "NOT_EXECUTED",
            },
            "LOCAL_IMPLEMENTATION": {
                "environment_contract": "LOCAL",
                "allowed_results": ["LOCAL_PASS"],
                "formal_suite_status_contract": "NOT_EXECUTED",
            },
            "PR_CHANGESET": {
                "environment_contract": "CI",
                "allowed_results": ["PR_REVIEWED"],
                "formal_suite_status_contract": "NOT_EXECUTED",
            },
            "RUNTIME_SUITE_RESULT": {
                "environment_contract": "EACH_SUITE_CANONICAL_ENVIRONMENT",
                "allowed_results_by_target_verification": {
                    "PASS": ["PASS"],
                    "PARTIAL": ["PASS", "PARTIAL"],
                    "FAIL": ["FAIL"],
                },
                "formal_suite_status_contract": "EQUALS_TARGET_VERIFICATION",
            },
            "STAGING_DEPLOYMENT": {
                "environment_contract": "STAGING",
                "allowed_results": ["DEPLOYED"],
                "formal_suite_status_contract": "PASS",
            },
            "PRODUCTION_RELEASE": {
                "environment_contract": "PRODUCTION",
                "allowed_results": ["RELEASED"],
                "formal_suite_status_contract": "PASS",
            },
            "REGRESSION": {
                "environment_contract": "EACH_SUITE_CANONICAL_ENVIRONMENT",
                "allowed_results_by_target_verification": {
                    "PARTIAL": ["PARTIAL"],
                    "FAIL": ["FAIL"],
                },
                "formal_suite_status_contract": "EQUALS_TARGET_VERIFICATION",
            },
            "EXPIRY": {
                "environment_contract": "EACH_SUITE_CANONICAL_ENVIRONMENT",
                "allowed_results": ["EXPIRED"],
                "formal_suite_status_contract": "NOT_EXECUTED",
            },
            "ROLLBACK_DECISION": {
                "environment_contract": "EACH_SUITE_CANONICAL_ENVIRONMENT",
                "allowed_results": ["ROLLBACK_APPROVED"],
                "formal_suite_status_contract": "NOT_EXECUTED",
            },
            "SCOPE_DECISION": {
                "environment_contract": "LOCAL",
                "allowed_results": ["SCOPE_APPROVED"],
                "formal_suite_status_contract": "NOT_EXECUTED",
            },
        },
    }


def source_paths() -> list[Path]:
    fixed = [
        REPO_ROOT / ".gitattributes",
        REPO_ROOT / GENERATOR_PATH,
        REPO_ROOT / "scripts" / "import_raos_design.py",
        REPO_ROOT / "docs" / "README.md",
        DEFAULT_BUNDLE_ROOT / "README.md",
        REPO_ROOT / "docs" / "execplans" / "ST-0005.md",
        REPO_ROOT / "docs" / "worklogs" / "ST-0005.md",
        REPO_ROOT / "tests" / "test_import_raos_design.py",
    ]
    tests_root = REPO_ROOT / "tests" / "st0005"
    if tests_root.is_symlink() or not tests_root.is_dir():
        raise RuntimeError("ST-0005 test source directory is missing")
    tests = sorted(
        path
        for path in tests_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".yaml", ".json"}
    )
    sources = (
        fixed + request_files() + evidence_files() + evidence_artifact_files() + tests
    )
    for path in sources:
        relative = PurePosixPath(path.relative_to(REPO_ROOT).as_posix())
        if (
            path.is_symlink()
            or path_has_symlink(REPO_ROOT, relative)
            or not path.is_file()
        ):
            raise RuntimeError(f"required ST-0005 source artifact is missing: {path}")
    return sources


def artifact_entry(path: Path, logical_path: str) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": logical_path,
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def source_artifacts() -> list[dict[str, Any]]:
    return [artifact_entry(path, relative_repo_path(path)) for path in source_paths()]


def generated_artifacts(staged_root: Path) -> list[dict[str, Any]]:
    paths = [staged_root / OVERLAY_NAME]
    paths.extend(
        sorted(
            path for path in (staged_root / CONTRACTS_NAME).rglob("*") if path.is_file()
        )
    )
    return [
        artifact_entry(
            path, f"changes/st-0005/{path.relative_to(staged_root).as_posix()}"
        )
        for path in paths
    ]


def build_manifest(staged_root: Path, overlay: Mapping[str, Any]) -> dict[str, Any]:
    generated = generated_artifacts(staged_root)
    counts = require_mapping(overlay.get("counts"), source="overlay.counts")
    applied = require_list(
        overlay.get("applied_transitions"), source="overlay.applied_transitions"
    )
    real_pr_evidence = "PRESENT" if applied else "ABSENT"
    return {
        "document": {
            "id": REVISION_ID,
            "version": REVISION_VERSION,
            "story_id": "ST-0005",
            "status": "IMPLEMENTATION_CANDIDATE",
            "generated_by": GENERATOR_PATH,
        },
        "provenance": {
            "requirement_ids": ["FR-020"],
            "design_refs": ["RAOS-STATUS-TAXONOMY-001"],
            "depends_on": ["ST-0001"],
            "canonical_base_sha256": canonical_base_digest(),
            "immutable_import_manifest_sha256": PINNED_INPUT_HASHES[
                "docs/manifest.json"
            ],
            "complete_st0001_import_verification": True,
        },
        "status_boundary": {
            "canonical_files_modified": False,
            "effective_apply_requests": counts["applied_requests"],
            "proposal_only_requests": counts["proposal_requests"],
            "authoritative_live_apply": "BLOCKED_PENDING_GOVERNANCE",
            "live_apply_activation_requires": list(LIVE_APPLY_ACTIVATION_PREREQUISITES),
            "deployment_apply_activation_additionally_requires": list(
                DEPLOYMENT_APPLY_ACTIVATION_PREREQUISITES
            ),
            "formal_tst_001": "NOT_EXECUTED",
            "ci_environment": "NOT_CONFIGURED",
            "real_pull_request_evidence": real_pr_evidence,
        },
        "manifest_self_integrity": {
            "path": "changes/st-0005/manifest.yaml",
            "included_in_generated_artifacts": False,
            "reason": "SELF_HASH_RECURSION_AVOIDED",
            "verification": "DETERMINISTIC_REGENERATION_BYTE_COMPARE",
        },
        "safety": {
            "strict_request_schema": REQUEST_SCHEMA_PATH,
            "path_traversal_symlink_missing_hash_mismatch": "REJECT",
            "unknown_story_suite_status_field": "REJECT",
            "required_suite_evidence_mismatch": "REJECT",
            "snapshot_binding_or_source_artifact_mismatch": "REJECT",
            "duplicate_content_addressed_capture_digest": "REJECT",
            "stale_status_evidence_against_active_observation": "REJECT",
            "stale_status_evidence_against_latest_applied_approval": "REJECT",
            "evidence_expired_at_approval_decision": "REJECT",
            "pull_request_uri_reuse": "REJECT",
            "approval_artifact_reuse": "REJECT",
            "scope_decision_and_approval_artifact_alias": "REJECT",
            "orphan_evidence_snapshot": "REJECT",
            "lost_update": "REJECT",
            "request_and_evidence_history": "APPEND_ONLY",
            "generated_install": "SIBLING_STAGING_WITH_ROLLBACK",
            "owned_tree_enforced": True,
        },
        "source_artifacts": source_artifacts(),
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
    }


def assert_owned_generated_destination(bundle_root: Path) -> None:
    if bundle_root.is_symlink() or (bundle_root.exists() and not bundle_root.is_dir()):
        raise RuntimeError(f"refusing unsafe bundle root: {bundle_root}")
    contracts = bundle_root / CONTRACTS_NAME
    overlay = bundle_root / OVERLAY_NAME
    manifest = bundle_root / MANIFEST_NAME
    if contracts.is_symlink() or overlay.is_symlink() or manifest.is_symlink():
        raise RuntimeError(f"refusing symlinked generated destination: {bundle_root}")
    exists = (contracts.exists(), overlay.exists(), manifest.exists())
    if any(exists) and not all(exists):
        raise RuntimeError("partial generated destination")
    if not any(exists):
        return
    if not contracts.is_dir() or not overlay.is_file() or not manifest.is_file():
        raise RuntimeError("malformed generated destination")
    manifest_document = load_yaml(manifest)
    document = manifest_document.get("document")
    if (
        not isinstance(document, dict)
        or document.get("id") != REVISION_ID
        or document.get("generated_by") != GENERATOR_PATH
    ):
        raise RuntimeError(f"destination is not owned by {REVISION_ID}")
    entries = manifest_document.get("generated_artifacts")
    if not isinstance(entries, list) or manifest_document.get(
        "generated_artifact_count"
    ) != len(entries):
        raise RuntimeError("owned destination manifest inventory is malformed")
    listed: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RuntimeError("malformed owned artifact entry")
        logical = entry["path"]
        prefix = "changes/st-0005/"
        if not logical.startswith(prefix):
            raise RuntimeError(f"owned artifact escapes bundle: {logical}")
        relative = logical.removeprefix(prefix)
        if relative != OVERLAY_NAME and not relative.startswith(f"{CONTRACTS_NAME}/"):
            raise RuntimeError(f"unexpected owned artifact path: {logical}")
        folded = relative.casefold()
        if folded in {item.casefold() for item in listed}:
            raise RuntimeError(f"casefold duplicate owned artifact: {logical}")
        listed[relative] = entry

    actual: dict[str, Path] = {OVERLAY_NAME: overlay}
    for directory, directory_names, filenames in os.walk(contracts, followlinks=False):
        directory_path = Path(directory)
        for name in directory_names:
            child = directory_path / name
            if child.is_symlink():
                raise RuntimeError(f"unowned symlink in generated tree: {child}")
        for name in filenames:
            child = directory_path / name
            if child.is_symlink() or not child.is_file():
                raise RuntimeError(f"unowned special file in generated tree: {child}")
            actual[child.relative_to(bundle_root).as_posix()] = child
    if set(listed) != set(actual):
        raise RuntimeError(
            "unowned or missing generated files: "
            f"unexpected={sorted(set(actual) - set(listed))}, "
            f"missing={sorted(set(listed) - set(actual))}"
        )
    for relative, path in actual.items():
        entry = listed[relative]
        if entry.get("bytes") != path.stat().st_size or entry.get(
            "sha256"
        ) != sha256_file(path):
            raise RuntimeError(f"owned generated artifact hash drift: {relative}")


def install_staged_generation(staged_root: Path, bundle_root: Path) -> None:
    backups = {
        name: staged_root.parent / f"previous-{name.replace('/', '-')}"
        for name in GENERATED_NAMES
    }
    moved_old: list[str] = []
    installed_new: list[str] = []
    had_previous = (bundle_root / MANIFEST_NAME).exists()
    try:
        if had_previous:
            for name in GENERATED_NAMES:
                os.replace(bundle_root / name, backups[name])
                moved_old.append(name)
        for name in GENERATED_NAMES:
            os.replace(staged_root / name, bundle_root / name)
            installed_new.append(name)
    except OSError:
        for name in reversed(installed_new):
            target = bundle_root / name
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
        for name in reversed(moved_old):
            os.replace(backups[name], bundle_root / name)
        raise


def build(bundle_root: Path) -> None:
    """Render generated files in sibling staging and replace owned output."""

    assert_immutable_inputs()
    assert_owned_generated_destination(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)
    overlay = build_overlay()
    with tempfile.TemporaryDirectory(
        prefix=".raos-st0005-build-", dir=bundle_root.parent
    ) as temporary:
        staged_root = Path(temporary) / "generated"
        staged_root.mkdir()
        write_json(staged_root / REQUEST_SCHEMA_PATH, request_schema())
        write_yaml(staged_root / "contracts" / "status-policy.v1.yaml", build_policy())
        write_yaml(staged_root / OVERLAY_NAME, overlay)
        write_yaml(staged_root / MANIFEST_NAME, build_manifest(staged_root, overlay))
        install_staged_generation(staged_root, bundle_root)


def generated_file_map(bundle_root: Path) -> dict[str, bytes]:
    paths = [bundle_root / MANIFEST_NAME, bundle_root / OVERLAY_NAME]
    contracts = bundle_root / CONTRACTS_NAME
    if contracts.is_dir():
        paths.extend(sorted(path for path in contracts.rglob("*") if path.is_file()))
    return {
        path.relative_to(bundle_root).as_posix(): path.read_bytes()
        for path in paths
        if path.is_file()
    }


def check_generated() -> None:
    assert_owned_generated_destination(DEFAULT_BUNDLE_ROOT)
    with tempfile.TemporaryDirectory(prefix="raos-st0005-check-") as temporary:
        candidate = Path(temporary) / "bundle"
        build(candidate)
        expected = generated_file_map(candidate)
        actual = generated_file_map(DEFAULT_BUNDLE_ROOT)
    if expected == actual:
        return
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    changed = sorted(
        path for path in set(expected) & set(actual) if expected[path] != actual[path]
    )
    raise RuntimeError(
        json.dumps(
            {
                "status": "DRIFT",
                "missing": missing,
                "unexpected": unexpected,
                "changed": changed,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def validate_request_files(
    paths: Sequence[Path], *, require_pr_context: bool
) -> list[dict[str, Any]]:
    assert_immutable_inputs()
    registry, story_document, suite_document, _ = canonical_inputs()
    story_index = index_records(
        story_document, collection="stories", source="canonical story catalog"
    )
    suite_index = index_records(
        suite_document, collection="suites", source="canonical suite catalog"
    )
    state = initial_effective_state(registry, story_document, suite_document)
    state["proposals"] = []
    state["applied_transitions"] = []
    results: list[dict[str, Any]] = []
    seen_request_ids: set[str] = set()
    for path in paths:
        validated = validate_request(
            load_yaml(path),
            state=state,
            story_index=story_index,
            suite_index=suite_index,
            require_pr_context=require_pr_context,
        )
        request_id = validated["document"]["id"]
        if request_id in seen_request_ids:
            raise RuntimeError(f"duplicate status request id: {request_id}")
        seen_request_ids.add(request_id)
        apply_validated_request(state, validated)
        results.append(validated)
    return results


def validate_request_file(path: Path, *, require_pr_context: bool) -> dict[str, Any]:
    """Compatibility wrapper for one request against the canonical base."""

    return validate_request_files([path], require_pr_context=require_pr_context)[0]


def validate_live_committed_request(path: Path) -> dict[str, Any]:
    """Replay all history offline and bind only the changed request to live PR."""

    assert_immutable_inputs()
    if os.environ.get("GITHUB_EVENT_NAME") not in {
        "pull_request",
        "pull_request_target",
    }:
        raise RuntimeError(
            "live status request validation requires a pull-request workflow event"
        )
    relative = relative_repo_path(path)
    if os.environ.get("RAOS_CHANGED_STATUS_REQUEST") != relative:
        raise RuntimeError("live changed-request path does not match workflow context")
    overlay = build_overlay(live_request=path)
    inventory = require_list(
        overlay.get("request_inventory"), source="overlay.request_inventory"
    )
    selected = [item for item in inventory if item.get("path") == relative]
    if len(selected) != 1:
        raise RuntimeError("live request was not uniquely replayed")
    try:
        changed_count = int(os.environ.get("RAOS_CHANGED_STATUS_REQUEST_COUNT", "0"))
    except ValueError as exc:
        raise RuntimeError("changed status request count is malformed") from exc
    if selected[0].get("intent") == "APPLY" and changed_count != 1:
        raise RuntimeError("an APPLY pull request must change exactly one request file")
    if changed_count < 1:
        raise RuntimeError("live pull request contains no changed status request")
    if selected[0].get("intent") == "APPLY":
        raise RuntimeError(
            "authoritative live APPLY is fail-closed until "
            f"{'/'.join(LIVE_APPLY_ACTIVATION_PREREQUISITES)} are integrated; "
            "deployment transitions additionally require "
            f"{'/'.join(DEPLOYMENT_APPLY_ACTIVATION_PREREQUISITES)}"
        )
    return dict(selected[0])


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_BUNDLE_ROOT,
        help="owned output; CLI accepts only changes/st-0005",
    )
    parser.add_argument(
        "--validate-live-request",
        type=Path,
        help=(
            "offline-replay all committed history, then bind only this changed "
            "request to the current pull request"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild in a temporary directory and fail on generated drift",
    )
    parser.add_argument(
        "--validate-request",
        type=Path,
        action="extend",
        nargs="+",
        default=[],
        help="validate and sequentially replay requests against the pinned base",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] = ()) -> int:
    args = parse_args(argv)
    try:
        selected = (
            int(args.check)
            + int(bool(args.validate_request))
            + int(args.validate_live_request is not None)
        )
        if selected > 1:
            raise RuntimeError(
                "--check, --validate-request, and --validate-live-request are "
                "mutually exclusive"
            )
        if args.validate_request:
            results = validate_request_files(
                [path.resolve() for path in args.validate_request],
                require_pr_context=False,
            )
            result: dict[str, Any] = {
                "status": "PASS",
                "story_id": "ST-0005",
                "mode": "validate-request",
                "requests": [item["document"]["id"] for item in results],
            }
        elif args.validate_live_request is not None:
            live = validate_live_committed_request(args.validate_live_request.resolve())
            result = {
                "status": "PASS",
                "story_id": "ST-0005",
                "mode": "validate-live-request",
                "request": live["request_id"],
            }
        elif args.check:
            if args.output.resolve() != DEFAULT_BUNDLE_ROOT.resolve():
                raise RuntimeError("--check does not accept a custom --output")
            check_generated()
            result = {"status": "PASS", "story_id": "ST-0005", "mode": "check"}
        else:
            output = args.output.resolve()
            if output != DEFAULT_BUNDLE_ROOT.resolve():
                raise RuntimeError(
                    "--output must be the owned canonical changes/st-0005 bundle"
                )
            build(output)
            result = {
                "status": "PASS",
                "story_id": "ST-0005",
                "mode": "build",
                "output": str(output),
            }
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        UnicodeError,
        ValueError,
        yaml.YAMLError,
    ) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "story_id": "ST-0005", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
