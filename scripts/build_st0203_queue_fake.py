#!/usr/bin/env python3
"""Validate ST-0203 queue semantics and build its evidence manifest."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import yaml

try:
    from scripts import build_st0201_postgres_service as shared
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0203/contracts/local-queue.v1.yaml")
MANIFEST_PATH: Final = Path("changes/st-0203/manifest.yaml")
PREDECESSOR_PATH: Final = Path("changes/st-0202/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0203_queue_fake.py")
SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st0203_queue_fake.py"
)

PINNED_CANONICAL_INPUTS: Final = {
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
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/08_codex/RAOS_14_codex_implementation_handbook_v1.0.md": (
        "501858e7cdb47db5d2987f6e3d778da4fb8d72224b4380790dcd91ffcac615b2"
    ),
}

CANONICAL_CONTRACTS: Final = {
    "job_message": {
        "uri": (
            "repo://contracts/raos-v0.4/contracts/schemas/common/"
            "job-message.schema.json"
        ),
        "sha256": ("cdb8e8094d4fa74843c26ea453354df7083bc41a6f165220ddd0e263e37db8d5"),
    },
    "job_catalog": {
        "uri": "repo://contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml",
        "sha256": ("70a9926f1ac64bd47ce084c28ebb08792d63b07feb5ced85e40377815ba3aeb1"),
    },
    "job_state": {
        "uri": "repo://contracts/raos-v0.4/job-state.v1.yaml",
        "sha256": ("9f6d39a784cb00d6ec5159fe45eddaf92d661a939b63cbcad6f33c899faab87a"),
    },
}

EXPECTED_PREDECESSOR_SHA256: Final = (
    "419d4de580e1755651056c335011a4200f25c7b40a4d868111dbd6131666f217"
)

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-0203/README.md"),
    Path("docs/execplans/ST-0203.md"),
    Path("docs/worklogs/ST-0203.md"),
    GENERATOR_PATH,
    Path("python/raos/ports/__init__.py"),
    Path("python/raos/ports/queue.py"),
    Path("python/raos/adapters/__init__.py"),
    Path("python/raos/adapters/queue_fake.py"),
    Path("tests/st0203/conftest.py"),
    Path("tests/st0203/test_port_contract.py"),
    Path("tests/st0203/test_queue_fake.py"),
    Path("tests/st0203/test_contract.py"),
    Path("tests/st0203/test_generation.py"),
    Path("tests/st0203/test_negative_cases.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("Makefile"),
    Path("README.md"),
    PREDECESSOR_PATH,
    Path("contracts/raos-v0.4/contracts/schemas/common/job-message.schema.json"),
    Path("contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"),
    Path("contracts/raos-v0.4/job-state.v1.yaml"),
)

EXPECTED_CONTRACT: Final = {
    "document": {
        "id": "RAOS-LOCAL-QUEUE-001",
        "version": "1.0.0",
        "story_id": "ST-0203",
        "status": "LOCAL_AND_CI_CANDIDATE",
        "formal_verification": "NOT_EXECUTED",
    },
    "story": {
        "dependency": "ST-0102",
        "objective": "REPRODUCE_AT_LEAST_ONCE_DELIVERY",
        "deliverables": [
            "PROVIDER_NEUTRAL_QUEUE_PORT",
            "DETERMINISTIC_QUEUE_FAKE",
            "DUPLICATE_AND_OUT_OF_ORDER_FIXTURES",
        ],
        "required_suite": "TST-013",
        "open_decisions": [],
    },
    "canonical_contracts": CANONICAL_CONTRACTS,
    "message": {
        "provider_type_exposure": "FORBIDDEN",
        "payload": "GENERIC_CALLER_OWNED",
        "identity_fields": ["message_id", "idempotency_key"],
        "scheduling_fields": ["queue_name", "available_at", "max_attempts"],
        "timestamps": "TIMEZONE_AWARE_REQUIRED",
        "max_attempts": {"minimum": 1, "maximum": 50},
    },
    "port": {
        "uri": "repo://python/raos/ports/queue.py",
        "operations": ["send", "receive", "acknowledge", "retry", "extend_lease"],
        "receipt_handle": {
            "scoped_to_delivery_occurrence": True,
            "stale_or_unknown": "REJECT",
        },
        "consumer_idempotency": "REQUIRED_BUT_OUTSIDE_QUEUE_PORT",
    },
    "fake": {
        "uri": "repo://python/raos/adapters/queue_fake.py",
        "clock": "EXPLICIT_MANUAL_AWARE_DATETIME",
        "background_threads": "FORBIDDEN",
        "sleeps": "FORBIDDEN",
        "network": "FORBIDDEN",
        "provider_sdk": "FORBIDDEN",
        "time_arithmetic_overflow": "REJECT_WITHOUT_STATE_MUTATION",
        "default_order": "FIFO_BY_ENQUEUE_SEQUENCE_WHEN_AVAILABLE",
        "duplicate_injection": {
            "operation": "inject_duplicate",
            "preserves_message_id": True,
            "preserves_idempotency_key": True,
            "distinct_receipt_per_occurrence": True,
        },
        "out_of_order_injection": {
            "operation": "inject_out_of_order",
            "exact_pending_multiset_required": True,
        },
        "lease": {
            "positive_duration_required": True,
            "expiry": "REDELIVER_WITH_NEW_RECEIPT",
            "renew_from_current_clock": True,
        },
        "retry": {
            "non_negative_delay_required": True,
            "delivery_attempt_increments_on_receive": True,
            "prior_receipt_becomes_stale": True,
        },
        "dlq": {
            "inspectable": True,
            "on_retry_at_max_attempts": True,
            "on_lease_expiry_at_max_attempts": True,
            "payload_logging": "FORBIDDEN",
        },
    },
    "security": {
        "controls": [
            {
                "id": "SEC-APP-011",
                "relationship": "FUTURE_CONSUMER_IDEMPOTENCY_OBLIGATION",
            },
            {
                "id": "SEC-INFRA-008",
                "relationship": "DEFERRED_TO_PROVIDER_ADAPTER_AND_IAM_STORY",
            },
        ],
        "secret_in_message": "PROHIBITED_BY_CANONICAL_JOB_CATALOG",
        "production_credentials": "NOT_USED",
    },
    "verification": {
        "required_suite": "TST-013",
        "local_command": (
            "uv run --locked --no-sync pytest -p no:cacheprovider -q tests/st0203"
        ),
        "required_behaviors": [
            "FIFO_DEFAULT",
            "DELAYED_VISIBILITY",
            "DUPLICATE_INJECTION",
            "OUT_OF_ORDER_INJECTION",
            "LEASE_EXPIRY_REDELIVERY",
            "LEASE_EXTENSION",
            "RETRY_DELAY",
            "DLQ_AT_MAX_ATTEMPTS",
            "STALE_AND_UNKNOWN_RECEIPT_REJECTION",
            "DURATION_OVERFLOW_STATE_PRESERVATION",
        ],
        "formal_environment": "CI",
        "local_result_can_promote_formal_suite": False,
    },
    "predecessor": {
        "manifest_uri": f"repo://{PREDECESSOR_PATH.as_posix()}",
        "story_id": "ST-0202",
        "sha256": EXPECTED_PREDECESSOR_SHA256,
    },
    "boundary": {
        "environment": "LOCAL_AND_CI_FAKE_ONLY",
        "production_use": "FORBIDDEN",
        "external_broker": "NOT_IMPLEMENTED",
        "provider_adapter": "NOT_IMPLEMENTED",
        "worker_runtime": "NOT_IMPLEMENTED",
        "durable_persistence": "NOT_IMPLEMENTED",
        "consumer_idempotency_store": "NOT_IMPLEMENTED",
        "formal_tst_013": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    },
}


def _repo_path(uri: str) -> Path:
    if not uri.startswith("repo://"):
        raise RuntimeError(f"expected repo URI: {uri}")
    relative = Path(uri.removeprefix("repo://"))
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"unsafe repo URI: {uri}")
    return relative


def _assert_digest(root: Path, relative: Path, expected: str, *, label: str) -> None:
    path = shared._repository_regular_file(root, relative, label)
    actual = shared.sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} digest drift: {relative}: {actual}")


def assert_pinned_inputs(root: Path = REPO_ROOT) -> None:
    for name, digest in PINNED_CANONICAL_INPUTS.items():
        _assert_digest(root, Path(name), digest, label="canonical input")
    for record in CANONICAL_CONTRACTS.values():
        _assert_digest(
            root,
            _repo_path(str(record["uri"])),
            str(record["sha256"]),
            label="canonical queue contract",
        )
    _assert_digest(
        root,
        PREDECESSOR_PATH,
        EXPECTED_PREDECESSOR_SHA256,
        label="predecessor manifest",
    )


def load_and_validate_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    assert_pinned_inputs(root)
    path = shared._repository_regular_file(root, CONTRACT_PATH, "ST-0203 contract")
    loaded = shared.load_yaml(path)
    if not isinstance(loaded, dict):
        raise RuntimeError("ST-0203 contract must be a mapping")
    shared._require_exact(loaded, EXPECTED_CONTRACT, "ST-0203 contract")
    return dict(loaded)


def _artifact_record(root: Path, relative: Path) -> dict[str, Any]:
    path = shared._repository_regular_file(root, relative, "source artifact")
    content = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": shared.sha256_bytes(content),
    }


def render_manifest(root: Path = REPO_ROOT) -> bytes:
    contract = load_and_validate_contract(root)
    artifacts = [_artifact_record(root, path) for path in SOURCE_ARTIFACT_PATHS]
    manifest = {
        "document": {
            "id": "RAOS-LOCAL-QUEUE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0203",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_uri": SOURCE_CONTRACT_URI,
            "canonical_inputs": [
                {"uri": f"repo://{name}", "sha256": digest}
                for name, digest in PINNED_CANONICAL_INPUTS.items()
            ],
            "canonical_contracts": CANONICAL_CONTRACTS,
            "predecessor_manifest": {
                "uri": f"repo://{PREDECESSOR_PATH.as_posix()}",
                "sha256": EXPECTED_PREDECESSOR_SHA256,
                "story_id": "ST-0202",
            },
        },
        "evidence_chain": {"stories": ["ST-0201", "ST-0202", "ST-0203"]},
        "source_artifact_count": len(artifacts),
        "source_artifacts": artifacts,
        "generated_artifact_count": 0,
        "generated_artifacts": [],
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": dict(contract["boundary"]),
    }
    return yaml.dump(
        manifest,
        Dumper=shared.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def install_manifest(content: bytes, root: Path = REPO_ROOT) -> None:
    if MANIFEST_PATH.is_absolute() or any(
        part in {"", ".", ".."} for part in MANIFEST_PATH.parts
    ):
        raise RuntimeError("unsafe ST-0203 manifest path")
    try:
        root_metadata = root.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("manifest root must exist") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("manifest root must be a real directory")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    temporary_name: str | None = None
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for part in MANIFEST_PATH.parent.parts:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        parent_descriptor = descriptors[-1]
        try:
            target_metadata = os.stat(
                MANIFEST_PATH.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None and not stat.S_ISREG(target_metadata.st_mode):
            raise RuntimeError("manifest target must be a regular non-symlink file")

        for suffix in range(100):
            candidate = f".{MANIFEST_PATH.name}.st0203-{os.getpid()}-{suffix}"
            try:
                output_descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            raise RuntimeError("cannot allocate a safe manifest staging file")

        try:
            view = memoryview(content)
            while view:
                written = os.write(output_descriptor, view)
                if written <= 0:
                    raise RuntimeError("short write while staging ST-0203 manifest")
                view = view[written:]
            os.fsync(output_descriptor)
        finally:
            os.close(output_descriptor)

        os.replace(
            temporary_name,
            MANIFEST_PATH.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    finally:
        if descriptors:
            parent_descriptor = descriptors[-1]
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
                except FileNotFoundError:
                    pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def check_generated(root: Path = REPO_ROOT) -> None:
    expected = render_manifest(root)
    target = shared._repository_regular_file(root, MANIFEST_PATH, "ST-0203 manifest")
    if target.stat().st_mode & 0o022:
        raise RuntimeError("ST-0203 manifest cannot be group/world writable")
    if target.read_bytes() != expected:
        raise RuntimeError("generated ST-0203 manifest drift")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the contract and manifest without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        if arguments.check:
            check_generated()
            mode = "check"
        else:
            install_manifest(render_manifest())
            mode = "install"
    except (OSError, RuntimeError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "generated_artifacts": 1,
                "mode": mode,
                "status": "PASS",
                "story_id": "ST-0203",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
