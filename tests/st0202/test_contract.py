"""Positive contract, cumulative Compose, and evidence-boundary tests for ST-0202."""

from __future__ import annotations

from typing import Any

import yaml

from conftest import (
    EXPECTED_BOUNDARY,
    EXPECTED_COMMAND,
    EXPECTED_COMPOSE,
    EXPECTED_DOCUMENT,
    EXPECTED_IMAGE,
    EXPECTED_RUNTIME,
    EXPECTED_SECURITY_CONTROLS,
    REPOSITORY_ROOT,
    SNAPSHOT_FILE,
)
from scripts import build_local_compose as generator
from scripts import build_st0201_postgres_service as strict_yaml


EXPECTED_REFERENCE = (
    "docker.io/chrislusf/seaweedfs:4.29@sha256:"
    "d47c7ee99fcb951351d7194915f4e3a5ea604a8e8871183d713907dec4fb9bf5"
)
EXPECTED_STAGE_SCRIPT = (
    "umask 077; cp /run/secrets/object_storage_s3_config "
    "/run/raos/object-storage-s3-config.json; chown 1000:1000 "
    "/run/raos/object-storage-s3-config.json; chmod 0400 "
    "/run/raos/object-storage-s3-config.json; chown 1000:1000 /run/raos; "
    "chmod 0700 /run/raos; chmod 0700 /run/secrets; "
    'exec /entrypoint.sh "$$@"'
)


def _rendered_compose() -> dict[str, Any]:
    value = yaml.safe_load(generator.render_compose(REPOSITORY_ROOT))
    assert isinstance(value, dict)
    return value


def test_contract_has_only_the_reviewed_sections_and_honest_status(
    object_storage_contract: dict[str, Any],
) -> None:
    assert set(object_storage_contract) == {
        "document",
        "image",
        "compose",
        "runtime",
        "security_controls",
        "boundary",
    }
    assert object_storage_contract["document"] == EXPECTED_DOCUMENT
    assert object_storage_contract["boundary"] == EXPECTED_BOUNDARY
    assert object_storage_contract["document"]["formal_verification"] == (
        "NOT_EXECUTED"
    )
    assert object_storage_contract["boundary"]["effective_canonical_status"] == (
        "UNCHANGED"
    )


def test_image_identity_pins_index_platform_manifest_config_and_source_revision(
    object_storage_contract: dict[str, Any],
) -> None:
    image = object_storage_contract["image"]
    assert image == EXPECTED_IMAGE
    assert image["reference"] == EXPECTED_REFERENCE
    assert image["tag"] == "4.29"
    assert image["platform"] == {
        "os": "linux",
        "architecture": "amd64",
        "manifest_digest": (
            "sha256:f16591b02e7a1d79dca57801405eec2c784711436edf65c0aa6394ef52800a3e"
        ),
        "config_digest": (
            "sha256:10b004ca7cc8ee13615dbe670e1be047270ab30a742a5944e82330017d64d8fd"
        ),
    }
    assert (
        image["expected_config"]["labels"]["org.opencontainers.image.revision"]
        == "1355c7a102194d6c461baf090eff50367b575afb"
    )


def test_compose_contract_is_exact_and_disables_unneeded_interfaces(
    object_storage_contract: dict[str, Any],
) -> None:
    compose = object_storage_contract["compose"]
    assert compose == EXPECTED_COMPOSE
    assert compose["command"] == EXPECTED_COMMAND
    assert len(compose["command"]) == 9
    assert {
        "-master.telemetry=false",
        "-webdav=false",
        "-admin.ui=false",
        "-s3.port.iceberg=0",
        "-s3.allowDeleteBucketNotEmpty=false",
    }.issubset(compose["command"])


def test_installed_compose_is_cumulative_and_has_exact_object_service() -> None:
    compose = _rendered_compose()
    assert set(compose) == {"services", "secrets", "volumes", "networks"}
    assert {"postgres", "object-storage"}.issubset(compose["services"])
    service = compose["services"]["object-storage"]
    assert service["image"] == EXPECTED_REFERENCE
    assert service["platform"] == "linux/amd64"
    assert service["pull_policy"] == "always"
    assert service["init"] is True
    assert service["restart"] == "no"
    assert service["stop_grace_period"] == "30s"
    assert service["entrypoint"] == ["/bin/sh", "-eu", "-c"]
    assert service["command"] == [
        EXPECTED_STAGE_SCRIPT,
        "raos-object-storage",
        *EXPECTED_COMMAND,
    ]
    assert service["tmpfs"] == [
        "/run/raos:rw,noexec,nosuid,nodev,size=64k,mode=0700,uid=0,gid=0"
    ]


def test_static_identity_is_only_a_file_backed_compose_secret() -> None:
    rendered = generator.render_compose(REPOSITORY_ROOT).decode("utf-8")
    compose = yaml.safe_load(rendered)
    service = compose["services"]["object-storage"]
    assert compose["secrets"]["object_storage_s3_config"] == {
        "file": (
            "${RAOS_OBJECT_STORAGE_S3_CONFIG_FILE:-"
            ".secrets/object-storage-s3-config.json}"
        )
    }
    assert service["secrets"] == [
        {
            "source": "object_storage_s3_config",
            "target": "/run/secrets/object_storage_s3_config",
            "mode": "0400",
        }
    ]
    assert "environment" not in service
    assert "AWS_ACCESS_KEY_ID" not in rendered
    assert "AWS_SECRET_ACCESS_KEY" not in rendered
    assert "accessKey" not in rendered
    assert "secretKey" not in rendered
    assert "/run/secrets/object_storage_s3_config" in EXPECTED_STAGE_SCRIPT
    assert "/run/raos/object-storage-s3-config.json" in EXPECTED_STAGE_SCRIPT
    assert "chown 1000:1000" in EXPECTED_STAGE_SCRIPT
    assert "chmod 0400" in EXPECTED_STAGE_SCRIPT
    assert "chown 1000:1000 /run/raos" in EXPECTED_STAGE_SCRIPT
    assert "chmod 0700 /run/raos" in EXPECTED_STAGE_SCRIPT
    assert "chmod 0700 /run/secrets" in EXPECTED_STAGE_SCRIPT


def test_storage_mount_network_and_host_publish_are_private_by_default() -> None:
    compose = _rendered_compose()
    service = compose["services"]["object-storage"]
    assert service["ports"] == [
        {
            "target": 8333,
            "published": "${RAOS_OBJECT_STORAGE_PORT-8333}",
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        }
    ]
    assert service["volumes"] == ["object_storage_data:/data"]
    assert compose["volumes"]["object_storage_data"] is None
    assert service["networks"] == ["object_storage_internal"]
    assert compose["networks"]["object_storage_internal"] == {
        "driver": "bridge",
        "internal": True,
    }
    assert "network_mode" not in service
    assert "privileged" not in service
    assert "/var/run/docker.sock" not in service.get("volumes", [])


def test_healthcheck_is_bounded_readiness_not_authenticated_acceptance(
    object_storage_contract: dict[str, Any],
) -> None:
    health = _rendered_compose()["services"]["object-storage"]["healthcheck"]
    assert health == {
        "test": [
            "CMD-SHELL",
            (
                "curl --fail --silent --show-error "
                "http://127.0.0.1:8333/status >/dev/null"
            ),
        ],
        "interval": "5s",
        "timeout": "5s",
        "retries": 12,
        "start_period": "10s",
    }
    readiness = object_storage_contract["runtime"]["readiness"]
    assert readiness["classification"] == "PROCESS_READINESS_ONLY"
    assert readiness["authenticated_acceptance_required"] is True


def test_runtime_requires_authenticated_versioned_integrity_fixture(
    object_storage_contract: dict[str, Any],
) -> None:
    runtime = object_storage_contract["runtime"]
    assert runtime == EXPECTED_RUNTIME
    assert runtime["docker_host"] == "unix:///var/run/docker.sock"
    assert runtime["expected_platform"] == "linux/amd64"
    process_model = runtime["expected_process_model"]
    assert process_model["host_config_init"] is True
    assert process_model["init"] == {
        "pid": 1,
        "parent_pid": 0,
        "uids": [0, 0, 0, 0],
        "gids": [0, 0, 0, 0],
        "executable": "/sbin/docker-init",
    }
    assert process_model["server"] == {
        "direct_child_count": 1,
        "parent_pid": 1,
        "uids": [1000, 1000, 1000, 1000],
        "gids": [1000, 1000, 1000, 1000],
        "effective_capabilities": "0000000000000000",
        "executable": "/usr/bin/weed",
        "zombie_state": "FORBIDDEN",
    }
    assert (
        runtime["expected_image_labels"]
        == (object_storage_contract["image"]["expected_config"]["labels"])
    )
    fixture = runtime["authenticated_fixture"]
    assert fixture["required"] is True
    assert fixture["formal_suite"] == "TST-014"
    assert fixture["execution_status"] == "NOT_EXECUTED"
    assert "put-two-object-versions" in fixture["operations"]
    assert "get-each-version-by-id" in fixture["operations"]
    assert "reject-declared-hash-mismatch" in fixture["operations"]


def test_runtime_ephemeral_override_contract_is_exact_and_untracked(
    object_storage_contract: dict[str, Any],
) -> None:
    override = object_storage_contract["runtime"]["ephemeral_port_override"]
    template = b"""services:
  object-storage:
    ports: !override
      - target: 8333
        host_ip: 127.0.0.1
        protocol: tcp
    networks: !override
      - object_storage_internal
      - object_storage_disposable_publish
networks:
  object_storage_disposable_publish:
    driver: bridge
    internal: false
    driver_opts:
      com.docker.network.bridge.enable_ip_masquerade: "false"
"""
    assert len(template) == override["exact_bytes"] == 382
    assert generator.st0201.sha256_bytes(template) == override["sha256"]
    assert override["tracked_artifact"] == "ABSENT"
    assert override["creation_executable"] == "/usr/bin/mktemp"
    assert override["compose_file_order"] == [
        "docker-compose.yml",
        "EPHEMERAL_VALIDATED_OVERRIDE",
    ]
    assert override["published"] == "OMITTED_ENGINE_ASSIGNED"
    assert override["service_networks"] == [
        "object_storage_internal",
        "object_storage_disposable_publish",
    ]
    assert override["publish_network"] == {
        "name": "object_storage_disposable_publish",
        "driver": "bridge",
        "internal": False,
        "driver_opts": {
            "com.docker.network.bridge.enable_ip_masquerade": "false",
        },
        "scope": "DISPOSABLE_PROJECT_ONLY",
    }
    assert override["observed_mapping"] == {
        "exact_count": 1,
        "host": "127.0.0.1",
        "lexical_port_rule": "^[0-9]{1,5}$",
        "minimum_port": 1024,
        "maximum_port": 65535,
    }
    assert b"published" not in template
    assert b"object_storage_internal" in template
    assert b"object_storage_disposable_publish" in template
    assert b'com.docker.network.bridge.enable_ip_masquerade: "false"\n' in template
    assert b"${" not in template
    assert b"#" not in template


def test_bucket_contract_is_private_versioned_hash_bound_and_retention_safe(
    object_storage_contract: dict[str, Any],
) -> None:
    bucket = object_storage_contract["runtime"]["bucket"]
    assert bucket["name"] == "raos-raw"
    assert bucket["visibility"] == "PRIVATE"
    assert bucket["object_lock_capability_at_creation"] == "REQUIRED"
    assert bucket["versioning"] == "REQUIRED"
    assert bucket["required_metadata"] == [
        "sha256",
        "content-type",
        "source",
        "acquired-at",
        "retention-class",
    ]
    assert bucket["hash_mismatch"] == "REJECT"
    assert bucket["retention_hook"] == "REQUIRED_POLICY_PERIOD_UNSET"
    assert bucket["default_retention"] == "FORBIDDEN"
    assert bucket["retention_period"] == "UNSET_HUMAN_DECISION_REQUIRED"
    assert bucket["lifecycle_delete"] == "FORBIDDEN"
    assert bucket["automatic_deletion"] == "DISABLED"


def test_security_controls_have_exact_canonical_trace(
    object_storage_contract: dict[str, Any],
) -> None:
    controls = object_storage_contract["security_controls"]
    assert controls == EXPECTED_SECURITY_CONTROLS
    assert [row["id"] for row in controls] == [
        "SEC-DATA-003",
        "SEC-DATA-004",
        "SEC-DATA-008",
        "SEC-INFRA-001",
        "SEC-INFRA-006",
        "SEC-SDLC-003",
        "SEC-SDLC-004",
    ]
    assert controls[-1]["verification"] == "NOT_EXECUTED"


def test_canonical_story_suite_decision_and_security_records_match() -> None:
    backlog = strict_yaml.load_yaml(
        REPOSITORY_ROOT / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    )
    story = next(row for row in backlog["stories"] if row["id"] == "ST-0202")
    assert story == {
        "id": "ST-0202",
        "epic_id": "EPIC-02",
        "title": "Local S3-compatible object service",
        "objective": "Raw/Snapshot用Local storage",
        "depends_on": ["ST-0102"],
        "requirement_ids": [],
        "design_refs": [],
        "deliverables": ["service", "bucket bootstrap"],
        "acceptance_criteria": ["put/get/version fixture"],
        "test_suites": ["TST-014"],
        "priority": "P0",
        "mvp": True,
        "size": "S",
        "open_decisions": [],
        "one_pr_preferred": True,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }

    suites = strict_yaml.load_yaml(
        REPOSITORY_ROOT / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    )
    suite = next(row for row in suites["suites"] if row["id"] == "TST-014")
    assert suite["purpose"] == "Hash、version、tamper、retention hooks"
    assert suite["release_blocking"] is True
    assert suite["environments"] == ["CI"]
    assert suite["implementation_status"] == "NOT_STARTED"
    assert suite["execution_status"] == "NOT_EXECUTED"

    decisions = strict_yaml.load_yaml(
        REPOSITORY_ROOT
        / "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
    )
    decision = next(row for row in decisions["items"] if row["id"] == "OD-014")
    assert decision == {
        "id": "OD-014",
        "topic": "retention_periods",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Deletion jobs",
        "owner": "Privacy/Finance/Legal",
        "decision_needed": (
            "Analytics個票、Security Log、AI Artifact、成果データの保持期間を承認"
        ),
        "default_behavior": "自動削除Jobは無効、最小収集",
        "blocking": True,
    }

    catalog = strict_yaml.load_yaml(
        REPOSITORY_ROOT
        / "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
    )
    controls = {row["id"]: row for row in catalog["controls"]}
    assert controls["SEC-DATA-003"]["requirement"] == "SecretをDB/Repo/Logへ置かない"
    assert controls["SEC-DATA-004"]["requirement"] == (
        "Raw/SnapshotへSHA-256とVersionを記録"
    )
    assert controls["SEC-DATA-008"]["requirement"] == (
        "承認済み期間に基づき削除/匿名化"
    )
    assert controls["SEC-INFRA-006"]["requirement"] == (
        "Artifact bucketのpublic accessを遮断"
    )


def test_provider_snapshot_matches_contract_and_preserves_runtime_boundary(
    object_storage_contract: dict[str, Any],
) -> None:
    snapshot = strict_yaml.load_yaml(SNAPSHOT_FILE)
    assert snapshot["document"]["story_id"] == "ST-0202"
    assert snapshot["registry_resolution"]["image_reference"] == EXPECTED_REFERENCE
    assert (
        snapshot["registry_resolution"]["platform"]
        == (object_storage_contract["image"]["platform"])
    )
    assert snapshot["security_semantics"]["master_telemetry"] == "DISABLED"
    assert snapshot["bucket_contract"]["governing_open_decision"] == "OD-014"
    boundary = snapshot["verification_boundary"]
    assert boundary["registry_metadata_review"] == "RECORDED"
    assert boundary["authenticated_s3_fixture"] == "NOT_EXECUTED"
    assert boundary["object_lock_and_version_delete_regression"] == "NOT_EXECUTED"
    assert boundary["container_vulnerability_scan"] == "NOT_EXECUTED"
    assert boundary["formal_tst_014"] == "NOT_EXECUTED"
    assert boundary["effective_canonical_status"] == "UNCHANGED"


def test_rendered_service_contains_no_unreviewed_capability() -> None:
    service = _rendered_compose()["services"]["object-storage"]
    forbidden = {
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
    assert forbidden.isdisjoint(service)


def test_installed_compose_matches_the_shared_renderer_byte_for_byte() -> None:
    assert (REPOSITORY_ROOT / "docker-compose.yml").read_bytes() == (
        generator.render_compose(REPOSITORY_ROOT)
    )
