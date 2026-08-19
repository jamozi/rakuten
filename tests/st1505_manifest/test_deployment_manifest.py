from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/staging_deployment_manifest.py"
SPEC = importlib.util.spec_from_file_location("st1505_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ACCOUNT = "123456789012"
REGION = "ap-northeast-1"
CLUSTER = "raos-staging"


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def manifest() -> dict[str, object]:
    services = {}
    rollback = {}
    for index, role in enumerate(
        ("public_web", "admin_web", "core_api", "worker_pool"), 1
    ):
        services[role] = {
            "service_arn": (
                f"arn:aws:ecs:{REGION}:{ACCOUNT}:service/{CLUSTER}/{role}"
            ),
            "task_definition_arn": (
                f"arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/{role}:{index}"
            ),
            "image_uri": (
                f"123456789012.dkr.ecr.{REGION}.amazonaws.com/{role}"
                f"@sha256:{_digest(role)}"
            ),
        }
        rollback[role] = (
            f"arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/{role}:{index + 10}"
        )
    return {
        "schema": "RAOS_ST1505_DEPLOYMENT_MANIFEST_V1",
        "environment": "STAGING",
        "attempt_id": "staging-20260819-001",
        "source_commit": "1" * 40,
        "aws_account_id": ACCOUNT,
        "aws_region": REGION,
        "artifact": {"sha256": _digest("artifact")},
        "supply_chain": {
            "sbom_sha256": _digest("sbom"),
            "vulnerability_scan_sha256": _digest("scan"),
            "provenance_sha256": _digest("provenance"),
            "signature_sha256": _digest("signature"),
        },
        "cluster_arn": f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/{CLUSTER}",
        "services": services,
        "migration": {
            "version": "202608190001_expand",
            "compatibility": "EXPAND_MIGRATE_CONTRACT_DEFERRED",
            "task_definition_arn": (
                f"arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/migration:1"
            ),
            "subnet_ids": ["subnet-111", "subnet-222"],
            "security_group_ids": ["sg-111"],
        },
        "target_groups": {
            "public": (
                f"arn:aws:elasticloadbalancing:{REGION}:{ACCOUNT}:"
                "targetgroup/public/111"
            ),
            "admin": (
                f"arn:aws:elasticloadbalancing:{REGION}:{ACCOUNT}:"
                "targetgroup/admin/222"
            ),
        },
        "health": {
            "public_readiness_url": "https://staging.example.invalid/ready",
            "admin_readiness_url": "https://admin-staging.example.invalid/ready",
        },
        "cloudfront_distribution_arns": {
            "public": f"arn:aws:cloudfront::{ACCOUNT}:distribution/PUBLIC123",
            "admin": f"arn:aws:cloudfront::{ACCOUNT}:distribution/ADMIN456",
        },
        "rollback": {
            "artifact_sha256": _digest("rollback"),
            "task_definition_arns": rollback,
        },
    }


def test_valid_manifest_is_accepted_and_canonical() -> None:
    value = manifest()
    assert MODULE.validate(value) is value
    encoded = MODULE.canonical_bytes(value)
    assert json.loads(encoded) == value


def test_unknown_key_fails_closed() -> None:
    value = manifest()
    value["unexpected"] = 1
    with pytest.raises(
        MODULE.ManifestError, match="MANIFEST_TOP_LEVEL_MISMATCH"
    ):
        MODULE.validate(value)


def test_duplicate_json_key_fails_closed() -> None:
    with pytest.raises(MODULE.ManifestError, match="JSON_DUPLICATE_KEY"):
        MODULE.pairs_no_duplicates([("schema", "a"), ("schema", "b")])


def test_production_environment_is_rejected() -> None:
    value = manifest()
    value["environment"] = "PRODUCTION"
    with pytest.raises(
        MODULE.ManifestError, match="MANIFEST_ENVIRONMENT_MISMATCH"
    ):
        MODULE.validate(value)


def test_mutable_image_tag_is_rejected() -> None:
    value = manifest()
    value["services"]["public_web"]["image_uri"] = (
        "example.invalid/public:latest"
    )
    with pytest.raises(MODULE.ManifestError, match="IMAGE_INVALID"):
        MODULE.validate(value)


def test_wildcard_resource_is_rejected() -> None:
    value = manifest()
    value["services"]["admin_web"]["service_arn"] = (
        f"arn:aws:ecs:{REGION}:{ACCOUNT}:service/{CLUSTER}/*"
    )
    with pytest.raises(MODULE.ManifestError, match="INVALID_ARN"):
        MODULE.validate(value)


def test_account_or_cluster_mismatch_is_rejected() -> None:
    value = manifest()
    value["services"]["core_api"]["service_arn"] = (
        f"arn:aws:ecs:{REGION}:999999999999:service/{CLUSTER}/core_api"
    )
    with pytest.raises(MODULE.ManifestError, match="INVALID_ARN"):
        MODULE.validate(value)

    value = manifest()
    value["services"]["core_api"]["service_arn"] = (
        f"arn:aws:ecs:{REGION}:{ACCOUNT}:service/other/core_api"
    )
    with pytest.raises(
        MODULE.ManifestError, match="SERVICE_CLUSTER_MISMATCH"
    ):
        MODULE.validate(value)


def test_destructive_migration_classification_is_rejected() -> None:
    value = manifest()
    value["migration"]["compatibility"] = "CONTRACT_NOW"
    with pytest.raises(
        MODULE.ManifestError, match="MIGRATION_COMPATIBILITY_INVALID"
    ):
        MODULE.validate(value)


def test_current_and_rollback_are_distinct() -> None:
    value = manifest()
    value["rollback"]["artifact_sha256"] = value["artifact"]["sha256"]
    with pytest.raises(
        MODULE.ManifestError, match="ROLLBACK_ARTIFACT_NOT_DISTINCT"
    ):
        MODULE.validate(value)

    value = manifest()
    value["rollback"]["task_definition_arns"]["worker_pool"] = (
        value["services"]["worker_pool"]["task_definition_arn"]
    )
    with pytest.raises(
        MODULE.ManifestError, match="ROLLBACK_TASK_NOT_DISTINCT"
    ):
        MODULE.validate(value)


def test_supply_chain_references_must_be_distinct() -> None:
    value = manifest()
    value["supply_chain"]["signature_sha256"] = (
        value["supply_chain"]["provenance_sha256"]
    )
    with pytest.raises(
        MODULE.ManifestError, match="SUPPLY_CHAIN_DIGEST_COLLISION"
    ):
        MODULE.validate(value)
