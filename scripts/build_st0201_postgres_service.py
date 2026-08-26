#!/usr/bin/env python3
"""Build and validate the local ST-0201 PostgreSQL service artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0201/contracts/local-postgres.v1.yaml")
ARCHITECTURE_SNAPSHOT_PATH: Final = Path(
    "docs/architecture/ST-0201-postgres-image-snapshot.yaml"
)
COMPOSE_PATH: Final = Path("docker-compose.yml")
MANIFEST_PATH: Final = Path("changes/st-0201/manifest.yaml")
RUNTIME_WRAPPER_PATH: Final = Path("scripts/postgres_service.sh")
GENERATED_PATHS: Final = (COMPOSE_PATH, MANIFEST_PATH)
SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st0201_postgres_service.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st0201_postgres_service.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"
EXPECTED_ARCHITECTURE_SNAPSHOT_SHA256: Final = (
    "ee64f731f41b88f185d4f58d9affd5eb35834353b074e215bb7ddc1788622dfd"
)

PINNED_SOURCES: Final = {
    "docs/manifest.json": (
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md": (
        "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c"
    ),
    "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md": (
        "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3"
    ),
    "docs/canonical/08_codex/RAOS_14_codex_implementation_handbook_v1.0.md": (
        "501858e7cdb47db5d2987f6e3d778da4fb8d72224b4380790dcd91ffcac615b2"
    ),
}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-0201/README.md"),
    ARCHITECTURE_SNAPSHOT_PATH,
    Path("docs/execplans/ST-0201.md"),
    Path("docs/worklogs/ST-0201.md"),
    Path("scripts/build_st0201_postgres_service.py"),
    RUNTIME_WRAPPER_PATH,
    Path("tests/st0201/conftest.py"),
    Path("tests/st0201/test_contract.py"),
    Path("tests/st0201/test_generation.py"),
    Path("tests/st0201/test_negative_cases.py"),
    Path("tests/st0201/test_wrapper.py"),
    Path(".github/workflows/ci.yml"),
    Path("changes/st-0107/contracts/pr-governance.v1.yaml"),
    Path("changes/st-0107/manifest.yaml"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("workspace-layout.json"),
    Path("infra/docker/README.md"),
    Path("AGENTS.md"),
    Path("Makefile"),
    Path("README.md"),
)

EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-LOCAL-POSTGRES-001",
    "version": "1.0.0",
    "story_id": "ST-0201",
    "status": "LOCAL_AND_CI_CANDIDATE",
    "formal_verification": "NOT_EXECUTED",
}
EXPECTED_IMAGE: Final = {
    "repository": "docker.io/library/postgres",
    "tag": "18.4-bookworm",
    "reference": "postgres:18.4-bookworm@sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296",
    "index_digest": "sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296",
    "platform": {
        "os": "linux",
        "architecture": "amd64",
        "manifest_digest": "sha256:16fa100a3a6e92c0556632870455e7f8c6f3df5cefddd67d6b95292732bd7ff0",
        "config_digest": "sha256:0a314d409a9633cff4f89dc18482262625c0ee78cb1aa2ff8e47bc6da0251e1b",
    },
    "expected_environment": {
        "PG_VERSION": "18.4-1.pgdg12+1",
        "PGDATA": "/var/lib/postgresql/18/docker",
    },
    "checked_at": "2026-08-02T11:19:33Z",
}
EXPECTED_COMPOSE: Final = {
    "service": {
        "name": "postgres",
        "platform": "linux/amd64",
        "database": "raos",
        "user": "raos",
        "init": True,
        "restart": "no",
        "stop_grace_period": "30s",
    },
    "port": {
        "host_ip": "127.0.0.1",
        "variable": "RAOS_POSTGRES_PORT",
        "default": 5432,
        "container": 5432,
        "protocol": "tcp",
    },
    "password_secret": {
        "name": "postgres_password",
        "source_variable": "RAOS_POSTGRES_PASSWORD_FILE",
        "source_default": ".secrets/postgres_password",
        "environment_key": "POSTGRES_PASSWORD_FILE",
        "mount_path": "/run/secrets/postgres_password",
    },
    "data": {
        "volume": "postgres_data",
        "mount_path": "/var/lib/postgresql",
        "pgdata": "/var/lib/postgresql/18/docker",
    },
    "network": {
        "name": "postgres_internal",
        "driver": "bridge",
        "internal": True,
    },
    "healthcheck": {
        "command": (
            'pg_isready --username "$$POSTGRES_USER" --dbname '
            '"$$POSTGRES_DB" --host 127.0.0.1 --port 5432'
        ),
        "interval": "5s",
        "timeout": "5s",
        "retries": 12,
        "start_period": "10s",
    },
}
EXPECTED_RUNTIME: Final = {
    "wrapper": "repo://scripts/postgres_service.sh",
    "interface": "scripts/postgres_service.sh --docker EXECUTABLE COMMAND",
    "commands": ["config", "up", "check", "down", "test"],
    "docker_host": "unix:///var/run/docker.sock",
    "minimum_compose_version": "2.24.4",
    "local_project": "raos-st0201-local",
    "disposable_project_prefix": "raos-st0201-test-",
    "disposable_password_mode": "0600",
    "disposable_pull_policy": "always",
    "expected_image_config_digest": "sha256:0a314d409a9633cff4f89dc18482262625c0ee78cb1aa2ff8e47bc6da0251e1b",
    "expected_platform": "linux/amd64",
    "expected_server_version_num": 180004,
    "version_query": "SHOW server_version_num;",
}
EXPECTED_SECURITY_CONTROLS: Final = [
    {
        "id": "SEC-DATA-003",
        "implementation": "Password value exists only in a non-symlink secret file and is never embedded in Compose, arguments, or logs.",
        "verification": "LOCAL_CONTRACT_AND_SECRET_SCAN",
    },
    {
        "id": "SEC-INFRA-001",
        "implementation": "The host publish is loopback-only and the service uses an internal bridge network.",
        "verification": "LOCAL_CONFIG_TEST_RUNTIME_NOT_EXECUTED",
    },
    {
        "id": "SEC-SDLC-003",
        "implementation": "The image tag, OCI index, linux/amd64 manifest, and configuration digests are pinned.",
        "verification": "LOCAL_CONTRACT_TEST",
    },
    {
        "id": "SEC-SDLC-004",
        "implementation": "A container vulnerability scan is required before validation and remains NOT_EXECUTED.",
        "verification": "NOT_EXECUTED",
    },
]
EXPECTED_BOUNDARY: Final = {
    "environment": "LOCAL_AND_CI_ONLY",
    "production_use": "FORBIDDEN",
    "remote_database": "FORBIDDEN",
    "raw_password_environment": "FORBIDDEN",
    "docker_runtime": "NOT_EXECUTED",
    "container_vulnerability_scan": "NOT_EXECUTED",
    "formal_tst_008": "NOT_EXECUTED",
    "effective_canonical_status": "UNCHANGED",
}

CANONICAL_STORY: Final = {
    "id": "ST-0201",
    "epic_id": "EPIC-02",
    "title": "Local PostgreSQL 18 service",
    "objective": "再現可能なLocal/CI DBを構築",
    "depends_on": ["ST-0102"],
    "requirement_ids": [],
    "design_refs": ["RAOS-DATA-001"],
    "deliverables": ["compose/service", "health check"],
    "acceptance_criteria": ["version assertion"],
    "test_suites": ["TST-008"],
    "priority": "P0",
    "mvp": True,
    "size": "S",
    "open_decisions": [],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_TST_008: Final = {
    "id": "TST-008",
    "name": "PostgreSQL baseline integration",
    "layer": "database",
    "purpose": "DDL/extension/seed/constraint/trigger/role",
    "candidate_tools": ["PostgreSQL 18 container", "pytest"],
    "release_blocking": True,
    "environments": ["CI"],
    "owner": "Engineering",
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "execution_status": "NOT_EXECUTED",
}
EXPECTED_CANONICAL_SECURITY_CONTROLS: Final = {
    "SEC-DATA-003": {
        "id": "SEC-DATA-003",
        "category": "DATA",
        "title": "Secret storage",
        "requirement": "SecretをDB/Repo/Logへ置かない",
        "verification": "secret scan",
        "priority": "P0",
        "gate": "GATE-0",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
    "SEC-INFRA-001": {
        "id": "SEC-INFRA-001",
        "category": "INFRA",
        "title": "Private data plane",
        "requirement": "RDS/worker/object admin endpointをPublicにしない",
        "verification": "network scan",
        "priority": "P1",
        "gate": "GATE-0",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
    "SEC-SDLC-003": {
        "id": "SEC-SDLC-003",
        "category": "SDLC",
        "title": "Dependency pinning",
        "requirement": "Lockfileとverified source",
        "verification": "dependency review",
        "priority": "P1",
        "gate": "GATE-0",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
    "SEC-SDLC-004": {
        "id": "SEC-SDLC-004",
        "category": "SDLC",
        "title": "SCA",
        "requirement": "Dependency/container vulnerability scan",
        "verification": "CI evidence",
        "priority": "P1",
        "gate": "GATE-0",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
}

MAX_YAML_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


class NoAliasDumper(yaml.SafeDumper):
    """Deterministic YAML dumper without anchors or aliases."""

    def ignore_aliases(self, data: object) -> bool:
        return True


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


def _require_exact(value: object, expected: object, label: str) -> None:
    """Compare recursively without Python's bool/int equality ambiguity."""

    if type(value) is not type(expected):
        raise RuntimeError(
            f"{label} type differs: {type(value).__name__} != {type(expected).__name__}"
        )
    if isinstance(expected, dict):
        actual_mapping = _mapping(value, label)
        _exact_keys(actual_mapping, set(expected), label)
        for key, expected_value in expected.items():
            _require_exact(actual_mapping[key], expected_value, f"{label}.{key}")
        return
    if isinstance(expected, list):
        actual_list = _list(value, label)
        if len(actual_list) != len(expected):
            raise RuntimeError(f"{label} length differs")
        for index, (actual_item, expected_item) in enumerate(
            zip(actual_list, expected, strict=True)
        ):
            _require_exact(actual_item, expected_item, f"{label}[{index}]")
        return
    if value != expected:
        raise RuntimeError(f"{label} differs from the reviewed value")


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
    observed_order: list[str] = []
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
        observed_order.append(key)
    if observed != PINNED_SOURCES or observed_order != list(PINNED_SOURCES):
        raise RuntimeError("source inventory differs from the reviewed pinned set")
    for relative, expected in PINNED_SOURCES.items():
        source_path = _repository_regular_file(root, Path(relative), "pinned source")
        actual = sha256_file(source_path)
        if actual != expected:
            raise RuntimeError(
                f"pinned source hash mismatch: {relative}: {actual} != {expected}"
            )


def _validate_architecture_snapshot(root: Path) -> None:
    path = _repository_regular_file(
        root, ARCHITECTURE_SNAPSHOT_PATH, "architecture snapshot"
    )
    actual = sha256_file(path)
    if actual != EXPECTED_ARCHITECTURE_SNAPSHOT_SHA256:
        raise RuntimeError(
            "architecture snapshot hash mismatch: "
            f"{actual} != {EXPECTED_ARCHITECTURE_SNAPSHOT_SHA256}"
        )
    snapshot = _mapping(load_yaml(path), "architecture snapshot")
    _exact_keys(
        snapshot,
        {
            "document",
            "official_sources",
            "registry_resolution",
            "local_candidate",
            "security_semantics",
            "runtime_acceptance",
            "verification_boundary",
        },
        "architecture snapshot",
    )
    document = _mapping(snapshot["document"], "architecture snapshot document")
    expected_document = {
        "id": "RAOS-ST0201-POSTGRES-IMAGE-SNAPSHOT-001",
        "schema_version": 1,
        "story_id": "ST-0201",
        "checked_at": "2026-08-02T11:19:33Z",
    }
    for key, value in expected_document.items():
        _require_exact(
            document.get(key), value, f"architecture snapshot document.{key}"
        )
    source_ids = tuple(
        _mapping(row, "architecture snapshot official source").get("id")
        for row in _list(snapshot["official_sources"], "official_sources")
    )
    if source_ids != (
        "DOCKER-OFFICIAL-POSTGRES",
        "DOCKER-OFFICIAL-IMAGES-POSTGRES-LIBRARY",
        "DOCKER-COMPOSE-SECRETS",
        "DOCKER-COMPOSE-PORTS",
    ):
        raise RuntimeError("architecture snapshot official source inventory drifted")
    resolution = _mapping(snapshot["registry_resolution"], "registry_resolution")
    _require_exact(
        resolution.get("image_reference"),
        EXPECTED_IMAGE["reference"],
        "registry_resolution.image_reference",
    )
    _require_exact(
        resolution.get("index_digest"),
        EXPECTED_IMAGE["index_digest"],
        "registry_resolution.index_digest",
    )
    _require_exact(
        resolution.get("platform"),
        EXPECTED_IMAGE["platform"],
        "registry_resolution.platform",
    )
    _require_exact(
        resolution.get("config_environment"),
        EXPECTED_IMAGE["expected_environment"],
        "registry_resolution.config_environment",
    )
    candidate = _mapping(snapshot["local_candidate"], "local_candidate")
    if (
        candidate.get("source_contract") != SOURCE_CONTRACT_URI
        or candidate.get("generator") != GENERATOR_URI.removeprefix("repo://")
        or candidate.get("generation_command") != GENERATION_COMMAND
        or candidate.get("drift_check_command") != CHECK_COMMAND
        or candidate.get("runtime_wrapper") != "scripts/postgres_service.sh"
        or candidate.get("remote_database_capability") != "FORBIDDEN"
    ):
        raise RuntimeError("architecture snapshot local candidate drifted")
    acceptance = _mapping(snapshot["runtime_acceptance"], "runtime_acceptance")
    if (
        acceptance.get("expected_server_version_num") != 180004
        or acceptance.get("expected_platform") != "linux/amd64"
        or acceptance.get("expected_image_config_digest")
        != EXPECTED_IMAGE["platform"]["config_digest"]
        or acceptance.get("formal_suite") != "TST-008"
    ):
        raise RuntimeError("architecture snapshot runtime acceptance drifted")
    security = _mapping(snapshot["security_semantics"], "security_semantics")
    if (
        security.get("selected_platform") != "linux/amd64"
        or security.get("expected_image_config_digest")
        != EXPECTED_IMAGE["platform"]["config_digest"]
    ):
        raise RuntimeError("architecture snapshot platform enforcement drifted")
    boundary = _mapping(snapshot["verification_boundary"], "verification_boundary")
    for key in (
        "docker_compose_config",
        "docker_image_pull",
        "container_health_probe",
        "server_version_assertion",
        "container_vulnerability_scan",
        "formal_tst_008",
    ):
        if boundary.get(key) != "NOT_EXECUTED":
            raise RuntimeError("architecture snapshot verification boundary drifted")
    if boundary.get("effective_canonical_status") != "UNCHANGED":
        raise RuntimeError("architecture snapshot canonical status was promoted")


def _select_exact_record(
    path: Path, collection: str, record_id: str, root: Path
) -> Mapping[str, Any]:
    source = _repository_regular_file(root, path, f"canonical {collection}")
    document = _mapping(load_yaml(source), f"canonical {collection}")
    rows = _list(document.get(collection), f"canonical {collection} records")
    matches = [
        row for row in rows if isinstance(row, Mapping) and row.get("id") == record_id
    ]
    if len(matches) != 1:
        raise RuntimeError(f"canonical record {record_id} is missing or duplicated")
    return _mapping(matches[0], f"canonical record {record_id}")


def _validate_canonical_contracts(root: Path) -> None:
    story = _select_exact_record(
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "stories",
        "ST-0201",
        root,
    )
    _require_exact(dict(story), CANONICAL_STORY, "canonical ST-0201")
    suite = _select_exact_record(
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "suites",
        "TST-008",
        root,
    )
    _require_exact(dict(suite), EXPECTED_TST_008, "canonical TST-008")
    for control_id, expected in EXPECTED_CANONICAL_SECURITY_CONTROLS.items():
        control = _select_exact_record(
            Path(
                "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
            ),
            "controls",
            control_id,
            root,
        )
        _require_exact(dict(control), expected, f"canonical {control_id}")


def load_and_validate_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "PostgreSQL contract")
    contract = _mapping(load_yaml(contract_path), "PostgreSQL contract")
    _exact_keys(
        contract,
        {
            "document",
            "sources",
            "image",
            "compose",
            "runtime",
            "security_controls",
            "boundary",
        },
        "PostgreSQL contract",
    )
    _require_exact(contract["document"], EXPECTED_DOCUMENT, "document")
    _validate_sources(contract, root)
    _validate_architecture_snapshot(root)
    _validate_canonical_contracts(root)
    _require_exact(contract["image"], EXPECTED_IMAGE, "image")
    _require_exact(contract["compose"], EXPECTED_COMPOSE, "compose")
    _require_exact(contract["runtime"], EXPECTED_RUNTIME, "runtime")
    _require_exact(
        contract["security_controls"],
        EXPECTED_SECURITY_CONTROLS,
        "security_controls",
    )
    _require_exact(contract["boundary"], EXPECTED_BOUNDARY, "boundary")
    return dict(contract)


def render_compose(contract: Mapping[str, Any]) -> bytes:
    image = _mapping(contract["image"], "image")
    compose = _mapping(contract["compose"], "compose")
    service = _mapping(compose["service"], "compose.service")
    port = _mapping(compose["port"], "compose.port")
    password_spec = _mapping(compose["password_secret"], "compose.password_secret")
    data = _mapping(compose["data"], "compose.data")
    network = _mapping(compose["network"], "compose.network")
    health = _mapping(compose["healthcheck"], "compose.healthcheck")
    content = f"""# Generated by scripts/build_st0201_postgres_service.py. Do not edit.
# Source contract: {SOURCE_CONTRACT_URI}
# Generation command: {GENERATION_COMMAND}
# Local/CI candidate only; runtime and formal TST-008 remain NOT_EXECUTED.
services:
  {service["name"]}:
    image: {image["reference"]}
    platform: {service["platform"]}
    pull_policy: always
    init: true
    restart: 'no'
    stop_grace_period: {service["stop_grace_period"]}
    environment:
      POSTGRES_DB: {service["database"]}
      POSTGRES_USER: {service["user"]}
      POSTGRES_PASSWORD_FILE: {password_spec["mount_path"]}
      PGDATA: {data["pgdata"]}
    ports:
      - '{port["host_ip"]}:${{{port["variable"]}-{port["default"]}}}:{port["container"]}/{port["protocol"]}'
    secrets:
      - source: {password_spec["name"]}
        target: {password_spec["name"]}
    volumes:
      - {data["volume"]}:{data["mount_path"]}
    networks:
      - {network["name"]}
    healthcheck:
      test:
        - CMD-SHELL
        - '{health["command"]}'
      interval: {health["interval"]}
      timeout: {health["timeout"]}
      retries: {health["retries"]}
      start_period: {health["start_period"]}

secrets:
  {password_spec["name"]}:
    file: ${{{password_spec["source_variable"]}:-{password_spec["source_default"]}}}

volumes:
  {data["volume"]}:

networks:
  {network["name"]}:
    driver: {network["driver"]}
    internal: true
"""
    return content.encode("utf-8")


def _artifact_record(root: Path, relative: Path) -> dict[str, Any]:
    path = _repository_regular_file(root, relative, "source artifact")
    content = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_manifest(root: Path, compose_content: bytes) -> bytes:
    source_artifacts = [
        _artifact_record(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    generated_artifacts = [
        {
            "uri": f"repo://{COMPOSE_PATH.as_posix()}",
            "bytes": len(compose_content),
            "sha256": sha256_bytes(compose_content),
        }
    ]
    manifest = {
        "document": {
            "id": "RAOS-LOCAL-POSTGRES-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0201",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_uri": SOURCE_CONTRACT_URI,
            "architecture_snapshot": {
                "uri": f"repo://{ARCHITECTURE_SNAPSHOT_PATH.as_posix()}",
                "sha256": EXPECTED_ARCHITECTURE_SNAPSHOT_SHA256,
            },
            "canonical_inputs": [
                {"uri": f"repo://{relative}", "sha256": digest}
                for relative, digest in PINNED_SOURCES.items()
            ],
            "image": {
                "reference": EXPECTED_IMAGE["reference"],
                "index_digest": EXPECTED_IMAGE["index_digest"],
                "linux_amd64_manifest_digest": EXPECTED_IMAGE["platform"][
                    "manifest_digest"
                ],
                "config_digest": EXPECTED_IMAGE["platform"]["config_digest"],
            },
        },
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(generated_artifacts),
        "generated_artifacts": generated_artifacts,
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "environment": "LOCAL_AND_CI_ONLY",
            "production_use": "FORBIDDEN",
            "remote_database": "FORBIDDEN",
            "docker_runtime": "NOT_EXECUTED",
            "container_vulnerability_scan": "NOT_EXECUTED",
            "formal_tst_008": "NOT_EXECUTED",
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def validate_wrapper_compose_binding(root: Path, compose_content: bytes) -> None:
    wrapper = _repository_regular_file(root, RUNTIME_WRAPPER_PATH, "runtime wrapper")
    text = wrapper.read_text(encoding="utf-8")
    prefix = "readonly expected_compose_sha256="
    bindings = [line for line in text.splitlines() if line.startswith(prefix)]
    accepted_digests = {sha256_bytes(compose_content)}
    try:
        from scripts import build_local_compose

        accepted_digests.add(sha256_bytes(build_local_compose.render_compose(root)))
    except ImportError, OSError, RuntimeError, TypeError, ValueError:
        # A detached ST-0201 component test may not include the cumulative inputs.
        pass
    expected = {f"{prefix}'{digest}'" for digest in accepted_digests}
    if len(bindings) != 1 or bindings[0] not in expected:
        raise RuntimeError("runtime wrapper Compose digest binding drifted")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_and_validate_contract(root)
    compose_content = render_compose(contract)
    validate_wrapper_compose_binding(root, compose_content)
    return {
        COMPOSE_PATH: compose_content,
        MANIFEST_PATH: render_manifest(root, compose_content),
    }


def _safe_parent(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError(f"unsafe generated path: {relative}")
    physical_root = root.resolve(strict=True)
    current = physical_root
    for part in relative.parent.parts:
        current /= part
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
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.st0201-", dir=parent)
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
    if set(outputs) != set(GENERATED_PATHS):
        raise RuntimeError("generated output inventory differs from the reviewed set")
    staged: dict[Path, Path] = {}
    previous: dict[Path, bytes | None] = {}
    installed: list[Path] = []
    try:
        for relative in GENERATED_PATHS:
            content = outputs[relative]
            if not isinstance(content, bytes):
                raise RuntimeError(f"generated output must be bytes: {relative}")
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
        if target.read_bytes() != expected[relative]:
            raise RuntimeError(f"generated artifact drift: {relative}")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or check the local ST-0201 PostgreSQL service artifacts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed artifacts byte-for-byte without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Compatibility entrypoint delegated to the sole cumulative Compose owner."""

    try:
        from scripts import build_local_compose
    except ModuleNotFoundError:
        import build_local_compose  # type: ignore[no-redef]

    return build_local_compose.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
