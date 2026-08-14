"""Fail-closed and adversarial contract tests for ST-0202."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from yaml.constructor import ConstructorError

from conftest import RejectContract, RejectProductionContract
from scripts import build_st0201_postgres_service as strict_yaml


def test_yaml_duplicate_mapping_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("image: one\nimage: two\n", encoding="utf-8")
    with pytest.raises(ConstructorError, match="found duplicate key 'image'"):
        strict_yaml.load_yaml(path)


@pytest.mark.parametrize(
    "content",
    [
        "shared: &shared\n  value: one\n",
        "shared: &shared\n  value: one\ncopy: *shared\n",
    ],
    ids=["anchor", "alias"],
)
def test_yaml_anchor_or_alias_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "alias.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(RuntimeError, match="anchors and aliases are forbidden"):
        strict_yaml.load_yaml(path)


def test_yaml_symlink_input_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    link = tmp_path / "link.yaml"
    target.write_text("value: safe\n", encoding="utf-8")
    link.symlink_to(target)
    with pytest.raises(RuntimeError, match="regular non-symlink file"):
        strict_yaml.load_yaml(link)


def test_unknown_top_level_contract_key_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["unexpected"] = {}
    reject_contract(mutable_contract, "object-storage contract keys differ")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "VALIDATED"),
        ("formal_verification", "PASS"),
        ("story_id", "ST-9999"),
    ],
)
def test_document_identity_or_status_promotion_is_rejected(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
) -> None:
    mutable_contract["document"][field] = value
    reject_contract(mutable_contract, rf"document\.{field} differs")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("reference",), "docker.io/chrislusf/seaweedfs:4.29"),
        (("tag",), "latest"),
        (("index_digest",), "sha256:" + "0" * 64),
        (("platform", "architecture"), "arm64"),
        (("platform", "manifest_digest"), "sha256:" + "0" * 64),
        (("platform", "config_digest"), "sha256:" + "0" * 64),
        (("expected_config", "labels", "org.opencontainers.image.revision"), "main"),
        (("expected_config", "declared_volume"), "/host/data"),
    ],
)
def test_image_identity_cannot_be_weakened(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    path: tuple[str, ...],
    value: str,
) -> None:
    target = mutable_contract["image"]
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    reject_contract(mutable_contract, r"image\.")


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("service", "init", False),
        ("service", "restart", "always"),
        ("service", "stop_grace_period", "1s"),
        ("port", "syntax", "short"),
        ("port", "host_ip", "0.0.0.0"),
        ("port", "default", 9000),
        ("port", "protocol", "udp"),
        ("config_secret", "source_variable", "AWS_SECRET_ACCESS_KEY"),
        ("config_secret", "mount_path", "/tmp/s3-config.json"),
        ("data", "mount_path", "/host/data"),
        ("network", "internal", False),
        ("network", "driver", "host"),
        ("healthcheck", "command", "curl http://0.0.0.0:8333/healthz"),
        ("healthcheck", "retries", 1),
    ],
)
def test_compose_security_or_readiness_field_cannot_drift(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    section: str,
    field: str,
    value: object,
) -> None:
    mutable_contract["compose"][section][field] = value
    reject_contract(mutable_contract, rf"compose\.{section}\.{field}")


def test_unknown_privileged_service_field_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["compose"]["service"]["privileged"] = True
    reject_contract(mutable_contract, "compose.service keys differ")


def test_raw_credential_environment_field_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["compose"]["service"]["environment"] = {
        "AWS_SECRET_ACCESS_KEY": "forbidden"
    }
    reject_contract(mutable_contract, "compose.service keys differ")


@pytest.mark.parametrize(
    ("index", "value"),
    [
        (0, "server"),
        (2, "-s3.config=/run/secrets/object_storage_s3_config"),
        (3, "-s3.port=9000"),
        (4, "-master.telemetry=true"),
        (5, "-webdav=true"),
        (6, "-admin.ui=true"),
        (7, "-s3.port.iceberg=8334"),
        (8, "-s3.allowDeleteBucketNotEmpty=true"),
    ],
)
def test_command_identity_or_hardening_cannot_be_weakened(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    index: int,
    value: str,
) -> None:
    mutable_contract["compose"]["command"][index] = value
    reject_contract(mutable_contract, rf"compose\.command\[{index}\] differs")


def test_command_flag_removal_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["compose"]["command"].pop()
    reject_contract(mutable_contract, "compose.command length differs")


def test_bool_as_integer_does_not_bypass_strict_comparison(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["compose"]["service"]["init"] = 1
    reject_contract(mutable_contract, "compose.service.init type differs")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("docker_host",), "tcp://127.0.0.1:2375"),
        (("expected_platform",), "linux/arm64"),
        (("expected_process_uid",), 0),
        (
            ("expected_image_labels", "org.opencontainers.image.revision"),
            "main",
        ),
        (("disposable_pull_policy",), "missing"),
        (("ephemeral_port_override", "tracked_artifact"), "PRESENT"),
        (("ephemeral_port_override", "creation_executable"), "mktemp"),
        (("ephemeral_port_override", "file_mode"), "0644"),
        (("ephemeral_port_override", "published"), "49152-65535"),
        (("ephemeral_port_override", "host_ip"), "0.0.0.0"),
        (("ephemeral_port_override", "sha256"), "0" * 64),
        (("local_project",), "default"),
        (("commands",), ["up", "down"]),
        (("authentication", "mode"), "ANONYMOUS"),
        (("authentication", "identity_count"), 0),
        (("authentication", "anonymous_access"), "ALLOWED"),
        (("authentication", "raw_credential_environment"), "ALLOWED"),
        (("readiness", "classification"), "AUTHENTICATED_ACCEPTANCE"),
        (("readiness", "authenticated_acceptance_required"), False),
        (("authenticated_fixture", "required"), False),
        (("authenticated_fixture", "execution_status"), "PASS"),
    ],
)
def test_runtime_contract_cannot_be_weakened_or_promoted(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    path: tuple[str, ...],
    value: object,
) -> None:
    target = mutable_contract["runtime"]
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    reject_contract(mutable_contract, r"runtime\.")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "public"),
        ("visibility", "PUBLIC"),
        ("object_lock_capability_at_creation", "OPTIONAL"),
        ("versioning", "SUSPENDED"),
        ("automatic_deletion", "ENABLED"),
        ("lifecycle_delete", "ALLOWED"),
        ("default_retention", "30_DAYS"),
        ("retention_period", "30_DAYS"),
        ("retention_hook", "OMITTED"),
        ("hash_mismatch", "ACCEPT"),
    ],
)
def test_bucket_integrity_privacy_or_retention_policy_cannot_be_weakened(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
) -> None:
    mutable_contract["runtime"]["bucket"][field] = value
    reject_contract(mutable_contract, rf"runtime\.bucket\.{field} differs")


def test_required_artifact_metadata_cannot_be_reduced(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["runtime"]["bucket"]["required_metadata"].remove("sha256")
    reject_contract(mutable_contract, "runtime.bucket.required_metadata length differs")


@pytest.mark.parametrize(
    "operation",
    [
        "create-lock-capable-private-bucket",
        "enable-and-read-versioning",
        "put-two-object-versions",
        "get-each-version-by-id",
        "round-trip-required-metadata",
        "reject-declared-hash-mismatch",
        "exercise-retention-hook-without-policy",
    ],
)
def test_authenticated_fixture_operation_cannot_be_omitted(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    operation: str,
) -> None:
    mutable_contract["runtime"]["authenticated_fixture"]["operations"].remove(operation)
    reject_contract(
        mutable_contract, "runtime.authenticated_fixture.operations length differs"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("production_use", "ALLOWED"),
        ("remote_object_storage", "ALLOWED"),
        ("raw_credential_environment", "ALLOWED"),
        ("anonymous_access", "ALLOWED"),
        ("default_retention", "30_DAYS"),
        ("retention_period", "30_DAYS"),
        ("lifecycle_delete", "ALLOWED"),
        ("automatic_deletion", "ENABLED"),
        ("od_014", "RESOLVED"),
        ("docker_runtime", "PASS"),
        ("authenticated_s3_fixture", "PASS"),
        ("object_lock_and_version_delete_regression", "PASS"),
        ("container_vulnerability_scan", "PASS"),
        ("formal_tst_014", "PASS"),
        ("effective_canonical_status", "VALIDATED"),
    ],
)
def test_boundary_cannot_be_promoted_or_od_014_silently_resolved(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
) -> None:
    mutable_contract["boundary"][field] = value
    reject_contract(mutable_contract, rf"boundary\.{field} differs")


def test_security_control_inventory_cannot_be_reduced(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["security_controls"].pop()
    reject_contract(mutable_contract, "security_controls length differs")


@pytest.mark.parametrize(
    ("section", "path", "value"),
    [
        ("document", ("story_id",), "ST-9999"),
        ("document", ("formal_verification",), "PASS"),
        (
            "image",
            ("reference",),
            "docker.io/chrislusf/seaweedfs:4.29",
        ),
        ("image", ("index_digest",), "sha256:" + "0" * 64),
        ("image", ("platform", "architecture"), "arm64"),
        ("compose", ("port", "host_ip"), "0.0.0.0"),
        (
            "compose",
            ("config_secret", "source_variable"),
            "AWS_SECRET_ACCESS_KEY",
        ),
        ("compose", ("network", "internal"), False),
        ("compose", ("command", 4), "-master.telemetry=true"),
        ("compose", ("healthcheck", "retries"), 1),
        ("runtime", ("authenticated_fixture", "execution_status"), "PASS"),
        ("runtime", ("bucket", "lifecycle_delete"), "ALLOWED"),
        ("security_controls", (0, "verification"), "NOT_EXECUTED"),
        ("boundary", ("od_014",), "RESOLVED"),
        ("boundary", ("lifecycle_delete",), "ALLOWED"),
        ("boundary", ("formal_tst_014",), "PASS"),
        ("boundary", ("effective_canonical_status",), "VALIDATED"),
    ],
)
def test_shared_generator_rejects_full_contract_mutations(
    mutable_contract: dict[str, Any],
    reject_production_contract: RejectProductionContract,
    section: str,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    target: Any = mutable_contract[section]
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    reject_production_contract(mutable_contract)


def test_shared_generator_rejects_unknown_top_level_contract_key(
    mutable_contract: dict[str, Any],
    reject_production_contract: RejectProductionContract,
) -> None:
    mutable_contract["unexpected"] = {}
    reject_production_contract(mutable_contract)


def test_shared_generator_rejects_removed_security_control(
    mutable_contract: dict[str, Any],
    reject_production_contract: RejectProductionContract,
) -> None:
    mutable_contract["security_controls"].pop()
    reject_production_contract(mutable_contract)
