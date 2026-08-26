#!/usr/bin/env python3
"""Build the cumulative, deterministic local/CI Docker Compose model."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

try:
    from scripts import build_st0201_postgres_service as st0201
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    import build_st0201_postgres_service as st0201  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
COMPOSE_PATH: Final = Path("docker-compose.yml")
MANIFEST_PATH: Final = Path("changes/st-0202/manifest.yaml")
ST0202_CONTRACT_PATH: Final = Path(
    "changes/st-0202/contracts/local-object-storage.v1.yaml"
)
PREDECESSOR_MANIFEST_PATH: Final = Path("changes/st-0201/manifest.yaml")
ARCHITECTURE_SNAPSHOT_PATH: Final = Path(
    "docs/architecture/ST-0202-object-storage-provider-snapshot.yaml"
)
OBJECT_STORAGE_WRAPPER_PATH: Final = Path("scripts/object_storage_service.sh")
GENERATED_PATHS: Final = (COMPOSE_PATH, MANIFEST_PATH)
GENERATOR_URI: Final = "repo://scripts/build_local_compose.py"
SOURCE_CONTRACT_URI: Final = f"repo://{ST0202_CONTRACT_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_local_compose.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"
COMPOSE_NAMESPACES: Final = ("services", "secrets", "volumes", "networks")

PINNED_CANONICAL_INPUTS: Final = {
    Path("docs/manifest.json"): (
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e"
    ),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"): (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"): (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    Path("docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"): (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"): (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"): (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    Path("docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml"): (
        "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d"
    ),
    Path("docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md"): (
        "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c"
    ),
    Path("docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md"): (
        "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3"
    ),
    Path("docs/canonical/08_codex/RAOS_14_codex_implementation_handbook_v1.0.md"): (
        "501858e7cdb47db5d2987f6e3d778da4fb8d72224b4380790dcd91ffcac615b2"
    ),
}

SEMANTIC_INPUT_PATHS: Final = (
    ST0202_CONTRACT_PATH,
    Path("changes/st-0202/README.md"),
    ARCHITECTURE_SNAPSHOT_PATH,
    PREDECESSOR_MANIFEST_PATH,
    Path("scripts/build_local_compose.py"),
    Path("scripts/build_st0201_postgres_service.py"),
    st0201.RUNTIME_WRAPPER_PATH,
    OBJECT_STORAGE_WRAPPER_PATH,
    Path("scripts/object_storage_fixture.py"),
    Path("tests/st0201/conftest.py"),
    Path("tests/st0201/test_contract.py"),
    Path("tests/st0201/test_generation.py"),
    Path("tests/st0201/test_negative_cases.py"),
    Path("tests/st0201/test_wrapper.py"),
    Path("tests/st0202/conftest.py"),
    Path("tests/st0202/test_contract.py"),
    Path("tests/st0202/test_fixture.py"),
    Path("tests/st0202/test_negative_cases.py"),
    Path("tests/st0202/test_wrapper.py"),
    Path("workspace-layout.json"),
    Path("infra/docker/README.md"),
)

EXPECTED_ST0202_IMAGE: Final = {
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
}
EXPECTED_ST0202_COMPOSE: Final = {
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
    "data": {
        "volume": "object_storage_data",
        "mount_path": "/data",
    },
    "network": {
        "name": "object_storage_internal",
        "driver": "bridge",
        "internal": True,
    },
    "command": [
        "mini",
        "-dir=/data",
        "-s3.config=/run/raos/object-storage-s3-config.json",
        "-s3.port=8333",
        "-master.telemetry=false",
        "-webdav=false",
        "-admin.ui=false",
        "-s3.port.iceberg=0",
        "-s3.allowDeleteBucketNotEmpty=false",
    ],
    "healthcheck": {
        "command": (
            "curl --fail --silent --show-error http://127.0.0.1:8333/status >/dev/null"
        ),
        "interval": "5s",
        "timeout": "5s",
        "retries": 12,
        "start_period": "10s",
    },
}
EXPECTED_ST0202_EPHEMERAL_OVERRIDE: Final = {
    "command": "test",
    "tracked_artifact": "ABSENT",
    "creation_executable": "/usr/bin/mktemp",
    "filename_template": "object-storage-disposable-port.override.XXXXXXXX.yml",
    "parent_directory_mode": "0700",
    "file_mode": "0600",
    "maximum_bytes": 512,
    "exact_bytes": 382,
    "sha256": "92e141f0c1b96ef47cf79855951d6cadaec509b9796cc03067186ff44dd27239",
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
    "compose_file_order": ["docker-compose.yml", "EPHEMERAL_VALIDATED_OVERRIDE"],
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
}
EXPECTED_ST0202_RUNTIME_VERSION_LINE: Final = "version 30GB 4.29 1355c7a10 linux amd64"
EXPECTED_ST0202_DOCUMENT: Final = {
    "id": "RAOS-LOCAL-OBJECT-STORAGE-001",
    "version": "1.0.0",
    "story_id": "ST-0202",
    "status": "LOCAL_AND_CI_CANDIDATE",
    "formal_verification": "NOT_EXECUTED",
}
EXPECTED_ST0202_RUNTIME_GATES: Final = {
    "wrapper": "repo://scripts/object_storage_service.sh",
    "fixture_client": "repo://scripts/object_storage_fixture.py",
    "interface": "scripts/object_storage_service.sh --docker EXECUTABLE COMMAND",
    "commands": ["config", "up", "check", "down", "test"],
    "docker_host": "unix:///var/run/docker.sock",
    "minimum_compose_version": "2.24.4",
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
}
EXPECTED_ST0202_SECURITY_VERIFICATIONS: Final = {
    "SEC-DATA-003": "LOCAL_CONTRACT_AND_SECRET_SCAN",
    "SEC-DATA-004": "LOCAL_CONTRACT_TEST_RUNTIME_NOT_EXECUTED",
    "SEC-DATA-008": "HUMAN_DECISION_AND_RUNTIME_TEST_REQUIRED",
    "SEC-INFRA-001": "LOCAL_CONFIG_TEST_RUNTIME_NOT_EXECUTED",
    "SEC-INFRA-006": "AUTHENTICATED_RUNTIME_FIXTURE_NOT_EXECUTED",
    "SEC-SDLC-003": "LOCAL_CONTRACT_TEST",
    "SEC-SDLC-004": "NOT_EXECUTED",
}
EXPECTED_ST0202_BOUNDARY: Final = {
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

FORBIDDEN_SERVICE_KEYS: Final = frozenset(
    {
        "build",
        "cap_add",
        "container_name",
        "devices",
        "env_file",
        "external_links",
        "network_mode",
        "pid",
        "privileged",
        "userns_mode",
    }
)


@dataclass(frozen=True)
class Component:
    """One reviewed Story contribution to the cumulative Compose namespace."""

    story_id: str
    contract_path: Path
    renderer_name: str


ORDERED_COMPONENTS: Final = (
    Component("ST-0201", st0201.CONTRACT_PATH, "render_st0201_component"),
    Component("ST-0202", ST0202_CONTRACT_PATH, "render_st0202_component"),
)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"{label} must be a string-keyed mapping")
    return value


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a list")
    return value


def _require_selected_fields(
    value: object, expected: Mapping[str, object], label: str
) -> Mapping[str, Any]:
    mapping = _mapping(value, label)
    missing = set(expected) - set(mapping)
    if missing:
        raise RuntimeError(f"{label} keys differ: missing={sorted(missing)}")
    selected = {key: mapping[key] for key in expected}
    st0201._require_exact(selected, dict(expected), label)
    return mapping


def load_and_validate_object_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Load ST-0202 and validate its complete reviewed contract, fail closed."""

    path = st0201._repository_regular_file(
        root, ST0202_CONTRACT_PATH, "object-storage contract"
    )
    contract = _mapping(st0201.load_yaml(path), "object-storage contract")
    st0201._require_exact(
        set(contract),
        {"document", "image", "compose", "runtime", "security_controls", "boundary"},
        "object-storage top-level keys",
    )
    document = _mapping(contract.get("document"), "object-storage document")
    st0201._require_exact(
        dict(document), EXPECTED_ST0202_DOCUMENT, "object-storage document"
    )
    image = _mapping(contract.get("image"), "object-storage image")
    _require_selected_fields(image, EXPECTED_ST0202_IMAGE, "object-storage image")
    compose = _mapping(contract.get("compose"), "object-storage compose")
    st0201._require_exact(
        dict(compose), EXPECTED_ST0202_COMPOSE, "object-storage compose"
    )
    runtime = _mapping(contract.get("runtime"), "object-storage runtime")
    _require_selected_fields(
        runtime, EXPECTED_ST0202_RUNTIME_GATES, "object-storage runtime"
    )
    ephemeral_override = _mapping(
        runtime.get("ephemeral_port_override"),
        "object-storage runtime.ephemeral_port_override",
    )
    st0201._require_exact(
        dict(ephemeral_override),
        EXPECTED_ST0202_EPHEMERAL_OVERRIDE,
        "object-storage runtime.ephemeral_port_override",
    )
    st0201._require_exact(
        runtime.get("expected_version_line"),
        EXPECTED_ST0202_RUNTIME_VERSION_LINE,
        "object-storage runtime.expected_version_line",
    )
    controls = _list(contract.get("security_controls"), "object-storage controls")
    observed_controls: dict[str, object] = {}
    for index, value in enumerate(controls):
        row = _mapping(value, f"object-storage controls[{index}]")
        control_id = row.get("id")
        if type(control_id) is not str or control_id in observed_controls:
            raise RuntimeError("object-storage security control IDs differ")
        observed_controls[control_id] = row.get("verification")
    st0201._require_exact(
        observed_controls,
        EXPECTED_ST0202_SECURITY_VERIFICATIONS,
        "object-storage security control verification",
    )
    boundary = _mapping(contract.get("boundary"), "object-storage boundary")
    st0201._require_exact(
        dict(boundary), EXPECTED_ST0202_BOUNDARY, "object-storage boundary"
    )
    return dict(contract)


def render_st0201_component(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Render only the exact ST-0201-owned Compose namespaces."""

    image = _mapping(contract["image"], "ST-0201 image")
    compose = _mapping(contract["compose"], "ST-0201 compose")
    service = _mapping(compose["service"], "ST-0201 compose.service")
    port = _mapping(compose["port"], "ST-0201 compose.port")
    password_spec = _mapping(
        compose["password_secret"], "ST-0201 compose.password_secret"
    )
    data = _mapping(compose["data"], "ST-0201 compose.data")
    network = _mapping(compose["network"], "ST-0201 compose.network")
    health = _mapping(compose["healthcheck"], "ST-0201 compose.healthcheck")
    service_name = str(service["name"])
    secret_name = str(password_spec["name"])
    volume_name = str(data["volume"])
    network_name = str(network["name"])
    return {
        "services": {
            service_name: {
                "image": image["reference"],
                "platform": service["platform"],
                "pull_policy": "always",
                "init": service["init"],
                "restart": service["restart"],
                "stop_grace_period": service["stop_grace_period"],
                "environment": {
                    "POSTGRES_DB": service["database"],
                    "POSTGRES_USER": service["user"],
                    "POSTGRES_PASSWORD_FILE": password_spec["mount_path"],
                    "PGDATA": data["pgdata"],
                },
                "ports": [
                    f"{port['host_ip']}:${{{port['variable']}-{port['default']}}}:"
                    f"{port['container']}/{port['protocol']}"
                ],
                "secrets": [{"source": secret_name, "target": secret_name}],
                "volumes": [f"{volume_name}:{data['mount_path']}"],
                "networks": [network_name],
                "healthcheck": {
                    "test": ["CMD-SHELL", health["command"]],
                    "interval": health["interval"],
                    "timeout": health["timeout"],
                    "retries": health["retries"],
                    "start_period": health["start_period"],
                },
            }
        },
        "secrets": {
            secret_name: {
                "file": (
                    f"${{{password_spec['source_variable']}:-"
                    f"{password_spec['source_default']}}}"
                )
            }
        },
        "volumes": {volume_name: None},
        "networks": {
            network_name: {
                "driver": network["driver"],
                "internal": network["internal"],
            }
        },
    }


def render_st0202_component(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Render only the exact ST-0202-owned Compose namespaces."""

    document = _mapping(contract.get("document"), "object-storage document")
    st0201._require_exact(
        document.get("story_id"), "ST-0202", "object-storage document.story_id"
    )
    image = _require_selected_fields(
        contract.get("image"), EXPECTED_ST0202_IMAGE, "object-storage image"
    )
    compose = _mapping(contract.get("compose"), "object-storage compose")
    st0201._require_exact(
        dict(compose), EXPECTED_ST0202_COMPOSE, "object-storage compose"
    )
    service = _mapping(compose["service"], "object-storage compose.service")
    port = _mapping(compose["port"], "object-storage compose.port")
    config_spec = _mapping(
        compose["config_secret"], "object-storage compose.config_secret"
    )
    secret_staging = _mapping(
        compose["secret_staging"], "object-storage compose.secret_staging"
    )
    data = _mapping(compose["data"], "object-storage compose.data")
    network = _mapping(compose["network"], "object-storage compose.network")
    health = _mapping(compose["healthcheck"], "object-storage compose.healthcheck")
    service_name = str(service["name"])
    secret_name = str(config_spec["name"])
    volume_name = str(data["volume"])
    network_name = str(network["name"])
    staging_path = str(secret_staging["path"])
    staging_script = (
        f"umask 077; cp {config_spec['mount_path']} {staging_path}; "
        f"chown {secret_staging['uid']}:{secret_staging['gid']} {staging_path}; "
        f"chmod {secret_staging['mode']} {staging_path}; "
        f"chown {secret_staging['directory_uid']}:"
        f"{secret_staging['directory_gid']} {secret_staging['directory']}; "
        f"chmod {secret_staging['directory_mode']} {secret_staging['directory']}; "
        f"chmod {secret_staging['source_directory_mode']} "
        f"{secret_staging['source_directory']}; "
        'exec /entrypoint.sh "$$@"'
    )
    return {
        "services": {
            service_name: {
                "image": image["reference"],
                "platform": service["platform"],
                "pull_policy": "always",
                "init": service["init"],
                "restart": service["restart"],
                "stop_grace_period": service["stop_grace_period"],
                "entrypoint": ["/bin/sh", "-eu", "-c"],
                "command": [
                    staging_script,
                    "raos-object-storage",
                    *_list(compose["command"], "object-storage command"),
                ],
                "ports": [
                    {
                        "target": port["container"],
                        "published": (f"${{{port['variable']}-{port['default']}}}"),
                        "host_ip": port["host_ip"],
                        "protocol": port["protocol"],
                    }
                ],
                "secrets": [
                    {
                        "source": secret_name,
                        "target": config_spec["mount_path"],
                        "mode": "0400",
                    }
                ],
                "tmpfs": [
                    f"{secret_staging['directory']}:{secret_staging['tmpfs_options']}"
                ],
                "volumes": [f"{volume_name}:{data['mount_path']}"],
                "networks": [network_name],
                "healthcheck": {
                    "test": ["CMD-SHELL", health["command"]],
                    "interval": health["interval"],
                    "timeout": health["timeout"],
                    "retries": health["retries"],
                    "start_period": health["start_period"],
                },
            }
        },
        "secrets": {
            secret_name: {
                "file": (
                    f"${{{config_spec['source_variable']}:-"
                    f"{config_spec['source_default']}}}"
                )
            }
        },
        "volumes": {volume_name: None},
        "networks": {
            network_name: {
                "driver": network["driver"],
                "internal": network["internal"],
            }
        },
    }


def _component_for_story(story_id: str, root: Path) -> Mapping[str, Any]:
    if story_id == "ST-0201":
        return render_st0201_component(st0201.load_and_validate_contract(root))
    if story_id == "ST-0202":
        return render_st0202_component(load_and_validate_object_contract(root))
    raise RuntimeError(f"unknown Compose component Story: {story_id}")


def _validate_component(component: Mapping[str, Any], story_id: str) -> None:
    if tuple(component) != COMPOSE_NAMESPACES:
        raise RuntimeError(
            f"{story_id} Compose component namespaces differ from the reviewed order"
        )
    for namespace in COMPOSE_NAMESPACES:
        values = _mapping(component[namespace], f"{story_id} {namespace}")
        if not values:
            raise RuntimeError(f"{story_id} {namespace} namespace must not be empty")


def _reference_name(value: object, label: str) -> str:
    if isinstance(value, str) and value:
        return value
    mapping = _mapping(value, label)
    source = mapping.get("source")
    if not isinstance(source, str) or not source:
        raise RuntimeError(f"{label}.source must be a non-empty string")
    return source


def validate_compose_model(model: Mapping[str, Any]) -> None:
    """Reject namespace collisions, dangling references, and unsafe capabilities."""

    if tuple(model) != COMPOSE_NAMESPACES:
        raise RuntimeError(
            "cumulative Compose namespaces differ from the reviewed order"
        )
    namespaces = {
        name: _mapping(model[name], f"cumulative {name}") for name in COMPOSE_NAMESPACES
    }
    services = namespaces["services"]
    for service_name, raw_service in services.items():
        service = _mapping(raw_service, f"service {service_name}")
        forbidden = FORBIDDEN_SERVICE_KEYS & set(service)
        if forbidden:
            raise RuntimeError(
                f"service {service_name} uses forbidden keys: {sorted(forbidden)}"
            )
        for index, reference in enumerate(
            _list(service.get("secrets", []), f"service {service_name}.secrets")
        ):
            name = _reference_name(
                reference, f"service {service_name}.secrets[{index}]"
            )
            if name not in namespaces["secrets"]:
                raise RuntimeError(
                    f"service {service_name} references missing secret {name}"
                )
        for index, reference in enumerate(
            _list(service.get("volumes", []), f"service {service_name}.volumes")
        ):
            name = _reference_name(
                reference, f"service {service_name}.volumes[{index}]"
            )
            if isinstance(reference, str):
                name = reference.split(":", 1)[0]
            if name.startswith(("/", "./", "../")) or name not in namespaces["volumes"]:
                raise RuntimeError(
                    f"service {service_name} references missing or unsafe volume {name}"
                )
        for index, reference in enumerate(
            _list(service.get("networks", []), f"service {service_name}.networks")
        ):
            name = _reference_name(
                reference, f"service {service_name}.networks[{index}]"
            )
            if name not in namespaces["networks"]:
                raise RuntimeError(
                    f"service {service_name} references missing network {name}"
                )
        depends_on = service.get("depends_on", [])
        if isinstance(depends_on, Mapping):
            dependency_names = list(depends_on)
        else:
            dependency_names = _list(depends_on, f"service {service_name}.depends_on")
        for dependency in dependency_names:
            if not isinstance(dependency, str) or dependency not in services:
                raise RuntimeError(
                    f"service {service_name} references missing dependency {dependency}"
                )


def assemble_compose(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Merge reviewed components in Story order with no implicit override behavior."""

    merged: dict[str, dict[str, Any]] = {name: {} for name in COMPOSE_NAMESPACES}
    owners: dict[tuple[str, str], str] = {}
    for definition in ORDERED_COMPONENTS:
        component = _mapping(
            _component_for_story(definition.story_id, root), definition.story_id
        )
        _validate_component(component, definition.story_id)
        for namespace in COMPOSE_NAMESPACES:
            for name, value in _mapping(
                component[namespace], f"{definition.story_id} {namespace}"
            ).items():
                key = (namespace, name)
                if key in owners:
                    raise RuntimeError(
                        f"duplicate Compose {namespace} name {name!r}: "
                        f"{owners[key]} and {definition.story_id}"
                    )
                owners[key] = definition.story_id
                merged[namespace][name] = value
    validate_compose_model(merged)
    return merged


def render_compose(root: Path = REPO_ROOT) -> bytes:
    header = (
        "# Generated by scripts/build_local_compose.py. Do not edit.\n"
        "# Ordered source contracts: "
        "repo://changes/st-0201/contracts/local-postgres.v1.yaml, "
        "repo://changes/st-0202/contracts/local-object-storage.v1.yaml\n"
        f"# Generation command: {GENERATION_COMMAND}\n"
        "# Local/CI candidates only; formal TST-008 and TST-014 remain separately gated.\n"
    )
    body = yaml.dump(
        assemble_compose(root),
        Dumper=st0201.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    )
    return (header + body).encode("utf-8")


def _validate_pinned_file(
    root: Path, relative: Path, expected_sha256: str, label: str
) -> Path:
    path = st0201._repository_regular_file(root, relative, label)
    actual = st0201.sha256_file(path)
    if actual != expected_sha256:
        raise RuntimeError(
            f"{label} hash mismatch: expected {expected_sha256}, found {actual}"
        )
    return path


def _validate_predecessor_manifest(root: Path) -> None:
    path = st0201._repository_regular_file(
        root, PREDECESSOR_MANIFEST_PATH, "ST-0201 predecessor manifest"
    )
    predecessor = _mapping(st0201.load_yaml(path), "ST-0201 predecessor manifest")
    document = _mapping(
        predecessor.get("document"), "ST-0201 predecessor manifest.document"
    )
    st0201._require_exact(
        document.get("story_id"),
        "ST-0201",
        "ST-0201 predecessor manifest.document.story_id",
    )
    generated = _list(
        predecessor.get("generated_artifacts"),
        "ST-0201 predecessor manifest.generated_artifacts",
    )
    if len(generated) != 1:
        raise RuntimeError(
            "ST-0201 predecessor manifest must attest exactly one generated artifact"
        )
    artifact = _mapping(
        generated[0], "ST-0201 predecessor manifest.generated_artifacts[0]"
    )
    st0201._require_exact(
        artifact.get("uri"),
        "repo://docker-compose.yml",
        "ST-0201 predecessor generated artifact URI",
    )


def _validate_manifest_provenance(root: Path) -> None:
    for relative, digest in PINNED_CANONICAL_INPUTS.items():
        _validate_pinned_file(root, relative, digest, f"canonical input {relative}")
    _validate_predecessor_manifest(root)


def _semantic_input_record(root: Path, relative: Path) -> dict[str, object]:
    st0201._repository_regular_file(root, relative, "semantic input")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "semantic_id": relative.as_posix(),
        "version": 2,
    }


def render_manifest(root: Path, compose_content: bytes) -> bytes:
    """Render the active ST-0202 attestation over the cumulative Compose file."""

    _validate_manifest_provenance(root)
    contract = load_and_validate_object_contract(root)
    image = _mapping(contract["image"], "object-storage image")
    platform = _mapping(image["platform"], "object-storage image.platform")
    boundary = _mapping(contract["boundary"], "object-storage boundary")
    semantic_inputs = [
        _semantic_input_record(root, relative) for relative in SEMANTIC_INPUT_PATHS
    ]
    generated_artifacts = [
        {
            "uri": f"repo://{COMPOSE_PATH.as_posix()}",
            "bytes": len(compose_content),
            "sha256": st0201.sha256_bytes(compose_content),
        }
    ]
    manifest = {
        "document": {
            "id": "RAOS-LOCAL-OBJECT-STORAGE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0202",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_uri": SOURCE_CONTRACT_URI,
            "architecture_snapshot": {
                "uri": f"repo://{ARCHITECTURE_SNAPSHOT_PATH.as_posix()}",
                "semantic_id": ARCHITECTURE_SNAPSHOT_PATH.as_posix(),
                "version": 2,
            },
            "canonical_inputs": [
                {"uri": f"repo://{relative.as_posix()}", "sha256": digest}
                for relative, digest in PINNED_CANONICAL_INPUTS.items()
            ],
            "image": {
                "reference": image["reference"],
                "index_digest": image["index_digest"],
                "linux_amd64_manifest_digest": platform["manifest_digest"],
                "config_digest": platform["config_digest"],
            },
            "predecessor_manifest": {
                "uri": f"repo://{PREDECESSOR_MANIFEST_PATH.as_posix()}",
                "owner_id": "build_st0201_postgres_service",
                "owner_version": 2,
                "story_id": "ST-0201",
            },
        },
        "stack": {"stories": ["ST-0201", "ST-0202"]},
        "semantic_input_count": len(semantic_inputs),
        "semantic_inputs": semantic_inputs,
        "generated_artifact_count": len(generated_artifacts),
        "generated_artifacts": generated_artifacts,
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": dict(boundary),
    }
    return yaml.dump(
        manifest,
        Dumper=st0201.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    compose_content = render_compose(root)
    return {
        COMPOSE_PATH: compose_content,
        MANIFEST_PATH: render_manifest(root, compose_content),
    }


def install_outputs(outputs: Mapping[Path, bytes], root: Path = REPO_ROOT) -> None:
    if set(outputs) != set(GENERATED_PATHS):
        raise RuntimeError("generated output inventory differs from the reviewed set")
    staged: dict[Path, Path] = {}
    targets: dict[Path, Path] = {}
    previous: dict[Path, bytes | None] = {}
    installed: list[Path] = []
    try:
        for relative in GENERATED_PATHS:
            content = outputs[relative]
            if not isinstance(content, bytes):
                raise RuntimeError(f"generated output must be bytes: {relative}")
            parent = st0201._safe_parent(root, relative)
            target = parent / relative.name
            if target.is_symlink():
                raise RuntimeError(f"generated target cannot be a symlink: {target}")
            if target.exists() and not target.is_file():
                raise RuntimeError(f"generated target must be a regular file: {target}")
            targets[relative] = target
            previous[relative] = target.read_bytes() if target.exists() else None
            staged[relative] = st0201._stage_file(parent, relative.name, content)
        for relative in GENERATED_PATHS:
            target = targets[relative]
            os.replace(staged[relative], target)
            staged.pop(relative)
            st0201._fsync_directory(target.parent)
            installed.append(relative)
    except BaseException as install_error:
        rollback_errors: list[str] = []
        for relative in reversed(installed):
            target = targets[relative]
            old_content = previous[relative]
            try:
                if old_content is None:
                    target.unlink(missing_ok=True)
                    st0201._fsync_directory(target.parent)
                else:
                    replacement = st0201._stage_file(
                        target.parent, target.name, old_content
                    )
                    try:
                        os.replace(replacement, target)
                        st0201._fsync_directory(target.parent)
                    finally:
                        replacement.unlink(missing_ok=True)
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


def _validate_object_wrapper_compose_binding(
    root: Path, compose_content: bytes
) -> None:
    wrapper = st0201._repository_regular_file(
        root, OBJECT_STORAGE_WRAPPER_PATH, "object-storage runtime wrapper"
    )
    prefix = "readonly expected_compose_sha256="
    bindings = [
        line
        for line in wrapper.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    ]
    expected = f"{prefix}'{st0201.sha256_bytes(compose_content)}'"
    if bindings != [expected]:
        raise RuntimeError(
            "object-storage runtime wrapper Compose digest binding drifted"
        )


def check_generated(root: Path = REPO_ROOT) -> None:
    expected = render_outputs(root)
    for relative in GENERATED_PATHS:
        target = st0201._repository_regular_file(root, relative, "generated artifact")
        if target.stat().st_mode & 0o022:
            raise RuntimeError(
                f"generated artifact is group/world writable: {relative}"
            )
        if target.read_bytes() != expected[relative]:
            raise RuntimeError(f"generated artifact drift: {relative}")
    st0201.validate_wrapper_compose_binding(root, expected[COMPOSE_PATH])
    _validate_object_wrapper_compose_binding(root, expected[COMPOSE_PATH])


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the cumulative Compose file and active manifest without writing",
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
                "component_story_ids": [item.story_id for item in ORDERED_COMPONENTS],
                "generated_artifacts": len(GENERATED_PATHS),
                "mode": mode,
                "status": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
