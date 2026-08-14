"""Shared fixtures and exact policy validation for the isolated ST-0202 suite."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_local_compose as generator
from scripts import build_st0201_postgres_service as strict_yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FILE = (
    REPOSITORY_ROOT
    / "changes"
    / "st-0202"
    / "contracts"
    / "local-object-storage.v1.yaml"
)
SNAPSHOT_FILE = (
    REPOSITORY_ROOT
    / "docs"
    / "architecture"
    / "ST-0202-object-storage-provider-snapshot.yaml"
)

Contract = dict[str, Any]
RejectContract = Callable[[Contract, str], None]
RejectProductionContract = Callable[[Contract], None]

EXPECTED_DOCUMENT = {
    "id": "RAOS-LOCAL-OBJECT-STORAGE-001",
    "version": "1.0.0",
    "story_id": "ST-0202",
    "status": "LOCAL_AND_CI_CANDIDATE",
    "formal_verification": "NOT_EXECUTED",
}

EXPECTED_IMAGE = {
    "repository": "docker.io/chrislusf/seaweedfs",
    "tag": "4.29",
    "reference": (
        "docker.io/chrislusf/seaweedfs:4.29@sha256:"
        "d47c7ee99fcb951351d7194915f4e3a5ea604a8e8871183d713907dec4fb9bf5"
    ),
    "index_digest": (
        "sha256:d47c7ee99fcb951351d7194915f4e3a5ea604a8e8871183d713907dec4fb9bf5"
    ),
    "platform": {
        "os": "linux",
        "architecture": "amd64",
        "manifest_digest": (
            "sha256:f16591b02e7a1d79dca57801405eec2c784711436edf65c0aa6394ef52800a3e"
        ),
        "config_digest": (
            "sha256:10b004ca7cc8ee13615dbe670e1be047270ab30a742a5944e82330017d64d8fd"
        ),
    },
    "expected_config": {
        "entrypoint": ["/entrypoint.sh"],
        "default_command": ["mini", "-dir=/data"],
        "declared_volume": "/data",
        "labels": {
            "org.opencontainers.image.source": (
                "https://github.com/seaweedfs/seaweedfs"
            ),
            "org.opencontainers.image.revision": (
                "1355c7a102194d6c461baf090eff50367b575afb"
            ),
            "org.opencontainers.image.version": "4.29",
            "org.opencontainers.image.licenses": "Apache-2.0",
        },
    },
    "checked_at": "2026-08-02T13:06:40Z",
}

EXPECTED_COMMAND = [
    "mini",
    "-dir=/data",
    "-s3.config=/run/raos/object-storage-s3-config.json",
    "-s3.port=8333",
    "-master.telemetry=false",
    "-webdav=false",
    "-admin.ui=false",
    "-s3.port.iceberg=0",
    "-s3.allowDeleteBucketNotEmpty=false",
]

EXPECTED_COMPOSE = {
    "service": {
        "name": "object-storage",
        "platform": "linux/amd64",
        "init": True,
        "restart": "no",
        "stop_grace_period": "30s",
    },
    "port": {
        "syntax": "long",
        "host_ip": "127.0.0.1",
        "variable": "RAOS_OBJECT_STORAGE_PORT",
        "default": 8333,
        "container": 8333,
        "protocol": "tcp",
    },
    "config_secret": {
        "name": "object_storage_s3_config",
        "source_variable": "RAOS_OBJECT_STORAGE_S3_CONFIG_FILE",
        "source_default": ".secrets/object-storage-s3-config.json",
        "mount_path": "/run/secrets/object_storage_s3_config",
    },
    "secret_staging": {
        "directory": "/run/raos",
        "path": "/run/raos/object-storage-s3-config.json",
        "uid": 1000,
        "gid": 1000,
        "mode": "0400",
        "directory_uid": 1000,
        "directory_gid": 1000,
        "directory_mode": "0700",
        "source_directory": "/run/secrets",
        "source_directory_mode": "0700",
        "tmpfs_options": "rw,noexec,nosuid,nodev,size=64k,mode=0700,uid=0,gid=0",
    },
    "data": {"volume": "object_storage_data", "mount_path": "/data"},
    "network": {
        "name": "object_storage_internal",
        "driver": "bridge",
        "internal": True,
    },
    "command": EXPECTED_COMMAND,
    "healthcheck": {
        "command": "curl --fail --silent --show-error http://127.0.0.1:8333/status >/dev/null",
        "interval": "5s",
        "timeout": "5s",
        "retries": 12,
        "start_period": "10s",
    },
}

EXPECTED_RUNTIME = {
    "wrapper": "repo://scripts/object_storage_service.sh",
    "fixture_client": "repo://scripts/object_storage_fixture.py",
    "interface": ("scripts/object_storage_service.sh --docker ABSOLUTE_PATH COMMAND"),
    "commands": ["config", "up", "check", "down", "test"],
    "docker_host": "unix:///var/run/docker.sock",
    "minimum_compose_version": "2.24.4",
    "local_project": "raos-st0202-local",
    "disposable_project_prefix": "raos-st0202-test-",
    "disposable_config_mode": "0600",
    "disposable_pull_policy": "always",
    "ephemeral_port_override": {
        "command": "test",
        "tracked_artifact": "ABSENT",
        "creation_executable": "/usr/bin/mktemp",
        "filename_template": "object-storage-disposable-port.override.XXXXXXXX.yml",
        "parent_directory_mode": "0700",
        "file_mode": "0600",
        "maximum_bytes": 512,
        "exact_bytes": 382,
        "sha256": ("92e141f0c1b96ef47cf79855951d6cadaec509b9796cc03067186ff44dd27239"),
        "compose_tag": "!override",
        "target": 8333,
        "host_ip": "127.0.0.1",
        "protocol": "tcp",
        "published": "OMITTED_ENGINE_ASSIGNED",
        "service_networks": [
            "object_storage_internal",
            "object_storage_disposable_publish",
        ],
        "publish_network": {
            "name": "object_storage_disposable_publish",
            "driver": "bridge",
            "internal": False,
            "driver_opts": {
                "com.docker.network.bridge.enable_ip_masquerade": "false",
            },
            "scope": "DISPOSABLE_PROJECT_ONLY",
        },
        "compose_file_order": [
            "docker-compose.yml",
            "EPHEMERAL_VALIDATED_OVERRIDE",
        ],
        "validation": "BEFORE_FIRST_DOCKER_AND_EVERY_COMPOSE_USE",
        "cleanup": "EXIT_HUP_INT_TERM",
        "forbidden_tokens": ["published", "${", "#"],
        "observed_mapping": {
            "exact_count": 1,
            "host": "127.0.0.1",
            "lexical_port_rule": "^[0-9]{1,5}$",
            "minimum_port": 1024,
            "maximum_port": 65535,
        },
    },
    "expected_image_config_digest": (
        "sha256:10b004ca7cc8ee13615dbe670e1be047270ab30a742a5944e82330017d64d8fd"
    ),
    "expected_platform": "linux/amd64",
    "expected_process_uid": 1000,
    "expected_image_labels": {
        "org.opencontainers.image.source": "https://github.com/seaweedfs/seaweedfs",
        "org.opencontainers.image.revision": (
            "1355c7a102194d6c461baf090eff50367b575afb"
        ),
        "org.opencontainers.image.version": "4.29",
        "org.opencontainers.image.licenses": "Apache-2.0",
    },
    "authentication": {
        "mode": "SINGLE_STATIC_JSON_CONFIG_FILE",
        "identity_count": 1,
        "identity_name": "raos-local-object-storage",
        "credential_count": 1,
        "config_file_mode": "0600",
        "config_max_bytes": 16384,
        "required_actions": ["Admin", "Read", "List", "Tagging", "Write"],
        "transport_chain": [
            "HOST_0600_SOURCE",
            "BOOTSTRAP_COMPOSE_SECRET_SOURCE",
            "NON_PERSISTENT_TMPFS_UID1000_MODE0400_COPY",
            "ROOT_ONLY_SOURCE_DIRECTORY_AFTER_COPY",
            "OFFICIAL_ENTRYPOINT_UID1000",
        ],
        "anonymous_access": "FORBIDDEN",
        "raw_credential_environment": "FORBIDDEN",
        "raw_credential_arguments": "FORBIDDEN",
    },
    "readiness": {
        "path": "/status",
        "classification": "PROCESS_READINESS_ONLY",
        "authenticated_acceptance_required": True,
    },
    "bucket": {
        "name": "raos-raw",
        "visibility": "PRIVATE",
        "object_lock_capability_at_creation": "REQUIRED",
        "versioning": "REQUIRED",
        "automatic_deletion": "DISABLED",
        "lifecycle_delete": "FORBIDDEN",
        "default_retention": "FORBIDDEN",
        "retention_period": "UNSET_HUMAN_DECISION_REQUIRED",
        "retention_hook": "REQUIRED_POLICY_PERIOD_UNSET",
        "required_metadata": [
            "sha256",
            "content-type",
            "source",
            "acquired-at",
            "retention-class",
        ],
        "hash_mismatch": "REJECT",
    },
    "authenticated_fixture": {
        "required": True,
        "operations": [
            "create-lock-capable-private-bucket",
            "enable-and-read-versioning",
            "put-two-object-versions",
            "get-each-version-by-id",
            "round-trip-required-metadata",
            "reject-declared-hash-mismatch",
            "exercise-retention-hook-without-policy",
        ],
        "formal_suite": "TST-014",
        "execution_status": "NOT_EXECUTED",
    },
}

EXPECTED_SECURITY_CONTROLS = [
    {
        "id": "SEC-DATA-003",
        "implementation": (
            "Access and secret keys move only from a host 0600 file through a "
            "bootstrap Compose secret into a non-persistent UID 1000 mode 0400 "
            "tmpfs copy; before privilege drop the source directory becomes "
            "root-only, and values never enter Compose values, arguments, logs, "
            "or tracked files."
        ),
        "verification": "LOCAL_CONTRACT_AND_SECRET_SCAN",
    },
    {
        "id": "SEC-DATA-004",
        "implementation": (
            "The raos-raw contract requires SHA-256 metadata, versioning, "
            "version-specific retrieval, and rejection of a declared hash mismatch."
        ),
        "verification": "LOCAL_CONTRACT_TEST_RUNTIME_NOT_EXECUTED",
    },
    {
        "id": "SEC-DATA-008",
        "implementation": (
            "A retention hook is required while OD-014 leaves every period unset "
            "and keeps automatic deletion and lifecycle delete disabled."
        ),
        "verification": "HUMAN_DECISION_AND_RUNTIME_TEST_REQUIRED",
    },
    {
        "id": "SEC-INFRA-001",
        "implementation": (
            "Persistent operation publishes only on loopback and uses only an "
            "internal bridge; the disposable test retains that bridge and adds "
            "one project-scoped non-internal bridge with IP masquerading disabled "
            "solely so Docker Engine can create the loopback mapping. Unneeded "
            "service interfaces remain disabled."
        ),
        "verification": "LOCAL_CONFIG_TEST_RUNTIME_NOT_EXECUTED",
    },
    {
        "id": "SEC-INFRA-006",
        "implementation": (
            "The raos-raw bucket is private and anonymous access is forbidden."
        ),
        "verification": "AUTHENTICATED_RUNTIME_FIXTURE_NOT_EXECUTED",
    },
    {
        "id": "SEC-SDLC-003",
        "implementation": (
            "The image tag, OCI index, linux/amd64 manifest, configuration "
            "digest, and reviewed source revision are pinned."
        ),
        "verification": "LOCAL_CONTRACT_TEST",
    },
    {
        "id": "SEC-SDLC-004",
        "implementation": (
            "A container vulnerability scan is required before validation and "
            "remains NOT_EXECUTED."
        ),
        "verification": "NOT_EXECUTED",
    },
]

EXPECTED_BOUNDARY = {
    "environment": "LOCAL_AND_CI_ONLY",
    "production_use": "FORBIDDEN",
    "remote_object_storage": "FORBIDDEN",
    "raw_credential_environment": "FORBIDDEN",
    "anonymous_access": "FORBIDDEN",
    "default_retention": "FORBIDDEN",
    "retention_period": "UNSET_HUMAN_DECISION_REQUIRED",
    "lifecycle_delete": "FORBIDDEN",
    "automatic_deletion": "DISABLED",
    "od_014": "HUMAN_DECISION_REQUIRED",
    "docker_runtime": "NOT_EXECUTED",
    "authenticated_s3_fixture": "NOT_EXECUTED",
    "object_lock_and_version_delete_regression": "NOT_EXECUTED",
    "container_vulnerability_scan": "NOT_EXECUTED",
    "formal_tst_014": "NOT_EXECUTED",
    "effective_canonical_status": "UNCHANGED",
}


def _require_exact(actual: object, expected: object, path: str) -> None:
    """Raise a path-specific error for type, key, length, or value drift."""

    if type(actual) is not type(expected):
        raise RuntimeError(f"{path} type differs")
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        if set(actual) != set(expected):
            raise RuntimeError(f"{path} keys differ")
        for key, expected_value in expected.items():
            _require_exact(actual[key], expected_value, f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list)
        if len(actual) != len(expected):
            raise RuntimeError(f"{path} length differs")
        for index, expected_value in enumerate(expected):
            _require_exact(actual[index], expected_value, f"{path}[{index}]")
        return
    if actual != expected:
        raise RuntimeError(f"{path} differs")


def validate_policy_contract(contract: object) -> Contract:
    """Validate ST-0202 policy fields not interpreted by the Compose renderer."""

    if not isinstance(contract, dict):
        raise RuntimeError("object-storage contract must be a mapping")
    expected_sections = {
        "document": EXPECTED_DOCUMENT,
        "image": EXPECTED_IMAGE,
        "compose": EXPECTED_COMPOSE,
        "runtime": EXPECTED_RUNTIME,
        "security_controls": EXPECTED_SECURITY_CONTROLS,
        "boundary": EXPECTED_BOUNDARY,
    }
    if set(contract) != set(expected_sections):
        raise RuntimeError("object-storage contract keys differ")
    for section, expected in expected_sections.items():
        _require_exact(contract[section], expected, section)
    return contract


@pytest.fixture(scope="session")
def object_storage_contract() -> Contract:
    """Load through the shared production YAML loader and validate policy fields."""

    return validate_policy_contract(
        generator.load_and_validate_object_contract(REPOSITORY_ROOT)
    )


@pytest.fixture
def mutable_contract(object_storage_contract: Contract) -> Contract:
    """Return a private mutable copy for one adversarial case."""

    return deepcopy(object_storage_contract)


@pytest.fixture
def reject_contract() -> RejectContract:
    """Assert that a mutated contract fails the exact policy validator."""

    def reject(mutated: Contract, message_pattern: str) -> None:
        with pytest.raises(RuntimeError, match=message_pattern):
            validate_policy_contract(mutated)

    return reject


@pytest.fixture
def reject_production_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> RejectProductionContract:
    """Inject a mutation and require the shared production validator to reject it."""

    real_load_yaml = strict_yaml.load_yaml

    def reject(mutated: Contract) -> None:
        def load_yaml(path: Path) -> object:
            if path == CONTRACT_FILE:
                return mutated
            return real_load_yaml(path)

        monkeypatch.setattr(strict_yaml, "load_yaml", load_yaml)
        with pytest.raises(RuntimeError):
            generator.load_and_validate_object_contract(REPOSITORY_ROOT)

    return reject
