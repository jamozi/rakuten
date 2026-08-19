#!/usr/bin/env python3
"""Strict offline verifier for one immutable ST-1505 staging manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, NoReturn

MAX_BYTES = 128 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
GIT_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
IMAGE_RE = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}\Z", re.ASCII)
ACCOUNT_RE = re.compile(r"[0-9]{12}\Z", re.ASCII)
REGION_RE = re.compile(r"[a-z]{2}-[a-z]+-[0-9]+\Z", re.ASCII)
ATTEMPT_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z",
    re.ASCII,
)

TOP_KEYS = {
    "schema",
    "environment",
    "attempt_id",
    "source_commit",
    "aws_account_id",
    "aws_region",
    "artifact",
    "supply_chain",
    "cluster_arn",
    "services",
    "migration",
    "target_groups",
    "health",
    "cloudfront_distribution_arns",
    "rollback",
}
SERVICE_KEYS = {"service_arn", "task_definition_arn", "image_uri"}
SERVICE_ROLES = {"public_web", "admin_web", "core_api", "worker_pool"}
ARTIFACT_KEYS = {"sha256"}
SUPPLY_KEYS = {
    "sbom_sha256",
    "vulnerability_scan_sha256",
    "provenance_sha256",
    "signature_sha256",
}
MIGRATION_KEYS = {
    "version",
    "compatibility",
    "task_definition_arn",
    "subnet_ids",
    "security_group_ids",
}
HEALTH_KEYS = {"public_readiness_url", "admin_readiness_url"}
ROLLBACK_KEYS = {"artifact_sha256", "task_definition_arns"}


class ManifestError(ValueError):
    pass


def fail(code: str) -> NoReturn:
    raise ManifestError(code)


def pairs_no_duplicates(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def exact_keys(
    value: object,
    expected: set[str],
    code: str,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        fail(code)
    return value


def exact_string(value: object, code: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        fail(code)
    return value


def digest(value: object, code: str) -> str:
    text = exact_string(value, code)
    if SHA256_RE.fullmatch(text) is None or text == "0" * 64:
        fail(code)
    return text


def arn(
    value: object,
    service: str,
    resource_prefix: str,
    account: str,
    region: str,
) -> str:
    text = exact_string(value, "INVALID_ARN")
    prefix = f"arn:aws:{service}:{region}:{account}:{resource_prefix}"
    if not text.startswith(prefix) or "*" in text:
        fail("INVALID_ARN")
    return text


def https_url(value: object, code: str) -> str:
    text = exact_string(value, code)
    if not text.startswith("https://") or any(
        character in text for character in "?#@"
    ):
        fail(code)
    return text


def read_manifest(path: Path) -> bytes:
    if path.is_symlink():
        fail("MANIFEST_SYMLINK_FORBIDDEN")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size < 2
            or info.st_size > MAX_BYTES
        ):
            fail("MANIFEST_FILE_INVALID")
        data = os.read(fd, MAX_BYTES + 1)
        if len(data) != info.st_size:
            fail("MANIFEST_FILE_CHANGED")
        return data
    finally:
        os.close(fd)


def _validate_identity(root: dict[str, Any]) -> tuple[str, str, str]:
    if root["schema"] != "RAOS_ST1505_DEPLOYMENT_MANIFEST_V1":
        fail("MANIFEST_SCHEMA_MISMATCH")
    if root["environment"] != "STAGING":
        fail("MANIFEST_ENVIRONMENT_MISMATCH")
    attempt_id = exact_string(root["attempt_id"], "ATTEMPT_ID_INVALID")
    if ATTEMPT_RE.fullmatch(attempt_id) is None:
        fail("ATTEMPT_ID_INVALID")
    source_commit = exact_string(
        root["source_commit"],
        "SOURCE_COMMIT_INVALID",
    )
    if GIT_SHA_RE.fullmatch(source_commit) is None:
        fail("SOURCE_COMMIT_INVALID")
    account = exact_string(root["aws_account_id"], "AWS_ACCOUNT_INVALID")
    region = exact_string(root["aws_region"], "AWS_REGION_INVALID")
    if (
        ACCOUNT_RE.fullmatch(account) is None
        or REGION_RE.fullmatch(region) is None
    ):
        fail("AWS_SCOPE_INVALID")
    return source_commit, account, region


def _validate_supply_chain(root: dict[str, Any]) -> str:
    artifact = exact_keys(
        root["artifact"],
        ARTIFACT_KEYS,
        "ARTIFACT_MISMATCH",
    )
    artifact_sha = digest(
        artifact["sha256"],
        "ARTIFACT_DIGEST_INVALID",
    )
    supply = exact_keys(
        root["supply_chain"],
        SUPPLY_KEYS,
        "SUPPLY_CHAIN_MISMATCH",
    )
    supply_values = [
        digest(supply[key], "SUPPLY_CHAIN_DIGEST_INVALID")
        for key in sorted(SUPPLY_KEYS)
    ]
    if len(set(supply_values)) != len(supply_values):
        fail("SUPPLY_CHAIN_DIGEST_COLLISION")
    return artifact_sha


def _validate_services(
    root: dict[str, Any],
    account: str,
    region: str,
) -> set[str]:
    cluster_arn = arn(
        root["cluster_arn"],
        "ecs",
        "cluster/",
        account,
        region,
    )
    cluster_name = cluster_arn.rsplit("/", 1)[-1]
    services = root["services"]
    if type(services) is not dict or set(services) != SERVICE_ROLES:
        fail("SERVICES_MISMATCH")

    task_definitions: set[str] = set()
    for role in sorted(SERVICE_ROLES):
        item = exact_keys(
            services[role],
            SERVICE_KEYS,
            "SERVICE_ENTRY_MISMATCH",
        )
        service = arn(
            item["service_arn"],
            "ecs",
            "service/",
            account,
            region,
        )
        if f"service/{cluster_name}/" not in service:
            fail("SERVICE_CLUSTER_MISMATCH")
        task_definition = arn(
            item["task_definition_arn"],
            "ecs",
            "task-definition/",
            account,
            region,
        )
        image = exact_string(item["image_uri"], "IMAGE_INVALID")
        if IMAGE_RE.fullmatch(image) is None:
            fail("IMAGE_INVALID")
        if task_definition in task_definitions:
            fail("SERVICE_TASK_DEFINITION_COLLISION")
        task_definitions.add(task_definition)
    return task_definitions


def _validate_migration(
    root: dict[str, Any],
    account: str,
    region: str,
    service_task_definitions: set[str],
) -> None:
    migration = exact_keys(
        root["migration"],
        MIGRATION_KEYS,
        "MIGRATION_MISMATCH",
    )
    exact_string(migration["version"], "MIGRATION_VERSION_INVALID")
    if migration["compatibility"] != "EXPAND_MIGRATE_CONTRACT_DEFERRED":
        fail("MIGRATION_COMPATIBILITY_INVALID")
    migration_task = arn(
        migration["task_definition_arn"],
        "ecs",
        "task-definition/",
        account,
        region,
    )
    if migration_task in service_task_definitions:
        fail("MIGRATION_TASK_COLLISION")

    network_lists = (
        ("subnet_ids", "subnet-"),
        ("security_group_ids", "sg-"),
    )
    for list_key, prefix in network_lists:
        values = migration[list_key]
        if (
            type(values) is not list
            or not values
            or len(values) != len(set(values))
        ):
            fail("MIGRATION_NETWORK_INVALID")
        if any(
            type(value) is not str
            or not value.startswith(prefix)
            or "*" in value
            for value in values
        ):
            fail("MIGRATION_NETWORK_INVALID")


def _validate_observation_targets(
    root: dict[str, Any],
    account: str,
    region: str,
) -> None:
    target_groups = root["target_groups"]
    if (
        type(target_groups) is not dict
        or set(target_groups) != {"public", "admin"}
    ):
        fail("TARGET_GROUPS_MISMATCH")
    for value in target_groups.values():
        arn(
            value,
            "elasticloadbalancing",
            "targetgroup/",
            account,
            region,
        )

    health = exact_keys(
        root["health"],
        HEALTH_KEYS,
        "HEALTH_MISMATCH",
    )
    public_url = https_url(
        health["public_readiness_url"],
        "HEALTH_URL_INVALID",
    )
    admin_url = https_url(
        health["admin_readiness_url"],
        "HEALTH_URL_INVALID",
    )
    if public_url == admin_url:
        fail("HEALTH_URL_COLLISION")

    distributions = root["cloudfront_distribution_arns"]
    if (
        type(distributions) is not dict
        or set(distributions) != {"public", "admin"}
    ):
        fail("CLOUDFRONT_MISMATCH")
    prefix = f"arn:aws:cloudfront::{account}:distribution/"
    for value in distributions.values():
        text = exact_string(value, "CLOUDFRONT_ARN_INVALID")
        if not text.startswith(prefix) or "*" in text:
            fail("CLOUDFRONT_ARN_INVALID")


def _validate_rollback(
    root: dict[str, Any],
    account: str,
    region: str,
    artifact_sha: str,
) -> None:
    rollback = exact_keys(
        root["rollback"],
        ROLLBACK_KEYS,
        "ROLLBACK_MISMATCH",
    )
    rollback_artifact = digest(
        rollback["artifact_sha256"],
        "ROLLBACK_DIGEST_INVALID",
    )
    if rollback_artifact == artifact_sha:
        fail("ROLLBACK_ARTIFACT_NOT_DISTINCT")
    rollback_tasks = rollback["task_definition_arns"]
    if (
        type(rollback_tasks) is not dict
        or set(rollback_tasks) != SERVICE_ROLES
    ):
        fail("ROLLBACK_TASKS_MISMATCH")
    for role, value in rollback_tasks.items():
        previous = arn(
            value,
            "ecs",
            "task-definition/",
            account,
            region,
        )
        current = root["services"][role]["task_definition_arn"]
        if previous == current:
            fail("ROLLBACK_TASK_NOT_DISTINCT")


def validate(payload: object) -> dict[str, Any]:
    root = exact_keys(
        payload,
        TOP_KEYS,
        "MANIFEST_TOP_LEVEL_MISMATCH",
    )
    _, account, region = _validate_identity(root)
    artifact_sha = _validate_supply_chain(root)
    task_definitions = _validate_services(root, account, region)
    _validate_migration(root, account, region, task_definitions)
    _validate_observation_targets(root, account, region)
    _validate_rollback(root, account, region, artifact_sha)
    return root


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-commit", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        expected_sha = digest(
            args.expected_sha256,
            "EXPECTED_DIGEST_INVALID",
        )
        expected_commit = exact_string(
            args.expected_commit,
            "EXPECTED_COMMIT_INVALID",
        )
        if GIT_SHA_RE.fullmatch(expected_commit) is None:
            fail("EXPECTED_COMMIT_INVALID")
        data = read_manifest(args.manifest)
        if hashlib.sha256(data).hexdigest() != expected_sha:
            fail("MANIFEST_DIGEST_MISMATCH")
        try:
            payload = json.loads(
                data.decode("utf-8", errors="strict"),
                object_pairs_hook=pairs_no_duplicates,
                parse_constant=lambda _: fail("JSON_NONFINITE_NUMBER"),
            )
        except (UnicodeError, json.JSONDecodeError):
            fail("MANIFEST_JSON_INVALID")
        root = validate(payload)
        if root["source_commit"] != expected_commit:
            fail("SOURCE_COMMIT_MISMATCH")
        if canonical_bytes(root) != data:
            fail("MANIFEST_NOT_CANONICAL")
    except (ManifestError, OSError) as error:
        message = (
            str(error)
            if isinstance(error, ManifestError)
            else "MANIFEST_IO_FAILURE"
        )
        print(message)
        return 2
    print(
        json.dumps(
            {
                "schema": (
                    "RAOS_ST1505_DEPLOYMENT_MANIFEST_RECEIPT_V1"
                ),
                "environment": "STAGING",
                "manifest_sha256": expected_sha,
                "source_commit": root["source_commit"],
                "external_write_count": 0,
                "production_action_count": 0,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
